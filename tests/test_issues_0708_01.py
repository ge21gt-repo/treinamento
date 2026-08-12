import pytest
from fastapi import status

from app.main import app

pytestmark = pytest.mark.db

AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


async def _setup_avaliacao_dissertativa(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Iss", "descricao": "x", "ordem": 0})
    curso_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod Iss", "descricao": "x", "ordem": 0})
    mod_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid Iss", "tipo": "conteudo", "ordem": 0})
    uni_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval Iss", "tipo": "prova", "nota_minima": 50})
    av_id = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Disserte", "tipo": "dissertativa", "pontuacao": 10}
    )
    q_id = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10}
    )
    q2_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q2_id, "texto": "4", "correta": True, "ordem": 0})
    alt_certa = r.json()["id"]
    r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    return {"curso_id": curso_id, "av_id": av_id, "q_id": q_id, "q2_id": q2_id, "alt_certa": alt_certa}


class TestInboxCorrecoes:
    async def test_inbox_agregado_retorna_pendentes_com_contexto(self, client):
        s = await _setup_avaliacao_dissertativa(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "resposta_texto": "Resposta"}]},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get("/api/v1/avaliacoes/correcoes-pendentes")
        assert r.status_code == status.HTTP_200_OK
        itens = r.json()
        assert len(itens) >= 1
        item = itens[0]
        assert item["resposta_texto"] == "Resposta"
        assert item["avaliacao_titulo"] == "Aval Iss"
        assert item["curso_id"] is not None
        assert item["curso_titulo"] is not None
        assert item["unidade_titulo"] is not None

    async def test_inbox_agregado_vazio_sem_pendentes(self, client):
        s = await _setup_avaliacao_dissertativa(client)
        r = await client.get("/api/v1/avaliacoes/correcoes-pendentes")
        assert r.status_code == status.HTTP_200_OK
        assert r.json() == []

    async def test_inbox_agregado_requer_autenticacao(self):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/avaliacoes/correcoes-pendentes")
        assert r.status_code in AUTH_OK


class TestEstatisticaQuestao:
    async def test_estatistica_por_questao_com_acertos(self, client):
        s = await _setup_avaliacao_dissertativa(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q2_id"], "alternativa_id": s["alt_certa"]}]},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/{s['av_id']}/estatisticas/questoes")
        assert r.status_code == status.HTTP_200_OK
        questoes = r.json()
        assert len(questoes) == 2
        por_id = {q["questao_id"]: q for q in questoes}
        me = por_id[s["q2_id"]]
        assert me["tipo"] == "multipla_escolha"
        assert me["respondida"] >= 1
        assert me["acertos"] >= 1
        assert me["taxa_acerto"] == 100.0

    async def test_estatistica_dissertativa_aguardando_correcao(self, client):
        s = await _setup_avaliacao_dissertativa(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "resposta_texto": "Resposta"}]},
        )
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/avaliacoes/{s['av_id']}/estatisticas/questoes")
        assert r.status_code == status.HTTP_200_OK
        questoes = r.json()
        por_id = {q["questao_id"]: q for q in questoes}
        diss = por_id[s["q_id"]]
        assert diss["tipo"] == "dissertativa"
        assert diss["respondida"] >= 1
        assert diss["aguardando_correcao"] >= 1


class TestInscricaoDuplicada:
    async def test_inscricao_duplicada_retorna_409(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Dup", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_409_CONFLICT
        assert "ja inscrito" in r.json()["detail"].lower()


class TestTempoLimite:
    async def _setup_avaliacao_com_tempo(self, client, tempo_min=1):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Tempo", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod Tempo", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid Tempo", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes",
            json={"unidade_id": uni_id, "titulo": "Aval Tempo", "tipo": "prova", "tempo_limite_min": tempo_min},
        )
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "Certa", "correta": True, "ordem": 0})
        alt_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        return {"av_id": av_id, "q_id": q_id, "alt_id": alt_id}

    async def test_iniciado_em_obrigatorio_com_tempo_limite(self, client):
        s = await self._setup_avaliacao_com_tempo(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "iniciado_em" in r.json()["detail"].lower()

    async def test_iniciado_em_no_futuro_retorna_400(self, client):
        from datetime import datetime, timedelta, timezone

        s = await self._setup_avaliacao_com_tempo(client)
        futuro = datetime.now(timezone.utc) + timedelta(hours=2)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={
                "respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}],
                "iniciado_em": futuro.isoformat(),
            },
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert "futuro" in r.json()["detail"].lower()

    async def test_iniciado_em_valido_passa(self, client):
        from datetime import datetime, timedelta, timezone

        s = await self._setup_avaliacao_com_tempo(client, tempo_min=5)
        agora = datetime.now(timezone.utc)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={
                "respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}],
                "iniciado_em": agora.isoformat(),
            },
        )
        assert r.status_code == status.HTTP_201_CREATED


