#!/usr/bin/env python3
"""
Nykaa.com Beauty Products Scraper
Scrapes product information from Nykaa's beauty categories using Playwright.

Usage:
    python scrape_nykaa.py --count 50 --out data/nykaa.csv
"""

import asyncio
import argparse
import csv
import os
import random
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
from tqdm import tqdm


@dataclass
class Product:
    """Data class for product information."""
    url: str
    title: str
    brand: str
    category: str
    price: Optional[str] = None


# Category configuration - using search pages (more reliable than category pages)
CATEGORIES = {
    "lipsticks": {
        "url": "https://www.nykaa.com/search/result/?q=lipstick",
        "name": "Lipstick",
        "query": "lipstick"
    },
    "foundations": {
        "url": "https://www.nykaa.com/search/result/?q=foundation",
        "name": "Foundation",
        "query": "foundation"
    },
    "serums": {
        "url": "https://www.nykaa.com/search/result/?q=serum",
        "name": "Serum",
        "query": "serum"
    }
}


async def random_delay(min_sec: float = 1.0, max_sec: float = 2.0) -> None:
    """Add random delay to avoid rate limiting."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def scroll_page(page: Page, scroll_count: int = 3) -> None:
    """Scroll down the page to load lazy-loaded content."""
    for _ in range(scroll_count):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(0.5)


async def extract_products_from_page(page: Page, category_name: str, max_products: int) -> list[Product]:
    """Extract product information from the current page."""
    products = []

    # Wait for product cards to load
    try:
        # Try multiple selectors as Nykaa's structure may vary
        selectors = [
            ".css-d5z3ro",  # Common product card class
            ".product-listing-content",
            "[data-test-id='product-card']",
            ".css-1rd7vky",  # Alternative product card class
            ".css-1knrt9j",  # Another variant
            ".productWrapper",
            ".css-po5vsk",  # Product container
        ]

        product_selector = None
        for selector in selectors:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                product_selector = selector
                break
            except PlaywrightTimeout:
                continue

        if not product_selector:
            # Fallback: try to find any product links
            product_selector = 'a[href*="/p/"]'
            await page.wait_for_selector(product_selector, timeout=10000)

        # Scroll to load more products
        await scroll_page(page, scroll_count=5)

        # Extract product data using JavaScript evaluation
        product_data = await page.evaluate("""
            () => {
                const products = [];

                // Try to find product containers
                const productCards = document.querySelectorAll('[class*="product"], [class*="Product"], .css-d5z3ro, .css-1rd7vky, .css-1knrt9j');

                for (const card of productCards) {
                    try {
                        // Find product link
                        const link = card.querySelector('a[href*="/p/"]');
                        if (!link) continue;

                        const url = link.href;

                        // Find title - try multiple approaches
                        let title = '';
                        const titleEl = card.querySelector('[class*="title"], [class*="Title"], [class*="name"], [class*="Name"], h3, h4');
                        if (titleEl) {
                            title = titleEl.textContent.trim();
                        } else if (link.title) {
                            title = link.title;
                        } else {
                            // Try to get title from nested text
                            const textNodes = card.querySelectorAll('span, p, div');
                            for (const node of textNodes) {
                                const text = node.textContent.trim();
                                if (text.length > 10 && text.length < 200 && !text.includes('Rs.') && !text.includes('OFF')) {
                                    title = text;
                                    break;
                                }
                            }
                        }

                        // Find brand
                        let brand = '';
                        const brandEl = card.querySelector('[class*="brand"], [class*="Brand"]');
                        if (brandEl) {
                            brand = brandEl.textContent.trim();
                        }

                        // Find price
                        let price = '';
                        const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                        if (priceEl) {
                            const priceText = priceEl.textContent.trim();
                            const priceMatch = priceText.match(/Rs\\.?\\s*([\\d,]+)/i) || priceText.match(/₹\\s*([\\d,]+)/);
                            if (priceMatch) {
                                price = 'Rs. ' + priceMatch[1];
                            } else {
                                price = priceText;
                            }
                        }

                        if (url && title) {
                            products.push({ url, title, brand, price });
                        }
                    } catch (e) {
                        continue;
                    }
                }

                // Also try finding products via direct link search
                if (products.length === 0) {
                    const links = document.querySelectorAll('a[href*="/p/"]');
                    for (const link of links) {
                        const url = link.href;
                        const title = link.textContent.trim() || link.title || '';
                        if (url && title && title.length > 5) {
                            products.push({ url, title, brand: '', price: '' });
                        }
                    }
                }

                return products;
            }
        """)

        # Convert to Product objects and deduplicate
        seen_urls = set()
        for item in product_data:
            if len(products) >= max_products:
                break
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                products.append(Product(
                    url=item['url'],
                    title=item['title'],
                    brand=item['brand'],
                    category=category_name,
                    price=item['price'] if item['price'] else None
                ))

    except PlaywrightTimeout:
        print(f"\nWarning: Timeout waiting for products in {category_name}")
    except Exception as e:
        print(f"\nError extracting products from {category_name}: {str(e)}")

    return products


async def get_next_page_url(page: Page) -> Optional[str]:
    """Get the URL for the next page of results."""
    try:
        # Try to find next page button/link
        next_selectors = [
            'a[aria-label="Next"]',
            'button[aria-label="Next"]',
            '.pagination-next',
            '[class*="next"]',
            'a[rel="next"]',
        ]

        for selector in next_selectors:
            next_btn = await page.query_selector(selector)
            if next_btn:
                href = await next_btn.get_attribute('href')
                if href:
                    return href if href.startswith('http') else f"https://www.nykaa.com{href}"
                # If it's a button, click it and return the new URL
                is_disabled = await next_btn.get_attribute('disabled')
                if not is_disabled:
                    await next_btn.click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    return page.url

        # Try URL parameter manipulation
        current_url = page.url
        if 'page_no=' in current_url:
            # Increment page number
            import re
            match = re.search(r'page_no=(\d+)', current_url)
            if match:
                current_page = int(match.group(1))
                return re.sub(r'page_no=\d+', f'page_no={current_page + 1}', current_url)
        else:
            # Add page parameter
            separator = '&' if '?' in current_url else '?'
            return f"{current_url}{separator}page_no=2"

    except Exception as e:
        print(f"\nWarning: Could not find next page: {str(e)}")

    return None


async def scrape_category(
    page: Page,
    category_key: str,
    target_count: int,
    pbar: tqdm
) -> list[Product]:
    """Scrape products from a single category."""
    category = CATEGORIES[category_key]
    products = []
    current_url = category['url']
    page_num = 1
    max_pages = 10  # Safety limit

    while len(products) < target_count and page_num <= max_pages:
        try:
            pbar.set_description(f"Scraping {category['name']} (page {page_num})")

            # Navigate to search page
            await page.goto(current_url, wait_until='domcontentloaded', timeout=60000)

            # Wait for dynamic content to load (critical for SPAs)
            await asyncio.sleep(5)
            await random_delay(1.5, 2.5)

            # Try to wait for product selector
            try:
                await page.wait_for_selector('a[href*="/p/"]', timeout=10000)
            except PlaywrightTimeout:
                pbar.write(f"Warning: No product links found on {category['name']} page {page_num}")

            # Extract products from current page
            remaining = target_count - len(products)
            page_products = await extract_products_from_page(page, category['name'], remaining)

            if not page_products:
                print(f"\nNo products found on page {page_num} of {category['name']}")
                break

            products.extend(page_products)
            pbar.update(len(page_products))

            # Check if we need more products
            if len(products) >= target_count:
                break

            # Get next page
            next_url = await get_next_page_url(page)
            if not next_url or next_url == current_url:
                break

            current_url = next_url
            page_num += 1
            await random_delay()

        except PlaywrightTimeout:
            print(f"\nTimeout on page {page_num} of {category['name']}")
            break
        except Exception as e:
            print(f"\nError scraping {category['name']} page {page_num}: {str(e)}")
            break

    return products[:target_count]


async def scrape_nykaa(total_count: int, output_path: str) -> list[Product]:
    """Main scraping function."""
    all_products = []

    # Calculate products per category
    categories = list(CATEGORIES.keys())
    per_category = total_count // len(categories)
    remainder = total_count % len(categories)

    # Distribute products: [17, 17, 16] for 50 total
    category_counts = {}
    for i, cat in enumerate(categories):
        category_counts[cat] = per_category + (1 if i < remainder else 0)

    print(f"\nScraping {total_count} products from Nykaa.com")
    print(f"Distribution: {', '.join(f'{CATEGORIES[k]['name']}: {v}' for k, v in category_counts.items())}")
    print("-" * 50)

    async with async_playwright() as p:
        # Launch browser with stealth settings
        browser: Browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]
        )

        # Create context with realistic settings
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='en-IN',
            timezone_id='Asia/Kolkata',
            java_script_enabled=True,
            geolocation={"latitude": 19.0760, "longitude": 72.8777},  # Mumbai
            permissions=["geolocation"],
        )

        # Set extra HTTP headers to appear more like a real browser
        await context.set_extra_http_headers({
            "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        })

        # Add stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override chrome detection
            window.chrome = {
                runtime: {}
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-IN', 'en-US', 'en']
            });
        """)

        page = await context.new_page()

        # First visit homepage to establish cookies and session
        print("Visiting homepage to establish session...")
        try:
            await page.goto("https://www.nykaa.com", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)  # Let page fully initialize
            # Simulate human-like behavior
            await page.mouse.move(500, 300)
            await asyncio.sleep(0.5)
            await page.mouse.move(800, 400)
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Warning: Homepage visit failed: {e}")

        # Create progress bar
        with tqdm(total=total_count, desc="Scraping", unit="product") as pbar:
            for category_key, count in category_counts.items():
                if count > 0:
                    products = await scrape_category(page, category_key, count, pbar)
                    all_products.extend(products)
                    await random_delay(2, 4)  # Longer delay between categories

        await browser.close()

    return all_products


def save_to_csv(products: list[Product], output_path: str) -> None:
    """Save products to CSV file."""
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Write CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        if products:
            fieldnames = ['url', 'title', 'brand', 'category', 'price']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for product in products:
                writer.writerow(asdict(product))

    print(f"\nSaved {len(products)} products to {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Scrape beauty products from Nykaa.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scrape_nykaa.py --count 50 --out data/nykaa.csv
    python scrape_nykaa.py --count 100 --out products.csv
        """
    )
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=50,
        help='Total number of products to scrape (default: 50)'
    )
    parser.add_argument(
        '--out', '-o',
        type=str,
        default='data/nykaa.csv',
        help='Output CSV file path (default: data/nykaa.csv)'
    )

    args = parser.parse_args()

    if args.count < 1:
        print("Error: Count must be at least 1")
        sys.exit(1)

    if args.count < 3:
        print("Warning: Count less than 3 may not distribute evenly across categories")

    try:
        # Run the async scraper
        products = asyncio.run(scrape_nykaa(args.count, args.out))

        if products:
            save_to_csv(products, args.out)

            # Print summary
            print("\n" + "=" * 50)
            print("SCRAPING COMPLETE")
            print("=" * 50)
            print(f"Total products scraped: {len(products)}")

            # Category breakdown
            from collections import Counter
            category_counts = Counter(p.category for p in products)
            print("\nBy category:")
            for cat, count in category_counts.items():
                print(f"  - {cat}: {count}")

            # Sample output
            print("\nSample products:")
            for product in products[:3]:
                print(f"  - {product.title[:50]}... ({product.brand or 'Unknown brand'})")
        else:
            print("\nNo products were scraped. The website structure may have changed.")
            print("Try running with visible browser to debug: set headless=False in the code")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
