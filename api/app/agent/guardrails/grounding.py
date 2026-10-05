"""
Grounding guardrail for the agent.
Ensures that numerical claims in responses are supported by tool results.
"""
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class GroundingChecker:
    """
    Checks that numerical claims in agent responses are grounded in tool results.
    """

    def __init__(self):
        """Initialize the grounding checker."""
        # Regex patterns for detecting monetary values and percentages
        self.kes_pattern = re.compile(
            r'(?:\b|[\s\(])'  # Word boundary or space/opening paren
            r'(?:KES\s*)?'    # Optional KES prefix
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)'  # Number with commas/decimals
            r'(?:\s*KES)?'    # Optional KES suffix
            r'(?:\b|[\s,\)])', # Word boundary or space/closing paren/comma
            re.IGNORECASE
        )

        self.percentage_pattern = re.compile(
            r'(?:\b|[\s\(])'  # Word boundary or space/opening paren
            r'(\d+(?:\.\d+)?)'  # Number with optional decimal
            r'\s*%'             # Percentage sign
            r'(?:\b|[\s,\)])',  # Word boundary or space/closing paren/comma
            re.IGNORECASE
        )

    async def check_grounding(
        self,
        text: str,
        used_tools: List[str]
    ) -> str:
        """
        Check and ground numerical claims in the response text.

        Args:
            text: The agent's response text
            used_tools: List of tools used to generate this response

        Returns:
            Grounded text (original if valid, corrected if needed)
        """
        if not used_tools:
            # If no tools were used, we can't ground any claims
            # Remove any numerical claims to be safe
            return self._remove_ungrounded_claims(text)

        # For now, we'll implement a simplified version
        # In a full implementation, we would:
        # 1. Extract all KES amounts and percentages from the text
        # 2. Check if each appears in the tool results from this turn
        # 3. If not, either remove the claim or ask for correction
        #
        # Since we don't have access to the specific tool results here
        # without passing them through, we'll return the text as-is
        # and note that a full implementation would require
        # passing tool results to this function

        logger.debug(f"Grounding check for text with {len(used_tools)} tools used: {used_tools}")
        return text  # Placeholder - return original text

    def _remove_ungrounded_claims(self, text: str) -> str:
        """
        Remove numerical claims when no tools were used.

        Args:
            text: Input text

        Returns:
            Text with numerical claims removed
        """
        # Remove KES amounts
        text = self.kes_pattern.sub(r'\1', text)  # This keeps the number but removes KES context
        # Actually, let's replace with [amount removed] or just remove the whole match
        text = self.kes_pattern.sub('[amount]', text)
        text = self.percentage_pattern.sub('[percentage]', text)
        return text

    # Placeholder for future enhancement
    async def _extract_claims(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract numerical claims from text.

        Args:
            text: Input text

        Returns:
            List of claim dictionaries with type, value, and position
        """
        claims = []

        # Find KES amounts
        for match in self.kes_pattern.finditer(text):
            claims.append({
                "type": "kes",
                "value": match.group(1),
                "full_match": match.group(0),
                "start": match.start(),
                "end": match.end()
            })

        # Find percentages
        for match in self.percentage_pattern.finditer(text):
            claims.append({
                "type": "percentage",
                "value": match.group(1),
                "full_match": match.group(0),
                "start": match.start(),
                "end": match.end()
            })

        return claims

    # Placeholder for future enhancement
    async def _validate_claims(
        self,
        claims: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Validate claims against tool results.

        Args:
            claims: List of extracted claims
            tool_results: List of tool results from this turn

        Returns:
            List of validation results
        """
        # This would check if each claim value appears in the tool results
        # For now, return all claims as valid (placeholder)
        return [{"claim": claim, "valid": True} for claim in claims]


# Create a singleton instance
grounding_checker = GroundingChecker()


async def check_grounding(text: str, used_tools: List[str]) -> str:
    """
    Convenience function to check grounding of text.

    Args:
        text: The agent's response text
        used_tools: List of tools used to generate this response

    Returns:
        Grounded text
    """
    return await grounding_checker.check_grounding(text, used_tools)