"""
Documentation generation pipeline.

Orchestrates the three stages:
1. **Analysis** — deterministic code scan via CodeAnalysisEngine.
2. **Generation** — template-based document assembly with isolated LLM sections.
3. **Save**         — persist the document to Outline and update the state file.

Progress events are streamed through an optional async callback.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from src.config import settings
from src.docs.analyzer import CodeAnalysisEngine
from src.docs.generator import DocumentGenerator
from src.tools.gitlab_tool import GitLabTool
from src.tools.outline_tool import OutlineTool

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[Dict[str, Any]], Any]


class DocPipeline:
    """
    Run the full release-documentation pipeline.

    :param gitlab_tool:  configured GitLab API tool.
    :param outline_tool: configured Outline API tool.
    :param llm_client:   LiteLLM client (``LLMClient``).
    :param on_progress:  optional async callback receiving ``{phase, status, ...}``.
    """

    def __init__(
        self,
        gitlab_tool: GitLabTool,
        outline_tool: OutlineTool,
        llm_client: Any,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self._on_progress = on_progress
        self._analyzer = CodeAnalysisEngine(gitlab_tool)
        self._generator = DocumentGenerator(outline_tool, llm_client)

    async def run(self) -> Dict[str, Any]:
        """Execute the full pipeline.  Returns a summary dict."""

        await self._emit({"phase": "analysis", "status": "started"})

        # ── Stage 1: Analysis ─────────────────────────────────
        try:
            report = await self._analyzer.analyze(on_progress=self._on_progress)
        except Exception as exc:
            logger.error("Analysis stage failed: %s", exc, exc_info=True)
            await self._emit({"phase": "analysis", "status": "error", "error": str(exc)})
            raise

        if not report.services:
            await self._emit({
                "phase": "analysis",
                "status": "done",
                "message": "Изменений не найдено — документация не требует обновления.",
            })
            return {"status": "no_changes", "report": report}

        await self._emit({
            "phase": "analysis",
            "status": "done",
            "services_count": len(report.services),
            "total_commits": report.total_commits,
            "total_files": report.total_files_changed,
        })

        # ── Stage 2: Generation ────────────────────────────────
        await self._emit({"phase": "generation", "status": "started"})

        try:
            result = await self._generator.generate(report, on_progress=self._on_progress)
        except Exception as exc:
            logger.error("Generation stage failed: %s", exc, exc_info=True)
            await self._emit({"phase": "generation", "status": "error", "error": str(exc)})
            raise

        await self._emit({
            "phase": "generation",
            "status": "done",
            "document_id": result.get("document_id"),
            "url": result.get("url"),
            "title": result.get("title"),
        })

        # ── Stage 3: Save state ────────────────────────────────
        await self._emit({"phase": "save", "status": "started"})
        self._analyzer.save_state_from_report(report)
        await self._emit({"phase": "save", "status": "done"})

        return {
            "status": "success",
            "document_id": result.get("document_id"),
            "document_url": result.get("url"),
            "document_title": result.get("title"),
            "services_count": len(report.services),
            "total_commits": report.total_commits,
            "total_files": report.total_files_changed,
        }

    async def _emit(self, event: Dict[str, Any]):
        if self._on_progress:
            try:
                await self._on_progress(event)
            except Exception:
                logger.warning("Progress callback failed", exc_info=True)
