"""
Normalization module for the search pipeline.
Handles text normalization, unit normalization, and synonym expansion for both
products and user queries.
"""

import re
import string
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import logging

from .config import get_normalization_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FIX (Bug 1): Kenyan-market shorthand/abbreviations that use punctuation as
# part of the token (e.g. "m/wave", "w/machine"). These MUST be expanded
# before punctuation is stripped and the text is tokenized, otherwise the
# slash is removed first, the phrase is shredded into separate single-word
# tokens ("m" + "wave"), and no synonym entry can ever match it again.
#
# Patterns are matched case-insensitively as whole tokens/phrases. Extend
# this list (or move it into normalization config) as more shorthand shows
# up in query_logs.
# ---------------------------------------------------------------------------
DEFAULT_ABBREVIATION_PATTERNS: List[Tuple[str, str]] = [
    (r'\bm\s*/\s*wave\b', 'microwave'),
    (r'\bw\s*/\s*machine\b', 'washing machine'),
    (r'\bw\s*/\s*m\b', 'washing machine'),
    (r'\bfridge\b', 'refrigerator'),
    (r'\bfrij\b', 'refrigerator'),
    (r'\bt\s*/\s*v\b', 'tv'),
    (r'\bs\s*/\s*bar\b', 'soundbar'),
    (r'\bwash\s*mach\b', 'washing machine'),
]


@dataclass
class NormalizedText:
    """Result of text normalization."""
    original: str
    normalized: str
    tokens: List[str]
    metadata: Dict[str, Any]

class TextNormalizer:
    """
    Handles text normalization including:
    - Lowercasing
    - Abbreviation/shorthand expansion (phrase-level, punctuation-aware)
    - Punctuation removal
    - Space collapsing
    - Unit normalization
    - Synonym expansion (single-token)
    """

    def __init__(self, synonym_dict_path: Optional[str] = None,
                 abbreviation_dict_path: Optional[str] = None):
        """
        Initialize the text normalizer.

        Args:
            synonym_dict_path: Optional path to synonym dictionary file
            abbreviation_dict_path: Optional path to an abbreviation dictionary
                file (same tab/comma format as the synonym file). Entries here
                are matched as phrases BEFORE punctuation removal.
        """
        self.config = get_normalization_config()
        self.synonym_mappings = self.config['synonym_mappings'].copy()

        # Abbreviation patterns: config-provided patterns win, defaults fill
        # in anything not already covered.
        configured_abbrevs = self.config.get('abbreviation_patterns', [])
        self.abbreviation_patterns_raw: List[Tuple[str, str]] = list(configured_abbrevs) + [
            pat for pat in DEFAULT_ABBREVIATION_PATTERNS
            if pat not in configured_abbrevs
        ]

        # Load synonym dictionary if provided
        if synonym_dict_path:
            self.load_synonym_dictionary(synonym_dict_path)

        # Load abbreviation dictionary if provided (adds/overrides patterns)
        if abbreviation_dict_path:
            self.load_abbreviation_dictionary(abbreviation_dict_path)

        # Compile regex patterns for efficiency
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for normalization."""
        # Punctuation removal pattern
        self.punct_pattern = re.compile(f'[{re.escape(string.punctuation)}]')

        # Multiple spaces pattern
        self.multi_space_pattern = re.compile(r'\s+')

        # Quantity normalization patterns
        self.quantity_patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.config['quantity_patterns']
        ]

        # Abbreviation patterns (case-insensitive, matched before punctuation
        # stripping so phrases like "m/wave" are still intact)
        self.abbreviation_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.abbreviation_patterns_raw
        ]

    def load_synonym_dictionary(self, file_path: str) -> None:
        """
        Load synonym dictionary from file.

        Expected format: one synonym pair per line, separated by tab or comma:
        coke\tcoca cola
        soda\tsoft drink
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Support both tab and comma separated formats
                    if '\t' in line:
                        parts = line.split('\t', 1)
                    elif ',' in line:
                        parts = line.split(',', 1)
                    else:
                        logger.warning(f"Invalid format in synonym file line {line_num}: {line}")
                        continue

                    if len(parts) == 2:
                        key, value = parts[0].strip().lower(), parts[1].strip().lower()
                        self.synonym_mappings[key] = value
                    else:
                        logger.warning(f"Invalid synonym entry in line {line_num}: {line}")

            logger.info(f"Loaded {len(self.synonym_mappings)} synonym mappings from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load synonym dictionary from {file_path}: {e}")

    def load_abbreviation_dictionary(self, file_path: str) -> None:
        """
        Load phrase-level abbreviation patterns from file.

        Expected format: one entry per line, "pattern<TAB or ,>expansion".
        `pattern` is treated as a regex (use \\b word boundaries yourself,
        e.g. "\\bm\\s*/\\s*wave\\b\tmicrowave"). Loaded entries are appended
        after the built-in defaults, so add more specific patterns last if
        ordering matters for your regex set.
        """
        loaded: List[Tuple[str, str]] = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    if '\t' in line:
                        parts = line.split('\t', 1)
                    elif ',' in line:
                        parts = line.split(',', 1)
                    else:
                        logger.warning(f"Invalid format in abbreviation file line {line_num}: {line}")
                        continue

                    if len(parts) == 2:
                        pattern, replacement = parts[0].strip(), parts[1].strip().lower()
                        loaded.append((pattern, replacement))
                    else:
                        logger.warning(f"Invalid abbreviation entry in line {line_num}: {line}")

            self.abbreviation_patterns_raw = loaded + self.abbreviation_patterns_raw
            logger.info(f"Loaded {len(loaded)} abbreviation patterns from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load abbreviation dictionary from {file_path}: {e}")

    def _expand_abbreviations(self, text: str) -> str:
        """
        Expand punctuation-bearing shorthand (e.g. "m/wave" -> "microwave")
        BEFORE punctuation removal / tokenization destroys the phrase.
        """
        expanded = text
        for pattern, replacement in self.abbreviation_patterns:
            expanded = pattern.sub(replacement, expanded)
        return expanded

    def normalize_text(self, text: str) -> NormalizedText:
        """
        Normalize text according to the normalization rules.

        Args:
            text: Input text to normalize

        Returns:
            NormalizedText object containing the normalized text and metadata
        """
        if not text or not isinstance(text, str):
            return NormalizedText(
                original="",
                normalized="",
                tokens=[],
                metadata={'error': 'Invalid input'}
            )

        original = text
        normalized = text.strip()

        # Step 1: Lowercase
        if self.config['text_normalization']['lowercase']:
            normalized = normalized.lower()

        # Step 2: Expand phrase-level abbreviations (FIX: must run before
        # punctuation removal, while "m/wave" / "w/machine" are still intact)
        normalized = self._expand_abbreviations(normalized)

        # Step 3: Remove punctuation
        if self.config['text_normalization']['remove_punctuation']:
            normalized = self.punct_pattern.sub(' ', normalized)

        # Step 4: Apply quantity/unit normalization
        normalized = self._normalize_quantities(normalized)

        # Step 5: Collapse multiple spaces
        if self.config['text_normalization']['collapse_spaces']:
            normalized = self.multi_space_pattern.sub(' ', normalized)

        # Step 6: Final trim
        normalized = normalized.strip()

        # Step 7: Expand single-token synonyms (e.g. "coke" -> "coca cola")
        expanded_tokens = self._expand_synonyms(normalized.split())
        normalized = ' '.join(expanded_tokens)

        # Create tokens list
        tokens = normalized.split() if normalized else []

        return NormalizedText(
            original=original,
            normalized=normalized,
            tokens=tokens,
            metadata={
                'original_length': len(original),
                'normalized_length': len(normalized),
                'token_count': len(tokens)
            }
        )

    def _normalize_quantities(self, text: str) -> str:
        """
        Normalize quantities and units in text.

        Examples:
        2kgs -> 2 kg
        half kg -> 0.5 kg
        500ml -> 500 ml
        """
        normalized = text

        # Apply each quantity pattern
        for pattern, replacement in self.quantity_patterns:
            normalized = pattern.sub(replacement, normalized)

        # Handle special cases like "half kg"
        normalized = re.sub(r'\bhalf\s+(kg|kgs?)\b', r'0.5 \1', normalized)
        normalized = re.sub(r'\bhalf\s+(g|grams?)\b', r'0.5 \1', normalized)
        normalized = re.sub(r'\bhalf\s+(ltr|litre|liter|litres|liters)\b', r'0.5 L', normalized)
        normalized = re.sub(r'\bhalf\s+(ml|milliliter|millilitre|milliliters|millilitres)\b', r'0.5 ml', normalized)

        return normalized

    def _expand_synonyms(self, tokens: List[str]) -> List[str]:
        """
        Expand tokens using synonym dictionary.

        Args:
            tokens: List of text tokens

        Returns:
            List of tokens with synonyms expanded
        """
        expanded = []
        for token in tokens:
            token_lower = token.lower()
            if token_lower in self.synonym_mappings:
                # Replace with synonym
                expanded.append(self.synonym_mappings[token_lower])
            else:
                expanded.append(token)
        return expanded

    def normalize_product_for_indexing(self, product_data: Dict[str, Any]) -> str:
        """
        Create normalized text for product indexing.

        Args:
            product_data: Product document from MongoDB

        Returns:
            Normalized text suitable for embedding generation
        """
        # Extract relevant fields
        name = product_data.get('name', '')
        brand = product_data.get('brand', '') or ''
        category = product_data.get('category', '') or ''
        swahili_aliases = product_data.get('swahili_aliases', [])
        sheng_aliases = product_data.get('sheng_aliases', [])

        # Combine all text
        text_parts = [name, brand, category]
        text_parts.extend(swahili_aliases)
        text_parts.extend(sheng_aliases)

        # Join and normalize
        combined_text = ' '.join(filter(None, text_parts))
        normalized_result = self.normalize_text(combined_text)

        return normalized_result.normalized

    def normalize_query(self, query: str) -> NormalizedText:
        """
        Normalize a user query.

        Args:
            query: User query string

        Returns:
            NormalizedText object
        """
        return self.normalize_text(query)

# Convenience functions
def normalize_text(text: str, synonym_dict_path: Optional[str] = None,
                    abbreviation_dict_path: Optional[str] = None) -> NormalizedText:
    """
    Convenience function to normalize text.

    Args:
        text: Input text to normalize
        synonym_dict_path: Optional path to synonym dictionary
        abbreviation_dict_path: Optional path to abbreviation dictionary

    Returns:
        NormalizedText object
    """
    normalizer = TextNormalizer(synonym_dict_path, abbreviation_dict_path)
    return normalizer.normalize_text(text)

def normalize_product_for_indexing(product_data: Dict[str, Any],
                                 synonym_dict_path: Optional[str] = None,
                                 abbreviation_dict_path: Optional[str] = None) -> str:
    """
    Convenience function to normalize product data for indexing.

    Args:
        product_data: Product document from MongoDB
        synonym_dict_path: Optional path to synonym dictionary
        abbreviation_dict_path: Optional path to abbreviation dictionary

    Returns:
        Normalized text suitable for embedding generation
    """
    normalizer = TextNormalizer(synonym_dict_path, abbreviation_dict_path)
    return normalizer.normalize_product_for_indexing(product_data)

def normalize_query(query: str, synonym_dict_path: Optional[str] = None,
                     abbreviation_dict_path: Optional[str] = None) -> NormalizedText:
    """
    Convenience function to normalize a user query.

    Args:
        query: User query string
        synonym_dict_path: Optional path to synonym dictionary
        abbreviation_dict_path: Optional path to abbreviation dictionary

    Returns:
        NormalizedText object
    """
    normalizer = TextNormalizer(synonym_dict_path, abbreviation_dict_path)
    return normalizer.normalize_text(query)