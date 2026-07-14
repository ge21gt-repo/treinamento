"""Testes reais de autenticação/autorização — usam PostgreSQL e HTTP"""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import status
from sqlalchemy import text

from app.main import app
from app.config import settings
from app.services.auth import create_access_token, hash_password
from app.models.usuario import Usuario, UsuarioPerfil


async def _criar_usuario(perfil_nome, email, nome="User"):
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    eng = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        user = Usuario(
            id=uuid.uuid4(), nome_completo=nome, email=email,
            senha_hash=hash_password("test123"), ativo=True,
            status_credenciamento="aprovado", aceite_lgpd=True,
        )
        session.add(user)
        await session.flush()
        r = await session.execute(text("SELECT id FROM lms.perfis WHERE nome = :n"), {"n": perfil_nome})
        session.add(UsuarioPerfil(usuario_id=user.id, perfil_id=r.scalar_one()))
        await session.commit()
        uid = user.id
    await eng.dispose()
    return uid


async def _client_para(uid):
    token = create_access_token(data={"sub": str(uid)})
    transport = ASGITransport(app=app)
    ac = AsyncClient(transport=transport, base_url="http://test")
    ac.headers.update({"Authorization": f"Bearer {token}"})
    return ac


class TestAutenticacao:
    async def test_sem_token_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/cursos")
        assert r.status_code == 401

    async def test_token_invalido_401(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            ac.headers.update({"Authorization": "Bearer token_invalido"})
            r = await ac.get("/api/v1/cursos")
        assert r.status_code == 401


class TestPermissoesCurso:
    async def test_qualquer_usuario_pode_criar_curso(self, db_clean):
        uid = await _criar_usuario("participante", "part@test.com")
        async with await _client_para(uid) as ac:
            r = await ac.post("/api/v1/cursos", json={"titulo": "Curso", "descricao": "x", "ordem": 0})
        assert r.status_code == 201

    async def test_qualquer_usuario_pode_editar_curso(self, db_clean):
        uid = await _criar_usuario("participante", "part2@test.com")
        async with await _client_para(uid) as ac:
            r1 = await ac.post("/api/v1/cursos", json={"titulo": "Original", "descricao": "x", "ordem": 0})
            cid = r1.json()["id"]
            r2 = await ac.patch(f"/api/v1/cursos/{cid}", json={"titulo": "Editado"})
        assert r2.status_code == 200


class TestPermissoesInscricao:
    async def test_participante_pode_se_inscrever(self, db_clean):
        uid = await _criar_usuario("participante", "p3@test.com")
        async with await _client_para(uid) as ac:
            r = await ac.post("/api/v1/cursos", json={"titulo": "C", "descricao": "x", "ordem": 0})
            cid = r.json()["id"]
            r = await ac.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
        assert r.status_code == 201

    async def test_participante_nao_pode_inscrever_outro(self, db_clean):
        uid = await _criar_usuario("participante", "p4@test.com")
        async with await _client_para(uid) as ac:
            r = await ac.post("/api/v1/cursos", json={"titulo": "C", "descricao": "x", "ordem": 0})
            cid = r.json()["id"]
            outro = str(uuid.uuid4())
            r = await ac.post("/api/v1/cursos/inscricoes", json={"curso_id": cid, "usuario_id": outro})
        assert r.status_code == 403


class TestPermissoesConteudo:
    async def test_participante_nao_pode_criar_conteudo(self, db_clean):
        uid = await _criar_usuario("participante", "p5@test.com")
        async with await _client_para(uid) as ac:
            r = await ac.post("/api/v1/conteudos", json={
                "unidade_id": 1, "tipo_midia": "link", "titulo": "X",
                "url_arquivo": "https://exemplo.com",
            })
        assert r.status_code == 403

    async def test_participante_nao_pode_gerenciar_materiais(self, db_clean):
        uid = await _criar_usuario("participante", "p6@test.com")
        async with await _client_para(uid) as ac:
            r = await ac.post("/api/v1/conteudos/materiais", json={
                "curso_id": 1, "titulo": "X", "tipo": "pdf",
                "url_arquivo": "https://exemplo.com/doc.pdf",
            })
        assert r.status_code == 403


class TestPermissoesAdmin:
    async def test_admin_pode_inscrever_outro_em_curso(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "C", "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post("/api/v1/auth/registro", json={
            "nome_completo": "Outro User", "email": "outro@test.com",
            "senha": "123456", "aceite_lgpd": True,
        })
        outro_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid, "usuario_id": outro_id})
        assert r.status_code == 201
