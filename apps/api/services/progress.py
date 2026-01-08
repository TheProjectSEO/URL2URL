"""
Progress Tracking Service for URL-to-URL Product Matching

Tracks job progress through multiple stages:
- crawling_site_a: Crawling source products
- crawling_site_b: Crawling target products
- generating_embeddings: Creating vector embeddings
- matching: Finding product matches
- completed: Job finished

Supports both in-memory tracking (for fast access) and
Supabase persistence (for durability and multi-instance deployments).
"""

import asyncio
import logging
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict
from dataclasses import dataclass, field
from enum import Enum

from services.supabase import get_supabase_service

logger = logging.getLogger(__name__)


class ProgressStage(str, Enum):
    """Progress stages for job execution."""
    PENDING = "pending"
    STARTED = "started"
    CRAWLING_SITE_A = "crawling_site_a"
    CRAWLING_SITE_B = "crawling_site_b"
    GENERATING_EMBEDDINGS = "generating_embeddings"
    MATCHING = "matching"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobProgress:
    """
    Data class representing current job progress.

    Attributes:
        job_id: UUID of the job being tracked
        stage: Current processing stage
        current: Number of items processed in current stage
        total: Total items to process in current stage
        rate: Processing rate (items per second)
        eta_seconds: Estimated time remaining in seconds
        message: Human-readable status message
        started_at: When tracking started
        updated_at: Last update timestamp
    """
    job_id: Optional[UUID] = None
    stage: str = "pending"
    current: int = 0
    total: int = 0
    rate: float = 0.0
    eta_seconds: int = 0
    message: str = ""
    started_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total == 0:
            return 0.0
        return round((self.current / self.total) * 100, 1)

    @property
    def is_complete(self) -> bool:
        """Check if current stage is complete."""
        return self.current >= self.total and self.total > 0

    def calculate_rate_and_eta(self):
        """Calculate processing rate and ETA based on progress."""
        if not self.started_at or self.current == 0:
            return

        elapsed = (datetime.utcnow() - self.started_at).total_seconds()
        if elapsed > 0:
            self.rate = self.current / elapsed
            remaining = self.total - self.current
            if self.rate > 0:
                self.eta_seconds = int(remaining / self.rate)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "job_id": str(self.job_id) if self.job_id else None,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "percentage": self.percentage,
            "rate": round(self.rate, 2),
            "eta_seconds": self.eta_seconds,
            "message": self.message,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class ProgressTracker:
    """
    Track and persist job progress through pipeline stages.

    Provides both instance-based and class-level tracking:
    - Instance methods: For tracking a specific job through its lifecycle
    - Class methods: For quick updates and queries (backwards compatible)

    Usage (Instance-based - recommended):
        tracker = ProgressTracker(job_id)

        # Start a stage
        await tracker.start_stage(ProgressStage.CRAWLING_SITE_A, total=100)

        # Update progress
        for i, item in enumerate(items):
            await tracker.update_progress(i + 1, f"Crawling {item.url}")

        # Complete stage
        await tracker.complete_stage()

        # Finish entire job
        await tracker.finish_job()

    Usage (Class-level - backwards compatible):
        await ProgressTracker.update(job_id, "matching", current=50, total=100)
        progress = await ProgressTracker.get(job_id)
    """

    # Class-level in-memory storage for fast access
    _progress: Dict[str, JobProgress] = {}
    _lock = asyncio.Lock()

    def __init__(self, job_id: UUID):
        """
        Initialize progress tracker for a job.

        Args:
            job_id: UUID of the job to track
        """
        self.job_id = job_id
        self.supabase = get_supabase_service()
        self._start_time: Optional[datetime] = None
        self._stage_start_time: Optional[datetime] = None
        self._items_processed: int = 0
        self._current_stage: str = ProgressStage.PENDING.value
        self._total: int = 0
        self._last_update_time: Optional[datetime] = None
        self._update_interval: float = 0.5  # Minimum seconds between DB updates

    async def start_stage(
        self,
        stage: ProgressStage,
        total: int,
        message: str = "Starting..."
    ):
        """
        Start tracking a new pipeline stage.

        Args:
            stage: The stage being started
            total: Total items to process in this stage
            message: Initial status message
        """
        self._stage_start_time = datetime.utcnow()
        self._items_processed = 0
        self._current_stage = stage.value
        self._total = total

        if self._start_time is None:
            self._start_time = self._stage_start_time

        logger.info(f"Job {self.job_id}: Starting stage {stage.value} with {total} items")
        await self._persist(stage.value, 0, total, message)

    async def update_progress(
        self,
        current: int,
        message: str = "",
        force: bool = False
    ):
        """
        Update progress for current stage.

        Args:
            current: Number of items processed
            message: Status message
            force: Force update even if within throttle interval
        """
        self._items_processed = current

        # Throttle updates to reduce database load
        now = datetime.utcnow()
        if not force and self._last_update_time:
            elapsed = (now - self._last_update_time).total_seconds()
            if elapsed < self._update_interval:
                return

        # Calculate rate
        elapsed = (now - self._stage_start_time).total_seconds() if self._stage_start_time else 0
        rate = current / elapsed if elapsed > 0 else 0

        # Generate default message if not provided
        if not message:
            message = self._get_default_message(self._current_stage, current, self._total)

        self._last_update_time = now
        await self._persist(self._current_stage, current, self._total, message, rate)

    async def increment(self, message: str = ""):
        """
        Increment progress by one item.

        Args:
            message: Status message
        """
        self._items_processed += 1
        await self.update_progress(self._items_processed, message)

    async def complete_stage(self, message: str = "Complete"):
        """
        Mark current stage as complete.

        Args:
            message: Completion message
        """
        logger.info(f"Job {self.job_id}: Stage {self._current_stage} complete")
        await self._persist(
            self._current_stage,
            self._total,
            self._total,
            message,
            rate=0
        )

    async def fail(self, error_message: str):
        """
        Mark job as failed.

        Args:
            error_message: Error description
        """
        logger.error(f"Job {self.job_id} failed: {error_message}")
        await self._persist(
            ProgressStage.FAILED.value,
            self._items_processed,
            self._total,
            f"Failed: {error_message}",
            rate=0
        )

    async def finish_job(self, message: str = "Job completed successfully"):
        """
        Mark entire job as completed.

        Args:
            message: Final completion message
        """
        elapsed = 0
        if self._start_time:
            elapsed = (datetime.utcnow() - self._start_time).total_seconds()

        logger.info(f"Job {self.job_id} completed in {elapsed:.1f} seconds")
        await self._persist(
            ProgressStage.COMPLETED.value,
            1,
            1,
            message,
            rate=0
        )

    async def _persist(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        rate: float = 0
    ):
        """
        Persist progress to both in-memory cache and database.

        Args:
            stage: Current stage name
            current: Items processed
            total: Total items
            message: Status message
            rate: Processing rate (items/second)
        """
        # Calculate ETA
        eta = 0
        if rate > 0 and current < total:
            eta = int((total - current) / rate)

        # Update in-memory cache
        job_key = str(self.job_id)
        async with self._lock:
            if job_key not in self._progress:
                self._progress[job_key] = JobProgress(
                    job_id=self.job_id,
                    started_at=self._start_time or datetime.utcnow()
                )

            progress = self._progress[job_key]
            progress.stage = stage
            progress.current = current
            progress.total = total
            progress.rate = rate
            progress.eta_seconds = eta
            progress.message = message
            progress.updated_at = datetime.utcnow()

        # Persist to Supabase
        try:
            self.supabase.client.rpc('url_update_progress', {
                'p_job_id': str(self.job_id),
                'p_stage': stage,
                'p_current': current,
                'p_total': total,
                'p_rate': round(rate, 2),
                'p_eta_seconds': eta,
                'p_message': message[:500] if message else ""  # Truncate long messages
            }).execute()
        except Exception as e:
            # Log but don't fail the job for progress tracking errors
            logger.warning(f"Failed to persist progress for job {self.job_id}: {e}")

    # =========================================================================
    # Class methods for backwards compatibility and quick access
    # =========================================================================

    @classmethod
    async def update(
        cls,
        job_id: UUID,
        stage: str,
        current: int = 0,
        total: int = 0,
        message: str = ""
    ) -> JobProgress:
        """
        Update progress for a job (class method for backwards compatibility).

        Args:
            job_id: The job UUID
            stage: Current stage
            current: Current progress count
            total: Total items to process
            message: Optional progress message

        Returns:
            Updated JobProgress object
        """
        job_key = str(job_id)

        async with cls._lock:
            if job_key not in cls._progress:
                cls._progress[job_key] = JobProgress(
                    job_id=job_id,
                    started_at=datetime.utcnow()
                )

            progress = cls._progress[job_key]
            progress.stage = stage
            progress.current = current
            progress.total = total
            progress.message = message or cls._get_default_message(stage, current, total)
            progress.updated_at = datetime.utcnow()
            progress.calculate_rate_and_eta()

            logger.debug(
                f"Progress update - Job {job_id}: {stage} {current}/{total} "
                f"({progress.rate:.1f}/s, ETA: {progress.eta_seconds}s)"
            )

        # Persist to Supabase
        try:
            supabase = get_supabase_service()
            supabase.client.rpc('url_update_progress', {
                'p_job_id': str(job_id),
                'p_stage': stage,
                'p_current': current,
                'p_total': total,
                'p_rate': round(progress.rate, 2),
                'p_eta_seconds': progress.eta_seconds,
                'p_message': progress.message[:500] if progress.message else ""
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to persist progress for job {job_id}: {e}")

        return progress

    @classmethod
    async def get(cls, job_id: UUID) -> Optional[JobProgress]:
        """
        Get current progress for a job.

        First checks in-memory cache, then falls back to Supabase.

        Args:
            job_id: UUID of the job

        Returns:
            JobProgress if found, None otherwise
        """
        job_key = str(job_id)

        # Check in-memory cache first
        async with cls._lock:
            if job_key in cls._progress:
                return cls._progress[job_key]

        # Fall back to Supabase
        try:
            supabase = get_supabase_service()
            result = supabase.client.rpc('url_get_progress', {
                'p_job_id': str(job_id)
            }).execute()

            if result.data:
                data = result.data
                # Handle both single object and array responses
                if isinstance(data, list):
                    if len(data) == 0:
                        return None
                    data = data[0]

                return JobProgress(
                    job_id=job_id,
                    stage=data.get('stage', 'pending'),
                    current=int(data.get('current_count', 0) or 0),
                    total=int(data.get('total_count', 0) or 0),
                    rate=float(data.get('rate', 0) or 0),
                    eta_seconds=int(data.get('eta_seconds', 0) or 0),
                    message=data.get('message', ''),
                    updated_at=datetime.fromisoformat(
                        data['updated_at'].replace('Z', '+00:00')
                    ) if data.get('updated_at') else datetime.utcnow()
                )
        except Exception as e:
            logger.error(f"Error getting progress for job {job_id}: {e}")
        return None

    @classmethod
    async def remove(cls, job_id: UUID) -> bool:
        """
        Remove progress tracking for a completed/failed job.

        Removes from both in-memory cache and Supabase.

        Args:
            job_id: UUID of the job

        Returns:
            True if removed, False otherwise
        """
        job_key = str(job_id)
        removed = False

        async with cls._lock:
            if job_key in cls._progress:
                del cls._progress[job_key]
                removed = True

        # Also remove from Supabase
        try:
            supabase = get_supabase_service()
            supabase.client.rpc('url_delete_progress', {
                'p_job_id': str(job_id)
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to delete progress from DB for job {job_id}: {e}")

        return removed

    @classmethod
    async def set_completed(cls, job_id: UUID, message: str = ""):
        """Mark job as completed."""
        await cls.update(
            job_id,
            stage=ProgressStage.COMPLETED.value,
            current=1,
            total=1,
            message=message or "Job completed successfully"
        )

    @classmethod
    async def set_failed(cls, job_id: UUID, message: str = ""):
        """Mark job as failed."""
        await cls.update(
            job_id,
            stage=ProgressStage.FAILED.value,
            message=message or "Job failed"
        )

    @staticmethod
    def _get_default_message(stage: str, current: int, total: int) -> str:
        """Generate default progress message based on stage."""
        stage_messages = {
            "pending": "Waiting to start...",
            "started": "Initializing job...",
            "crawling_site_a": f"Crawling Site A products ({current}/{total})",
            "crawling_site_b": f"Crawling Site B products ({current}/{total})",
            "generating_embeddings": f"Generating embeddings ({current}/{total})",
            "matching": f"Matching products ({current}/{total})",
            "completed": "Job completed successfully",
            "failed": "Job failed"
        }
        return stage_messages.get(stage, f"{stage}: {current}/{total}")


# =========================================================================
# Convenience functions
# =========================================================================

async def track_progress(
    job_id: UUID,
    stage: str,
    current: int = 0,
    total: int = 0,
    message: str = ""
) -> None:
    """
    Convenience function to update job progress.

    Args:
        job_id: The job UUID
        stage: Current stage
        current: Items processed
        total: Total items
        message: Status message
    """
    await ProgressTracker.update(job_id, stage, current, total, message)


def create_progress_tracker(job_id: UUID) -> ProgressTracker:
    """
    Create a new progress tracker instance for a job.

    Args:
        job_id: UUID of the job to track

    Returns:
        ProgressTracker instance
    """
    return ProgressTracker(job_id)
