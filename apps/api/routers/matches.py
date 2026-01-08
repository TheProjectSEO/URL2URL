"""
Matches Router for URL-to-URL Product Matching API
Handles match results viewing and status updates
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from models.schemas import (
    Match, MatchUpdate, MatchResponse, MatchWithProducts,
    MatchStatus, ConfidenceTier,
    BulkMatchUpdate, BulkUpdateResponse,
    PaginatedResponse
)
from services.supabase import SupabaseService, get_supabase_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/matches", tags=["Matches"])


# =============================================================================
# Individual Match Endpoints
# =============================================================================

@router.get("/{match_id}", response_model=MatchResponse)
async def get_match(
    match_id: UUID,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get a single match by ID with product details.
    """
    try:
        match = await db.get_match(match_id)
        if not match:
            raise HTTPException(status_code=404, detail="Match not found")

        # Get product details
        source_product = await db.get_product(match.source_product_id)
        target_product = await db.get_product(match.matched_product_id)

        if not source_product or not target_product:
            raise HTTPException(status_code=500, detail="Match products not found")

        return MatchResponse(
            id=match.id,
            source_url=source_product.url,
            source_title=source_product.title,
            best_match_url=target_product.url,
            best_match_title=target_product.title,
            score=match.score,
            confidence_tier=match.confidence_tier,
            explanation=match.explanation,
            status=match.status,
            needs_review=match.confidence_tier in [
                ConfidenceTier.LIKELY_MATCH,
                ConfidenceTier.MANUAL_REVIEW,
                ConfidenceTier.NO_MATCH
            ],
            created_at=match.created_at
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting match {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{match_id}", response_model=Match)
async def update_match(
    match_id: UUID,
    update: MatchUpdate,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Update match status (approve/reject).

    **Status Options**:
    - `pending`: Default status, not yet reviewed
    - `approved`: Match has been verified as correct
    - `rejected`: Match has been rejected as incorrect

    This endpoint is typically used by human reviewers to validate
    matches that need manual review (confidence < 80%).
    """
    try:
        # Check match exists
        existing = await db.get_match(match_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Match not found")

        # Update the match
        updated_match = await db.update_match(match_id, update)
        if not updated_match:
            raise HTTPException(status_code=500, detail="Failed to update match")

        logger.info(f"Updated match {match_id} to status: {update.status}")
        return updated_match
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating match {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Bulk Operations
# =============================================================================

@router.post("/bulk/update", response_model=BulkUpdateResponse)
async def bulk_update_matches(
    update: BulkMatchUpdate,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Update multiple matches at once.

    Useful for batch approval/rejection operations from the UI.

    **Request Body**:
    - **match_ids**: List of match UUIDs to update
    - **status**: New status to set (approved/rejected)
    - **reviewed_by**: Optional reviewer UUID
    """
    try:
        if not update.match_ids:
            raise HTTPException(status_code=400, detail="No match IDs provided")

        if len(update.match_ids) > 1000:
            raise HTTPException(status_code=400, detail="Maximum 1000 matches per bulk update")

        updated_count = await db.update_matches_bulk(
            match_ids=update.match_ids,
            status=update.status,
            reviewed_by=update.reviewed_by
        )

        failed_count = len(update.match_ids) - updated_count
        errors = []
        if failed_count > 0:
            errors.append(f"{failed_count} matches could not be updated")

        logger.info(f"Bulk updated {updated_count}/{len(update.match_ids)} matches to {update.status}")

        return BulkUpdateResponse(
            updated_count=updated_count,
            failed_count=failed_count,
            errors=errors
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk match update: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk/approve")
async def bulk_approve_matches(
    match_ids: List[UUID],
    reviewed_by: Optional[UUID] = None,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Approve multiple matches at once.

    Convenience endpoint for approving matches.
    """
    return await bulk_update_matches(
        BulkMatchUpdate(
            match_ids=match_ids,
            status=MatchStatus.APPROVED,
            reviewed_by=reviewed_by
        ),
        db=db
    )


@router.post("/bulk/reject")
async def bulk_reject_matches(
    match_ids: List[UUID],
    reviewed_by: Optional[UUID] = None,
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Reject multiple matches at once.

    Convenience endpoint for rejecting matches.
    """
    return await bulk_update_matches(
        BulkMatchUpdate(
            match_ids=match_ids,
            status=MatchStatus.REJECTED,
            reviewed_by=reviewed_by
        ),
        db=db
    )


# =============================================================================
# Query Endpoints
# =============================================================================

@router.get("/needs-review", response_model=PaginatedResponse)
async def get_matches_needing_review(
    job_id: Optional[UUID] = Query(None, description="Filter by job ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get all matches that need manual review.

    These are matches with confidence tier: likely_match, manual_review, or no_match.
    """
    try:
        # This is a convenience endpoint that filters for review-needed matches
        # If job_id is provided, filter by that job
        if job_id:
            offset = (page - 1) * page_size
            matches_data, total = await db.get_matches_by_job(
                job_id=job_id,
                needs_review=True,
                status=MatchStatus.PENDING,  # Only pending reviews
                limit=page_size,
                offset=offset
            )

            items = []
            for m in matches_data:
                source = m.get("source_product", {})
                target = m.get("matched_product", {})

                items.append({
                    "id": m["id"],
                    "job_id": m["job_id"],
                    "source_url": source.get("url", ""),
                    "source_title": source.get("title", ""),
                    "best_match_url": target.get("url", ""),
                    "best_match_title": target.get("title", ""),
                    "score": float(m["score"]),
                    "confidence_tier": m["confidence_tier"],
                    "explanation": m.get("explanation"),
                    "status": m["status"],
                    "created_at": m["created_at"]
                })

            total_pages = (total + page_size - 1) // page_size

            return PaginatedResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages
            )
        else:
            # If no job_id, return empty for now
            # TODO: Implement cross-job query
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                total_pages=0
            )
    except Exception as e:
        logger.error(f"Error getting matches needing review: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-confidence/{tier}", response_model=PaginatedResponse)
async def get_matches_by_confidence(
    tier: ConfidenceTier,
    job_id: UUID = Query(..., description="Job ID (required)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get matches filtered by confidence tier.

    **Confidence Tiers**:
    - `exact_match`: Score >= 0.95
    - `high_confidence`: Score 0.90-0.94
    - `good_match`: Score 0.80-0.89
    - `likely_match`: Score 0.70-0.79
    - `manual_review`: Score 0.50-0.69
    - `no_match`: Score < 0.50
    """
    try:
        offset = (page - 1) * page_size
        matches_data, total = await db.get_matches_by_job(
            job_id=job_id,
            confidence_tier=tier,
            limit=page_size,
            offset=offset
        )

        items = []
        for m in matches_data:
            source = m.get("source_product", {})
            target = m.get("matched_product", {})

            items.append({
                "id": m["id"],
                "job_id": m["job_id"],
                "source_url": source.get("url", ""),
                "source_title": source.get("title", ""),
                "best_match_url": target.get("url", ""),
                "best_match_title": target.get("title", ""),
                "score": float(m["score"]),
                "confidence_tier": m["confidence_tier"],
                "explanation": m.get("explanation"),
                "status": m["status"],
                "created_at": m["created_at"]
            })

        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Error getting matches by confidence tier: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-status/{status}", response_model=PaginatedResponse)
async def get_matches_by_status(
    status: MatchStatus,
    job_id: UUID = Query(..., description="Job ID (required)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Get matches filtered by review status.

    **Status Options**:
    - `pending`: Not yet reviewed
    - `approved`: Verified as correct
    - `rejected`: Marked as incorrect
    """
    try:
        offset = (page - 1) * page_size
        matches_data, total = await db.get_matches_by_job(
            job_id=job_id,
            status=status,
            limit=page_size,
            offset=offset
        )

        items = []
        for m in matches_data:
            source = m.get("source_product", {})
            target = m.get("matched_product", {})

            items.append({
                "id": m["id"],
                "job_id": m["job_id"],
                "source_url": source.get("url", ""),
                "source_title": source.get("title", ""),
                "best_match_url": target.get("url", ""),
                "best_match_title": target.get("title", ""),
                "score": float(m["score"]),
                "confidence_tier": m["confidence_tier"],
                "explanation": m.get("explanation"),
                "status": m["status"],
                "created_at": m["created_at"]
            })

        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"Error getting matches by status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
