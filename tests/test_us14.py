from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import status

from app.api.deps import get_current_user
from app.main import app

pytestmark = pytest.mark.db


async def _criar_curso(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Forum", "descricao": "x", "ordem": 0})
    return r.json()["id"]


async def _criar_usuario_com_perfil(perfil_nome: str, email: str, nome: str = "User"):
    """Cria um usuario aprovado com um perfil atribuido, para simular um segundo autor."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from tests.conftest import _assign_perfil, _create_user

    engine = create_async_engine(settings.TEST_DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = maker()
    try:
        user = await _create_user(session, uuid4(), email, nome, perfil_nome)
        await _assign_perfil(session, user.id, perfil_nome)
        await session.commit()
        return user
    finally:
        await session.close()
        await engine.dispose()


@asynccontextmanager
async def _como(usuario):
    """Troca temporariamente o current_user do client (fixture) para simular outro autor."""
    anterior = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: usuario
    try:
        yield
    finally:
        if anterior is not None:
            app.dependency_overrides[get_current_user] = anterior
        else:
            app.dependency_overrides.pop(get_current_user, None)


class TestModeracaoConteudo:
    async def test_topico_com_termo_bloqueado_422(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Vamos falar de campanha eleitoral", "conteudo": "texto"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "bloqueado" in r.json()["detail"].lower()

    async def test_topico_normal_criado(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Duvida sobre modulo 3", "conteudo": "nao entendi a unidade 2"},
        )
        assert r.status_code == status.HTTP_201_CREATED

    async def test_resposta_com_termo_bloqueado_422(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "Topico normal", "conteudo": "conteudo ok"},
        )
        topico_id = r.json()["id"]
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "apoie o candidato numero 22"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "bloqueado" in r.json()["detail"].lower()


class TestModeracaoService:
    async def test_normalizar_remove_acentos(self):
        from app.services.moderacao import normalizar

        assert normalizar("Eleição Presidente") == "eleicao presidente"

    async def test_checar_conteudo_detecta_termo(self, db_clean):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.services.moderacao import checar_conteudo, seed_termos_default

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        try:
            await seed_termos_default(session)
            termo = await checar_conteudo(session, "vamos organizar uma campanha eleitoral forte")
            assert termo is not None
            assert termo[0] == "campanha eleitoral"
            assert termo[1] == "politico"
            termo2 = await checar_conteudo(session, "conteudo totalmente normal")
            assert termo2 is None
        finally:
            await session.close()
            await engine.dispose()


class TestTermosBloqueadosCRUD:
    async def test_listar_termos_seed(self, client):
        r = await client.get("/api/v1/comunicacao/forum/termos-bloqueados")
        assert r.status_code == status.HTTP_200_OK
        termos = r.json()
        assert len(termos) >= 1
        assert any(t["termo"] == "campanha eleitoral" for t in termos)

    async def test_criar_termo_novo(self, client):
        termo_unico = f"guerra-{uuid4()}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico, "categoria": "improprio"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["termo"] == termo_unico

        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": f"topico sobre {termo_unico}", "conteudo": "x"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_criar_termo_duplicado_409(self, client):
        termo_unico = f"dup-{uuid4()}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico},
        )
        assert r.status_code == status.HTTP_201_CREATED
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": termo_unico},
        )
        assert r.status_code == status.HTTP_409_CONFLICT

    async def test_excluir_termo(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": f"excluir-{uuid4()}"},
        )
        termo_id = r.json()["id"]
        r = await client.delete(f"/api/v1/comunicacao/forum/termos-bloqueados/{termo_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT
        r = await client.get("/api/v1/comunicacao/forum/termos-bloqueados")
        assert all(t["id"] != termo_id for t in r.json())


class TestCRUDTopicoCompleto:
    async def test_criar_topico_curso_inexistente_404(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": 999999999, "titulo": "topico", "conteudo": "conteudo"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_topico_tem_autor_nome(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico autor", "conteudo": "conteudo"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["autor_nome"] != ""

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()[0]["autor_nome"] != ""

    async def test_listar_topicos_curso_inexistente_404(self, client):
        r = await client.get("/api/v1/comunicacao/forum/999999999")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_resposta_tem_autor_nome(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico resp", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "minha resposta"},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["autor_nome"] != ""

    async def test_resposta_topico_inexistente_404(self, client):
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": 999999999, "conteudo": "resposta"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestThreadingRespostas:
    async def test_resposta_a_resposta_monta_arvore(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico thread", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]

        r1 = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta raiz"},
        )
        raiz_id = r1.json()["id"]
        r2 = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta filha", "resposta_pai_id": raiz_id},
        )
        assert r2.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/comunicacao/forum/topico/{topico_id}/respostas")
        assert r.status_code == status.HTTP_200_OK
        respostas = r.json()
        assert len(respostas) == 1  # so a raiz no topo
        assert respostas[0]["id"] == raiz_id
        assert len(respostas[0]["respostas_filhas"]) == 1
        assert respostas[0]["respostas_filhas"][0]["conteudo"] == "resposta filha"

    async def test_resposta_pai_de_outro_topico_404(self, client):
        curso_id = await _criar_curso(client)
        r1 = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico A", "conteudo": "conteudo"},
        )
        r2 = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico B", "conteudo": "conteudo"},
        )
        raiz = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": r1.json()["id"], "conteudo": "raiz do topico A"},
        )
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": r2.json()["id"], "conteudo": "resposta", "resposta_pai_id": raiz.json()["id"]},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_resposta_pai_inexistente_404(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico pai", "conteudo": "conteudo"},
        )
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": r.json()["id"], "conteudo": "resposta", "resposta_pai_id": 999999999},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestFixarFecharTopico:
    async def test_fixar_topico(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico fixar", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        r = await client.patch(f"/api/v1/comunicacao/forum/topico/{topico_id}/fixar?fixado=true")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["fixado"] is True

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        assert r.json()[0]["id"] == topico_id  # fixado vem primeiro

    async def test_fechar_topico_bloqueia_respostas(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico fechar", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        r = await client.patch(f"/api/v1/comunicacao/forum/topico/{topico_id}/fechar?fechado=true")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["fechado"] is True

        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta em topico fechado"},
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_fixar_topico_inexistente_404(self, client):
        r = await client.patch("/api/v1/comunicacao/forum/topico/999999999/fixar")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestEditarExcluirTopico:
    """Issue 50: autoria em editar/excluir topico, e o filtro tambem valendo no PATCH."""

    async def test_autor_edita_proprio_topico(self, client):
        curso_id = await _criar_curso(client)
        autor = await _criar_usuario_com_perfil("participante", f"autor-{uuid4()}@test.com")
        async with _como(autor):
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "titulo original", "conteudo": "conteudo original"},
            )
            assert r.status_code == status.HTTP_201_CREATED, r.text
            topico_id = r.json()["id"]

            r = await client.patch(
                f"/api/v1/comunicacao/forum/topico/{topico_id}",
                json={"titulo": "titulo corrigido"},
            )
            assert r.status_code == status.HTTP_200_OK, r.text
            assert r.json()["titulo"] == "titulo corrigido"
            assert r.json()["atualizado_em"] is not None

    async def test_outro_participante_nao_edita_nem_exclui_topico_alheio(self, client):
        curso_id = await _criar_curso(client)
        autor = await _criar_usuario_com_perfil("participante", f"autor2-{uuid4()}@test.com")
        outro = await _criar_usuario_com_perfil("participante", f"outro-{uuid4()}@test.com")

        async with _como(autor):
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "topico do autor", "conteudo": "conteudo"},
            )
            topico_id = r.json()["id"]

        async with _como(outro):
            r = await client.patch(
                f"/api/v1/comunicacao/forum/topico/{topico_id}",
                json={"titulo": "tentativa de sequestro"},
            )
            assert r.status_code == status.HTTP_403_FORBIDDEN

            r = await client.delete(f"/api/v1/comunicacao/forum/topico/{topico_id}")
            assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_moderador_edita_topico_de_outro(self, client):
        curso_id = await _criar_curso(client)
        autor = await _criar_usuario_com_perfil("participante", f"autor3-{uuid4()}@test.com")
        async with _como(autor):
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "topico moderavel", "conteudo": "conteudo"},
            )
            topico_id = r.json()["id"]

        # fora do "async with", o client volta a autenticar como admin_user (administrador_geral, tem forum:moderar)
        r = await client.patch(
            f"/api/v1/comunicacao/forum/topico/{topico_id}",
            json={"titulo": "moderado pelo admin"},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_patch_topico_passa_pelo_filtro(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico limpo", "conteudo": "conteudo limpo"},
        )
        topico_id = r.json()["id"]
        r = await client.patch(
            f"/api/v1/comunicacao/forum/topico/{topico_id}",
            json={"conteudo": "agora com campanha eleitoral no meio"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "bloqueado" in r.json()["detail"].lower()

    async def test_editar_topico_inexistente_404(self, client):
        r = await client.patch("/api/v1/comunicacao/forum/topico/999999999", json={"titulo": "x"})
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestEditarExcluirResposta:
    """Issue 49: PATCH/DELETE de resposta, com autoria e soft delete preservando a arvore."""

    async def test_autor_edita_propria_resposta(self, client):
        curso_id = await _criar_curso(client)
        autor = await _criar_usuario_com_perfil("participante", f"ra-{uuid4()}@test.com")
        async with _como(autor):
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "topico resp edit", "conteudo": "conteudo"},
            )
            topico_id = r.json()["id"]
            r = await client.post(
                "/api/v1/comunicacao/forum/respostas",
                json={"topico_id": topico_id, "conteudo": "resposta com erro de digitacao"},
            )
            resposta_id = r.json()["id"]

            r = await client.patch(
                f"/api/v1/comunicacao/forum/respostas/{resposta_id}",
                json={"conteudo": "resposta corrigida"},
            )
            assert r.status_code == status.HTTP_200_OK, r.text
            assert r.json()["conteudo"] == "resposta corrigida"
            assert r.json()["atualizado_em"] is not None

    async def test_outro_participante_nao_edita_nem_exclui_resposta_alheia(self, client):
        curso_id = await _criar_curso(client)
        autor = await _criar_usuario_com_perfil("participante", f"rb-{uuid4()}@test.com")
        outro = await _criar_usuario_com_perfil("participante", f"rc-{uuid4()}@test.com")

        async with _como(autor):
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": "topico resp alheia", "conteudo": "conteudo"},
            )
            topico_id = r.json()["id"]
            r = await client.post(
                "/api/v1/comunicacao/forum/respostas",
                json={"topico_id": topico_id, "conteudo": "resposta do autor"},
            )
            resposta_id = r.json()["id"]

        async with _como(outro):
            r = await client.patch(
                f"/api/v1/comunicacao/forum/respostas/{resposta_id}",
                json={"conteudo": "sequestro de resposta"},
            )
            assert r.status_code == status.HTTP_403_FORBIDDEN

            r = await client.delete(f"/api/v1/comunicacao/forum/respostas/{resposta_id}")
            assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_excluir_resposta_e_soft_delete_preserva_filhas(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico thread removida", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        raiz = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta raiz"},
        )
        raiz_id = raiz.json()["id"]
        filha = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta filha", "resposta_pai_id": raiz_id},
        )
        assert filha.status_code == status.HTTP_201_CREATED

        r = await client.delete(f"/api/v1/comunicacao/forum/respostas/{raiz_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

        r = await client.get(f"/api/v1/comunicacao/forum/topico/{topico_id}/respostas")
        assert r.status_code == status.HTTP_200_OK
        respostas = r.json()
        assert len(respostas) == 1  # raiz continua no topo, so marcada como removida
        assert respostas[0]["id"] == raiz_id
        assert respostas[0]["conteudo"] == "[mensagem removida]"
        assert respostas[0]["removida"] is True
        assert len(respostas[0]["respostas_filhas"]) == 1
        assert respostas[0]["respostas_filhas"][0]["conteudo"] == "resposta filha"

    async def test_excluir_resposta_ja_removida_404(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico dupla exclusao", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        raiz = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta unica"},
        )
        resposta_id = raiz.json()["id"]
        r = await client.delete(f"/api/v1/comunicacao/forum/respostas/{resposta_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT
        r = await client.delete(f"/api/v1/comunicacao/forum/respostas/{resposta_id}")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_patch_resposta_passa_pelo_filtro(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico resp filtro", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        r = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta limpa"},
        )
        resposta_id = r.json()["id"]
        r = await client.patch(
            f"/api/v1/comunicacao/forum/respostas/{resposta_id}",
            json={"conteudo": "apoie o candidato numero 22"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_editar_resposta_inexistente_404(self, client):
        r = await client.patch(
            "/api/v1/comunicacao/forum/respostas/999999999",
            json={"conteudo": "x"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestFiltroPalavraInteira:
    """Issue 51: casamento por palavra/frase inteira (nao substring) + semente revisada."""

    async def test_substring_dentro_de_palavra_maior_nao_bloqueia(self, client):
        raiz = f"zzterm{uuid4().hex[:8]}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": raiz, "categoria": "politico"},
        )
        assert r.status_code == status.HTTP_201_CREATED

        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": f"discussao sobre pre{raiz}pos no material", "conteudo": "x"},
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text

    async def test_palavra_inteira_ainda_bloqueia(self, client):
        raiz = f"zzterm{uuid4().hex[:8]}"
        r = await client.post(
            "/api/v1/comunicacao/forum/termos-bloqueados",
            json={"termo": raiz, "categoria": "politico"},
        )
        assert r.status_code == status.HTTP_201_CREATED

        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": f"discussao sobre {raiz} no material", "conteudo": "x"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_seed_nao_bloqueia_vocabulario_administrativo_legitimo(self, client):
        curso_id = await _criar_curso(client)
        for texto in [
            "quem e o presidente da comissao de licitacao?",
            "o candidato aprovado no concurso deve comparecer",
            "o lote foi repartido em duas parcelas no edital",
            "citacao do decreto do governador sobre a lei 14133",
        ]:
            r = await client.post(
                "/api/v1/comunicacao/forum",
                json={"curso_id": curso_id, "titulo": texto, "conteudo": "duvida sobre o material"},
            )
            assert r.status_code == status.HTTP_201_CREATED, f"{texto!r} -> {r.text}"

    async def test_erro_inclui_categoria(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "campanha eleitoral do vereador", "conteudo": "x"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "categoria" in r.json()["detail"].lower()
        assert "politico" in r.json()["detail"].lower()


class TestListaTopicosContagemOrdenacao:
    """Issue 52: respostas_count + ultima_atividade na listagem, e ordenacao por atividade."""

    async def test_respostas_count_e_ultima_atividade(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico com respostas", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta 1"},
        )
        r2 = await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": topico_id, "conteudo": "resposta 2"},
        )
        ultima_resposta_em = r2.json()["criado_em"]

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        assert r.status_code == status.HTTP_200_OK
        item = next(t for t in r.json() if t["id"] == topico_id)
        assert item["respostas_count"] == 2
        assert item["ultima_atividade"] == ultima_resposta_em

    async def test_topico_sem_resposta_usa_criado_em_como_atividade(self, client):
        curso_id = await _criar_curso(client)
        r = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico sem resposta", "conteudo": "conteudo"},
        )
        topico_id = r.json()["id"]
        criado_em = r.json()["criado_em"]

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        item = next(t for t in r.json() if t["id"] == topico_id)
        assert item["respostas_count"] == 0
        assert item["ultima_atividade"] == criado_em

    async def test_ordenacao_padrao_por_atividade(self, client):
        curso_id = await _criar_curso(client)
        r_antigo = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico antigo mas ativo", "conteudo": "conteudo"},
        )
        antigo_id = r_antigo.json()["id"]
        r_novo = await client.post(
            "/api/v1/comunicacao/forum",
            json={"curso_id": curso_id, "titulo": "topico novo sem atividade", "conteudo": "conteudo"},
        )
        novo_id = r_novo.json()["id"]
        # resposta recente no topico antigo o torna mais ativo que o novo
        await client.post(
            "/api/v1/comunicacao/forum/respostas",
            json={"topico_id": antigo_id, "conteudo": "reacende a discussao"},
        )

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}")
        ids_em_ordem = [t["id"] for t in r.json()]
        assert ids_em_ordem.index(antigo_id) < ids_em_ordem.index(novo_id)

        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}?ordenar_por=recentes")
        ids_em_ordem = [t["id"] for t in r.json()]
        assert ids_em_ordem.index(novo_id) < ids_em_ordem.index(antigo_id)

    async def test_ordenar_por_invalido_422(self, client):
        curso_id = await _criar_curso(client)
        r = await client.get(f"/api/v1/comunicacao/forum/{curso_id}?ordenar_por=chute")
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
