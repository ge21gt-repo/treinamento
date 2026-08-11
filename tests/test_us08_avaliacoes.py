"""Testes US-08: bug nota dissertativa (#46), correcao manual (#45) e peso (#47)"""

import uuid

from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.main import app
from app.models.avaliacao import RespostaParticipante, ResultadoAvaliacao
from app.services.auth import create_access_token


async def _setup_avaliacao_mista(client, nota_minima=50):
    """Avaliacao com 1 objetiva (10pts) + 1 dissertativa (10pts)."""
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso US08", "descricao": "x", "ordem": 0})
    curso_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "Mod", "descricao": "x", "ordem": 0})
    mod_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "Unid", "tipo": "conteudo", "ordem": 0})
    uni_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Mista", "tipo": "prova", "nota_minima": nota_minima})
    av_id = r.json()["id"]

    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10},
    )
    q_obj = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_obj, "texto": "4", "correta": True, "ordem": 0})
    alt_certa = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_obj, "texto": "5", "correta": False, "ordem": 1})
    alt_errada = r.json()["id"]

    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={"avaliacao_id": av_id, "enunciado": "Explique", "tipo": "dissertativa", "pontuacao": 10},
    )
    q_diss = r.json()["id"]

    await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    return {"av_id": av_id, "q_obj": q_obj, "alt_certa": alt_certa, "alt_errada": alt_errada, "q_diss": q_diss}


class TestBugNotaDissertativa:
    """Issue #46 — dissertativa pendente nao pode inflar o denominador"""

    async def test_dissertativa_pendente_nao_penaliza_objetivas(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Minha resposta"},
                ]
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["aprovado"] is True
        assert data["nota"] == 100.0, f"Esperava 100 com dissertativa pendente, veio {data['nota']}"

    async def test_dissertativa_pendente_sem_objetiva_certa_zerada(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_errada"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Resposta"},
                ]
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert data["nota"] == 0.0


class TestCorrecaoManual:
    """Issue #45 — endpoint de correcao manual de dissertativa"""

    async def test_corrigir_dissertativa_recalcula_nota(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Resposta boa"},
                ]
            },
        )
        assert r.status_code == status.HTTP_201_CREATED

        pendentes = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/correcoes-pendentes")
        assert pendentes.status_code == status.HTTP_200_OK
        items = pendentes.json()
        assert len(items) == 1
        resp_id = items[0]["resposta_id"]
        assert items[0]["resposta_texto"] == "Resposta boa"

        r = await client.patch(
            f"/api/v1/avaliacoes/respostas/{resp_id}/corrigir",
            json={"pontuacao_atribuida": 10},
        )
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["pontuacao_atribuida"] == 10
        assert data["corrigida_por"] is not None
        assert data["corrigida_em"] is not None

        resultado = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/resultados")
        assert resultado.status_code == status.HTTP_200_OK
        assert resultado.json()[0]["nota"] == 100.0

    async def test_corrigir_com_nota_parcial(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Resposta meia"},
                ]
            },
        )
        pendentes = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/correcoes-pendentes")
        resp_id = pendentes.json()[0]["resposta_id"]

        r = await client.patch(
            f"/api/v1/avaliacoes/respostas/{resp_id}/corrigir",
            json={"pontuacao_atribuida": 5},
        )
        assert r.status_code == status.HTTP_200_OK

        resultado = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/resultados")
        nota = resultado.json()[0]["nota"]
        assert nota == 75.0, f"10+5 de 20 = 75, veio {nota}"

    async def test_corrigir_resposta_nao_dissertativa_erro(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso ND", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "U", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Obj", "tipo": "prova"})
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "Q?", "tipo": "multipla_escolha"}
        )
        q_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "A", "correta": True, "ordem": 0})
        alt_id = r.json()["id"]
        await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        r = await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={"respostas": [{"questao_id": q_id, "alternativa_id": alt_id}]},
        )
        resp_id = None
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.config import settings

        url = settings.TEST_DATABASE_URL or settings.DATABASE_URL
        _eng = create_async_engine(url)
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        _maker = async_sessionmaker(_eng, class_=AsyncSession, expire_on_commit=False)
        session = _maker()
        try:
            res = await session.execute(select(RespostaParticipante).where(RespostaParticipante.questao_id == q_id))
            resp_id = res.scalar_one().id
        finally:
            await session.close()
            await _eng.dispose()

        r = await client.patch(
            f"/api/v1/avaliacoes/respostas/{resp_id}/corrigir",
            json={"pontuacao_atribuida": 5},
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST


class TestPesoRemovido:
    """Issue #47 — campo peso removido, criar avaliacao sem peso funciona"""

    async def test_criar_avaliacao_sem_peso(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso P", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "U", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Sem peso", "tipo": "prova"})
        assert r.status_code == status.HTTP_201_CREATED
        data = r.json()
        assert "peso" not in data
