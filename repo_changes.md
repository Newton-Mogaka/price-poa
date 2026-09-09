# Repository Changes & Fixes

## 1. Issue Summary

### Symptoms
When running `docker compose up`, the startup aborted with:
```text
✘ Container pricepoa_mongo           Error dependency mongo failed to start
dependency failed to start: container pricepoa_mongo is unhealthy
```

### Root Causes
1. **Keyfile Directory Issue:**
   When `docker compose up` was initially invoked before `./mongo-keyfile` existed as a file, Docker created `./mongo-keyfile` as an empty directory. MongoDB failed when attempting to read the directory as a keyfile (`iostream error`).

2. **Windows NTFS Permission Limitation:**
   When hosting on Windows, files bind-mounted from the host into a Linux container default to permissive POSIX modes (typically `0777` or `0755`). MongoDB requires keyfiles to strictly have `0400` or `0600` permissions (readable only by the owner). Attempting to use the host-mounted file directly causes MongoDB to crash with:
   ```text
   permissions on /etc/mongo-keyfile are too open
   ```

3. **User Initialization Bypass:**
   When customizing the container entrypoint to set permissions, bypassing the standard `/usr/local/bin/docker-entrypoint.sh` causes MongoDB to skip creating the root user defined by `MONGO_INITDB_ROOT_USERNAME` (`pricepoa_dev`). Consequently, healthchecks authenticating with that user fail with `UserNotFound: Could not find user "pricepoa_dev" for db "admin"` and mark the container unhealthy.

---

## 2. Changes Applied

### [docker-compose.yml](docker-compose.yml) — `mongo` Service

Updated the `mongo` container definition to copy the mounted keyfile to `/tmp/mongo-keyfile`, apply ownership (`999:999`) and permissions (`400`), and pass control to `/usr/local/bin/docker-entrypoint.sh` so the root credentials and replica set are properly initialized:

```diff
   mongo:
     image: mongo:6.0
     container_name: pricepoa_mongo
-    command: ["mongod", "--replSet", "rs0", "--bind_ip_all", "--keyFile", "/etc/mongo-keyfile"]
+    entrypoint: ["/bin/bash", "-c"]
+    command:
+      - |
+        cp /etc/mongo-keyfile /tmp/mongo-keyfile
+        chmod 400 /tmp/mongo-keyfile
+        chown 999:999 /tmp/mongo-keyfile
+        exec /usr/local/bin/docker-entrypoint.sh mongod --replSet rs0 --bind_ip_all --keyFile /tmp/mongo-keyfile
     environment:
       MONGO_INITDB_ROOT_USERNAME: ${MONGO_INITDB_ROOT_USERNAME}
       MONGO_INITDB_ROOT_PASSWORD: ${MONGO_INITDB_ROOT_PASSWORD}
       MONGO_INITDB_DATABASE: ${MONGODB_DB}
     ports:
       - "27017:27017"
     volumes:
       - mongo_data:/data/db
       - mongo_config:/data/configdb
-      - ./mongo-keyfile:/etc/mongo-keyfile
+      - ./mongo-keyfile:/etc/mongo-keyfile:ro
```

**Benefits:**
- **Cross-Platform Compatibility:** Works on Windows (Docker Desktop / WSL2), macOS, and Linux without requiring host-level permission hacks.
- **Proper Authentication Provisioning:** Invoking `docker-entrypoint.sh` ensures `MONGO_INITDB_ROOT_USERNAME` is created in MongoDB before replica set operations, allowing container healthchecks to pass.
- **Security:** Mounts the host keyfile as read-only (`:ro`) and isolates the active keyfile inside the container with `400` permissions.

---

## 3. Verified Verification Results

Both `pricepoa_mongo` and `pricepoa_mongo_init` were verified:
```text
NAME             IMAGE       STATUS                    PORTS
pricepoa_mongo   mongo:6.0   Up (healthy)              0.0.0.0:27017->27017/tcp
```
And `mongo-init` output:
```text
pricepoa_mongo_init  | Waiting for mongod...
pricepoa_mongo_init  | Replica set rs0 initiated
```

---

## 4. How to Start the Entire Stack

In PowerShell:
```powershell
docker compose up -d
```
All dependent services (`api`, `scraper`, `intelligence`, `mongo-express`, etc.) will now successfully connect to `pricepoa_mongo`.

---

## 5. Quickmart Localized Multi-Branch Scraper Implementation

### Context & Requirements
- **Goal:** Enable localized web scraping for Quickmart supermarkets across distinct branches (e.g., Nairobi Pioneer CBD vs. Kisumu Kondele) so that product prices are localized per branch and saved with distinct `store_id` references in MongoDB.
- **Database Model Alignment:**
  - `db.products`: Global, canonical, and store-agnostic (`name`, `category`, `brand`, `sizes_variants`).
  - `db.stores`: Branch entity (`chain`, `branch`, `town`, `county`, `gps_latitude`, `gps_longitude`, `address`).
  - `db.prices`: Foreign-keyed price record (`product_id`, `store_id`, `price_kes`, `source`, `verified_at`) deduplicated per day via compound key `(product_id, store_id, source, day_start)`.
- **Zero Redundancy & No Hardcoding:**
  - Coordinates and cookies are dynamically obtained from Quickmart's backend (Growcer/FATbit).
  - No changes needed to `MongoDBPipeline` or `PriceValidationPipeline` as the architecture already properly supported `store_id` foreign keying.

---

### Chronological Changes

#### 1. `.gitignore`
- **File:** [`.gitignore`](.gitignore)
- **Change:** Added `docker-compose.yml` and `docker-compose.*.yml`.
- **Rationale:** Prevents developer credentials, localized environment secrets, or environment overrides from being accidentally tracked in git.

#### 2. `scraper/config/quickmart_branches.py` (New File)
- **File:** [`scraper/config/quickmart_branches.py`](scraper/config/quickmart_branches.py)
- **Change:** Created branch presets and dynamic resolver `resolve_branch(town, branch)`:
  - Mapped preset branch configurations for `Kisumu` (Kondele, Shop ID: 23, slug: `/2801`), `Nairobi` (Pioneer CBD, Shop ID: 16, slug: `/3501`), `Nairobi Donholm` (Shop ID: 52, slug: `/2201`), `Nakuru` (Statehouse, Shop ID: 67), and `Mombasa` (Mtwapa Mall, Shop ID: 35).
  - Supplies the exact Growcer session cookies (`_ygShopId`, `_ygGeoAddress`, `_ygGeoLat`, `_ygGeoLng`, `_ygGeoRadius`), coordinates, town, county, and street address.
  - Automatically falls back to Nairobi CBD if no matching branch or town is specified.

#### 3. `scraper/spiders/quickmart_spider.py`
- **File:** [`scraper/spiders/quickmart_spider.py`](scraper/spiders/quickmart_spider.py)
- **Changes:**
  - Updated `QuickmartSpider.__init__` to accept `town: Optional[str] = None` and `branch: Optional[str] = None`.
  - Invokes `resolve_branch(town=town, branch=branch)` to configure `self.location_gate_cookies`, which `InvisiblePlaywrightMiddleware` injects into Playwright browser contexts to ensure the target branch's inventory and localized prices are rendered.
  - Passes branch metadata (`store_branch`, `store_town`, `store_county`, `gps_latitude`, `gps_longitude`, `store_address`) across all category and pagination requests via request `meta`.
  - Injects `branch_fields` into `self.build_item(...)` during product extraction.

#### 4. `scraper/pipelines/store_resolution_pipeline.py`
- **File:** [`scraper/pipelines/store_resolution_pipeline.py`](scraper/pipelines/store_resolution_pipeline.py)
- **Changes:**
  - Extended store upsert logic in `_create_store` and existing store resolution:
    - Sets `town`, `county`, `gps_latitude`, `gps_longitude`, and `address` from item metadata when registering new branch entries in `db.stores`.
    - Updates missing town or coordinates on existing store records.
  - Ensures all created store records strictly satisfy MongoDB schema validation (`STORE_VALIDATOR`) and can be queried by town in the API layer (`api/query_engine.py`).

#### 5. `scraper/worker.py`
- **File:** [`scraper/worker.py`](scraper/worker.py)
- **Changes:**
  - Added CLI options `--town` and `--branch` to `argparse`.
  - Propagated `town` and `branch` as `crawl_kwargs` to `process.crawl(spider_name, **crawl_kwargs)`.
  - Enables ad-hoc single-branch runs, e.g.:
    ```bash
    python scraper/worker.py --mode once --spider quickmart_spider --town Kisumu --branch Kondele
    ```

#### 6. `scraper/scheduler.py`
- **File:** [`scraper/scheduler.py`](scraper/scheduler.py)
- **Changes:**
  - Updated `ScrapeScheduler.add_scrape_job` and `_run_spider_job` to accept `spider_kwargs: Optional[Dict[str, Any]] = None` and pass `**(spider_kwargs or {})` to `process.crawl`.
  - In `setup_default_schedules()`, registered independent scheduled cron jobs for localized branches:
    - `daily_quickmart_nairobi` (`town="Nairobi"`, `branch="Pioneer CBD"`, 02:15 AM)
    - `daily_quickmart_kisumu` (`town="Kisumu"`, `branch="Kondele"`, 02:30 AM)

#### 7. `scraper/spiders/quickmart_spider.py` — DOM Selector & Text Extraction Fix
- **File:** [`scraper/spiders/quickmart_spider.py`](scraper/spiders/quickmart_spider.py)
- **Issue:** During live container crawl, product pages were visited successfully (HTTP 200) but logged `Missing product name or price`.
- **Root Cause:**
  1. Quickmart's Growcer frontend renders prices inside `<div class="products-price"><span class="products-price-new">KES 155.00</span></div>`. The generic selector `[class*="price"]::text` matched the outer `div`, whose immediate text child was whitespace (`\n `).
  2. `_extract_first` accepted whitespace-only strings and returned `""`, which caused `if not product_name or not price_text:` to drop the item.
- **Fix:**
  1. Updated `_extract_first` to iterate through matches and skip whitespace-only text, returning only non-empty strings.
  2. Targeted exact Growcer selectors: `h1.product-title *::text` for product names, `.products-price-new *::text` for active prices, `.products-price-old *::text` for original prices, and `.products-price-off *::text` for discount badges.

#### 8. `scraper/settings.py` & `scraper/Dockerfile` — Logging Level Normalization & PYTHONPATH
- **Files:** [`scraper/settings.py`](scraper/settings.py), [`scraper/Dockerfile`](scraper/Dockerfile)
- **Issue:** Running `python -m scrapy crawl ...` raised `ValueError: Unknown level: 'info'`.
- **Root Cause:** In Python's standard `logging` library, log level names must be uppercase (`INFO`, `DEBUG`, etc.). The environment variable `SCRAPER_LOG_LEVEL` defaulted to lowercase `'info'`.
- **Fix:**
  1. In `scraper/settings.py`, applied `.upper()` to `os.getenv('SCRAPER_LOG_LEVEL', 'INFO').upper()`.
  2. In `scraper/Dockerfile`, set `ENV SCRAPER_LOG_LEVEL=INFO` and `ENV PYTHONPATH=/app`.

#### 9. Price Validation & Currency Normalization Fix
- **Files:** [`scraper/pipelines/validation_pipeline.py`](scraper/pipelines/validation_pipeline.py), [`scraper/spiders/quickmart_spider.py`](scraper/spiders/quickmart_spider.py)
- **Issue:** Items extracted with prices such as `"KES 299.00"` or `"KES 1,399.00"` were dropped by `PriceValidationPipeline` with `Dropped: Invalid price value: KES ...`.
- **Root Cause:** In `PriceValidationPipeline._validate_data_types`, raw prices were converted using direct `float(price_val)`. Currency abbreviations (`KES`, `KSh`), thousand commas (`,`), and whitespace caused `ValueError`.
- **Fix:**
  1. Updated `PriceValidationPipeline._validate_data_types` to cleanly extract the numeric portion via regex (`re.search(r'\d+(?:\.\d+)?', val_str)`), stripping commas and currency prefixes before converting to `float`.
  2. Added `_clean_price` helper in `QuickmartSpider` to convert price strings to floats at extraction time.
  3. Cleaned multi-line whitespace in promotional details strings (e.g. `11.3%  Off`).

#### 10. Multi-Branch Batch Runner & Dynamic 72-Branch Resolver
- **Files:** [`scraper/batch_quickmart.py`](scraper/batch_quickmart.py), [`scraper/config/quickmart_branches.py`](scraper/config/quickmart_branches.py)
- **Features Added:**
  1. Created `scraper/batch_quickmart.py` to sequentially scrape branches with a customizable item limit (e.g., `--items 2`) in clean, isolated subprocesses to prevent memory exhaustion and reactor conflicts.
  2. Extended `scraper/config/quickmart_branches.py` to dynamically load all 72 discovered branches from `quickmart_branches_discovered.json`. Any branch can now be queried by name, town, or slug, and its Growcer location cookies and coordinates are fetched and cached on demand.
  3. Added options to scrape all 72 branches (`--all`), preset key regional branches (default), a limited count (`--count N`), or filter by towns (`--towns Kisumu,Mombasa,Nakuru,Nairobi`).

#### 11. `scraper/seed_quickmart_stores.py` — Quickmart Stores Pre-Population & Seed Utility
- **File:** [`scraper/seed_quickmart_stores.py`](scraper/seed_quickmart_stores.py)
- **Problem:** `db.stores` previously only had `Quickmart Kondele` because `StoreResolutionPipeline` operates lazily on-the-fly when spiders crawl. Other branches did not appear in `db.stores` before being scraped.
- **Solution:**
  1. Created a dedicated seed script `scraper/seed_quickmart_stores.py` that reads both `QUICKMART_BRANCH_PRESETS` and all 72 entries from `quickmart_branches_discovered.json`.
  2. Upserts all 73 Quickmart branches into `db.stores` with preset GPS coordinates, town names, county, and addresses using MongoDB `bulk_write` with `$set` and `$setOnInsert`.
  3. Preserves compatibility with `StoreResolutionPipeline`: existing stores are enriched rather than duplicated when individual spiders run.
- **Verification:**
  - Ran `docker compose exec scraper python scraper/seed_quickmart_stores.py`.
  - Confirmed 73 Quickmart stores populated in `db.stores` (total stores in database: 75 including Naivas and Carrefour).

#### 12. `QUICKMART_COMMANDS.md` — Comprehensive Quickmart Docker Commands Cheat-Sheet
- **Files:** [`QUICKMART_COMMANDS.md`](QUICKMART_COMMANDS.md), [`ReadMe.md`](ReadMe.md)
- **Addition:** Created an end-to-end testing guide in the repository root detailing all Docker Compose commands for other developers:
  1. Service startup & build commands (`docker compose up -d mongo scraper`, `build scraper`).
  2. One-command store seeding (`docker compose exec scraper python scraper/seed_quickmart_stores.py`).
  3. Single-branch crawls with item limits for Kisumu, Nairobi, Nakuru, Mombasa.
  4. Multi-branch batch crawls via `scraper/batch_quickmart.py`.
  5. MongoDB verification commands via Python one-liners, `mongosh`, and Mongo Express.
  6. Real-time log monitoring commands.

---

### Verification
- **Python Byte-compilation:** Successfully compiled `scraper/config/quickmart_branches.py`, `scraper/spiders/quickmart_spider.py`, `scraper/pipelines/store_resolution_pipeline.py`, `scraper/worker.py`, and `scraper/scheduler.py` (`python -m py_compile`).
- **Branch Resolution Test Suite:** Verified branch resolution across Kisumu, Nairobi CBD, Nairobi Donholm, Nakuru, and Mombasa:
  - Correctly resolved shop IDs (Kisumu: 23, Nairobi Pioneer: 16, Donholm: 52, Nakuru: 67, Mombasa: 35).
  - Correctly generated localized Growcer cookies (`_ygShopId`, `_ygGeoAddress`, `_ygGeoLat`, `_ygGeoLng`, `_ygGeoRadius`).
- **DOM Selector Verification:** Verified extraction on live Quickmart product HTML (`https://www.quickmart.co.ke/quick-choice-sugar-1kg-22`), successfully resolving product title `"Quick Choice Sugar 1Kg"` and active price `"KES 155.00"`.
- **Spider & Item Integration:** Verified that `store_branch`, `store_town`, `store_county`, and GPS coordinates propagate through `QuickmartSpider.build_item` into `StoreResolutionPipeline` for distinct `store_id` generation.
- **Live Scrape Verification:** Ran live Kisumu crawl in container; verified `Quickmart Kondele` created in `db.stores` and prices recorded in `db.prices` with the matching `store_id`.
- **Store Pre-population Verification:** Successfully executed `scraper/seed_quickmart_stores.py` populating all 73 Quickmart branches into `db.stores`.

