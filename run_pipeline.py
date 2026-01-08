#!/usr/bin/env python3
"""
Unified CLI Pipeline Runner for URL-to-URL Product Matching

MAIN ENTRY POINT that orchestrates:
- Parallel site crawling (Site A and Site B simultaneously using asyncio)
- Incremental matching (matches every 10 products from Site A as they arrive)
- Real-time progress tracking (terminal UI + HTML dashboard)
- Graceful interruption (Ctrl+C saves progress, can resume)
- Checkpoint/resume support

Pipeline Stages:
1. Initialize - Setup crawlers, progress tracker, matcher
2. Parallel Crawl - Crawl both sites simultaneously
3. Incremental Match - Match products as Site A products arrive (every 10)
4. Generate Report - Create HTML report with match results
5. Complete - Save final state, cleanup

Usage:
    # Full interactive pipeline with parallel crawling
    python run_pipeline.py --site-a nykaa --site-b purplle --categories lipstick,foundation,serum --interactive

    # With HTML dashboard
    python run_pipeline.py --site-a nykaa --site-b purplle --products-a 50 --products-b 500 --dashboard

    # Crawl only (no matching)
    python run_pipeline.py --site-a nykaa --crawl-only --categories lipstick

    # Match from existing data
    python run_pipeline.py --match-only --site-a-data data/nykaa.csv --site-b-data data/purplle.csv

    # Resume interrupted session
    python run_pipeline.py --resume output/checkpoints/crawl_state.json

Author: Aditya Aman
Created: 2026-01-07
"""

import argparse
import asyncio
import csv
import json
import logging
import os
import signal
import sys
import threading
import time
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Local imports
from crawler import ProgressTracker, Status

# Conditional imports for optional features
try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class PipelineConfig:
    """Configuration for the pipeline run."""
    # Sites
    site_a: str = "nykaa"
    site_b: str = "purplle"

    # Crawling targets
    categories: List[str] = field(default_factory=lambda: ["lipstick", "foundation", "serum"])
    target_products_a: int = 50
    target_products_b: int = 500

    # Paths
    output_dir: Path = field(default_factory=lambda: Path("./output"))
    checkpoint_dir: Path = field(default_factory=lambda: Path("./data/checkpoints"))

    # Existing data (for match-only mode)
    site_a_data: Optional[Path] = None
    site_b_data: Optional[Path] = None

    # Execution modes
    crawl_only: bool = False
    match_only: bool = False
    interactive: bool = True
    dashboard: bool = False

    # Performance tuning
    parallel_browsers: int = 2
    rate_limit: int = 30  # requests per minute per site

    # Matching parameters
    top_k: int = 25
    threshold: float = 0.5
    model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Resume
    resume_from: Optional[Path] = None


@dataclass
class CrawlCheckpoint:
    """Checkpoint state for resumable crawling."""
    timestamp: str
    site_a_products: int = 0
    site_b_products: int = 0
    site_a_pages: int = 0
    site_b_pages: int = 0
    current_category_a: str = ""
    current_category_b: str = ""
    completed_categories_a: List[str] = field(default_factory=list)
    completed_categories_b: List[str] = field(default_factory=list)
    matches_found: int = 0
    status: str = "in_progress"


# ============================================================================
# Live Terminal Display (Rich)
# ============================================================================

class LiveDisplay:
    """
    Real-time terminal display using Rich library.

    Shows:
    - Site A crawl progress bar
    - Site B crawl progress bar
    - Matching progress
    - Recent products discovered
    - Current status
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.console = Console() if RICH_AVAILABLE else None
        self._live: Optional[Live] = None
        self._progress: Optional[Progress] = None

        # Progress tracking
        self.site_a_count = 0
        self.site_b_count = 0
        self.match_count = 0
        self.current_stage = "Initializing"
        self.recent_products_a: deque = deque(maxlen=3)
        self.recent_products_b: deque = deque(maxlen=3)
        self.last_match: Optional[Dict] = None
        self.errors: List[str] = []

    def _create_layout(self) -> Layout:
        """Create the display layout."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        return layout

    def _render_progress_table(self) -> Table:
        """Render the progress table."""
        table = Table(title="Pipeline Progress", expand=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        # Site A progress
        a_pct = (self.site_a_count / self.config.target_products_a * 100
                 if self.config.target_products_a > 0 else 0)
        table.add_row(
            f"Site A ({self.config.site_a})",
            f"{self.site_a_count}/{self.config.target_products_a} ({a_pct:.1f}%)"
        )

        # Site B progress
        b_pct = (self.site_b_count / self.config.target_products_b * 100
                 if self.config.target_products_b > 0 else 0)
        table.add_row(
            f"Site B ({self.config.site_b})",
            f"{self.site_b_count}/{self.config.target_products_b} ({b_pct:.1f}%)"
        )

        # Matches
        table.add_row("Matches Found", str(self.match_count))

        # Stage
        table.add_row("Current Stage", self.current_stage)

        return table

    def _render_recent_products(self) -> Panel:
        """Render recent products panel."""
        text = Text()
        text.append("Recent Site A Products:\n", style="bold cyan")
        for p in self.recent_products_a:
            text.append(f"  - {p[:50]}...\n" if len(p) > 50 else f"  - {p}\n")

        text.append("\nRecent Site B Products:\n", style="bold magenta")
        for p in self.recent_products_b:
            text.append(f"  - {p[:50]}...\n" if len(p) > 50 else f"  - {p}\n")

        if self.last_match:
            text.append("\nLast Match:\n", style="bold green")
            text.append(f"  {self.last_match.get('source_title', '')[:40]} -> "
                        f"{self.last_match.get('best_match_title', '')[:40]}\n")
            text.append(f"  Score: {self.last_match.get('score', 0):.2f}\n")

        return Panel(text, title="Activity")

    def start(self) -> None:
        """Start the live display."""
        if not RICH_AVAILABLE or not self.config.interactive:
            return

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self._live = Live(self._render_progress_table(), refresh_per_second=2, console=self.console)
        self._live.start()

    def stop(self) -> None:
        """Stop the live display."""
        if self._live:
            self._live.stop()

    def update(
        self,
        site_a_count: Optional[int] = None,
        site_b_count: Optional[int] = None,
        match_count: Optional[int] = None,
        stage: Optional[str] = None,
        product_a: Optional[str] = None,
        product_b: Optional[str] = None,
        last_match: Optional[Dict] = None,
    ) -> None:
        """Update display with new values."""
        if site_a_count is not None:
            self.site_a_count = site_a_count
        if site_b_count is not None:
            self.site_b_count = site_b_count
        if match_count is not None:
            self.match_count = match_count
        if stage is not None:
            self.current_stage = stage
        if product_a:
            self.recent_products_a.append(product_a)
        if product_b:
            self.recent_products_b.append(product_b)
        if last_match:
            self.last_match = last_match

        if self._live:
            self._live.update(self._render_progress_table())

    def print_status(self, message: str, style: str = "info") -> None:
        """Print a status message."""
        if RICH_AVAILABLE and self.console:
            styles = {
                "info": "blue",
                "success": "green",
                "warning": "yellow",
                "error": "red",
            }
            self.console.print(f"[{styles.get(style, 'white')}]{message}[/]")
        else:
            print(message)


# ============================================================================
# Incremental Matching Queue
# ============================================================================

class IncrementalMatcher:
    """
    Handles incremental matching as products arrive.

    Products from Site A are queued and matched against Site B products
    in batches of N (default: 10) to provide real-time feedback.
    """

    def __init__(
        self,
        batch_size: int = 10,
        threshold: float = 0.5,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        self.batch_size = batch_size
        self.threshold = threshold
        self.model_name = model_name

        # Queues
        self.product_queue: Queue = Queue()
        self.site_b_products: List[Dict] = []
        self.matches: List[Dict] = []

        # State
        self._running = False
        self._matcher = None
        self._products_a_embeddings = None
        self._products_b_embeddings = None
        self._logger = logging.getLogger("IncrementalMatcher")

        # Callbacks
        self.on_match: Optional[Callable[[Dict], None]] = None
        self.on_batch_complete: Optional[Callable[[int], None]] = None

    def set_site_b_products(self, products: List[Dict]) -> None:
        """Set the Site B products for matching against."""
        self.site_b_products = products
        self._logger.info(f"Site B products set: {len(products)} products")

    def queue_product(self, product: Dict) -> None:
        """Queue a Site A product for matching."""
        self.product_queue.put(product)

    def start(self) -> None:
        """Start the matching thread."""
        self._running = True
        self._match_thread = threading.Thread(target=self._match_loop, daemon=True)
        self._match_thread.start()

    def stop(self) -> None:
        """Stop the matching thread."""
        self._running = False
        self.product_queue.put(None)  # Sentinel to unblock

    def _match_loop(self) -> None:
        """Main matching loop running in background thread."""
        batch: List[Dict] = []

        while self._running:
            try:
                product = self.product_queue.get(timeout=1.0)

                if product is None:  # Sentinel
                    break

                batch.append(product)

                # Process batch when full
                if len(batch) >= self.batch_size:
                    self._process_batch(batch)
                    batch = []

            except Empty:
                # Process partial batch if no new products coming
                if batch and not self._running:
                    self._process_batch(batch)
                    batch = []
                continue

        # Process remaining batch
        if batch:
            self._process_batch(batch)

    def _process_batch(self, batch: List[Dict]) -> None:
        """Process a batch of products for matching."""
        if not self.site_b_products:
            self._logger.warning("No Site B products available for matching")
            return

        self._logger.info(f"Processing batch of {len(batch)} products")

        for product_a in batch:
            best_match, score = self._find_best_match(product_a)

            if best_match and score >= self.threshold:
                match_result = {
                    "source_url": product_a.get('url', ''),
                    "source_title": product_a.get('title', ''),
                    "source_brand": product_a.get('brand', ''),
                    "best_match_url": best_match.get('url', ''),
                    "best_match_title": best_match.get('title', ''),
                    "best_match_brand": best_match.get('brand', ''),
                    "score": score,
                    "timestamp": datetime.now().isoformat()
                }
                self.matches.append(match_result)

                if self.on_match:
                    self.on_match(match_result)

        if self.on_batch_complete:
            self.on_batch_complete(len(self.matches))

    def _find_best_match(self, product_a: Dict) -> Tuple[Optional[Dict], float]:
        """Find the best match for a product using title similarity."""
        from difflib import SequenceMatcher

        best_match = None
        best_score = 0.0

        title_a = product_a.get('title', '').lower()
        brand_a = product_a.get('brand', '').lower()

        for product_b in self.site_b_products:
            title_b = product_b.get('title', '').lower()
            brand_b = product_b.get('brand', '').lower()

            # Title similarity
            title_score = SequenceMatcher(None, title_a, title_b).ratio()

            # Brand bonus
            brand_bonus = 0.1 if brand_a and brand_b and (
                brand_a in brand_b or brand_b in brand_a
            ) else 0

            score = title_score + brand_bonus

            if score > best_score:
                best_score = score
                best_match = product_b

        return best_match, min(best_score, 1.0)

    def get_matches(self) -> List[Dict]:
        """Get all matches found so far."""
        return self.matches.copy()


# ============================================================================
# Logging
# ============================================================================

def setup_logging(output_dir: Path, verbose: bool = False) -> logging.Logger:
    """Configure logging for the pipeline."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "pipeline.log"

    logger = logging.getLogger("URLPipeline")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    ))

    # File handler
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s'
    ))

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger


# ============================================================================
# Pipeline Runner
# ============================================================================

class PipelineRunner:
    """
    Main orchestrator for the URL-to-URL matching pipeline.

    Coordinates:
    - Multi-site parallel crawling
    - Real-time progress tracking
    - Live matching (optional)
    - Checkpoint management
    """

    def __init__(self, config: PipelineConfig):
        """Initialize the pipeline runner."""
        self.config = config
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.logger = setup_logging(config.output_dir)
        self.tracker: Optional[ProgressTracker] = None

        # Product storage
        self.site_a_products: List[Dict] = []
        self.site_b_products: List[Dict] = []
        self.matches: List[Dict] = []

        # Checkpoint state
        self.checkpoint = CrawlCheckpoint(timestamp=datetime.now().isoformat())

        # Control flags
        self._running = False
        self._paused = False
        self._cancelled = False

        # Rich console for pretty output
        if RICH_AVAILABLE:
            self.console = Console()

        self.logger.info(f"Pipeline initialized. Output: {config.output_dir}")

    def _print_header(self) -> None:
        """Print pipeline startup header."""
        if RICH_AVAILABLE:
            header = Text()
            header.append("URL-to-URL Product Matching Pipeline\n", style="bold blue")
            header.append(f"Sites: {self.config.site_a} -> {self.config.site_b}\n")
            header.append(f"Categories: {', '.join(self.config.categories)}\n")
            header.append(f"Mode: ", style="dim")

            if self.config.crawl_only:
                header.append("Crawl Only", style="yellow")
            elif self.config.match_only:
                header.append("Match Only", style="cyan")
            else:
                header.append("Full Pipeline (Crawl + Match)", style="green")

            self.console.print(Panel(header, title="Starting Pipeline"))
        else:
            print("=" * 60)
            print("URL-to-URL Product Matching Pipeline")
            print("=" * 60)
            print(f"Sites: {self.config.site_a} -> {self.config.site_b}")
            print(f"Categories: {', '.join(self.config.categories)}")
            print("-" * 60)

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def handle_interrupt(signum, frame):
            self.logger.warning("Interrupt received, saving checkpoint...")
            self._cancelled = True
            self._save_checkpoint()

        signal.signal(signal.SIGINT, handle_interrupt)
        signal.signal(signal.SIGTERM, handle_interrupt)

    def _save_checkpoint(self) -> None:
        """Save current state to checkpoint file."""
        self.checkpoint.timestamp = datetime.now().isoformat()
        self.checkpoint.site_a_products = len(self.site_a_products)
        self.checkpoint.site_b_products = len(self.site_b_products)

        checkpoint_file = self.config.checkpoint_dir / "crawl_state.json"

        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(asdict(self.checkpoint), f, indent=2)

            # Also save current product data
            self._save_products_csv()

            self.logger.info(f"Checkpoint saved to {checkpoint_file}")
        except Exception as e:
            self.logger.error(f"Failed to save checkpoint: {e}")

    def _load_checkpoint(self, checkpoint_file: Path) -> bool:
        """Load state from checkpoint file."""
        try:
            with open(checkpoint_file) as f:
                data = json.load(f)

            self.checkpoint = CrawlCheckpoint(**data)
            self.logger.info(f"Loaded checkpoint from {checkpoint_file}")
            self.logger.info(f"  Site A products: {self.checkpoint.site_a_products}")
            self.logger.info(f"  Site B products: {self.checkpoint.site_b_products}")

            # Load existing product data if available
            self._load_existing_products()

            return True
        except Exception as e:
            self.logger.error(f"Failed to load checkpoint: {e}")
            return False

    def _load_existing_products(self) -> None:
        """Load existing product data from CSV files."""
        # Site A
        site_a_file = self.config.output_dir / f"products_{self.config.site_a}.csv"
        if site_a_file.exists():
            self.site_a_products = self._load_csv(site_a_file)
            self.logger.info(f"Loaded {len(self.site_a_products)} Site A products")

        # Site B
        site_b_file = self.config.output_dir / f"products_{self.config.site_b}.csv"
        if site_b_file.exists():
            self.site_b_products = self._load_csv(site_b_file)
            self.logger.info(f"Loaded {len(self.site_b_products)} Site B products")

    def _load_csv(self, file_path: Path) -> List[Dict]:
        """Load products from CSV file."""
        products = []
        try:
            with open(file_path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                products = list(reader)
        except Exception as e:
            self.logger.error(f"Failed to load {file_path}: {e}")
        return products

    def _save_products_csv(self) -> None:
        """Save current products to CSV files."""
        # Site A
        if self.site_a_products:
            site_a_file = self.config.output_dir / f"products_{self.config.site_a}.csv"
            self._save_csv(self.site_a_products, site_a_file)

        # Site B
        if self.site_b_products:
            site_b_file = self.config.output_dir / f"products_{self.config.site_b}.csv"
            self._save_csv(self.site_b_products, site_b_file)

    def _save_csv(self, products: List[Dict], file_path: Path) -> None:
        """Save products to CSV file."""
        if not products:
            return

        try:
            fieldnames = ['url', 'title', 'brand', 'category', 'price']
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(products)
            self.logger.debug(f"Saved {len(products)} products to {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to save {file_path}: {e}")

    async def run(self) -> Dict[str, Any]:
        """
        Execute the pipeline.

        Returns:
            Summary dictionary with results
        """
        self._print_header()
        self._setup_signal_handlers()
        self._running = True

        start_time = time.time()

        try:
            # Initialize progress tracker
            self.tracker = ProgressTracker(
                total_sites=2,
                output_dir=str(self.config.output_dir),
                enable_terminal_ui=self.config.interactive and RICH_AVAILABLE,
                enable_html_dashboard=self.config.dashboard
            )

            # Open dashboard in browser if requested
            if self.config.dashboard:
                dashboard_path = self.config.output_dir / "dashboard.html"
                self.logger.info(f"Dashboard will be available at: {dashboard_path}")
                # Give it a moment to create the file
                await asyncio.sleep(1)
                if dashboard_path.exists():
                    webbrowser.open(f"file://{dashboard_path.absolute()}")

            # Load checkpoint if resuming
            if self.config.resume_from and self.config.resume_from.exists():
                self._load_checkpoint(self.config.resume_from)

            # Execute appropriate mode
            if self.config.match_only:
                # Match only mode
                await self._run_match_only()
            elif self.config.crawl_only:
                # Crawl only mode
                await self._run_crawl_only()
            else:
                # Full pipeline: crawl + match
                await self._run_full_pipeline()

            # Complete tracking
            summary = self.tracker.complete() if self.tracker else {}

            # Save final checkpoint
            self.checkpoint.status = "completed" if not self._cancelled else "interrupted"
            self._save_checkpoint()

            elapsed = time.time() - start_time

            return {
                "status": "completed" if not self._cancelled else "interrupted",
                "elapsed_seconds": round(elapsed, 2),
                "site_a_products": len(self.site_a_products),
                "site_b_products": len(self.site_b_products),
                "matches": len(self.matches),
                "output_dir": str(self.config.output_dir),
                **summary
            }

        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            self._save_checkpoint()
            raise
        finally:
            self._running = False

    async def _run_crawl_only(self) -> None:
        """Execute crawl-only mode."""
        self.logger.info("Running in CRAWL ONLY mode")

        # Start tracking for Site A
        self.tracker.start_crawl(self.config.site_a, self.config.target_products_a)

        # Simulate crawling (in production, use PlaywrightCrawler)
        await self._simulate_crawl(
            site_name=self.config.site_a,
            target=self.config.target_products_a,
            products_list=self.site_a_products
        )

        self.tracker.complete_crawl(self.config.site_a, len(self.site_a_products))

        # Optionally crawl Site B
        if self.config.site_b:
            self.tracker.start_crawl(self.config.site_b, self.config.target_products_b)

            await self._simulate_crawl(
                site_name=self.config.site_b,
                target=self.config.target_products_b,
                products_list=self.site_b_products
            )

            self.tracker.complete_crawl(self.config.site_b, len(self.site_b_products))

    async def _run_match_only(self) -> None:
        """Execute match-only mode with existing data."""
        self.logger.info("Running in MATCH ONLY mode")

        # Load data from specified files
        if self.config.site_a_data:
            self.site_a_products = self._load_csv(self.config.site_a_data)
            self.logger.info(f"Loaded {len(self.site_a_products)} products from {self.config.site_a_data}")

        if self.config.site_b_data:
            self.site_b_products = self._load_csv(self.config.site_b_data)
            self.logger.info(f"Loaded {len(self.site_b_products)} products from {self.config.site_b_data}")

        if not self.site_a_products or not self.site_b_products:
            self.logger.error("Cannot match: missing product data")
            return

        # Run matching
        await self._run_matching()

    async def _run_full_pipeline(self) -> None:
        """
        Execute full pipeline with TRUE PARALLEL CRAWLING and INCREMENTAL MATCHING.

        Architecture:
        1. Start Site B crawl first (background) - larger dataset
        2. Start Site A crawl (parallel) - smaller dataset
        3. As Site A products arrive, queue them for incremental matching
        4. Matching runs in background thread, processes every 10 products
        5. Once both crawls complete, finalize matching and generate report
        """
        self.logger.info("Running FULL PIPELINE (Parallel Crawl + Incremental Match)")

        # Initialize live display
        display = LiveDisplay(self.config)
        if self.config.interactive and RICH_AVAILABLE:
            display.start()

        # Initialize incremental matcher
        matcher = IncrementalMatcher(
            batch_size=10,
            threshold=self.config.threshold,
            model_name=self.config.model
        )

        # Callbacks for matcher
        def on_match(match_result: Dict):
            display.update(
                match_count=len(matcher.matches),
                last_match=match_result
            )
            self.matches.append(match_result)

        def on_batch_complete(total_matches: int):
            self.logger.info(f"Batch complete: {total_matches} total matches")

        matcher.on_match = on_match
        matcher.on_batch_complete = on_batch_complete

        # Callbacks for Site A crawl - queue products for incremental matching
        async def on_product_a(product: Dict):
            self.site_a_products.append(product)
            display.update(
                site_a_count=len(self.site_a_products),
                product_a=product.get('title', '')
            )
            # Queue for incremental matching once Site B has some products
            if len(self.site_b_products) >= 50:
                matcher.queue_product(product)

        # Callbacks for Site B crawl
        async def on_product_b(product: Dict):
            self.site_b_products.append(product)
            display.update(
                site_b_count=len(self.site_b_products),
                product_b=product.get('title', '')
            )
            # Update matcher's target products periodically
            if len(self.site_b_products) % 50 == 0:
                matcher.set_site_b_products(self.site_b_products.copy())

        try:
            # Stage 1: Initialize
            display.update(stage="Stage 1: Initializing")
            self.tracker.start_crawl(self.config.site_a, self.config.target_products_a)
            self.tracker.start_crawl(self.config.site_b, self.config.target_products_b)

            # Stage 2: Parallel Crawl
            display.update(stage="Stage 2: Parallel Crawling")
            self.logger.info("Starting parallel crawl of both sites...")

            # Create crawl tasks
            crawl_a = self._crawl_site(
                site_name=self.config.site_a,
                target=self.config.target_products_a,
                on_product=on_product_a,
                display=display
            )

            crawl_b = self._crawl_site(
                site_name=self.config.site_b,
                target=self.config.target_products_b,
                on_product=on_product_b,
                display=display
            )

            # Start matcher thread
            matcher.start()

            # Run crawls in parallel using asyncio.gather
            await asyncio.gather(crawl_a, crawl_b)

            self.logger.info(f"Parallel crawl complete: Site A={len(self.site_a_products)}, Site B={len(self.site_b_products)}")

            # Stage 3: Finalize Incremental Matching
            display.update(stage="Stage 3: Finalizing Matches")

            # Set final Site B products and queue remaining Site A products
            matcher.set_site_b_products(self.site_b_products.copy())

            # Queue any Site A products that weren't matched during crawl
            queued_count = matcher.product_queue.qsize()
            for product in self.site_a_products[queued_count:]:
                if self._cancelled:
                    break
                matcher.queue_product(product)

            # Wait for matching to complete
            matcher.stop()
            await asyncio.sleep(2)  # Give time for final batch

            # Get all matches
            self.matches = matcher.get_matches()

            # Update tracker
            self.tracker.complete_crawl(self.config.site_a, len(self.site_a_products))
            self.tracker.complete_crawl(self.config.site_b, len(self.site_b_products))

            # Stage 4: Generate Report
            if not self._cancelled and self.matches:
                display.update(stage="Stage 4: Generating Report")
                await self._generate_report()

            # Stage 5: Complete
            display.update(stage="Stage 5: Complete")

        finally:
            display.stop()

    async def _crawl_site(
        self,
        site_name: str,
        target: int,
        on_product: Callable,
        display: LiveDisplay
    ) -> None:
        """
        Crawl a single site with product callbacks.

        This method tries to use actual crawl data first, falling back to
        loading from existing CSV files.
        """
        self.logger.info(f"Starting crawl for {site_name} (target: {target})")

        # First check for existing data
        data_file = Path("data") / f"{site_name}.csv"
        output_file = self.config.output_dir / f"products_{site_name}.csv"

        source_file = None
        if data_file.exists():
            source_file = data_file
        elif output_file.exists():
            source_file = output_file

        if source_file:
            self.logger.info(f"Loading existing data from {source_file}")
            products = self._load_csv(source_file)

            for i, product in enumerate(products[:target]):
                if self._cancelled:
                    break

                await on_product(product)

                # Update tracker
                self.tracker.update_crawl(
                    site_name,
                    products_found=i + 1,
                    current_page=(i // 20) + 1,
                    last_product=product
                )

                # Simulate crawl timing for realistic progress
                await asyncio.sleep(0.05)

            self.logger.info(f"Loaded {min(len(products), target)} products for {site_name}")
            return

        # No existing data - generate mock data for demo
        self.logger.warning(f"No existing data for {site_name}, generating demo data")
        for i in range(target):
            if self._cancelled:
                break

            product = {
                "url": f"https://www.{site_name}.com/product/{i+1}",
                "title": f"Sample {site_name.title()} Product {i+1}",
                "brand": f"Brand{i % 10}",
                "category": self.config.categories[i % len(self.config.categories)],
                "price": f"Rs. {100 + i * 10}"
            }

            await on_product(product)

            self.tracker.update_crawl(
                site_name,
                products_found=i + 1,
                current_page=(i // 20) + 1,
                last_product=product
            )

            await asyncio.sleep(0.05)

    async def _generate_report(self) -> None:
        """Generate HTML report from matches."""
        if not self.matches:
            self.logger.info("No matches to report")
            return

        # Save matches to CSV first
        matches_file = self.config.output_dir / "matches.csv"
        fieldnames = [
            'source_url', 'source_title', 'source_brand',
            'best_match_url', 'best_match_title', 'best_match_brand',
            'score', 'timestamp'
        ]

        try:
            with open(matches_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(self.matches)
            self.logger.info(f"Saved {len(self.matches)} matches to {matches_file}")
        except Exception as e:
            self.logger.error(f"Failed to save matches: {e}")
            return

        # Try to generate HTML report
        try:
            from generate_report import generate_report

            report_file = self.config.output_dir / "report.html"
            generate_report(
                matches_csv=str(matches_file),
                output_path=str(report_file),
                source_name=self.config.site_a,
                target_name=self.config.site_b,
                source_count=len(self.site_a_products),
                target_count=len(self.site_b_products)
            )
            self.logger.info(f"Generated HTML report: {report_file}")

        except ImportError:
            self.logger.warning("generate_report module not available, skipping HTML report")
        except Exception as e:
            self.logger.error(f"Failed to generate HTML report: {e}")

    async def _simulate_crawl(
        self,
        site_name: str,
        target: int,
        products_list: List[Dict]
    ) -> None:
        """
        Simulate crawling (placeholder for actual MCP crawler integration).

        In production, this would use PlaywrightCrawler with MCP tools.
        For now, it loads from existing CSV or generates mock data.
        """
        # Try to load from existing data first
        existing_file = self.config.output_dir / f"products_{site_name}.csv"
        if existing_file.exists():
            loaded = self._load_csv(existing_file)
            if loaded:
                products_list.extend(loaded[:target])

                # Update progress
                for i, product in enumerate(products_list):
                    if self._cancelled:
                        break
                    self.tracker.update_crawl(
                        site_name,
                        products_found=i + 1,
                        current_page=(i // 20) + 1,
                        last_product=product
                    )
                    await asyncio.sleep(0.01)  # Small delay for UI updates

                return

        # Also check data/ directory
        data_file = Path("data") / f"{site_name}.csv"
        if data_file.exists():
            loaded = self._load_csv(data_file)
            if loaded:
                products_list.extend(loaded[:target])

                for i, product in enumerate(products_list):
                    if self._cancelled:
                        break
                    self.tracker.update_crawl(
                        site_name,
                        products_found=i + 1,
                        current_page=(i // 20) + 1,
                        last_product=product
                    )
                    await asyncio.sleep(0.01)

                return

        # Generate mock data if no existing data
        self.logger.warning(f"No existing data for {site_name}, generating mock data")

        for i in range(target):
            if self._cancelled:
                break

            product = {
                "url": f"https://www.{site_name}.com/product/{i+1}",
                "title": f"Sample Product {i+1} from {site_name}",
                "brand": f"Brand{i % 10}",
                "category": self.config.categories[i % len(self.config.categories)],
                "price": f"Rs. {100 + i * 10}"
            }
            products_list.append(product)

            # Update progress
            self.tracker.update_crawl(
                site_name,
                products_found=i + 1,
                current_page=(i // 20) + 1,
                last_product=product
            )

            # Simulate crawl delay
            await asyncio.sleep(0.05)

    async def _run_matching(self) -> None:
        """Run the semantic matching engine."""
        self.logger.info("Starting semantic matching...")

        if not self.site_a_products or not self.site_b_products:
            self.logger.error("Cannot match: missing product data")
            return

        self.tracker.start_matching(
            source_count=len(self.site_a_products),
            target_count=len(self.site_b_products)
        )

        # Import matching engine
        try:
            from url_mapper import SemanticMatcher

            # Initialize matcher
            matcher = SemanticMatcher(model_name=self.config.model)

            # Convert to DataFrames
            import pandas as pd
            df_a = pd.DataFrame(self.site_a_products)
            df_b = pd.DataFrame(self.site_b_products)

            # Load products
            products_a = matcher.load_products(df_a, "Site A")
            products_b = matcher.load_products(df_b, "Site B")

            # Find matches with progress updates
            for i, product_a in enumerate(products_a):
                if self._cancelled:
                    break

                # Find best match
                best_match, score = matcher.find_best_match(product_a, products_b)

                if best_match:
                    match_result = {
                        "source_url": product_a.url,
                        "source_title": product_a.title,
                        "best_match_url": best_match.url,
                        "best_match_title": best_match.title,
                        "score": score
                    }
                    self.matches.append(match_result)

                    # Update progress
                    self.tracker.update_matching(
                        matched=i + 1,
                        current_product=product_a.title[:50],
                        best_match=best_match.title[:50] if best_match else None,
                        score=score
                    )

                await asyncio.sleep(0.01)  # Allow UI updates

            # Save matches
            matches_file = self.config.output_dir / "matches.csv"
            self._save_csv(self.matches, matches_file)
            self.logger.info(f"Saved {len(self.matches)} matches to {matches_file}")

        except ImportError as e:
            self.logger.warning(f"SemanticMatcher not available: {e}")
            self.logger.info("Running simple title-based matching instead...")

            # Simple fallback matching
            await self._simple_matching()

    async def _simple_matching(self) -> None:
        """Simple title-based matching fallback."""
        from difflib import SequenceMatcher

        for i, product_a in enumerate(self.site_a_products):
            if self._cancelled:
                break

            best_match = None
            best_score = 0.0

            title_a = product_a.get('title', '').lower()

            for product_b in self.site_b_products:
                title_b = product_b.get('title', '').lower()
                score = SequenceMatcher(None, title_a, title_b).ratio()

                if score > best_score:
                    best_score = score
                    best_match = product_b

            if best_match and best_score > self.config.threshold:
                match_result = {
                    "source_url": product_a.get('url', ''),
                    "source_title": product_a.get('title', ''),
                    "best_match_url": best_match.get('url', ''),
                    "best_match_title": best_match.get('title', ''),
                    "score": best_score
                }
                self.matches.append(match_result)

            # Update progress
            self.tracker.update_matching(
                matched=i + 1,
                current_product=product_a.get('title', '')[:50],
                best_match=best_match.get('title', '')[:50] if best_match else None,
                score=best_score
            )

            await asyncio.sleep(0.01)

        # Save matches
        matches_file = self.config.output_dir / "matches.csv"
        if self.matches:
            fieldnames = ['source_url', 'source_title', 'best_match_url', 'best_match_title', 'score']
            try:
                with open(matches_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(self.matches)
                self.logger.info(f"Saved {len(self.matches)} matches to {matches_file}")
            except Exception as e:
                self.logger.error(f"Failed to save matches: {e}")


# ============================================================================
# CLI Interface
# ============================================================================

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="URL-to-URL Product Matching Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full interactive pipeline with dashboard
  python run_pipeline.py --site-a nykaa --site-b purplle --interactive --dashboard

  # Crawl specific categories
  python run_pipeline.py --site-a nykaa --site-b purplle --categories lipstick,foundation

  # Match from existing CSV files
  python run_pipeline.py --match-only --site-a-data data/nykaa.csv --site-b-data data/purplle.csv

  # Resume interrupted session
  python run_pipeline.py --resume output/checkpoints/crawl_state.json

  # Crawl only (no matching)
  python run_pipeline.py --site-a nykaa --crawl-only --products 100
        """
    )

    # Site configuration
    site_group = parser.add_argument_group("Sites")
    site_group.add_argument(
        "--site-a", "-a",
        default="nykaa",
        help="Primary site name (default: nykaa)"
    )
    site_group.add_argument(
        "--site-b", "-b",
        default="purplle",
        help="Competitor site name (default: purplle)"
    )
    site_group.add_argument(
        "--categories", "-c",
        default="lipstick,foundation,serum",
        help="Comma-separated categories to crawl (default: lipstick,foundation,serum)"
    )
    site_group.add_argument(
        "--products-a", "-n",
        type=int,
        default=50,
        help="Total target products for Site A (default: 50)"
    )
    site_group.add_argument(
        "--products-b",
        type=int,
        default=500,
        help="Total target products for Site B (default: 500)"
    )
    site_group.add_argument(
        "--products",
        type=int,
        default=None,
        help="Shorthand: set Site A target (Site B = 10x automatically)"
    )

    # Mode selection
    mode_group = parser.add_argument_group("Execution Mode")
    mode_group.add_argument(
        "--crawl-only",
        action="store_true",
        help="Only crawl, skip matching"
    )
    mode_group.add_argument(
        "--match-only",
        action="store_true",
        help="Only match from existing data"
    )
    mode_group.add_argument(
        "--site-a-data",
        type=Path,
        help="Path to Site A CSV for match-only mode"
    )
    mode_group.add_argument(
        "--site-b-data",
        type=Path,
        help="Path to Site B CSV for match-only mode"
    )

    # Progress & UI
    ui_group = parser.add_argument_group("Progress & UI")
    ui_group.add_argument(
        "--interactive", "-i",
        action="store_true",
        default=True,
        help="Enable interactive terminal UI (default: enabled)"
    )
    ui_group.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable interactive terminal UI"
    )
    ui_group.add_argument(
        "--dashboard", "-d",
        action="store_true",
        help="Open live HTML dashboard in browser"
    )

    # Output & checkpoint
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("./output"),
        help="Output directory (default: ./output)"
    )
    output_group.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=Path("./data/checkpoints"),
        help="Checkpoint directory (default: ./data/checkpoints)"
    )
    output_group.add_argument(
        "--resume", "-r",
        type=Path,
        help="Resume from checkpoint file"
    )

    # Matching parameters
    match_group = parser.add_argument_group("Matching")
    match_group.add_argument(
        "--top-k",
        type=int,
        default=25,
        help="Top K candidates per product (default: 25)"
    )
    match_group.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Minimum match score threshold (default: 0.5)"
    )
    match_group.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Sentence transformer model (default: all-MiniLM-L6-v2)"
    )

    # Performance
    perf_group = parser.add_argument_group("Performance")
    perf_group.add_argument(
        "--parallel",
        type=int,
        default=2,
        help="Number of parallel browser instances (default: 2)"
    )
    perf_group.add_argument(
        "--rate-limit",
        type=int,
        default=30,
        help="Requests per minute per site (default: 30)"
    )

    # Misc
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Handle --products shorthand
    products_a = args.products_a
    products_b = args.products_b
    if args.products is not None:
        products_a = args.products
        products_b = args.products * 10  # Site B is 10x Site A

    # Build configuration
    config = PipelineConfig(
        site_a=args.site_a,
        site_b=args.site_b,
        categories=[c.strip() for c in args.categories.split(",")],
        target_products_a=products_a,
        target_products_b=products_b,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir,
        site_a_data=args.site_a_data,
        site_b_data=args.site_b_data,
        crawl_only=args.crawl_only,
        match_only=args.match_only,
        interactive=args.interactive and not args.no_interactive,
        dashboard=args.dashboard,
        parallel_browsers=args.parallel,
        rate_limit=args.rate_limit,
        top_k=args.top_k,
        threshold=args.threshold,
        model=args.model,
        resume_from=args.resume
    )

    # Create and run pipeline
    runner = PipelineRunner(config)

    try:
        summary = asyncio.run(runner.run())

        # Print final summary
        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Status: {summary.get('status', 'unknown')}")
        print(f"Elapsed: {summary.get('elapsed_seconds', 0):.1f} seconds")
        print(f"Site A products: {summary.get('site_a_products', 0)}")
        print(f"Site B products: {summary.get('site_b_products', 0)}")
        print(f"Matches found: {summary.get('matches', 0)}")
        print(f"Output directory: {summary.get('output_dir', '')}")
        print("=" * 60)

        if summary.get('status') == 'completed':
            sys.exit(0)
        else:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nPipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
