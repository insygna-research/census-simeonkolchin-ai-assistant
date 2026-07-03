"""
Deterministic code analysis engine.

Scans commits across GitLab projects, classifies changed files by
category (api / config / dependency / ...), and extracts structured
facts (endpoints, config keys, new dependencies) — all without LLM.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.config import settings
from src.docs.models import (
    ChangeCategory,
    ChangeReport,
    CommitInfo,
    FileChange,
    ServiceChanges,
)
from src.tools.gitlab_tool import GitLabTool

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════
#  Classification rules (path patterns + heuristics)
# ══════════════════════════════════════════════════════════════════


def _classify_file(file_path: str, diff: str) -> Tuple[ChangeCategory, str]:
    """
    Deterministic classification of a single file.

    Returns (category, human summary).
    """

    path_lower = file_path.lower()

    # ── Infrastructure files (checked before config to avoid false positives) ──
    if _matches_any(path_lower, (
        "dockerfile", ".gitlab-ci.yml", ".github/workflows",
        "k8s/", "kubernetes/", "helm/", "terraform", "ansible",
        "nginx", "caddy", "deployment", "service.yaml", "ingress",
        "statefulset", "configmap",
    )):
        return ChangeCategory.INFRASTRUCTURE, "infrastructure changes"

    # ── API files ──
    if _matches_any(path_lower, (
        "routes.py", "api.py", "endpoint", "/api/", "/router",
        "app.py", "main.py",
    )):
        endpoints = _extract_api_endpoints(diff)
        summary = ", ".join(endpoints) if endpoints else "API changes"
        return ChangeCategory.API, summary

    # ── Config files ──
    if _matches_any(path_lower, (
        "config.py", "settings.py", ".env", ".env.", "docker-compose",
        ".yaml", ".yml", "makefile", ".toml", "setup.cfg",
    )):
        keys = _extract_config_keys(diff)
        summary = ", ".join(keys) if keys else "configuration changes"
        return ChangeCategory.CONFIG, summary

    # ── Dependency files ──
    if _matches_any(path_lower, (
        "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg",
        "package.json", "package-lock.json", "go.mod", "go.sum",
    )):
        added, removed = _extract_dependency_changes(diff)
        parts = []
        if added:
            parts.append(f"added: {', '.join(added[:5])}")
        if removed:
            parts.append(f"removed: {', '.join(removed[:5])}")
        summary = "; ".join(parts) or "dependency changes"
        return ChangeCategory.DEPENDENCY, summary

    # ── Model / schema files ──
    if _matches_any(path_lower, (
        "model", "schema", "dto", "types.py", "entity", "domain",
    )):
        return ChangeCategory.MODEL_LAYER, "model / schema changes"

    # ── Test files ──
    if _matches_any(path_lower, ("test_", "_test", "tests/", "spec", "__tests__")):
        return ChangeCategory.OTHER, "test changes (skipped)"

    # ── Fallback ──
    return ChangeCategory.OTHER, "code changes"


def _matches_any(path_lower: str, patterns: Tuple[str, ...]) -> bool:
    for p in patterns:
        if p in path_lower:
            return True
    return False


# ══════════════════════════════════════════════════════════════════
#  Extractors
# ══════════════════════════════════════════════════════════════════


_API_DECORATOR_RE = re.compile(
    r"@(?:router|app)\.\s*(get|post|put|delete|patch|head|options)\s*\(\s*[\"'](.*?)[\"']",
    re.IGNORECASE,
)
_API_DEF_RE = re.compile(
    r"async\s+def\s+(\w+)\s*\(.*?\)\s*.*?:",
)

_CONFIG_LINE_RE = re.compile(
    r'^[A-Z][A-Z0-9_]+\s*(?::\s*[^=]+)?\s*=\s*', re.MULTILINE,
)

_DEP_LINE_RE = re.compile(r'^\s*([\w\-\[\]]+)\s*([><=!~]+.*?)?(?:#.*)?$', re.MULTILINE)


def _extract_api_endpoints(diff: str) -> List[str]:
    """Extract ``METHOD /path`` strings from a diff."""
    endpoints: List[str] = []
    for m in _API_DECORATOR_RE.finditer(diff):
        method = m.group(1).upper()
        path = m.group(2)
        endpoints.append(f"{method} {path}")
    # De-duplicate while preserving order
    seen = set()
    out = []
    for ep in endpoints:
        if ep not in seen:
            seen.add(ep)
            out.append(ep)
    return out


def _extract_config_keys(diff: str) -> List[str]:
    """Extract new env / config variable names (lines starting with +)."""
    keys: List[str] = []
    for line in diff.splitlines():
        if not line.startswith("+"):
            continue
        m = _CONFIG_LINE_RE.match(line[1:])
        if m:
            key = m.group(0).split("=")[0].rstrip().rstrip(":").strip()
            if key and key.isascii():
                keys.append(key)
    seen = set()
    return [k for k in keys if not (k in seen or seen.add(k))]


def _extract_dependency_changes(diff: str) -> Tuple[List[str], List[str]]:
    """Return (added, removed) dependency names."""
    added: List[str] = []
    removed: List[str] = []
    for line in diff.splitlines():
        if line.startswith("+"):
            m = _DEP_LINE_RE.match(line[1:])
            if m:
                added.append(m.group(1).strip())
        elif line.startswith("-"):
            m = _DEP_LINE_RE.match(line[1:])
            if m:
                removed.append(m.group(1).strip())
    return added, removed


# ══════════════════════════════════════════════════════════════════
#  Commit-level category heuristic
# ══════════════════════════════════════════════════════════════════

def _dominant_category_from_files(files: List[FileChange]) -> ChangeCategory:
    if not files:
        return ChangeCategory.OTHER
    counts: Dict[ChangeCategory, int] = {}
    for f in files:
        counts[f.category] = counts.get(f.category, 0) + 1
    return max(counts, key=counts.get)


# ══════════════════════════════════════════════════════════════════
#  Engine
# ══════════════════════════════════════════════════════════════════


class CodeAnalysisEngine:
    """
    Deterministic code analyser.

    1. Lists projects in the configured GitLab group.
    2. Fetches commits since the last documented point (or since N days).
    3. Fetches per-commit diffs and classifies every touched file.
    4. Builds a ``ChangeReport`` (json-serialisable).
    """

    def __init__(self, gitlab_tool: GitLabTool):
        self._gl = gitlab_tool
        self._state_path = settings.DOCS_STATE_FILE

    # ── public API ─────────────────────────────────────────────

    async def analyze(
        self,
        since_days: Optional[int] = None,
        on_progress: Optional[Any] = None,
    ) -> ChangeReport:
        window = since_days or settings.DOCS_CHANGE_WINDOW_DAYS
        state = self._load_state()

        # 1. Discover projects
        group = settings.DOCS_ANALYZED_GROUP
        projects_result = await self._gl.alist_group_projects(group)
        projects = projects_result.get("projects", [])

        # Filter to explicit list if configured
        explicit = settings.get_docs_analyzed_projects()
        if explicit:
            projects = [p for p in projects if p["path"] in explicit]

        if not projects:
            logger.warning("No projects found in group %s", group)
            return ChangeReport(generated_at=_now_iso())

        # 2. Collect changes per service
        services: List[ServiceChanges] = []
        for idx, proj in enumerate(projects):
            if on_progress:
                await on_progress({
                    "phase": "analysis",
                    "status": "progress",
                    "service": proj["path"],
                    "current": idx + 1,
                    "total": len(projects),
                })

            svc = await self._analyze_project(proj, state, window)
            if svc.commits_since_last_doc:
                services.append(svc)

        # 3. Assemble report
        report = ChangeReport(
            services=services,
            generated_at=_now_iso(),
            last_documented_at=max(
                (ts for ts in state.values() if ts), default=None
            ) if state else None,
        )
        return report

    # ── project analysis ───────────────────────────────────────

    async def _analyze_project(
        self,
        proj: Dict[str, Any],
        state: Dict[str, str],
        window: int,
    ) -> ServiceChanges:
        pid = proj["id"]
        path = proj["path"]
        branch = proj.get("default_branch", "master")

        # Determine since-sha
        last_sha = state.get(path)
        limit = 50
        since_arg: Optional[int] = None

        if last_sha:
            # Fetch commits with a generous limit, then filter by sha
            since_arg = None
            limit = 100
        else:
            since_arg = window

        commits_raw = await self._gl.aget_commits(
            pid, branch=branch, limit=limit, since_days=since_arg,
        )

        svc = ServiceChanges(
            project_id=pid,
            project_path=path,
            project_url=proj["url"],
            default_branch=branch,
            description=proj.get("description", ""),
        )

        for raw_commit in commits_raw.get("commits", []):
            sha = raw_commit.get("id", "")
            # Stop when we reach the last documented commit
            if last_sha and sha == last_sha:
                break

            commit_info = await self._analyze_commit(pid, raw_commit)
            # Only include commits with real code changes
            if commit_info.changed_files:
                svc.commits_since_last_doc.append(commit_info)

        return svc

    async def _analyze_commit(
        self, project_id: int, raw_commit: Dict[str, Any]
    ) -> CommitInfo:
        sha = raw_commit.get("id", "")
        diff_result = await self._gl.aget_diff(project_id, sha)

        files: List[FileChange] = []
        for f in diff_result.get("files", []):
            cat, summary = _classify_file(
                f.get("new_path") or f.get("old_path", ""),
                f.get("diff", ""),
            )

            fc = FileChange(
                path=f.get("new_path") or f.get("old_path", ""),
                change_type="modified",
                category=cat,
                summary=summary,
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
            )

            # Attach structured extracts
            if cat == ChangeCategory.API:
                fc.api_endpoints = _extract_api_endpoints(f.get("diff", ""))
            elif cat == ChangeCategory.CONFIG:
                fc.config_keys = _extract_config_keys(f.get("diff", ""))

            files.append(fc)

        return CommitInfo(
            sha=sha,
            short_id=raw_commit.get("short_id", sha[:8]),
            title=raw_commit.get("title", ""),
            message=raw_commit.get("message", ""),
            author=raw_commit.get("author_name", raw_commit.get("author", "")),
            date=raw_commit.get("created_at", raw_commit.get("date", "")),
            url=raw_commit.get("web_url", raw_commit.get("url", "")),
            changed_files=files,
        )

    # ── state persistence ──────────────────────────────────────

    def _load_state(self) -> Dict[str, str]:
        """{project_path: last_sha}."""
        try:
            with open(self._state_path, "r") as fh:
                return json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_state_from_report(self, report: ChangeReport):
        """Update state to the head sha of each analysed service."""
        state = self._load_state()
        for svc in report.services:
            if svc.commits_since_last_doc:
                head = svc.commits_since_last_doc[0]
                state[svc.project_path] = head.sha
        os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
        with open(self._state_path, "w") as fh:
            json.dump(state, fh, indent=2)


# ── helpers ────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
