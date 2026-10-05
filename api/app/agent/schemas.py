"""
Pydantic schemas for the agent module.
"""
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ToolResult(BaseModel):
    """Result from a tool execution."""
    name: str = Field(description="Name of the tool that was called")
    success: bool = Field(description="Whether the tool execution succeeded")
    result: dict = Field(description="Tool result data")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")


class DraftItem(BaseModel):
    """Item in the user's draft shopping list."""
    name: str = Field(description="Product name")
    quantity: Optional[float] = Field(default=None, description="Quantity")
    unit: Optional[str] = Field(default=None, description="Unit (kg, g, pc, etc.)")
    resolved_product_id: Optional[str] = Field(default=None, description="Resolved product ID if known")
    added_at: datetime = Field(default_factory=datetime.utcnow)


class ChatTurn(BaseModel):
    """A single turn in the chat conversation."""
    user_message: str = Field(description="Message from the user")
    agent_response: str = Field(description="Response from the agent")
    used_tools: List[str] = Field(default_factory=list, description="Tools used in this turn")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentReply(BaseModel):
    """Response from the agent handler."""
    text: str = Field(description="Text response to send to user")
    image_path: Optional[str] = Field(default=None, description="Path to generated image, if any")
    used_tools: List[str] = Field(default_factory=list, description="List of tools used to generate this reply")