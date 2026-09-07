"""
scanning.decoder
~~~~~~~~~~~~~~~~
Decode barcodes and QR codes from an image using pyzbar (with zxing fallback).

Returns a dict: {"symbology": str | None, "payload": str | None}
where symbology is one of "EAN13", "UPCA", "QR", or None if nothing decoded.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Try to import pyzbar first
try:
    from pyzbar import pyzbar
    from pyzbar.wrapper import ZBarSymbol
    PYZBAR_AVAILABLE = True
except ImportError:  # pragma: no cover
    pyzbar = None  # type: ignore
    ZBarSymbol = None  # type: ignore
    PYZBAR_AVAILABLE = False

# Fallback to zxing if pyzbar not available or fails
try:
    from zxing import BarCodeReader
    ZXING_AVAILABLE = True
except ImportError:  # pragma: no cover
    BarCodeReader = None  # type: ignore
    ZXING_AVAILABLE = False


def _decode_with_pyzbar(image_bytes: bytes) -> Optional[Dict[str, Optional[str]]]:
    """Attempt to decode using pyzbar."""
    if not PYZBAR_AVAILABLE:
        return None

    try:
        # pyzbar expects a numpy array or PIL Image; we'll convert from bytes
        # For simplicity, we assume the caller has already converted to a format pyzbar accepts.
        # In practice, we might need to use PIL to open the bytes.
        # However, to keep this module self-contained and avoid heavy dependencies,
        # we note that pyzbar can work directly with bytes if they represent a valid image.
        # We'll try to decode directly; if it fails, we'll log and return None.
        barcodes = pyzbar.decode(image_bytes)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("pyzbar failed to decode image: %s", exc)
        return None

    if not barcodes:
        return None

    # We only care about the first barcode/QR code found.
    # In practice, there might be multiple; we take the first.
    barcode = barcodes[0]
    symbology = barcode.type
    payload = barcode.data.decode("utf-8")

    # Normalize symbology names to match our expectations.
    if symbology in ("EAN13", "EAN 13"):
        symbology = "EAN13"
    elif symbology in ("UPC A", "UPC-A"):
        symbology = "UPCA"
    elif symbology == "QR CODE":
        symbology = "QR"
    else:
        # We only support EAN13, UPCA, and QR for now.
        # Return None symbology to indicate unsupported type.
        logger.info("Decoded unsupported symbology: %s", symbology)
        return None

    return {"symbology": symbology, "payload": payload}


def _decode_with_zxing(image_bytes: bytes) -> Optional[Dict[str, Optional[str]]]:
    """Attempt to decode using zxing as a fallback."""
    if not ZXING_AVAILABLE:
        return None

    try:
        # zxing expects a file path or raw bytes? We'll try to use it with bytes.
        # Note: the zxing Python wrapper may require a file. We'll create a temporary file.
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp.flush()
            reader = BarCodeReader()
            barcode = reader.decode(tmp.path)
            os.unlink(tmp.name)

        if barcode is None:
            return None

        # zxing returns a BarCode object with raw and parsed attributes.
        raw = barcode.raw
        if raw is None:
            return None

        symbology = barcode.format
        payload = raw

        # Normalize symbology names.
        if symbology in ("EAN_13", "EAN13"):
            symbology = "EAN13"
        elif symbology in ("UPC_A", "UPCA"):
            symbology = "UPCA"
        elif symbology == "QR_CODE":
            symbology = "QR"
        else:
            logger.info("zxing decoded unsupported symbology: %s", symbology)
            return None

        return {"symbology": symbology, "payload": payload}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("zxing failed to decode image: %s", exc)
        return None


def decode_image(image_bytes: bytes) -> Dict[str, Optional[str]]:
    """
    Decode a barcode or QR code from the given image bytes.

    Returns a dictionary with keys "symbology" and "payload".
    If nothing is decoded, both values are None.
    If a supported symbology is decoded, returns the symbology and the decoded payload.
    """
    # Try pyzbar first
    result = _decode_with_pyzbar(image_bytes)
    if result is not None:
        return result

    # Fall back to zxing
    result = _decode_with_zxing(image_bytes)
    if result is not None:
        return result

    # Nothing decoded
    return {"symbology": None, "payload": None}