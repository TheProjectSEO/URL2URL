"""
Crawler module for URL-to-URL product matching pipeline.

Components:
- PlaywrightCrawler: Web scraping using Playwright (requires playwright package)
- ProgressTracker: Real-time progress tracking with terminal UI and HTML dashboard
- Callbacks: Event handling for product discovery and matching
"""

# Progress tracking (no external dependencies except optional 'rich')
from .progress_tracker import (
    ProgressTracker,
    ProgressCallback,
    DefaultCallback,
    Status,
    SiteProgress,
    MatchingProgress,
    ProgressState,
    load_progress,
    watch_progress,
)

__all__ = [
    # Progress Tracking
    'ProgressTracker',
    'ProgressCallback',
    'DefaultCallback',
    'Status',
    'SiteProgress',
    'MatchingProgress',
    'ProgressState',
    'load_progress',
    'watch_progress',
]

# Optional: Playwright crawler (only if playwright is installed)
try:
    from .playwright_crawler import PlaywrightCrawler, CrawlerConfig, CrawledProduct
    __all__.extend([
        'PlaywrightCrawler',
        'CrawlerConfig',
        'CrawledProduct',
    ])
except ImportError:
    # Playwright not installed - that's okay, progress tracker still works
    pass
