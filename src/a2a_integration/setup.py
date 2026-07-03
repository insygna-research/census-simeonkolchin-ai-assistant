"""A2A server setup: Agent Card, skills, and route registration."""

import logging
from fastapi import FastAPI

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from src.a2a_integration.executor import TeamAssistantExecutor
from src.config import settings

logger = logging.getLogger(__name__)


def _build_skills() -> list[AgentSkill]:
    """Build the list of agent skills based on enabled integrations."""
    skills = []

    if settings.validate_telegram_config():
        skills.append(AgentSkill(
            id="telegram_operations",
            name="Telegram Operations",
            description="Read messages from Telegram chats, search messages, get chat info, send messages to allowed chats",
            tags=["telegram", "chat", "messages"],
            examples=[
                "Прочитай последние 20 сообщений из чата @company_support",
                "Отправь сообщение в чат @internal_team: задача принята",
            ],
        ))

    if settings.validate_yougile_config():
        skills.append(AgentSkill(
            id="yougile_operations",
            name="YouGile Task Management",
            description="Create, update, search tasks in YouGile. Manage projects, boards, columns. Assign tasks to team members.",
            tags=["yougile", "tasks", "project-management"],
            examples=[
                "Создай задачу 'Исправить баг авторизации' в проекте Platform на доске Backend",
                "Покажи все задачи в колонке 'В работе' на доске Frontend",
            ],
        ))

    if settings.validate_gitlab_config():
        skills.append(AgentSkill(
            id="gitlab_operations",
            name="GitLab Operations",
            description="List projects, get commits, merge requests, pipelines and jobs from GitLab",
            tags=["gitlab", "git", "ci-cd"],
            examples=[
                "Покажи последние коммиты в проекте backend",
                "Какие MR открыты в проекте frontend?",
            ],
        ))

    if settings.validate_outline_config():
        skills.append(AgentSkill(
            id="outline_operations",
            name="Outline Wiki Operations",
            description="Search, read, create and update documents in Outline Wiki. Read document attachments (DOC, DOCX, TXT).",
            tags=["outline", "wiki", "docs"],
            examples=[
                "Найди документ про архитектуру в Outline",
            ],
        ))

    skills.append(AgentSkill(
        id="web_search",
        name="Web Search",
        description="Search the internet and news via DuckDuckGo",
        tags=["search", "web"],
        examples=["Найди информацию о последних обновлениях Python 3.13"],
    ))

    return skills


def build_agent_card() -> AgentCard:
    """Build the Agent Card describing this agent's capabilities."""
    return AgentCard(
        name="Team Assistant",
        description=(
            "AI-assistant for development teams. "
            "Integrates with Telegram, YouGile, GitLab, Outline Wiki and web search. "
            "Accepts tasks in natural language and executes multi-step workflows."
        ),
        url=f"http://{settings.HOST}:{settings.PORT}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=_build_skills(),
    )


def register_a2a_routes(app: FastAPI, agent) -> None:
    """Register A2A protocol routes on the existing FastAPI app."""
    agent_card = build_agent_card()

    executor = TeamAssistantExecutor(agent)
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    a2a_app = A2AFastAPIApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    a2a_app.add_routes_to_app(app)

    logger.info("A2A protocol routes registered")
    logger.info(f"  Agent Card: GET /.well-known/agent.json")
    logger.info(f"  JSON-RPC:   POST /")
    logger.info(f"  Skills:     {[s.id for s in agent_card.skills]}")
