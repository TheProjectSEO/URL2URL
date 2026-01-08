#!/usr/bin/env python3
"""
Upload test data from previous Nykaa/Purplle run to Supabase via API.
Uses the /api/jobs/{job_id}/run endpoint to upload products and run matching.
"""

import csv
import requests
import json
from typing import Dict, List

API_URL = "http://localhost:8000"
JOB_ID = "550f113b-d9f9-468f-9370-a98f8235bb17"
DATA_DIR = "/Users/adityaaman/Desktop/All Development/urltourl/output/demo_run"


def load_csv(filepath: str) -> List[Dict]:
    """Load CSV file into list of dicts."""
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    print("=" * 60)
    print("UPLOADING TEST DATA & RUNNING MATCHING")
    print("=" * 60)

    # Load data
    print("\n1. Loading CSV files...")
    nykaa_products = load_csv(f"{DATA_DIR}/products_nykaa.csv")
    purplle_products = load_csv(f"{DATA_DIR}/products_purplle.csv")

    print(f"   - Nykaa products: {len(nykaa_products)}")
    print(f"   - Purplle products: {len(purplle_products)}")

    # Prepare products for API
    site_a_products = [
        {
            "url": p["url"],
            "title": p["title"],
            "brand": p.get("brand", ""),
            "category": p.get("category", ""),
            "price": float(p["price"]) if p.get("price") else None
        }
        for p in nykaa_products
    ]

    site_b_products = [
        {
            "url": p["url"],
            "title": p["title"],
            "brand": p.get("brand", ""),
            "category": p.get("category", ""),
            "price": float(p["price"]) if p.get("price") else None
        }
        for p in purplle_products
    ]

    # Run matching via API
    print("\n2. Sending data to API for matching...")
    print(f"   Job ID: {JOB_ID}")

    payload = {
        "site_a_products": site_a_products,
        "site_b_products": site_b_products
    }

    resp = requests.post(
        f"{API_URL}/api/jobs/{JOB_ID}/run",
        json=payload,
        timeout=300  # 5 minute timeout for large datasets
    )

    print(f"   Response status: {resp.status_code}")

    if resp.status_code == 200:
        result = resp.json()
        print(f"\n3. MATCHING COMPLETED!")
        print(f"   - Total matches: {result.get('total_matches', 0)}")
        print(f"   - High confidence: {result.get('high_confidence', 0)}")
        print(f"   - Needs review: {result.get('needs_review', 0)}")
    else:
        print(f"   Error: {resp.text}")
        return

    # Verify data in Supabase
    print("\n4. Verifying data via API...")

    # Get job details
    resp = requests.get(f"{API_URL}/api/jobs/{JOB_ID}")
    if resp.status_code == 200:
        job = resp.json()
        print(f"   - Job status: {job.get('status')}")
        print(f"   - Products Site A: {job.get('products_site_a', 0)}")
        print(f"   - Products Site B: {job.get('products_site_b', 0)}")
        print(f"   - Total matches: {job.get('total_matches', 0)}")

    # Get sample matches
    resp = requests.get(f"{API_URL}/api/jobs/{JOB_ID}/matches?page_size=3")
    if resp.status_code == 200:
        matches = resp.json()
        print(f"\n5. Sample matches:")
        for i, m in enumerate(matches.get("items", [])[:3], 1):
            print(f"\n   Match {i}:")
            print(f"   - Source: {m['source_title'][:50]}...")
            print(f"   - Target: {m['best_match_title'][:50]}...")
            print(f"   - Score: {m['score']:.4f}")
            print(f"   - Confidence: {m['confidence_tier']}")

    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
