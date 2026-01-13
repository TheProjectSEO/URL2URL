"""
Pydantic models for URL-to-URL Product Matching API
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator


# =============================================================================
# Enums
# =============================================================================

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MatchStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ConfidenceTier(str, Enum):
    EXACT_MATCH = "exact_match"
    HIGH_CONFIDENCE = "high_confidence"
    GOOD_MATCH = "good_match"
    LIKELY_MATCH = "likely_match"
    MANUAL_REVIEW = "manual_review"
    NO_MATCH = "no_match"


class Site(str, Enum):
    SITE_A = "site_a"
    SITE_B = "site_b"


# =============================================================================
# Organization Schemas
# =============================================================================

class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class OrganizationCreate(OrganizationBase):
    pass


class Organization(OrganizationBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Crawl Job Schemas
# =============================================================================

class JobConfig(BaseModel):
    """Configuration options for crawl jobs"""
    top_k: int = Field(default=25, ge=1, le=100, description="Number of candidates to consider")
    model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    batch_size: int = Field(default=32, ge=1, le=128)
    ai_validation_enabled: bool = Field(default=False, description="Enable AI validation for borderline matches")
    ai_validation_min: float = Field(default=0.70, ge=0.0, le=1.0)
    ai_validation_max: float = Field(default=0.90, ge=0.0, le=1.0)
    ai_validation_cap: int = Field(default=100, ge=0)
    # Text matching enhancements
    embed_enriched_text: bool = Field(default=False, description="Embed title+brand+category for better semantics")
    token_norm_v2: bool = Field(default=False, description="Use improved token normalization for overlap scoring")
    # Ontologies & variants
    use_brand_ontology: bool = Field(default=False, description="Canonicalize brand via alias mapping")
    use_category_ontology: bool = Field(default=False, description="Use category synonyms/related mapping")
    use_variant_extractor: bool = Field(default=False, description="Parse and compare size/shade/model variants")
    # OCR image text signal
    use_ocr_text: bool = Field(default=False, description="Use OCR text from product images as visual signal")
    ocr_max_comparisons: int = Field(default=500, ge=0, description="Max image pairs to OCR per job")


class CrawlJobBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Job name")
    site_a_url: str = Field(..., description="URL of Site A (source)")
    site_b_url: str = Field(..., description="URL of Site B (target)")
    categories: List[str] = Field(default_factory=list, description="Categories to crawl")
    config: JobConfig = Field(default_factory=JobConfig)


class CrawlJobCreate(CrawlJobBase):
    org_id: Optional[UUID] = None


class CrawlJobUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    categories: Optional[List[str]] = None
    config: Optional[JobConfig] = None


class CrawlJob(CrawlJobBase):
    id: UUID
    org_id: Optional[UUID] = None
    status: JobStatus = JobStatus.PENDING
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CrawlJobWithStats(CrawlJob):
    """Job with additional statistics"""
    total_matches: int = 0
    high_confidence_matches: int = 0
    needs_review_count: int = 0
    products_site_a: int = 0
    products_site_b: int = 0


# =============================================================================
# Product Schemas
# =============================================================================

class ProductBase(BaseModel):
    url: str = Field(..., description="Product URL")
    title: str = Field(..., min_length=1, description="Product title")
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    metadata: dict = Field(default_factory=dict)


class ProductCreate(ProductBase):
    job_id: UUID
    site: Site


class Product(ProductBase):
    id: UUID
    job_id: UUID
    site: Site
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Match Schemas
# =============================================================================

class MatchBase(BaseModel):
    score: float = Field(..., ge=0, le=1, description="Match score (0-1)")
    confidence_tier: ConfidenceTier
    explanation: Optional[str] = None


class MatchCreate(MatchBase):
    job_id: UUID
    source_product_id: UUID
    matched_product_id: UUID


class MatchUpdate(BaseModel):
    status: MatchStatus
    reviewed_by: Optional[UUID] = None


class Match(MatchBase):
    id: UUID
    job_id: UUID
    source_product_id: UUID
    matched_product_id: UUID
    status: MatchStatus = MatchStatus.PENDING
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MatchWithProducts(Match):
    """Match with expanded product details"""
    source_product: Optional[Product] = None
    matched_product: Optional[Product] = None


class MatchResponse(BaseModel):
    """API response for match data"""
    id: UUID
    source_url: str
    source_title: str
    matched_url: str  # Renamed from best_match_url to match frontend expectations
    matched_title: str  # Renamed from best_match_title to match frontend expectations
    score: float
    confidence_tier: ConfidenceTier
    explanation: Optional[str] = None
    status: MatchStatus
    needs_review: bool
    created_at: datetime


# =============================================================================
# Job Progress Schemas
# =============================================================================

class JobProgressBase(BaseModel):
    site: Site
    products_found: int = 0
    products_matched: int = 0
    current_category: Optional[str] = None
    current_url: Optional[str] = None
    rate: Optional[float] = None
    eta_seconds: Optional[int] = None


class JobProgressCreate(JobProgressBase):
    job_id: UUID


class JobProgress(JobProgressBase):
    id: UUID
    job_id: UUID
    updated_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Request/Response Schemas
# =============================================================================

class RunJobRequest(BaseModel):
    """Request to run matching on uploaded data"""
    site_a_products: List[ProductBase] = Field(..., min_length=1)
    site_b_products: List[ProductBase] = Field(..., min_length=1)


class RunJobResponse(BaseModel):
    """Response after running a job"""
    job_id: UUID
    status: JobStatus
    message: str
    total_matches: int
    high_confidence: int
    needs_review: int


class PaginatedResponse(BaseModel):
    """Generic paginated response"""
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class MatchListResponse(BaseModel):
    """Response for listing matches"""
    items: List[MatchResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: dict = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    supabase_connected: bool
    model_loaded: bool
    timestamp: datetime


class ErrorResponse(BaseModel):
    """Standard error response"""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Bulk Operations
# =============================================================================

class BulkMatchUpdate(BaseModel):
    """Bulk update matches"""
    match_ids: List[UUID]
    status: MatchStatus
    reviewed_by: Optional[UUID] = None


class BulkUpdateResponse(BaseModel):
    """Response for bulk operations"""
    updated_count: int
    failed_count: int
    errors: List[str] = Field(default_factory=list)


# =============================================================================
# Statistics
# =============================================================================

class JobStatistics(BaseModel):
    """Detailed statistics for a job"""
    total_products_a: int
    total_products_b: int
    total_matches: int
    confidence_distribution: dict[str, int]
    status_distribution: dict[str, int]
    avg_score: float
    median_score: float
    needs_review_count: int
    processing_time_seconds: Optional[float] = None


# =============================================================================
# Quick Match
# =============================================================================

class QuickMatchRequest(BaseModel):
    job_id: UUID
    title: str
    url: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None


class QuickMatchCandidate(BaseModel):
    product_id: UUID
    title: str
    url: str
    score: float
    brand: str
    category: str
    confidence_tier: ConfidenceTier


class QuickMatchResponse(BaseModel):
    best_match: Optional[QuickMatchCandidate] = None
    top_5: List[QuickMatchCandidate]
    confidence_tier: ConfidenceTier
    explanation: Optional[str] = None
    is_no_match: bool
