"""
Product search tool for the agent.
Wraps the existing search_pipeline.search_products function and adds pricing data.
"""
import logging
from typing import Dict, Any
from ..adapters.matching import search_products_adapter
from database.connection import get_database
from query_engine import get_product_prices
from bson import ObjectId

logger = logging.getLogger(__name__)


class SearchProductsTool:
    """Tool for searching products."""

    def get_description(self) -> str:
        return """Search for products by name or description with pricing information.
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
                    "description": "Town/city to filter results (e.g., 'Nairobi', 'Nyeri')",
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
        Execute the product search tool with pricing data.

        Args:
            arguments: Tool arguments containing query, location, limit, and chat_id

        Returns:
            Dictionary with search results and pricing information
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
            # Get database connection for pricing lookup
            db = await get_database()

            # Use the adapter to call the existing search function
            search_result = await search_products_adapter(
                query=query,
                location=location,
                limit=limit
            )

            # Get pricing data for each product result
            products_with_pricing = []
            for product_result in search_result.get("results", []):
                try:
                    product_id = product_result.get("product_id")
                    if not product_id:
                        logger.warning("Search result missing product_id")
                        # Skip this result or use as is without pricing?
                        product_with_pricing = product_result.copy()
                        product_with_pricing["pricing_data"] = None
                        products_with_pricing.append(product_with_pricing)
                        continue

                    # Fetch the full product document from the database
                    object_id = ObjectId(product_id)
                    product_doc = await db.products.find_one({"_id": object_id})
                    if not product_doc:
                        logger.warning(f"Product document not found for ID: {product_id}")
                        # Use the search result product as fallback, but without pricing data
                        product_with_pricing = product_result.copy()
                        product_with_pricing["pricing_data"] = None
                        products_with_pricing.append(product_with_pricing)
                        continue

                    # Get pricing data for this product
                    prices_data = await get_product_prices(db, product_doc, town=location)

                    # Combine product info with pricing data
                    # We return the full product document with an added "pricing_data" field
                    product_with_pricing = product_doc.copy()
                    product_with_pricing["pricing_data"] = prices_data
                    products_with_pricing.append(product_with_pricing)
                except Exception as e:
                    logger.warning(f"Could not get pricing for product {product_result.get('product_id', 'unknown')}: {e}")
                    # Still include the product but without pricing data
                    # Use the search result product as fallback
                    product_with_pricing = product_result.copy()
                    product_with_pricing["pricing_data"] = None
                    products_with_pricing.append(product_with_pricing)

            return {
                "success": True,
                "results": products_with_pricing,
                "no_confident_match": search_result.get("no_confident_match", True),
                "count": len(products_with_pricing)
            }
        except Exception as e:
            logger.error(f"Error in search_products tool: {e}")
            return {
                "success": False,
                "error": f"Failed to search products: {str(e)}"
            }


# Create a singleton instance
search_products_tool = SearchProductsTool()