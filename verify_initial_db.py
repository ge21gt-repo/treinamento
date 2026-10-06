"""Prepara o banco antes de subir a API (chamado pelo CMD do Dockerfile).

1. Schema `lms` sem tabelas: `create_all` + `alembic stamp head`.
   A cadeia do Alembic nao cria o banco do zero (a 001 altera `usuarios`).
2. Sempre: `alembic upgrade head` (nao faz nada se ja estiver na head).

Banco com tabelas e sem `alembic_version` para aqui: reconciliar a mao.
O pg_advisory_lock evita duas pods migrando ao mesmo tempo.
"""

import asyncio
import sys

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.config import settings
from app.models import Base

LOCK_KEY = 20261004


async def main() -> int:
    alembic_cfg = Config("alembic.ini")
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
            await conn.commit()

            tabelas = set(
                (await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'lms'"))).scalars()
            )
            await conn.commit()

            if not tabelas:
                print("verify_initial_db: banco vazio, criando tabelas e marcando a head", flush=True)
                async with engine.begin() as ddl:
                    await ddl.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
                    await ddl.run_sync(Base.metadata.create_all)
                await asyncio.to_thread(command.stamp, alembic_cfg, "head")
            elif "alembic_version" not in tabelas:
                print("verify_initial_db: tabelas sem lms.alembic_version; reconciliar a mao", file=sys.stderr)
                return 1

            # alembic/env.py usa asyncio.run, por isso roda numa thread sem loop.
            await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
            print("verify_initial_db: banco na head", flush=True)
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
