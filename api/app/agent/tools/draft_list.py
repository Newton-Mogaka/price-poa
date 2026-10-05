"""
Draft list management tools for the agent.
Handle adding/removing items from user's shopping list.
"""
import logging
from typing import Dict, Any
from datetime import datetime
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
            arguments: Tool arguments containing item, quantity, unit, and chat_id

        Returns:
            Dictionary with execution result
        """
        item = arguments.get("item", "").strip()
        quantity = arguments.get("quantity", 1.0)
        unit = arguments.get("unit")
        chat_id = arguments.get("chat_id")

        if not item:
            return {
                "success": False,
                "error": "Item parameter is required and cannot be empty"
            }

        if chat_id is None:
            return {
                "success": False,
                "error": "Chat ID is required for this operation"
            }

        try:
            # Add item to the user's draft list in memory
            draft_list = await _memory_store.get_draft_list(chat_id)

            # Create new draft item
            new_item = {
                "name": item,
                "quantity": quantity,
                "unit": unit,
                "added_at": datetime.utcnow().isoformat()
            }

            draft_list.append(new_item)

            # Save updated draft list
            await _memory_store.set_draft_list(chat_id, draft_list)

            return {
                "success": True,
                "message": f"Added '{item}' to shopping list",
                "item": item,
                "quantity": quantity,
                "unit": unit,
                "draft_list": draft_list
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
            arguments: Tool arguments containing item to remove and chat_id

        Returns:
            Dictionary with execution result
        """
        item = arguments.get("item", "").strip()
        chat_id = arguments.get("chat_id")

        if not item:
            return {
                "success": False,
                "error": "Item parameter is required and cannot be empty"
            }

        if chat_id is None:
            return {
                "success": False,
                "error": "Chat ID is required for this operation"
            }

        try:
            # Remove item from the user's draft list in memory
            draft_list = await _memory_store.get_draft_list(chat_id)

            # Find and remove items matching the name (case-insensitive)
            original_length = len(draft_list)
            draft_list = [it for it in draft_list if it.get("name", "").lower() != item.lower()]

            if len(draft_list) == original_length:
                # Item not found
                return {
                    "success": False,
                    "error": f"Item '{item}' not found in shopping list"
                }

            # Save updated draft list
            await _memory_store.set_draft_list(chat_id, draft_list)

            return {
                "success": True,
                "message": f"Removed '{item}' from shopping list",
                "item": item,
                "draft_list": draft_list
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
            arguments: Tool arguments containing chat_id

        Returns:
            Dictionary with the current draft list
        """
        chat_id = arguments.get("chat_id")

        if chat_id is None:
            return {
                "success": False,
                "error": "Chat ID is required for this operation"
            }

        try:
            # Get draft list from memory
            draft_list = await _memory_store.get_draft_list(chat_id)

            return {
                "success": True,
                "draft_list": draft_list,
                "count": len(draft_list)
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
            arguments: Tool arguments containing chat_id

        Returns:
            Dictionary with execution result
        """
        chat_id = arguments.get("chat_id")

        if chat_id is None:
            return {
                "success": False,
                "error": "Chat ID is required for this operation"
            }

        try:
            # Clear the draft list in memory
            await _memory_store.clear(chat_id)

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