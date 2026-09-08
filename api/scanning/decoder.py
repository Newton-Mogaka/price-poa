"""
scanning.decoder
~~~~~~~~~~~~~~~~
Decode barcodes and QR codes from an image using pyzbar (with zxing-cpp fallback).

Returns a dict: {"symbology": str | None, "payload": str | None}
where symbology is one of "EAN13", "UPCA", "QR", or None if nothing decoded.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional
import io

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

# Fallback to zxing-cpp if pyzbar not available or fails
try:
    import zxingcpp
    ZXING_CPP_AVAILABLE = True
except ImportError:  # pragma: no cover
    zxingcpp = None  # type: ignore
    ZXING_CPP_AVAILABLE = False


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
        return None)
        return None

    return {"symbology": symbology, "payload": payload}


def _decode_with_zxing_cpp(image_bytes: bytes) -> Optional[Dict[str, Optional[str]]]:
    """Attempt to decode using zxing-cpp as a fallback."""
    if not ZXING_CPP_AVAILABLE:
        return None

    try:
        # Convert bytes to PIL Image then to numpy array (RGB)
        from PIL import Image
        import numpy as np

        image = Image.open(io.BytesIO(image_bytes))
        # Ensure we have RGB (or grayscale) array
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_array = np.array(image)

        # zxing-cpp expects a numpy array (H, W, 3) uint8 RGB
        barcodes = zxingcpp.read_barcodes(img_array)

        if not barcodes:
            return None

        # Take the first barcode
        barcode = barcodes[0]
        raw = barcode.text
        if raw is None:
            return None

        # Get symbology from barcode.format (enum)
        fmt = barcode.format
        # The format attribute is an enum; we can get its name
        # Example: fmt.name -> 'EAN_13', 'UPC_A', 'QR_CODE'
        symbology = getattr(fmt, "name", None)
        if symbology is None:
            # fallback to string representation
            symbology = str(fmt).split(".")[-1] if "." in str(fmt) else str(fmt)

        # Normalize symbology names.
        if symbology in ("EAN_13", "EAN13"):
            symbology = "EAN13"
        elif symbology in ("UPC_A", "UPCA"):
            symbology = "UPCA"
        elif symbology == "QR_CODE":
            symbology = "QR"
        else:
            logger.info("zxing-cpp decoded unsupported symbology: %s", symbology)
            return None

        payload = raw
        return {"symbology": symbology, "payload": payload}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("zxing-cpp failed to decode image: %s", exc)
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

    # Fall back to zxing-cpp
    result = _decode_with_zxing_cpp(image_bytes)
    if result is not None:
        return result

    # Nothing decoded
    return {"symbology": None, "payload": None}