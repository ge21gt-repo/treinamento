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


async def test_patch_permite_alterar_o_ativo_de_outro_usuario(client, participante_user):
    r = await client.patch(f"/api/v1/usuarios/{participante_user.id}", json={"ativo": False})

    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["ativo"] is False


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
