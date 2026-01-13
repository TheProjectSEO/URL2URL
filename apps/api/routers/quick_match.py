"""
Quick Match Router
Returns top-5 candidates for a single source product without persisting.
"""

import uuid
from types import SimpleNamespace
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException

from models.schemas import (
    QuickMatchRequest, QuickMatchResponse, QuickMatchCandidate,
    Site, ConfidenceTier
)
from services.supabase import get_supabase_service
from services.matcher_v2 import get_matcher_v2_service

router = APIRouter(prefix="/api/match", tags=["Quick Match"])


@router.post("/quick", response_model=QuickMatchResponse)
async def quick_match(payload: QuickMatchRequest):
    """
    Returns top 5 candidates from Site B for a single source product in a job.
    Does not write anything to the database.
    """
    db = get_supabase_service()

    # Validate job exists
    job = await db.get_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    matcher = get_matcher_v2_service()

    # Build a lightweight object with the attributes the matcher needs
    source = SimpleNamespace(
        id=uuid.uuid4(),
        job_id=payload.job_id,
        site=Site.SITE_A,
        url=payload.url or "",
        title=payload.title,
        brand=payload.brand or "",
        category=payload.category or "",
        price=payload.price,
        metadata={}
    )

    result = await matcher.match_product(source, payload.job_id)

    # Build response
    candidates = [
        QuickMatchCandidate(
            product_id=c.product_id,
            title=c.title,
            url=c.url,
            score=c.score,
            brand=c.brand or "",
            category=c.category or "",
            confidence_tier=matcher._get_confidence_tier(c.score)
        ) for c in result.top_5_candidates
    ]

    best = None
    if result.best_match:
        best = QuickMatchCandidate(
            product_id=result.best_match.product_id,
            title=result.best_match.title,
            url=result.best_match.url,
            score=result.best_match.score,
            brand=result.best_match.brand or "",
            category=result.best_match.category or "",
            confidence_tier=matcher._get_confidence_tier(result.best_match.score)
        )

    return QuickMatchResponse(
        best_match=best,
        top_5=candidates,
        confidence_tier=result.confidence_tier,
        explanation=result.explanation,
        is_no_match=result.is_no_match
    )

