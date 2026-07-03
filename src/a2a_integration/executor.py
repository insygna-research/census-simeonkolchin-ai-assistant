"""A2A AgentExecutor wrapping TeamAgent."""

import logging
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message

logger = logging.getLogger(__name__)


class TeamAssistantExecutor(AgentExecutor):
    """Bridges A2A protocol requests to TeamAgent.chat()."""

    def __init__(self, agent):
        self.agent = agent

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        user_text = context.get_user_input()
        if not user_text:
            await event_queue.enqueue_event(
                new_agent_text_message("Empty message received.")
            )
            return

        session_id = f"a2a_{context.context_id or context.task_id or 'default'}"
        logger.info(f"A2A execute: session={session_id}, text={user_text[:120]}")

        try:
            result = await self.agent.chat(user_text, session_id)
            await event_queue.enqueue_event(new_agent_text_message(result))
        except Exception as e:
            logger.error(f"A2A execute error: {e}", exc_info=True)
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=context.task_id or "",
                    context_id=context.context_id or "",
                    final=True,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(f"Error: {e}"),
                    ),
                )
            )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        session_id = f"a2a_{context.context_id or context.task_id or 'default'}"
        self.agent.stop_session(session_id)
        logger.info(f"A2A cancel: session={session_id}")
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id or "",
                context_id=context.context_id or "",
                final=True,
                status=TaskStatus(state=TaskState.canceled),
            )
        )
