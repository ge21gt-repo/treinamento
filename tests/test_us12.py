import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.db


async def _criar_aula(client, data_hora_fim=None, em_curso=False):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso Presenca", "descricao": "x", "ordem": 0})
    curso_id = r.json()["id"]
    payload = {
        "curso_id": curso_id,
        "titulo": "Aula Presenca",
        "descricao": "x",
        "data_hora": "2026-08-10T14:00:00Z",
        "duracao_minutos": 60,
    }
    if data_hora_fim is not None:
        payload["data_hora_fim"] = data_hora_fim
    if em_curso:
        payload["data_hora"] = "2099-01-01T14:00:00Z"
        payload.pop("data_hora_fim", None)
    r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json=payload)
    return curso_id, r.json()["id"]


class TestFechamentoLazy:
    async def test_presencas_fechadas_quando_aula_encerrada(self, client):
        _, aula_id = await _criar_aula(client, data_hora_fim="2026-08-10T15:00:00Z")
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["hora_saida"] is None

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/presencas")
        assert r.status_code == status.HTTP_200_OK
        presencas = r.json()
        assert len(presencas) >= 1
        p = presencas[0]
        assert p["hora_saida"] is not None
        assert p["tempo_permanencia_seg"] >= 0

    async def test_presencas_nao_fechadas_quando_aula_em_curso(self, client):
        _, aula_id = await _criar_aula(client, em_curso=True)
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/presencas")
        assert r.status_code == status.HTTP_200_OK
        presencas = r.json()
        assert len(presencas) >= 1
        assert presencas[0]["hora_saida"] is None

    async def test_presencas_ja_fechadas_nao_sao_alteradas(self, client):
        _, aula_id = await _criar_aula(client, data_hora_fim="2026-08-10T15:00:00Z")
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/sair")
        assert r.status_code == status.HTTP_200_OK
        saida_saida = r.json()["hora_saida"]

        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/presencas")
        assert r.status_code == status.HTTP_200_OK
        presencas = r.json()
        assert len(presencas) >= 1
        assert presencas[0]["hora_saida"] == saida_saida

    async def test_presencas_aula_inexistente_404(self, client):
        r = await client.get("/api/v1/cursos/aulas/999999999/presencas")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestRelatorioPresencas:
    async def _setup_aula_com_presencas(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Rel", "descricao": "x", "ordem": 0})
        curso_id = r.json()["id"]
        r = await client.post(
            f"/api/v1/cursos/{curso_id}/aulas",
            json={
                "curso_id": curso_id,
                "titulo": "Aula Rel",
                "descricao": "x",
                "data_hora": "2026-08-10T14:00:00Z",
                "data_hora_fim": "2026-08-10T15:00:00Z",
            },
        )
        aula_id = r.json()["id"]
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code == status.HTTP_201_CREATED
        return aula_id

    async def test_relatorio_csv_retorna_arquivo(self, client):
        aula_id = await self._setup_aula_com_presencas(client)
        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/presencas/relatorio?formato=csv")
        assert r.status_code == status.HTTP_200_OK
        assert "text/csv" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        body = r.content.decode("utf-8-sig")
        assert "Relatorio de presenca" in body
        assert "Participante" in body

    async def test_relatorio_aula_inexistente_404(self, client):
        r = await client.get("/api/v1/cursos/aulas/999999999/presencas/relatorio?formato=csv")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_relatorio_formato_invalido_422(self, client):
        r = await client.get("/api/v1/cursos/aulas/1/presencas/relatorio?formato=xls")
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_relatorio_pdf_retorna_arquivo(self, client):
        aula_id = await self._setup_aula_com_presencas(client)
        r = await client.get(f"/api/v1/cursos/aulas/{aula_id}/presencas/relatorio?formato=pdf")
        assert r.status_code == status.HTTP_200_OK
        assert "application/pdf" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        assert r.content[:4] == b"%PDF"
