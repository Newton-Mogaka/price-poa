"""
Agent configuration loaded from environment variables.
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    """Agent configuration from environment variables."""

    # Agent enable/disable
    AGENT_ENABLED: bool = Field(default=False, description="Enable/disable the LLM agent")

    # LLM API keys
    GROQ_API_KEY: Optional[str] = Field(default=None, description="Groq API key")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, description="Anthropic API key")

    # Model configuration
    AGENT_PRIMARY_MODEL: str = Field(default="groq:llama3-8b-8192", description="Primary model to use")
    AGENT_FALLBACK_MODEL: str = Field(default="anthropic:claude-3-haiku-20240307", description="Fallback model")

    # Agent behavior
    AGENT_HISTORY_LIMIT: int = Field(default=10, description="Maximum chat history turns to keep")
    AGENT_MAX_TOOL_ITERATIONS: int = Field(default=5, description="Maximum tool call iterations per turn")
    AGENT_LLM_TIMEOUT_S: int = Field(default=20, description="LLM request timeout in seconds")
    AGENT_SESSION_TTL_DAYS: int = Field(default=14, description="Chat session TTL in days")

    class Config:
        case_sensitive = True


# Global settings instance
settings = AgentSettings()