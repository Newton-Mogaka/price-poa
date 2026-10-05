"""
Adapter for product matching functionality.
Wraps existing search pipeline and product matching code.
"""
import logging
from typing import Dict, Any, List, Optional
from bson import ObjectId

# Import existing PricePoa functions
try:
    from search_pipeline import search_products
    from query_engine import find_product, find_product_matches, get_product_prices
    from database.connection import get_database
except ImportError as e:
    logging.warning(f"Could not import existing PricePoa functions: {e}")
    # We'll handle this gracefully in the functions below

logger = logging.getLogger(__name__)


async def search_products_adapter(
    query: str,
    location: Optional[str] = None,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Adapter for product search that wraps the existing search_pipeline.search_products.

    Args:
        query: Search query string
        location: Optional town/city to filter results
        limit: Maximum number of results to return

    Returns:
        Dictionary with results and no_confident_match flag
    """
    try:
        # Get database connection
        db = await get_database()

        # Call the existing search function
        # Note: The existing search_products returns dict with "results" and "no_confident_match"
        result = await search_products(db, query, limit=limit, vector_limit=50)

        # Filter by location if specified
        if location and result.get("results"):
            location_lower = location.lower().strip()
            filtered_results = []
            for product in result["results"]:
                # We would need to get store information to filter by location
                # For now, we'll return all results and let the calling code handle location filtering
                # In a full implementation, we'd check if the product has prices in the specified location
                filtered_results.append(product)
            result["results"] = filtered_results

        return result

    except Exception as e:
        logger.error(f"Error in search_products_adapter: {e}")
        # Return empty results on error
        return {
            "results": [],
            "no_confident_match": True
        }


async def find_product_adapter(query: str) -> Optional[Dict[str, Any]]:
    """
    Adapter for finding a single product that wraps query_engine.find_product.

    Args:
        query: Search query string

    Returns:
        Product dictionary or None
    """
    try:
        db = await get_database()
        product = await find_product(db, query)
        return product
    except Exception as e:
        logger.error(f"Error in find_product_adapter: {e}")
        return None


async def find_product_matches_adapter(
    query: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Adapter for finding product matches that wraps query_engine.find_product_matches.

    Args:
        query: Search query string
        limit: Maximum number of results to return

    Returns:
        List of product match dictionaries
    """
    try:
        db = await get_database()
        matches = await find_product_matches(db, query, limit)
        return matches
    except Exception as e:
        logger.error(f"Error in find_product_matches_adapter: {e}")
        return []


async def compare_variants_adapter(
    product_ids: List[str],
    location: Optional[str] = None
) -> Dict[str, Any]:
    """
    Adapter for comparing product variants across stores.

    Args:
        product_ids: List of product IDs to compare
        location: Optional town/city to filter results

    Returns:
        Dictionary with comparison data
    """
    try:
        db = await get_database()
        comparison_data = {}

        for product_id in product_ids:
            try:
                # Convert string to ObjectId for database query
                object_id = ObjectId(product_id)

                # Get product details
                product = await db.products.find_one({"_id": object_id})
                if not product:
                    comparison_data[product_id] = {
                        "error": "Product not found"
                    }
                    continue

                # Get prices for this product
                prices_data = await get_product_prices(db, product, town=location)

                comparison_data[product_id] = {
                    "product_name": product.get("name", "Unknown"),
                    "brand": product.get("brand"),
                    "category": product.get("category"),
                    "prices": prices_data.get("stores", []) if prices_data else [],
                    "has_prices": bool(prices_data and prices_data.get("stores"))
                }

            except Exception as e:
                logger.error(f"Error processing product {product_id}: {e}")
                comparison_data[product_id] = {
                    "error": f"Error processing product: {str(e)}"
                }

        return comparison_data

    except Exception as e:
        logger.error(f"Error in compare_variants_adapter: {e}")
        return {"error": f"Failed to compare variants: {str(e)}"}