"""
Data models for the documentation generation pipeline.

All models are plain dataclasses — json‑serialisable by default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Change categories ────────────────────────────────────────────


class ChangeCategory(str, Enum):
    API = "api"
    FEATURE = "feature"
    BUGFIX = "bugfix"
    CONFIG = "config"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    MODEL_LAYER = "model"
    REFACTOR = "refactor"
    OTHER = "other"


# ── Low‑level primitives ──────────────────────────────────────────


@dataclass
class FileChange:
    """A single file touched in a commit."""

    path: str
    change_type: str             # added / modified / deleted / renamed
    category: ChangeCategory
    summary: str                 # short human‑readable label
    additions: int = 0
    deletions: int = 0

    # Optional – populated only when the file is api‑related
    api_endpoints: List[str] = field(default_factory=list)
    config_keys: List[str] = field(default_factory=list)


@dataclass
class CommitInfo:
    """A single commit with its changed files."""

    sha: str
    short_id: str                # 8‑char abbreviation
    title: str
    message: str
    author: str
    date: str                    # ISO‑8601
    url: str
    changed_files: List[FileChange] = field(default_factory=list)

    @property
    def dominant_category(self) -> Optional[ChangeCategory]:
        """Return the most frequent change category across files."""
        if not self.changed_files:
            return None
        counts: Dict[ChangeCategory, int] = {}
        for fc in self.changed_files:
            counts[fc.category] = counts.get(fc.category, 0) + 1
        return max(counts, key=counts.get)


@dataclass
class ServiceChanges:
    """Aggregated changes for one GitLab project."""

    project_id: int
    project_path: str            # e.g. botann / botann
    project_url: str
    default_branch: str
    description: str             # pulled from project README
    commits_since_last_doc: List[CommitInfo] = field(default_factory=list)

    @property
    def service_name(self) -> str:
        return self.project_path.split("/")[-1]


# ── High‑level report ─────────────────────────────────────────────


@dataclass
class ChangeReport:
    """The full analysis output consumed by the generator."""

    services: List[ServiceChanges] = field(default_factory=list)
    cross_cutting_changes: List[str] = field(default_factory=list)
    yougile_tasks: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: str = ""
    last_documented_at: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def from_json(raw: str) -> ChangeReport:
        return _dict_to_report(json.loads(raw))

    # Helpers ──────────────────────────────────────────────────

    @property
    def total_commits(self) -> int:
        return sum(len(s.commits_since_last_doc) for s in self.services)

    @property
    def total_files_changed(self) -> int:
        return sum(
            len(c.changed_files)
            for s in self.services
            for c in s.commits_since_last_doc
        )

    def changes_by_category(self) -> Dict[ChangeCategory, int]:
        """Number of commits per category."""
        result: Dict[ChangeCategory, int] = {}
        for srv in self.services:
            for c in srv.commits_since_last_doc:
                cat = c.dominant_category or ChangeCategory.OTHER
                result[cat] = result.get(cat, 0) + 1
        return result

    def all_api_changes(self) -> List[Dict[str, Any]]:
        """Flat list of every api endpoint change across all services."""
        items: List[Dict[str, Any]] = []
        for srv in self.services:
            for c in srv.commits_since_last_doc:
                for fc in c.changed_files:
                    if fc.category != ChangeCategory.API or not fc.api_endpoints:
                        continue
                    for ep in fc.api_endpoints:
                        items.append({
                            "service": srv.service_name,
                            "project_path": srv.project_path,
                            "commit_sha": c.short_id,
                            "commit_title": c.title,
                            "file": fc.path,
                            "endpoint": ep,
                        })
        return items

    def all_config_changes(self) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for srv in self.services:
            for c in srv.commits_since_last_doc:
                for fc in c.changed_files:
                    if fc.category != ChangeCategory.CONFIG or not fc.config_keys:
                        continue
                    for key in fc.config_keys:
                        items.append({
                            "service": srv.service_name,
                            "file": fc.path,
                            "key": key,
                        })
        return items


# ── Document template & sections ──────────────────────────────────


@dataclass
class DocSection:
    """A single named section inside the template."""

    section_id: str              # matches the HTML comment marker
    title: str                   # human‑readable heading
    content: str                 # current content (markdown), may be empty
    is_dynamic: bool = True      # False → section is never regenerated
    change_category: Optional[ChangeCategory] = None


@dataclass
class DocTemplate:
    """A parsed documentation template with ordered sections."""

    template_id: str             # document id in Outline (or "default")
    title: str
    sections: List[DocSection]   # order matters
    version: str = "v1"


# ── Serialisation helper ──────────────────────────────────────────


def _dict_to_report(d: dict) -> ChangeReport:
    """Convert a plain dict back to a ChangeReport (handles enum fields)."""

    def _parse_file_change(fc: dict) -> FileChange:
        fc["category"] = ChangeCategory(fc.get("category", "other"))
        return FileChange(**fc)

    def _parse_commit(c: dict) -> CommitInfo:
        files = [_parse_file_change(fc) for fc in c.get("changed_files", [])]
        c["changed_files"] = files
        return CommitInfo(**c)

    services = []
    for s in d.get("services", []):
        s["commits_since_last_doc"] = [
            _parse_commit(c) for c in s.get("commits_since_last_doc", [])
        ]
        services.append(ServiceChanges(**s))

    return ChangeReport(
        services=services,
        cross_cutting_changes=d.get("cross_cutting_changes", []),
        yougile_tasks=d.get("yougile_tasks", []),
        generated_at=d.get("generated_at", ""),
        last_documented_at=d.get("last_documented_at"),
    )
