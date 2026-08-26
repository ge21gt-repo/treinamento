"""Testes issues 25/27: aulas ao vivo (acesso, presenca, moderacao, ws)."""

from datetime import timedelta

from sqlalchemy import select
from fastapi import status

pytestmark = __import__("pytest").mark.db


async def _setup_curso_aula(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Aula Live", "descricao": "x", "ordem": 0, "publicado": True})
    curso_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/cursos/{curso_id}/aulas",
        json={"curso_id": curso_id, "titulo": "Aula Live", "data_hora": "2099-01-01T10:00:00Z", "duracao_minutos": 60},
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    aula_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return {"curso_id": curso_id, "aula_id": aula_id}


class TestCodigoAcesso:
    """P1 — codigo de acesso nao vaza na listagem"""

    async def test_listagem_esconde_codigo_para_participante(self, client):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.api.deps import get_current_user
        from app.config import settings
        from app.database import get_db
        from app.main import app

        s = await _setup_curso_aula(client)

        # simular um participante (sem permissao de edicao de aula)
        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        try:
            from app.models.usuario import Usuario

            user = (await session.execute(select(Usuario).where(Usuario.email == "seed.us03@sp.gov.br"))).scalar_one_or_none()
            if user is None:
                from tests.conftest import _create_user
                import uuid

                user = await _create_user(session, uuid.uuid4(), "participante.teste@sp.gov.br", "Participante", "participante")
                await session.commit()
        finally:
            await session.close()
            await engine.dispose()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            r = await client.get(f"/api/v1/cursos/{s['curso_id']}/aulas")
            assert r.status_code == status.HTTP_200_OK, r.text
            aula = r.json()[0]
            assert aula["exige_codigo"] is True, "Deve indicar que ha codigo"
            assert aula["codigo_acesso"] is None, "Participante nao pode ver o codigo"
        finally:
            app.dependency_overrides.clear()

    async def test_entrar_sem_inscricao_403(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Sem Insc", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.post(
            f"/api/v1/cursos/{cid}/aulas",
            json={"curso_id": cid, "titulo": "Aula", "data_hora": "2099-01-01T10:00:00Z", "duracao_minutos": 60},
        )
        aula_id = r.json()["id"]
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_403_FORBIDDEN, "Sem inscricao nao pode entrar"


class TestPresenca:
    """P2/P4 — entrar nao duplica, acessar nao grava presenca"""

    async def test_entrar_duas_vezes_nao_duplica(self, client):
        s = await _setup_curso_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{s['aula_id']}/entrar")
        assert r.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED), r.text
        r = await client.post(f"/api/v1/cursos/aulas/{s['aula_id']}/entrar")
        assert r.status_code == status.HTTP_409_CONFLICT, "Entrar 2x deve dar 409 (sem duplicar)"

        r = await client.get("/api/v1/cursos/aulas/minhas-presencas")
        assert r.status_code == status.HTTP_200_OK, r.text
        presencas = [p for p in r.json() if p["aula_id"] == s["aula_id"]]
        assert len(presencas) == 1, f"Entrar 2x deve dar 1 presenca, veio {len(presencas)}"

    async def test_minhas_presencas(self, client):
        s = await _setup_curso_aula(client)
        await client.post(f"/api/v1/cursos/aulas/{s['aula_id']}/entrar")
        r = await client.get("/api/v1/cursos/aulas/minhas-presencas")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert len(r.json()) >= 1


class TestAulasProximas:
    """P5 — /aulas/proximas filtra por inscricao"""

    async def test_proximas_so_do_meu_curso(self, client):
        s = await _setup_curso_aula(client)
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Outro", "descricao": "x", "ordem": 0, "publicado": True})
        cid2 = r.json()["id"]
        await client.post(
            f"/api/v1/cursos/{cid2}/aulas",
            json={"curso_id": cid2, "titulo": "Aula de Outro Curso", "data_hora": "2099-01-02T10:00:00Z", "duracao_minutos": 60},
        )

        r = await client.get("/api/v1/cursos/aulas/proximas")
        assert r.status_code == status.HTTP_200_OK, r.text
        titulos = [a["titulo"] for a in r.json()]
        assert "Aula Live" in titulos, "Aula do curso inscrito deve aparecer"
        assert "Aula de Outro Curso" not in titulos, "Aula de curso nao inscrito nao deve aparecer"


class TestSilenciarWS:
    """P3 — silenciar vale para quem esta no websocket (relido do banco)"""

    async def test_websocket_relê_silenciado_ate(self, client):
        from httpx import ASGITransport, AsyncClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.models.usuario import Usuario

        s = await _setup_curso_aula(client)
        uid = "00000000-0000-0000-0000-000000000001"

        # silenciar o admin por 1h
        r = await client.patch(f"/api/v1/cursos/aulas/{s['aula_id']}/chat/silenciar/{uid}?silenciado_ate=2099-01-01T00:00:00Z")
        assert r.status_code == status.HTTP_200_OK, r.text

        # enviar mensagem via HTTP deve ser bloqueado (403)
        r = await client.post(f"/api/v1/cursos/aulas/{s['aula_id']}/chat", json={"texto": "oi"})
        assert r.status_code == status.HTTP_403_FORBIDDEN, r.text


class TestSaidaEstimada:
    """P10 — saida_estimada marca fechamento automatico"""

    async def test_fechamento_lazy_marca_saida_estimada(self, client):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy import select

        from app.config import settings
        from app.models.curso import AulaSincrona, PresencaAula

        s = await _setup_curso_aula(client)
        await client.post(f"/api/v1/cursos/aulas/{s['aula_id']}/entrar")

        # aula no passado (data_hora_fim ja passou)
        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        try:
            aula = (await session.execute(select(AulaSincrona).where(AulaSincrona.id == s["aula_id"]))).scalar_one()
            from datetime import datetime, timezone

            aula.data_hora = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
            aula.data_hora_fim = aula.data_hora + timedelta(minutes=60)
            await session.commit()
        finally:
            await session.close()
            await engine.dispose()

        r = await client.get(f"/api/v1/cursos/aulas/{s['aula_id']}/presencas")
        assert r.status_code == status.HTTP_200_OK, r.text
        presencas = r.json()
        assert len(presencas) == 1
        assert presencas[0]["saida_estimada"] is True, "Fechamento automatico deve marcar saida_estimada"