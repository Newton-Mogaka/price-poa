"""
Pydantic models for agent memory storage.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ChatMessageModel(BaseModel):
    """Model for a chat message in memory."""
    user_message: str = Field(description="Message from the user")
    agent_response: str = Field(description="Response from the agent")
    used_tools: List[str] = Field(default_factory=list, description="Tools used in this turn")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatSessionModel(BaseModel):
    """Model for a chat session in memory."""
    chat_id: int = Field(description="Telegram chat ID")
    messages: List[ChatMessageModel] = Field(default_factory=list, description="Chat history")
    draft_list: List[Dict[str, Any]] = Field(default_factory=list, description="Draft shopping list items")
    location: Optional[str] = Field(default=None, description="User's default location")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")