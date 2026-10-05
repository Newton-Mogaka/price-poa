"""
Groq LLM client implementation.
"""
import os
from typing import List, Dict, Any, Optional
from groq import Groq
from .base import LLMClient


class GroqClient(LLMClient):
    """Groq LLM client."""

    def __init__(self, api_key: str, model: str):
        """
        Initialize Groq client.

        Args:
            api_key: Groq API key
            model: Model name to use (e.g., "llama3-8b-8192")
        """
        self.client = Groq(api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request to Groq.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            tool_choice: Tool choice strategy
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with LLM response
        """
        try:
            # Prepare request parameters
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            if tools:
                params["tools"] = tools
                params["tool_choice"] = tool_choice

            # Make the API call
            response = self.client.chat.completions.create(**params)

            # Extract response
            message = response.choices[0].message

            result = {
                "content": message.content or "",
                "tool_calls": [],
            }

            # Handle tool calls if present
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tool_call.id,
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    })

            return result

        except Exception as e:
            # Re-raise with context
            raise Exception(f"Groq API error: {str(e)}") from e