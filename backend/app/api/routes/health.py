from fastapi import APIRouter
from datetime import datetime, timezone
from app.core.config import settings
from app.core.database import check_db_health

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Health check endpoint returning service status, university name,
    API version, environment, and database connection state.
    """
    db_status = await check_db_health()
    return {
        "status": "healthy",
        "service": "Adaptive Interview Intelligence API",
        "institution": "Vignan's Foundation for Science, Technology and Research (VFSTR)",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 1 - Foundation & Core Architecture"
    }
