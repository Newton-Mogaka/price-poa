"""
scanning.router
~~~~~~~~~~~~~~~
Route decoded barcode/QR payloads to the appropriate product lookup.

Returns a dict with keys:
    - status: one of "decode_failed", "unrecognized_code", "product_not_found", "success"
    - product: product document (only present when status is "success")
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from api.query_engine import find_product

logger = logging.getLogger(__name__)


def _is_product_sku_pattern(payload: str) -> bool:
    """
    Check if payload looks like a product SKU (e.g., GTIN).
    Heuristic: all digits, length between 8 and 14 inclusive.
    """
    return payload.isdigit() and 8 <= len(payload) <= 14


def _extract_gtin_from_gs1_digital_link(uri: str) -> Optional[str]:
    """
    Attempt to extract a GTIN from a GS1 Digital Link URI.
    Supports URI syntax like: https://id.gs1.org/01/09501101530013
    Returns the GTIN string if found and valid, else None.
    """
    if not uri.startswith("https://id.gs1.org/"):
        return None
    try:
        # Remove prefix and split by '/'
        rest = uri[len("https://id.gs1.org/"):]
        parts = rest.split('/')
        # Look for GS1 Application Identifier "01" (GTIN)
        for i, part in enumerate(parts):
            if part == "01" and i + 1 < len(parts):
                gtin_candidate = parts[i + 1]
                # GTIN should be all digits and one of the valid lengths
                if gtin_candidate.isdigit() and len(gtin_candidate) in (8, 12, 13, 14):
                    return gtin_candidate
        # If not found in AID format, maybe it's just the GTIN after the domain?
        # Some Digital Links might be: https://id.gs1.org/09501101530013
        # We'll check if the first part is a valid GTIN.
        if parts and parts[0].isdigit() and len(parts[0]) in (8, 12, 13, 14):
            return parts[0]
    except Exception:  # pragma: no cover - defensive
        logger.warning("Failed to parse GS1 Digital Link URI: %s", uri)
    return None


async def route_to_product(
    decoder_result: Dict[str, Optional[str]],
    db: AsyncIOMotorDatabase,
) -> Dict[str, Optional[object]]:
    """
    Route a decoded barcode/QR result to the product lookup function.

    Args:
        decoder_result: Output from api.scanning.decoder.decode_image
        db: MongoDB database connection

    Returns:
        A dictionary with status and optionally a product document.
    """
    symbology = decoder_result.get("symbology")
    payload = decoder_result.get("payload")

    # Case 1: Nothing decoded
    if symbology is None or payload is None:
        logger.info("Decoder returned no symbology or payload")
        return {"status": "decode_failed"}

    logger.info("Decoded %s: %s", symbology, payload)

    # Case 2: EAN13 or UPCA -> treat as product SKU
    if symbology in ("EAN13", "UPCA"):
        sku = payload
        product = await find_product(db, sku)
        if product is not None:
            logger.info("Found product for %s symbology: %s", symbology, sku)
            return {"status": "success", "product": product}
        else:
            logger.info("No product found for %s symbology: %s", symbology, sku)
            return {"status": "product_not_found"}

    # Case 3: QR -> check if it matches product SKU pattern or GS1 Digital Link
    if symbology == "QR":
        # First, check if it looks like a plain product SKU (all digits, reasonable length)
        if _is_product_sku_pattern(payload):
            sku = payload
            product = await find_product(db, sku)
            if product is not None:
                logger.info("Found product for QR (as SKU): %s", sku)
                return {"status": "success", "product": product}
            else:
                logger.info("No product found for QR (as SKU): %s", sku)
                return {"status": "product_not_found"}

        # Second, check if it looks like a GS1 Digital Link URI
        gtin = _extract_gtin_from_gs1_digital_link(payload)
        if gtin is not None:
            product = await find_product(db, gtin)
            if product is not None:
                logger.info("Found product for QR (GS1 Digital Link): %s -> GTIN %s", payload, gtin)
                return {"status": "success", "product": product}
            else:
                logger.info("No product found for QR (GS1 Digital Link): %s -> GTIN %s", payload, gtin)
                return {"status": "product_not_found"}

        # If neither, it's an unrecognized QR payload
        logger.info("QR payload does not match product SKU pattern or GS1 Digital Link: %s", payload)
        return {"status": "unrecognized_code"}

    # Should not happen given decoder only returns EAN13, UPCA, QR, or None
    logger.warning("Unexpected symbology from decoder: %s", symbology)
    return {"status": "decode_failed"}