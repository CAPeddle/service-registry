"""Health check endpoints."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@router.get("/ready")
async def readiness_check():
    """Readiness check endpoint."""
    # Add database connectivity check here if needed
    return {"status": "ready"}
