"""
Query parser module for the search pipeline.
Extracts structured attributes (brand, category, size, unit, keywords) from user queries.
"""

import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import logging

from .config import get_config

logger = logging.getLogger(__name__)

@dataclass
class ParsedQuery:
    """Result of query parsing."""
    # Original query
    original: str = ""

    # Normalized query (from normalizer)
    normalized: str = ""

    # Extracted attributes
    brand: Optional[str] = None
    category: Optional[str] = None
    size: Optional[float] = None
    unit: Optional[str] = None

    # Remaining keywords after attribute extraction
    keywords: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'original': self.original,
            'normalized': self.normalized,
            'brand': self.brand,
            'category': self.category,
            'size': self.size,
            'unit': self.unit,
            'keywords': self.keywords,
            'metadata': self.metadata
        }

class QueryParser:
    """
    Parses user queries to extract structured attributes:
    - brand
    - category
    - size
    - unit
    - remaining keywords
    """

    def __init__(self):
        """Initialize the query parser."""
        self.config = get_config()
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for attribute extraction."""

        # use the brand indicators from the config
        query_parser_config = self.config.get('query_parser', {})

        brand_terms = query_parser_config.get('brand_terms', [])
        if brand_terms:
            # Escape each term, sort longest-first so multi-word brands are matched before shorter ones
            escaped_brands = sorted(
                (re.escape(term.strip()) for term in brand_terms if term.strip()),
                key=len, reverse=True
            )

            # Combined brand pattern
            #wrap in \b...\b for word-boundary matching
            brand_pattern = r'\b(?:' + '|'.join(escaped_brands) + r')\b'
            self.brand_pattern = re.compile(brand_pattern, re.IGNORECASE)
        else:
            # if config has nothing, fall back to empty-match pattern
            self.brand_pattern = re.compile(r'(?!)')

        # Category patterns - common product categories
        category_terms = query_parser_config.get('category_terms', [])

        if category_terms:
            escaped_categories = sorted(
                (re.escape(term.strip()) for term in category_terms if term.strip()),
                key=len, reverse=True
            )
            category_pattern = r'\b(?:' + '|'.join(escaped_categories) + r')\b'
            self.category_pattern = re.compile(category_pattern, re.IGNORECASE)
        else:
            self.category_pattern = re.compile(r'(?!)')
        # Size and unit patterns
        size_unit_patterns = [
            # Pattern: number + space + unit
            (r'\b(\d+(?:\.\d+)?)\s*(kg|kgs?|kilogram|kilograms|g|grams?|gram|ml|milliliters?|millilitres?l|ltr|litre|liter|litres|liters|oz|ounces?|lb|lbs?|pound|pounds)\b', 'size_unit'),
            # Pattern: number + unit (no space)
            (r'\b(\d+(?:\.\d+)?)(kg|kgs?|kilogram|kilograms|g|grams?|gram|ml|milliliters?|millilitres?l|ltr|litre|liter|litres|liters|oz|ounces?|lb|lbs?|pound|pounds)\b', 'size_unit_nospace'),
            # Pattern: fraction + unit
            (r'\b(half|quarter)\s+(kg|kgs?|kilogram|kilograms|g|grams?|gram|ml|milliliters?|millilitres?l|ltr|litre|liter|litres|liters|oz|ounces?|lb|lbs?|pound|pounds)\b', 'fraction_unit'),
        ]

        self.size_unit_patterns = [
            (re.compile(pattern, re.IGNORECASE), group_type)
            for pattern, group_type in size_unit_patterns
        ]

    def parse_query(self, query: str) -> ParsedQuery:
        """
        Parse a query to extract structured attributes.

        Args:
            query: User query string

        Returns:
            ParsedQuery object with extracted attributes
        """
        if not query or not isinstance(query, str):
            return ParsedQuery(original="", normalized="")

        # Store original
        parsed = ParsedQuery(original=query)

        # First normalize the query using the normalizer
        from .normalizer import normalize_text
        norm_result = normalize_text(query)
        parsed.normalized = norm_result.normalized

        # Work with normalized text for parsing
        text_to_parse = norm_result.normalized

        # Extract brand
        brand_match = self.brand_pattern.search(text_to_parse)
        if brand_match:
            parsed.brand = brand_match.group(0).lower()
            # Remove the brand from text for further processing
            text_to_parse = self.brand_pattern.sub(' ', text_to_parse)

        # Extract category
        category_match = self.category_pattern.search(text_to_parse)
        if category_match:
            parsed.category = category_match.group(0).lower()
            # Remove the category from text for further processing
            text_to_parse = self.category_pattern.sub(' ', text_to_parse)

        # Extract size and unit
        size_unit_found = False
        for pattern, group_type in self.size_unit_patterns:
            match = pattern.search(text_to_parse)
            if match:
                if group_type in ['size_unit', 'size_unit_nospace']:
                    # Standard number+unit or numberunit format
                    size_str = match.group(1)
                    unit_str = match.group(2)

                    try:
                        parsed.size = float(size_str)
                        parsed.unit = self._normalize_unit(unit_str)
                        size_unit_found = True
                    except ValueError:
                        pass

                    # Remove the matched portion
                    text_to_parse = pattern.sub(' ', text_to_parse)
                    break

                elif group_type == 'fraction_unit':
                    # Handle fractions like "half kg"
                    fraction_word = match.group(1)
                    unit_str = match.group(2)

                    fraction_map = {
                        'half': 0.5,
                        'quarter': 0.25
                    }

                    if fraction_word in fraction_map:
                        parsed.size = fraction_map[fraction_word]
                        parsed.unit = self._normalize_unit(unit_str)
                        size_unit_found = True

                    # Remove the matched portion
                    text_to_parse = pattern.sub(' ', text_to_parse)
                    break

        # Extract remaining keywords (split by whitespace and filter)
        words = text_to_parse.split()
        parsed.keywords = [word.strip() for word in words if word.strip() and len(word.strip()) > 1]

        # Clean up extracted fields
        if parsed.brand:
            parsed.brand = parsed.brand.strip()
        if parsed.category:
            parsed.category = parsed.category.strip()
        if parsed.unit:
            parsed.unit = parsed.unit.strip().upper()

        # Add metadata
        parsed.metadata = {
            'original_length': len(query),
            'normalized_length': len(norm_result.normalized),
            'tokens_count': len(norm_result.tokens),
            'extracted_fields': {
                'brand': parsed.brand is not None,
                'category': parsed.category is not None,
                'size': parsed.size is not None,
                'unit': parsed.unit is not None,
                'keywords_count': len(parsed.keywords)
            }
        }

        return parsed

    def _normalize_unit(self, unit: str) -> str:
        """
        Normalize unit to standard form.

        Args:
            unit: Unit string to normalize

        Returns:
            Normalized unit string
        """
        unit_lower = unit.lower().strip()

        unit_mapping = {
            # Mass/Weight
            'kg': 'kg',
            'kgs': 'kg',
            'kilogram': 'kg',
            'kilograms': 'kg',
            'g': 'g',
            'gram': 'g',
            'grams': 'g',

            # Volume
            'ml': 'ml',
            'milliliter': 'ml',
            'milliliters': 'ml',
            'millilitre': 'ml',
            'millilitres': 'ml',
            'ltr': 'L',
            'litre': 'L',
            'liter': 'L',
            'litres': 'L',
            'liters': 'L',

            # Other units
            'oz': 'oz',
            'ounce': 'oz',
            'ounces': 'oz',
            'lb': 'lb',
            'pound': 'lb',
            'pounds': 'lb',
        }

        return unit_mapping.get(unit_lower, unit_lower.upper() if len(unit_lower) <= 2 else unit_lower)

# Convenience functions
def parse_query(query: str) -> ParsedQuery:
    """
    Convenience function to parse a query.

    Args:
        query: User query string

    Returns:
        ParsedQuery object
    """
    parser = QueryParser()
    return parser.parse_query(query)

def extract_brand_category_size_unit(query: str) -> tuple[Optional[str], Optional[str], Optional[float], Optional[str]]:
    """
    Convenience function to extract brand, category, size, and unit from query.

    Args:
        query: User query string

    Returns:
        Tuple of (brand, category, size, unit)
    """
    parsed = parse_query(query)
    return parsed.brand, parsed.category, parsed.size, parsed.unit

def extract_keywords(query: str) -> List[str]:
    """
    Convenience function to extract keywords from query.

    Args:
        query: User query string

    Returns:
        List of keywords
    """
    parsed = parse_query(query)
    return parsed.keywords