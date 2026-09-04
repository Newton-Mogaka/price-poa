"""
Tests for the scanning.points module.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from scanning.points import award_scan_points


@pytest.mark.asyncio
async def test_award_scan_points_barcode():
    """Test awarding points for a barcode scan."""
    user_id = 12345
    action = "barcode_scan"
    product_id = "product123"

    # Mock the database
    db = AsyncMock()
    db.points_ledger.insert_one = AsyncMock()

    # Patch get_database to return our mock
    from database.connection import get_database
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("database.connection.get_database", AsyncMock(return_value=db))
        await award_scan_points(user_id, action, product_id)

    # Verify the insert was called with correct data
    db.points_ledger.insert_one.assert_called_once()
    call_args = db.points_ledger.insert_one.call_args[0][0]
    assert call_args["user_id"] == user_id
    assert call_args["action"] == action
    assert call_args["product_id"] == product_id
    assert call_args["points"] == 1
    # Check that timestamp is recent (within last 5 seconds)
    assert (datetime.now(timezone.utc) - call_args["timestamp"]).total_seconds() < 5


@pytest.mark.asyncio
async def test_award_scan_points_qr():
    """Test awarding points for a QR scan."""
    user_id = 12345
    action = "qr_scan"
    product_id = "product456"

    # Mock the database
    db = AsyncMock()
    db.points_ledger.insert_one = AsyncMock()

    # Patch get_database to return our mock
    from database.connection import get_database
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("database.connection.get_database", AsyncMock(return_value=db))
        await award_scan_points(user_id, action, product_id)

    # Verify the insert was called with correct data
    db.points_ledger.insert_one.assert_called_once()
    call_args = db.points_ledger.insert_one.call_args[0][0]
    assert call_args["user_id"] == user_id
    assert call_args["action"] == action
    assert call_args["product_id"] == product_id
    assert call_args["points"] == 1
    # Check that timestamp is recent (within last 5 seconds)
    assert (datetime.now(timezone.utc) - call_args["timestamp"]).total_seconds() < 5


@pytest.mark.asyncio
async def test_award_scan_points_invalid_action():
    """Test that invalid action is logged and returns early."""
    user_id = 12345
    action = "invalid_action"
    product_id = "product123"

    # Mock the database
    db = AsyncMock()
    db.points_ledger.insert_one = AsyncMock()

    # Patch get_database to return our mock
    from database.connection import get_database
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("database.connection.get_database", AsyncMock(return_value=db))
        await award_scan_points(user_id, action, product_id)

    # Verify the insert was NOT called
    db.points_ledger.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_award_scan_points_database_error():
    """Test that database errors are logged but don't crash."""
    user_id = 12345
    action = "barcode_scan"
    product_id = "product123"

    # Mock the database to raise an exception
    db = AsyncMock()
    db.points_ledger.insert_one = AsyncMock(side_effect=Exception("DB error"))

    # Patch get_database to return our mock
    from database.connection import get_database
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("database.connection.get_database", AsyncMock(return_value=db))
        # This should not raise an exception
        await award_scan_points(user_id, action, product_id)

    # Verify the insert was attempted
    db.points_ledger.insert_one.assert_called_once()


if __name__ == "__main__":
    # Run the tests if this script is executed directly
    pytest.main([__file__, "-v"])