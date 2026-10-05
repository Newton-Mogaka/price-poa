"""
Product search tool for the agent.
Wraps the existing search_pipeline.search_products function.
"""
import logging
from typing import Dict, Any
from ..adapters.matching import search_products_adapter

logger = logging.getLogger(__name__)


class SearchProductsTool:
    """Tool for searching products."""

    def get_description(self) -> str:
        return """Search for products by name or description.
        Use this when the user asks about product prices, availability, or wants to find products.
        Parameters:
        - query (str): The search query (product name or description)
        - location (str, optional): Town/city to filter results (e.g., "Nairobi", "Nyeri")
        - limit (int, optional): Maximum number of results to return (default: 5)"""

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query (product name or description)"
                },
                "location": {
                    "type": "string",
                    "description": "Town/city to filter results (e.g., 'Nairobi', 'Nyeri')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                }
            },
            "required": ["query"]
        }

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the product search tool.

        Args:
            arguments: Tool arguments containing query, location, limit, and chat_id

        Returns:
            Dictionary with search results
        """
        query = arguments.get("query", "").strip()
        location = arguments.get("location")
        limit = arguments.get("limit", 5)
        chat_id = arguments.get("chat_id")  # chat_id is accepted but not used in this tool

        if not query:
            return {
                "success": False,
                "error": "Query parameter is required"
            }

        try:
            # Use the adapter to call the existing search function
            result = await search_products_adapter(
                query=query,
                location=location,
                limit=limit
            )
            return {
                "success": True,
                "results": result.get("results", []),
                "no_confident_match": result.get("no_confident_match", True),
                "count": len(result.get("results", []))
            }
        except Exception as e:
            logger.error(f"Error in search_products tool: {e}")
            return {
                "success": False,
                "error": f"Failed to search products: {str(e)}"
            }


# Create a singleton instance
search_products_tool = SearchProductsTool()