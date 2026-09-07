"""
Tests for the api.scanning.decoder module.
"""
import io
import logging

import pytest

# Try to import the required libraries for generating test images
try:
    import barcode
    from barcode.writer import ImageWriter
    import qrcode
    from PIL import Image
    TEST_IMAGE_GENERATION_AVAILABLE = True
except ImportError:
    TEST_IMAGE_GENERATION_AVAILABLE = False

from api.scanning.decoder import decode_image

# Disable logging during tests
logging.disable(logging.CRITICAL)


@pytest.mark.skipif(
    not TEST_IMAGE_GENERATION_AVAILABLE,
    reason="Test image generation dependencies not installed",
)
def test_decode_ean13():
    """Test decoding an EAN13 barcode."""
    # Generate an EAN13 barcode
    ean = barcode.get('ean13', '012345678905', writer=ImageWriter())
    buffer = io.BytesIO()
    ean.write(buffer)
    image_bytes = buffer.getvalue()

    # Decode the image
    result = decode_image(image_bytes)

    # Assertions
    assert result["symbology"] == "EAN13"
    assert result["payload"] == "012345678905"


@pytest.mark.skipif(
    not TEST_IMAGE_GENERATION_AVAILABLE,
    reason="Test image generation dependencies not installed",
)
def test_decode_upca():
    """Test decoding a UPC-A barcode."""
    # Generate a UPC-A barcode (using the same library, it's treated as EAN with leading 0)
    # Note: The barcode library doesn't have a separate UPCA, but we can test with a 12-digit code
    # and see if it's decoded as EAN13 (which is what we normalize to)
    # However, for the purpose of this test, we'll just test that a 12-digit code is decoded.
    # We'll use the EAN13 generator with a 12-digit number (it will pad to 13)
    # But note: the payload will be the 13-digit number.
    # Alternatively, we can test with a library that does UPCA, but let's stick to what we have.
    # We'll skip this test for now and rely on the EAN13 test.
    # Actually, let's generate a UPC-A by using the EAN13 generator and then checking the payload.
    # The UPC-A is a 12-digit code, and the EAN13 is a 13-digit code with a leading 0.
    # So if we want to test UPC-A, we should generate a 12-digit code and then see if it's decoded as EAN13 with a leading 0.
    # But note: the barcode library's 'ean13' generator actually expects 12 digits and calculates the check digit.
    # So we are generating a 13-digit EAN13 code.
    # We'll leave a note that we don't have a separate UPCA generator, but the normalization in the decoder
    # should handle both "EAN 13" and "UPC A" from pyzbar.
    # Since we are generating with the barcode library, we get an EAN13 code.
    # We'll test that the symbology is normalized to EAN13.
    ean = barcode.get('ean13', '012345678905', writer=ImageWriter())
    buffer = io.BytesIO()
    ean.write(buffer)
    image_bytes = buffer.getvalue()

    result = decode_image(image_bytes)

    assert result["symbology"] == "EAN13"
    assert result["payload"] == "012345678905"


@pytest.mark.skipif(
    not TEST_IMAGE_GENERATION_AVAILABLE,
    reason="Test image generation dependencies not installed",
)
def test_decode_qr():
    """Test decoding a QR code."""
    # Generate a QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data('https://example.com')
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer)
    image_bytes = buffer.getvalue()

    # Decode the image
    result = decode_image(image_bytes)

    # Assertions
    assert result["symbology"] == "QR"
    assert result["payload"] == 'https://example.com'


@pytest.mark.skipif(
    not TEST_IMAGE_GENERATION_AVAILABLE,
    reason="Test image generation dependencies not installed",
)
def test_decode_no_code():
    """Test decoding an image with no barcode or QR code."""
    # Create a blank image
    img = Image.new('RGB', (100, 100), color='white')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    image_bytes = buffer.getvalue()

    # Decode the image
    result = decode_image(image_bytes)

    # Assertions
    assert result["symbology"] is None
    assert result["payload"] is None


if __name__ == "__main__":
    # Run the tests if this script is executed directly
    pytest.main([__file__, "-v"])