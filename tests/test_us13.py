import pytest
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db


async def _criar_participante_com_token(sufixo: str):
    """Participante sem inscricao em curso nenhum, com token valido (issue 43)."""
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.services.auth import create_access_token
    from tests.conftest import _assign_perfil, _create_user

    engine = create_async_engine(settings.TEST_DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    try:
        user = await _create_user(session, uuid.uuid4(), f"forasteiro-{sufixo}@test.com", "Forasteiro", "participante")
        await _assign_perfil(session, user.id, "participante")
        await session.commit()
        token = create_access_token(data={"sub": str(user.id), "email": user.email})
        return user, token
    finally:
        await session.close()
        await engine.dispose()


async def _criar_aula(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Chat", "descricao": "x", "ordem": 0})
    curso_id = r.json()["id"]
    r = await client.post(
        f"/api/v1/cursos/{curso_id}/aulas",
        json={
            "curso_id": curso_id,
            "titulo": "Aula Chat",
            "descricao": "x",
            "data_hora": "2026-08-10T14:00:00Z",
            "data_hora_fim": "2026-08-10T15:00:00Z",
        },
    )
    return r.json()["id"]


class TestChatAulaREST:
    async def test_enviar_e_listar_mensagem(self, client):
        aula_id = await _criar_aula(client)
        r = await client.post(
            f"/api/v1/cursos/aulas/{aula_id}/chat",
            json={"texto": "Ola, primeira mensagem"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["texto"] == "Ola, primeira mensagem"
        assert data["aula_id"] == aula_id
        assert data["usuario_nome"] != ""

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/chat")
        assert r.status_code == status.HTTP_200_OK
        msgs = r.json()
        assert len(msgs) >= 1
        assert msgs[-1]["texto"] == "Ola, primeira mensagem"

    async def test_enviar_mensagem_vazia_422(self, client):
        aula_id = await _criar_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "   "})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_chat_aula_inexistente_404(self, client):
        r = await client.get("/api/v1/cursos/aulas/999999999/chat")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_mensagens_sao_por_aula(self, client):
        aula1 = await _criar_aula(client)
        aula2 = await _criar_aula(client)
        await client.post(f"/api/v1/cursos/aulas/{aula1}/chat", json={"texto": "msg aula 1"})
        await client.post(f"/api/v1/cursos/aulas/{aula2}/chat", json={"texto": "msg aula 2"})

        r1 = await client.get(f"/api/v1/cursos/aulas/{aula1}/chat")
        r2 = await client.get(f"/api/v1/cursos/aulas/{aula2}/chat")
        assert len(r1.json()) == 1 and r1.json()[0]["texto"] == "msg aula 1"
        assert len(r2.json()) == 1 and r2.json()[0]["texto"] == "msg aula 2"


class TestChatAulaWebSocket:
    async def test_websocket_envia_e_recebe_mensagem(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws:
                inicial = ws.receive_json()
                assert inicial["type"] == "presenca_inicial", inicial
                ws.send_json({"texto": "ola via websocket"})
                data = ws.receive_json()
                assert data["type"] == "mensagem"
                assert data["texto"] == "ola via websocket"
                assert data["usuario_nome"] != ""

    async def test_websocket_token_invalido_recusado(self):
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with TestClient(app) as tc:
            with pytest.raises(WebSocketDisconnect):
                with tc.websocket_connect("/api/v1/cursos/aulas/1/chat/ws?token=invalido"):
                    pass


class TestModeracaoChat:
    async def test_excluir_mensagem_remove_do_historico(self, client):
        aula_id = await _criar_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "msg para excluir"})
        msg_id = r.json()["id"]

        r = await client.delete(f"/api/v1/cursos/aulas/{aula_id}/chat/{msg_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/chat")
        assert all(m["id"] != msg_id for m in r.json())

    async def test_excluir_mensagem_inexistente_404(self, client):
        aula_id = await _criar_aula(client)
        r = await client.delete(f"/api/v1/cursos/aulas/{aula_id}/chat/999999999")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_silenciar_usuario_bloqueia_envio(self, client):
        aula_id = await _criar_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "antes de silenciar"})
        assert r.status_code == status.HTTP_201_CREATED

        from datetime import datetime, timedelta, timezone
        from urllib.parse import quote

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/chat")
        usuario_id = r.json()[0]["usuario_id"]
        ate = datetime.now(timezone.utc) + timedelta(hours=1)
        r = await client.patch(
            f"/api/v1/cursos/aulas/{aula_id}/chat/silenciar/{usuario_id}?silenciado_ate={quote(ate.isoformat())}"
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["silenciado_ate"].startswith(ate.isoformat()[:19])

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "depois de silenciar"})
        assert r.status_code == status.HTTP_403_FORBIDDEN


class TestComunicacaoTempoReal:
    async def test_broadcast_entre_duas_conexoes(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws1:
                assert ws1.receive_json()["type"] == "presenca_inicial"
                with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws2:
                    assert ws2.receive_json()["type"] == "presenca_inicial"
                    ws1.send_json({"texto": "broadcast para todos"})
                    data1 = ws1.receive_json()
                    data2 = ws2.receive_json()
                    assert data1["texto"] == "broadcast para todos"
                    assert data2["texto"] == "broadcast para todos"
                    assert data1["id"] == data2["id"]

    async def test_usuario_silenciado_bloqueado_no_websocket(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from datetime import datetime, timedelta, timezone
        from urllib.parse import quote

        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "inicial"})
        usuario_id = r.json()["usuario_id"]
        ate = datetime.now(timezone.utc) + timedelta(hours=1)
        r = await client.patch(
            f"/api/v1/cursos/aulas/{aula_id}/chat/silenciar/{usuario_id}?silenciado_ate={quote(ate.isoformat())}"
        )
        assert r.status_code == status.HTTP_200_OK

        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws:
                assert ws.receive_json()["type"] == "presenca_inicial"
                ws.send_json({"texto": "silenciado nao pode enviar"})
                data = ws.receive_json()
                assert data["type"] == "erro"
                assert "silenciado" in data["detail"].lower()


class TestUsuarioPerfilNoChat:
    """Issue 35: a mensagem do chat da aula diz o papel de quem fala."""

    async def test_admin_tem_perfil_no_envio_rest(self, client):
        aula_id = await _criar_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "sou admin"})
        assert r.status_code == status.HTTP_201_CREATED, r.text
        assert r.json()["usuario_perfil"] == "administrador_geral"

    async def test_admin_tem_perfil_na_listagem(self, client):
        aula_id = await _criar_aula(client)
        await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "msg"})
        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/chat")
        assert r.json()[0]["usuario_perfil"] == "administrador_geral"

    async def test_admin_tem_perfil_no_broadcast_ws(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws:
                ws.receive_json()
                ws.send_json({"texto": "via ws"})
                data = ws.receive_json()
                assert data["usuario_perfil"] == "administrador_geral"

    async def test_participante_sem_perfil_destacado(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Chat Perfil", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={
                "curso_id": curso_id,
                "titulo": "Aula Perfil",
                "data_hora": "2026-08-10T14:00:00Z",
                "data_hora_fim": "2026-08-10T15:00:00Z",
            },
        )
        aula_id = r.json()["id"]

        participante, _ = await _criar_participante_com_token("perfilchat")
        from app.api.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: participante
        try:
            r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
            assert r.status_code == status.HTTP_201_CREATED, r.text
            r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "sou participante"})
            assert r.status_code == status.HTTP_201_CREATED, r.text
            assert r.json()["usuario_perfil"] is None
        finally:
            app.dependency_overrides.pop(get_current_user, None)


class TestChatAulaExigeInscricao:
    """Issue 43: chat da aula exige inscricao no curso (ou permissao de moderar)."""

    async def test_forasteiro_nao_le_nem_envia_chat_da_aula(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Chat Fechado", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={
                "curso_id": curso_id,
                "titulo": "Aula Fechada",
                "data_hora": "2026-08-10T14:00:00Z",
                "data_hora_fim": "2026-08-10T15:00:00Z",
            },
        )
        aula_id = r.json()["id"]

        forasteiro, forasteiro_token = await _criar_participante_com_token("forachat")
        from app.api.deps import get_current_user

        app.dependency_overrides[get_current_user] = lambda: forasteiro
        try:
            r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/chat")
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
            r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/chat", json={"texto": "nao deveria entrar"})
            assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with TestClient(app) as tc:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={forasteiro_token}"):
                    pass
            assert exc_info.value.code == 4403


class TestPresencaWebSocketDisconnect:
    """Issue 41 (ponto 1): fechar a aba avisa quem mais esta no socket."""

    async def test_disconnect_transmite_saiu(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as observador:
                assert observador.receive_json()["type"] == "presenca_inicial"

                with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}"):
                    pass  # fecha ao sair do "with" -- equivalente a fechar a aba

                evento = observador.receive_json()
                assert evento["type"] == "presenca", evento
                assert evento["acao"] == "saiu", evento


class TestPresencaInicialUsaPresencaOficial:
    """Issue 41 (ponto 2): presenca_inicial vem de PresencaAula, nao de quem tem o socket aberto."""

    async def test_socket_sem_entrar_nao_aparece_na_lista(self, client, admin_token):
        aula_id = await _criar_aula(client)
        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws:
                inicial = ws.receive_json()
                assert inicial["type"] == "presenca_inicial"
                assert inicial["presentes"] == [], "sem presenca oficial (sem /entrar), a lista deve vir vazia"

    async def test_presenca_sem_socket_aparece_na_lista(self, client, admin_token, admin_user):
        aula_id = await _criar_aula(client)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED, r.text

        from fastapi.testclient import TestClient

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/api/v1/cursos/aulas/{aula_id}/chat/ws?token={admin_token}") as ws:
                inicial = ws.receive_json()
                usuario_ids = [p["usuario_id"] for p in inicial["presentes"]]
                assert str(admin_user.id) in usuario_ids
