"""Issue #118, itens 2 e 3.

- item 2: a sincronizacao de perfis nao pode mais reativar/aprovar sozinha uma
  conta desativada pelo administrador;
- item 3: ninguem ativa ou desativa a propria conta pelo servidor.

O item 1 (refletir no Keycloak) depende da #115 e nao entra aqui.
"""

import uuid

from fastapi import status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.usuario import Usuario, UsuarioPerfil
from app.services.auth import hash_password
from app.services.keycloak import sincronizar_perfis_keycloak


async def test_patch_nao_permite_alterar_o_proprio_ativo(client, admin_user):
    r = await client.patch(f"/api/v1/usuarios/{admin_user.id}", json={"ativo": False})

    assert r.status_code == status.HTTP_403_FORBIDDEN, r.text
    assert "propria conta" in r.json()["detail"]


async def _criar_alvo(perfil: str = "participante", keycloak_sub: str | None = "kc-alvo"):
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    usuario_id = uuid.uuid4()
    email = f"alvo.{usuario_id.hex[:8]}@test.com"
    try:
        async with maker() as sessao:
            perfil_id = (
                await sessao.execute(text("SELECT id FROM lms.perfis WHERE nome = :n"), {"n": perfil})
            ).scalar_one()
            sessao.add(
                Usuario(
                    id=usuario_id,
                    nome_completo=perfil,
                    email=email,
                    senha_hash=hash_password("test123"),
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


async def _ativo(usuario_id: uuid.UUID) -> bool:
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as sessao:
            user = (
                await sessao.execute(select(Usuario).where(Usuario.id == usuario_id))
            ).scalar_one()
            return user.ativo
    finally:
        await engine.dispose()


async def test_patch_permite_alterar_o_ativo_de_outro_usuario(client, keycloak_admin_fake):
    alvo_id, _ = await _criar_alvo()

    r = await client.patch(f"/api/v1/usuarios/{alvo_id}", json={"ativo": False})

    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["ativo"] is False
    assert keycloak_admin_fake["habilitados"] == [("kc-alvo", False)]


async def test_patch_ativo_sem_keycloak_sub_da_400(client, keycloak_admin_fake):
    alvo_id, _ = await _criar_alvo(keycloak_sub=None)

    r = await client.patch(f"/api/v1/usuarios/{alvo_id}", json={"ativo": False})

    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.text
    assert keycloak_admin_fake["habilitados"] == []
    assert await _ativo(alvo_id) is True


async def test_patch_ativo_falha_no_keycloak_da_502_e_nao_muda(client, monkeypatch):
    from app.services import keycloak_admin as ka

    async def falha(*args, **kwargs):
        raise ka.KeycloakAdminError("indisponivel")

    monkeypatch.setattr(ka, "definir_habilitado", falha)
    alvo_id, _ = await _criar_alvo()

    r = await client.patch(f"/api/v1/usuarios/{alvo_id}", json={"ativo": False})

    assert r.status_code == status.HTTP_502_BAD_GATEWAY, r.text
    assert await _ativo(alvo_id) is True


async def test_sync_nao_reativa_usuario_desativado(db_clean):
    engine = create_async_engine(settings.DATABASE_URL)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    usuario_id = uuid.uuid4()

    try:
        async with maker() as sessao:
            perfil_id = (
                await sessao.execute(text("SELECT id FROM lms.perfis WHERE nome = 'gestor'"))
            ).scalar_one()
            sessao.add(
                Usuario(
                    id=usuario_id,
                    nome_completo="Gestor Desativado",
                    email="gestor.desativado@test.com",
                    senha_hash=hash_password("test123"),
                    ativo=False,
                    status_credenciamento="pendente",
                    aceite_lgpd=True,
                )
            )
            await sessao.flush()
            sessao.add(UsuarioPerfil(usuario_id=usuario_id, perfil_id=perfil_id))
            await sessao.commit()

        async with maker() as sessao:
            user = (
                await sessao.execute(
                    select(Usuario)
                    .options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))
                    .where(Usuario.id == usuario_id)
                )
            ).scalar_one()

            # O token traz perfil de gestao, que antes fazia o sync reativar.
            await sincronizar_perfis_keycloak(sessao, user, ["TRE_GESTOR"])
            await sessao.commit()

        async with maker() as sessao:
            user = (
                await sessao.execute(select(Usuario).where(Usuario.id == usuario_id))
            ).scalar_one()
            assert user.ativo is False, "o sync reativou uma conta desativada"
            assert user.status_credenciamento == "pendente", "o sync aprovou a conta sozinho"
    finally:
        await engine.dispose()
