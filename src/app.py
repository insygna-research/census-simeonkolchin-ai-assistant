"""
FastAPI Application with lifecycle management
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.agent.team_agent import TeamAgent

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global agent instance
agent: TeamAgent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    """
    # Startup
    global agent
    
    logger.info("="*60)
    logger.info("Team Assistant Starting...")
    logger.info("="*60)
    logger.info(f"LLM Provider: {settings.LLM_PROVIDER}")
    logger.info(f"LLM Model: {settings.get_llm_model()}")
    logger.info(f"GitLab URL: {settings.GITLAB_URL or 'not configured'}")
    logger.info(f"YouGile URL: {settings.YOUGILE_URL or 'not configured'}")
    logger.info(f"Telegram: {'configured' if settings.TELEGRAM_API_ID else 'not configured'}")
    logger.info("="*60)
    
    try:
        # Initialize agent
        agent = TeamAgent()
        logger.info("Agent initialized successfully")
        all_tools = set(agent.tools.keys()) | set(agent.async_tools.keys())
        logger.info(f"Available tools: {len(all_tools)}")
        
        # Register A2A protocol routes
        from src.a2a_integration.setup import register_a2a_routes
        register_a2a_routes(app, agent)
    except Exception as e:
        logger.error(f"Failed to initialize agent: {str(e)}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Team Assistant Shutting down...")
    if agent and hasattr(agent, "browser_tool"):
        try:
            import asyncio
            await agent.browser_tool.close()
        except Exception:
            pass
    agent = None


# Create FastAPI app
app = FastAPI(
    title="Team Assistant API",
    description="AI-powered assistant for development teams with GitLab, YouGile and Telegram integration",
    version="0.1.0",
    lifespan=lifespan
)

# Auth middleware
from src.auth.middleware import AuthMiddleware
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint - redirects to UI"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agent_initialized": agent is not None,
        "llm_provider": settings.LLM_PROVIDER,
        "gitlab_configured": bool(settings.GITLAB_URL and settings.GITLAB_TOKEN),
        "yougile_configured": bool(settings.YOUGILE_API_KEY),
        "telegram_configured": bool(settings.TELEGRAM_API_ID)
    }


# ──── Sessions ────

@app.get("/api/sessions")
async def list_sessions():
    if not agent:
        return {"error": "Agent not initialized"}
    return {"sessions": agent.list_sessions()}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    if not agent:
        return {"error": "Agent not initialized"}
    info = agent.get_session_info(session_id)
    return info if info else {"error": "Session not found"}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if not agent:
        return {"error": "Agent not initialized"}
    success = agent.clear_session(session_id)
    return {"success": success}


@app.post("/api/chat")
async def chat(request: dict):
    if not agent:
        return {"error": "Agent not initialized"}
    message = request.get("message")
    session_id = request.get("session_id", "default")
    if not message:
        return {"error": "Message is required"}
    try:
        response = await agent.chat(message, session_id)
        return {"response": response, "session_id": session_id}
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return {"error": str(e)}


# ──── Chat history (SQLite) ────

@app.get("/api/chats")
async def list_chats():
    if not agent:
        return {"error": "Agent not initialized"}
    return {"chats": agent.chat_db.list_chats()}


@app.get("/api/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: str):
    if not agent:
        return {"error": "Agent not initialized"}
    messages = agent.chat_db.get_messages(chat_id)
    chat = agent.chat_db.get_chat(chat_id)
    return {"chat": chat, "messages": messages}


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if not agent:
        return {"error": "Agent not initialized"}
    if chat_id in agent.sessions:
        del agent.sessions[chat_id]
    success = agent.chat_db.delete_chat(chat_id)
    return {"success": success}


# ──── Models ────

@app.get("/api/models")
async def list_models():
    return {
        "models": settings.get_llm_models_list(),
        "default": settings.get_default_model(),
    }


# ──── File upload ────

from fastapi import UploadFile, File as FastAPIFile

@app.post("/api/upload")
async def upload_file(file: UploadFile = FastAPIFile(...)):
    from src.tools.file_processor import FileProcessor
    processor = FileProcessor()
    content = await file.read()
    result = processor.process(file.filename, content)
    return result


# ──── Integration sources (YouGile, Outline) ────

from src.storage.integrations import IntegrationStore
_int_store = IntegrationStore()


@app.get("/api/integrations")
async def list_integrations(source_type: str = None, category: str = None):
    return {"sources": _int_store.list_sources(source_type=source_type, category=category)}


@app.post("/api/integrations")
async def add_integration(req: dict):
    try:
        entry = _int_store.add_source(
            source_type=req.get("type", ""),
            name=req.get("name", ""),
            category=req.get("category", "internal"),
            config=req.get("config", {}),
        )
        return {"success": True, **entry}
    except ValueError as e:
        return {"error": str(e)}


@app.put("/api/integrations/{source_id}")
async def update_integration(source_id: str, req: dict):
    ok = _int_store.update_source(
        source_id,
        enabled=req.get("enabled"),
        name=req.get("name"),
        category=req.get("category"),
    )
    return {"success": ok}


@app.delete("/api/integrations/{source_id}")
async def delete_integration(source_id: str):
    ok = _int_store.delete_source(source_id)
    return {"success": ok}


# Legacy compatibility: keep old YouGile token endpoints redirecting to new store
@app.get("/api/yougile/tokens")
async def yg_list_tokens_legacy():
    return {"tokens": _int_store.list_sources(source_type="yougile")}


# ──── Screenshots (browser tool) ────

from fastapi.responses import FileResponse
from pathlib import Path

@app.get("/api/screenshots/{filename}")
async def get_screenshot(filename: str):
    path = Path("data/screenshots") / filename
    if not path.exists() or not path.suffix == ".png":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(str(path), media_type="image/png")


# Import routes
from src.auth.routes import router as auth_router
from src.ui.routes import router as ui_router
from src.ui.telegram_admin import router as telegram_router
from src.api.data_api import router as data_router
app.include_router(auth_router)
app.include_router(ui_router)
app.include_router(telegram_router)
app.include_router(data_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
