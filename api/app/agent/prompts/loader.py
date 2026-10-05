"""
Prompt loader for the agent.
Loads and manages prompt templates.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_system_prompt() -> str:
    """
    Load the system prompt for the agent.

    Returns:
        System prompt string
    """
    try:
        # Get the path to the system prompt file
        current_dir = Path(__file__).parent
        system_prompt_path = current_dir / "system.md"

        if system_prompt_path.exists():
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                logger.debug("Loaded system prompt from file")
                return content
        else:
            logger.warning(f"System prompt file not found: {system_prompt_path}")
            # Return a default system prompt
            return get_default_system_prompt()

    except Exception as e:
        logger.error(f"Error loading system prompt: {e}")
        return get_default_system_prompt()


def get_default_system_prompt() -> str:
    """
    Get a default system prompt if the file cannot be loaded.

    Returns:
        Default system prompt string
    """
    return """You are a helpful shopping assistant for PricePoa, a Kenyan grocery price comparison service.

Your role is to help users find grocery prices, compare products, and create shopping lists.

IMPORTANT RULES:
1. Never invent prices, store names, or comparisons - every numerical claim must come from a tool result in the same conversation turn
2. If a product is not tracked in the system, say so clearly
3. Only mention prices, stores, savings, or comparisons if you have obtained that information from executing tools in this turn
4. Understand and respond in the user's language (mix of English, Swahili, and Sheng is common)
5. Keep responses short and Telegram-friendly
6. Ask at most one clarifying question when location or product is ambiguous
7. The current draft list and saved location are provided in context each turn

Available tools:
- search_products: Search for products by name/description
- compare_variants: Compare prices of specific product variants
- add_to_list: Add items to the shopping list
- remove_from_list: Remove items from the shopping list
- get_draft_list: View the current shopping list
- clear_draft_list: Clear the shopping list
- build_basket: Generate a shopping list comparison and infographic

When users ask for a shopping list or to "make me the list", use the build_basket tool to generate a comparison image.

Always execute tools to get information before making claims about products, prices, or stores.
"""