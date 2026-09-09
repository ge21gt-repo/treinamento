import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


async def criar_curso(client, titulo="Curso Teste"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    return r.json()["id"]


async def _criar_forasteiro():
    """Participante sem inscricao em curso nenhum (issue 43)."""
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from tests.conftest import _assign_perfil, _create_user

    engine = create_async_engine(settings.TEST_DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    try:
        email = f"forasteiro-{uuid.uuid4()}@test.com"
        user = await _create_user(session, uuid.uuid4(), email, "Forasteiro", "participante")
        await _assign_perfil(session, user.id, "participante")
        await session.commit()
        return user
    finally:
        await session.close()
        await engine.dispose()


class TestComunicacaoAuth:
    async def test_forum_list_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/comunicacao/forum/1")
        assert r.status_code in AUTH_OK

    async def test_create_forum_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/comunicacao/forum", json={"curso_id": 1, "titulo": "x", "conteudo": "x"})
        assert r.status_code in AUTH_OK

    async def test_chat_send_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/comunicacao/chat", json={"conteudo": "oi"})
        assert r.status_code in AUTH_OK


class TestForum:
    async def test_create_and_list_topicos(self, client):
        curso_id = await criar_curso(client, "Curso Forum")
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Duvida sobre Python", "conteudo": "Como funciona async/await?"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["titulo"] == "Duvida sobre Python"
        topico_id = data["id"]

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        assert r.status_code == status.HTTP_200_OK
        topicos = r.json()
        assert any(t["id"] == topico_id for t in topicos)

    async def test_get_update_delete_topico(self, client):
        curso_id = await criar_curso(client, "Curso Forum Update")
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Topico", "conteudo": "Conteudo original"},
        )
        topico_id = r.json()["id"]

        r = await client.get(f"/api/v1/comunicacao/forum/topico/{topico_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Topico"

        r = await client.patch(f"/api/v1/comunicacao/forum/topico/{topico_id}", json={"fixado": True, "fechado": True})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["fixado"] is True

        r = await client.delete(f"/api/v1/comunicacao/forum/topico/{topico_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    async def test_forum_respostas(self, client):
        curso_id = await criar_curso(client, "Curso Forum Respostas")
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Pergunta", "conteudo": "Qual a resposta?"},
        )
        topico_id = r.json()["id"]

        r = await client.post(
            "/api/v1/comunicacao/forum/respostas", json={"topico_id": topico_id, "conteudo": "Resposta 1"}
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/comunicacao/forum/topico/{topico_id}/respostas")
        assert r.status_code == status.HTTP_200_OK
        respostas = r.json()
        assert len(respostas) >= 1
        assert respostas[0]["conteudo"] == "Resposta 1"


class TestChat:
    async def test_send_and_list_chat(self, client, admin_user):
        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/sessoes",
            json={
                "titulo": "Sessao Chat",
                "instrutor_id": uid,
                "data_hora_inicio": "2026-07-14T10:00:00Z",
            },
        )
        sessao_id = r.json()["id"]

        r = await client.post("/api/v1/comunicacao/chat", json={"sessao_id": sessao_id, "conteudo": "Ola pessoal!"})
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["conteudo"] == "Ola pessoal!"

        r = await client.get(f"/api/v1/comunicacao/chat/{sessao_id}")
        assert r.status_code == status.HTTP_200_OK
        msgs = r.json()
        assert len(msgs) >= 1


class TestRotasLegadoSaoDeprecated:
    """Issue 44: chat de sessao (MensagemChat) marcado deprecated, sem remover nada."""

    async def test_openapi_marca_rotas_de_sessao_como_deprecated(self, client):
        r = await client.get("/openapi.json")
        assert r.status_code == status.HTTP_200_OK, r.text
        paths = r.json()["paths"]
        assert paths["/api/v1/comunicacao/chat"]["post"]["deprecated"] is True
        assert paths["/api/v1/comunicacao/chat/{sessao_id}"]["get"]["deprecated"] is True


class TestForumExigeInscricao:
    """Issue 43: forum de um curso e so para quem esta inscrito nele, ou quem modera."""

    async def test_forasteiro_nao_le_nem_cria_topico(self, client):
        curso_id = await criar_curso(client, "Curso Forum Fechado")
        forasteiro = await _criar_forasteiro()

        from app.api.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: forasteiro
        try:
            r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text

            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "nao deveria entrar", "conteudo": "x"},
            )
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    async def test_inscrito_le_e_cria_topico(self, client):
        curso_id = await criar_curso(client, "Curso Forum Aberto")
        participante = await _criar_forasteiro()

        from app.api.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: participante
        try:
            r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
            assert r.status_code == status.HTTP_201_CREATED, r.text

            r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
            assert r.status_code == status.HTTP_200_OK, r.text

            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "agora posso", "conteudo": "x"},
            )
            assert r.status_code == status.HTTP_201_CREATED, r.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestChatCursoExigeInscricao:
    """Issue 43: chat do curso e so para quem esta inscrito nele, ou quem modera."""

    async def test_forasteiro_nao_le_nem_envia(self, client):
        curso_id = await criar_curso(client, "Curso Chat Fechado")
        forasteiro = await _criar_forasteiro()

        from app.api.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: forasteiro
        try:
            r = await client.get(f"/api/v1/cursos/{curso_id}/chat")
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text

            r = await client.post(f"/api/v1/cursos/{curso_id}/chat", json={"texto": "nao deveria entrar"})
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)
