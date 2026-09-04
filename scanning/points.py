"""
scanning.points
~~~~~~~~~~~~~~~
Award points for successful barcode/QR scans that resolve to a product.

Writes to the `points_ledger` collection in MongoDB.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from database.connection import get_database

logger = logging.getLogger(__name__)


async def award_scan_points(
    user_id: int,
    action: str,
    product_id: str,
) -> None:
    """
    Insert a points ledger document for a successful scan.

    Args:
        user_id: The Telegram user ID of the scanner.
        action: Either "barcode_scan" or "qr_scan".
        product_id: The MongoDB ObjectId string of the product that was matched.
    """
    if action not in ("barcode_scan", "qr_scan"):
        logger.error("Invalid action for points award: %s", action)
        return

    db: AsyncIOMotorDatabase = await get_database()
    ledger_entry = {
        "user_id": user_id,
        "action": action,
        "product_id": product_id,
        "points": 1,
        "timestamp": datetime.now(timezone.utc),
    }
    try:
        await db.points_ledger.insert_one(ledger_entry)
        logger.info(
            "Awarded %s point for %s (user %s, product %s)",
            ledger_entry["points"],
            action,
            user_id,
            product_id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Failed to insert points ledger entry: %s", exc)