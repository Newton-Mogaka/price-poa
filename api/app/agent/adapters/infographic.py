"""
Adapter for infographic generation.
Wraps existing infographic generation code.
"""
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path

# Import existing PricePoa infographic functions
try:
    from infographics.generator import generate_shopping_list_image
except ImportError as e:
    logging.warning(f"Could not import existing infographic functions: {e}")

logger = logging.getLogger(__name__)


async def generate_shopping_list_image_adapter(
    data: Dict[str, Any]
) -> Optional[str]:
    """
    Adapter for generating shopping list images that wraps the existing infographic generator.

    Args:
        data: Dictionary containing shopping list data for image generation
              Expected keys: stores, recommendation, savings, date, item_count (optional)

    Returns:
        Path to generated image file or None if failed
    """
    try:
        # Validate required data
        if not isinstance(data, dict):
            logger.error("Invalid data provided to infographic adapter: expected dictionary")
            return None

        required_keys = ["stores", "recommendation", "savings", "date"]
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            logger.error(f"Missing required keys in infographic data: {missing_keys}")
            return None

        # Generate the image using the existing function
        image_bytes = generate_shopping_list_image(data)

        if not image_bytes:
            logger.error("Infographic generation returned empty bytes")
            return None

        # Save to a temporary file
        temp_dir = Path("/tmp")
        temp_dir.mkdir(exist_ok=True)

        # Create a unique filename
        import uuid
        filename = f"shopping_list_{uuid.uuid4().hex[:8]}.png"
        file_path = temp_dir / filename

        # Write the image bytes to file
        with open(file_path, "wb") as f:
            f.write(image_bytes)

        logger.info(f"Generated infographic saved to: {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Error in generate_shopping_list_image_adapter: {e}", exc_info=True)
        return None