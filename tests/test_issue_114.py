"""Testes da issue #114: PATCH /usuarios/{id} respondia 500 ao ativar e inativar,
mas a alteracao ficava gravada.

A excecao nascia em app/api/usuarios.py:202: o commit da linha 199 gravava o
UPDATE e o _serializar seguinte tocava atributo expirado, disparando IO sincrono
em contexto async (MissingGreenlet). O bug e da rota inteira, nao do campo
'ativo': qualquer campo passa pelo mesmo caminho de auditoria.
"""

import os

from fastapi import status
from sqlalchemy import text

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]


async def _linhas_de_auditoria(registro_id):
    """Conta as linhas de log_auditoria daquele usuario (nao ha rota de leitura por registro)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            r = await conn.execute(
                text(
                    "SELECT count(*) FROM lms.log_auditoria "
                    "WHERE tabela_afetada = 'usuarios' AND registro_id = :rid AND acao = 'atualizar'"
                ),
                {"rid": str(registro_id)},
            )
            return r.scalar_one()
    finally:
        await eng.dispose()


async def _criar_usuario(client, nome, email, telefone):
    """Cria o usuario direto no banco, nao por /auth/registro.

    A rota de registro tem limite de 10 por minuto (slowapi), e esses testes
    criam varios usuarios: usar HTTP aqui estoura a cota compartilhada e faz
    os testes vizinhos receberem 429. O alvo destes testes e o PATCH, nao o
    cadastro, entao o usuario e inserido pelo ORM (que aplica os defaults).
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.usuario import Usuario

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                nome_completo=nome,
                email=email,
                telefone=telefone,
                ativo=True,
                aceite_lgpd=True,
                status_credenciamento="aprovado",
            )
            sessao.add(user)
            await sessao.commit()
            return str(user.id)
    finally:
        await eng.dispose()


class TestIssue114PatchUsuario:
    """Critério de aceite da #114, item por item."""

    async def test_inativar_e_reativar_devolvem_200(self, client):
        uid = await _criar_usuario(client, "Alvo A", "alvo.a114@test.com", "11944440001")

        r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["ativo"] is False

        r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": True})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["ativo"] is True

    async def test_chamada_repetida_continua_200(self, client):
        """A issue e explicita: o erro repetia na segunda chamada."""
        uid = await _criar_usuario(client, "Alvo B", "alvo.b114@test.com", "11944440002")
        for valor in (False, True, False, True):
            r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": valor})
            assert r.status_code == status.HTTP_200_OK, f"ativo={valor}: {r.text}"
            assert r.json()["ativo"] is valor

    async def test_campo_comum_tambem_devolve_200(self, client):
        """O bug e da rota, nao do campo 'ativo'."""
        uid = await _criar_usuario(client, "Alvo C", "alvo.c114@test.com", "11944440003")
        r = await client.patch(
            f"/api/v1/usuarios/{uid}", json={"nome_completo": "Alvo C Editado", "cargo": "Analista"}
        )
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["nome_completo"] == "Alvo C Editado"
        assert r.json()["cargo"] == "Analista"

    async def test_alteracao_fica_gravada(self, client):
        uid = await _criar_usuario(client, "Alvo D", "alvo.d114@test.com", "11944440004")
        r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get(f"/api/v1/usuarios/{uid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["ativo"] is False

    async def test_uma_linha_de_auditoria_por_chamada(self, client):
        uid = await _criar_usuario(client, "Alvo E", "alvo.e114@test.com", "11944440005")
        assert await _linhas_de_auditoria(uid) == 0

        r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert await _linhas_de_auditoria(uid) == 1

        r = await client.patch(f"/api/v1/usuarios/{uid}", json={"ativo": True})
        assert r.status_code == status.HTTP_200_OK, r.text
        assert await _linhas_de_auditoria(uid) == 2

    async def test_nenhum_outro_usuario_muda(self, client):
        """A Tatiana relatou que outros usuarios mudavam de situacao."""
        a = await _criar_usuario(client, "Trio A", "trio.a114@test.com", "11944440006")
        b = await _criar_usuario(client, "Trio B", "trio.b114@test.com", "11944440007")
        c = await _criar_usuario(client, "Trio C", "trio.c114@test.com", "11944440008")

        antes = {}
        for uid in (a, b, c):
            antes[uid] = (await client.get(f"/api/v1/usuarios/{uid}")).json()["ativo"]

        r = await client.patch(f"/api/v1/usuarios/{b}", json={"ativo": False})
        assert r.status_code == status.HTTP_200_OK, r.text

        assert (await client.get(f"/api/v1/usuarios/{b}")).json()["ativo"] is False
        assert (await client.get(f"/api/v1/usuarios/{a}")).json()["ativo"] == antes[a]
        assert (await client.get(f"/api/v1/usuarios/{c}")).json()["ativo"] == antes[c]
