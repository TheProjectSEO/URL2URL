"""
Health Router for URL-to-URL Product Matching API
System health checks and status endpoints
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends

from models.schemas import HealthResponse
from services.supabase import SupabaseService, get_supabase_service
from services.matcher import MatcherService, get_matcher_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Health"])

# API Version
API_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: SupabaseService = Depends(get_supabase_service),
    matcher: MatcherService = Depends(get_matcher_service)
):
    """
    Health check endpoint for monitoring and load balancers.

    Returns the status of:
    - API server
    - Supabase database connection
    - ML model loading status
    """
    # Check Supabase connection
    supabase_connected = False
    try:
        supabase_connected = db.is_connected()
    except Exception as e:
        logger.warning(f"Supabase health check failed: {e}")

    # Check if model is loaded (don't force load on health check)
    model_loaded = matcher.is_loaded

    # Determine overall status
    if supabase_connected:
        status = "healthy"
    else:
        status = "degraded"

    return HealthResponse(
        status=status,
        version=API_VERSION,
        supabase_connected=supabase_connected,
        model_loaded=model_loaded,
        timestamp=datetime.utcnow()
    )


@router.get("/health/ready")
async def readiness_check(
    db: SupabaseService = Depends(get_supabase_service)
):
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the service is ready to accept traffic.
    Returns 503 if critical dependencies are unavailable.
    """
    try:
        # Check critical dependency: Supabase
        if not db.is_connected():
            return {"ready": False, "reason": "Database not connected"}, 503

        return {"ready": True}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {"ready": False, "reason": str(e)}, 503


@router.get("/health/live")
async def liveness_check():
    """
    Kubernetes liveness probe endpoint.

    Returns 200 if the service is alive.
    This is a simple check that the server is responding.
    """
    return {"alive": True, "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/detailed")
async def detailed_health(
    db: SupabaseService = Depends(get_supabase_service),
    matcher: MatcherService = Depends(get_matcher_service)
):
    """
    Detailed health check with component status.

    Returns comprehensive information about each service component.
    """
    components = {}

    # Check Supabase
    try:
        supabase_connected = db.is_connected()
        components["supabase"] = {
            "status": "healthy" if supabase_connected else "unhealthy",
            "connected": supabase_connected,
            "url": db.SUPABASE_URL,
            "schema": db.SCHEMA
        }
    except Exception as e:
        components["supabase"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Check Matcher
    try:
        model_loaded = matcher.is_loaded
        components["matcher"] = {
            "status": "healthy" if model_loaded else "not_loaded",
            "model_loaded": model_loaded,
            "model_name": matcher.model_name,
            "top_k": matcher.top_k
        }
    except Exception as e:
        components["matcher"] = {
            "status": "unhealthy",
            "error": str(e)
        }

    # Environment info
    components["environment"] = {
        "python_env": os.environ.get("PYTHON_ENV", "development"),
        "port": os.environ.get("PORT", "8000"),
        "has_supabase_key": bool(os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY"))
    }

    # Overall status
    all_healthy = all(
        c.get("status") == "healthy"
        for c in components.values()
        if isinstance(c, dict) and "status" in c
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": API_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "components": components
    }


@router.get("/")
async def root():
    """
    API root endpoint.

    Returns basic API information and links to documentation.
    """
    return {
        "name": "URL-to-URL Product Matching API",
        "version": API_VERSION,
        "description": "Semantic product matching API using ML embeddings",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/api/health"
    }
