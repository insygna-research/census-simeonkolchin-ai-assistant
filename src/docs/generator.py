"""
Document generator: template + section markers + isolated LLM prompts.

The key design goal is **structural stability**:
- The document template owns the section order and headings.
- Each section is delimited by HTML comments (``<!-- SECTION: id -->``).
- Unchanged sections are copied verbatim from the previous release.
- Only sections with real changes are regenerated — and even then,
  the LLM only produces the *body* of the section, never the heading.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.config import settings
from src.docs.models import (
    ChangeCategory,
    ChangeReport,
    DocSection,
    DocTemplate,
)
from src.tools.outline_tool import OutlineTool

logger = logging.getLogger(__name__)

# Regex to find section markers:  <!-- SECTION: id -->
_SECTION_RE = re.compile(r"<!--\s*SECTION:\s*(\w+)\s*-->")

# Mapping of ChangeCategory → section_id
_CATEGORY_TO_SECTION: Dict[ChangeCategory, str] = {
    ChangeCategory.API: "api_changes",
    ChangeCategory.CONFIG: "config_changes",
    ChangeCategory.DEPENDENCY: "dependencies",
    ChangeCategory.INFRASTRUCTURE: "infrastructure",
    ChangeCategory.BUGFIX: "bug_fixes",
}


class DocumentGenerator:
    """
    Generates a release document from a ``ChangeReport``.

    Usage::

        generator = DocumentGenerator(outline_tool, llm_client)
        doc_id   = await generator.generate(report)
    """

    def __init__(self, outline_tool: OutlineTool, llm_client: Any):
        self._outline = outline_tool
        self._llm = llm_client

    # ── public API ─────────────────────────────────────────────

    async def generate(
        self,
        report: ChangeReport,
        on_progress: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Main entry-point.

        Returns ``{"document_id": ..., "url": ..., "title": ...}`` — the
        Outline document that was created (or updated).
        """

        # 1. Load / build template
        template = await self._load_template()

        if on_progress:
            await on_progress({
                "phase": "generation",
                "status": "progress",
                "sections_total": len(template.sections),
            })

        # 2. Build a map of section_id → list of change facts
        section_facts = self._build_section_facts(report)

        # 3. Regenerate sections that have changes
        for idx, section in enumerate(template.sections):
            if on_progress:
                await on_progress({
                    "phase": "generation",
                    "status": "progress",
                    "section": section.title,
                    "current": idx + 1,
                    "total": len(template.sections),
                })

            facts = section_facts.get(section.section_id, [])
            if facts and section.is_dynamic:
                section.content = await self._generate_section(section, facts)
            elif not facts and section.section_id == "overview":
                # Always regenerate overview (it is a summary)
                section.content = await self._generate_section(section, [
                    self._build_overview_facts(report),
                ])

        # 4. Assemble final document
        title = settings.DOCS_TITLE_TEMPLATE.format(date=_today_slug())
        markdown = self._assemble_document(title, template.sections)

        # 5. Save to Outline
        result = await self._save_to_outline(title, markdown)
        return result

    # ── template loading ───────────────────────────────────────

    async def _load_template(self) -> DocTemplate:
        """Try to load from Outline; fall back to the built-in default."""
        collection_id = settings.DOCS_TEMPLATE_COLLECTION_ID
        if collection_id:
            try:
                docs = await self._outline.alist_documents(collection_id, limit=5)
                if docs.get("documents"):
                    doc = docs["documents"][0]
                    full = await self._outline.aget_document(doc["id"])
                    if full.get("success"):
                        return DocTemplate(
                            template_id=doc["id"],
                            title=full.get("title", "Release Notes"),
                            sections=self._parse_sections(full.get("text", "")),
                            version=doc.get("updated_at", "v1"),
                        )
            except Exception:
                logger.warning("Could not load template from Outline, using default")

        # Fallback
        text = settings.DOCS_DEFAULT_TEMPLATE
        return DocTemplate(
            template_id="default",
            title="Release Notes",
            sections=self._parse_sections(text),
        )

    def _parse_sections(self, raw_text: str) -> List[DocSection]:
        """
        Split a markdown document into sections based on ``<!-- SECTION: id -->``
        markers.  Each section body includes everything from its marker up to the
        next marker (or EOF).
        """
        sections: List[DocSection] = []
        parts = _SECTION_RE.split(raw_text)

        if not parts:
            return sections

        # parts[0] is text before the first marker (usually the top-level heading)
        # After that pairs: (section_id, body)

        for i in range(1, len(parts) - 1, 2):
            sid = parts[i]
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""

            # Derive heading and category
            heading = self._derive_heading(body, sid)
            cat = _section_id_to_category(sid)
            is_dynamic = sid not in ("overview",)

            sections.append(DocSection(
                section_id=sid,
                title=heading,
                content=body,
                is_dynamic=is_dynamic,
                change_category=cat,
            ))

        return sections

    @staticmethod
    def _derive_heading(body: str, fallback_id: str) -> str:
        """Extract the first markdown heading from body, or use a fallback."""
        m = re.search(r"^##\s+(.+)$", body, re.MULTILINE)
        return m.group(1).strip() if m else fallback_id.replace("_", " ").title()

    # ── fact extraction ────────────────────────────────────────

    @staticmethod
    def _build_section_facts(report: ChangeReport) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group change data by section id.

        Returns ``{section_id: [fact_dict, ...]}``.
        """
        facts: Dict[str, List[Dict[str, Any]]] = {}
        for svc in report.services:
            for commit in svc.commits_since_last_doc:
                for fc in commit.changed_files:
                    section_id = _CATEGORY_TO_SECTION.get(fc.category, "services")
                    fact = {
                        "service": svc.service_name,
                        "project_path": svc.project_path,
                        "commit_sha": commit.short_id,
                        "commit_title": commit.title,
                        "author": commit.author,
                        "date": commit.date,
                        "file": fc.path,
                        "summary": fc.summary,
                    }
                    if fc.api_endpoints:
                        fact["api_endpoints"] = fc.api_endpoints
                    if fc.config_keys:
                        fact["config_keys"] = fc.config_keys
                    facts.setdefault(section_id, []).append(fact)

        # services section gets ALL commits, not just uncategorised ones
        svc_facts: List[Dict[str, Any]] = []
        for svc in report.services:
            for commit in svc.commits_since_last_doc:
                svc_facts.append({
                    "service": svc.service_name,
                    "project_path": svc.project_path,
                    "description": svc.description,
                    "commits": len(svc.commits_since_last_doc),
                    "files_changed": len(commit.changed_files),
                    "latest_commit": {
                        "sha": commit.short_id,
                        "title": commit.title,
                        "author": commit.author,
                        "date": commit.date,
                    },
                })
        facts["services"] = svc_facts

        # Tasks section
        if report.yougile_tasks:
            facts["tasks"] = report.yougile_tasks

        return facts

    @staticmethod
    def _build_overview_facts(report: ChangeReport) -> Dict[str, Any]:
        return {
            "total_commits": report.total_commits,
            "total_files": report.total_files_changed,
            "services_count": len(report.services),
            "services": [s.service_name for s in report.services],
            "categories": {
                k.value: v for k, v in report.changes_by_category().items()
            },
            "last_documented": report.last_documented_at or "впервые",
        }

    # ── LLM section generation ─────────────────────────────────

    async def _generate_section(
        self,
        section: DocSection,
        facts: List[Dict[str, Any]],
    ) -> str:
        """
        Call LLM to produce the *body* of a single section based on structured
        facts.  The LLM must NOT output the section heading.
        """
        import json as _json

        facts_json = _json.dumps(facts, ensure_ascii=False, indent=2)
        prompt = (
            "Ты — редактор технической документации.\n\n"
            f"Секция: **{section.title}**\n\n"
            "Факты об изменениях (JSON):\n"
            f"```json\n{facts_json}\n```\n\n"
            "Сгенерируй содержимое этой секции в формате Markdown. "
            "Не добавляй заголовок секции — только содержимое. "
            "Пиши на русском языке, кратко и по делу. "
            "Используй списки и таблицы где уместно. "
            "Если фактов нет или они пустые, напиши: *Изменений не обнаружено.*"
        )

        try:
            response = await self._llm.achat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
                model="deepseek/deepseek-v4-pro",
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception as exc:
            logger.error("LLM call failed for section %s: %s", section.section_id, exc)
            return f"*Ошибка при генерации секции: {exc}*\n\n{section.content}"

    # ── assembly ───────────────────────────────────────────────

    @staticmethod
    def _assemble_document(title: str, sections: List[DocSection]) -> str:
        """
        Build the final markdown document: title, then each section
        starting with its marker, heading, and content.
        """
        lines = [f"# {title}\n"]
        for sec in sections:
            lines.append(f"<!-- SECTION: {sec.section_id} -->")
            lines.append(f"## {sec.title}\n")
            if sec.content:
                lines.append(sec.content)
            lines.append("")
        return "\n".join(lines)

    # ── persistence ────────────────────────────────────────────

    async def _save_to_outline(
        self, title: str, markdown: str,
    ) -> Dict[str, Any]:
        """Save or update the document in Outline."""
        collection_id = settings.DOCS_OUTPUT_COLLECTION_ID

        if not collection_id:
            logger.warning(
                "DOCS_OUTPUT_COLLECTION_ID is not set; cannot save to Outline"
            )
            return {"document_id": None, "url": None, "title": title}

        try:
            # Try to find an existing document to update
            docs = await self._outline.alist_documents(collection_id, limit=10)
            existing_id: Optional[str] = None
            for d in docs.get("documents", []):
                if "Релизная документация" in (d.get("title") or ""):
                    existing_id = d["id"]
                    break

            if existing_id:
                result = await self._outline.aupdate_document(
                    existing_id, title=title, text=markdown,
                )
                return {
                    "document_id": existing_id,
                    "url": f"{settings.OUTLINE_URL}/doc/{existing_id}",
                    "title": title,
                }

            # Create new
            result = await self._outline.acreate_document(
                title=title,
                text=markdown,
                collection_id=collection_id,
                publish=True,
            )
            doc_id = result.get("id", "")
            return {
                "document_id": doc_id,
                "url": f"{settings.OUTLINE_URL}/doc/{doc_id}",
                "title": title,
            }
        except Exception as exc:
            logger.error("Failed to save document to Outline: %s", exc)
            raise


# ── helpers ────────────────────────────────────────────────────────


def _section_id_to_category(sid: str) -> Optional[ChangeCategory]:
    return {
        "api_changes": ChangeCategory.API,
        "config_changes": ChangeCategory.CONFIG,
        "dependencies": ChangeCategory.DEPENDENCY,
        "infrastructure": ChangeCategory.INFRASTRUCTURE,
        "bug_fixes": ChangeCategory.BUGFIX,
        "services": ChangeCategory.FEATURE,
    }.get(sid)


def _today_slug() -> str:
    return datetime.now().strftime("%d.%m.%Y")
