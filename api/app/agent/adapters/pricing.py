"""
Adapter for pricing functionality.
Wraps existing price lookup code.
"""
import logging
from typing import Dict, Any, Optional
from bson import ObjectId

# Import existing PricePoa functions
try:
    from query_engine import get_product_prices
    from database.connection import get_database
except ImportError as e:
    logging.warning(f"Could not import existing PricePoa functions: {e}")

logger = logging.getLogger(__name__)


async def get_product_prices_adapter(
    product_id: str,
    location: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Adapter for getting product prices that wraps query_engine.get_product_prices.

    Args:
        product_id: Product ID string
        location: Optional town/city to filter results

    Returns:
        Dictionary with product pricing data or None
    """
    try:
        # Get database connection
        db = await get_database()

        # Convert string to ObjectId
        try:
            object_id = ObjectId(product_id)
        except Exception:
            logger.error(f"Invalid product ID format: {product_id}")
            return None

        # Get product document
        product = await db.products.find_one({"_id": object_id})
        if not product:
            logger.warning(f"Product not found: {product_id}")
            return None

        # Call the existing price lookup function
        prices_data = await get_product_prices(db, product, town=location)

        return prices_data

    except Exception as e:
        logger.error(f"Error in get_product_prices_adapter: {e}")
        return None