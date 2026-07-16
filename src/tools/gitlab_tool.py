"""
GitLab Tool - Integration with GitLab API
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GitLabTool:
    """Tool for interacting with GitLab"""
    
    def __init__(self, url: str, token: str, allowed_projects: Optional[List[str]] = None):
        """
        Initialize GitLab tool
        
        Args:
            url: GitLab URL (e.g., https://gitlab.example.com)
            token: GitLab personal access token
            allowed_projects: Optional list of allowed project paths to filter
        """
        self.url = url.rstrip('/')
        self.token = token
        self.allowed_projects = allowed_projects or []
        self._gl = None
    
    def _get_client(self):
        """Lazy load GitLab client"""
        if self._gl is None:
            try:
                import gitlab
                self._gl = gitlab.Gitlab(self.url, private_token=self.token)
                self._gl.auth()
            except ImportError:
                logger.error("python-gitlab not installed. Run: pip install python-gitlab")
                raise
            except Exception as e:
                logger.error(f"Failed to authenticate with GitLab: {e}")
                raise
        return self._gl
    
    def _is_project_allowed(self, project_path: str) -> bool:
        """Check if project is in allowed list"""
        if not self.allowed_projects:
            return True
        return any(
            allowed.lower() in project_path.lower() 
            for allowed in self.allowed_projects
        )
    
    def list_projects(self, search: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """
        List accessible GitLab projects
        
        Args:
            search: Optional search query
            limit: Maximum number of results
        
        Returns:
            Dictionary with list of projects
        """
        try:
            gl = self._get_client()
            
            kwargs = {'per_page': limit, 'membership': True}
            if search:
                kwargs['search'] = search
            
            projects = gl.projects.list(**kwargs)
            
            result = []
            for p in projects:
                if self._is_project_allowed(p.path_with_namespace):
                    result.append({
                        'id': p.id,
                        'name': p.name,
                        'path': p.path_with_namespace,
                        'description': p.description or '',
                        'url': p.web_url,
                        'default_branch': getattr(p, 'default_branch', 'main'),
                        'last_activity': p.last_activity_at
                    })
            
            return {
                "success": True,
                "count": len(result),
                "projects": result
            }
        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            return {"error": f"Failed to list projects: {str(e)}"}
    
    def get_commits(
        self,
        project_id: int,
        branch: Optional[str] = None,
        limit: int = 20,
        since_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get commits from a project
        
        Args:
            project_id: GitLab project ID
            branch: Branch name (default: project's default branch)
            limit: Maximum number of commits
            since_days: Get commits from last N days
        
        Returns:
            Dictionary with list of commits
        """
        try:
            gl = self._get_client()
            project = gl.projects.get(project_id)
            
            kwargs = {'per_page': limit}
            if branch:
                kwargs['ref_name'] = branch
            if since_days:
                since = datetime.utcnow() - timedelta(days=since_days)
                kwargs['since'] = since.isoformat()
            
            commits = project.commits.list(**kwargs)
            
            result = []
            for c in commits:
                result.append({
                    'id': c.short_id,
                    'full_id': c.id,
                    'title': c.title,
                    'message': c.message,
                    'author': c.author_name,
                    'author_email': c.author_email,
                    'date': c.created_at,
                    'url': c.web_url
                })
            
            return {
                "success": True,
                "project": project.path_with_namespace,
                "branch": branch or project.default_branch,
                "count": len(result),
                "commits": result
            }
        except Exception as e:
            logger.error(f"Failed to get commits: {e}")
            return {"error": f"Failed to get commits: {str(e)}"}
    
    def get_merge_requests(
        self,
        project_id: int,
        state: str = "opened",
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get merge requests from a project
        
        Args:
            project_id: GitLab project ID
            state: MR state (opened, closed, merged, all)
            limit: Maximum number of MRs
        
        Returns:
            Dictionary with list of merge requests
        """
        try:
            gl = self._get_client()
            project = gl.projects.get(project_id)
            
            mrs = project.mergerequests.list(state=state, per_page=limit)
            
            result = []
            for mr in mrs:
                result.append({
                    'iid': mr.iid,
                    'title': mr.title,
                    'description': mr.description[:500] if mr.description else '',
                    'state': mr.state,
                    'author': mr.author['name'] if mr.author else 'Unknown',
                    'source_branch': mr.source_branch,
                    'target_branch': mr.target_branch,
                    'created_at': mr.created_at,
                    'updated_at': mr.updated_at,
                    'url': mr.web_url,
                    'labels': mr.labels,
                    'assignees': [a['name'] for a in (mr.assignees or [])]
                })
            
            return {
                "success": True,
                "project": project.path_with_namespace,
                "state": state,
                "count": len(result),
                "merge_requests": result
            }
        except Exception as e:
            logger.error(f"Failed to get merge requests: {e}")
            return {"error": f"Failed to get merge requests: {str(e)}"}
    
    def get_mr_details(
        self,
        project_id: int,
        mr_iid: int,
        include_diff: bool = False
    ) -> Dict[str, Any]:
        """
        Get detailed information about a merge request
        
        Args:
            project_id: GitLab project ID
            mr_iid: Merge request internal ID
            include_diff: Whether to include the diff
        
        Returns:
            Dictionary with MR details
        """
        try:
            gl = self._get_client()
            project = gl.projects.get(project_id)
            mr = project.mergerequests.get(mr_iid)
            
            result = {
                'iid': mr.iid,
                'title': mr.title,
                'description': mr.description or '',
                'state': mr.state,
                'author': mr.author['name'] if mr.author else 'Unknown',
                'source_branch': mr.source_branch,
                'target_branch': mr.target_branch,
                'created_at': mr.created_at,
                'updated_at': mr.updated_at,
                'merged_at': getattr(mr, 'merged_at', None),
                'url': mr.web_url,
                'labels': mr.labels,
                'assignees': [a['name'] for a in (mr.assignees or [])],
                'reviewers': [r['name'] for r in (getattr(mr, 'reviewers', []) or [])],
                'changes_count': getattr(mr, 'changes_count', 'unknown'),
                'has_conflicts': getattr(mr, 'has_conflicts', False),
                'draft': getattr(mr, 'draft', False)
            }
            
            if include_diff:
                try:
                    changes = mr.changes()
                    diff_summary = []
                    for change in changes.get('changes', [])[:10]:  # Limit to 10 files
                        diff_summary.append({
                            'file': change.get('new_path', change.get('old_path', 'unknown')),
                            'additions': change.get('diff', '').count('\n+'),
                            'deletions': change.get('diff', '').count('\n-')
                        })
                    result['diff_summary'] = diff_summary
                except:
                    result['diff_summary'] = []
            
            return {
                "success": True,
                "merge_request": result
            }
        except Exception as e:
            logger.error(f"Failed to get MR details: {e}")
            return {"error": f"Failed to get MR details: {str(e)}"}
    
    def get_pipelines(
        self,
        project_id: int,
        status: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get pipelines from a project
        
        Args:
            project_id: GitLab project ID
            status: Pipeline status (running, pending, success, failed, canceled)
            limit: Maximum number of pipelines
        
        Returns:
            Dictionary with list of pipelines
        """
        try:
            gl = self._get_client()
            project = gl.projects.get(project_id)
            
            kwargs = {'per_page': limit}
            if status:
                kwargs['status'] = status
            
            pipelines = project.pipelines.list(**kwargs)
            
            result = []
            for p in pipelines:
                result.append({
                    'id': p.id,
                    'status': p.status,
                    'ref': p.ref,
                    'sha': p.sha[:8],
                    'created_at': p.created_at,
                    'updated_at': p.updated_at,
                    'url': p.web_url,
                    'source': getattr(p, 'source', 'unknown')
                })
            
            return {
                "success": True,
                "project": project.path_with_namespace,
                "count": len(result),
                "pipelines": result
            }
        except Exception as e:
            logger.error(f"Failed to get pipelines: {e}")
            return {"error": f"Failed to get pipelines: {str(e)}"}
    
    def get_pipeline_jobs(
        self,
        project_id: int,
        pipeline_id: int
    ) -> Dict[str, Any]:
        """
        Get jobs from a pipeline
        
        Args:
            project_id: GitLab project ID
            pipeline_id: Pipeline ID
        
        Returns:
            Dictionary with list of jobs
        """
        try:
            gl = self._get_client()
            project = gl.projects.get(project_id)
            pipeline = project.pipelines.get(pipeline_id)
            
            jobs = pipeline.jobs.list(all=True)
            
            result = []
            for j in jobs:
                result.append({
                    'id': j.id,
                    'name': j.name,
                    'stage': j.stage,
                    'status': j.status,
                    'duration': getattr(j, 'duration', None),
                    'started_at': getattr(j, 'started_at', None),
                    'finished_at': getattr(j, 'finished_at', None),
                    'url': j.web_url,
                    'failure_reason': getattr(j, 'failure_reason', None)
                })
            
            return {
                "success": True,
                "pipeline_id": pipeline_id,
                "pipeline_status": pipeline.status,
                "count": len(result),
                "jobs": result
            }
        except Exception as e:
            logger.error(f"Failed to get pipeline jobs: {e}")
            return {"error": f"Failed to get pipeline jobs: {str(e)}"}
    
    # Async versions
    async def alist_projects(self, search: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """Async version of list_projects"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.list_projects(search, limit)
        )

    async def alist_group_projects(
        self, group_path: str, search: Optional[str] = None, limit: int = 50
    ) -> Dict[str, Any]:
        """
        List projects inside a GitLab group / subgroup.
        Uses GitLab's ``groups/<path>/projects`` API.
        """
        import httpx

        url = f"{self.url}/api/v4/groups/{group_path.replace('/', '%2F')}/projects"
        params: Dict[str, Any] = {
            "per_page": limit,
            "include_subgroups": True,
            "order_by": "last_activity_at",
            "sort": "desc",
        }
        if search:
            params["search"] = search

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"PRIVATE-TOKEN": self.token}, params=params)
            resp.raise_for_status()
            projects = resp.json()

        result = []
        for p in projects:
            if self._is_project_allowed(p.get("path_with_namespace", "")):
                result.append({
                    "id": p["id"],
                    "name": p["name"],
                    "path": p["path_with_namespace"],
                    "description": p.get("description") or "",
                    "url": p["web_url"],
                    "default_branch": p.get("default_branch", "main"),
                    "last_activity": p.get("last_activity_at"),
                })
        return {"success": True, "count": len(result), "projects": result}

    async def aget_commits(
        self,
        project_id: int,
        branch: Optional[str] = None,
        limit: int = 20,
        since_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """Async version of get_commits"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.get_commits(project_id, branch, limit, since_days)
        )
    
    async def aget_merge_requests(
        self,
        project_id: int,
        state: str = "opened",
        limit: int = 20
    ) -> Dict[str, Any]:
        """Async version of get_merge_requests"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.get_merge_requests(project_id, state, limit)
        )
    
    async def aget_mr_details(
        self,
        project_id: int,
        mr_iid: int,
        include_diff: bool = False
    ) -> Dict[str, Any]:
        """Async version of get_mr_details"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.get_mr_details(project_id, mr_iid, include_diff)
        )
    
    async def aget_pipelines(
        self,
        project_id: int,
        status: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Async version of get_pipelines"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.get_pipelines(project_id, status, limit)
        )
    
    async def aget_pipeline_jobs(
        self,
        project_id: int,
        pipeline_id: int
    ) -> Dict[str, Any]:
        """Async version of get_pipeline_jobs"""
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: self.get_pipeline_jobs(project_id, pipeline_id)
        )

    # ── Diff / compare helpers for documentation pipeline ──────────

    async def aget_diff(self, project_id: int, commit_sha: str) -> Dict[str, Any]:
        """
        Get the files changed in a single commit along with line-level diffs.

        Returns a dict with ``success`` and a list of ``files``, each containing:
        ``old_path``, ``new_path``, ``new_file``, ``renamed_file``,
        ``deleted_file``, ``additions``, ``deletions``, ``diff`` (truncated to 8000 chars).
        """
        import httpx

        url = f"{self.url}/api/v4/projects/{project_id}/repository/commits/{commit_sha}/diff"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"PRIVATE-TOKEN": self.token})
            resp.raise_for_status()
            files = resp.json()

        result = []
        for f in files:
            diff = f.get("diff", "") or ""
            result.append({
                "old_path": f.get("old_path", ""),
                "new_path": f.get("new_path", ""),
                "new_file": f.get("new_file", False),
                "renamed_file": f.get("renamed_file", False),
                "deleted_file": f.get("deleted_file", False),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "diff": diff[:8000],  # truncate to avoid huge payloads
            })
        return {"success": True, "commit": commit_sha, "count": len(result), "files": result}

    async def aget_file_content(
        self, project_id: int, file_path: str, ref: str = "master"
    ) -> Dict[str, Any]:
        """
        Read the raw content of a single file from the repository.

        Returns ``{"success": True, "path": ..., "ref": ..., "content": "…"}``
        or an error dict.
        """
        import httpx

        url = (
            f"{self.url}/api/v4/projects/{project_id}/repository/files/"
            f"{file_path.replace('/', '%2F')}/raw?ref={ref}"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers={"PRIVATE-TOKEN": self.token})
            if resp.status_code != 200:
                return {"error": f"File not found or access denied: {file_path} @ {ref}"}
            content = resp.text
        return {"success": True, "path": file_path, "ref": ref, "content": content[:20000]}

    async def aget_compare(
        self, project_id: int, from_sha: str, to_sha: str
    ) -> Dict[str, Any]:
        """
        Compare two commits / branches / tags.

        Returns a unified diff-like summary with ``commits`` and ``diffs``.
        """
        import httpx

        url = f"{self.url}/api/v4/projects/{project_id}/repository/compare"
        params = {"from": from_sha, "to": to_sha}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                url, headers={"PRIVATE-TOKEN": self.token}, params=params
            )
            resp.raise_for_status()
            data = resp.json()

        commits = []
        for c in data.get("commits", []):
            commits.append({
                "sha": c.get("id", ""),
                "short_id": c.get("short_id", ""),
                "title": c.get("title", ""),
                "message": c.get("message", ""),
                "author": c.get("author_name", ""),
                "date": c.get("created_at", ""),
            })

        diffs = []
        for d in data.get("diffs", []):
            diff = d.get("diff", "") or ""
            diffs.append({
                "old_path": d.get("old_path", ""),
                "new_path": d.get("new_path", ""),
                "new_file": d.get("new_file", False),
                "renamed_file": d.get("renamed_file", False),
                "deleted_file": d.get("deleted_file", False),
                "additions": d.get("additions", 0),
                "deletions": d.get("deletions", 0),
                "diff": diff[:8000],
            })

        return {
            "success": True,
            "from": from_sha,
            "to": to_sha,
            "commits": commits,
            "diffs": diffs,
        }


# Tool definitions for the agent
GITLAB_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "gitlab_list_projects",
            "description": "Получить список доступных проектов в GitLab. Используй для поиска проектов по имени или получения списка всех проектов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Поисковый запрос для фильтрации проектов по имени"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество проектов (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_commits",
            "description": "Получить список коммитов в проекте GitLab. Показывает автора, сообщение и дату коммита.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "integer",
                        "description": "ID проекта в GitLab"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Название ветки (по умолчанию основная ветка)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество коммитов (по умолчанию 20)",
                        "default": 20
                    },
                    "since_days": {
                        "type": "integer",
                        "description": "Получить коммиты за последние N дней"
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_merge_requests",
            "description": "Получить список merge requests (MR) в проекте. Можно фильтровать по статусу: opened, merged, closed, all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "integer",
                        "description": "ID проекта в GitLab"
                    },
                    "state": {
                        "type": "string",
                        "description": "Статус MR: opened, merged, closed, all",
                        "enum": ["opened", "merged", "closed", "all"],
                        "default": "opened"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество MR (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_mr_details",
            "description": "Получить детальную информацию о конкретном merge request, включая описание, assignees, reviewers и опционально diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "integer",
                        "description": "ID проекта в GitLab"
                    },
                    "mr_iid": {
                        "type": "integer",
                        "description": "Внутренний ID merge request (IID)"
                    },
                    "include_diff": {
                        "type": "boolean",
                        "description": "Включить информацию об изменённых файлах",
                        "default": False
                    }
                },
                "required": ["project_id", "mr_iid"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_pipelines",
            "description": "Получить список CI/CD пайплайнов проекта. Показывает статус, ветку и время запуска.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "integer",
                        "description": "ID проекта в GitLab"
                    },
                    "status": {
                        "type": "string",
                        "description": "Фильтр по статусу: running, pending, success, failed, canceled",
                        "enum": ["running", "pending", "success", "failed", "canceled"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество пайплайнов (по умолчанию 10)",
                        "default": 10
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gitlab_get_pipeline_jobs",
            "description": "Получить список джобов (задач) в конкретном пайплайне. Показывает статус каждого этапа сборки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "integer",
                        "description": "ID проекта в GitLab"
                    },
                    "pipeline_id": {
                        "type": "integer",
                        "description": "ID пайплайна"
                    }
                },
                "required": ["project_id", "pipeline_id"]
            }
        }
    }
]
