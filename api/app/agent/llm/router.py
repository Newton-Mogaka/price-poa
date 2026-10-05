"""
LLM router that tries primary provider and falls back on errors.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from .base import LLMClient
from .groq_client import GroqClient
from .anthropic_client import AnthropicClient
from ..config import settings

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM requests to primary provider with fallback.
    Tries Groq first, falls back to Anthropic on errors/timeouts/rate limits.
    """

    def __init__(self):
        """Initialize the LLM router with configured clients."""
        self.primary_client: Optional[LLMClient] = None
        self.fallback_client: Optional[LLMClient] = None
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize primary and fallback LLM clients."""
        # Initialize primary client (Groq)
        if settings.GROQ_API_KEY:
            # Extract model name from format like "groq:model-name"
            primary_model = settings.AGENT_PRIMARY_MODEL
            if primary_model.startswith("groq:"):
                primary_model = primary_model[5:]  # Remove "groq:" prefix

            self.primary_client = GroqClient(
                api_key=settings.GROQ_API_KEY,
                model=primary_model
            )
            logger.info(f"Initialized Groq client with model: {primary_model}")
        else:
            logger.warning("GROQ_API_KEY not set, primary client not initialized")

        # Initialize fallback client (Anthropic)
        if settings.ANTHROPIC_API_KEY:
            # Extract model name from format like "anthropic:model-name"
            fallback_model = settings.AGENT_FALLBACK_MODEL
            if fallback_model.startswith("anthropic:"):
                fallback_model = fallback_model[11:]  # Remove "anthropic:" prefix

            self.fallback_client = AnthropicClient(
                api_key=settings.ANTHROPIC_API_KEY,
                model=fallback_model
            )
            logger.info(f"Initialized Anthropic client with model: {fallback_model}")
        else:
            logger.warning("ANTHROPIC_API_KEY not set, fallback client not initialized")

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request with fallback logic.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            tool_choice: Tool choice strategy
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with LLM response from successful provider
        """
        last_error = None

        # Try primary client first
        if self.primary_client:
            try:
                logger.debug("Attempting LLM request with primary provider (Groq)")
                return await asyncio.wait_for(
                    self.primary_client.chat(
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    timeout=settings.AGENT_LLM_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                last_error = "Primary provider (Groq) timeout"
                logger.warning(last_error)
            except Exception as e:
                last_error = f"Primary provider (Groq) error: {str(e)}"
                logger.warning(last_error)
                # Check if it's a rate limit error
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    logger.warning("Rate limit detected, will try fallback")
        else:
            last_error = "Primary client (Groq) not initialized"
            logger.debug(last_error)

        # Try fallback client
        if self.fallback_client:
            try:
                logger.debug("Attempting LLM request with fallback provider (Anthropic)")
                return await asyncio.wait_for(
                    self.fallback_client.chat(
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    ),
                    timeout=settings.AGENT_LLM_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                last_error = f"Fallback provider (Anthropic) timeout. Last error: {last_error}"
                logger.error(last_error)
                raise Exception(last_error)
            except Exception as e:
                last_error = f"Fallback provider (Anthropic) error: {str(e)}. Last error: {last_error}"
                logger.error(last_error)
                raise Exception(last_error)
        else:
            last_error = f"Fallback client (Anthropic) not initialized. Last error: {last_error}"
            logger.error(last_error)
            raise Exception(last_error)

        # If we get here, both clients failed
        raise Exception(f"All LLM providers failed. Last error: {last_error}")


# Global router instance
llm_router = LLMRouter()