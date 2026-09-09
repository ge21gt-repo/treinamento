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


async def check_migrations(db: AsyncSession) -> dict:
    """Compara a revisao gravada no banco com a head do codigo.

    Existe porque o deploy nao roda `alembic upgrade head` e o `create_all` do
    startup so cria tabelas que faltam -- nunca adiciona coluna em tabela que ja
    existe. O resultado e que migration de coluna passa despercebida ate um
    endpoint quebrar com 500 (foi o que aconteceu com `conteudos.disponivel`).
    """
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(Config("alembic.ini"))
        head = script.get_current_head()

        resultado = await db.execute(text("SELECT version_num FROM lms.alembic_version"))
        atual = resultado.scalar_one_or_none()

        if atual == head:
            return {"status": "ok", "detail": f"Schema na revisao {head}"}

        if atual is None:
            return {
                "status": "pendente",
                "detail": f"Banco sem alembic_version; head do codigo e {head}",
            }

        try:
            pendentes = [r.revision for r in script.iterate_revisions(head, atual)]
        except Exception:
            pendentes = []

        return {
            "status": "pendente",
            "detail": (
                f"Banco em {atual}, codigo em {head}. "
                f"Rode 'alembic upgrade head'. Pendentes: {pendentes or 'desconhecidas'}"
            ),
        }
    except Exception as e:
        logger.error("Health check - falha ao conferir migrations: %s", e)
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
