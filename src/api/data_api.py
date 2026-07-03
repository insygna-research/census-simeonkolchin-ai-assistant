"""REST API for YouGile and Telegram data (used by Agent ITSM)."""

import logging
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/data", tags=["data"])


def _get_agent():
    from src.app import agent
    return agent


@router.get("/yougile/projects")
async def yougile_projects():
    agent = _get_agent()
    if not agent or not agent.yougile_tool:
        return JSONResponse({"error": "YouGile not configured"}, status_code=400)
    return await agent.yougile_tool.alist_projects()


@router.get("/yougile/boards")
async def yougile_boards(project_id: str = Query(...)):
    agent = _get_agent()
    if not agent or not agent.yougile_tool:
        return JSONResponse({"error": "YouGile not configured"}, status_code=400)
    return await agent.yougile_tool.alist_boards(project_id)


@router.get("/yougile/columns")
async def yougile_columns(board_id: str = Query(...)):
    agent = _get_agent()
    if not agent or not agent.yougile_tool:
        return JSONResponse({"error": "YouGile not configured"}, status_code=400)
    return await agent.yougile_tool.alist_columns(board_id)


@router.get("/yougile/task/{task_id}/raw")
async def yougile_task_raw(task_id: str):
    """Return raw API response for a task (for debugging URL format)."""
    agent = _get_agent()
    if not agent or not agent.yougile_tool:
        return JSONResponse({"error": "YouGile not configured"}, status_code=400)
    return await agent.yougile_tool._aget(f"tasks/{task_id}")


@router.get("/yougile/task/{task_id}/display-id")
async def yougile_task_display_id(task_id: str):
    """Return idTaskProject (BSU-12) for building YouGile links."""
    agent = _get_agent()
    if not agent or not agent.yougile_tool:
        return JSONResponse({"error": "YouGile not configured"}, status_code=400)
    try:
        task = await agent.yougile_tool._aget(f"tasks/{task_id}")
        if isinstance(task, dict) and "error" in task:
            return JSONResponse(task, status_code=400)
        display_id = task.get("idTaskProject") or task.get("idTaskCommon")
        return {"task_id": task_id, "display_id": display_id}
    except Exception as e:
        logger.exception("Failed to get task display id")
        return JSONResponse({"error": str(e)}, status_code=500)
