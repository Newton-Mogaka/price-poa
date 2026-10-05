"""
Basket building tool for the agent.
Creates shopping list comparisons and generates infographics.
"""
import logging
from typing import Dict, Any
from ..adapters.pricing import get_product_prices_adapter
from ..adapters.infographic import generate_shopping_list_image_adapter
from ..memory.store import ChatMemoryStore

logger = logging.getLogger(__name__)

# Initialize memory store
_memory_store = ChatMemoryStore()


class BuildBasketTool:
    """Tool for building a shopping list comparison and generating infographics."""

    def get_description(self) -> str:
        return """Build a shopping list comparison from the user's draft list and generate an infographic.
        Use this when the user asks to see their shopping list, compare prices, or 'make me the list'.
        Parameters:
        - location (str, optional): Town/city for price comparison (e.g., 'Nairobi', 'Nyeri')"""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "Town/city for price comparison (e.g., 'Nairobi', 'Nyeri')"
                }
            },
            "additionalProperties": False
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the build basket tool.

        Args:
            arguments: Tool arguments containing optional location

        Returns:
            Dictionary with basket comparison results and image path
        """
        location = arguments.get("location")

        try:
            # TODO: Need to get chat_id from context to retrieve draft list
            # For now, returning placeholder to show tool structure
            return {
                "success": True,
                "message": "Basket built successfully",
                "image_path": "/tmp/shopping_list.png",  # Placeholder
                "text_summary": "Your shopping list comparison is ready.",
                "location": location
            }
        except Exception as e:
            logger.error(f"Error in build_basket tool: {e}")
            return {
                "success": False,
                "error": f"Failed to build basket: {str(e)}"
            }


# Create a singleton instance
build_basket_tool = BuildBasketTool()