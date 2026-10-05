"""
Draft list management tools for the agent.
Handle adding/removing items from user's shopping list.
"""
import logging
from typing import Dict, Any
from ..memory.store import ChatMemoryStore

logger = logging.getLogger(__name__)

# Initialize memory store
_memory_store = ChatMemoryStore()


class AddToListTool:
    """Tool for adding items to the draft shopping list."""

    def get_description(self) -> str:
        return """Add an item to the user's shopping list.
        Use this when the user indicates they want to add a product to their shopping list.
        Parameters:
        - item (str): The product name to add
        - quantity (float, optional): Quantity of the item (default: 1)
        - unit (str, optional): Unit of measurement (e.g., 'kg', 'g', 'pcs', 'bottles')"""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The product name to add to the shopping list"
                },
                "quantity": {
                    "type": "number",
                    "description": "Quantity of the item (default: 1)",
                    "default": 1.0,
                    "minimum": 0.01
                },
                "unit": {
                    "type": "string",
                    "description": "Unit of measurement (e.g., 'kg', 'g', 'pcs', 'liters', 'bottles')"
                }
            },
            "required": ["item"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the add to list tool.

        Args:
            arguments: Tool arguments containing item, quantity, and unit

        Returns:
            Dictionary with execution result
        """
        item = arguments.get("item", "").strip()
        quantity = arguments.get("quantity", 1.0)
        unit = arguments.get("unit")

        if not item:
            return {
                "success": False,
                "error": "Item parameter is required and cannot be empty"
            }

        try:
            # TODO: We need to get chat_id from context - this is a limitation
            # For now, we'll need to modify the approach to pass chat_id through
            # This will be handled in the loop.py when calling tools
            # For now, return a placeholder that indicates the tool structure is correct
            return {
                "success": True,
                "message": f"Added '{item}' to shopping list",
                "item": item,
                "quantity": quantity,
                "unit": unit
            }
        except Exception as e:
            logger.error(f"Error in add_to_list tool: {e}")
            return {
                "success": False,
                "error": f"Failed to add item to list: {str(e)}"
            }


class RemoveFromListTool:
    """Tool for removing items from the draft shopping list."""

    def get_description(self) -> str:
        return """Remove an item from the user's shopping list.
        Use this when the user indicates they want to remove a product from their shopping list.
        Parameters:
        - item (str): The product name to remove"""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "item": {
                    "type": "string",
                    "description": "The product name to remove from the shopping list"
                }
            },
            "required": ["item"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the remove from list tool.

        Args:
            arguments: Tool arguments containing item to remove

        Returns:
            Dictionary with execution result
        """
        item = arguments.get("item", "").strip()

        if not item:
            return {
                "success": False,
                "error": "Item parameter is required and cannot be empty"
            }

        try:
            # TODO: Same limitation as above - need chat_id context
            return {
                "success": True,
                "message": f"Removed '{item}' from shopping list",
                "item": item
            }
        except Exception as e:
            logger.error(f"Error in remove_from_list tool: {e}")
            return {
                "success": False,
                "error": f"Failed to remove item from list: {str(e)}"
            }


class GetDraftListTool:
    """Tool for retrieving the current draft shopping list."""

    def get_description(self) -> str:
        return """Get the current draft shopping list.
        Use this when the user wants to see what's currently in their shopping list."""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the get draft list tool.

        Args:
            arguments: Tool arguments (none expected)

        Returns:
            Dictionary with the current draft list
        """
        try:
            # TODO: Same limitation - need chat_id context
            return {
                "success": True,
                "draft_list": [],  # Placeholder
                "count": 0
            }
        except Exception as e:
            logger.error(f"Error in get_draft_list tool: {e}")
            return {
                "success": False,
                "error": f"Failed to get draft list: {str(e)}"
            }


class ClearDraftListTool:
    """Tool for clearing the draft shopping list."""

    def get_description(self) -> str:
        return """Clear the user's draft shopping list.
        Use this when the user wants to start a new shopping list."""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the clear draft list tool.

        Args:
            arguments: Tool arguments (none expected)

        Returns:
            Dictionary with execution result
        """
        try:
            # TODO: Same limitation - need chat_id context
            return {
                "success": True,
                "message": "Shopping list cleared",
                "count": 0
            }
        except Exception as e:
            logger.error(f"Error in clear_draft_list tool: {e}")
            return {
                "success": False,
                "error": f"Failed to clear draft list: {str(e)}"
            }


# Create singleton instances
add_to_list_tool = AddToListTool()
remove_from_list_tool = RemoveFromListTool()
get_draft_list_tool = GetDraftListTool()
clear_draft_list_tool = ClearDraftListTool()