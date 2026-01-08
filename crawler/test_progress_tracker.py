#!/usr/bin/env python3
"""
Test script for the Progress Tracker system.

This script demonstrates all features of the progress tracking system:
- Real-time progress updates
- JSON state file
- Terminal UI (if rich is installed)
- HTML dashboard
- Callback system
- Error handling

Run from the project root:
    python -m crawler.test_progress_tracker

Or directly:
    python crawler/test_progress_tracker.py
"""

import json
import os
import random
import sys
import time
import webbrowser
from pathlib import Path
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crawler.progress_tracker import (
    ProgressTracker,
    ProgressCallback,
    load_progress,
    watch_progress,
    RICH_AVAILABLE
)


class VerboseCallback(ProgressCallback):
    """Callback that prints detailed information about events."""

    def __init__(self):
        self.product_count = 0
        self.match_count = 0

    def on_product_found(self, product: Dict) -> None:
        self.product_count += 1
        # Print every 10th product to avoid spam
        if self.product_count % 10 == 0:
            title = product.get('title', 'Unknown')[:40]
            print(f"    [PRODUCT #{self.product_count}] {title}...")

    def on_match_found(self, source: Dict, target: Dict, score: float) -> None:
        self.match_count += 1
        # Print high-quality matches
        if score >= 0.8:
            src = source.get('title', 'Unknown')[:25]
            tgt = target.get('title', 'Unknown')[:25]
            print(f"    [HIGH MATCH] {src}... -> {tgt}... ({score:.2f})")

    def on_error(self, error: str, context: Dict) -> None:
        print(f"    [ERROR] {error}")
        if context:
            print(f"            Context: {context}")


def run_basic_test(output_dir: str) -> None:
    """Run a basic test of the progress tracker."""
    print("\n" + "=" * 70)
    print("TEST 1: Basic Progress Tracking")
    print("=" * 70)

    tracker = ProgressTracker(
        total_sites=2,
        output_dir=output_dir,
        enable_terminal_ui=False,  # Disable for cleaner test output
        enable_html_dashboard=True,
        callback=VerboseCallback()
    )

    # Start crawling site 1
    print("\n[Starting] Crawling Nykaa...")
    tracker.start_crawl("nykaa", target_products=20)

    for i in range(1, 21):
        time.sleep(0.05)  # Simulate work
        tracker.update_crawl(
            "nykaa",
            products_found=i,
            current_page=(i // 5) + 1,
            last_product={"title": f"Nykaa Product {i}", "brand": "TestBrand", "url": f"https://nykaa.com/p/{i}"}
        )

    tracker.complete_crawl("nykaa", 20)
    print("[Completed] Nykaa: 20 products")

    # Start crawling site 2
    print("\n[Starting] Crawling Purplle...")
    tracker.start_crawl("purplle", target_products=25)

    for i in range(1, 26):
        time.sleep(0.05)
        tracker.update_crawl(
            "purplle",
            products_found=i,
            current_page=(i // 6) + 1,
            last_product={"title": f"Purplle Product {i}", "brand": "TestBrand", "url": f"https://purplle.com/p/{i}"}
        )

    tracker.complete_crawl("purplle", 25)
    print("[Completed] Purplle: 25 products")

    # Start matching
    print("\n[Starting] Matching phase...")
    tracker.start_matching(source_count=20, target_count=25)

    for i in range(1, 21):
        time.sleep(0.05)
        score = random.uniform(0.4, 0.95)
        target_idx = random.randint(1, 25)

        tracker.update_matching(
            matched=i,
            current_product=f"Nykaa Product {i}",
            best_match=f"Purplle Product {target_idx}",
            score=score,
            source_data={"title": f"Nykaa Product {i}"},
            target_data={"title": f"Purplle Product {target_idx}"}
        )

    # Complete
    summary = tracker.complete()

    print("\n[Summary]")
    print(f"  Total time: {summary['total_time_formatted']}")
    print(f"  Products crawled: {summary['total_products']}")
    print(f"  Matches completed: {summary['total_matches']}")
    print(f"  Match rate: {summary['match_rate']}%")

    # Verify JSON file
    progress_data = load_progress(output_dir)
    assert progress_data is not None, "Progress file should exist"
    assert progress_data["status"] == "completed", "Status should be completed"
    print("\n[PASSED] Basic test completed successfully!")


def run_error_handling_test(output_dir: str) -> None:
    """Test error handling functionality."""
    print("\n" + "=" * 70)
    print("TEST 2: Error Handling")
    print("=" * 70)

    tracker = ProgressTracker(
        total_sites=1,
        output_dir=output_dir,
        enable_terminal_ui=False,
        enable_html_dashboard=False
    )

    tracker.start_crawl("test_site", target_products=10)

    # Simulate some progress
    for i in range(1, 6):
        tracker.update_crawl("test_site", i, 1)
        time.sleep(0.02)

    # Report an error
    tracker.report_error(
        "Connection timeout after 30 seconds",
        context={"site": "test_site", "page": 1, "url": "https://test.com/page/1"}
    )

    # Continue with more progress
    for i in range(6, 11):
        tracker.update_crawl("test_site", i, 2)
        time.sleep(0.02)

    # Report another error
    tracker.report_error(
        "Rate limit exceeded",
        context={"site": "test_site", "retry_after": 60}
    )

    tracker.complete_crawl("test_site", 10)
    summary = tracker.complete()

    assert summary["errors_count"] == 2, "Should have 2 errors"
    print(f"\n[Summary] Errors recorded: {summary['errors_count']}")
    print("[PASSED] Error handling test completed!")


def run_context_manager_test(output_dir: str) -> None:
    """Test context manager support."""
    print("\n" + "=" * 70)
    print("TEST 3: Context Manager")
    print("=" * 70)

    # Test successful completion
    with ProgressTracker(
        total_sites=1,
        output_dir=output_dir,
        enable_terminal_ui=False,
        enable_html_dashboard=False
    ) as tracker:
        tracker.start_crawl("context_test", 5)
        for i in range(1, 6):
            tracker.update_crawl("context_test", i, 1)
            time.sleep(0.02)
        tracker.complete_crawl("context_test", 5)

    progress_data = load_progress(output_dir)
    assert progress_data["status"] == "completed", "Context manager should auto-complete"
    print("[PASSED] Context manager auto-completion works!")

    # Test error handling in context manager
    error_dir = os.path.join(output_dir, "error_test")
    os.makedirs(error_dir, exist_ok=True)

    try:
        with ProgressTracker(
            total_sites=1,
            output_dir=error_dir,
            enable_terminal_ui=False,
            enable_html_dashboard=False
        ) as tracker:
            tracker.start_crawl("error_test", 10)
            tracker.update_crawl("error_test", 5, 1)
            raise ValueError("Simulated error for testing")
    except ValueError:
        pass  # Expected

    error_progress = load_progress(error_dir)
    assert error_progress["status"] == "error", "Context manager should set error status on exception"
    assert len(error_progress["errors"]) > 0, "Error should be recorded"
    print("[PASSED] Context manager error handling works!")


def run_callback_test(output_dir: str) -> None:
    """Test custom callback functionality."""
    print("\n" + "=" * 70)
    print("TEST 4: Custom Callbacks")
    print("=" * 70)

    class CountingCallback(ProgressCallback):
        def __init__(self):
            self.products = []
            self.matches = []
            self.errors = []

        def on_product_found(self, product: Dict) -> None:
            self.products.append(product)

        def on_match_found(self, source: Dict, target: Dict, score: float) -> None:
            self.matches.append({"source": source, "target": target, "score": score})

        def on_error(self, error: str, context: Dict) -> None:
            self.errors.append({"error": error, "context": context})

    callback = CountingCallback()

    tracker = ProgressTracker(
        total_sites=1,
        output_dir=output_dir,
        enable_terminal_ui=False,
        enable_html_dashboard=False,
        callback=callback
    )

    tracker.start_crawl("callback_test", 5)
    for i in range(1, 6):
        tracker.update_crawl(
            "callback_test", i, 1,
            last_product={"title": f"Product {i}"}
        )
    tracker.complete_crawl("callback_test", 5)

    tracker.start_matching(5, 5)
    for i in range(1, 6):
        tracker.update_matching(
            i, f"Product {i}", f"Target {i}", 0.9,
            source_data={"title": f"Product {i}"},
            target_data={"title": f"Target {i}"}
        )

    tracker.report_error("Test error", {"test": True})
    tracker.complete()

    assert len(callback.products) == 5, f"Expected 5 products, got {len(callback.products)}"
    assert len(callback.matches) == 5, f"Expected 5 matches, got {len(callback.matches)}"
    assert len(callback.errors) == 1, f"Expected 1 error, got {len(callback.errors)}"

    print(f"  Products captured: {len(callback.products)}")
    print(f"  Matches captured: {len(callback.matches)}")
    print(f"  Errors captured: {len(callback.errors)}")
    print("[PASSED] Custom callback test completed!")


def run_interactive_demo(output_dir: str) -> None:
    """Run an interactive demo with terminal UI and HTML dashboard."""
    print("\n" + "=" * 70)
    print("DEMO: Interactive Progress Tracking")
    print("=" * 70)

    dashboard_path = os.path.join(output_dir, "dashboard.html")
    print(f"\nDashboard will be created at: {dashboard_path}")

    # Ask if user wants to open browser
    try:
        response = input("\nOpen dashboard in browser? (y/n): ").strip().lower()
        open_browser = response in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        open_browser = False
        print()

    tracker = ProgressTracker(
        total_sites=2,
        output_dir=output_dir,
        enable_terminal_ui=RICH_AVAILABLE,
        enable_html_dashboard=True,
        callback=VerboseCallback()
    )

    if open_browser:
        webbrowser.open(f"file://{os.path.abspath(dashboard_path)}")
        print("Dashboard opened in browser (auto-refreshes every 2 seconds)")

    print("\nStarting interactive demo...")
    print("Watch the terminal UI and/or HTML dashboard for live updates!")
    print("-" * 70)

    # Simulate realistic crawling
    sites_config = [
        ("nykaa", 40, ["Lipstick", "Foundation", "Serum", "Mascara"]),
        ("purplle", 50, ["Face Wash", "Moisturizer", "Sunscreen", "Toner"])
    ]

    total_products = []

    for site_name, target, product_types in sites_config:
        print(f"\n[{site_name.upper()}] Starting crawl (target: {target} products)")
        tracker.start_crawl(site_name, target)

        products_found = 0
        page = 1

        while products_found < target:
            # Simulate batch scraping
            batch_size = random.randint(4, 10)
            time.sleep(random.uniform(0.1, 0.3))

            new_products = []
            for _ in range(batch_size):
                if products_found >= target:
                    break
                products_found += 1
                product_type = random.choice(product_types)
                product = {
                    "title": f"{site_name.title()} {product_type} #{products_found}",
                    "brand": random.choice(["Lakme", "Maybelline", "L'Oreal", "Revlon", "NYX"]),
                    "url": f"https://{site_name}.com/product/{products_found}",
                    "price": f"Rs. {random.randint(199, 2999)}"
                }
                new_products.append(product)
                total_products.append(product)

            tracker.update_crawl(
                site_name,
                products_found,
                page,
                last_product=new_products[-1] if new_products else None
            )

            # Occasionally simulate page turn
            if random.random() > 0.6:
                page += 1

            # Occasionally simulate an error
            if random.random() > 0.95:
                tracker.report_error(
                    f"Temporary rate limit on page {page}",
                    context={"site": site_name, "page": page}
                )
                time.sleep(0.2)

        tracker.complete_crawl(site_name, products_found)
        print(f"[{site_name.upper()}] Completed: {products_found} products from {page} pages")

    # Matching phase
    source_products = total_products[:40]  # Nykaa products
    target_products = total_products[40:]  # Purplle products

    print(f"\n[MATCHING] Starting match phase ({len(source_products)} sources x {len(target_products)} targets)")
    tracker.start_matching(len(source_products), len(target_products))

    for i, source in enumerate(source_products, 1):
        # Simulate matching computation
        time.sleep(random.uniform(0.05, 0.15))

        # Find "best" match (randomly for demo)
        target = random.choice(target_products)
        score = random.uniform(0.3, 0.98)

        # Higher scores for same product type
        if any(word in source["title"] for word in target["title"].split()):
            score = min(score + 0.2, 0.99)

        tracker.update_matching(
            matched=i,
            current_product=source["title"],
            best_match=target["title"],
            score=score,
            source_data=source,
            target_data=target
        )

    # Complete
    summary = tracker.complete()

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print(f"\nFinal Summary:")
    print(json.dumps(summary, indent=2))
    print(f"\nFiles created:")
    print(f"  - {tracker.progress_file}")
    print(f"  - {tracker.dashboard_file}")


def main():
    """Run all tests."""
    print("\n" + "#" * 70)
    print("#" + " " * 20 + "PROGRESS TRACKER TESTS" + " " * 26 + "#")
    print("#" * 70)

    # Create test output directory
    test_output_dir = Path(__file__).parent.parent / "output" / "test_progress"
    test_output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nTest output directory: {test_output_dir}")
    print(f"Rich library available: {RICH_AVAILABLE}")

    # Run tests
    try:
        run_basic_test(str(test_output_dir / "basic"))
        run_error_handling_test(str(test_output_dir / "errors"))
        run_context_manager_test(str(test_output_dir / "context"))
        run_callback_test(str(test_output_dir / "callback"))

        print("\n" + "=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)

        # Ask about interactive demo
        try:
            response = input("\nRun interactive demo with live UI? (y/n): ").strip().lower()
            if response in ('y', 'yes'):
                run_interactive_demo(str(test_output_dir / "demo"))
        except (EOFError, KeyboardInterrupt):
            print("\nSkipping interactive demo.")

    except AssertionError as e:
        print(f"\n[FAILED] Test assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
