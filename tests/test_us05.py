"""Testes reais US-05 — aulas síncronas, chat, reorder, árvore via API"""
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status

from app.main import app


async def criar_curso(client, titulo="Curso US05"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0, "publicado": True})
    return r.json()["id"]


async def criar_modulo(client, curso_id, titulo="Modulo"):
    r = await client.post("/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": titulo, "descricao": "x", "ordem": 0})
    return r.json()["id"]


async def criar_unidade(client, modulo_id, titulo="Unidade"):
    r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": modulo_id, "titulo": titulo, "tipo": "conteudo", "descricao": "x", "conteudo_url": "https://exemplo.com/aula.pdf", "ordem": 0})
    return r.json()["id"]


class TestAulasSincronas:
    async def test_criar_aula(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json={
            "curso_id": curso_id, "titulo": "Aula 1", "data_hora": "2026-08-01T14:00:00Z", "duracao_minutos": 60,
        })
        assert r.status_code == 201
        assert r.json()["titulo"] == "Aula 1"

    async def test_listar_aulas_do_curso(self, client):
        curso_id = await criar_curso(client)
        await client.post(f"/api/v1/cursos/{curso_id}/aulas", json={
            "curso_id": curso_id, "titulo": "Aula Unica", "data_hora": "2026-08-01T14:00:00Z", "duracao_minutos": 60,
        })
        r = await client.get(f"/api/v1/cursos/{curso_id}/aulas")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    async def test_listar_proximas_aulas(self, client):
        curso_id = await criar_curso(client)
        await client.post(f"/api/v1/cursos/{curso_id}/aulas", json={
            "curso_id": curso_id, "titulo": "Aula Proxima", "data_hora": "2026-12-01T14:00:00Z", "duracao_minutos": 60,
        })
        r = await client.get("/api/v1/cursos/aulas/proximas")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_atualizar_aula(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json={
            "curso_id": curso_id, "titulo": "Original", "data_hora": "2026-08-01T14:00:00Z", "duracao_minutos": 60,
        })
        aula_id = r.json()["id"]
        r = await client.patch(f"/api/v1/cursos/aulas/{aula_id}", json={"titulo": "Atualizada"})
        assert r.status_code == 200
        assert r.json()["titulo"] == "Atualizada"

    async def test_deletar_aula(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json={
            "curso_id": curso_id, "titulo": "Deletar", "data_hora": "2026-08-01T14:00:00Z", "duracao_minutos": 60,
        })
        aula_id = r.json()["id"]
        r = await client.delete(f"/api/v1/cursos/aulas/{aula_id}")
        assert r.status_code == 204


class TestChat:
    async def test_enviar_mensagem(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(f"/api/v1/cursos/{curso_id}/chat", json={"texto": "Ola turma!"})
        assert r.status_code == 201
        assert r.json()["texto"] == "Ola turma!"

    async def test_listar_mensagens(self, client):
        curso_id = await criar_curso(client)
        await client.post(f"/api/v1/cursos/{curso_id}/chat", json={"texto": "Msg 1"})
        await client.post(f"/api/v1/cursos/{curso_id}/chat", json={"texto": "Msg 2"})
        r = await client.get(f"/api/v1/cursos/{curso_id}/chat")
        assert r.status_code == 200
        assert len(r.json()) >= 2


class TestReordenacao:
    async def test_reordenar_modulos(self, client):
        curso_id = await criar_curso(client)
        m1 = await criar_modulo(client, curso_id, "B")
        m2 = await criar_modulo(client, curso_id, "A")
        r = await client.patch("/api/v1/cursos/modulos/reorder", json=[
            {"id": m2, "ordem": 0},
            {"id": m1, "ordem": 1},
        ])
        assert r.status_code == 204

    async def test_reordenar_unidades(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        u1 = await criar_unidade(client, mod_id, "Z")
        u2 = await criar_unidade(client, mod_id, "Y")
        r = await client.patch("/api/v1/cursos/unidades/reorder", json=[
            {"id": u2, "ordem": 0},
            {"id": u1, "ordem": 1},
        ])
        assert r.status_code == 204


class TestArvore:
    async def test_arvore_retorna_estrutura_aninhada(self, client):
        curso_id = await criar_curso(client, "Curso Arvore")
        mod_id = await criar_modulo(client, curso_id, "Modulo A")
        uni_id = await criar_unidade(client, mod_id, "Unidade 1")
        r = await client.get(f"/api/v1/cursos/{curso_id}/arvore")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == curso_id
        assert len(data["modulos"]) >= 1
        assert any(u["id"] == uni_id for m in data["modulos"] for u in m["unidades"])
