"""
YouGile multi-token management with JSON file storage.
"""

import json
import uuid
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_PATH = "data/yougile_tokens.json"


class YouGileTokenStore:
    """CRUD for YouGile API tokens persisted in a JSON file."""

    def __init__(self, path: str = _DEFAULT_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._tokens = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Failed to load YouGile tokens: {e}")
                self._tokens = []
        else:
            self._tokens = []

    def _save(self):
        self.path.write_text(
            json.dumps(self._tokens, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_tokens(self, include_secret: bool = False) -> List[Dict[str, Any]]:
        result = []
        for t in self._tokens:
            item = {"id": t["id"], "name": t["name"], "enabled": t["enabled"]}
            if include_secret:
                item["token"] = t["token"]
            result.append(item)
        return result

    def add_token(self, name: str, token: str, enabled: bool = True) -> Dict[str, Any]:
        entry = {
            "id": str(uuid.uuid4()),
            "name": name,
            "token": token,
            "enabled": enabled,
        }
        self._tokens.append(entry)
        self._save()
        return {"id": entry["id"], "name": name, "enabled": enabled}

    def update_token(self, token_id: str, enabled: Optional[bool] = None, name: Optional[str] = None) -> bool:
        for t in self._tokens:
            if t["id"] == token_id:
                if enabled is not None:
                    t["enabled"] = enabled
                if name is not None:
                    t["name"] = name
                self._save()
                return True
        return False

    def delete_token(self, token_id: str) -> bool:
        before = len(self._tokens)
        self._tokens = [t for t in self._tokens if t["id"] != token_id]
        if len(self._tokens) < before:
            self._save()
            return True
        return False

    def get_enabled_tokens(self) -> List[Dict[str, str]]:
        """Return list of {name, token} for all enabled tokens."""
        return [
            {"name": t["name"], "token": t["token"]}
            for t in self._tokens
            if t["enabled"]
        ]
