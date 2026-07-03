"""
Team Agent - Main agent for development team assistance
"""

import json
import logging
from typing import Dict, List, Any, Optional, AsyncIterator, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime

from src.config import settings
from src.llm.factory import LLMFactory, LLMClient
from src.tools.gitlab_tool import GitLabTool, GITLAB_TOOLS
from src.tools.yougile_tool import YouGileTool, MultiYouGileTool, YOUGILE_TOOLS
from src.tools.outline_tool import OutlineTool, MultiOutlineTool, OUTLINE_TOOLS
from src.storage.integrations import IntegrationStore
from src.tools.telegram_tool import TelegramTool, TELEGRAM_TOOLS
from src.tools.web_search_tool import WebSearchTool, WEB_SEARCH_TOOLS
from src.tools.browser_tool import BrowserTool, BROWSER_TOOLS
from src.tools.icloud_tool import ICloudTool, ICLOUD_TOOLS
from src.storage.chat_db import ChatDB

logger = logging.getLogger(__name__)


class StopRequestedException(Exception):
    """Exception raised when user requests to stop execution"""
    pass


# Type alias for progress callback
ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]

# Human-readable tool names and descriptions
TOOL_LABELS = {
    # GitLab
    "gitlab_list_projects": {"icon": "📁", "label": "Список проектов GitLab"},
    "gitlab_get_commits": {"icon": "📝", "label": "Коммиты"},
    "gitlab_get_merge_requests": {"icon": "🔀", "label": "Merge Requests"},
    "gitlab_get_mr_details": {"icon": "🔍", "label": "Детали MR"},
    "gitlab_get_pipelines": {"icon": "🚀", "label": "Пайплайны"},
    "gitlab_get_pipeline_jobs": {"icon": "⚙️", "label": "Джобы пайплайна"},
    
    # iCloud
    "icloud_list_calendars": {"icon": "📆", "label": "Календари iCloud"},
    "icloud_list_events": {"icon": "📅", "label": "События календаря"},
    "icloud_create_event": {"icon": "🗓️", "label": "Создание события"},
    "icloud_list_reminders": {"icon": "✅", "label": "Напоминания iCloud"},
    "icloud_create_reminder": {"icon": "➕", "label": "Создание напоминания"},
    "icloud_complete_reminder": {"icon": "☑️", "label": "Завершение напоминания"},

    # Outline
    "outline_search": {"icon": "🔍", "label": "Поиск в Outline"},
    "outline_get_document": {"icon": "📄", "label": "Загрузка документа"},
    "outline_list_collections": {"icon": "📚", "label": "Список коллекций"},
    "outline_create_document": {"icon": "✏️", "label": "Создание документа"},
    "outline_update_document": {"icon": "📝", "label": "Обновление документа"},
    "outline_get_attachments": {"icon": "📎", "label": "Вложения документа"},
    "outline_read_attachment": {"icon": "📖", "label": "Чтение вложения"},
    
    # YouGile
    "yougile_list_users": {"icon": "👥", "label": "Сотрудники YouGile"},
    "yougile_list_projects": {"icon": "📋", "label": "Проекты YouGile"},
    "yougile_list_boards": {"icon": "📊", "label": "Доски YouGile"},
    "yougile_list_columns": {"icon": "📑", "label": "Колонки доски"},
    "yougile_list_tasks": {"icon": "📌", "label": "Задачи"},
    "yougile_get_task": {"icon": "📄", "label": "Детали задачи"},
    "yougile_search_tasks": {"icon": "🔍", "label": "Поиск задач"},
    "yougile_create_task": {"icon": "➕", "label": "Создание задачи"},
    "yougile_update_task": {"icon": "✏️", "label": "Обновление задачи"},
    
    # Telegram
    "telegram_list_chats": {"icon": "💬", "label": "Список чатов"},
    "telegram_get_messages": {"icon": "📨", "label": "Сообщения"},
    "telegram_search_messages": {"icon": "🔎", "label": "Поиск в чате"},
    "telegram_get_chat_info": {"icon": "ℹ️", "label": "Информация о чате"},
    "telegram_send_message": {"icon": "✉️", "label": "Отправка сообщения"},
    
    # Web Search
    "web_search": {"icon": "🌐", "label": "Поиск в интернете"},
    "web_search_news": {"icon": "📰", "label": "Поиск новостей"},
    "web_search_google": {"icon": "🔍", "label": "Поиск в Google"},
    "web_search_yandex": {"icon": "🔎", "label": "Поиск в Яндексе"},
    "web_search_multi": {"icon": "🔎", "label": "Мультипоиск"},

    # Browser
    "browser_navigate": {"icon": "🌐", "label": "Открытие страницы"},
    "browser_snapshot": {"icon": "👁️", "label": "Vision-снимок страницы"},
    "browser_click": {"icon": "🖱️", "label": "Клик"},
    "browser_fill": {"icon": "⌨️", "label": "Ввод текста"},
    "browser_type_text": {"icon": "⌨️", "label": "Набор текста"},
    "browser_press_key": {"icon": "⌨️", "label": "Нажатие клавиши"},
    "browser_get_text": {"icon": "📖", "label": "Чтение текста"},
    "browser_screenshot": {"icon": "📸", "label": "Скриншот"},
    "browser_scroll": {"icon": "📜", "label": "Прокрутка"},
    "browser_go_back": {"icon": "⬅️", "label": "Назад"},
    "browser_hover": {"icon": "👆", "label": "Наведение"},
    "browser_wait_for": {"icon": "⏳", "label": "Ожидание элемента"},
    "browser_evaluate": {"icon": "⚡", "label": "JavaScript"},
    "browser_select_option": {"icon": "📋", "label": "Выбор опции"},
    "browser_close": {"icon": "❌", "label": "Закрытие браузера"},
}


@dataclass
class Session:
    """User session with conversation history"""
    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    stop_requested: bool = field(default=False)
    
    def request_stop(self):
        """Request to stop the current execution"""
        self.stop_requested = True
    
    def reset_stop(self):
        """Reset the stop flag"""
        self.stop_requested = False
    
    def is_stop_requested(self) -> bool:
        """Check if stop was requested"""
        return self.stop_requested
    
    def add_message(self, role: str, content: str):
        """Add a message to the session history"""
        self.messages.append({
            "role": role,
            "content": content
        })
        self.last_active = datetime.now()
    
    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages in the session"""
        return self.messages
    
    def trim_messages(self, max_messages: int = None, max_tokens: int = None):
        """Trim old messages to stay within limits"""
        if max_messages and len(self.messages) > max_messages:
            # Keep system message + recent messages
            system_messages = [m for m in self.messages if m["role"] == "system"]
            other_messages = [m for m in self.messages if m["role"] != "system"]
            
            # Keep the most recent messages
            keep_count = max_messages - len(system_messages)
            self.messages = system_messages + other_messages[-keep_count:]


class TeamAgent:
    """
    Main Team Assistant Agent with tool calling capabilities
    """
    
    def __init__(self):
        """Initialize the agent with LLM and tools"""
        self.llm: LLMClient = LLMFactory.create()
        self.chat_db = ChatDB()

        # Initialize tools based on configuration
        self.tool_definitions = []
        self.tools = {}
        self.async_tools = {}
        
        # GitLab Tool
        if settings.validate_gitlab_config():
            self.gitlab_tool = GitLabTool(
                url=settings.GITLAB_URL,
                token=settings.GITLAB_TOKEN,
                allowed_projects=settings.get_gitlab_projects_list()
            )
            self.tools.update({
                "gitlab_list_projects": self.gitlab_tool.list_projects,
                "gitlab_get_commits": self.gitlab_tool.get_commits,
                "gitlab_get_merge_requests": self.gitlab_tool.get_merge_requests,
                "gitlab_get_mr_details": self.gitlab_tool.get_mr_details,
                "gitlab_get_pipelines": self.gitlab_tool.get_pipelines,
                "gitlab_get_pipeline_jobs": self.gitlab_tool.get_pipeline_jobs,
            })
            self.async_tools.update({
                "gitlab_list_projects": self.gitlab_tool.alist_projects,
                "gitlab_get_commits": self.gitlab_tool.aget_commits,
                "gitlab_get_merge_requests": self.gitlab_tool.aget_merge_requests,
                "gitlab_get_mr_details": self.gitlab_tool.aget_mr_details,
                "gitlab_get_pipelines": self.gitlab_tool.aget_pipelines,
                "gitlab_get_pipeline_jobs": self.gitlab_tool.aget_pipeline_jobs,
            })
            self.tool_definitions.extend(GITLAB_TOOLS)
            logger.info("GitLab tool initialized")
        else:
            logger.warning("GitLab not configured - tool disabled")

        # iCloud Tool (Calendar + Reminders via CalDAV)
        if settings.validate_icloud_config():
            self.icloud_tool = ICloudTool(
                username=settings.ICLOUD_USERNAME,
                password=settings.ICLOUD_APP_PASSWORD,
                caldav_url=settings.ICLOUD_CALDAV_URL,
                tz_name=settings.ICLOUD_TIMEZONE,
                verify_ssl=settings.ICLOUD_VERIFY_SSL,
            )
            self.tools.update({
                "icloud_list_calendars": self.icloud_tool.list_calendars,
                "icloud_list_events": self.icloud_tool.list_events,
                "icloud_create_event": self.icloud_tool.create_event,
                "icloud_list_reminders": self.icloud_tool.list_reminders,
                "icloud_create_reminder": self.icloud_tool.create_reminder,
                "icloud_complete_reminder": self.icloud_tool.complete_reminder,
            })
            self.async_tools.update({
                "icloud_list_calendars": self.icloud_tool.alist_calendars,
                "icloud_list_events": self.icloud_tool.alist_events,
                "icloud_create_event": self.icloud_tool.acreate_event,
                "icloud_list_reminders": self.icloud_tool.alist_reminders,
                "icloud_create_reminder": self.icloud_tool.acreate_reminder,
                "icloud_complete_reminder": self.icloud_tool.acomplete_reminder,
            })
            self.tool_definitions.extend(ICLOUD_TOOLS)
            logger.info("iCloud tool initialized")
        else:
            logger.warning("iCloud not configured - tool disabled")

        # Integration store (unified source management)
        self.integration_store = IntegrationStore()

        # Outline Tool — multi-server support
        outline_servers = self.integration_store.get_outline_servers()
        if not outline_servers and settings.validate_outline_config():
            outline_servers = [{
                "name": "env",
                "url": settings.OUTLINE_URL,
                "api_token": settings.OUTLINE_API_TOKEN,
                "category": "internal",
            }]
        if outline_servers:
            self.outline_tool = MultiOutlineTool(servers=outline_servers)
            self.tools.update({
                "outline_search": self.outline_tool.search_documents,
                "outline_get_document": self.outline_tool.get_document,
                "outline_list_collections": self.outline_tool.list_collections,
                "outline_create_document": self.outline_tool.create_document,
                "outline_update_document": self.outline_tool.update_document,
                "outline_get_attachments": self.outline_tool.get_document_attachments,
                "outline_read_attachment": self.outline_tool.read_document_attachment,
            })
            self.async_tools.update({
                "outline_search": self.outline_tool.asearch_documents,
                "outline_get_document": self.outline_tool.aget_document,
                "outline_list_collections": self.outline_tool.alist_collections,
                "outline_create_document": self.outline_tool.acreate_document,
                "outline_update_document": self.outline_tool.aupdate_document,
                "outline_get_attachments": self.outline_tool.aget_document_attachments,
                "outline_read_attachment": self.outline_tool.aread_document_attachment,
            })
            self.tool_definitions.extend(OUTLINE_TOOLS)
            logger.info(f"Outline tool initialized with {len(outline_servers)} server(s)")
        else:
            logger.warning("Outline not configured - tool disabled")
        
        # YouGile Tool — multi-token support
        yougile_tokens = self.integration_store.get_yougile_tokens()
        if settings.YOUGILE_API_KEY and not any(
            t["token"] == settings.YOUGILE_API_KEY for t in yougile_tokens
        ):
            yougile_tokens.insert(0, {"name": "env", "token": settings.YOUGILE_API_KEY, "category": "internal"})
        if yougile_tokens:
            self.yougile_tool = MultiYouGileTool(
                url=settings.YOUGILE_URL,
                tokens=yougile_tokens,
                allowed_projects=settings.get_yougile_projects_list()
            )
            self.tools.update({
                "yougile_list_users": self.yougile_tool.list_users,
                "yougile_list_projects": self.yougile_tool.list_projects,
                "yougile_list_boards": self.yougile_tool.list_boards,
                "yougile_list_columns": self.yougile_tool.list_columns,
                "yougile_list_tasks": self.yougile_tool.list_tasks,
                "yougile_get_task": self.yougile_tool.get_task,
                "yougile_search_tasks": self.yougile_tool.search_tasks,
                "yougile_create_task": self.yougile_tool.create_task,
                "yougile_update_task": self.yougile_tool.update_task,
            })
            self.async_tools.update({
                "yougile_list_users": self.yougile_tool.alist_users,
                "yougile_list_projects": self.yougile_tool.alist_projects,
                "yougile_list_boards": self.yougile_tool.alist_boards,
                "yougile_list_columns": self.yougile_tool.alist_columns,
                "yougile_list_tasks": self.yougile_tool.alist_tasks,
                "yougile_get_task": self.yougile_tool.aget_task,
                "yougile_search_tasks": self.yougile_tool.asearch_tasks,
                "yougile_create_task": self.yougile_tool.acreate_task,
                "yougile_update_task": self.yougile_tool.aupdate_task,
            })
            self.tool_definitions.extend(YOUGILE_TOOLS)
            logger.info(f"YouGile tool initialized with {len(yougile_tokens)} token(s)")
        else:
            logger.warning("YouGile not configured - no tokens available")
        
        # Telegram Tool
        if settings.validate_telegram_config():
            self.telegram_tool = TelegramTool(
                api_id=settings.TELEGRAM_API_ID,
                api_hash=settings.TELEGRAM_API_HASH,
                phone=settings.TELEGRAM_PHONE,
                session_path=settings.TELEGRAM_SESSION_PATH,
                allowed_chats=settings.get_telegram_allowed_chats_list()
            )
            self.tools.update({
                "telegram_list_chats": lambda: {"error": "Use async version"},
                "telegram_get_messages": lambda **k: {"error": "Use async version"},
                "telegram_search_messages": lambda **k: {"error": "Use async version"},
                "telegram_get_chat_info": lambda **k: {"error": "Use async version"},
                "telegram_send_message": lambda **k: {"error": "Use async version"},
            })
            self.async_tools.update({
                "telegram_list_chats": self.telegram_tool.list_chats,
                "telegram_get_messages": self.telegram_tool.get_messages,
                "telegram_search_messages": self.telegram_tool.search_messages,
                "telegram_get_chat_info": self.telegram_tool.get_chat_info,
                "telegram_send_message": self.telegram_tool.send_message,
            })
            self.tool_definitions.extend(TELEGRAM_TOOLS)
            logger.info("Telegram tool initialized")
        else:
            logger.warning("Telegram not configured - tool disabled")
        
        # Web Search Tool (always enabled)
        self.web_search_tool = WebSearchTool(searxng_url=settings.SEARXNG_URL)
        self.tools.update({
            "web_search": self.web_search_tool.search,
            "web_search_news": self.web_search_tool.search_news,
            "web_search_google": self.web_search_tool.search_google,
            "web_search_yandex": self.web_search_tool.search_yandex,
            "web_search_multi": self.web_search_tool.search_multi,
        })
        self.async_tools.update({
            "web_search": self.web_search_tool.asearch,
            "web_search_news": self.web_search_tool.asearch_news,
            "web_search_google": self.web_search_tool.asearch_google,
            "web_search_yandex": self.web_search_tool.asearch_yandex,
            "web_search_multi": self.web_search_tool.asearch_multi,
        })
        self.tool_definitions.extend(WEB_SEARCH_TOOLS)
        
        # Browser Tool (Playwright)
        self.browser_tool = BrowserTool()
        self.async_tools.update({
            "browser_navigate": self.browser_tool.navigate,
            "browser_snapshot": self.browser_tool.snapshot,
            "browser_click": self.browser_tool.click,
            "browser_fill": self.browser_tool.fill,
            "browser_type_text": self.browser_tool.type_text,
            "browser_press_key": self.browser_tool.press_key,
            "browser_get_text": self.browser_tool.get_text,
            "browser_screenshot": self.browser_tool.screenshot,
            "browser_scroll": self.browser_tool.scroll,
            "browser_go_back": self.browser_tool.go_back,
            "browser_hover": self.browser_tool.hover,
            "browser_wait_for": self.browser_tool.wait_for,
            "browser_evaluate": self.browser_tool.evaluate,
            "browser_select_option": self.browser_tool.select_option,
            "browser_close": self.browser_tool.close,
        })
        self.tool_definitions.extend(BROWSER_TOOLS)
        logger.info("Browser tool initialized (Playwright)")
        
        # Session management
        self.sessions: Dict[str, Session] = {}
        
        all_tool_names = set(self.tools.keys()) | set(self.async_tools.keys())
        logger.info(f"Team Agent initialized with {len(all_tool_names)} tools")
    
    def stop_session(self, session_id: str) -> bool:
        """Request to stop the current execution for a session"""
        if session_id in self.sessions:
            self.sessions[session_id].request_stop()
            logger.info(f"Stop requested for session: {session_id}")
            return True
        return False
    
    def set_reasoning_enabled(self, enabled: bool):
        """Enable or disable DeepSeek reasoning mode"""
        LLMFactory.set_reasoning_enabled(enabled)
        logger.info(f"Reasoning mode {'enabled' if enabled else 'disabled'}")
    
    def is_reasoning_enabled(self) -> bool:
        """Check if reasoning mode is currently enabled"""
        return LLMFactory.is_reasoning_enabled()
    
    def _build_system_prompt(self) -> str:
        """Build system prompt with current date/time and source info."""
        now = datetime.now()
        date_block = (
            f"\n\nТекущая дата и время: {now.strftime('%d.%m.%Y %H:%M')} "
            f"({now.strftime('%A')}).\n"
            f"Текущий год: {now.year}. Всегда используй актуальный год в запросах.\n"
        )
        sources_desc = self.integration_store.describe_for_prompt()
        sources_block = (
            f"\nДоступные источники данных:\n{sources_desc}\n"
            "Результаты инструментов содержат метку [Имя (категория)] — используй для понимания откуда данные.\n"
            "Если пользователь указывает конкретный источник (по имени или URL) — ищи результаты от него.\n"
        )
        return settings.SYSTEM_PROMPT + date_block + sources_block

    def get_or_create_session(self, session_id: str) -> Session:
        """Get existing session or create a new one, restoring history from DB."""
        if session_id not in self.sessions:
            session = Session(session_id=session_id)
            session.add_message("system", self._build_system_prompt())

            # Restore saved messages from DB
            saved = self.chat_db.get_messages(session_id)
            for msg in saved:
                if msg["role"] != "system":
                    session.messages.append(msg)

            self.sessions[session_id] = session
            logger.info(f"Created session: {session_id} (restored {len(saved)} messages)")

        return self.sessions[session_id]
    
    async def chat(
        self,
        message: str,
        session_id: str,
        on_progress: Optional[ProgressCallback] = None,
        model: Optional[str] = None,
        browser_enabled: bool = True,
    ) -> str:
        """
        Process a chat message and return a response.

        Args:
            message: User message
            session_id: Session identifier
            on_progress: Optional async callback for streaming progress updates
            model: Optional LLM model override (e.g. "deepseek/deepseek-chat")
            browser_enabled: Whether browser tools are available for this request
        """
        session = self.get_or_create_session(session_id)

        session.reset_stop()

        session.add_message("user", message)

        # Persist user message
        if not self.chat_db.get_chat(session_id):
            self.chat_db.create_chat(chat_id=session_id)
            self.chat_db.auto_title(session_id, message)
        self.chat_db.save_message(session_id, "user", message)

        session.trim_messages(max_messages=settings.MAX_MESSAGES)

        try:
            response_text = await self._chat_with_tools(
                session, on_progress, model=model, browser_enabled=browser_enabled,
            )

            session.add_message("assistant", response_text)
            self.chat_db.save_message(session_id, "assistant", response_text)

            return response_text

        except StopRequestedException:
            stop_msg = "⏹️ Выполнение остановлено по запросу пользователя."
            session.add_message("assistant", stop_msg)
            self.chat_db.save_message(session_id, "assistant", stop_msg)
            return stop_msg

        except Exception as e:
            logger.error(f"Error in chat: {str(e)}", exc_info=True)
            error_msg = f"Произошла ошибка: {str(e)}"
            session.add_message("assistant", error_msg)
            self.chat_db.save_message(session_id, "assistant", error_msg)
            return error_msg
    
    async def _send_progress(self, callback: Optional[ProgressCallback], event: Dict[str, Any]):
        """Send progress event if callback is provided"""
        if callback:
            try:
                await callback(event)
            except Exception as e:
                logger.warning(f"Error sending progress: {e}")

    async def _vision_describe_screenshot(self, b64: str) -> Optional[str]:
        """Use a vision-capable fallback model to describe a browser screenshot as text."""
        import litellm

        vision_keywords = ("gpt-4o", "gemini", "claude-3", "claude-4")
        vision_model = None
        try:
            for model_cfg in settings.get_llm_models_list():
                model_id = model_cfg.get("id", "").lower()
                if any(kw in model_id for kw in vision_keywords):
                    vision_model = model_cfg["id"]
                    break
        except Exception:
            pass

        if not vision_model:
            return None

        try:
            response = await litellm.acompletion(
                model=vision_model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": (
                            "Кратко опиши что видно на скриншоте браузера: "
                            "основные блоки, формы, поля ввода и их значения, "
                            "кнопки, выпадающие списки, календари. "
                            "Формат: перечисли элементы сверху вниз. Максимум 500 символов."
                        )},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "low",
                        }},
                    ],
                }],
                max_tokens=300,
                timeout=15,
            )
            desc = response.choices[0].message.content
            logger.info(f"Vision fallback via {vision_model}: {len(desc)} chars")
            return desc
        except Exception as e:
            logger.warning(f"Vision fallback failed ({vision_model}): {e}")
            return None

    def _describe_tool_call(self, function_name: str, function_args: Dict[str, Any]) -> str:
        """Create a human-readable description of a tool call"""
        info = TOOL_LABELS.get(function_name, {"icon": "🔧", "label": function_name})
        
        # Build a short description of the arguments
        detail = ""
        if "url" in function_args and function_name.startswith("browser"):
            detail = function_args["url"][:80]
        elif "query" in function_args:
            detail = f'"{function_args["query"]}"'
        elif "project_id" in function_args:
            detail = f'проект: {function_args["project_id"]}'
        elif "task_id" in function_args:
            detail = f'задача: {function_args["task_id"]}'
        elif "chat_id" in function_args:
            detail = f'чат: {function_args["chat_id"]}'
        elif "title" in function_args:
            detail = f'"{function_args["title"]}"'
        elif "mr_iid" in function_args:
            detail = f'MR #{function_args["mr_iid"]}'
        elif "text" in function_args and function_name.startswith("browser"):
            detail = f'"{function_args["text"]}"'
        
        return f'{info["icon"]} {info["label"]}' + (f' — {detail}' if detail else '')

    def _describe_tool_result(self, function_name: str, result: Any) -> str:
        """Create a short summary of tool result"""
        if isinstance(result, dict):
            if "error" in result:
                return f"Ошибка: {result['error']}"
            if "projects" in result:
                return f"Проектов: {len(result['projects'])}"
            if "commits" in result:
                return f"Коммитов: {len(result['commits'])}"
            if "merge_requests" in result:
                return f"MR: {len(result['merge_requests'])}"
            if "pipelines" in result:
                return f"Пайплайнов: {len(result['pipelines'])}"
            if "jobs" in result:
                return f"Джобов: {len(result['jobs'])}"
            if "boards" in result:
                return f"Досок: {len(result['boards'])}"
            if "columns" in result:
                return f"Колонок: {len(result['columns'])}"
            if "tasks" in result:
                return f"Задач: {len(result['tasks'])}"
            if "task" in result:
                return f'Задача: "{result["task"].get("title", "")}"'
            if "chats" in result:
                return f"Чатов: {len(result['chats'])}"
            if "messages" in result:
                return f"Сообщений: {len(result['messages'])}"
            if "chat" in result:
                return f'Чат: "{result["chat"].get("title", "")}"'
            if "results" in result:
                r = result["results"]
                if isinstance(r, list):
                    return f"Результатов: {len(r)}"
            if "merge_request" in result:
                mr = result["merge_request"]
                return f'MR: "{mr.get("title", "")}"'
            if "_has_vision" in result:
                return f'📸 Vision: {result.get("title", "")[:50]} ({result.get("url", "")[:50]})'
            if "title" in result and "url" in result:
                return f'{result["title"][:60]} ({result["url"][:60]})'
            if "filename" in result and "path" in result:
                return f'Файл: {result["filename"]}'
            if "success" in result:
                msg = result.get("message", "Успешно")
                return msg[:80] if isinstance(msg, str) else "Успешно"
        
        s = str(result)
        return s[:80] + "..." if len(s) > 80 else s

    def _estimate_context_chars(self, messages: List[Dict[str, Any]]) -> int:
        """Estimate total character count of all messages"""
        total = 0
        for msg in messages:
            content = msg.get("content") or ""
            total += len(str(content))
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    total += len(tc.get("function", {}).get("arguments", ""))
        return total

    def _trim_tool_context(self, messages: List[Dict[str, Any]], max_chars: int = 50000) -> List[Dict[str, Any]]:
        """
        Trim older tool results to keep context within limits.
        """
        total = self._estimate_context_chars(messages)
        if total <= max_chars:
            return messages
        
        logger.warning(f"Context too large ({total} chars), trimming tool results to {max_chars}")
        
        tool_indices = [
            i for i, m in enumerate(messages)
            if m.get("role") == "tool" and len(str(m.get("content", ""))) > 200
        ]
        
        for idx in tool_indices:
            if self._estimate_context_chars(messages) <= max_chars:
                break
            old_content = messages[idx].get("content", "")
            tool_name = messages[idx].get("name", "tool")
            messages[idx]["content"] = f'[Результат {tool_name} сжат: было {len(old_content)} символов]'
        
        logger.info(f"Context after trimming: {self._estimate_context_chars(messages)} chars")
        return messages

    async def _chat_with_tools(
        self,
        session: Session,
        on_progress: Optional[ProgressCallback] = None,
        model: Optional[str] = None,
        browser_enabled: bool = True,
    ) -> str:
        """Process chat with tool calling support."""
        messages = session.get_messages().copy()
        iteration = 0

        active_tool_defs = self.tool_definitions
        if not browser_enabled:
            browser_names = {t["function"]["name"] for t in BROWSER_TOOLS}
            active_tool_defs = [t for t in self.tool_definitions if t["function"]["name"] not in browser_names]
            logger.info("Browser tools disabled for this request")

        MAX_CONTEXT_CHARS = settings.MAX_CONTEXT_CHARS
        MAX_TOOL_RESULT_CHARS = settings.MAX_TOOL_RESULT_CHARS

        await self._send_progress(on_progress, {
            "event": "thinking",
            "message": "Анализирую запрос..."
        })

        while iteration < settings.MAX_ITERATIONS:
            iteration += 1
            logger.debug(f"Iteration {iteration}/{settings.MAX_ITERATIONS}")

            if session.is_stop_requested():
                logger.info(f"Stop requested, terminating at iteration {iteration}")
                await self._send_progress(on_progress, {
                    "event": "stopped",
                    "message": "Остановлено пользователем"
                })
                raise StopRequestedException()

            messages = self._trim_tool_context(messages, MAX_CONTEXT_CHARS)

            response = await self.llm.achat_completion(
                messages=messages,
                tools=active_tool_defs,
                temperature=0.7,
                model=model,
            )
            
            assistant_message = response.choices[0].message
            
            reasoning_content = self.llm.extract_reasoning(response)
            if reasoning_content:
                await self._send_progress(on_progress, {
                    "event": "reasoning",
                    "message": "Размышление модели",
                    "reasoning": reasoning_content
                })
            
            if not hasattr(assistant_message, 'tool_calls') or not assistant_message.tool_calls:
                await self._send_progress(on_progress, {
                    "event": "done",
                    "message": "Формирую ответ..."
                })
                return assistant_message.content or "Извините, я не смог сформулировать ответ."
            
            if assistant_message.content:
                await self._send_progress(on_progress, {
                    "event": "thinking",
                    "message": assistant_message.content[:200]
                })
            
            assistant_msg = {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            }
            
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            
            messages.append(assistant_msg)
            
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from LLM for tool {function_name}: {e}")
                    logger.debug(f"Raw arguments: {tool_call.function.arguments}")
                    
                    raw_args = tool_call.function.arguments
                    
                    for fix in ['}', '"}', '"}]', '}]']:
                        try:
                            function_args = json.loads(raw_args + fix)
                            logger.info(f"Fixed JSON by adding '{fix}'")
                            break
                        except json.JSONDecodeError:
                            continue
                    else:
                        error_msg = f"Невалидный JSON от LLM: {str(e)}"
                        logger.error(error_msg)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": json.dumps({"error": error_msg}, ensure_ascii=False)
                        })
                        await self._send_progress(on_progress, {
                            "event": "tool_done",
                            "tool": function_name,
                            "description": f"Ошибка парсинга аргументов",
                            "result": error_msg,
                            "success": False,
                        })
                        continue
                
                logger.info(f"Calling tool: {function_name} with args: {function_args}")
                
                description = self._describe_tool_call(function_name, function_args)
                await self._send_progress(on_progress, {
                    "event": "tool_start",
                    "tool": function_name,
                    "description": description,
                    "iteration": iteration,
                    "max_iterations": settings.MAX_ITERATIONS,
                })
                
                try:
                    if function_name in self.async_tools:
                        result = await self.async_tools[function_name](**function_args)
                    elif function_name in self.tools:
                        result = self.tools[function_name](**function_args)
                    else:
                        result = {"error": f"Unknown tool: {function_name}"}
                    
                    result_for_msg = result
                    if isinstance(result, dict) and "_has_vision" in result:
                        result_for_msg = {k: v for k, v in result.items() if k != "_has_vision"}
                    result_str = json.dumps(result_for_msg, ensure_ascii=False, indent=2)
                    
                    if len(result_str) > MAX_TOOL_RESULT_CHARS:
                        result_str = result_str[:MAX_TOOL_RESULT_CHARS] + f"\n\n... [Обрезано: {len(result_str)} -> {MAX_TOOL_RESULT_CHARS} символов]"
                    
                    logger.debug(f"Tool result ({len(result_str)} chars): {result_str[:500]}")
                    
                    result_summary = self._describe_tool_result(function_name, result)
                    await self._send_progress(on_progress, {
                        "event": "tool_done",
                        "tool": function_name,
                        "description": description,
                        "result": result_summary,
                        "success": True,
                    })
                
                except Exception as e:
                    logger.error(f"Error calling tool {function_name}: {str(e)}", exc_info=True)
                    error_detail = str(e)
                    
                    if "missing" in error_detail.lower() and "argument" in error_detail.lower():
                        hint = "Пожалуйста, повтори вызов инструмента со всеми обязательными параметрами."
                    else:
                        hint = "Попробуй другой подход или уточни параметры."
                    
                    result_str = json.dumps({
                        "error": error_detail,
                        "hint": hint,
                        "action_required": "retry_with_correct_parameters"
                    }, ensure_ascii=False)
                    
                    await self._send_progress(on_progress, {
                        "event": "tool_done",
                        "tool": function_name,
                        "description": description,
                        "result": f"Ошибка: {error_detail}",
                        "success": False,
                    })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": result_str
                })

                if function_name == "browser_snapshot" and hasattr(self, "browser_tool"):
                    b64 = self.browser_tool.pop_screenshot_b64()
                    if b64:
                        effective_model = (model or "").lower()
                        vision_ok = any(
                            kw in effective_model
                            for kw in ("gpt-4o", "gpt-4-vision", "gemini", "claude-3", "claude-4")
                        )
                        if vision_ok:
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "[Скриншот текущего состояния браузера для визуального анализа]"},
                                    {"type": "image_url", "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}",
                                        "detail": "low",
                                    }},
                                ],
                            })
                            logger.info("Vision image injected into conversation")
                        else:
                            desc = await self._vision_describe_screenshot(b64)
                            if desc:
                                messages.append({
                                    "role": "user",
                                    "content": f"[Визуальное описание скриншота браузера:\n{desc}]"
                                })
                                logger.info(f"Vision fallback injected ({len(desc)} chars)")
                            else:
                                logger.info("Vision unavailable: no vision-capable fallback model")

                if session.is_stop_requested():
                    logger.info(f"Stop requested after tool {function_name}")
                    await self._send_progress(on_progress, {
                        "event": "stopped",
                        "message": "Остановлено пользователем"
                    })
                    raise StopRequestedException()
        
        logger.warning(f"Max iterations ({settings.MAX_ITERATIONS}) reached for session")
        await self._send_progress(on_progress, {
            "event": "done",
            "message": f"Достигнут лимит итераций ({settings.MAX_ITERATIONS})"
        })
        return f"""Я выполнил максимальное количество операций ({settings.MAX_ITERATIONS}), но всё ещё собираю информацию. 

Чтобы получить ответ, попробуйте:
1. **Уточнить запрос** - сделать его более конкретным
2. **Разбить на части** - задать несколько отдельных вопросов
3. **Упростить** - спросить о конкретном аспекте

Что именно вас интересует больше всего?"""
    
    async def chat_stream(self, message: str, session_id: str) -> AsyncIterator[str]:
        """Stream chat responses"""
        response = await self.chat(message, session_id)
        yield response
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Cleared session: {session_id}")
            return True
        return False
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a session"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return {
            "session_id": session.session_id,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat(),
            "last_active": session.last_active.isoformat()
        }
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all active sessions"""
        return [
            self.get_session_info(session_id)
            for session_id in self.sessions.keys()
        ]
