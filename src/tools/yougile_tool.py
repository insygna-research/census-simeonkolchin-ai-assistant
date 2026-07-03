"""
YouGile Tool - Integration with YouGile Task Manager API
"""

import httpx
import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


def md_to_html(text: str) -> str:
    """
    Convert Markdown to HTML for YouGile task descriptions.
    
    YouGile supports: h1-h6, p, b/strong, i/em, ul/ol/li, a, br.
    It strips: blockquote, code, pre.
    """
    try:
        import markdown
        html = markdown.markdown(
            text,
            extensions=['nl2br', 'sane_lists']
        )
        return html
    except ImportError:
        logger.warning("markdown library not available, using simple conversion")
        # Fallback: simple regex-based conversion
        lines = text.split('\n')
        html_lines = []
        in_list = False
        list_type = None
        
        for line in lines:
            stripped = line.strip()
            
            # Empty line — close list if open, add <br>
            if not stripped:
                if in_list:
                    html_lines.append(f'</{list_type}>')
                    in_list = False
                    list_type = None
                html_lines.append('<br>')
                continue
            
            # Headers
            header_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if header_match:
                level = len(header_match.group(1))
                content = header_match.group(2)
                html_lines.append(f'<h{level}>{_inline_md(content)}</h{level}>')
                continue
            
            # Unordered list
            ul_match = re.match(r'^[-*+]\s+(.+)$', stripped)
            if ul_match:
                if not in_list or list_type != 'ul':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ul>')
                    in_list = True
                    list_type = 'ul'
                html_lines.append(f'<li>{_inline_md(ul_match.group(1))}</li>')
                continue
            
            # Ordered list
            ol_match = re.match(r'^\d+[.)]\s+(.+)$', stripped)
            if ol_match:
                if not in_list or list_type != 'ol':
                    if in_list:
                        html_lines.append(f'</{list_type}>')
                    html_lines.append('<ol>')
                    in_list = True
                    list_type = 'ol'
                html_lines.append(f'<li>{_inline_md(ol_match.group(1))}</li>')
                continue
            
            # Regular paragraph
            if in_list:
                html_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None
            html_lines.append(f'<p>{_inline_md(stripped)}</p>')
        
        if in_list:
            html_lines.append(f'</{list_type}>')
        
        return '\n'.join(html_lines)


def _inline_md(text: str) -> str:
    """Convert inline Markdown: bold, italic, links."""
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    # Italic: *text* or _text_
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)
    # Links: [text](url)
    text = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', text)
    return text


class YouGileTool:
    """Tool for interacting with YouGile task manager (single token)"""
    
    def __init__(self, url: str, api_key: str, allowed_projects: Optional[List[str]] = None, token_name: str = "default"):
        """
        Initialize YouGile tool
        
        Args:
            url: YouGile URL (e.g., https://ru.yougile.com)
            api_key: YouGile API key
            allowed_projects: Optional list of allowed project names to filter
        """
        self.base_url = url.rstrip('/')
        self.api_key = api_key
        self.token_name = token_name
        self.allowed_projects = [p.lower() for p in (allowed_projects or [])]
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Make a GET request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            response = httpx.get(
                url,
                headers=self.headers,
                params=params or {},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    def _post(self, endpoint: str, data: dict = None) -> dict:
        """Make a POST request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            response = httpx.post(
                url,
                headers=self.headers,
                json=data or {},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    def _put(self, endpoint: str, data: dict = None) -> dict:
        """Make a PUT request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            response = httpx.put(
                url,
                headers=self.headers,
                json=data or {},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    def _is_project_allowed(self, project_name: str) -> bool:
        """Check if project is in allowed list"""
        if not self.allowed_projects:
            return True
        return project_name.lower() in self.allowed_projects
    
    def list_users(self) -> Dict[str, Any]:
        """
        List all users in the company
        
        Returns:
            Dictionary with list of users
        """
        result = self._get('users')
        
        if 'error' in result:
            return result
        
        users = []
        for u in result.get('content', []):
            users.append({
                'id': u.get('id'),
                'name': u.get('realName', ''),
                'email': u.get('email', ''),
                'is_admin': u.get('isAdmin', False),
                'status': u.get('status', 'offline')
            })
        
        return {
            "success": True,
            "count": len(users),
            "users": users
        }
    
    def list_projects(self) -> Dict[str, Any]:
        """
        List all accessible projects
        
        Returns:
            Dictionary with list of projects
        """
        result = self._get('projects')
        
        if 'error' in result:
            return result
        
        projects = []
        for p in result.get('content', []):
            if self._is_project_allowed(p.get('title', '')):
                projects.append({
                    'id': p.get('id'),
                    'title': p.get('title'),
                    'deleted': p.get('deleted', False)
                })
        
        return {
            "success": True,
            "count": len(projects),
            "projects": projects
        }
    
    def list_boards(self, project_id: str) -> Dict[str, Any]:
        """
        List boards in a project
        
        Args:
            project_id: YouGile project ID
        
        Returns:
            Dictionary with list of boards
        """
        result = self._get('boards', {'projectId': project_id})
        
        if 'error' in result:
            return result
        
        boards = []
        for b in result.get('content', []):
            boards.append({
                'id': b.get('id'),
                'title': b.get('title'),
                'deleted': b.get('deleted', False)
            })
        
        return {
            "success": True,
            "project_id": project_id,
            "count": len(boards),
            "boards": boards
        }
    
    def list_columns(self, board_id: str) -> Dict[str, Any]:
        """
        List columns in a board
        
        Args:
            board_id: YouGile board ID
        
        Returns:
            Dictionary with list of columns
        """
        result = self._get('columns', {'boardId': board_id})
        
        if 'error' in result:
            return result
        
        columns = []
        for c in result.get('content', []):
            columns.append({
                'id': c.get('id'),
                'title': c.get('title'),
                'color': c.get('color'),
                'deleted': c.get('deleted', False)
            })
        
        return {
            "success": True,
            "board_id": board_id,
            "count": len(columns),
            "columns": columns
        }
    
    def list_tasks(
        self,
        column_id: Optional[str] = None,
        board_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        List tasks in a column or board.
        Note: YouGile API v2 only supports columnId for tasks listing,
        so if board_id is provided, we first fetch all columns and then tasks.
        
        Args:
            column_id: YouGile column ID
            board_id: YouGile board ID (fetches tasks from all columns)
            limit: Maximum number of tasks
        
        Returns:
            Dictionary with list of tasks
        """
        if not column_id and not board_id:
            return {"error": "Either column_id or board_id is required"}
        
        all_tasks = []
        
        if column_id:
            # Direct column query
            result = self._get('tasks', {'columnId': column_id, 'limit': limit})
            if 'error' in result:
                return result
            all_tasks = result.get('content', [])
        else:
            # Get all columns for the board, then tasks from each
            columns_result = self.list_columns(board_id)
            if 'error' in columns_result:
                return columns_result
            
            for col in columns_result.get('columns', []):
                if col.get('deleted'):
                    continue
                result = self._get('tasks', {'columnId': col['id'], 'limit': limit})
                if 'error' not in result:
                    all_tasks.extend(result.get('content', []))
                if len(all_tasks) >= limit:
                    all_tasks = all_tasks[:limit]
                    break
        
        tasks = []
        for t in all_tasks:
            tasks.append({
                'id': t.get('id'),
                'title': t.get('title'),
                'description': (t.get('description') or '')[:500],
                'column_id': t.get('columnId'),
                'completed': t.get('completed', False),
                'deadline': t.get('deadline'),
                'assigned': t.get('assigned', []),
                'created_at': t.get('createdAt'),
                'updated_at': t.get('updatedAt')
            })
        
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }
    
    def get_task(self, task_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a task
        
        Args:
            task_id: YouGile task ID
        
        Returns:
            Dictionary with task details
        """
        result = self._get(f'tasks/{task_id}')
        
        if 'error' in result:
            return result
        
        t = result
        return {
            "success": True,
            "task": {
                'id': t.get('id'),
                'title': t.get('title'),
                'description': t.get('description') or '',
                'column_id': t.get('columnId'),
                'completed': t.get('completed', False),
                'deadline': t.get('deadline'),
                'assigned': t.get('assigned', []),
                'subtasks': t.get('subtasks', []),
                'checklists': t.get('checklists', []),
                'comments_count': len(t.get('chat', {}).get('messages', [])),
                'created_at': t.get('createdAt'),
                'updated_at': t.get('updatedAt'),
                'time_tracking': t.get('timeTracking')
            }
        }
    
    def search_tasks(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """
        Search for tasks by text (client-side filtering).
        YouGile API v2 does not support server-side search,
        so we fetch tasks from all boards and filter locally.
        
        Args:
            query: Search query
            limit: Maximum number of results
        
        Returns:
            Dictionary with search results
        """
        query_lower = query.lower()
        matched_tasks = []
        
        # Get all projects
        projects_result = self.list_projects()
        if 'error' in projects_result:
            return projects_result
        
        for project in projects_result.get('projects', []):
            if project.get('deleted'):
                continue
            project_id = project.get('id')
            
            # Get boards for each project
            boards_result = self.list_boards(project_id)
            if 'error' in boards_result:
                continue
            
            for board in boards_result.get('boards', []):
                if board.get('deleted'):
                    continue
                board_id = board.get('id')
                
                # Get columns for each board, then tasks
                cols_result = self.list_columns(board_id)
                if 'error' in cols_result:
                    continue
                
                board_tasks = []
                for col in cols_result.get('columns', []):
                    if col.get('deleted'):
                        continue
                    tasks_result = self._get('tasks', {'columnId': col['id'], 'limit': 100})
                    if 'error' not in tasks_result:
                        board_tasks.extend(tasks_result.get('content', []))
                
                for t in board_tasks:
                    title = t.get('title', '')
                    description = t.get('description') or ''
                    if query_lower in title.lower() or query_lower in description.lower():
                        matched_tasks.append({
                            'id': t.get('id'),
                            'title': title,
                            'description': description[:200],
                            'column_id': t.get('columnId'),
                            'completed': t.get('completed', False),
                            'project': project.get('title'),
                            'board': board.get('title')
                        })
                        if len(matched_tasks) >= limit:
                            break
                
                if len(matched_tasks) >= limit:
                    break
            if len(matched_tasks) >= limit:
                break
        
        return {
            "success": True,
            "query": query,
            "count": len(matched_tasks),
            "tasks": matched_tasks
        }
    
    def create_task(
        self,
        column_id: str,
        title: str,
        description: Optional[str] = None,
        deadline: Optional[str] = None,
        assigned: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new task
        
        Args:
            column_id: Column ID to create task in
            title: Task title
            description: Optional task description
            deadline: Optional deadline (ISO format)
            assigned: Optional list of assignee IDs
        
        Returns:
            Dictionary with created task data
        """
        data = {
            'columnId': column_id,
            'title': title
        }
        if description:
            data['description'] = md_to_html(description)
        if deadline:
            data['deadline'] = deadline
        if assigned:
            data['assigned'] = assigned
        
        result = self._post('tasks', data)
        
        if 'error' in result:
            return result
        
        return {
            "success": True,
            "task_id": result.get('id'),
            "title": result.get('title'),
            "message": f"Задача '{title}' создана"
        }
    
    def update_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        completed: Optional[bool] = None,
        column_id: Optional[str] = None,
        deadline: Optional[str] = None,
        assigned: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing task
        
        Args:
            task_id: Task ID to update
            title: New title
            description: New description
            completed: Mark as completed/uncompleted
            column_id: Move to another column
            deadline: New deadline
            assigned: List of user IDs to assign (use [] to unassign all)
        
        Returns:
            Dictionary with update result
        """
        data = {}
        if title is not None:
            data['title'] = title
        if description is not None:
            data['description'] = md_to_html(description)
        if completed is not None:
            data['completed'] = completed
        if column_id is not None:
            data['columnId'] = column_id
        if deadline is not None:
            data['deadline'] = deadline
        if assigned is not None:
            data['assigned'] = assigned
        
        if not data:
            return {"error": "No fields to update"}
        
        result = self._put(f'tasks/{task_id}', data)
        
        if 'error' in result:
            return result
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Задача обновлена"
        }
    
    # Async versions
    async def _aget(self, endpoint: str, params: dict = None) -> dict:
        """Make an async GET request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self.headers,
                    params=params or {},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    async def _apost(self, endpoint: str, data: dict = None) -> dict:
        """Make an async POST request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=self.headers,
                    json=data or {},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    async def _aput(self, endpoint: str, data: dict = None) -> dict:
        """Make an async PUT request to YouGile API"""
        url = f"{self.base_url}/api-v2/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    url,
                    headers=self.headers,
                    json=data or {},
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = str(e)
            try:
                error_body = e.response.json()
                error_detail = f"{e}: {error_body}"
            except:
                error_detail = f"{e}: {e.response.text[:500]}"
            logger.error(f"YouGile API error: {error_detail}")
            return {"error": error_detail}
        except httpx.HTTPError as e:
            return {"error": str(e)}
    
    async def alist_users(self) -> Dict[str, Any]:
        """Async version of list_users"""
        result = await self._aget('users')
        
        if 'error' in result:
            return result
        
        users = []
        for u in result.get('content', []):
            users.append({
                'id': u.get('id'),
                'name': u.get('realName', ''),
                'email': u.get('email', ''),
                'is_admin': u.get('isAdmin', False),
                'status': u.get('status', 'offline')
            })
        
        return {
            "success": True,
            "count": len(users),
            "users": users
        }
    
    async def alist_projects(self) -> Dict[str, Any]:
        """Async version of list_projects"""
        result = await self._aget('projects')
        
        if 'error' in result:
            return result
        
        projects = []
        for p in result.get('content', []):
            if self._is_project_allowed(p.get('title', '')):
                projects.append({
                    'id': p.get('id'),
                    'title': p.get('title'),
                    'deleted': p.get('deleted', False)
                })
        
        return {
            "success": True,
            "count": len(projects),
            "projects": projects
        }
    
    async def alist_boards(self, project_id: str) -> Dict[str, Any]:
        """Async version of list_boards"""
        result = await self._aget('boards', {'projectId': project_id})
        
        if 'error' in result:
            return result
        
        boards = []
        for b in result.get('content', []):
            boards.append({
                'id': b.get('id'),
                'title': b.get('title'),
                'deleted': b.get('deleted', False)
            })
        
        return {
            "success": True,
            "project_id": project_id,
            "count": len(boards),
            "boards": boards
        }
    
    async def alist_columns(self, board_id: str) -> Dict[str, Any]:
        """Async version of list_columns"""
        result = await self._aget('columns', {'boardId': board_id})
        
        if 'error' in result:
            return result
        
        columns = []
        for c in result.get('content', []):
            columns.append({
                'id': c.get('id'),
                'title': c.get('title'),
                'color': c.get('color'),
                'deleted': c.get('deleted', False)
            })
        
        return {
            "success": True,
            "board_id": board_id,
            "count": len(columns),
            "columns": columns
        }
    
    async def alist_tasks(
        self,
        column_id: Optional[str] = None,
        board_id: Optional[str] = None,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Async version of list_tasks"""
        if not column_id and not board_id:
            return {"error": "Either column_id or board_id is required"}
        
        all_tasks = []
        
        if column_id:
            result = await self._aget('tasks', {'columnId': column_id, 'limit': limit})
            if 'error' in result:
                return result
            all_tasks = result.get('content', [])
        else:
            columns_result = await self.alist_columns(board_id)
            if 'error' in columns_result:
                return columns_result
            
            for col in columns_result.get('columns', []):
                if col.get('deleted'):
                    continue
                result = await self._aget('tasks', {'columnId': col['id'], 'limit': limit})
                if 'error' not in result:
                    all_tasks.extend(result.get('content', []))
                if len(all_tasks) >= limit:
                    all_tasks = all_tasks[:limit]
                    break
        
        tasks = []
        for t in all_tasks:
            tasks.append({
                'id': t.get('id'),
                'title': t.get('title'),
                'description': (t.get('description') or '')[:500],
                'column_id': t.get('columnId'),
                'completed': t.get('completed', False),
                'deadline': t.get('deadline'),
                'assigned': t.get('assigned', []),
                'created_at': t.get('createdAt'),
                'updated_at': t.get('updatedAt')
            })
        
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        }
    
    async def aget_task(self, task_id: str) -> Dict[str, Any]:
        """Async version of get_task"""
        result = await self._aget(f'tasks/{task_id}')
        
        if 'error' in result:
            return result
        
        t = result
        return {
            "success": True,
            "task": {
                'id': t.get('id'),
                'title': t.get('title'),
                'description': t.get('description') or '',
                'column_id': t.get('columnId'),
                'completed': t.get('completed', False),
                'deadline': t.get('deadline'),
                'assigned': t.get('assigned', []),
                'subtasks': t.get('subtasks', []),
                'checklists': t.get('checklists', []),
                'comments_count': len(t.get('chat', {}).get('messages', [])),
                'created_at': t.get('createdAt'),
                'updated_at': t.get('updatedAt'),
                'time_tracking': t.get('timeTracking')
            }
        }
    
    async def asearch_tasks(self, query: str, limit: int = 20) -> Dict[str, Any]:
        """Async version of search_tasks - client-side filtering"""
        query_lower = query.lower()
        matched_tasks = []
        
        # Get all projects
        projects_result = await self.alist_projects()
        if 'error' in projects_result:
            return projects_result
        
        for project in projects_result.get('projects', []):
            if project.get('deleted'):
                continue
            project_id = project.get('id')
            
            # Get boards for each project
            boards_result = await self.alist_boards(project_id)
            if 'error' in boards_result:
                continue
            
            for board in boards_result.get('boards', []):
                if board.get('deleted'):
                    continue
                board_id = board.get('id')
                
                # Get columns for each board, then tasks
                cols_result = await self.alist_columns(board_id)
                if 'error' in cols_result:
                    continue
                
                board_tasks = []
                for col in cols_result.get('columns', []):
                    if col.get('deleted'):
                        continue
                    tasks_result = await self._aget('tasks', {'columnId': col['id'], 'limit': 100})
                    if 'error' not in tasks_result:
                        board_tasks.extend(tasks_result.get('content', []))
                
                for t in board_tasks:
                    title = t.get('title', '')
                    description = t.get('description') or ''
                    if query_lower in title.lower() or query_lower in description.lower():
                        matched_tasks.append({
                            'id': t.get('id'),
                            'title': title,
                            'description': description[:200],
                            'column_id': t.get('columnId'),
                            'completed': t.get('completed', False),
                            'project': project.get('title'),
                            'board': board.get('title')
                        })
                        if len(matched_tasks) >= limit:
                            break
                
                if len(matched_tasks) >= limit:
                    break
            if len(matched_tasks) >= limit:
                break
        
        return {
            "success": True,
            "query": query,
            "count": len(matched_tasks),
            "tasks": matched_tasks
        }
    
    async def acreate_task(
        self,
        column_id: str,
        title: str,
        description: Optional[str] = None,
        deadline: Optional[str] = None,
        assigned: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Async version of create_task"""
        data = {
            'columnId': column_id,
            'title': title
        }
        if description:
            data['description'] = md_to_html(description)
        if deadline:
            data['deadline'] = deadline
        if assigned:
            data['assigned'] = assigned
        
        result = await self._apost('tasks', data)
        
        if 'error' in result:
            return result
        
        return {
            "success": True,
            "task_id": result.get('id'),
            "title": result.get('title'),
            "message": f"Задача '{title}' создана"
        }
    
    async def aupdate_task(
        self,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        completed: Optional[bool] = None,
        column_id: Optional[str] = None,
        deadline: Optional[str] = None,
        assigned: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Async version of update_task"""
        data = {}
        if title is not None:
            data['title'] = title
        if description is not None:
            data['description'] = md_to_html(description)
        if completed is not None:
            data['completed'] = completed
        if column_id is not None:
            data['columnId'] = column_id
        if deadline is not None:
            data['deadline'] = deadline
        if assigned is not None:
            data['assigned'] = assigned
        
        if not data:
            return {"error": "No fields to update"}
        
        result = await self._aput(f'tasks/{task_id}', data)
        
        if 'error' in result:
            return result
        
        return {
            "success": True,
            "task_id": task_id,
            "message": "Задача обновлена"
        }


class MultiYouGileTool:
    """Aggregates results from multiple YouGile API tokens."""

    def __init__(self, url: str, tokens: List[Dict[str, str]], allowed_projects: Optional[List[str]] = None):
        """
        Args:
            url: YouGile base URL
            tokens: List of {"name": ..., "token": ...}
            allowed_projects: Optional project name filter
        """
        self._instances: List[YouGileTool] = []
        for t in tokens:
            self._instances.append(
                YouGileTool(url=url, api_key=t["token"], allowed_projects=allowed_projects, token_name=t["name"])
            )
        logger.info(f"MultiYouGileTool initialized with {len(self._instances)} token(s): "
                     + ", ".join(t["name"] for t in tokens))

    def _dedup(self, items: list, key: str = "id") -> list:
        seen = set()
        result = []
        for item in items:
            k = item.get(key)
            if k and k not in seen:
                seen.add(k)
                result.append(item)
        return result

    # --- sync read (aggregate) ---

    def list_users(self) -> Dict[str, Any]:
        all_users = []
        for inst in self._instances:
            r = inst.list_users()
            if "error" not in r:
                all_users.extend(r.get("users", []))
        return {"success": True, "count": len(self._dedup(all_users)), "users": self._dedup(all_users)}

    def list_projects(self) -> Dict[str, Any]:
        all_projects = []
        for inst in self._instances:
            r = inst.list_projects()
            if "error" not in r:
                for p in r.get("projects", []):
                    p["_token"] = inst.token_name
                    all_projects.append(p)
        deduped = self._dedup(all_projects)
        return {"success": True, "count": len(deduped), "projects": deduped}

    def search_tasks(self, query: str, limit: int = 20) -> Dict[str, Any]:
        all_tasks = []
        for inst in self._instances:
            r = inst.search_tasks(query, limit=limit)
            if "error" not in r:
                all_tasks.extend(r.get("tasks", []))
        deduped = self._dedup(all_tasks)[:limit]
        return {"success": True, "query": query, "count": len(deduped), "tasks": deduped}

    # --- sync read (try each token) ---

    def _try_each(self, method_name: str, *args, **kwargs) -> Dict[str, Any]:
        last_err = {"error": "No YouGile tokens configured"}
        for inst in self._instances:
            r = getattr(inst, method_name)(*args, **kwargs)
            if "error" not in r:
                return r
            last_err = r
        return last_err

    def list_boards(self, project_id: str) -> Dict[str, Any]:
        return self._try_each("list_boards", project_id)

    def list_columns(self, board_id: str) -> Dict[str, Any]:
        return self._try_each("list_columns", board_id)

    def list_tasks(self, column_id: Optional[str] = None, board_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        return self._try_each("list_tasks", column_id=column_id, board_id=board_id, limit=limit)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self._try_each("get_task", task_id)

    def create_task(self, column_id: str, title: str, description: Optional[str] = None,
                    deadline: Optional[str] = None, assigned: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._try_each("create_task", column_id=column_id, title=title,
                              description=description, deadline=deadline, assigned=assigned)

    def update_task(self, task_id: str, title: Optional[str] = None, description: Optional[str] = None,
                    completed: Optional[bool] = None, column_id: Optional[str] = None,
                    deadline: Optional[str] = None, assigned: Optional[List[str]] = None) -> Dict[str, Any]:
        return self._try_each("update_task", task_id=task_id, title=title, description=description,
                              completed=completed, column_id=column_id, deadline=deadline, assigned=assigned)

    # --- async read (aggregate) ---

    async def alist_users(self) -> Dict[str, Any]:
        all_users = []
        for inst in self._instances:
            r = await inst.alist_users()
            if "error" not in r:
                all_users.extend(r.get("users", []))
        return {"success": True, "count": len(self._dedup(all_users)), "users": self._dedup(all_users)}

    async def alist_projects(self) -> Dict[str, Any]:
        all_projects = []
        for inst in self._instances:
            r = await inst.alist_projects()
            if "error" not in r:
                for p in r.get("projects", []):
                    p["_token"] = inst.token_name
                    all_projects.append(p)
        deduped = self._dedup(all_projects)
        return {"success": True, "count": len(deduped), "projects": deduped}

    async def asearch_tasks(self, query: str, limit: int = 20) -> Dict[str, Any]:
        all_tasks = []
        for inst in self._instances:
            r = await inst.asearch_tasks(query, limit=limit)
            if "error" not in r:
                all_tasks.extend(r.get("tasks", []))
        deduped = self._dedup(all_tasks)[:limit]
        return {"success": True, "query": query, "count": len(deduped), "tasks": deduped}

    # --- async read (try each token) ---

    async def _atry_each(self, method_name: str, *args, **kwargs) -> Dict[str, Any]:
        last_err = {"error": "No YouGile tokens configured"}
        for inst in self._instances:
            r = await getattr(inst, method_name)(*args, **kwargs)
            if "error" not in r:
                return r
            last_err = r
        return last_err

    async def alist_boards(self, project_id: str) -> Dict[str, Any]:
        return await self._atry_each("alist_boards", project_id)

    async def alist_columns(self, board_id: str) -> Dict[str, Any]:
        return await self._atry_each("alist_columns", board_id)

    async def alist_tasks(self, column_id: Optional[str] = None, board_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
        return await self._atry_each("alist_tasks", column_id=column_id, board_id=board_id, limit=limit)

    async def aget_task(self, task_id: str) -> Dict[str, Any]:
        return await self._atry_each("aget_task", task_id)

    async def acreate_task(self, column_id: str, title: str, description: Optional[str] = None,
                           deadline: Optional[str] = None, assigned: Optional[List[str]] = None) -> Dict[str, Any]:
        return await self._atry_each("acreate_task", column_id=column_id, title=title,
                                     description=description, deadline=deadline, assigned=assigned)

    async def aupdate_task(self, task_id: str, title: Optional[str] = None, description: Optional[str] = None,
                           completed: Optional[bool] = None, column_id: Optional[str] = None,
                           deadline: Optional[str] = None, assigned: Optional[List[str]] = None) -> Dict[str, Any]:
        return await self._atry_each("aupdate_task", task_id=task_id, title=title, description=description,
                                     completed=completed, column_id=column_id, deadline=deadline, assigned=assigned)


# Tool definitions for the agent
YOUGILE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "yougile_list_users",
            "description": "Получить список сотрудников компании в YouGile. Используй для получения ID пользователей при назначении задач.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_list_projects",
            "description": "Получить список проектов в YouGile.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_list_boards",
            "description": "Получить список досок в проекте YouGile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "ID проекта в YouGile"
                    }
                },
                "required": ["project_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_list_columns",
            "description": "Получить список колонок на доске YouGile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "board_id": {
                        "type": "string",
                        "description": "ID доски в YouGile"
                    }
                },
                "required": ["board_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_list_tasks",
            "description": "Получить список задач в колонке или на доске YouGile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "ID колонки (приоритетнее board_id)"
                    },
                    "board_id": {
                        "type": "string",
                        "description": "ID доски (используется если не указан column_id)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество задач (по умолчанию 50)",
                        "default": 50
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_get_task",
            "description": "Получить детальную информацию о задаче в YouGile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID задачи"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_search_tasks",
            "description": "Поиск задач по тексту в YouGile.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальное количество результатов (по умолчанию 20)",
                        "default": 20
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_create_task",
            "description": "Создать новую задачу в YouGile. Для назначения используй ID пользователей из yougile_list_users.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column_id": {
                        "type": "string",
                        "description": "ID колонки для создания задачи"
                    },
                    "title": {
                        "type": "string",
                        "description": "Заголовок задачи"
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание задачи"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Дедлайн в формате ISO (например: 2026-02-20T18:00:00Z)"
                    },
                    "assigned": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список ID пользователей для назначения (получить через yougile_list_users)"
                    }
                },
                "required": ["column_id", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yougile_update_task",
            "description": "Обновить существующую задачу в YouGile. Можно назначить исполнителей через assigned.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID задачи для обновления"
                    },
                    "title": {
                        "type": "string",
                        "description": "Новый заголовок"
                    },
                    "description": {
                        "type": "string",
                        "description": "Новое описание"
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "Отметить как выполненную/невыполненную"
                    },
                    "column_id": {
                        "type": "string",
                        "description": "Переместить в другую колонку"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Новый дедлайн"
                    },
                    "assigned": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список ID пользователей для назначения (получить через yougile_list_users). Передай [] чтобы снять всех исполнителей."
                    }
                },
                "required": ["task_id"]
            }
        }
    }
]
