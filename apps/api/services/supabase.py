"""
Supabase Service for URL-to-URL Product Matching API
Uses RPC functions to access url_to_url schema tables
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from supabase import create_client, Client

from models.schemas import (
    CrawlJob, CrawlJobCreate, CrawlJobUpdate,
    Product, ProductCreate,
    Match, MatchCreate, MatchUpdate,
    JobProgress, JobProgressCreate,
    Organization, OrganizationCreate,
    JobStatus, MatchStatus, ConfidenceTier, Site
)

logger = logging.getLogger(__name__)


class SupabaseService:
    """
    Service for interacting with Supabase database.
    Uses RPC functions to access url_to_url schema tables.
    """

    # Schema name (for reference in health checks)
    SCHEMA = "url_to_url"

    def __init__(self):
        """Initialize Supabase client."""
        self._client: Optional[Client] = None
        self._initialized = False
        # Get Supabase URL from environment with secure default
        self.SUPABASE_URL = os.environ.get(
            "SUPABASE_URL",
            "https://qyjzqzqqjimittltttph.supabase.co"
        )

    @property
    def client(self) -> Client:
        """Get or create Supabase client."""
        if self._client is None:
            supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
            if not supabase_key:
                raise ValueError("SUPABASE_KEY or SUPABASE_SERVICE_KEY environment variable is required")

            self._client = create_client(self.SUPABASE_URL, supabase_key)
            self._initialized = True
            logger.info(f"Supabase client initialized for {self.SUPABASE_URL}")

        return self._client

    def is_connected(self) -> bool:
        """Check if Supabase is connected."""
        try:
            result = self.client.rpc('url_list_organizations').execute()
            return True
        except Exception as e:
            logger.error(f"Supabase connection check failed: {e}")
            return False

    # =========================================================================
    # Organization Operations
    # =========================================================================

    async def create_organization(self, org: OrganizationCreate) -> Organization:
        """Create a new organization."""
        try:
            result = self.client.rpc('url_create_organization', {
                'p_name': org.name
            }).execute()

            if result.data:
                return self._parse_organization(result.data)
            raise Exception("Failed to create organization")
        except Exception as e:
            logger.error(f"Error creating organization: {e}")
            raise

    async def list_organizations(self) -> List[Organization]:
        """List all organizations."""
        try:
            result = self.client.rpc('url_list_organizations').execute()
            return [self._parse_organization(o) for o in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error listing organizations: {e}")
            return []

    def _parse_organization(self, data: dict) -> Organization:
        """Parse organization data."""
        return Organization(
            id=UUID(data["id"]),
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        )

    # =========================================================================
    # Crawl Job Operations
    # =========================================================================

    async def create_job(self, job: CrawlJobCreate) -> CrawlJob:
        """Create a new crawl job."""
        try:
            result = self.client.rpc('url_create_job', {
                'p_name': job.name,
                'p_site_a_url': job.site_a_url,
                'p_site_b_url': job.site_b_url,
                'p_categories': job.categories or [],
                'p_config': job.config.model_dump() if job.config else {}
            }).execute()

            if result.data:
                return self._parse_job(result.data)
            raise Exception("Failed to create job")
        except Exception as e:
            logger.error(f"Error creating job: {e}")
            raise

    async def get_job(self, job_id: UUID) -> Optional[CrawlJob]:
        """Get job by ID."""
        try:
            result = self.client.rpc('url_get_job', {'p_job_id': str(job_id)}).execute()
            if result.data:
                return self._parse_job(result.data)
            return None
        except Exception as e:
            logger.error(f"Error fetching job: {e}")
            return None

    async def list_jobs(
        self,
        org_id: Optional[UUID] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[CrawlJob], int]:
        """List jobs with optional filters."""
        try:
            result = self.client.rpc('url_list_jobs', {
                'p_limit': limit,
                'p_offset': offset
            }).execute()

            jobs = [self._parse_job(j) for j in result.data] if result.data else []

            # Filter by status if provided (since RPC doesn't support it yet)
            if status:
                jobs = [j for j in jobs if j.status == status]

            return jobs, len(jobs)
        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return [], 0

    async def update_job_status(
        self,
        job_id: UUID,
        status: JobStatus,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None
    ) -> bool:
        """Update job status and timestamps."""
        try:
            result = self.client.rpc('url_update_job_status', {
                'p_job_id': str(job_id),
                'p_status': status.value,
                'p_started_at': started_at.isoformat() if started_at else None,
                'p_completed_at': completed_at.isoformat() if completed_at else None
            }).execute()
            return bool(result.data)
        except Exception as e:
            logger.error(f"Error updating job status: {e}")
            return False

    async def update_job(self, job_id: UUID, update: CrawlJobUpdate) -> Optional[CrawlJob]:
        """Update job fields (name, config, etc.)."""
        try:
            result = self.client.rpc('url_update_job', {
                'p_job_id': str(job_id),
                'p_name': update.name,
                'p_categories': update.categories,
                'p_config': update.config.model_dump() if update.config else None
            }).execute()
            if result.data:
                return self._parse_job(result.data)
            return None
        except Exception as e:
            logger.error(f"Error updating job: {e}")
            return None

    async def delete_job(self, job_id: UUID) -> bool:
        """Delete a job."""
        try:
            # Use direct RPC or SQL for delete
            result = self.client.rpc('url_delete_job', {'p_job_id': str(job_id)}).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting job: {e}")
            return False

    def _parse_job(self, data: dict) -> CrawlJob:
        """Parse job data from database."""
        return CrawlJob(
            id=UUID(data["id"]),
            org_id=UUID(data["org_id"]) if data.get("org_id") else None,
            name=data["name"],
            site_a_url=data["site_a_url"],
            site_b_url=data["site_b_url"],
            categories=data.get("categories", []),
            config=data.get("config", {}),
            status=JobStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            started_at=datetime.fromisoformat(data["started_at"].replace("Z", "+00:00")) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00")) if data.get("completed_at") else None
        )

    # =========================================================================
    # Product Operations
    # =========================================================================

    async def create_product(self, product: ProductCreate) -> Product:
        """Create a new product."""
        try:
            result = self.client.rpc('url_create_product', {
                'p_job_id': str(product.job_id),
                'p_site': product.site.value,
                'p_url': product.url,
                'p_title': product.title,
                'p_brand': product.brand,
                'p_category': product.category,
                'p_price': float(product.price) if product.price else None,
                'p_metadata': product.metadata or {}
            }).execute()

            if result.data:
                return self._parse_product(result.data)
            raise Exception("Failed to create product")
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            raise

    async def create_products_bulk(self, products: List[ProductCreate]) -> List[Product]:
        """Create multiple products."""
        created = []
        for p in products:
            try:
                prod = await self.create_product(p)
                created.append(prod)
            except Exception as e:
                logger.error(f"Error creating product {p.url}: {e}")
        return created

    async def get_product(self, product_id: UUID) -> Optional[Product]:
        """Get a single product by ID."""
        try:
            result = self.client.rpc('url_get_product', {
                'p_product_id': str(product_id)
            }).execute()

            if result.data:
                return self._parse_product(result.data)
            return None
        except Exception as e:
            logger.error(f"Error fetching product {product_id}: {e}")
            return None

    async def get_products_by_job(
        self,
        job_id: UUID,
        site: Optional[Site] = None
    ) -> List[Product]:
        """Get products for a job."""
        try:
            result = self.client.rpc('url_get_products_by_job', {
                'p_job_id': str(job_id),
                'p_site': site.value if site else None
            }).execute()

            return [self._parse_product(p) for p in result.data] if result.data else []
        except Exception as e:
            logger.error(f"Error fetching products: {e}")
            return []

    async def get_products_by_site(
        self,
        job_id: UUID,
        site: Site,
        with_embeddings: bool = False
    ) -> List[Product]:
        """Get products by site for vector operations. Alias for get_products_by_job with required site."""
        return await self.get_products_by_job(job_id, site)

    def _parse_product(self, data: dict) -> Product:
        """Parse product data from database."""
        return Product(
            id=UUID(data["id"]),
            job_id=UUID(data["job_id"]),
            site=Site(data["site"]),
            url=data["url"],
            title=data["title"],
            brand=data.get("brand"),
            category=data.get("category"),
            price=float(data["price"]) if data.get("price") else None,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        )

    # =========================================================================
    # Match Operations
    # =========================================================================

    async def get_match(self, match_id: UUID) -> Optional[Match]:
        """Get a single match by ID."""
        try:
            result = self.client.rpc('url_get_match', {
                'p_match_id': str(match_id)
            }).execute()

            if result.data:
                return self._parse_match(result.data)
            return None
        except Exception as e:
            logger.error(f"Error fetching match {match_id}: {e}")
            return None

    async def create_match(self, match: MatchCreate) -> Match:
        """Create a new match."""
        try:
            result = self.client.rpc('url_create_match', {
                'p_job_id': str(match.job_id),
                'p_source_product_id': str(match.source_product_id),
                'p_matched_product_id': str(match.matched_product_id),
                'p_score': float(match.score),
                'p_confidence_tier': match.confidence_tier.value,
                'p_explanation': match.explanation
            }).execute()

            if result.data:
                return self._parse_match(result.data)
            raise Exception("Failed to create match")
        except Exception as e:
            logger.error(f"Error creating match: {e}")
            raise

    async def create_matches_bulk(self, matches: List[MatchCreate]) -> List[Match]:
        """Create multiple matches."""
        created = []
        for m in matches:
            try:
                match = await self.create_match(m)
                created.append(match)
            except Exception as e:
                logger.error(f"Error creating match: {e}")
        return created

    async def get_matches_by_job(
        self,
        job_id: UUID,
        status: Optional[MatchStatus] = None,
        confidence_tier: Optional[ConfidenceTier] = None,
        min_score: Optional[float] = None,
        needs_review: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[Dict[str, Any]], int]:
        """Get matches for a job with product details."""
        try:
            result = self.client.rpc('url_get_matches_by_job', {
                'p_job_id': str(job_id),
                'p_limit': limit,
                'p_offset': offset
            }).execute()

            matches = result.data or []

            # Apply filters
            if status:
                matches = [m for m in matches if m.get('status') == status.value]
            if confidence_tier:
                matches = [m for m in matches if m.get('confidence_tier') == confidence_tier.value]
            if min_score is not None:
                matches = [m for m in matches if float(m.get('score', 0)) >= min_score]
            if needs_review:
                review_tiers = ['likely_match', 'manual_review', 'no_match']
                matches = [m for m in matches if m.get('confidence_tier') in review_tiers]

            return matches, len(matches)
        except Exception as e:
            logger.error(f"Error fetching matches: {e}")
            return [], 0

    async def update_match(self, match_id: UUID, update: MatchUpdate) -> Optional[Match]:
        """Update match status."""
        try:
            result = self.client.rpc('url_update_match_status', {
                'p_match_id': str(match_id),
                'p_status': update.status.value
            }).execute()

            if result.data:
                return self._parse_match(result.data)
            return None
        except Exception as e:
            logger.error(f"Error updating match: {e}")
            return None

    async def update_matches_bulk(
        self,
        match_ids: List[UUID],
        status: MatchStatus
    ) -> int:
        """Bulk update match status. Returns count of updated matches."""
        try:
            updated = 0
            for match_id in match_ids:
                result = self.client.rpc('url_update_match_status', {
                    'p_match_id': str(match_id),
                    'p_status': status.value
                }).execute()
                if result.data:
                    updated += 1
            return updated
        except Exception as e:
            logger.error(f"Error bulk updating matches: {e}")
            return 0

    async def get_job_match_stats(self, job_id: UUID) -> Dict[str, Any]:
        """Get match statistics for a job."""
        try:
            result = self.client.rpc('url_get_job_stats', {'p_job_id': str(job_id)}).execute()

            if result.data and len(result.data) > 0:
                stats = result.data[0]
                return {
                    "total_matches": stats.get("total_matches", 0),
                    "avg_score": float(stats.get("avg_score", 0)) if stats.get("avg_score") else 0,
                    "status_distribution": {
                        "pending": stats.get("pending_count", 0),
                        "approved": stats.get("approved_count", 0),
                        "rejected": stats.get("rejected_count", 0)
                    },
                    "needs_review_count": stats.get("needs_review_count", 0)
                }
            return {
                "total_matches": 0,
                "avg_score": 0,
                "status_distribution": {},
                "needs_review_count": 0
            }
        except Exception as e:
            logger.error(f"Error getting match stats: {e}")
            return {}

    def _parse_match(self, data: dict) -> Match:
        """Parse match data from database."""
        return Match(
            id=UUID(data["id"]),
            job_id=UUID(data["job_id"]),
            source_product_id=UUID(data["source_product_id"]),
            matched_product_id=UUID(data["matched_product_id"]),
            score=float(data["score"]),
            confidence_tier=ConfidenceTier(data["confidence_tier"]),
            explanation=data.get("explanation"),
            status=MatchStatus(data["status"]),
            reviewed_by=UUID(data["reviewed_by"]) if data.get("reviewed_by") else None,
            reviewed_at=datetime.fromisoformat(data["reviewed_at"].replace("Z", "+00:00")) if data.get("reviewed_at") else None,
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        )


# Global instance for dependency injection
_supabase_service: Optional[SupabaseService] = None


def get_supabase_service() -> SupabaseService:
    """Get or create Supabase service instance."""
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service
