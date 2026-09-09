#!/usr/bin/env python3
"""
Seed script to populate all discovered Quickmart branches into MongoDB db.stores.

Can be run inside the scraper container:
    docker compose exec scraper python scraper/seed_quickmart_stores.py
"""
import os
import sys
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pymongo import MongoClient, UpdateOne
from scraper.config.quickmart_branches import (
    QUICKMART_BRANCH_PRESETS,
    DISCOVERED_BRANCHES
)

MONGO_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://pricepoa_dev:pricepoa_dev_password@mongo:27017/pricepoa?authSource=admin"
)
DB_NAME = os.getenv("MONGODB_DB", "pricepoa")


def seed_stores():
    print(f"Connecting to MongoDB at {MONGO_URI.split('@')[-1]}...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    operations = []
    now = datetime.now(timezone.utc)

    # 1. First add all preset branches (high-quality coordinates and addresses)
    seen_branches = set()
    for preset_key, preset in QUICKMART_BRANCH_PRESETS.items():
        branch_name = preset.get("branch_name")
        seen_branches.add(branch_name.lower())
        
        doc_set = {
            "chain": "Quickmart",
            "branch": branch_name,
            "town": preset.get("town", "Nairobi"),
            "county": preset.get("county", "Nairobi"),
            "gps_latitude": preset.get("gps_latitude"),
            "gps_longitude": preset.get("gps_longitude"),
            "address": preset.get("address"),
            "is_active": True,
            "updated_at": now
        }
        operations.append(
            UpdateOne(
                {"chain": "Quickmart", "branch": branch_name},
                {
                    "$set": doc_set,
                    "$setOnInsert": {"created_at": now}
                },
                upsert=True
            )
        )

    # 2. Add remaining discovered branches from JSON
    for discovered in DISCOVERED_BRANCHES:
        name = discovered.get("name", "").strip()
        if not name or name.lower() in seen_branches:
            continue
        seen_branches.add(name.lower())
        
        tags = discovered.get("location_tags", [])
        town = tags[0] if tags else "Nairobi"
        county = tags[0] if tags else "Nairobi"
        address = f"{name}, {town}, Kenya"
        
        doc_set = {
            "chain": "Quickmart",
            "branch": name,
            "town": town,
            "county": county,
            "gps_latitude": None,
            "gps_longitude": None,
            "address": address,
            "is_active": True,
            "updated_at": now
        }
        operations.append(
            UpdateOne(
                {"chain": "Quickmart", "branch": name},
                {
                    "$set": doc_set,
                    "$setOnInsert": {"created_at": now}
                },
                upsert=True
            )
        )

    if operations:
        res = db.stores.bulk_write(operations)
        print(f"Successfully processed {len(operations)} Quickmart branches:")
        print(f" - Upserted (newly inserted): {len(res.upserted_ids)}")
        print(f" - Matched (already existed): {res.matched_count}")
        print(f" - Modified: {res.modified_count}")
    else:
        print("No branch records to seed.")

    total_quickmart = db.stores.count_documents({"chain": "Quickmart"})
    total_stores = db.stores.count_documents({})
    print(f"\nTotal stores in db.stores: {total_stores} (Quickmart branches: {total_quickmart})")


if __name__ == "__main__":
    seed_stores()
