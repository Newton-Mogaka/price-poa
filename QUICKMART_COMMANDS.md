# Quickmart Kenya Scraper — Docker Commands & Testing Guide

This cheat-sheet provides all Docker commands for developers to test and verify the localized Quickmart supermarket scraper on their local environment.

---

## 1. Prerequisites & Environment Setup

Start the required services (`mongo` and `scraper`):

```bash
# Start MongoDB and Scraper in background
docker compose up -d mongo scraper

# (Optional) Rebuild scraper image after pulling code changes
docker compose build scraper
```

Verify containers are running:
```bash
docker compose ps
```

---

## 2. Pre-Populate All 73 Quickmart Branches (Recommended First Step)

Populate all 73 discovered Quickmart branches across Kenya into `db.stores` with preset GPS coordinates, towns, counties, and addresses:

```bash
docker compose exec scraper python scraper/seed_quickmart_stores.py
```

*Note: If stores are already seeded, this command safely updates existing records without creating duplicates.*

---

## 3. Single-Branch Crawling (Test Sample)

### A. Crawl by Town (with item limit)
Scrape a sample (e.g. 5 products) from a specific town. The resolver maps towns to the appropriate regional branch and sets Growcer session cookies:

```bash
# Kisumu (Quickmart Kondele)
docker compose exec scraper python -m scrapy crawl quickmart_spider -a town=Kisumu -s CLOSESPIDER_ITEMCOUNT=5

# Nairobi (Quickmart Pioneer CBD)
docker compose exec scraper python -m scrapy crawl quickmart_spider -a town=Nairobi -s CLOSESPIDER_ITEMCOUNT=5

# Nakuru (Quickmart Nakuru Statehouse)
docker compose exec scraper python -m scrapy crawl quickmart_spider -a town=Nakuru -s CLOSESPIDER_ITEMCOUNT=5

# Mombasa (Quickmart Mtwapa Mall)
docker compose exec scraper python -m scrapy crawl quickmart_spider -a town=Mombasa -s CLOSESPIDER_ITEMCOUNT=5
```

### B. Crawl by Branch Name / Keyword
```bash
# Specific Nairobi branches
docker compose exec scraper python -m scrapy crawl quickmart_spider -a branch="Donholm" -s CLOSESPIDER_ITEMCOUNT=5
docker compose exec scraper python -m scrapy crawl quickmart_spider -a branch="Chaka Rd" -s CLOSESPIDER_ITEMCOUNT=5
docker compose exec scraper python -m scrapy crawl quickmart_spider -a branch="Banana" -s CLOSESPIDER_ITEMCOUNT=5
```

---

## 4. Multi-Branch Batch Crawling (`batch_quickmart.py`)

Run sequential crawls across multiple branches in isolated subprocesses (prevents Twisted reactor errors and memory accumulation from Playwright):

```bash
# 1. Crawl sample towns (Kisumu, Nairobi, Nakuru, Mombasa) with 2 products each:
docker compose exec scraper python scraper/batch_quickmart.py --towns "Kisumu,Nairobi,Nakuru,Mombasa" --items 2

# 2. Crawl all 7 regional presets (Kisumu, Pioneer CBD, Donholm, Ruaka, Kilimani, Nakuru, Mombasa):
docker compose exec scraper python scraper/batch_quickmart.py --items 2

# 3. Crawl the first 5 branches from the discovered catalog:
docker compose exec scraper python scraper/batch_quickmart.py --count 5 --items 2

# 4. Crawl all 72 branches nationwide (2 products per branch):
docker compose exec scraper python scraper/batch_quickmart.py --all --items 2
```

---

## 5. Running via Background Worker (`worker.py`)

You can also run through the standardized worker interface:

```bash
# Run Quickmart once immediately for a specific town:
docker compose exec scraper python scraper/worker.py --mode once --spider quickmart_spider --town Kisumu

# Run in test mode:
docker compose exec scraper python scraper/worker.py --mode test --spider quickmart_spider --town Nairobi --branch Pioneer
```

---

## 6. Verifying Scraped Data in MongoDB

### A. Quick Summary Script
Verify stores, products, and prices directly in the terminal:

```bash
# Check Quickmart branches in db.stores:
docker compose exec scraper python -c "from pymongo import MongoClient; c=MongoClient('mongodb://pricepoa_dev:pricepoa_dev_password@mongo:27017/pricepoa?authSource=admin'); qm=list(c.pricepoa.stores.find({'chain':'Quickmart'})); print(f'Total Quickmart branches in db.stores: {len(qm)}'); [print(f' - {s[\"branch\"]} ({s.get(\"town\")}) | coords: {s.get(\"gps_latitude\")}, {s.get(\"gps_longitude\")}') for s in qm[:7]]"

# Check products & prices scraped:
docker compose exec scraper python -c "from pymongo import MongoClient; c=MongoClient('mongodb://pricepoa_dev:pricepoa_dev_password@mongo:27017/pricepoa?authSource=admin'); print('Total products in db:', c.pricepoa.products.count_documents({})); print('Total prices in db:', c.pricepoa.prices.count_documents({})); [print(f'Price: KES {p.get(\"price_kes\")} | Store ID: {p.get(\"store_id\")}') for p in c.pricepoa.prices.find().limit(5)]"
```

### B. Interactive Mongo Shell (`mongosh`)
```bash
docker compose exec mongo mongosh -u pricepoa_dev -p pricepoa_dev_password --authenticationDatabase admin pricepoa
```

Inside `mongosh`:
```javascript
// Count Quickmart branches
db.stores.countDocuments({ chain: "Quickmart" });

// View sample Quickmart store records
db.stores.find({ chain: "Quickmart" }, { chain: 1, branch: 1, town: 1, gps_latitude: 1, gps_longitude: 1 }).limit(5);

// View prices linked to Quickmart stores
db.prices.find().sort({ verified_at: -1 }).limit(5);

// Exit
exit
```

### C. Mongo Express Web UI (Visual)
If Mongo Express is running:
1. Start it if needed: `docker compose --profile dev up -d mongo-express`
2. Open in browser: [http://localhost:8081](http://localhost:8081)
3. Navigate to database `pricepoa` -> collections `stores`, `products`, `prices`.

---

## 7. Monitoring & Debugging

```bash
# Follow scraper logs in real time:
docker compose logs -f scraper

# Check exit codes and process health:
docker compose ps scraper
```
