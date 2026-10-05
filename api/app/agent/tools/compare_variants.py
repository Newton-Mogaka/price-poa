"""
Product variant comparison tool for the agent.
Compares prices of specific product variants across stores.
"""
import logging
from typing import Dict, Any, List
from ..adapters.matching import compare_variants_adapter

logger = logging.getLogger(__name__)


class CompareVariantsTool:
    """Tool for comparing product variants."""

    def get_description(self) -> str:
        return """Compare prices of specific product variants across stores.
        Use this when the user wants to compare prices of specific products they've identified.
        Parameters:
        - product_ids (list[str]): List of product IDs to compare
        - location (str, optional): Town/city to filter results (e.g., "Nairobi", "Nyeri")"""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "product_ids": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of product IDs to compare",
                    "minItems": 1
                },
                "location": {
                    "type": "string",
                    "description": "Town/city to filter results (e.g., 'Nairobi', 'Nyeri')"
                }
            },
            "required": ["product_ids"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the compare variants tool.

        Args:
            arguments: Tool arguments containing product_ids, optional location, and chat_id

        Returns:
            Dictionary with comparison results
        """
        product_ids = arguments.get("product_ids", [])
        location = arguments.get("location")
        chat_id = arguments.get("chat_id")  # chat_id is accepted but not used in this tool

        if not product_ids or not isinstance(product_ids, list):
            return {
                "success": False,
                "error": "product_ids parameter is required and must be a list"
            }

        # Validate that all items are strings
        if not all(isinstance(pid, str) for pid in product_ids):
            return {
                "success": False,
                "error": "All product_ids must be strings"
            }

        try:
            # Use the adapter to call the existing comparison function
            result = await compare_variants_adapter(
                product_ids=product_ids,
                location=location
            )
            return {
                "success": True,
                "comparison": result,
                "product_count": len(product_ids)
            }
        except Exception as e:
            logger.error(f"Error in compare_variants tool: {e}")
            return {
                "success": False,
                "error": f"Failed to compare variants: {str(e)}"
            }


# Create a singleton instance
compare_variants_tool = CompareVariantsTool()