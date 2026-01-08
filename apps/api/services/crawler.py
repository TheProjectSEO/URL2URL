"""
Playwright-based Product Crawler for URL-to-URL Matching
Extracts product data from e-commerce URLs using headless browser.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser

logger = logging.getLogger(__name__)


@dataclass
class ProductData:
    """Extracted product data from a URL."""
    url: str
    title: str
    description: str = ""
    brand: str = ""
    category: str = ""
    price: Optional[float] = None
    images: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str = ""


class ProductCrawler:
    """
    Playwright-based product data extractor.
    Supports Nykaa, Purplle, and generic e-commerce sites.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        max_concurrent: int = 5
    ):
        """
        Initialize crawler.

        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
            max_concurrent: Maximum concurrent crawls
        """
        self.headless = headless
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry - launch browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        logger.info("ProductCrawler browser launched")
        return self

    async def __aexit__(self, *args):
        """Async context manager exit - close browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("ProductCrawler browser closed")

    async def crawl_product(self, url: str) -> ProductData:
        """
        Crawl a single product URL and extract data.

        Args:
            url: Product page URL

        Returns:
            ProductData with extracted information
        """
        page = None
        try:
            page = await self._browser.new_page()
            page.set_default_timeout(self.timeout)

            # Add stealth headers
            await page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            })

            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)  # Allow JS to render

            # Determine site and extract
            domain = urlparse(url).netloc.lower()

            if 'nykaa.com' in domain:
                data = await self._extract_nykaa(page, url)
            elif 'purplle.com' in domain:
                data = await self._extract_purplle(page, url)
            else:
                data = await self._extract_generic(page, url)

            return data

        except Exception as e:
            logger.error(f"Crawl failed for {url}: {e}")
            return ProductData(
                url=url,
                title="",
                success=False,
                error=str(e)
            )
        finally:
            if page:
                await page.close()

    async def _extract_nykaa(self, page: Page, url: str) -> ProductData:
        """Extract product data from Nykaa."""
        try:
            # Title - multiple possible selectors
            title = ""
            for selector in ['h1.css-1gc4x7i', 'h1[class*="product-title"]', 'h1']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        title = await el.text_content() or ""
                        if title.strip():
                            break
                except:
                    continue

            # Brand
            brand = ""
            for selector in ['a.css-1afod2z', 'a[class*="brand"]', '[itemprop="brand"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        brand = await el.text_content() or ""
                        if brand.strip():
                            break
                except:
                    continue

            # Price
            price = None
            for selector in ['span.css-1jczs19', 'span[class*="price"]', '[itemprop="price"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        price_text = await el.text_content() or ""
                        price_clean = price_text.replace('₹', '').replace(',', '').strip()
                        if price_clean:
                            price = float(price_clean)
                            break
                except:
                    continue

            # Description
            description = ""
            try:
                desc_el = page.locator('div.product-description, [class*="description"]').first
                if await desc_el.count() > 0:
                    description = await desc_el.text_content() or ""
            except:
                pass

            return ProductData(
                url=url,
                title=title.strip(),
                brand=brand.strip(),
                price=price,
                description=description[:500] if description else "",
                category="Beauty",
                metadata={"source": "nykaa", "domain": "nykaa.com"}
            )

        except Exception as e:
            logger.error(f"Nykaa extraction failed: {e}")
            return ProductData(url=url, title="", success=False, error=str(e))

    async def _extract_purplle(self, page: Page, url: str) -> ProductData:
        """Extract product data from Purplle."""
        try:
            # Title
            title = ""
            for selector in ['h1.product-title', 'h1[class*="title"]', 'h1']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        title = await el.text_content() or ""
                        if title.strip():
                            break
                except:
                    continue

            # Brand
            brand = ""
            for selector in ['a.brand-name', 'a[class*="brand"]', '[itemprop="brand"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        brand = await el.text_content() or ""
                        if brand.strip():
                            break
                except:
                    continue

            # Price
            price = None
            for selector in ['span.price', 'span[class*="price"]', '[itemprop="price"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        price_text = await el.text_content() or ""
                        price_clean = price_text.replace('₹', '').replace(',', '').strip()
                        if price_clean:
                            price = float(price_clean)
                            break
                except:
                    continue

            return ProductData(
                url=url,
                title=title.strip(),
                brand=brand.strip(),
                price=price,
                category="Beauty",
                metadata={"source": "purplle", "domain": "purplle.com"}
            )

        except Exception as e:
            logger.error(f"Purplle extraction failed: {e}")
            return ProductData(url=url, title="", success=False, error=str(e))

    async def _extract_generic(self, page: Page, url: str) -> ProductData:
        """Generic extractor using common e-commerce patterns."""
        try:
            # Title - try multiple common patterns
            title = ""
            for selector in [
                'h1',
                '[itemprop="name"]',
                '.product-title',
                '.product-name',
                '[class*="product-title"]',
                '[class*="product-name"]'
            ]:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        title = await el.text_content() or ""
                        if title.strip():
                            break
                except:
                    continue

            # Brand
            brand = ""
            for selector in ['[itemprop="brand"]', '.brand', '[class*="brand"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        brand = await el.text_content() or ""
                        if brand.strip():
                            break
                except:
                    continue

            # Price
            price = None
            for selector in ['[itemprop="price"]', '.price', '[class*="price"]']:
                try:
                    el = page.locator(selector).first
                    if await el.count() > 0:
                        price_text = await el.text_content() or ""
                        # Extract numbers from price string
                        import re
                        numbers = re.findall(r'[\d,]+\.?\d*', price_text)
                        if numbers:
                            price = float(numbers[0].replace(',', ''))
                            break
                except:
                    continue

            domain = urlparse(url).netloc

            return ProductData(
                url=url,
                title=title.strip(),
                brand=brand.strip(),
                price=price,
                metadata={"source": "generic", "domain": domain}
            )

        except Exception as e:
            logger.error(f"Generic extraction failed: {e}")
            return ProductData(url=url, title="", success=False, error=str(e))

    async def crawl_batch(
        self,
        urls: List[str],
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> List[ProductData]:
        """
        Crawl multiple URLs with concurrency control.

        Args:
            urls: List of product URLs to crawl
            on_progress: Optional callback(current, total, url) for progress updates

        Returns:
            List of ProductData results
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def crawl_with_semaphore(url: str, index: int) -> ProductData:
            async with semaphore:
                result = await self.crawl_product(url)
                if on_progress:
                    on_progress(index + 1, len(urls), url)
                return result

        tasks = [crawl_with_semaphore(url, i) for i, url in enumerate(urls)]
        return await asyncio.gather(*tasks)
