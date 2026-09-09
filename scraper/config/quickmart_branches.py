"""
Quickmart Kenya store branches configuration and resolver.
Maps towns and branch names to Quickmart's Growcer session cookies and coordinates.
"""
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Predefined primary branch configurations for key regions
QUICKMART_BRANCH_PRESETS: Dict[str, Dict[str, Any]] = {
    # Kisumu region
    "kisumu": {
        "branch_name": "Quickmart Kondele",
        "town": "Kisumu",
        "county": "Kisumu",
        "shop_id": 23,
        "slug": "/2801",
        "gps_latitude": -0.0786108,
        "gps_longitude": 34.7768412,
        "address": "Kibos Road, Kondele, Kisumu, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "23"},
            {"name": "_ygGeoAddress", "value": "Kisumu"},
            {"name": "_ygGeoLat", "value": "-0.0786108"},
            {"name": "_ygGeoLng", "value": "34.7768412"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Nairobi region (Default Flagship CBD)
    "nairobi": {
        "branch_name": "Quickmart Pioneer (CBD)",
        "town": "Nairobi",
        "county": "Nairobi",
        "shop_id": 16,
        "slug": "/3501",
        "gps_latitude": -1.283698,
        "gps_longitude": 36.825346,
        "address": "Pioneer House, Moi Avenue, Nairobi, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "16"},
            {"name": "_ygGeoAddress", "value": "Nairobi"},
            {"name": "_ygGeoLat", "value": "-1.283698"},
            {"name": "_ygGeoLng", "value": "36.825346"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Nairobi - Eastlands / Donholm
    "nairobi_donholm": {
        "branch_name": "Quickmart Donholm",
        "town": "Nairobi",
        "county": "Nairobi",
        "shop_id": 52,
        "slug": "/2201",
        "gps_latitude": -1.3018395,
        "gps_longitude": 36.8885271,
        "address": "Donholm, Nairobi, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "52"},
            {"name": "_ygGeoAddress", "value": "Nairobi"},
            {"name": "_ygGeoLat", "value": "-1.3018395"},
            {"name": "_ygGeoLng", "value": "36.8885271"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Nairobi / Kiambu - Ruaka
    "nairobi_ruaka": {
        "branch_name": "Quickmart Banana Rd",
        "town": "Nairobi",
        "county": "Kiambu",
        "shop_id": 65,
        "slug": "/banana",
        "gps_latitude": -1.2056044,
        "gps_longitude": 36.7796064,
        "address": "Banana Raini Road, Ruaka, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "65"},
            {"name": "_ygGeoAddress", "value": "Ruaka"},
            {"name": "_ygGeoLat", "value": "-1.2056044"},
            {"name": "_ygGeoLng", "value": "36.7796064"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Nairobi - Kilimani
    "nairobi_kilimani": {
        "branch_name": "Quickmart Chaka Rd",
        "town": "Nairobi",
        "county": "Nairobi",
        "shop_id": 14,
        "slug": "/1801",
        "gps_latitude": -1.2915,
        "gps_longitude": 36.7865,
        "address": "Chaka Road, Kilimani, Nairobi, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "14"},
            {"name": "_ygGeoAddress", "value": "Nairobi"},
            {"name": "_ygGeoLat", "value": "-1.2915"},
            {"name": "_ygGeoLng", "value": "36.7865"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Nakuru region
    "nakuru": {
        "branch_name": "Quickmart Nakuru Statehouse",
        "town": "Nakuru",
        "county": "Nakuru",
        "shop_id": 67,
        "slug": "/nakurustatehouse",
        "gps_latitude": -0.3030988,
        "gps_longitude": 36.080026,
        "address": "Statehouse Road, Nakuru, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "67"},
            {"name": "_ygGeoAddress", "value": "Nakuru"},
            {"name": "_ygGeoLat", "value": "-0.3030988"},
            {"name": "_ygGeoLng", "value": "36.080026"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    },
    # Coastal / Mombasa region
    "mombasa": {
        "branch_name": "Quickmart Mtwapa Mall",
        "town": "Mombasa",
        "county": "Kilifi",
        "shop_id": 35,
        "slug": "/4801",
        "gps_latitude": -3.9455956,
        "gps_longitude": 39.7452844,
        "address": "Mtwapa Mall, Mombasa, Kenya",
        "cookies": [
            {"name": "_ygShopId", "value": "35"},
            {"name": "_ygGeoAddress", "value": "Mtwapa"},
            {"name": "_ygGeoLat", "value": "-3.9455956"},
            {"name": "_ygGeoLng", "value": "39.7452844"},
            {"name": "_ygGeoRadius", "value": "15"},
        ]
    }
}


import os
import json
import urllib.request
import http.cookiejar

# In-memory cache for dynamically resolved branches
_DYNAMIC_BRANCH_CACHE: Dict[str, Dict[str, Any]] = {}

def _load_discovered_branches() -> List[Dict[str, Any]]:
    """Load discovered branches from JSON file if available."""
    candidates = [
        os.path.join(os.path.dirname(__file__), "quickmart_branches_discovered.json"),
        os.path.join(os.path.abspath("."), "quickmart_branches_discovered.json"),
        "/app/scraper/config/quickmart_branches_discovered.json",
        "/app/quickmart_branches_discovered.json"
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading {path}: {e}")
    return []

DISCOVERED_BRANCHES: List[Dict[str, Any]] = _load_discovered_branches()


def fetch_dynamic_branch_profile(discovered_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch live Growcer cookies and coordinates for a discovered branch slug."""
    slug = discovered_entry.get("slug", "")
    name = discovered_entry.get("name", "Quickmart")
    tags = discovered_entry.get("location_tags", [])
    
    town = tags[0] if tags else "Nairobi"
    county = tags[0] if tags else "Nairobi"
    shop_id = discovered_entry.get("shop_id")
    
    cookies = []
    lat = None
    lng = None
    address = f"{name}, {town}, Kenya"
    
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        url = f"https://www.quickmart.co.ke{slug}"
        req = urllib.request.Request(url, headers={'User-Agent': 'PricePoa Scraper (+https://pricepoa.co.ke)'})
        with opener.open(req, timeout=10) as resp:
            for c in cj:
                if c.name.startswith('_yg') or c.name == 'PHPSESSID':
                    cookies.append({"name": c.name, "value": c.value})
                    if c.name == '_ygGeoLat':
                        try: lat = float(c.value)
                        except: pass
                    elif c.name == '_ygGeoLng':
                        try: lng = float(c.value)
                        except: pass
                    elif c.name == '_ygShopId':
                        try: shop_id = int(c.value)
                        except: pass
                    elif c.name == '_ygGeoAddress':
                        address = f"{c.value}, Kenya"
    except Exception as e:
        logger.warning(f"Failed to fetch dynamic cookies for {name} ({slug}): {e}")
        
    profile = {
        "branch_name": name,
        "branch": name,
        "town": town,
        "county": county,
        "shop_id": shop_id,
        "slug": slug,
        "gps_latitude": lat,
        "gps_longitude": lng,
        "address": address,
        "cookies": cookies
    }
    return profile


def resolve_branch(town: Optional[str] = None, branch: Optional[str] = None) -> Dict[str, Any]:
    """
    Resolve a branch configuration by town or branch name.
    
    Args:
        town: Town name (e.g. 'Kisumu', 'Nairobi', 'Nakuru')
        branch: Branch name or keyword (e.g. 'Kondele', 'Donholm', 'Banana', 'Pioneer')
        
    Returns:
        Dictionary containing branch profile with cookies and coordinates.
        Defaults to Nairobi CBD if neither matches.
    """
    # 1. Match by branch name/keyword in presets
    if branch:
        branch_lower = branch.strip().lower()
        for key, config in QUICKMART_BRANCH_PRESETS.items():
            if branch_lower in config["branch_name"].lower() or branch_lower in key:
                logger.info(f"Resolved Quickmart branch by preset name: '{branch}' -> {config['branch_name']}")
                res = config.copy()
                res["branch"] = res["branch_name"]
                return res

    # 2. Match by town in presets
    if town:
        town_lower = town.strip().lower()
        if town_lower in QUICKMART_BRANCH_PRESETS:
            config = QUICKMART_BRANCH_PRESETS[town_lower]
            logger.info(f"Resolved Quickmart branch by preset town: '{town}' -> {config['branch_name']}")
            res = config.copy()
            res["branch"] = res["branch_name"]
            return res
        
        for config in QUICKMART_BRANCH_PRESETS.values():
            if town_lower in config["town"].lower():
                logger.info(f"Resolved Quickmart branch by preset partial town: '{town}' -> {config['branch_name']}")
                res = config.copy()
                res["branch"] = res["branch_name"]
                return res

    # 3. Dynamic lookup across all 72 discovered branches
    query = (branch or town or "").strip().lower()
    if query:
        # Check dynamic cache first
        if query in _DYNAMIC_BRANCH_CACHE:
            return _DYNAMIC_BRANCH_CACHE[query].copy()

        for entry in DISCOVERED_BRANCHES:
            b_name = entry.get("name", "").lower()
            b_slug = entry.get("slug", "").lower()
            b_tags = " ".join(entry.get("location_tags", [])).lower()
            
            if query in b_name or query in b_slug or query in b_tags:
                logger.info(f"Dynamically resolving discovered branch for '{query}': {entry.get('name')}")
                profile = fetch_dynamic_branch_profile(entry)
                _DYNAMIC_BRANCH_CACHE[query] = profile
                return profile.copy()

    # 4. Default fallback: Nairobi CBD
    logger.info("No branch or town matched, falling back to default Quickmart Nairobi Pioneer")
    result = QUICKMART_BRANCH_PRESETS["nairobi"].copy()
    result["branch"] = result["branch_name"]
    return result


def list_available_branches() -> List[Dict[str, Any]]:
    """List all available predefined branch configurations."""
    return list(QUICKMART_BRANCH_PRESETS.values())


def list_all_branches() -> List[Dict[str, Any]]:
    """List all 72 discovered Quickmart branches."""
    if DISCOVERED_BRANCHES:
        return DISCOVERED_BRANCHES
    return list_available_branches()
