"""Testes da issue #123: o administrador nao conseguia aprovar credenciamento e a
lista de pendentes nao filtrava pelo escopo.

HIERARQUIA_APROVACAO nao tinha a chave "administrador". O perfil tem a permissao
credenciamento:aprovar e passava na rota, mas pode_aprovar devolvia falso e a
acao morria em 400 - a mensagem "Fora do seu escopo de aprovação" da tela.
Valia para aprovar e para rejeitar, porque as duas leem a mesma tabela.
"""

import os
import uuid

from fastapi import status
from sqlalchemy import text

from app.api.deps import get_current_user
from app.main import app

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]


def _engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(_URL)


async def _criar_usuario_com_perfil(nome, email, perfil_nome):
    """Cria usuario aprovado e ativo com o perfil pedido, e devolve o objeto.

    Vai direto no banco: /auth/registro tem limite de 10 por minuto (slowapi) e
    nasce pendente, que nao serve para quem vai ser o aprovador.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.usuario import Usuario, UsuarioPerfil

    eng = _engine()
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                id=uuid.uuid4(),
                nome_completo=nome,
                email=email,
                ativo=True,
                aceite_lgpd=True,
                status_credenciamento="aprovado",
            )
            sessao.add(user)
            await sessao.flush()
            perfil_id = (
                await sessao.execute(text("SELECT id FROM lms.perfis WHERE nome = :n"), {"n": perfil_nome})
            ).scalar_one()
            sessao.add(UsuarioPerfil(usuario_id=user.id, perfil_id=perfil_id))
            await sessao.commit()
            return user
    finally:
        await eng.dispose()


async def _criar_solicitacao(perfil_solicitado, email):
    """Cria um usuario pendente com solicitacao pendente e devolve o id dela."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.credenciamento import SolicitacaoCredenciamento
    from app.models.usuario import Usuario

    eng = _engine()
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                id=uuid.uuid4(),
                nome_completo="Pendente " + perfil_solicitado,
                email=email,
                ativo=False,
                aceite_lgpd=True,
                status_credenciamento="pendente",
            )
            sessao.add(user)
            await sessao.flush()
            sol = SolicitacaoCredenciamento(
                usuario_id=user.id, perfil_solicitado=perfil_solicitado, status="pendente"
            )
            sessao.add(sol)
            await sessao.commit()
            return sol.id
    finally:
        await eng.dispose()


class _ComoUsuario:
    """Troca o get_current_user e devolve o anterior no fim."""

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.anterior = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: self.user
        return self.user

    def __exit__(self, *exc):
        if self.anterior is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = self.anterior
        return False


class TestIssue123AdministradorAprova:
    """Item 1 do 'o que resolveria': incluir administrador na hierarquia."""

    async def test_administrador_aprova_participante(self, client):
        admin = await _criar_usuario_com_perfil("Adm", "adm123@test.com", "administrador")
        sol = await _criar_solicitacao("participante", "pend.part123@test.com")

        with _ComoUsuario(admin):
            r = await client.post(
                "/api/v1/credenciamento/solicitacoes/{}/aprovar".format(sol), json={"observacao": "ok"}
            )
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_administrador_aprova_gestor(self, client):
        admin = await _criar_usuario_com_perfil("Adm2", "adm2.123@test.com", "administrador")
        sol = await _criar_solicitacao("gestor", "pend.gestor123@test.com")

        with _ComoUsuario(admin):
            r = await client.post(
                "/api/v1/credenciamento/solicitacoes/{}/aprovar".format(sol), json={"observacao": "ok"}
            )
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_administrador_rejeita_participante(self, client):
        """A rejeicao le a mesma tabela, entao estava quebrada do mesmo jeito."""
        admin = await _criar_usuario_com_perfil("Adm3", "adm3.123@test.com", "administrador")
        sol = await _criar_solicitacao("participante", "pend.rej123@test.com")

        with _ComoUsuario(admin):
            r = await client.post(
                "/api/v1/credenciamento/solicitacoes/{}/rejeitar".format(sol),
                json={"observacao": "fora do perfil"},
            )
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_administrador_nao_aprova_auditor(self, client):
        """A matriz de produto da issue #116 e explicita: nao cria auditor."""
        admin = await _criar_usuario_com_perfil("Adm4", "adm4.123@test.com", "administrador")
        sol = await _criar_solicitacao("auditor", "pend.aud123@test.com")

        with _ComoUsuario(admin):
            r = await client.post(
                "/api/v1/credenciamento/solicitacoes/{}/aprovar".format(sol), json={"observacao": "ok"}
            )
        assert r.status_code == status.HTTP_400_BAD_REQUEST, r.text

    async def test_admin_geral_continua_aprovando(self, client):
        """Regressao: o perfil que ja funcionava nao pode ter sido afetado."""
        sol = await _criar_solicitacao("instrutor", "pend.instr123@test.com")
        r = await client.post(
            "/api/v1/credenciamento/solicitacoes/{}/aprovar".format(sol), json={"observacao": "ok"}
        )
        assert r.status_code == status.HTTP_200_OK, r.text


class TestIssue123ListaFiltradaPeloEscopo:
    """Item 2: a lista pendente devolvia tudo (havia um TODO no codigo)."""

    async def test_administrador_nao_ve_auditor(self, client):
        admin = await _criar_usuario_com_perfil("Adm5", "adm5.123@test.com", "administrador")
        await _criar_solicitacao("participante", "l.part123@test.com")
        await _criar_solicitacao("gestor", "l.gestor123@test.com")
        await _criar_solicitacao("auditor", "l.aud123@test.com")

        with _ComoUsuario(admin):
            r = await client.get("/api/v1/credenciamento/solicitacoes/pendentes")
        assert r.status_code == status.HTTP_200_OK, r.text

        perfis = {s["perfil_solicitado"] for s in r.json()}
        assert "participante" in perfis
        assert "gestor" in perfis
        assert "auditor" not in perfis

    async def test_instrutor_so_ve_o_proprio_escopo(self, client):
        """Instrutor aprova gestor e participante, mais nada."""
        instrutor = await _criar_usuario_com_perfil("Instr", "instr123@test.com", "instrutor")
        await _criar_solicitacao("participante", "i.part123@test.com")
        await _criar_solicitacao("gestor", "i.gestor123@test.com")
        await _criar_solicitacao("auditor", "i.aud123@test.com")
        await _criar_solicitacao("administrador", "i.adm123@test.com")

        with _ComoUsuario(instrutor):
            r = await client.get("/api/v1/credenciamento/solicitacoes/pendentes")
        assert r.status_code == status.HTTP_200_OK, r.text

        assert {s["perfil_solicitado"] for s in r.json()} == {"participante", "gestor"}

    async def test_tudo_que_a_lista_mostra_e_aprovavel(self, client):
        """O critério de aceite, direto: nada que a lista mostra pode dar 400."""
        admin = await _criar_usuario_com_perfil("Adm6", "adm6.123@test.com", "administrador")
        for perfil in ("participante", "gestor", "instrutor", "auditor"):
            await _criar_solicitacao(perfil, "c." + perfil + "123@test.com")

        with _ComoUsuario(admin):
            r = await client.get("/api/v1/credenciamento/solicitacoes/pendentes")
            assert r.status_code == status.HTTP_200_OK, r.text
            listadas = r.json()
            assert listadas, "a lista nao deveria vir vazia"

            for s in listadas:
                ap = await client.post(
                    "/api/v1/credenciamento/solicitacoes/{}/aprovar".format(s["id"]),
                    json={"observacao": "ok"},
                )
                assert ap.status_code == status.HTTP_200_OK, "{}: {}".format(
                    s["perfil_solicitado"], ap.text
                )
