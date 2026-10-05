"""
Tool registry for the agent.
Manages tool specifications and execution.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from .search_products import search_products_tool
from .compare_variants import compare_variants_tool
from .draft_list import (
    add_to_list_tool,
    remove_from_list_tool,
    get_draft_list_tool,
    clear_draft_list_tool
)
from .build_basket import build_basket_tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for agent tools."""

    def __init__(self):
        """Initialize the tool registry with available tools."""
        self._tools: Dict[str, Any] = {
            "search_products": search_products_tool,
            "compare_variants": compare_variants_tool,
            "add_to_list": add_to_list_tool,
            "remove_from_list": remove_from_list_tool,
            "get_draft_list": get_draft_list_tool,
            "clear_draft_list": clear_draft_list_tool,
            "build_basket": build_basket_tool,
        }

    def get_tool_specs(self) -> List[Dict[str, Any]]:
        """
        Get specifications for all available tools in LLM-friendly format.

        Returns:
            List of tool specifications for LLM tool calling
        """
        specs = []
        for tool_name, tool_impl in self._tools.items():
            specs.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_impl.get_description(),
                    "parameters": tool_impl.get_parameters(),
                }
            })
        return specs

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool

        Returns:
            Tool execution result

        Raises:
            KeyError: If tool_name is not registered
            Exception: If tool execution fails
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not found in registry")

        tool_impl = self._tools[tool_name]
        logger.debug(f"Executing tool '{tool_name}' with arguments: {arguments}")

        try:
            result = await tool_impl.execute(arguments)
            logger.debug(f"Tool '{tool_name}' executed successfully")
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            raise e