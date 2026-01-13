"""
Jobs Router for URL-to-URL Product Matching API
Handles job CRUD and execution endpoints
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.schemas import (
    CrawlJob, CrawlJobCreate, CrawlJobUpdate, CrawlJobWithStats,
    ProductBase, ProductCreate,
    MatchCreate, MatchResponse,
    JobStatus, MatchStatus, ConfidenceTier, Site,
    RunJobRequest, RunJobResponse,
    PaginatedResponse, JobStatistics, ErrorResponse
)
from services.supabase import SupabaseService, get_supabase_service
from services.job_runner import run_job_background, JobRunner
from services.matcher_v2 import get_matcher_v2_service, MatcherConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


# =============================================================================
# Job CRUD Endpoints
# =============================================================================

@router.post("", response_model=CrawlJob, status_code=201)
async def create_job(
    job: CrawlJobCreate,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Create a new crawl/matching job.

    The job is created in 'pending' status and can be executed
    by calling POST /api/jobs/{id}/run
    """
    try:
        created_job = await db.create_job(job)
        logger.info(f"Created job: {created_job.id}")
        return created_job
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=PaginatedResponse)
async def list_jobs(
    org_id: Optional[UUID] = Query(None, description="Filter by organization"),
    status: Optional[JobStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    List all jobs with optional filters and pagination.

    - **org_id**: Filter by organization UUID
    - **status**: Filter by job status (pending, running, completed, failed)
    - **page**: Page number (starting from 1)
    - **page_size**: Number of items per page (max 100)
    """
    try:
        offset = (page - 1) * page_size
        jobs, total = await db.list_jobs(
            org_id=org_id,
            status=status,
            limit=page_size,
            offset=offset
        )

        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=[job.model_dump() for job in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}", response_model=CrawlJobWithStats)
async def get_job(
    job_id: UUID,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get job details by ID including match statistics.
    """
    try:
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get statistics
        stats = await db.get_job_match_stats(job_id)

        # Get product counts
        products_a = await db.get_products_by_job(job_id, site=Site.SITE_A)
        products_b = await db.get_products_by_job(job_id, site=Site.SITE_B)

        return CrawlJobWithStats(
            **job.model_dump(),
            total_matches=stats.get("total_matches", 0),
            high_confidence_matches=stats.get("confidence_distribution", {}).get("exact_match", 0) +
                                    stats.get("confidence_distribution", {}).get("high_confidence", 0) +
                                    stats.get("confidence_distribution", {}).get("good_match", 0),
            needs_review_count=stats.get("needs_review_count", 0),
            products_site_a=len(products_a),
            products_site_b=len(products_b)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{job_id}", response_model=CrawlJob)
async def update_job(
    job_id: UUID,
    update: CrawlJobUpdate,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Update job properties.

    Note: Cannot update jobs that are currently running.
    """
    try:
        # Check job exists and is not running
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Cannot update running job")

        updated_job = await db.update_job(job_id, update)
        if not updated_job:
            raise HTTPException(status_code=500, detail="Failed to update job")

        return updated_job
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: UUID,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Delete a job and all related data.

    This action cannot be undone. All products and matches
    associated with this job will be deleted.
    """
    try:
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Cannot delete running job")

        success = await db.delete_job(job_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete job")

        logger.info(f"Deleted job: {job_id}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job Execution Endpoints
# =============================================================================

@router.post("/{job_id}/run", response_model=RunJobResponse)
async def run_job(
    job_id: UUID,
    request: RunJobRequest,
    background_tasks: BackgroundTasks,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Run product matching for a job.

    This endpoint accepts product data for both sites and performs
    semantic matching. Products and matches are saved to the database.

    **Request Body**:
    - **site_a_products**: List of source products (required)
    - **site_b_products**: List of target products (required)

    Each product should have: url, title, brand (optional), category (optional)

    **Response**:
    - Job status and match statistics
    """
    try:
        # Validate job exists
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == JobStatus.RUNNING:
            raise HTTPException(status_code=400, detail="Job is already running")

        # Update job status to running
        await db.update_job_status(
            job_id,
            JobStatus.RUNNING,
            started_at=datetime.utcnow()
        )

        try:
            # Create products in database (provided lists)
            logger.info(f"Creating {len(request.site_a_products)} Site A products...")
            products_a_to_create = [
                ProductCreate(
                    job_id=job_id,
                    site=Site.SITE_A,
                    url=p.url,
                    title=p.title,
                    brand=p.brand,
                    category=p.category,
                    price=p.price,
                    metadata=p.metadata or {}
                ) for p in request.site_a_products
            ]
            await db.create_products_bulk(products_a_to_create)

            logger.info(f"Creating {len(request.site_b_products)} Site B products...")
            products_b_to_create = [
                ProductCreate(
                    job_id=job_id,
                    site=Site.SITE_B,
                    url=p.url,
                    title=p.title,
                    brand=p.brand,
                    category=p.category,
                    price=p.price,
                    metadata=p.metadata or {}
                ) for p in request.site_b_products
            ]
            await db.create_products_bulk(products_b_to_create)

            # Run the full pipeline synchronously using JobRunner (no crawling if not pending)
            runner = JobRunner()
            stats = await runner.run_job(job_id)

            total_products = stats.get("total_products", 0)
            high_conf = stats.get("high_confidence", 0)
            no_match = stats.get("no_match", 0)
            needs_review = max(total_products - high_conf - no_match, 0)

            return RunJobResponse(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                message="Matching completed successfully",
                total_matches=stats.get("matches_found", 0),
                high_confidence=high_conf,
                needs_review=needs_review
            )

        except Exception as e:
            await db.update_job_status(job_id, JobStatus.FAILED)
            logger.error(f"Job {job_id} failed: {e}")
            raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/statistics", response_model=JobStatistics)
async def get_job_statistics(
    job_id: UUID,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get detailed statistics for a job.
    """
    try:
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        stats = await db.get_job_match_stats(job_id)
        products_a = await db.get_products_by_job(job_id, site=Site.SITE_A)
        products_b = await db.get_products_by_job(job_id, site=Site.SITE_B)

        # Calculate processing time if completed
        processing_time = None
        if job.started_at and job.completed_at:
            processing_time = (job.completed_at - job.started_at).total_seconds()

        return JobStatistics(
            total_products_a=len(products_a),
            total_products_b=len(products_b),
            total_matches=stats.get("total_matches", 0),
            confidence_distribution=stats.get("confidence_distribution", {}),
            status_distribution=stats.get("status_distribution", {}),
            avg_score=stats.get("avg_score", 0),
            median_score=stats.get("avg_score", 0),  # TODO: Calculate actual median
            needs_review_count=stats.get("needs_review_count", 0),
            processing_time_seconds=processing_time
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting statistics for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Job Matches Endpoint (convenience)
# =============================================================================

@router.get("/{job_id}/matches", response_model=dict)
async def get_job_matches(
    job_id: UUID,
    status: Optional[MatchStatus] = Query(None, description="Filter by match status"),
    confidence_tier: Optional[ConfidenceTier] = Query(None, description="Filter by confidence tier"),
    min_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum score filter"),
    needs_review: Optional[bool] = Query(None, description="Filter matches needing review"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get matches for a specific job with filtering and pagination.

    This is a convenience endpoint that includes product details
    with each match result.
    """
    try:
        job = await db.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        offset = (page - 1) * page_size
        matches_data, total = await db.get_matches_by_job(
            job_id=job_id,
            status=status,
            confidence_tier=confidence_tier,
            min_score=min_score,
            needs_review=needs_review,
            limit=page_size,
            offset=offset
        )

        # Transform to response format
        # Note: RPC returns flat columns (source_url, source_title, matched_url, matched_title)
        # not nested objects
        items = []
        for m in matches_data:
            items.append(MatchResponse(
                id=UUID(m["id"]),
                source_url=m.get("source_url", ""),
                source_title=m.get("source_title", ""),
                matched_url=m.get("matched_url", ""),
                matched_title=m.get("matched_title", ""),
                score=float(m["score"]),
                confidence_tier=ConfidenceTier(m["confidence_tier"]),
                explanation=m.get("explanation"),
                status=MatchStatus(m["status"]),
                needs_review=m["confidence_tier"] in ["likely_match", "manual_review", "no_match"],
                created_at=datetime.fromisoformat(m["created_at"].replace("Z", "+00:00"))
            ).model_dump())

        total_pages = (total + page_size - 1) // page_size

        # Get stats for this filter
        stats = await db.get_job_match_stats(job_id)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting matches for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Background Job Execution
# =============================================================================

@router.post("/{job_id}/run-background")
async def run_job_in_background(
    job_id: UUID,
    background_tasks: BackgroundTasks,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Start job execution in background.

    This triggers the full matching pipeline:
    1. Crawl uncrawled products (if any)
    2. Generate embeddings for Site B
    3. Match all Site A products against Site B
    4. Store results with top 5 candidates

    The job runs asynchronously. Poll GET /api/jobs/{job_id} for status.
    """
    # Verify job exists
    job = await db.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Job is already running")

    if job.status == JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail="Job already completed. Create a new job to re-run."
        )

    # Add to background tasks
    background_tasks.add_task(run_job_background, job_id)

    return {
        "status": "started",
        "message": f"Job {job_id} started in background",
        "job_id": str(job_id),
        "check_status": f"/api/jobs/{job_id}"
    }


# =============================================================================
# Job Progress Endpoint
# =============================================================================

@router.get("/{job_id}/progress")
async def get_job_progress(
    job_id: UUID,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get real-time job progress.

    Returns current stage, progress count, rate, and ETA.
    Poll this endpoint every 2 seconds during job execution.
    """
    from services.progress import ProgressTracker, JobProgress

    # Verify job exists
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    progress = await ProgressTracker.get(job_id)

    if not progress:
        # No progress record yet - job might be pending
        return {
            "stage": job.status.value if job.status else "pending",
            "current": 0,
            "total": 0,
            "rate": 0,
            "eta_seconds": 0,
            "message": f"Job status: {job.status.value}" if job.status else "Pending"
        }

    return {
        "stage": progress.stage,
        "current": progress.current,
        "total": progress.total,
        "rate": progress.rate,
        "eta_seconds": progress.eta_seconds,
        "message": progress.message
    }


# =============================================================================
# Export Matches CSV
# =============================================================================

@router.get("/{job_id}/export")
async def export_job_matches_csv(
    job_id: UUID,
    db: SupabaseService = Depends(get_supabase_service),
    page_size: int = Query(1000, ge=1, le=5000)
):
    """
    Download matches for a job as CSV.

    Columns: source_url, source_title, matched_url, matched_title, score, confidence_tier, explanation, status
    """
    import csv
    import io

    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Stream all matches in pages
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "source_url", "source_title", "matched_url", "matched_title",
        "score", "confidence_tier", "explanation", "status"
    ])

    offset = 0
    total_written = 0
    while True:
        matches_data, total = await db.get_matches_by_job(
            job_id=job_id,
            limit=page_size,
            offset=offset
        )
        if not matches_data:
            break
        for m in matches_data:
            writer.writerow([
                m.get("source_url", ""),
                m.get("source_title", ""),
                m.get("matched_url", ""),
                m.get("matched_title", ""),
                f"{float(m.get('score', 0)):.4f}",
                m.get("confidence_tier", ""),
                (m.get("explanation") or "").replace("\n", " ").strip(),
                m.get("status", "")
            ])
            total_written += 1
        offset += page_size
        if offset >= total:
            break

    output.seek(0)
    filename = f"job_{job_id}_matches.csv"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}"
    }
    return StreamingResponse(output, media_type="text/csv", headers=headers)


# =============================================================================
# Diagnostics Export (component scores for a sample of matches)
# =============================================================================

@router.get("/{job_id}/diagnostics")
async def export_diagnostics(
    job_id: UUID,
    sample_size: int = Query(50, ge=1, le=500),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Export a CSV with component scores (semantic/token/attr/visual) for a sample of matches.
    Recomputes components using current matcher config for the job.
    """
    import csv, io
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Configure matcher like the runner does
    cfg = job.config if isinstance(job.config, dict) else {}
    matcher = get_matcher_v2_service(config=MatcherConfig(
        enable_ai_validation=bool(cfg.get('ai_validation_enabled', False)),
        ai_validation_min_score=float(cfg.get('ai_validation_min', 0.70)),
        ai_validation_max_score=float(cfg.get('ai_validation_max', 0.90)),
        max_ai_validations_per_job=int(cfg.get('ai_validation_cap', 100)),
        enable_image_matching=bool(cfg.get('use_ocr_text', False)),
        embed_enriched_text=bool(cfg.get('embed_enriched_text', False)),
        token_norm_v2=bool(cfg.get('token_norm_v2', False)),
        use_brand_ontology=bool(cfg.get('use_brand_ontology', False)),
        use_category_ontology=bool(cfg.get('use_category_ontology', False)),
        use_variant_extractor=bool(cfg.get('use_variant_extractor', False)),
    ), reset=True)

    # Fetch a page of matches
    matches_data, total = await db.get_matches_by_job(job_id=job_id, limit=sample_size, offset=0)
    if not matches_data:
        raise HTTPException(status_code=404, detail="No matches for diagnostics")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'source_title','target_title','final_score','semantic','token','attributes','visual','brand_src','brand_tgt','category_src','category_tgt'
    ])

    for m in matches_data:
        source = await db.get_product(UUID(m['source_product_id']))
        target = await db.get_product(UUID(m['matched_product_id'])) if m.get('matched_product_id') else None
        if not source or not target:
            continue

        # Compose texts and embeddings
        src_text = matcher._compose_text(source)
        tgt_text = matcher._compose_text(target)
        src_emb = matcher.generate_embedding(src_text)
        tgt_emb = matcher.generate_embedding(tgt_text)
        sem = float(cosine_similarity([src_emb], [tgt_emb])[0][0])

        # Token overlap
        st = matcher._tokenize_text(source.title)
        tt = matcher._tokenize_text(target.title)
        inter = len(st & tt)
        uni = len(st | tt)
        tok = (inter / uni) if uni else 0.0

        # Attributes (0..1)
        attr = matcher._attribute_match(source, target)

        # Visual not recomputed here (set blank)
        visual = ''

        # Final using current weights (no visual)
        final = sem * matcher.SEMANTIC_WEIGHT + tok * matcher.TOKEN_WEIGHT + attr * matcher.ATTRIBUTE_WEIGHT

        writer.writerow([
            source.title,
            target.title,
            f"{final:.4f}",
            f"{sem:.4f}",
            f"{tok:.4f}",
            f"{attr:.4f}",
            visual,
            source.brand or '',
            target.brand or '',
            source.category or '',
            target.category or ''
        ])

    output.seek(0)
    headers = {"Content-Disposition": f"attachment; filename=diagnostics_{job_id}.csv"}
    return StreamingResponse(output, media_type="text/csv", headers=headers)


@router.get("/{job_id}/metrics")
async def get_job_metrics(job_id: UUID, db: SupabaseService = Depends(get_supabase_service)):
    """
    Return persisted matcher metrics for a job (if available).
    Metrics are stored in job.config.metrics at the end of a run.
    """
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cfg = job.config if isinstance(job.config, dict) else {}
    return cfg.get('metrics', {})
