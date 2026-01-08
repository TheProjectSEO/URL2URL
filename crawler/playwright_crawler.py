#!/usr/bin/env python3
"""
Playwright MCP-based Unblockable E-commerce Crawler

This crawler uses Playwright MCP tools to navigate and extract product data
from e-commerce sites with anti-blocking features.

The MCP tools provide:
- browser_navigate - Navigate to URLs
- browser_snapshot - Get page accessibility tree (better than screenshots)
- browser_click - Click elements
- browser_type - Type in fields
- browser_evaluate - Run JavaScript to extract data

Usage:
    from playwright_crawler import ProductCrawler, SITE_CONFIGS

    # Initialize with MCP invoke function
    crawler = ProductCrawler(mcp_invoke=your_mcp_invoke_function)
    products = await crawler.crawl_category(SITE_CONFIGS['nykaa'], 'lipstick', max_products=100)

Author: Aditya Aman
Created: 2026-01-07
"""

import asyncio
import csv
import json
import logging
import random
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse, quote_plus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('crawler.log')
    ]
)
logger = logging.getLogger('playwright_mcp_crawler')


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class Product:
    """Product data model for crawled products."""
    url: str
    title: str
    brand: str
    category: str
    price: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        if isinstance(other, Product):
            return self.url == other.url
        return False


@dataclass
class SiteConfig:
    """Configuration for a specific e-commerce site."""
    name: str
    base_url: str
    search_url_template: str  # Use {query} as placeholder

    # Hints for product extraction from accessibility snapshots
    product_container_hint: str  # Accessibility hint for product containers
    title_hint: str
    brand_hint: str
    price_hint: str
    link_hint: str

    # Pagination configuration
    next_page_hint: str
    page_param: str  # URL parameter for pagination

    # Optional: Custom extraction patterns
    price_regex: str = r'[\d,]+(?:\.\d{2})?'

    # Rate limiting (anti-blocking)
    min_delay: float = 1.0
    max_delay: float = 3.0

    # Retry configuration
    max_retries: int = 3
    retry_backoff_base: float = 2.0

    # Known brands for this site (optional)
    known_brands: List[str] = field(default_factory=list)

    # Search queries per category (optional - expands search coverage)
    queries_per_category: Dict[str, List[str]] = field(default_factory=dict)


# =============================================================================
# Pre-configured Site Configurations
# =============================================================================

SITE_CONFIGS: Dict[str, SiteConfig] = {
    'nykaa': SiteConfig(
        name='Nykaa',
        base_url='https://www.nykaa.com',
        search_url_template='https://www.nykaa.com/search/result/?q={query}&root=search&searchType=Manual',
        product_container_hint='product',
        title_hint='name',
        brand_hint='brand',
        price_hint='price',
        link_hint='link',
        next_page_hint='next',
        page_param='page_no',
        min_delay=1.5,
        max_delay=3.5,
        known_brands=[
            "Maybelline New York", "Maybelline", "NY Bae", "FACES CANADA", "Lakme",
            "MARS", "L'Oreal Paris", "L'Oreal", "Colorbar", "Revlon", "Sugar",
            "SUGAR", "Elle18", "Nykaa", "Plum", "Mamaearth", "The Derma Co",
            "Good Vibes", "WOW Skin Science", "Biotique", "Lotus", "Neutrogena",
            "Olay", "Garnier", "Nivea", "Himalaya", "Pond's", "Lakmé", "MAC",
            "Minimalist", "Dot & Key", "mCaffeine", "Re'equil", "Swiss Beauty",
        ],
        queries_per_category={
            'lipstick': ['lipstick', 'matte lipstick', 'liquid lipstick', 'lip gloss', 'lip tint'],
            'foundation': ['foundation', 'bb cream', 'cc cream', 'concealer', 'primer'],
            'serum': ['serum', 'face serum', 'vitamin c serum', 'hyaluronic acid', 'niacinamide'],
            'mascara': ['mascara', 'eye mascara', 'waterproof mascara'],
            'eyeliner': ['eyeliner', 'kajal', 'kohl'],
        },
    ),
    'purplle': SiteConfig(
        name='Purplle',
        base_url='https://www.purplle.com',
        search_url_template='https://www.purplle.com/search?q={query}',
        product_container_hint='product',
        title_hint='title',
        brand_hint='brand',
        price_hint='price',
        link_hint='link',
        next_page_hint='next',
        page_param='page',
        min_delay=1.5,
        max_delay=3.0,
        known_brands=[
            "Maybelline", "Lakme", "L'Oreal", "Colorbar", "Revlon", "Sugar",
            "Elle18", "Plum", "Mamaearth", "Biotique", "Lotus", "Neutrogena",
            "Garnier", "Nivea", "Himalaya", "Pond's", "Swiss Beauty", "Insight",
            "Blue Heaven", "Renee", "Pilgrim", "mCaffeine", "WOW",
        ],
        queries_per_category={
            'lipstick': ['lipstick', 'matte lipstick', 'liquid lipstick', 'lip gloss', 'lip tint'],
            'foundation': ['foundation', 'bb cream', 'cc cream', 'concealer', 'primer'],
            'serum': ['serum', 'face serum', 'vitamin c serum', 'niacinamide', 'retinol'],
        },
    ),
    'generic': SiteConfig(
        name='Generic E-commerce',
        base_url='',  # Set dynamically
        search_url_template='{base_url}/search?q={query}',
        product_container_hint='product',
        title_hint='title',
        brand_hint='brand',
        price_hint='price',
        link_hint='link',
        next_page_hint='next',
        page_param='page',
        min_delay=2.0,
        max_delay=4.0,
    ),
}


# =============================================================================
# MCP Client Wrapper
# =============================================================================

class MCPPlaywrightClient:
    """
    Client wrapper for Playwright MCP tools.

    This class provides a Pythonic interface to call MCP tools:
    - mcp__playwright__browser_navigate
    - mcp__playwright__browser_snapshot
    - mcp__playwright__browser_click
    - mcp__playwright__browser_type
    - mcp__playwright__browser_evaluate
    - mcp__playwright__browser_wait_for
    """

    def __init__(self, mcp_invoke: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None):
        """
        Initialize the MCP client.

        Args:
            mcp_invoke: Async callable to invoke MCP tools.
                       Signature: async def invoke(tool_name: str, params: dict) -> Any
        """
        self._mcp_invoke = mcp_invoke
        self._last_snapshot: Optional[str] = None
        self._current_url: Optional[str] = None

    async def _invoke(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Internal method to invoke MCP tools."""
        if self._mcp_invoke:
            try:
                result = await self._mcp_invoke(tool_name, params)
                return result
            except Exception as e:
                logger.error(f"MCP tool invocation failed: {tool_name} - {e}")
                raise
        else:
            logger.warning(f"No MCP invoke function provided, mock mode for: {tool_name}")
            return None

    async def navigate(self, url: str) -> Dict[str, Any]:
        """
        Navigate to a URL using mcp__playwright__browser_navigate.

        Args:
            url: URL to navigate to

        Returns:
            Navigation result
        """
        logger.info(f"Navigating to: {url}")
        self._current_url = url

        result = await self._invoke('mcp__playwright__browser_navigate', {'url': url})
        return result or {'success': True, 'url': url}

    async def snapshot(self, save_to_file: Optional[str] = None) -> str:
        """
        Get page accessibility snapshot using mcp__playwright__browser_snapshot.

        The snapshot provides a text representation of the page's accessibility tree,
        which is more reliable for data extraction than screenshots.

        Args:
            save_to_file: Optional filename to save snapshot

        Returns:
            Snapshot text content
        """
        logger.debug("Taking page snapshot")

        params = {}
        if save_to_file:
            params['filename'] = save_to_file

        result = await self._invoke('mcp__playwright__browser_snapshot', params)

        if result:
            self._last_snapshot = result if isinstance(result, str) else str(result)
        else:
            self._last_snapshot = ""

        return self._last_snapshot

    async def click(self, element: str, ref: str) -> Dict[str, Any]:
        """
        Click an element using mcp__playwright__browser_click.

        Args:
            element: Human-readable element description
            ref: Exact element reference from snapshot (e.g., "S1E2")

        Returns:
            Click result
        """
        logger.debug(f"Clicking element: {element} (ref: {ref})")

        result = await self._invoke('mcp__playwright__browser_click', {
            'element': element,
            'ref': ref
        })
        return result or {'success': True}

    async def type_text(
        self,
        element: str,
        ref: str,
        text: str,
        submit: bool = False,
        slowly: bool = False
    ) -> Dict[str, Any]:
        """
        Type text into an element using mcp__playwright__browser_type.

        Args:
            element: Human-readable element description
            ref: Exact element reference from snapshot
            text: Text to type
            submit: Whether to press Enter after typing
            slowly: Whether to type character by character (more human-like)

        Returns:
            Type result
        """
        logger.debug(f"Typing into element: {element}")

        result = await self._invoke('mcp__playwright__browser_type', {
            'element': element,
            'ref': ref,
            'text': text,
            'submit': submit,
            'slowly': slowly
        })
        return result or {'success': True}

    async def evaluate(
        self,
        js_code: str,
        element: Optional[str] = None,
        ref: Optional[str] = None
    ) -> Any:
        """
        Execute JavaScript using mcp__playwright__browser_evaluate.

        Args:
            js_code: JavaScript function to execute
            element: Optional element description (if running on specific element)
            ref: Optional element reference

        Returns:
            JavaScript execution result
        """
        logger.debug("Evaluating JavaScript")

        params: Dict[str, Any] = {'function': js_code}
        if element and ref:
            params['element'] = element
            params['ref'] = ref

        return await self._invoke('mcp__playwright__browser_evaluate', params)

    async def wait_for(
        self,
        text: Optional[str] = None,
        text_gone: Optional[str] = None,
        time_seconds: Optional[float] = None
    ) -> None:
        """
        Wait for text to appear/disappear or for specified time.

        Args:
            text: Text to wait for to appear
            text_gone: Text to wait for to disappear
            time_seconds: Time to wait in seconds
        """
        params = {}
        if text:
            params['text'] = text
        if text_gone:
            params['textGone'] = text_gone
        if time_seconds:
            params['time'] = time_seconds

        await self._invoke('mcp__playwright__browser_wait_for', params)

    async def scroll_page(self, direction: str = 'down', amount: int = 500) -> None:
        """
        Scroll the page in a human-like manner.

        Args:
            direction: 'down' or 'up'
            amount: Base scroll amount in pixels (will be randomized)
        """
        # Add randomness for human-like behavior
        actual_amount = amount + random.randint(-100, 200)

        scroll_js = f"""
        () => {{
            const scrollAmount = {actual_amount};
            window.scrollBy({{
                top: {'' if direction == 'down' else '-'}scrollAmount,
                behavior: 'smooth'
            }});
            return window.scrollY;
        }}
        """
        await self.evaluate(scroll_js)

    async def wait_for_load(self, timeout_ms: int = 10000) -> bool:
        """
        Wait for page to fully load.

        Args:
            timeout_ms: Maximum wait time in milliseconds

        Returns:
            True if page loaded, False if timeout
        """
        wait_js = f"""
        () => {{
            return new Promise((resolve) => {{
                if (document.readyState === 'complete') {{
                    resolve(true);
                }} else {{
                    window.addEventListener('load', () => resolve(true));
                    setTimeout(() => resolve(false), {timeout_ms});
                }}
            }});
        }}
        """
        result = await self.evaluate(wait_js)
        return bool(result)

    async def extract_products_js(self) -> List[Dict[str, str]]:
        """
        Extract product data using JavaScript evaluation.

        This method tries multiple selector strategies to find products
        on various e-commerce sites.

        Returns:
            List of product dictionaries with url, title, brand, price
        """
        extract_js = """
        () => {
            const products = [];

            // Common product container selectors (ordered by specificity)
            const containerSelectors = [
                '[data-product-id]',
                '[data-productid]',
                '.product-card',
                '.product-item',
                '.product-box',
                '.plp-card',
                '.search-product',
                '[class*="ProductCard"]',
                '[class*="product-card"]',
                '[class*="productCard"]',
                'article[class*="product"]',
                'li[class*="product"]',
                'div[class*="product"][class*="card"]',
            ];

            let productElements = [];

            // Try each selector until we find products
            for (const selector of containerSelectors) {
                const elements = document.querySelectorAll(selector);
                if (elements.length > 0) {
                    productElements = Array.from(elements);
                    console.log(`Found ${elements.length} products with selector: ${selector}`);
                    break;
                }
            }

            // Fallback: find links that look like product URLs
            if (productElements.length === 0) {
                const productLinks = document.querySelectorAll(
                    'a[href*="/p/"], a[href*="/product/"], a[href*="/dp/"], a[href*="/buy/"]'
                );
                productElements = Array.from(productLinks).map(link => {
                    // Get the containing element
                    return link.closest('div, article, li, section') || link;
                }).filter((el, idx, arr) => arr.indexOf(el) === idx); // Dedupe
            }

            productElements.forEach(el => {
                try {
                    // Extract URL
                    const linkEl = el.querySelector('a[href]') || el.closest('a') || el;
                    let url = '';
                    if (linkEl && linkEl.href) {
                        url = linkEl.href;
                    } else if (linkEl && linkEl.getAttribute('href')) {
                        url = linkEl.getAttribute('href');
                    }

                    if (!url || url === '#' || url === window.location.href) return;

                    // Extract title (try multiple strategies)
                    let title = '';
                    const titleSelectors = [
                        '[class*="title"]', '[class*="Title"]',
                        '[class*="name"]', '[class*="Name"]',
                        '[class*="product-name"]', '[class*="productName"]',
                        'h2', 'h3', 'h4',
                        '[itemprop="name"]',
                    ];

                    for (const sel of titleSelectors) {
                        const titleEl = el.querySelector(sel);
                        if (titleEl && titleEl.textContent.trim().length > 5) {
                            title = titleEl.textContent.trim();
                            break;
                        }
                    }

                    // Fallback: try img alt text
                    if (!title || title.length < 5) {
                        const img = el.querySelector('img');
                        if (img && img.alt && img.alt.length > 5) {
                            title = img.alt.replace(/^Buy /, '').replace(/-Purplle$|-Nykaa$/i, '').trim();
                        }
                    }

                    // Fallback: link title attribute
                    if (!title || title.length < 5) {
                        if (linkEl && linkEl.title) {
                            title = linkEl.title;
                        }
                    }

                    // Extract brand
                    let brand = '';
                    const brandSelectors = [
                        '[class*="brand"]', '[class*="Brand"]',
                        '[itemprop="brand"]',
                        '[class*="manufacturer"]',
                    ];

                    for (const sel of brandSelectors) {
                        const brandEl = el.querySelector(sel);
                        if (brandEl && brandEl.textContent.trim()) {
                            brand = brandEl.textContent.trim();
                            break;
                        }
                    }

                    // Extract price
                    let price = '';
                    const priceSelectors = [
                        '[class*="price"]', '[class*="Price"]',
                        '[class*="amount"]', '[class*="Amount"]',
                        '[itemprop="price"]',
                        '[class*="cost"]',
                    ];

                    for (const sel of priceSelectors) {
                        const priceEl = el.querySelector(sel);
                        if (priceEl) {
                            const priceText = priceEl.textContent.trim();
                            // Extract numeric price
                            const match = priceText.match(/[\\u20b9$\\u00a3\\u20ac]?\\s*([\\d,]+(?:\\.\\d{2})?)/);
                            if (match) {
                                price = match[0];
                                break;
                            }
                        }
                    }

                    // Only add if we have URL and title
                    if (url && title && title.length > 5) {
                        products.push({
                            url: url,
                            title: title.substring(0, 500), // Limit title length
                            brand: brand.substring(0, 100),
                            price: price.substring(0, 50)
                        });
                    }
                } catch (e) {
                    console.error('Error extracting product:', e);
                }
            });

            // Deduplicate by URL
            const seen = new Set();
            return products.filter(p => {
                if (seen.has(p.url)) return false;
                seen.add(p.url);
                return true;
            });
        }
        """
        result = await self.evaluate(extract_js)
        return result if result else []

    async def get_page_info(self) -> Dict[str, Any]:
        """Get current page information."""
        info_js = """
        () => {
            return {
                url: window.location.href,
                title: document.title,
                scrollHeight: document.body.scrollHeight,
                scrollY: window.scrollY,
                productCount: document.querySelectorAll('[class*="product"]').length,
            };
        }
        """
        return await self.evaluate(info_js) or {}


# =============================================================================
# Progress Tracker
# =============================================================================

class ProgressTracker:
    """Track and persist crawling progress in real-time."""

    def __init__(self, progress_file: Path):
        """
        Initialize progress tracker.

        Args:
            progress_file: Path to JSON file for progress persistence
        """
        self.progress_file = Path(progress_file)
        self.start_time = time.time()
        self.products_found = 0
        self.pages_crawled = 0
        self.errors = 0
        self.current_query = ""
        self._rate_samples: List[float] = []

    def update(
        self,
        new_products: int,
        current_page: int,
        total_pages: Optional[int] = None,
        current_query: str = ""
    ) -> None:
        """
        Update progress tracking after batch.

        Args:
            new_products: Number of new products found
            current_page: Current page number
            total_pages: Total pages if known
            current_query: Current search query
        """
        self.products_found += new_products
        self.pages_crawled = current_page
        self.current_query = current_query

        # Calculate rate
        elapsed_minutes = (time.time() - self.start_time) / 60
        if elapsed_minutes > 0:
            rate = self.products_found / elapsed_minutes
            self._rate_samples.append(rate)
            # Keep only last 10 samples for moving average
            self._rate_samples = self._rate_samples[-10:]

        self._save_progress(total_pages)

    def record_error(self, error_message: str = "") -> None:
        """Record an error occurrence."""
        self.errors += 1
        logger.error(f"Crawler error: {error_message}")
        self._save_progress()

    def _save_progress(self, total_pages: Optional[int] = None) -> None:
        """Save progress to JSON file."""
        elapsed_seconds = time.time() - self.start_time
        rate_per_minute = (
            sum(self._rate_samples) / len(self._rate_samples)
            if self._rate_samples else 0
        )

        # Estimate remaining products
        estimated_remaining = None
        if total_pages and self.pages_crawled > 0:
            avg_products_per_page = self.products_found / self.pages_crawled
            remaining_pages = total_pages - self.pages_crawled
            estimated_remaining = int(avg_products_per_page * remaining_pages)

        progress_data = {
            'products_found': self.products_found,
            'current_page': self.pages_crawled,
            'total_pages': total_pages,
            'estimated_remaining': estimated_remaining,
            'rate_per_minute': round(rate_per_minute, 2),
            'errors': self.errors,
            'elapsed_seconds': round(elapsed_seconds, 2),
            'current_query': self.current_query,
            'last_updated': datetime.now().isoformat()
        }

        try:
            with open(self.progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")

        logger.info(
            f"Progress: {self.products_found} products, page {self.pages_crawled}, "
            f"rate: {rate_per_minute:.1f}/min"
        )

    def get_summary(self) -> Dict[str, Any]:
        """Get progress summary."""
        elapsed = time.time() - self.start_time
        return {
            'products_found': self.products_found,
            'pages_crawled': self.pages_crawled,
            'errors': self.errors,
            'elapsed_seconds': elapsed,
            'rate_per_minute': self.products_found / (elapsed / 60) if elapsed > 0 else 0
        }


# =============================================================================
# Main Product Crawler
# =============================================================================

class ProductCrawler:
    """
    Main crawler class for extracting product data from e-commerce sites.

    Uses Playwright MCP tools for browser automation with anti-blocking features:
    - Random delays between requests
    - Human-like scrolling behavior
    - Session persistence (cookies maintained)
    - Retry logic with exponential backoff
    """

    def __init__(
        self,
        output_dir: Union[str, Path] = './output',
        mcp_invoke: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
    ):
        """
        Initialize the crawler.

        Args:
            output_dir: Directory to save output files (CSV, progress JSON)
            mcp_invoke: Async callable to invoke MCP tools
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.client = MCPPlaywrightClient(mcp_invoke)
        self.products: Dict[str, Product] = {}  # URL -> Product for deduplication
        self.progress_tracker: Optional[ProgressTracker] = None

        logger.info(f"ProductCrawler initialized. Output dir: {self.output_dir}")

    async def crawl_category(
        self,
        site_config: SiteConfig,
        category: str,
        max_products: int = 100,
        start_page: int = 1
    ) -> List[Product]:
        """
        Crawl a category/search page and extract products.

        Args:
            site_config: Site configuration (use SITE_CONFIGS dict)
            category: Category name or search term
            max_products: Maximum products to collect
            start_page: Starting page number (for resumption)

        Returns:
            List of extracted Product objects
        """
        logger.info(
            f"Starting crawl: {site_config.name} - '{category}' "
            f"(max: {max_products}, start: {start_page})"
        )

        # Initialize progress tracking
        safe_category = re.sub(r'[^\w\-]', '_', category)
        progress_file = self.output_dir / f'progress_{site_config.name.lower()}_{safe_category}.json'
        self.progress_tracker = ProgressTracker(progress_file)

        # Get queries for this category (expand search coverage)
        queries = site_config.queries_per_category.get(
            category.lower(),
            [category]  # Default to category name itself
        )

        total_collected = 0
        current_page = start_page
        consecutive_errors = 0

        for query in queries:
            if total_collected >= max_products:
                break

            logger.info(f"Searching for: '{query}'")

            # Build search URL
            search_url = site_config.search_url_template.format(
                query=quote_plus(query),
                base_url=site_config.base_url
            )

            # Reset page counter for new query
            current_page = start_page

            while total_collected < max_products:
                try:
                    # Add page parameter if not first page
                    page_url = search_url
                    if current_page > 1:
                        separator = '&' if '?' in search_url else '?'
                        page_url = f"{search_url}{separator}{site_config.page_param}={current_page}"

                    # Navigate with retry logic
                    success = await self._navigate_with_retry(page_url, site_config)
                    if not success:
                        logger.warning(f"Failed to load page {current_page}, trying next query")
                        break

                    # Human-like delay and scrolling (anti-blocking)
                    await self._human_like_behavior(site_config)

                    # Extract products from current page
                    page_products = await self.extract_products(site_config, category)

                    if not page_products:
                        logger.warning(f"No products found on page {current_page}")
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            logger.warning("Too many consecutive empty pages, trying next query")
                            break
                    else:
                        consecutive_errors = 0
                        total_collected = len(self.products)

                    # Update progress
                    self.progress_tracker.update(
                        new_products=len(page_products),
                        current_page=current_page,
                        total_pages=None,
                        current_query=query
                    )

                    # Save incremental progress to CSV
                    output_file = self.output_dir / f'products_{site_config.name.lower()}_{safe_category}.csv'
                    await self.save_progress(list(self.products.values()), output_file)

                    # Check for next page
                    has_next = await self.handle_pagination(site_config)
                    if not has_next:
                        logger.info(f"No more pages for query '{query}'")
                        break

                    current_page += 1

                    # Rate limiting delay (anti-blocking)
                    delay = random.uniform(site_config.min_delay, site_config.max_delay)
                    logger.debug(f"Waiting {delay:.2f}s before next page")
                    await asyncio.sleep(delay)

                except Exception as e:
                    logger.error(f"Error on page {current_page}: {e}")
                    self.progress_tracker.record_error(str(e))
                    consecutive_errors += 1

                    if consecutive_errors >= site_config.max_retries:
                        logger.error("Max consecutive errors reached, trying next query")
                        break

                    # Exponential backoff
                    backoff = site_config.retry_backoff_base ** consecutive_errors
                    logger.info(f"Backing off for {backoff:.1f}s")
                    await asyncio.sleep(backoff)

            # Delay between queries
            await asyncio.sleep(random.uniform(2.0, 4.0))

        products_list = list(self.products.values())
        logger.info(f"Crawl complete: {len(products_list)} products collected")

        return products_list

    async def extract_products(
        self,
        site_config: SiteConfig,
        category: str
    ) -> List[Product]:
        """
        Extract products from current page.

        Uses two methods:
        1. JavaScript evaluation (primary - more reliable)
        2. Accessibility snapshot parsing (fallback)

        Args:
            site_config: Site configuration
            category: Category being crawled

        Returns:
            List of newly extracted products (not seen before)
        """
        new_products: List[Product] = []

        # Method 1: JavaScript extraction (preferred)
        try:
            js_products = await self.client.extract_products_js()

            for p in js_products:
                url = p.get('url', '')

                # Skip if already seen
                if not url or url in self.products:
                    continue

                # Normalize URL
                if not url.startswith('http'):
                    url = urljoin(site_config.base_url, url)

                # Skip non-product URLs
                if not self._is_product_url(url):
                    continue

                # Clean and validate data
                title = self._clean_text(p.get('title', ''))
                brand = self._clean_text(p.get('brand', ''))
                price = self._extract_price(p.get('price', ''), site_config.price_regex)

                # Try to extract brand from title if not found
                if not brand and title:
                    brand = self._extract_brand_from_title(title, site_config.known_brands)

                if url and title:
                    product = Product(
                        url=url,
                        title=title,
                        brand=brand,
                        category=category,
                        price=price
                    )
                    self.products[url] = product
                    new_products.append(product)

        except Exception as e:
            logger.warning(f"JavaScript extraction failed: {e}")

        # Method 2: Snapshot parsing (fallback if JS extraction found nothing)
        if not new_products:
            try:
                snapshot = await self.client.snapshot()
                snapshot_products = self._parse_snapshot(snapshot, site_config, category)

                for product in snapshot_products:
                    if product.url not in self.products:
                        self.products[product.url] = product
                        new_products.append(product)

            except Exception as e:
                logger.warning(f"Snapshot extraction failed: {e}")

        logger.info(f"Extracted {len(new_products)} new products from page")
        return new_products

    def _parse_snapshot(
        self,
        snapshot: str,
        config: SiteConfig,
        category: str
    ) -> List[Product]:
        """
        Parse products from accessibility snapshot.

        The snapshot is a text representation of the page's accessibility tree.
        Format typically includes lines like:
        - link "Product Name" [ref1]
        - text "Brand Name"
        - text "$99.99"

        Args:
            snapshot: Page accessibility snapshot text
            config: Site configuration
            category: Category being crawled

        Returns:
            List of extracted products
        """
        products = []

        if not snapshot:
            return products

        lines = snapshot.split('\n')
        current_product: Dict[str, str] = {}

        for line in lines:
            line = line.strip()

            # Look for links (potential product URLs)
            link_match = re.search(r'link\s+"([^"]+)"\s+\[([^\]]+)\]', line, re.IGNORECASE)
            if link_match:
                # Save previous product if valid
                if current_product.get('title'):
                    url = current_product.get('url', '')
                    if url and self._is_product_url(url):
                        products.append(Product(
                            url=url,
                            title=current_product.get('title', ''),
                            brand=current_product.get('brand', ''),
                            category=category,
                            price=current_product.get('price', '')
                        ))

                # Start new product
                title = link_match.group(1)
                current_product = {
                    'title': title,
                    'ref': link_match.group(2),
                    'brand': self._extract_brand_from_title(title, config.known_brands)
                }
                continue

            # Look for URLs in the line
            url_match = re.search(r'href[=:]\s*["\']?([^"\'>\s]+)', line, re.IGNORECASE)
            if url_match and current_product:
                url = url_match.group(1)
                if self._is_product_url(url):
                    if not url.startswith('http'):
                        url = urljoin(config.base_url, url)
                    current_product['url'] = url

            # Look for price patterns
            price_match = re.search(r'[\u20b9$\u00a3\u20ac]\s*[\d,]+(?:\.\d{2})?', line)
            if price_match and current_product:
                current_product['price'] = price_match.group(0)

        # Don't forget the last product
        if current_product.get('title') and current_product.get('url'):
            products.append(Product(
                url=current_product['url'],
                title=current_product.get('title', ''),
                brand=current_product.get('brand', ''),
                category=category,
                price=current_product.get('price', '')
            ))

        return products

    async def handle_pagination(self, site_config: SiteConfig) -> bool:
        """
        Check if there's a next page available.

        Args:
            site_config: Site configuration

        Returns:
            True if next page exists, False otherwise
        """
        check_next_js = """
        () => {
            const nextSelectors = [
                'a[rel="next"]',
                'button[aria-label*="next" i]:not([disabled])',
                'a[aria-label*="next" i]',
                '[class*="next" i]:not([disabled]):not([class*="disabled"])',
                '[class*="pagination"] a:last-child',
                'a[class*="page"]:last-child',
                'button[class*="next" i]:not([disabled])',
            ];

            for (const selector of nextSelectors) {
                try {
                    const el = document.querySelector(selector);
                    if (el && !el.disabled && el.offsetParent !== null) {
                        // Check if element is visible
                        const style = window.getComputedStyle(el);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            return {
                                found: true,
                                selector: selector,
                                href: el.href || null,
                                text: el.textContent.trim().substring(0, 50)
                            };
                        }
                    }
                } catch (e) {
                    // Selector might be invalid, continue
                }
            }

            return { found: false };
        }
        """

        try:
            result = await self.client.evaluate(check_next_js)

            if result and result.get('found'):
                logger.debug(f"Next page found: {result.get('href', 'button')}")
                return True
        except Exception as e:
            logger.warning(f"Pagination check failed: {e}")

        return False

    async def save_progress(
        self,
        products: List[Product],
        output_file: Path
    ) -> None:
        """
        Save products to CSV file with deduplication.

        Args:
            products: List of products to save
            output_file: Output CSV file path
        """
        if not products:
            return

        fieldnames = ['url', 'title', 'brand', 'category', 'price', 'timestamp']

        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                seen_urls: Set[str] = set()
                for product in products:
                    if product.url not in seen_urls:
                        writer.writerow(product.to_dict())
                        seen_urls.add(product.url)

            logger.debug(f"Saved {len(seen_urls)} products to {output_file}")

        except Exception as e:
            logger.error(f"Failed to save products: {e}")

    async def _navigate_with_retry(
        self,
        url: str,
        config: SiteConfig
    ) -> bool:
        """
        Navigate to URL with retry logic and exponential backoff.

        Args:
            url: URL to navigate to
            config: Site configuration

        Returns:
            True if navigation successful, False otherwise
        """
        for attempt in range(config.max_retries):
            try:
                await self.client.navigate(url)

                # Wait for page to load
                await self.client.wait_for(time_seconds=2)
                loaded = await self.client.wait_for_load(timeout_ms=15000)

                if loaded:
                    return True

                logger.warning(f"Page did not fully load on attempt {attempt + 1}")

            except Exception as e:
                logger.warning(f"Navigation attempt {attempt + 1} failed: {e}")

            if attempt < config.max_retries - 1:
                backoff = config.retry_backoff_base ** (attempt + 1)
                await asyncio.sleep(backoff)

        return False

    async def _human_like_behavior(self, config: SiteConfig) -> None:
        """
        Simulate human-like browsing behavior (anti-blocking).

        - Random initial delay
        - Gradual scrolling
        - Mouse movement simulation
        - Occasional scroll back up

        Args:
            config: Site configuration
        """
        # Random initial delay
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # Scroll down gradually to load lazy-loaded content
        scroll_steps = random.randint(3, 6)
        for _ in range(scroll_steps):
            await self.client.scroll_page('down', random.randint(300, 700))
            await asyncio.sleep(random.uniform(0.3, 0.8))

        # Sometimes scroll back up a bit (human-like)
        if random.random() < 0.3:
            await self.client.scroll_page('up', random.randint(100, 300))
            await asyncio.sleep(random.uniform(0.2, 0.5))

        # Simulate mouse movement
        try:
            mouse_move_js = """
            () => {
                const event = new MouseEvent('mousemove', {
                    clientX: Math.random() * window.innerWidth,
                    clientY: Math.random() * window.innerHeight,
                    bubbles: true
                });
                document.dispatchEvent(event);
            }
            """
            await self.client.evaluate(mouse_move_js)
        except Exception:
            pass  # Mouse movement is optional

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        if not text:
            return ''
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove common unwanted patterns
        text = re.sub(r'[\n\r\t]', '', text)
        return text

    def _extract_price(self, text: str, price_regex: str) -> str:
        """
        Extract price from text.

        Handles multiple currency formats:
        - Indian Rupee: Rs.1,299 or Rs. 1299
        - Dollar: $99.99
        - Euro: 99.99
        """
        if not text:
            return ''

        patterns = [
            r'[\u20b9]\s*([\d,]+(?:\.\d{2})?)',  # symbol
            r'Rs\.?\s*([\d,]+(?:\.\d{2})?)',     # Rs. prefix
            r'INR\s*([\d,]+(?:\.\d{2})?)',       # INR prefix
            r'\$\s*([\d,]+(?:\.\d{2})?)',        # $ symbol
            r'\u20ac\s*([\d,]+(?:\.\d{2})?)',    # symbol
            price_regex                          # Custom pattern
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Return with currency symbol if found
                if match.group(0).startswith(('₹', '$', '€', 'Rs', 'INR')):
                    return match.group(0)
                return match.group(1) if match.lastindex else match.group(0)

        return ''

    def _extract_brand_from_title(
        self,
        title: str,
        known_brands: List[str]
    ) -> str:
        """
        Extract brand from product title.

        Args:
            title: Product title
            known_brands: List of known brand names

        Returns:
            Extracted brand name or empty string
        """
        if not title:
            return ''

        title_lower = title.lower()

        # Check against known brands
        for brand in known_brands:
            if title_lower.startswith(brand.lower()):
                return brand
            # Also check if brand appears early in title
            if brand.lower() in title_lower[:50]:
                return brand

        # Fallback: assume first 1-3 capitalized words are the brand
        words = title.split()
        brand_words = []
        for word in words[:4]:
            if word and word[0].isupper():
                brand_words.append(word)
            else:
                break

        return ' '.join(brand_words) if brand_words else ''

    def _is_product_url(self, url: str) -> bool:
        """Check if URL looks like a product URL."""
        if not url:
            return False

        product_patterns = [
            r'/p/', r'/product/', r'/dp/', r'/buy/',
            r'/item/', r'/products/', r'-pd-',
        ]

        url_lower = url.lower()
        return any(pattern in url_lower for pattern in product_patterns)


# =============================================================================
# Utility Functions
# =============================================================================

def create_generic_config(
    base_url: str,
    search_path: str = '/search?q={query}',
    **kwargs
) -> SiteConfig:
    """
    Create a generic site configuration for any e-commerce site.

    Args:
        base_url: Base URL of the site (e.g., 'https://example.com')
        search_path: Search URL path with {query} placeholder
        **kwargs: Override any SiteConfig defaults

    Returns:
        Configured SiteConfig instance

    Example:
        config = create_generic_config(
            base_url='https://www.example-beauty.com',
            search_path='/products/search?term={query}',
            min_delay=2.0,
            max_delay=4.0
        )
    """
    domain = urlparse(base_url).netloc
    config_dict = {
        'name': domain,
        'base_url': base_url,
        'search_url_template': base_url + search_path,
        'product_container_hint': 'product',
        'title_hint': 'title',
        'brand_hint': 'brand',
        'price_hint': 'price',
        'link_hint': 'link',
        'next_page_hint': 'next',
        'page_param': 'page',
    }
    config_dict.update(kwargs)
    return SiteConfig(**config_dict)


def load_progress(progress_file: Path) -> Optional[Dict[str, Any]]:
    """
    Load progress from file for resumption.

    Args:
        progress_file: Path to progress JSON file

    Returns:
        Progress data or None if not found
    """
    try:
        if progress_file.exists():
            with open(progress_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load progress: {e}")
    return None


# =============================================================================
# Main / Example Usage
# =============================================================================

async def main():
    """Example usage of the crawler."""

    print("=" * 60)
    print("Playwright MCP-based E-commerce Crawler")
    print("=" * 60)

    # Create output directory
    output_dir = Path('./crawler_output')
    output_dir.mkdir(exist_ok=True)

    # Example MCP invoke function (replace with actual implementation)
    async def mock_mcp_invoke(tool_name: str, params: Dict[str, Any]) -> Any:
        """Mock MCP invoke function for testing."""
        logger.info(f"[MOCK] Would call MCP tool: {tool_name}")
        logger.debug(f"[MOCK] Params: {params}")

        # Return mock data for testing
        if 'snapshot' in tool_name:
            return "link 'Test Product' [S1E1]\ntext 'Test Brand'\ntext '999'"
        elif 'evaluate' in tool_name:
            return [
                {'url': 'https://example.com/product/1', 'title': 'Test Product 1', 'brand': 'Brand A', 'price': '999'},
                {'url': 'https://example.com/product/2', 'title': 'Test Product 2', 'brand': 'Brand B', 'price': '1299'},
            ]
        return {'success': True}

    # Initialize crawler
    # In production, pass your actual MCP invoke function
    crawler = ProductCrawler(output_dir=output_dir, mcp_invoke=mock_mcp_invoke)

    print("\nAvailable site configurations:")
    for name, config in SITE_CONFIGS.items():
        print(f"  - {name}: {config.name} ({config.base_url})")

    print("\nExample usage:")
    print("""
    # Import the crawler
    from playwright_crawler import ProductCrawler, SITE_CONFIGS

    # Define your MCP invoke function
    async def mcp_invoke(tool_name: str, params: dict):
        # Your MCP tool invocation logic here
        # This should call the actual MCP tools:
        # - mcp__playwright__browser_navigate
        # - mcp__playwright__browser_snapshot
        # - mcp__playwright__browser_click
        # - mcp__playwright__browser_type
        # - mcp__playwright__browser_evaluate
        pass

    # Initialize crawler with MCP invoke function
    crawler = ProductCrawler(
        output_dir='./output',
        mcp_invoke=mcp_invoke
    )

    # Crawl Nykaa for lipstick products
    products = await crawler.crawl_category(
        site_config=SITE_CONFIGS['nykaa'],
        category='lipstick',
        max_products=100
    )

    # Products are automatically:
    # - Deduplicated by URL
    # - Saved to CSV: output/products_nykaa_lipstick.csv
    # - Progress tracked in: output/progress_nykaa_lipstick.json

    # Create custom config for other sites
    from playwright_crawler import create_generic_config

    custom_config = create_generic_config(
        base_url='https://www.another-site.com',
        search_path='/search?query={query}',
        min_delay=2.0,
        max_delay=4.0,
        known_brands=['Brand1', 'Brand2']
    )

    products = await crawler.crawl_category(custom_config, 'skincare', 50)
    """)

    print("\nOutput files:")
    print(f"  - CSV: {output_dir}/products_<site>_<category>.csv")
    print(f"  - Progress: {output_dir}/progress_<site>_<category>.json")

    print("\nCSV columns: url, title, brand, category, price, timestamp")

    print("\n" + "=" * 60)
    print("Ready to crawl! Import this module and use ProductCrawler.")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
