"""
Tests for the scanning.router module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from scanning.router import (
    _extract_gtin_from_gs1_digital_link,
    _is_product_sku_pattern,
    route_to_product,
)


def test_is_product_sku_pattern():
    """Test the product SKU pattern detection."""
    # Valid SKU patterns (8-14 digits)
    assert _is_product_sku_pattern("12345678") is True  # 8 digits
    assert _is_product_sku_pattern("12345678901234") is True  # 14 digits
    assert _is_product_sku_pattern("012345678905") is True  # EAN13

    # Invalid patterns
    assert _is_product_sku_pattern("1234567") is False  # 7 digits
    assert _is_product_sku_pattern("123456789012345") is False  # 15 digits
    assert _is_product_sku_pattern("123abc456") is False  # contains letters
    assert _is_product_sku_pattern("") is False  # empty string


def test_extract_gtin_from_gs1_digital_link():
    """Test GS1 Digital Link URI parsing."""
    # Valid GS1 Digital Link URIs
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/09501101530013") == "09501101530013"
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/09501101530013/10/ABC123") == "09501101530013"
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/09501101530013?21=123") == "09501101530013"

    # Alternative format (GTIN directly after domain)
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/09501101530013") == "09501101530013"

    # Invalid URIs
    assert _extract_gtin_from_gs1_digital_link("https://example.com/01/09501101530013") is None
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/02/09501101530013") is None  # wrong AI
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/0950110153001") is None  # too short
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/095011015300130") is None  # too long
    assert _extract_gtin_from_gs1_digital_link("https://id.gs1.org/01/0950110153001a") is None  # non-digit
    assert _extract_gtin_from_gs1_digital_link("not a uri") is None
    assert _extract_gtin_from_gs1_digital_link("") is None


@pytest.mark.asyncio
async def test_route_to_product_decode_failed():
    """Test routing when nothing is decoded."""
    decoder_result = {"symbology": None, "payload": None}
    db = AsyncMock()

    result = await route_to_product(decoder_result, db)

    assert result["status"] == "decode_failed"
    assert "product" not in result


@pytest.mark.asyncio
async def test_route_to_product_ean13_success():
    """Test successful routing of EAN13 barcode to product."""
    decoder_result = {"symbology": "EAN13", "payload": "012345678905"}
    db = AsyncMock()

    # Mock the find_product function to return a product
    mock_product = {"_id": "product123", "name": "Test Product"}
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=mock_product))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "success"
    assert result["product"] == mock_product


@pytest.mark.asyncio
async def test_route_to_product_ean13_not_found():
    """Test routing when EAN13 barcode doesn't match a product."""
    decoder_result = {"symbology": "EAN13", "payload": "012345678905"}
    db = AsyncMock()

    # Mock the find_product function to return None
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=None))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "product_not_found"
    assert "product" not in result


@pytest.mark.asyncio
async def test_route_to_product_upca_success():
    """Test successful routing of UPC-A barcode to product."""
    decoder_result = {"symbology": "UPCA", "payload": "012345678905"}
    db = AsyncMock()

    # Mock the find_product function to return a product
    mock_product = {"_id": "product123", "name": "Test Product"}
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=mock_product))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "success"
    assert result["product"] == mock_product


@pytest.mark.asyncio
async def test_route_to_product_qr_as_sku_success():
    """Test successful routing of QR code that looks like a product SKU."""
    decoder_result = {"symbology": "QR", "payload": "012345678905"}  # 12 digits
    db = AsyncMock()

    # Mock the find_product function to return a product
    mock_product = {"_id": "product123", "name": "Test Product"}
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=mock_product))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "success"
    assert result["product"] == mock_product


@pytest.mark.asyncio
async def test_route_to_product_qr_as_sku_not_found():
    """Test routing when QR code looks like SKU but doesn't match a product."""
    decoder_result = {"symbology": "QR", "payload": "012345678905"}  # 12 digits
    db = AsyncMock()

    # Mock the find_product function to return None
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=None))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "product_not_found"
    assert "product" not in result


@pytest.mark.asyncio
async def test_route_to_product_qr_gs1_digital_link_success():
    """Test successful routing of QR code that is a GS1 Digital Link."""
    decoder_result = {"symbology": "QR", "payload": "https://id.gs1.org/01/09501101530013"}
    db = AsyncMock()

    # Mock the find_product function to return a product
    mock_product = {"_id": "product123", "name": "Test Product"}
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=mock_product))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "success"
    assert result["product"] == mock_product


@pytest.mark.asyncio
async def test_route_to_product_qr_gs1_digital_link_not_found():
    """Test routing when QR code is GS1 Digital Link but doesn't match a product."""
    decoder_result = {"symbology": "QR", "payload": "https://id.gs1.org/01/09501101530013"}
    db = AsyncMock()

    # Mock the find_product function to return None
    from api.query_engine import find_product
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("api.query_engine.find_product", AsyncMock(return_value=None))
        result = await route_to_product(decoder_result, db)

    assert result["status"] == "product_not_found"
    assert "product" not in result


@pytest.mark.asyncio
async def test_route_to_product_qr_unrecognized():
    """Test routing when QR code is not recognized as product SKU or GS1 Digital Link."""
    decoder_result = {"symbology": "QR", "payload": "Hello World"}
    db = AsyncMock()

    result = await route_to_product(decoder_result, db)

    assert result["status"] == "unrecognized_code"
    assert "product" not in result


@pytest.mark.asyncio
async def test_route_to_product_unsupported_symbology():
    """Test routing when decoder returns unsupported symbology."""
    decoder_result = {"symbology": "CODE128", "payload": "some data"}
    db = AsyncMock()

    result = await route_to_product(decoder_result, db)

    assert result["status"] == "decode_failed"
    assert "product" not in result


if __name__ == "__main__":
    # Run the tests if this script is executed directly
    pytest.main([__file__, "-v"])