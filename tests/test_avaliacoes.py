import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestAvaliacoesAuth:
    async def test_list_avaliacoes_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/avaliacoes")
        assert r.status_code in AUTH_OK

    async def test_create_avaliacao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/avaliacoes", json={"titulo": "x", "tipo": "quiz"})
        assert r.status_code in AUTH_OK

    async def test_get_avaliacao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/avaliacoes/1")
        assert r.status_code in AUTH_OK


class TestAvaliacoesCRUD:
    async def _setup(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso AV", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod AV", "descricao": "x", "ordem": 0}
        )
        mod_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid AV", "tipo": "conteudo", "ordem": 0}
        )
        return r.json()["id"]

    async def test_create_and_get_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post(
            "/api/v1/avaliacoes",
            json={"unidade_id": uni_id, "titulo": "Prova Final", "tipo": "prova", "nota_minima": 70.0},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["titulo"] == "Prova Final"
        av_id = data["id"]

        r = await client.get(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Prova Final"

    async def test_update_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Original", "tipo": "quiz"})
        av_id = r.json()["id"]

        r = await client.patch(f"/api/v1/avaliacoes/{av_id}", json={"titulo": "Atualizado"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Atualizado"

    async def test_delete_avaliacao(self, client):
        uni_id = await self._setup(client)
        r = await client.post(
            "/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Pra Deletar", "tipo": "quiz"}
        )
        av_id = r.json()["id"]

        r = await client.delete(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

        r = await client.get(f"/api/v1/avaliacoes/{av_id}")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_list_avaliacoes(self, client):
        r = await client.get("/api/v1/avaliacoes")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)


class TestQuestoesAlternativas:
    async def _setup(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Q", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod Q", "descricao": "x", "ordem": 0}
        )
        mod_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid Q", "tipo": "conteudo", "ordem": 0}
        )
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval Q", "tipo": "prova"})
        return r.json()["id"]

    async def test_create_questao_and_alternativas(self, client):
        av_id = await self._setup(client)

        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={"avaliacao_id": av_id, "enunciado": "Quanto é 2+2?", "tipo": "multipla_escolha", "pontuacao": 10},
        )
        assert r.status_code == status.HTTP_201_CREATED
        q_id = r.json()["id"]

        r = await client.post(
            "/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "4", "correta": True, "ordem": 0}
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["correta"] is True

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/questoes")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) == 1

        r = await client.get(f"/api/v1/avaliacoes/questoes/{q_id}/alternativas")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) == 1

    async def test_update_questao(self, client):
        av_id = await self._setup(client)
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Old", "tipo": "dissertativa"}
        )
        q_id = r.json()["id"]

        r = await client.patch(f"/api/v1/avaliacoes/questoes/{q_id}", json={"enunciado": "Updated"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["enunciado"] == "Updated"


class TestRespostasResultados:
    async def test_register_resposta_and_resultado(self, client, admin_user):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso R", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod R", "descricao": "x", "ordem": 0}
        )
        mod_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid R", "tipo": "conteudo", "ordem": 0}
        )
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval R", "tipo": "prova"})
        av_id = r.json()["id"]

        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={"avaliacao_id": av_id, "enunciado": "Pergunta?", "tipo": "multipla_escolha"},
        )
        q_id = r.json()["id"]

        r = await client.post(
            "/api/v1/avaliacoes/alternativas",
            json={"questao_id": q_id, "texto": "Correta", "correta": True, "ordem": 0},
        )
        alt_id = r.json()["id"]

        uid = str(admin_user.id)
        r = await client.post(
            "/api/v1/avaliacoes/respostas", json={"usuario_id": uid, "questao_id": q_id, "alternativa_id": alt_id}
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["correta"] is True

        r = await client.post(
            "/api/v1/avaliacoes/resultados",
            json={"usuario_id": uid, "avaliacao_id": av_id, "nota": 85.0, "aprovado": True},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/resultados/{uid}")
        assert r.status_code == status.HTTP_200_OK
        assert len(r.json()) >= 1


class TestTipoQuestaoValidation:
    async def _setup_avaliacao(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso T", "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": cid, "titulo": "Mod T", "descricao": "x", "ordem": 0})
        mid = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mid, "titulo": "Unid T", "tipo": "conteudo", "ordem": 0})
        uid = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uid, "titulo": "Aval T", "tipo": "prova"})
        return r.json()["id"]

    async def test_criar_questao_tipo_invalido(self, client):
        av_id = await self._setup_avaliacao(client)
        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={"avaliacao_id": av_id, "enunciado": "Teste", "tipo": "tipo_invalido"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_atualizar_questao_tipo_invalido(self, client):
        av_id = await self._setup_avaliacao(client)
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Teste", "tipo": "dissertativa"}
        )
        q_id = r.json()["id"]
        r = await client.patch(f"/api/v1/avaliacoes/questoes/{q_id}", json={"tipo": "invalido"})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_vf_limit_2_alternativas(self, client):
        av_id = await self._setup_avaliacao(client)
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "V ou F?", "tipo": "verdadeiro_falso"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "V", "correta": True, "ordem": 0})
        assert r.status_code == status.HTTP_201_CREATED
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "F", "correta": False, "ordem": 1})
        assert r.status_code == status.HTTP_201_CREATED
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Terceira", "correta": False, "ordem": 2})
        assert r.status_code == status.HTTP_400_BAD_REQUEST


class TestAlternativaCRUD:
    async def test_patch_alternativa(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Alt", "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": cid, "titulo": "Mod Alt", "descricao": "x", "ordem": 0})
        mid = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mid, "titulo": "Unid Alt", "tipo": "conteudo", "ordem": 0})
        uid = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uid, "titulo": "Aval Alt", "tipo": "prova"})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Original", "correta": False, "ordem": 0})
        alt_id = r.json()["id"]

        r = await client.patch(f"/api/v1/avaliacoes/alternativas/{alt_id}", json={"texto": "Atualizada", "correta": True})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["texto"] == "Atualizada"
        assert r.json()["correta"] is True

    async def test_delete_alternativa(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Del", "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": cid, "titulo": "Mod Del", "descricao": "x", "ordem": 0})
        mid = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mid, "titulo": "Unid Del", "tipo": "conteudo", "ordem": 0})
        uid = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uid, "titulo": "Aval Del", "tipo": "prova"})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Delete me", "correta": False, "ordem": 0})
        alt_id = r.json()["id"]

        r = await client.delete(f"/api/v1/avaliacoes/alternativas/{alt_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT


class TestSubmeterAvaliacao:
    async def _setup_completo(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Sub", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod Sub", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid Sub", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval Sub", "tipo": "prova", "nota_minima": 50})
        av_id = r.json()["id"]

        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "4", "correta": True, "ordem": 0})
        alt_certa = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "5", "correta": False, "ordem": 1})
        alt_errada = r.json()["id"]

        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        return {"av_id": av_id, "q_id": q_id, "alt_certa": alt_certa, "alt_errada": alt_errada}

    async def test_submeter_correcao_automatica(self, client):
        setup = await self._setup_completo(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={"respostas": [{"questao_id": setup["q_id"], "alternativa_id": setup["alt_certa"]}]},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["aprovado"] is True
        assert data["nota"] == 100.0

    async def test_submeter_resposta_errada(self, client):
        setup = await self._setup_completo(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={"respostas": [{"questao_id": setup["q_id"], "alternativa_id": setup["alt_errada"]}]},
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["aprovado"] is False
        assert data["nota"] == 0.0

    async def test_submeter_sem_inscricao(self, client, admin_user):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso NoIns", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod NoIns", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid NoIns", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval NoIns", "tipo": "prova"})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]

        r = await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={"respostas": [{"questao_id": q_id}]},
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_limite_tentativas(self, client):
        setup = await self._setup_completo(client)
        for i in range(3):
            r = await client.post(
                f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
                json={"respostas": [{"questao_id": setup["q_id"], "alternativa_id": setup["alt_certa"]}]},
            )
            assert r.status_code == status.HTTP_201_CREATED
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={"respostas": [{"questao_id": setup["q_id"], "alternativa_id": setup["alt_certa"]}]},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "tentativas" in r.json()["detail"].lower()


class TestFeedbackResultados:
    async def test_meus_resultados(self, client):
        r = await client.get("/api/v1/avaliacoes/meus-resultados")
        assert r.status_code == status.HTTP_200_OK
        assert isinstance(r.json(), list)

    async def test_feedback_endpoint(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso F", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod F", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid F", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval F", "tipo": "prova", "nota_minima": 50})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha", "explicacao": "Porque sim"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Correta", "correta": True, "ordem": 0})
        alt_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        r = await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={"respostas": [{"questao_id": q_id, "alternativa_id": alt_id}]},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "questoes" in data
        assert len(data["questoes"]) >= 1
        questao = data["questoes"][0]
        assert questao["explicacao"] == "Porque sim"
        alternativas = questao["alternativas"]
        assert any(a["escolhida"] for a in alternativas)
        assert any(a["correta"] for a in alternativas)

    async def test_estatisticas(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso E", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod E", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid E", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval E", "tipo": "prova", "nota_minima": 50})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Correta", "correta": True, "ordem": 0})
        alt_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})

        r = await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={"respostas": [{"questao_id": q_id, "alternativa_id": alt_id}]},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/estatisticas")
        assert r.status_code == status.HTTP_200_OK
        stats = r.json()
        assert stats["total_tentativas"] >= 1
        assert stats["total_aprovados"] >= 1
        assert stats["taxa_aprovacao"] > 0
