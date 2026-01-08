#!/usr/bin/env python3
"""
Real-Time Progress Tracking System for URL-to-URL Mapping Crawler

Provides:
- Real-time progress tracking with JSON state file
- Rich terminal UI with live progress bars
- HTML dashboard for browser-based monitoring
- Callback system for event handling
- ETA and rate statistics

Usage:
    from crawler.progress_tracker import ProgressTracker

    tracker = ProgressTracker(total_sites=2, output_dir="output")
    tracker.start_crawl("nykaa", target_products=50)
    tracker.update_crawl("nykaa", products_found=10, current_page=1)
    # ... more updates
    tracker.complete()
"""

import json
import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Dict, List, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, TaskID
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    from rich.style import Style
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Warning: 'rich' library not installed. Terminal UI will be basic.")
    print("Install with: pip install rich")


class Status(Enum):
    """Progress status states."""
    IDLE = "idle"
    CRAWLING = "crawling"
    MATCHING = "matching"
    COMPLETED = "completed"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class SiteProgress:
    """Progress data for a single site."""
    name: str
    products: int = 0
    target: int = 0
    pages: int = 0
    rate: float = 0.0  # products per second
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    last_product: Optional[str] = None


@dataclass
class MatchingProgress:
    """Progress data for matching phase."""
    completed: int = 0
    total: int = 0
    source_count: int = 0
    target_count: int = 0
    current: Optional[str] = None
    best_match: Optional[str] = None
    best_score: Optional[float] = None
    eta_seconds: Optional[float] = None
    rate: float = 0.0  # matches per second
    recent_matches: List[Dict] = field(default_factory=list)


@dataclass
class ProgressState:
    """Complete progress state."""
    status: str = Status.IDLE.value
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    sites: Dict[str, Dict] = field(default_factory=dict)
    matching: Dict = field(default_factory=dict)
    last_update: Optional[str] = None
    total_products: int = 0
    total_matches: int = 0
    errors: List[Dict] = field(default_factory=list)


class ProgressCallback(ABC):
    """Abstract base class for progress callbacks."""

    @abstractmethod
    def on_product_found(self, product: Dict) -> None:
        """Called when a new product is found."""
        pass

    @abstractmethod
    def on_match_found(self, source: Dict, target: Dict, score: float) -> None:
        """Called when a match is found."""
        pass

    @abstractmethod
    def on_error(self, error: str, context: Dict) -> None:
        """Called when an error occurs."""
        pass


class DefaultCallback(ProgressCallback):
    """Default callback implementation that logs events."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def on_product_found(self, product: Dict) -> None:
        if self.verbose:
            print(f"[PRODUCT] {product.get('title', 'Unknown')[:50]}")

    def on_match_found(self, source: Dict, target: Dict, score: float) -> None:
        if self.verbose:
            print(f"[MATCH] {source.get('title', 'Unknown')[:30]} -> {target.get('title', 'Unknown')[:30]} (score: {score:.2f})")

    def on_error(self, error: str, context: Dict) -> None:
        print(f"[ERROR] {error} | Context: {context}")


class ProgressTracker:
    """
    Real-time progress tracking system for crawling and matching operations.

    Features:
    - JSON state file for external monitoring
    - Rich terminal UI with live updates
    - HTML dashboard generation
    - Callback system for event handling
    - Rate and ETA calculations
    """

    def __init__(
        self,
        total_sites: int,
        output_dir: str,
        enable_terminal_ui: bool = True,
        enable_html_dashboard: bool = True,
        callback: Optional[ProgressCallback] = None,
        update_interval: float = 0.5
    ):
        """
        Initialize the progress tracker.

        Args:
            total_sites: Number of sites to crawl
            output_dir: Directory for output files (progress.json, dashboard.html)
            enable_terminal_ui: Enable rich terminal UI
            enable_html_dashboard: Enable HTML dashboard generation
            callback: Custom callback for events
            update_interval: How often to update displays (seconds)
        """
        self.total_sites = total_sites
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.enable_terminal_ui = enable_terminal_ui and RICH_AVAILABLE
        self.enable_html_dashboard = enable_html_dashboard
        self.callback = callback or DefaultCallback(verbose=False)
        self.update_interval = update_interval

        # State
        self.state = ProgressState()
        self.sites: Dict[str, SiteProgress] = {}
        self.matching = MatchingProgress()

        # Timing
        self._start_time: Optional[float] = None
        self._crawl_start_times: Dict[str, float] = {}
        self._matching_start_time: Optional[float] = None
        self._last_matching_update: Optional[float] = None

        # Recent items for display
        self._recent_products: List[Dict] = []
        self._recent_matches: List[Dict] = []
        self._max_recent = 10

        # Threading for background updates
        self._lock = threading.Lock()
        self._update_thread: Optional[threading.Thread] = None
        self._running = False

        # Rich console
        if self.enable_terminal_ui:
            self.console = Console()
            self._live: Optional[Live] = None
            self._progress: Optional[Progress] = None
            self._task_ids: Dict[str, TaskID] = {}

        # File paths
        self.progress_file = self.output_dir / "progress.json"
        self.dashboard_file = self.output_dir / "dashboard.html"

        # Initialize state
        self._init_state()

    def _init_state(self) -> None:
        """Initialize the progress state."""
        self.state = ProgressState(
            status=Status.IDLE.value,
            sites={},
            matching=asdict(MatchingProgress())
        )
        self._save_state()

    def _now(self) -> str:
        """Get current timestamp as ISO string."""
        return datetime.now().isoformat()

    def _save_state(self) -> None:
        """Save current state to JSON file."""
        with self._lock:
            # Update state from internal tracking
            self.state.sites = {name: asdict(site) for name, site in self.sites.items()}
            self.state.matching = asdict(self.matching)
            self.state.last_update = self._now()
            self.state.total_products = sum(s.products for s in self.sites.values())
            self.state.total_matches = self.matching.completed

            # Write to file
            try:
                with open(self.progress_file, 'w') as f:
                    json.dump(asdict(self.state), f, indent=2, default=str)
            except Exception as e:
                print(f"Warning: Could not save progress file: {e}")

        # Update HTML dashboard
        if self.enable_html_dashboard:
            self._generate_html_dashboard()

    def _calculate_rate(self, count: int, start_time: float) -> float:
        """Calculate rate (items per second)."""
        elapsed = time.time() - start_time
        return count / elapsed if elapsed > 0 else 0.0

    def _calculate_eta(self, completed: int, total: int, rate: float) -> Optional[float]:
        """Calculate estimated time remaining in seconds."""
        remaining = total - completed
        if rate > 0 and remaining > 0:
            return remaining / rate
        return None

    # =========================================================================
    # Public API - Crawling
    # =========================================================================

    def start_crawl(self, site_name: str, target_products: int) -> None:
        """
        Start tracking a site crawl.

        Args:
            site_name: Name of the site (e.g., "nykaa", "purplle")
            target_products: Target number of products to crawl
        """
        with self._lock:
            self.sites[site_name] = SiteProgress(
                name=site_name,
                target=target_products,
                status="crawling",
                started_at=self._now()
            )
            self._crawl_start_times[site_name] = time.time()

            if self.state.status == Status.IDLE.value:
                self.state.status = Status.CRAWLING.value
                self.state.started_at = self._now()
                self._start_time = time.time()

        self._save_state()

        if self.enable_terminal_ui:
            self._start_terminal_ui()

    def update_crawl(
        self,
        site_name: str,
        products_found: int,
        current_page: int,
        last_product: Optional[Dict] = None
    ) -> None:
        """
        Update crawl progress for a site.

        Args:
            site_name: Name of the site
            products_found: Total products found so far
            current_page: Current page being crawled
            last_product: Optional dict with info about last product found
        """
        with self._lock:
            if site_name not in self.sites:
                return

            site = self.sites[site_name]
            site.products = products_found
            site.pages = current_page

            # Calculate rate
            if site_name in self._crawl_start_times:
                site.rate = self._calculate_rate(
                    products_found,
                    self._crawl_start_times[site_name]
                )

            # Track last product
            if last_product:
                site.last_product = last_product.get('title', str(last_product))[:100]
                self._recent_products.append(last_product)
                if len(self._recent_products) > self._max_recent:
                    self._recent_products.pop(0)

                # Trigger callback
                self.callback.on_product_found(last_product)

        self._save_state()
        self._update_terminal_ui()

    def complete_crawl(self, site_name: str, final_count: Optional[int] = None) -> None:
        """
        Mark a site crawl as complete.

        Args:
            site_name: Name of the site
            final_count: Optional final product count
        """
        with self._lock:
            if site_name in self.sites:
                site = self.sites[site_name]
                site.status = "completed"
                site.completed_at = self._now()
                if final_count is not None:
                    site.products = final_count

        self._save_state()

    # =========================================================================
    # Public API - Matching
    # =========================================================================

    def start_matching(self, source_count: int, target_count: int) -> None:
        """
        Start tracking the matching phase.

        Args:
            source_count: Number of source products
            target_count: Number of target products
        """
        with self._lock:
            self.matching = MatchingProgress(
                source_count=source_count,
                target_count=target_count,
                total=source_count  # We match each source to targets
            )
            self._matching_start_time = time.time()
            self._last_matching_update = time.time()

            self.state.status = Status.MATCHING.value

        self._save_state()
        self._update_terminal_ui()

    def update_matching(
        self,
        matched: int,
        current_product: str,
        best_match: Optional[str] = None,
        score: Optional[float] = None,
        source_data: Optional[Dict] = None,
        target_data: Optional[Dict] = None
    ) -> None:
        """
        Update matching progress.

        Args:
            matched: Number of products matched so far
            current_product: Name of current product being matched
            best_match: Name of best match found
            score: Match score
            source_data: Full source product data
            target_data: Full target product data
        """
        with self._lock:
            self.matching.completed = matched
            self.matching.current = current_product[:100] if current_product else None
            self.matching.best_match = best_match[:100] if best_match else None
            self.matching.best_score = score

            # Calculate rate
            if self._matching_start_time:
                self.matching.rate = self._calculate_rate(
                    matched,
                    self._matching_start_time
                )
                self.matching.eta_seconds = self._calculate_eta(
                    matched,
                    self.matching.total,
                    self.matching.rate
                )

            # Track recent matches
            if best_match and score and score > 0:
                match_record = {
                    "source": current_product[:50],
                    "target": best_match[:50],
                    "score": round(score, 3),
                    "timestamp": self._now()
                }
                self._recent_matches.append(match_record)
                if len(self._recent_matches) > self._max_recent:
                    self._recent_matches.pop(0)
                self.matching.recent_matches = self._recent_matches.copy()

                # Trigger callback
                if source_data and target_data:
                    self.callback.on_match_found(source_data, target_data, score)

        self._save_state()
        self._update_terminal_ui()

    # =========================================================================
    # Public API - Error Handling
    # =========================================================================

    def report_error(self, error: str, context: Optional[Dict] = None) -> None:
        """
        Report an error.

        Args:
            error: Error message
            context: Optional context dictionary
        """
        with self._lock:
            error_record = {
                "error": error,
                "context": context or {},
                "timestamp": self._now()
            }
            self.state.errors.append(error_record)

            # Also add to site if relevant
            if context and "site" in context:
                site_name = context["site"]
                if site_name in self.sites:
                    self.sites[site_name].errors.append(error)

        self.callback.on_error(error, context or {})
        self._save_state()

    # =========================================================================
    # Public API - Completion
    # =========================================================================

    def complete(self) -> Dict:
        """
        Mark the entire process as complete.

        Returns:
            Final summary statistics
        """
        with self._lock:
            self.state.status = Status.COMPLETED.value
            self.state.completed_at = self._now()

        self._save_state()
        self._stop_terminal_ui()

        # Generate final summary
        summary = self._generate_summary()

        if self.enable_terminal_ui:
            self._print_final_summary(summary)

        return summary

    def _generate_summary(self) -> Dict:
        """Generate final summary statistics."""
        total_elapsed = time.time() - self._start_time if self._start_time else 0

        return {
            "status": "completed",
            "total_time_seconds": round(total_elapsed, 2),
            "total_time_formatted": str(timedelta(seconds=int(total_elapsed))),
            "sites_crawled": len(self.sites),
            "total_products": sum(s.products for s in self.sites.values()),
            "total_matches": self.matching.completed,
            "match_rate": round(
                self.matching.completed / self.matching.total * 100, 1
            ) if self.matching.total > 0 else 0,
            "errors_count": len(self.state.errors),
            "site_details": {
                name: {
                    "products": site.products,
                    "target": site.target,
                    "pages": site.pages,
                    "rate": round(site.rate, 2)
                }
                for name, site in self.sites.items()
            }
        }

    # =========================================================================
    # Terminal UI (Rich)
    # =========================================================================

    def _start_terminal_ui(self) -> None:
        """Start the rich terminal UI."""
        if not self.enable_terminal_ui:
            return

        # Will be updated in _update_terminal_ui
        pass

    def _update_terminal_ui(self) -> None:
        """Update the terminal UI display."""
        if not self.enable_terminal_ui:
            return

        self.console.clear()
        self._render_status_panel()

    def _render_status_panel(self) -> None:
        """Render the current status panel."""
        if not self.enable_terminal_ui:
            return

        # Header
        status_color = {
            Status.IDLE.value: "white",
            Status.CRAWLING.value: "yellow",
            Status.MATCHING.value: "cyan",
            Status.COMPLETED.value: "green",
            Status.ERROR.value: "red"
        }.get(self.state.status, "white")

        header = Text()
        header.append("URL-to-URL Progress Tracker\n", style="bold blue")
        header.append(f"Status: ", style="white")
        header.append(f"{self.state.status.upper()}", style=f"bold {status_color}")

        if self._start_time:
            elapsed = time.time() - self._start_time
            header.append(f"  |  Elapsed: {timedelta(seconds=int(elapsed))}", style="dim")

        self.console.print(Panel(header, title="Progress"))

        # Sites table
        if self.sites:
            sites_table = Table(title="Site Crawling Progress")
            sites_table.add_column("Site", style="cyan")
            sites_table.add_column("Products", justify="right")
            sites_table.add_column("Target", justify="right")
            sites_table.add_column("Pages", justify="right")
            sites_table.add_column("Rate", justify="right")
            sites_table.add_column("Progress", justify="center")
            sites_table.add_column("Status")

            for name, site in self.sites.items():
                progress_pct = (site.products / site.target * 100) if site.target > 0 else 0
                progress_bar = self._text_progress_bar(progress_pct, width=20)

                status_style = "green" if site.status == "completed" else "yellow"

                sites_table.add_row(
                    name,
                    str(site.products),
                    str(site.target),
                    str(site.pages),
                    f"{site.rate:.1f}/s",
                    progress_bar,
                    Text(site.status, style=status_style)
                )

            self.console.print(sites_table)

        # Matching progress
        if self.state.status == Status.MATCHING.value or self.matching.completed > 0:
            self.console.print()
            match_table = Table(title="Matching Progress")
            match_table.add_column("Metric", style="cyan")
            match_table.add_column("Value", justify="right")

            progress_pct = (
                self.matching.completed / self.matching.total * 100
            ) if self.matching.total > 0 else 0

            match_table.add_row("Completed", f"{self.matching.completed} / {self.matching.total}")
            match_table.add_row("Progress", self._text_progress_bar(progress_pct, width=30))
            match_table.add_row("Rate", f"{self.matching.rate:.2f} matches/sec")

            if self.matching.eta_seconds:
                eta = timedelta(seconds=int(self.matching.eta_seconds))
                match_table.add_row("ETA", str(eta))

            if self.matching.current:
                match_table.add_row("Current", self.matching.current[:40] + "...")

            if self.matching.best_match and self.matching.best_score:
                match_table.add_row(
                    "Best Match",
                    f"{self.matching.best_match[:30]}... ({self.matching.best_score:.2f})"
                )

            self.console.print(match_table)

        # Recent matches
        if self._recent_matches:
            self.console.print()
            recent_table = Table(title="Recent Matches")
            recent_table.add_column("Source", style="cyan", max_width=30)
            recent_table.add_column("Target", style="green", max_width=30)
            recent_table.add_column("Score", justify="right")

            for match in self._recent_matches[-5:]:
                score_style = "green" if match["score"] >= 0.8 else "yellow" if match["score"] >= 0.5 else "red"
                recent_table.add_row(
                    match["source"],
                    match["target"],
                    Text(f"{match['score']:.3f}", style=score_style)
                )

            self.console.print(recent_table)

        # Errors
        if self.state.errors:
            self.console.print()
            self.console.print(
                Panel(
                    f"[red]Errors: {len(self.state.errors)}[/red]",
                    title="Warnings"
                )
            )

    def _text_progress_bar(self, percentage: float, width: int = 20) -> str:
        """Create a text-based progress bar."""
        filled = int(width * percentage / 100)
        bar = "=" * filled + "-" * (width - filled)
        return f"[{bar}] {percentage:.1f}%"

    def _stop_terminal_ui(self) -> None:
        """Stop the terminal UI."""
        pass

    def _print_final_summary(self, summary: Dict) -> None:
        """Print final summary to terminal."""
        if not self.enable_terminal_ui:
            return

        self.console.print()
        self.console.print("=" * 60)
        self.console.print(Panel(
            Text("CRAWLING & MATCHING COMPLETE", style="bold green"),
            title="Final Summary"
        ))

        summary_table = Table()
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", justify="right")

        summary_table.add_row("Total Time", summary["total_time_formatted"])
        summary_table.add_row("Sites Crawled", str(summary["sites_crawled"]))
        summary_table.add_row("Total Products", str(summary["total_products"]))
        summary_table.add_row("Total Matches", str(summary["total_matches"]))
        summary_table.add_row("Match Rate", f"{summary['match_rate']}%")
        summary_table.add_row("Errors", str(summary["errors_count"]))

        self.console.print(summary_table)
        self.console.print("=" * 60)

    # =========================================================================
    # HTML Dashboard
    # =========================================================================

    def _generate_html_dashboard(self) -> None:
        """Generate an auto-refreshing HTML dashboard."""
        if not self.enable_html_dashboard:
            return

        # Calculate progress percentages
        site_data = []
        for name, site in self.sites.items():
            pct = (site.products / site.target * 100) if site.target > 0 else 0
            site_data.append({
                "name": name,
                "products": site.products,
                "target": site.target,
                "pages": site.pages,
                "rate": f"{site.rate:.1f}",
                "progress": round(pct, 1),
                "status": site.status
            })

        match_pct = (
            self.matching.completed / self.matching.total * 100
        ) if self.matching.total > 0 else 0

        eta_str = str(timedelta(seconds=int(self.matching.eta_seconds))) if self.matching.eta_seconds else "N/A"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>URL Mapper Progress Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.5rem;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.9rem;
        }}
        .status-crawling {{ background: #f59e0b; color: #000; }}
        .status-matching {{ background: #06b6d4; color: #000; }}
        .status-completed {{ background: #10b981; color: #000; }}
        .status-idle {{ background: #6b7280; }}
        .status-error {{ background: #ef4444; }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .card h3 {{
            color: #00d4ff;
            margin-bottom: 16px;
            font-size: 1.2rem;
        }}
        .progress-container {{
            background: rgba(0, 0, 0, 0.3);
            border-radius: 10px;
            height: 24px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .progress-bar {{
            height: 100%;
            border-radius: 10px;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 0.8rem;
        }}
        .progress-crawl {{
            background: linear-gradient(90deg, #f59e0b, #fbbf24);
            color: #000;
        }}
        .progress-match {{
            background: linear-gradient(90deg, #06b6d4, #22d3ee);
            color: #000;
        }}
        .stat {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        .stat:last-child {{
            border-bottom: none;
        }}
        .stat-value {{
            font-weight: bold;
            color: #00ff88;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }}
        th {{
            color: #00d4ff;
            font-weight: 600;
        }}
        .score-high {{ color: #10b981; }}
        .score-medium {{ color: #f59e0b; }}
        .score-low {{ color: #ef4444; }}

        .timestamp {{
            text-align: center;
            color: #6b7280;
            font-size: 0.85rem;
            margin-top: 20px;
        }}
        .pulse {{
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>URL-to-URL Mapper</h1>
            <span class="status-badge status-{self.state.status}">{self.state.status.upper()}</span>
            {'<span class="pulse" style="margin-left: 10px;">Processing...</span>' if self.state.status in ['crawling', 'matching'] else ''}
        </div>

        <div class="grid">
            <!-- Site Progress Cards -->
            {''.join(f"""
            <div class="card">
                <h3>{site['name'].upper()}</h3>
                <div class="progress-container">
                    <div class="progress-bar progress-crawl" style="width: {site['progress']}%">
                        {site['progress']:.1f}%
                    </div>
                </div>
                <div class="stat">
                    <span>Products</span>
                    <span class="stat-value">{site['products']} / {site['target']}</span>
                </div>
                <div class="stat">
                    <span>Pages</span>
                    <span class="stat-value">{site['pages']}</span>
                </div>
                <div class="stat">
                    <span>Rate</span>
                    <span class="stat-value">{site['rate']}/s</span>
                </div>
                <div class="stat">
                    <span>Status</span>
                    <span class="stat-value">{site['status']}</span>
                </div>
            </div>
            """ for site in site_data)}

            <!-- Matching Progress Card -->
            <div class="card">
                <h3>MATCHING PROGRESS</h3>
                <div class="progress-container">
                    <div class="progress-bar progress-match" style="width: {match_pct:.1f}%">
                        {match_pct:.1f}%
                    </div>
                </div>
                <div class="stat">
                    <span>Completed</span>
                    <span class="stat-value">{self.matching.completed} / {self.matching.total}</span>
                </div>
                <div class="stat">
                    <span>Rate</span>
                    <span class="stat-value">{self.matching.rate:.2f}/s</span>
                </div>
                <div class="stat">
                    <span>ETA</span>
                    <span class="stat-value">{eta_str}</span>
                </div>
                {f'''<div class="stat">
                    <span>Current</span>
                    <span class="stat-value" style="font-size: 0.8rem;">{self.matching.current[:30] if self.matching.current else "N/A"}...</span>
                </div>''' if self.matching.current else ''}
            </div>
        </div>

        <!-- Recent Matches Table -->
        {f'''
        <div class="card">
            <h3>RECENT MATCHES</h3>
            <table>
                <thead>
                    <tr>
                        <th>Source</th>
                        <th>Target</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(f"""
                    <tr>
                        <td>{match['source']}</td>
                        <td>{match['target']}</td>
                        <td class="{'score-high' if match['score'] >= 0.8 else 'score-medium' if match['score'] >= 0.5 else 'score-low'}">{match['score']:.3f}</td>
                    </tr>
                    """ for match in self._recent_matches[-10:])}
                </tbody>
            </table>
        </div>
        ''' if self._recent_matches else ''}

        <!-- Errors -->
        {f'''
        <div class="card" style="border-color: rgba(239, 68, 68, 0.5);">
            <h3 style="color: #ef4444;">ERRORS ({len(self.state.errors)})</h3>
            {''.join(f"<p style='color: #fca5a5; margin: 8px 0;'>{err['error']}</p>" for err in self.state.errors[-5:])}
        </div>
        ''' if self.state.errors else ''}

        <p class="timestamp">Last updated: {self.state.last_update}</p>
    </div>
</body>
</html>"""

        try:
            with open(self.dashboard_file, 'w') as f:
                f.write(html)
        except Exception as e:
            print(f"Warning: Could not write HTML dashboard: {e}")

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    def __enter__(self) -> 'ProgressTracker':
        """Enter context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager."""
        if exc_type is not None:
            self.report_error(str(exc_val), {"exception_type": str(exc_type)})
            self.state.status = Status.ERROR.value
            self._save_state()
        elif self.state.status != Status.COMPLETED.value:
            self.complete()


# =========================================================================
# Utility Functions
# =========================================================================

def load_progress(output_dir: str) -> Optional[Dict]:
    """
    Load progress from a progress.json file.

    Args:
        output_dir: Directory containing progress.json

    Returns:
        Progress data dict or None if not found
    """
    progress_file = Path(output_dir) / "progress.json"
    if progress_file.exists():
        try:
            with open(progress_file) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def watch_progress(output_dir: str, callback: Callable[[Dict], None], interval: float = 1.0) -> None:
    """
    Watch progress file and call callback on changes.

    Args:
        output_dir: Directory containing progress.json
        callback: Function to call with progress data
        interval: Check interval in seconds
    """
    progress_file = Path(output_dir) / "progress.json"
    last_mtime = 0

    while True:
        try:
            if progress_file.exists():
                mtime = progress_file.stat().st_mtime
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(progress_file) as f:
                        data = json.load(f)
                    callback(data)

                    if data.get("status") == "completed":
                        break

            time.sleep(interval)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Watch error: {e}")
            time.sleep(interval)


# =========================================================================
# Main - Demo/Test
# =========================================================================

if __name__ == "__main__":
    # Demo the progress tracker
    import random

    print("=" * 60)
    print("Progress Tracker Demo")
    print("=" * 60)

    # Create tracker
    tracker = ProgressTracker(
        total_sites=2,
        output_dir="output/demo",
        enable_terminal_ui=RICH_AVAILABLE,
        enable_html_dashboard=True
    )

    print(f"\nProgress file: {tracker.progress_file}")
    print(f"Dashboard file: {tracker.dashboard_file}")
    print("\nOpen dashboard.html in a browser to see live updates!")
    print("-" * 60)

    # Simulate crawling
    sites = [
        ("nykaa", 25),
        ("purplle", 30)
    ]

    for site_name, target in sites:
        tracker.start_crawl(site_name, target)

        products_found = 0
        page = 1

        while products_found < target:
            # Simulate finding products
            time.sleep(0.2)
            batch = random.randint(3, 8)
            products_found = min(products_found + batch, target)

            tracker.update_crawl(
                site_name,
                products_found,
                page,
                last_product={"title": f"Sample Product {products_found}", "url": f"http://example.com/{products_found}"}
            )

            if products_found < target and random.random() > 0.7:
                page += 1

        tracker.complete_crawl(site_name, products_found)

    # Simulate matching
    total_source = 25
    total_target = 30

    tracker.start_matching(total_source, total_target)

    for i in range(total_source):
        time.sleep(0.1)

        score = random.uniform(0.3, 0.98)
        tracker.update_matching(
            matched=i + 1,
            current_product=f"Source Product {i + 1}",
            best_match=f"Target Product {random.randint(1, total_target)}",
            score=score,
            source_data={"title": f"Source {i+1}"},
            target_data={"title": f"Target {random.randint(1, total_target)}"}
        )

    # Complete
    summary = tracker.complete()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print(f"Summary: {json.dumps(summary, indent=2)}")
