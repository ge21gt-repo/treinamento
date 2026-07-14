"""Health check service - verifies PostgreSQL and S3 connectivity."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def check_database(db: AsyncSession) -> dict:
    """Check if PostgreSQL is reachable."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "Database is reachable"}
    except Exception as e:
        logger.error("Health check - database unreachable: %s", e)
        return {"status": "error", "detail": str(e)}


async def check_storage() -> dict:
    """Check if S3 bucket is accessible."""
    from app.config import settings

    if settings.STORAGE_BACKEND != "s3":
        return {"status": "ok", "detail": "Storage backend is local (no S3 check)"}

    try:
        import aioboto3

        session = aioboto3.Session(
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
        )
        async with session.client("s3", endpoint_url=settings.S3_ENDPOINT or None) as s3:
            await s3.head_bucket(Bucket=settings.S3_BUCKET)
        return {"status": "ok", "detail": "S3 bucket is accessible"}
    except Exception as e:
        logger.error("Health check - S3 unreachable: %s", e)
        return {"status": "error", "detail": str(e)}
