"""
URL-to-URL Product Matching API
FastAPI Backend Entry Point

Author: Aditya Aman
Created: 2026-01-08
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

# Add parent directory to path for url_mapper import
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import routers
from routers.jobs import router as jobs_router
from routers.matches import router as matches_router
from routers.health import router as health_router
from routers.upload import router as upload_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("=" * 60)
    logger.info("URL-TO-URL PRODUCT MATCHING API")
    logger.info("=" * 60)
    logger.info(f"Environment: {os.environ.get('PYTHON_ENV', 'development')}")
    logger.info(f"Port: {os.environ.get('PORT', '8000')}")

    # Verify critical environment variables
    supabase_key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not supabase_key:
        logger.warning("SUPABASE_KEY not set - database operations will fail")
    else:
        logger.info("Supabase key configured")

    # Preload ML model (avoids 10-15s cold start)
    logger.info("Preloading ML model...")
    try:
        from services.matcher import get_matcher_service
        matcher = get_matcher_service()
        matcher._ensure_loaded()
        logger.info("ML model preloaded successfully")
    except Exception as e:
        logger.warning(f"Failed to preload ML model: {e}")

    logger.info("API started successfully")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down API...")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="URL-to-URL Product Matching API",
    description="""
    ## Semantic Product Matching API

    This API provides endpoints for matching products between e-commerce sites
    using ML-based semantic similarity.

    ### Features
    - Create and manage matching jobs
    - Run semantic product matching using sentence-transformers
    - Review and approve/reject matches
    - Multi-signal scoring (semantic + token + attributes)

    ### Authentication
    Currently, this API does not require authentication.
    Future versions will integrate with Supabase Auth.

    ### Rate Limits
    - No rate limits currently implemented
    - Future versions will add rate limiting

    ### Support
    Contact: Aditya Aman
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# =============================================================================
# CORS Middleware
# =============================================================================

# Get allowed origins from environment - be restrictive in production
is_production = os.environ.get("PYTHON_ENV", "").lower() in ("production", "prod")
cors_origins_env = os.environ.get("CORS_ORIGINS", "")

if cors_origins_env and cors_origins_env != "*":
    # Use explicitly configured origins
    CORS_ORIGINS = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
elif is_production:
    # Production without explicit config - be restrictive
    CORS_ORIGINS = [
        "https://product-matcher-production-ef35.up.railway.app",  # Railway domain
    ]
    logger.warning("CORS: Using default production origins. Set CORS_ORIGINS for custom domains.")
else:
    # Development - allow all
    CORS_ORIGINS = ["*"]
    logger.info("CORS: Development mode - allowing all origins")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True if CORS_ORIGINS != ["*"] else False,  # Can't use credentials with "*"
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept"],
    expose_headers=["X-Total-Count", "X-Page", "X-Page-Size"],
)


# =============================================================================
# Exception Handlers
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed messages."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Don't expose internal errors in production
    if os.environ.get("PYTHON_ENV") == "production":
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )


# =============================================================================
# Include Routers
# =============================================================================

# Health check endpoints (no prefix - includes /api internally)
app.include_router(health_router)

# Job management endpoints
app.include_router(jobs_router)

# Match result endpoints
app.include_router(matches_router)

# CSV upload endpoints
app.include_router(upload_router)


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to docs."""
    return {
        "name": "URL-to-URL Product Matching API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/api/health"
    }


# =============================================================================
# Run with Uvicorn (for local development)
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    reload = os.environ.get("PYTHON_ENV") != "production"

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
