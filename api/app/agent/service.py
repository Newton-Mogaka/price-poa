"""
Main agent service - entry point for handling Telegram messages.
"""
import logging
from typing import Optional
from .schemas import AgentReply
from .loop import AgentLoop
from .memory.store import ChatMemoryStore
from .config import settings

logger = logging.getLogger(__name__)


async def handle_message(chat_id: int, text: str, user_ctx: Optional[dict] = None) -> AgentReply:
    """
    Handle a Telegram message and return an agent response.

    This is the main entry point called from the Telegram webhook when AGENT_ENABLED=true.

    Args:
        chat_id: Telegram chat ID
        text: Message text from user
        user_ctx: Optional user context (not currently used)

    Returns:
        AgentReply with text response and optional image path
    """
    if not settings.AGENT_ENABLED:
        # This shouldn't happen if the webhook is configured correctly,
        # but return a safe fallback just in case
        return AgentReply(
            text="Sorry, the agent is currently disabled.",
            used_tools=[]
        )

    try:
        # Initialize memory store and agent loop
        memory_store = ChatMemoryStore()
        agent_loop = AgentLoop(memory_store)

        # Process the message through the agent loop
        reply = await agent_loop.run(chat_id, text, user_ctx or {})

        return reply

    except Exception as e:
        logger.error(f"Error in agent handle_message for chat_id {chat_id}: {e}", exc_info=True)
        # Return a safe fallback message
        return AgentReply(
            text="Sorry, I encountered an error processing your message. Please try again.",
            used_tools=[]
        )