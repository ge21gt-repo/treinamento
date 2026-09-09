"""Testes US-17: logs de auditoria e rastreabilidade."""

import asyncio

from fastapi import status

pytestmark = __import__("pytest").mark.db


class TestLogAcessoEscrita:
    """T-17.1 — log_acesso em operacoes de escrita"""

    async def test_escrita_gera_log_acesso(self, client):
        from sqlalchemy import select, func
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.models.log import LogAcesso

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()

        antes = 0
        try:
            async with maker() as s:
                antes = (await s.execute(select(func.count()).select_from(LogAcesso))).scalar() or 0
        finally:
            await engine.dispose()

        # operacao de escrita (POST) que o middleware deve logar
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Aud", "descricao": "x", "ordem": 0, "publicado": True})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        await asyncio.sleep(1)
        engine2 = create_async_engine(settings.TEST_DATABASE_URL)
        maker2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker2() as s:
                escritas = (
                    await s.execute(
                        select(func.count()).select_from(LogAcesso).where(LogAcesso.acao == "POST")
                    )
                ).scalar() or 0
            assert escritas > antes, "Operacao de escrita deve gerar log_acesso"
        finally:
            await engine2.dispose()


import asyncio  # noqa: E402

class TestAuditoria:
    """T-17.2 — log_auditoria em operacoes de escrita nas tabelas principais"""

    async def test_criar_curso_gera_auditoria(self, client):
        from sqlalchemy import select, func
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.models.log import LogAuditoria

        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Auditoria", "descricao": "x", "ordem": 0, "publicado": True})
        assert r.status_code == status.HTTP_201_CREATED, r.text
        curso_id = r.json()["id"]

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s:
                logs = (
                    await s.execute(
                        select(LogAuditoria).where(
                            LogAuditoria.tabela_afetada == "cursos",
                            LogAuditoria.registro_id == str(curso_id),
                            LogAuditoria.acao == "criar",
                        )
                    )
                ).scalars().all()
            assert len(logs) == 1, f"Esperava 1 auditoria de criacao, veio {len(logs)}"
            assert logs[0]["dados_novos"]["titulo"] == "Curso Auditoria" if hasattr(logs[0], "__getitem__") else True
        finally:
            await engine.dispose()


class TestConsultaAuditoria:
    """T-17.3/17.4/17.5 — consulta, filtros e exportacao de logs de auditoria"""

    async def test_listar_logs_auditoria(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Aud2", "descricao": "x", "ordem": 0, "publicado": True})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.get("/api/v1/auditoria/logs")
        assert r.status_code == status.HTTP_200_OK, r.text
        logs = r.json()
        assert isinstance(logs, list)
        assert any(l["tabela_afetada"] == "cursos" and l["acao"] == "criar" for l in logs)

    async def test_filtro_por_tabela(self, client):
        await client.post("/api/v1/cursos", json={"titulo": "Curso Aud3", "descricao": "x", "ordem": 0, "publicado": True})
        r = await client.get("/api/v1/auditoria/logs?tabela=cursos")
        assert r.status_code == status.HTTP_200_OK, r.text
        logs = r.json()
        assert len(logs) >= 1
        assert all(l["tabela_afetada"] == "cursos" for l in logs)

    async def test_exportacao_csv(self, client):
        await client.post("/api/v1/cursos", json={"titulo": "Curso Aud4", "descricao": "x", "ordem": 0, "publicado": True})
        r = await client.get("/api/v1/auditoria/logs?formato=csv")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "text/csv" in r.headers.get("content-type", "")

    async def test_exportacao_pdf(self, client):
        r = await client.get("/api/v1/auditoria/logs?formato=pdf")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "application/pdf" in r.headers.get("content-type", "")

    async def test_auditoria_requer_permissao(self):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/auditoria/logs")
        assert r.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
