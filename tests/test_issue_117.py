"""Issue #117 — trocar o perfil de um usuario existente.

A role muda primeiro no Keycloak; o local so acompanha depois. Cobre a matriz
(quem atribui o que e quem pode ser editado), auto-alteracao, escalada, usuario
sem vinculo com o Keycloak e falha do Keycloak sem mudar o local.
"""

import uuid

from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.main import app
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import create_access_token


async def _criar_usuario(perfil_nome: str, keycloak_sub: str | None = "kc-alvo"):
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    usuario_id = uuid.uuid4()
    email = f"{perfil_nome}.{usuario_id.hex[:8]}@test.com"
    try:
        async with maker() as sessao:
            perfil_id = (
                await sessao.execute(
                    text("SELECT id FROM lms.perfis WHERE nome = :n"), {"n": perfil_nome}
                )
            ).scalar_one()
            sessao.add(
                Usuario(
                    id=usuario_id,
                    nome_completo=perfil_nome,
                    email=email,
                    senha_hash=None,
                    ativo=True,
                    status_credenciamento="aprovado",
                    aceite_lgpd=True,
                    keycloak_sub=keycloak_sub,
                    auth_provider="keycloak" if keycloak_sub else "local",
                )
            )
            await sessao.flush()
            sessao.add(UsuarioPerfil(usuario_id=usuario_id, perfil_id=perfil_id))
            await sessao.commit()
    finally:
        await engine.dispose()
    return usuario_id, email


async def _perfis(usuario_id: uuid.UUID) -> list[str]:
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as sessao:
            from sqlalchemy.orm import selectinload

            user = (
                await sessao.execute(
                    select(Usuario)
                    .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
                    .where(Usuario.id == usuario_id)
                )
            ).scalar_one()
            return [up.perfil.nome for up in user.perfis]
    finally:
        await engine.dispose()


def _token(usuario_id: uuid.UUID, email: str) -> str:
    return create_access_token(data={"sub": str(usuario_id), "email": email})


def _cliente(token: str) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_admin_geral_troca_participante_para_instrutor(
    db_clean, admin_user, admin_token, keycloak_admin_fake
):
    alvo_id, _ = await _criar_usuario("participante")

    async with _cliente(admin_token) as ac:
        r = await ac.put(f"/api/v1/usuarios/{alvo_id}/perfil", json={"perfil": "instrutor"})

    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["perfis"] == ["instrutor"]
    assert keycloak_admin_fake["roles"] == [("kc-alvo", "instrutor")]
    assert await _perfis(alvo_id) == ["instrutor"]


async def test_nao_altera_o_proprio_perfil(db_clean, admin_user, admin_token, keycloak_admin_fake):
    async with _cliente(admin_token) as ac:
        r = await ac.put(
            f"/api/v1/usuarios/{admin_user.id}/perfil", json={"perfil": "administrador"}
        )

    assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
    assert "proprio perfil" in r.json()["detail"]
    assert keycloak_admin_fake["roles"] == []


async def test_administrador_nao_promove_a_administrador_geral(
    db_clean, keycloak_admin_fake
):
    editor_id, editor_email = await _criar_usuario("administrador", keycloak_sub="kc-editor")
    alvo_id, _ = await _criar_usuario("participante")

    async with _cliente(_token(editor_id, editor_email)) as ac:
        r = await ac.put(
            f"/api/v1/usuarios/{alvo_id}/perfil", json={"perfil": "administrador_geral"}
        )

    assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
    assert keycloak_admin_fake["roles"] == []
    assert await _perfis(alvo_id) == ["participante"]


async def test_administrador_nao_edita_usuario_auditor(db_clean, keycloak_admin_fake):
    editor_id, editor_email = await _criar_usuario("administrador", keycloak_sub="kc-editor")
    alvo_id, _ = await _criar_usuario("auditor")

    async with _cliente(_token(editor_id, editor_email)) as ac:
        r = await ac.put(f"/api/v1/usuarios/{alvo_id}/perfil", json={"perfil": "participante"})

    assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
    assert await _perfis(alvo_id) == ["auditor"]


async def test_usuario_sem_keycloak_sub_da_400(db_clean, admin_token, keycloak_admin_fake):
    alvo_id, _ = await _criar_usuario("participante", keycloak_sub=None)

    async with _cliente(admin_token) as ac:
        r = await ac.put(f"/api/v1/usuarios/{alvo_id}/perfil", json={"perfil": "instrutor"})

    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.text
    assert keycloak_admin_fake["roles"] == []


async def test_falha_do_keycloak_da_502_e_nao_muda_o_local(
    db_clean, admin_token, monkeypatch
):
    from app.services import keycloak_admin as ka

    async def falha(*args, **kwargs):
        raise ka.KeycloakAdminError("indisponivel")

    monkeypatch.setattr(ka, "definir_role", falha)

    alvo_id, _ = await _criar_usuario("participante")

    async with _cliente(admin_token) as ac:
        r = await ac.put(f"/api/v1/usuarios/{alvo_id}/perfil", json={"perfil": "instrutor"})

    assert r.status_code == status.HTTP_502_BAD_GATEWAY, r.text
    assert await _perfis(alvo_id) == ["participante"]
