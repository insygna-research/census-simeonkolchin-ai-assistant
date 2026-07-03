"""
Unified integration source store.
Manages YouGile tokens and Outline servers with internal/external categorization.
"""

import json
import uuid
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

VALID_TYPES = ("yougile", "outline")
VALID_CATEGORIES = ("internal", "external")
_DEFAULT_PATH = "data/integrations.json"


class IntegrationStore:
    """CRUD for integration sources persisted in a JSON file."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sources: List[Dict[str, Any]] = []
        self._load()
        self._migrate_legacy()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._sources = data if isinstance(data, list) else data.get("sources", [])
            except Exception as e:
                logger.error(f"Failed to load integrations: {e}")
                self._sources = []

    def _save(self):
        self.path.write_text(
            json.dumps(self._sources, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _migrate_legacy(self):
        """Auto-migrate from old yougile_tokens.json if present."""
        old_path = Path("data/yougile_tokens.json")
        if not old_path.exists():
            return
        try:
            old_tokens = json.loads(old_path.read_text(encoding="utf-8"))
            if not old_tokens:
                return
            existing_tokens = {
                s.get("config", {}).get("token")
                for s in self._sources
                if s.get("type") == "yougile"
            }
            migrated = 0
            for t in old_tokens:
                if t.get("token") and t["token"] not in existing_tokens:
                    self._sources.append({
                        "id": t.get("id", str(uuid.uuid4())),
                        "type": "yougile",
                        "name": t.get("name", "Migrated"),
                        "category": "internal",
                        "config": {"token": t["token"]},
                        "enabled": t.get("enabled", True),
                    })
                    migrated += 1
            if migrated:
                self._save()
                old_path.rename(old_path.with_suffix(".json.bak"))
                logger.info(f"Migrated {migrated} YouGile tokens from legacy store")
        except Exception as e:
            logger.warning(f"Legacy migration failed: {e}")

    # ── Read ────────────────────────────────────────────────────

    def list_sources(
        self,
        source_type: Optional[str] = None,
        category: Optional[str] = None,
        enabled_only: bool = False,
        hide_secrets: bool = True,
    ) -> List[Dict[str, Any]]:
        result = []
        for s in self._sources:
            if source_type and s.get("type") != source_type:
                continue
            if category and s.get("category") != category:
                continue
            if enabled_only and not s.get("enabled", True):
                continue
            item = {
                "id": s["id"],
                "type": s["type"],
                "name": s["name"],
                "category": s.get("category", "internal"),
                "enabled": s.get("enabled", True),
            }
            if not hide_secrets:
                item["config"] = s.get("config", {})
            else:
                cfg = s.get("config", {})
                item["config"] = {}
                if "url" in cfg:
                    item["config"]["url"] = cfg["url"]
            result.append(item)
        return result

    def get_sources_for_agent(
        self,
        source_type: str,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return enabled sources with full config (secrets included) for agent init."""
        return [
            {
                "name": s["name"],
                "category": s.get("category", "internal"),
                **s.get("config", {}),
            }
            for s in self._sources
            if s.get("type") == source_type
            and s.get("enabled", True)
            and (category is None or s.get("category") == category)
        ]

    # ── Write ───────────────────────────────────────────────────

    def add_source(
        self,
        source_type: str,
        name: str,
        category: str,
        config: Dict[str, str],
    ) -> Dict[str, Any]:
        if source_type not in VALID_TYPES:
            raise ValueError(f"Invalid type: {source_type}. Must be one of {VALID_TYPES}")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")

        entry = {
            "id": str(uuid.uuid4()),
            "type": source_type,
            "name": name,
            "category": category,
            "config": config,
            "enabled": True,
        }
        self._sources.append(entry)
        self._save()
        logger.info(f"Added {source_type} source '{name}' ({category})")
        return {"id": entry["id"], "type": source_type, "name": name,
                "category": category, "enabled": True}

    def update_source(
        self,
        source_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        category: Optional[str] = None,
    ) -> bool:
        for s in self._sources:
            if s["id"] == source_id:
                if enabled is not None:
                    s["enabled"] = enabled
                if name is not None:
                    s["name"] = name
                if category is not None:
                    if category not in VALID_CATEGORIES:
                        return False
                    s["category"] = category
                self._save()
                return True
        return False

    def delete_source(self, source_id: str) -> bool:
        before = len(self._sources)
        self._sources = [s for s in self._sources if s["id"] != source_id]
        if len(self._sources) < before:
            self._save()
            return True
        return False

    # ── Helpers for agent ───────────────────────────────────────

    def get_yougile_tokens(self) -> List[Dict[str, str]]:
        """Backward-compatible: return enabled YouGile tokens as [{name, token, category}]."""
        return [
            {"name": s["name"], "token": s.get("config", {}).get("token", ""),
             "category": s.get("category", "internal")}
            for s in self._sources
            if s.get("type") == "yougile" and s.get("enabled", True)
            and s.get("config", {}).get("token")
        ]

    def get_outline_servers(self) -> List[Dict[str, str]]:
        """Return enabled Outline servers as [{name, url, api_token, category}]."""
        return [
            {"name": s["name"],
             "url": s.get("config", {}).get("url", ""),
             "api_token": s.get("config", {}).get("api_token", ""),
             "category": s.get("category", "internal")}
            for s in self._sources
            if s.get("type") == "outline" and s.get("enabled", True)
            and s.get("config", {}).get("url") and s.get("config", {}).get("api_token")
        ]

    def _describe_source(self, s: dict) -> str:
        cfg = s.get("config", {})
        parts = [f'  - {s["name"]} ({s["type"]})']
        if cfg.get("url"):
            parts.append(f'URL: {cfg["url"]}')
        return " | ".join(parts)

    def describe_for_prompt(self) -> str:
        """Generate a detailed description of available sources for the system prompt."""
        enabled = [s for s in self._sources if s.get("enabled")]
        if not enabled:
            return "Источники не настроены"

        internal = [s for s in enabled if s.get("category") == "internal"]
        external = [s for s in enabled if s.get("category") == "external"]

        lines = []
        if internal:
            lines.append("Мои источники (internal):")
            for s in internal:
                lines.append(self._describe_source(s))
        if external:
            lines.append("Внешние источники (external):")
            for s in external:
                lines.append(self._describe_source(s))

        lines.append("")
        urls = [cfg.get("url") for s in enabled if (cfg := s.get("config", {})).get("url")]
        if urls:
            lines.append(f"Подключённые URL: {', '.join(urls)}")
            lines.append("Если пользователь даёт URL которого нет в списке — сервер НЕ подключён, сообщи об этом.")

        return "\n".join(lines)
