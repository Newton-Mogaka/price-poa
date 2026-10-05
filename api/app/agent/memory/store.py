"""
Memory store for the agent.
Handles persistence of chat history and draft lists in MongoDB.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from bson import ObjectId

from ..config import settings
from ..memory.models import ChatSessionModel, ChatMessageModel

logger = logging.getLogger(__name__)


class ChatMemoryStore:
    """
    Store for chat history and draft shopping lists.
    Uses MongoDB with TTL index for automatic cleanup.
    """

    def __init__(self):
        """Initialize the memory store."""
        self._collection_name = "chat_sessions"

    async def _get_collection(self):
        """Get the MongoDB collection for chat sessions."""
        from database.connection import get_database
        db = await get_database()
        return db[self._collection_name]

    async def load(self, chat_id: int) -> Dict[str, Any]:
        """
        Load a chat session from memory.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Dictionary containing chat session data (messages, draft_list, etc.)
        """
        try:
            collection = await self._get_collection()
            session_doc = await collection.find_one({"chat_id": chat_id})

            if session_doc:
                # Convert ObjectId to string for JSON serialization
                session_doc["_id"] = str(session_doc["_id"])
                return session_doc
            else:
                # Return default session structure
                return {
                    "chat_id": chat_id,
                    "messages": [],
                    "draft_list": [],
                    "location": None,
                    "updated_at": datetime.utcnow()
                }

        except Exception as e:
            logger.error(f"Error loading chat session for chat_id {chat_id}: {e}")
            # Return default session structure on error
            return {
                "chat_id": chat_id,
                "messages": [],
                "draft_list": [],
                "location": None,
                "updated_at": datetime.utcnow()
            }

    async def append_turn(self, chat_id: int, turn_data: Dict[str, Any]) -> None:
        """
        Append a chat turn to the session history.

        Args:
            chat_id: Telegram chat ID
            turn_data: Dictionary containing turn data (user_message, agent_response, used_tools, timestamp)
        """
        try:
            collection = await self._get_collection()
            await collection.update_one(
                {"chat_id": chat_id},
                {
                    "$push": {"messages": turn_data},
                    "$set": {"updated_at": datetime.utcnow()}
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error appending turn to chat session for chat_id {chat_id}: {e}")

    async def set_draft_list(self, chat_id: int, draft_list: List[Dict[str, Any]]) -> None:
        """
        Set the draft shopping list for a chat session.

        Args:
            chat_id: Telegram chat ID
            draft_list: List of draft list items
        """
        try:
            collection = await self._get_collection()
            await collection.update_one(
                {"chat_id": chat_id},
                {
                    "$set": {
                        "draft_list": draft_list,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error setting draft list for chat_id {chat_id}: {e}")

    async def get_draft_list(self, chat_id: int) -> List[Dict[str, Any]]:
        """
        Get the draft shopping list for a chat session.

        Args:
            chat_id: Telegram chat ID

        Returns:
            List of draft list items
        """
        try:
            session_data = await self.load(chat_id)
            return session_data.get("draft_list", [])
        except Exception as e:
            logger.error(f"Error getting draft list for chat_id {chat_id}: {e}")
            return []

    async def clear(self, chat_id: int) -> None:
        """
        Clear a chat session (remove all data).

        Args:
            chat_id: Telegram chat ID
        """
        try:
            collection = await self._get_collection()
            await collection.delete_one({"chat_id": chat_id})
        except Exception as e:
            logger.error(f"Error clearing chat session for chat_id {chat_id}: {e}")

    # Note: TTL index creation should be done during database setup/migrations
    # For now, we rely on the existing database setup to have the TTL index