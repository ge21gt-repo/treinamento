"""Real health check endpoint for production readiness."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.health import check_database, check_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    db_status = await check_database(db)
    storage_status = await check_storage()

    all_ok = db_status["status"] == "ok" and storage_status["status"] == "ok"

    return {
        "status": "ok" if all_ok else "degraded",
        "version": "1.0.0",
        "checks": {
            "database": db_status,
            "storage": storage_status,
        },
    }


@router.get("/health/live")
async def health_live():
    """Minimal liveness probe - always responds if process is alive."""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    """Readiness probe - verifies DB connection."""
    db_status = await check_database(db)
    if db_status["status"] != "ok":
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Database not ready"},
        )
    return {"status": "ok"}
