"""Testes US-15: emissao e validacao de certificados digitais."""

from fastapi import status

pytestmark = __import__("pytest").mark.db


async def _setup_curso_com_avaliacao(client, nota_minima=50):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Certificado", "descricao": "x", "ordem": 0, "publicado": True, "carga_horaria": 40})
    curso_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "descricao": "x", "ordem": 0})
    mod_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "U", "tipo": "conteudo", "ordem": 0})
    uni_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes", json={"unidade_id": uni_id, "titulo": "Aval", "tipo": "prova", "nota_minima": nota_minima})
    av_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes/questoes", json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10})
    q_id = r.json()["id"]
    r = await client.post("/api/v1/avaliacoes/alternativas", json={"questao_id": q_id, "texto": "4", "correta": True, "ordem": 0})
    alt_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return {"curso_id": curso_id, "uni_id": uni_id, "av_id": av_id, "q_id": q_id, "alt_id": alt_id}


class TestEmissaoAutomatica:
    """T-15.2/15.3/15.4 — emissao ao concluir + PDF + QR + hash"""

    async def test_emitir_ao_concluir_com_avaliacao_aprovada(self, client):
        s = await _setup_curso_com_avaliacao(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text
        r = await client.post(f"/api/v1/cursos/unidades/{s['uni_id']}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/certificados/meus")
        assert r.status_code == status.HTTP_200_OK, r.text
        certs = r.json()
        assert len(certs) == 1, f"Esperava 1 certificado, veio {len(certs)}"
        cert = certs[0]
        assert cert["hash_validacao"], "Hash de validacao deve existir"
        assert cert["url_pdf"], "PDF deve ser gerado"
        assert cert["qr_code_url"], "QR Code deve ser gerado"
        assert float(cert["nota_final"]) == 100.0

    async def test_nao_duplica_na_reconclusao(self, client):
        s = await _setup_curso_com_avaliacao(client)
        await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        await client.post(f"/api/v1/cursos/unidades/{s['uni_id']}/concluir")
        await client.post(f"/api/v1/cursos/unidades/{s['uni_id']}/concluir")

        r = await client.get("/api/v1/certificados/meus")
        assert len(r.json()) == 1, "Concluir de novo nao deve reemitir"

    async def test_emitir_sem_avaliacao(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Sem Aval", "descricao": "x", "ordem": 0, "publicado": True, "carga_horaria": 20})
        curso_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "descricao": "x", "ordem": 0})
        mod_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mod_id, "titulo": "U", "tipo": "conteudo", "ordem": 0})
        uni_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED, r.text
        r = await client.post(f"/api/v1/cursos/unidades/{uni_id}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/certificados/meus")
        certs = r.json()
        assert len(certs) == 1, f"Curso sem avaliacao deve emitir certificado, veio {len(certs)}"
        assert certs[0]["nota_final"] is None


class TestValidacao:
    """T-15.5 — validacao publica + T-15.6 — meus certificados"""

    async def test_validar_publico_por_hash(self, client):
        s = await _setup_curso_com_avaliacao(client)
        await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        await client.post(f"/api/v1/cursos/unidades/{s['uni_id']}/concluir")

        r = await client.get("/api/v1/certificados/meus")
        cert = r.json()[0]

        r = await client.get(f"/api/v1/certificados/validar/{cert['hash_validacao']}")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["hash_validacao"] == cert["hash_validacao"]

    async def test_validar_hash_invalido_404(self, client):
        r = await client.get("/api/v1/certificados/validar/hash_inexistente")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_meus_certificados_sem_permissao_admin(self, client):
        """Participante comum ve os proprios certificados (sem certificado:visualizar)."""
        r = await client.get("/api/v1/certificados/meus")
        assert r.status_code == status.HTTP_200_OK, r.text

class TestPaginaValidacao:
    """T-15.5 — pagina publica HTML de validacao"""

    async def test_pagina_valida_retorna_html(self, client):
        s = await _setup_curso_com_avaliacao(client)
        await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        await client.post(f"/api/v1/cursos/unidades/{s['uni_id']}/concluir")

        r = await client.get("/api/v1/certificados/meus")
        cert = r.json()[0]

        r = await client.get(f"/api/v1/certificados/validar/{cert['hash_validacao']}/pagina")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "text/html" in r.headers.get("content-type", ""), r.headers
        assert "Certificado VALIDO" in r.text
        assert cert["hash_validacao"] in r.text

    async def test_pagina_hash_invalido_mostra_invalido(self, client):
        r = await client.get("/api/v1/certificados/validar/hash_inexistente/pagina")
        assert r.status_code == status.HTTP_200_OK
        assert "Certificado INVALIDO" in r.text
