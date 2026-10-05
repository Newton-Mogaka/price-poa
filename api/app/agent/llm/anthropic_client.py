"""
Anthropic LLM client implementation.
"""
import os
from typing import List, Dict, Any, Optional
from anthropic import Anthropic
from .base import LLMClient


class AnthropicClient(LLMClient):
    """Anthropic LLM client."""

    def __init__(self, api_key: str, model: str):
        """
        Initialize Anthropic client.

        Args:
            api_key: Anthropic API key
            model: Model name to use (e.g., "claude-3-haiku-20240307")
        """
        self.client = Anthropic(api_key=api_key)
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
        Send a chat request to Anthropic.

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
            # Convert messages to Anthropic format
            # Anthropic expects: system prompt (if any) + user/assistant messages
            system_messages = [m for m in messages if m.get("role") == "system"]
            conversation_messages = [m for m in messages if m.get("role") in ("user", "assistant")]

            system_prompt = ""
            if system_messages:
                # Combine all system messages
                system_prompt = "\n".join([m.get("content", "") for m in system_messages])

            # Prepare request parameters
            params = {
                "model": self.model,
                "messages": conversation_messages,
                "temperature": temperature,
            }

            if system_prompt:
                params["system"] = system_prompt

            if max_tokens is not None:
                params["max_tokens"] = max_tokens

            if tools:
                # Convert tools to Anthropic format
                anthropic_tools = []
                for tool in tools:
                    if tool.get("type") == "function":
                        anthropic_tools.append({
                            "name": tool["function"]["name"],
                            "description": tool["function"].get("description", ""),
                            "input_schema": tool["function"]["parameters"],
                        })
                if anthropic_tools:
                    params["tools"] = anthropic_tools
                    params["tool_choice"] = {"type": tool_choice} if tool_choice != "auto" else {"type": "auto"}

            # Make the API call
            response = self.client.messages.create(**params)

            # Extract response
            content_blocks = response.content
            text_content = ""
            tool_calls = []

            for block in content_blocks:
                if block.type == "text":
                    text_content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    })

            result = {
                "content": text_content,
                "tool_calls": tool_calls,
            }

            return result

        except Exception as e:
            # Re-raise with context
            raise Exception(f"Anthropic API error: {str(e)}") from e