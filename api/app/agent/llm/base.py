"""
LLM client base interface.
Defines the common interface for all LLM providers.
"""
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request to the LLM.

        Args:
            messages: List of message dictionaries (role, content)
            tools: Optional list of tool definitions in JSON schema format
            tool_choice: Tool choice strategy ("auto", "none", or specific tool)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with LLM response containing:
            - content: Text response
            - tool_calls: List of tool calls if any (each with id, name, arguments)
        """
        pass