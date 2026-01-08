#!/usr/bin/env python3
"""
Purplle.com Beauty Products Scraper
Scrapes lipsticks, foundations, and serums from Purplle.com using Playwright.

Usage:
    python scrape_purplle.py --count 600 --out data/purplle.csv
"""

import asyncio
import argparse
import csv
import os
import random
import re
import sys
from dataclasses import dataclass, asdict
from typing import Optional
from urllib.parse import urljoin, quote

try:
    from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
except ImportError:
    print("Error: playwright not installed. Run: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm not installed. Run: pip install tqdm")
    sys.exit(1)


@dataclass
class Product:
    """Represents a scraped product."""
    url: str
    title: str
    brand: str
    category: str


# Category configuration with multiple search queries to get more products
# Purplle limits infinite scroll to ~50 products per search, so we use multiple queries
CATEGORIES = {
    "Lipstick": {
        "queries": [
            "lipstick",
            "matte lipstick",
            "liquid lipstick",
            "lip gloss",
            "lip color",
            "lip tint",
            "lip crayon",
            "lip stain",
            "lip balm tinted",
        ],
        "default_count": 200,
    },
    "Foundation": {
        "queries": [
            "foundation",
            "liquid foundation",
            "matte foundation",
            "bb cream",
            "cc cream",
            "concealer",
            "powder foundation",
            "compact powder",
            "cushion foundation",
            "tinted moisturizer",
            "color corrector",
            "primer face",
        ],
        "default_count": 200,
    },
    "Serum": {
        "queries": [
            "serum",
            "face serum",
            "vitamin c serum",
            "niacinamide serum",
            "hyaluronic acid",
            "retinol serum",
            "salicylic acid serum",
            "glycolic acid",
            "alpha arbutin",
            "skin brightening serum",
            "anti aging serum",
            "acne serum",
        ],
        "default_count": 200,
    },
}

BASE_URL = "https://www.purplle.com"


def extract_brand_from_title(title: str) -> str:
    """
    Extract brand name from product title.
    Common patterns:
    - "Brand Name Product Description"
    - "BRAND Product Description"

    Known brands are checked first, then first word(s) are used as fallback.
    """
    known_brands = [
        "Maybelline New York", "Maybelline", "NY Bae", "FACES CANADA", "Lakme",
        "MARS", "L'Oreal Paris", "L'Oreal", "Colorbar", "Revlon", "Sugar",
        "SUGAR", "Elle18", "Nykaa", "Plum", "Mamaearth", "The Derma Co",
        "DERMDOC", "Good Vibes", "WOW Skin Science", "Biotique", "Lotus",
        "Neutrogena", "Olay", "Garnier", "Nivea", "Himalaya", "Pond's",
        "Lakmé", "MAC", "Bobbi Brown", "Clinique", "Estee Lauder",
        "Forest Essentials", "Kama Ayurveda", "Minimalist", "Dot & Key",
        "mCaffeine", "Re'equil", "Cetaphil", "CeraVe", "Simple", "Alps Goodness",
        "Swiss Beauty", "Insight Cosmetics", "Blue Heaven", "Miss Claire",
        "PAC", "Renee", "Bella Voste", "Just Herbs", "Kiro", "Kay Beauty",
        "Pilgrim", "Deconstruct", "Foxtale", "Hyphen", "Fixderma"
    ]

    # Check for known brands (case-insensitive)
    title_lower = title.lower()
    for brand in known_brands:
        if title_lower.startswith(brand.lower()):
            return brand

    # Fallback: extract first meaningful word(s) before common product words
    product_keywords = [
        "lipstick", "foundation", "serum", "cream", "gel", "lotion",
        "moisturizer", "cleanser", "toner", "mask", "oil", "powder",
        "compact", "primer", "concealer", "highlighter", "blush",
        "matte", "liquid", "velvet", "glossy", "pro", "perfect"
    ]

    words = title.split()
    brand_words = []

    for word in words:
        word_clean = word.lower().strip(",-|()")
        if word_clean in [kw.lower() for kw in product_keywords]:
            break
        # Skip numeric or very short words at the start
        if len(word_clean) > 1 and not word_clean.isdigit():
            brand_words.append(word)
        if len(brand_words) >= 3:  # Max 3 words for brand
            break

    return " ".join(brand_words) if brand_words else "Unknown"


async def wait_random_delay(min_sec: float = 1.0, max_sec: float = 2.0):
    """Add random delay to avoid rate limiting."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def scroll_to_load_products(page: Page, target_count: int, pbar: tqdm, max_scrolls: int = 200) -> int:
    """
    Scroll down the page to load more products via infinite scroll.
    Returns the number of products found.
    """
    previous_count = 0
    no_change_count = 0

    for scroll_num in range(max_scrolls):
        # Count current products using the correct selector
        current_count = await page.evaluate('''() => {
            return document.querySelectorAll('a[href*="/product/"]').length;
        }''')

        if pbar and scroll_num % 10 == 0:
            pbar.write(f"  Scroll {scroll_num}: {current_count} products loaded...")

        if current_count >= target_count:
            return current_count

        if current_count == previous_count:
            no_change_count += 1
            if no_change_count >= 15:  # No new products after 15 scrolls
                pbar.write(f"  No more products loading after {current_count} items")
                break
        else:
            no_change_count = 0

        previous_count = current_count

        # Scroll to bottom of page
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.2)  # Wait for content to load

        # Additional scroll variations to trigger lazy loading
        if scroll_num % 3 == 0:
            await page.evaluate("window.scrollBy(0, -500)")
            await asyncio.sleep(0.3)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)

        # Check for "Load More" button and click if present
        try:
            load_more = page.locator('button:has-text("Load More"), a:has-text("Load More"), button:has-text("View More"), button:has-text("Show More")')
            if await load_more.count() > 0 and await load_more.first.is_visible():
                await load_more.first.click()
                pbar.write(f"  Clicked Load More button...")
                await asyncio.sleep(2.0)
        except Exception:
            pass

    return await page.evaluate('''() => {
        return document.querySelectorAll('a[href*="/product/"]').length;
    }''')


async def extract_products_from_page(page: Page, category_name: str) -> list[dict]:
    """Extract product data from the current page using JavaScript evaluation."""
    products_data = await page.evaluate('''() => {
        const products = [];
        const links = document.querySelectorAll('a[href*="/product/"]');

        links.forEach(link => {
            const href = link.getAttribute('href');
            if (!href || href.includes('javascript:')) return;

            // Get title from inner text
            let title = '';
            const textContent = link.innerText || '';

            // Clean up the text - take the first meaningful line
            const lines = textContent.split('\\n').filter(l => l.trim().length > 10);
            if (lines.length > 0) {
                // Skip lines that are just offers or badges
                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.match(/^(Free gift|Buy [0-9]|offers?$|[0-9]+ offers?$)/i) && trimmed.length > 15) {
                        title = trimmed;
                        break;
                    }
                }
            }

            // Also try to get from img alt attribute
            if (!title || title.length < 10) {
                const img = link.querySelector('img');
                if (img) {
                    let alt = img.getAttribute('alt') || '';
                    if (alt.startsWith('Buy ')) alt = alt.substring(4);
                    if (alt.endsWith('-Purplle')) alt = alt.slice(0, -8);
                    if (alt.length > 15) title = alt;
                }
            }

            if (title && title.length > 10 && href) {
                products.push({
                    url: href,
                    title: title.trim()
                });
            }
        });

        return products;
    }''')

    return products_data


async def scrape_single_query(
    page: Page,
    category_name: str,
    query: str,
    seen_urls: set,
    pbar: tqdm
) -> list[Product]:
    """
    Scrape products from a single search query.
    """
    products = []

    # Navigate to search page
    search_url = f"{BASE_URL}/search?q={quote(query)}"

    max_retries = 3
    for retry in range(max_retries):
        try:
            pbar.write(f"  Searching '{query}' (attempt {retry + 1})...")

            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for the page to fully load with products
            await asyncio.sleep(4)  # Initial wait for dynamic content

            # Wait for product links to appear
            try:
                await page.wait_for_selector('a[href*="/product/"]', timeout=15000)
                break
            except PlaywrightTimeout:
                if retry < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                else:
                    pbar.write(f"  No products for '{query}'")
                    return products

        except Exception as e:
            if retry < max_retries - 1:
                await asyncio.sleep(2)
            else:
                pbar.write(f"  Failed '{query}': {str(e)[:50]}")
                return products

    # Scroll to load more products (but not too many - we'll get more from other queries)
    await scroll_to_load_products(page, 60, pbar, max_scrolls=30)

    # Extra wait after scrolling
    await asyncio.sleep(1)

    # Extract product information using JavaScript
    products_data = await extract_products_from_page(page, category_name)

    new_count = 0
    for item in products_data:
        url = item.get('url', '')
        title = item.get('title', '')

        if not url or not title or url in seen_urls:
            continue

        seen_urls.add(url)

        # Clean title
        title = re.sub(r'\s+', ' ', title).strip()

        # Skip if title is too short or looks like a badge
        if len(title) < 15:
            continue

        # Extract brand
        brand = extract_brand_from_title(title)

        # Build full URL
        full_url = urljoin(BASE_URL, url)

        product = Product(
            url=full_url,
            title=title,
            brand=brand,
            category=category_name
        )
        products.append(product)
        new_count += 1
        pbar.update(1)

    pbar.write(f"  Found {new_count} new products from '{query}'")
    await wait_random_delay(1.0, 2.0)

    return products


async def scrape_category(
    page: Page,
    category_name: str,
    queries: list[str],
    target_count: int,
    pbar: tqdm
) -> list[Product]:
    """
    Scrape products from a category using multiple search queries.
    """
    all_products = []
    seen_urls = set()

    pbar.write(f"Scraping {category_name} ({len(queries)} queries, target: {target_count})...")

    for query in queries:
        if len(all_products) >= target_count:
            break

        products = await scrape_single_query(
            page=page,
            category_name=category_name,
            query=query,
            seen_urls=seen_urls,
            pbar=pbar
        )

        all_products.extend(products)

    pbar.write(f"Total for {category_name}: {len(all_products)} products")
    return all_products


async def apply_stealth_scripts(page: Page):
    """Apply stealth scripts to avoid bot detection."""
    # Override navigator.webdriver
    await page.add_init_script("""
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
            get: () => ['en-US', 'en']
        });
    """)


async def scrape_all_categories(
    total_count: int,
    headless: bool = True,
    pbar: Optional[tqdm] = None
) -> list[Product]:
    """
    Scrape products from all categories.
    """
    all_products = []

    # Calculate per-category count
    per_category = total_count // len(CATEGORIES)

    async with async_playwright() as p:
        # Launch browser with stealth settings
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized",
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            java_script_enabled=True,
            locale="en-US",
            timezone_id="Asia/Kolkata",
            geolocation={"latitude": 19.0760, "longitude": 72.8777},  # Mumbai
            permissions=["geolocation"],
        )

        # Set extra HTTP headers to appear more like a real browser
        await context.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
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

        page = await context.new_page()

        # Apply stealth scripts
        await apply_stealth_scripts(page)

        try:
            # First, visit the homepage to establish cookies and session
            if pbar:
                pbar.write("Visiting homepage to establish session...")
            await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)  # Let the page fully initialize

            # Simulate some human-like behavior
            await page.mouse.move(500, 300)
            await asyncio.sleep(0.5)
            await page.mouse.move(800, 400)
            await asyncio.sleep(1)
            for category_name, config in CATEGORIES.items():
                if pbar:
                    pbar.set_description(f"Scraping {category_name}")

                products = await scrape_category(
                    page=page,
                    category_name=category_name,
                    queries=config["queries"],
                    target_count=per_category,
                    pbar=pbar
                )

                all_products.extend(products)

                # Delay between categories
                await wait_random_delay(2.0, 3.0)

        finally:
            await browser.close()

    return all_products


def save_to_csv(products: list[Product], output_path: str):
    """Save products to CSV file."""
    # Ensure directory exists
    dir_path = os.path.dirname(os.path.abspath(output_path))
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "title", "brand", "category"])
        writer.writeheader()
        for product in products:
            writer.writerow(asdict(product))

    print(f"\nSaved {len(products)} products to {output_path}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape beauty products from Purplle.com"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=600,
        help="Total number of products to scrape (default: 600)"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="data/purplle.csv",
        help="Output CSV file path (default: data/purplle.csv)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible window"
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    headless = not args.no_headless

    print(f"Purplle.com Product Scraper")
    print(f"=" * 40)
    print(f"Target count: {args.count} products")
    print(f"Output file: {args.out}")
    print(f"Headless mode: {headless}")
    print(f"Categories: {', '.join(CATEGORIES.keys())}")
    print(f"=" * 40)
    print()

    # Create progress bar
    with tqdm(total=args.count, desc="Scraping products", unit="product") as pbar:
        products = await scrape_all_categories(
            total_count=args.count,
            headless=headless,
            pbar=pbar
        )

    # Remove duplicates based on URL
    seen_urls = set()
    unique_products = []
    for p in products:
        if p.url not in seen_urls:
            seen_urls.add(p.url)
            unique_products.append(p)

    print(f"\nScraped {len(unique_products)} unique products")

    # Print category breakdown
    category_counts = {}
    for p in unique_products:
        category_counts[p.category] = category_counts.get(p.category, 0) + 1

    print("\nCategory breakdown:")
    for cat, count in category_counts.items():
        print(f"  - {cat}: {count} products")

    # Save to CSV
    save_to_csv(unique_products, args.out)

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
