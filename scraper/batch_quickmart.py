#!/usr/bin/env python3
"""
Batch Runner for Quickmart Kenya Multi-Branch Scraping.

Runs quickmart_spider sequentially across multiple branches with a specified
item limit (e.g. 2 items per branch) to build a sample dataset without running
out of memory or hitting concurrent connection limits.
"""
import argparse
import os
import sys
import subprocess
import time
from typing import List, Dict, Any

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scraper.config.quickmart_branches import (
    QUICKMART_BRANCH_PRESETS,
    DISCOVERED_BRANCHES,
    list_available_branches
)


def get_target_branches(args: argparse.Namespace) -> List[Dict[str, Any]]:
    """Determine the list of branches to scrape based on CLI arguments."""
    # 1. Filter by specific towns if requested
    if args.towns:
        target_towns = [t.strip().lower() for t in args.towns.split(",")]
        matched = []
        # Check presets first
        for p in QUICKMART_BRANCH_PRESETS.values():
            if p["town"].lower() in target_towns:
                matched.append(p)
        # Check discovered branches for any missing towns
        for d in DISCOVERED_BRANCHES:
            tags = " ".join(d.get("location_tags", [])).lower()
            name = d.get("name", "").lower()
            if any(t in tags or t in name for t in target_towns):
                if not any(m["branch_name"].lower() == d["name"].lower() for m in matched):
                    matched.append({
                        "branch_name": d["name"],
                        "town": d.get("location_tags", ["Nairobi"])[0],
                        "slug": d.get("slug")
                    })
        return matched

    # 2. All 72 branches
    if args.all:
        branches = []
        for d in DISCOVERED_BRANCHES:
            branches.append({
                "branch_name": d["name"],
                "town": d.get("location_tags", ["Nairobi"])[0],
                "slug": d.get("slug")
            })
        if not branches:
            branches = list_available_branches()
        if args.count:
            return branches[:args.count]
        return branches

    # 3. Limited count from discovered or presets
    if args.count:
        if DISCOVERED_BRANCHES:
            branches = []
            for d in DISCOVERED_BRANCHES[:args.count]:
                branches.append({
                    "branch_name": d["name"],
                    "town": d.get("location_tags", ["Nairobi"])[0],
                    "slug": d.get("slug")
                })
            return branches
        return list_available_branches()[:args.count]

    # 4. Default: Preset key regional branches (Kisumu, Nairobi CBD, Donholm, Ruaka, Kilimani, Nakuru, Mombasa)
    return list_available_branches()


def run_branch_scrape(branch_info: Dict[str, Any], items_per_branch: int) -> Dict[str, Any]:
    """Execute a single Scrapy run for a branch in a fresh subprocess."""
    branch_name = branch_info.get("branch_name") or branch_info.get("name")
    town = branch_info.get("town", "Nairobi")

    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "quickmart_spider",
        "-a", f"branch={branch_name}",
        "-a", f"town={town}",
        "-s", f"CLOSESPIDER_ITEMCOUNT={items_per_branch}"
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT

    start_time = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        duration = time.time() - start_time
        success = proc.returncode == 0
        return {
            "branch_name": branch_name,
            "town": town,
            "success": success,
            "duration": duration,
            "output": proc.stdout
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "branch_name": branch_name,
            "town": town,
            "success": False,
            "duration": duration,
            "output": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="Batch Scrape Quickmart Kenya Branches")
    parser.add_argument(
        "--items", "-n",
        type=int,
        default=2,
        help="Number of items to scrape per branch (default: 2)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scrape all 72 discovered branches"
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=None,
        help="Limit number of branches to scrape"
    )
    parser.add_argument(
        "--towns",
        type=str,
        default=None,
        help="Comma-separated towns to filter by (e.g. 'Kisumu,Nairobi,Nakuru,Mombasa')"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print Scrapy log output for each branch crawl"
    )

    args = parser.parse_args()
    targets = get_target_branches(args)

    print("\n" + "=" * 80)
    print(" QUICKMART MULTI-BRANCH BATCH SCRAPER")
    print("=" * 80)
    print(f" Total Target Branches: {len(targets)}")
    print(f" Target Items Per Branch: {args.items}")
    print(" Branches Scheduled:")
    for idx, b in enumerate(targets, 1):
        print(f"   {idx:2d}. {b.get('branch_name', b.get('name'))} ({b.get('town')})")
    print("=" * 80 + "\n")

    results = []
    total_start = time.time()

    for idx, branch in enumerate(targets, 1):
        b_name = branch.get("branch_name") or branch.get("name")
        b_town = branch.get("town")
        print(f"[{idx}/{len(targets)}] Scraping '{b_name}' ({b_town}) [limit={args.items}] ... ", end="", flush=True)

        res = run_branch_scrape(branch, args.items)
        results.append(res)

        if res["success"]:
            print(f"DONE ({res['duration']:.1f}s)")
        else:
            print(f"FAILED ({res['duration']:.1f}s)")

        if args.verbose:
            print("-" * 40 + f" LOGS: {b_name} " + "-" * 40)
            print(res["output"][-1500:])  # print last 1500 chars
            print("-" * 80)

    total_time = time.time() - total_start

    # Print Summary Report
    print("\n" + "=" * 80)
    print("                       BATCH SCRAPING SUMMARY")
    print("=" * 80)
    print(f"{'Branch Name':<38} {'Town':<15} {'Status':<10} {'Duration':<10}")
    print("-" * 80)
    successful = 0
    for r in results:
        status = "SUCCESS" if r["success"] else "FAILED"
        if r["success"]:
            successful += 1
        print(f"{r['branch_name']:<38} {r['town']:<15} {status:<10} {r['duration']:.1f}s")
    print("=" * 80)
    print(f" Total: {len(results)} | Successful: {successful} | Failed: {len(results) - successful} | Total Elapsed: {total_time:.1f}s")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
