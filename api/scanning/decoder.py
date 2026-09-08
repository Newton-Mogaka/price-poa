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
from PIL import Image
import numpy as np

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


def _preprocess_image_variants(image: Image.Image):
    """Yield a sequence of PIL Image variants to try for barcode detection."""
    # Original
    yield image.convert("RGB")
    # Grayscale
    yield image.convert("L")
    # Inverted RGB
    rgb = image.convert("RGB")
    inv_rgb_array = 255 - np.array(rgb)
    yield Image.fromarray(inv_rgb_array.astype('uint8'))
    # Inverted grayscale
    gray = image.convert("L")
    inv_gray_array = 255 - np.array(gray)
    yield Image.fromarray(inv_gray_array.astype('uint8'))
    # Upscaled 2x (RGB)
    w, h = image.size
    yield image.resize((w * 2, h * 2), Image.BILINEAR).convert("RGB")
    # Upscaled 2x grayscale
    yield image.resize((w * 2, h * 2), Image.BILINEAR).convert("L")


def _decode_with_pyzbar(image_bytes: bytes) -> Optional[Dict[str, Optional[str]]]:
    """Attempt to decode using pyzbar with multiple preprocessing variants."""
    if not PYZBAR_AVAILABLE:
        logger.info("pyzbar not available")
        return None

    try:
        pil_image = Image.open(io.BytesIO(image_bytes))
        logger.info("pyzbar input image: mode=%s, size=%s", pil_image.mode, pil_image.size)
    except Exception as exc:
        logger.warning("Failed to open image for pyzbar: %s", exc)
        return None

    for idx, variant in enumerate(_preprocess_image_variants(pil_image)):
        try:
            # pyzbar works directly on PIL Image
            barcodes = pyzbar.decode(variant)
            logger.info("pyzbar variant %d: raw barcodes: %s", idx, barcodes)
            if barcodes:
                barcode = barcodes[0]
                symbology = barcode.type
                payload = barcode.data.decode("utf-8")
                logger.info("pyzbar variant %d decoded: symbology=%s, payload=%s", idx, symbology, payload)
                # Normalize symbology names
                if symbology in ("EAN13", "EAN 13"):
                    symbology = "EAN13"
                elif symbology in ("UPC A", "UPC-A"):
                    symbology = "UPCA"
                elif symbology == "QR CODE":
                    symbology = "QR"
                else:
                    logger.info("pyzbar decoded unsupported symbology: %s", symbology)
                    continue
                return {"symbology": symbology, "payload": payload}
        except Exception as exc:
            logger.warning("pyzbar variant %d failed: %s", idx, exc)
            continue

    logger.info("pyzbar found no barcodes in any variant")
    return None


def _decode_with_zxing_cpp(image_bytes: bytes) -> Optional[Dict[str, Optional[str]]]:
    """Attempt to decode using zxing-cpp with multiple preprocessing variants."""
    if not ZXING_CPP_AVAILABLE:
        logger.info("zxing-cpp not available")
        return None

    try:
        pil_image = Image.open(io.BytesIO(image_bytes))
        logger.info("zxing-cpp input image: mode=%s, size=%s", pil_image.mode, pil_image.size)
    except Exception as exc:
        logger.warning("Failed to open image for zxing-cpp: %s", exc)
        return None

    for idx, variant in enumerate(_preprocess_image_variants(pil_image)):
        try:
            # Convert to numpy array as expected by zxing-cpp
            if variant.mode == "L":
                arr = np.array(variant)  # shape (H, W)
            else:
                arr = np.array(variant.convert("RGB"))  # ensure RGB
            logger.info("zxing-cpp variant %d: array shape=%s, dtype=%s", idx, arr.shape, arr.dtype)
            barcodes = zxingcpp.read_barcodes(arr)
            logger.info("zxing-cpp variant %d: raw barcodes result: %s", idx, barcodes)
            if barcodes:
                barcode = barcodes[0]
                raw = barcode.text
                logger.info("zxing-cpp variant %d barcode text: %s", idx, raw)
                if raw is None:
                    logger.info("zxing-cpp variant %d barcode text is None", idx)
                    continue
                # Get symbology from barcode.format (enum)
                fmt = barcode.format
                symbology = getattr(fmt, "name", None)
                if symbology is None:
                    symbology = str(fmt).split(".")[-1] if "." in str(fmt) else str(fmt)
                logger.info("zxing-cpp variant %d raw symbology: %s", idx, symbology)
                # Normalize symbology names.
                if symbology in ("EAN_13", "EAN13"):
                    symbology = "EAN13"
                elif symbology in ("UPC_A", "UPCA"):
                    symbology = "UPCA"
                elif symbology == "QR_CODE":
                    symbology = "QR"
                else:
                    logger.info("zxing-cpp variant %d decoded unsupported symbology: %s", idx, symbology)
                    continue
                payload = raw
                logger.info(
                    "zxing-cpp variant %d decoded barcode: symbology=%s, payload=%s", idx, symbology, payload
                )
                return {"symbology": symbology, "payload": payload}
        except Exception as exc:
            logger.warning("zxing-cpp variant %d failed: %s", idx, exc)
            continue

    logger.info("zxing-cpp found no barcodes in any variant")
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