"""Testes da issue #120: a auditoria de alteracoes so guardava o IP.

log_auditoria nao tinha user_agent nem dispositivo - as colunas existiam apenas
em log_acesso -, entao a aba de Alteracoes dos Logs nao tinha o que mostrar nas
colunas Dispositivo e Navegador.

registrar_auditoria ja recebia o request, logo o user-agent estava ali, so nao
era lido nem gravado.
"""

import os
import uuid

from fastapi import status
from sqlalchemy import text

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
)


async def _ultima_auditoria(registro_id):
    """Le a linha de auditoria mais recente daquele registro.

    Nao ha rota que devolva a auditoria de um registro especifico, e a tabela e
    imutavel por trigger, entao o teste so faz SELECT.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            r = await conn.execute(
                text(
                    # host() e nao ::text: a coluna e INET e o cast devolveria
                    # "203.0.113.47/32", enquanto a rota serializa sem a mascara.
                    "SELECT host(ip_address), user_agent, dispositivo "
                    "FROM lms.log_auditoria "
                    "WHERE tabela_afetada = 'usuarios' AND registro_id = :rid "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"rid": str(registro_id)},
            )
            linha = r.first()
            assert linha is not None, "nenhuma linha de auditoria foi gravada"
            return {"ip_address": linha[0], "user_agent": linha[1], "dispositivo": linha[2]}
    finally:
        await eng.dispose()


async def _criar_usuario(email):
    """Cria o usuario direto no banco (o /auth/registro tem limite por minuto)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.models.usuario import Usuario

    eng = create_async_engine(_URL)
    try:
        maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
        async with maker() as sessao:
            user = Usuario(
                id=uuid.uuid4(),
                nome_completo="Alvo 120",
                email=email,
                ativo=True,
                aceite_lgpd=True,
                status_credenciamento="aprovado",
            )
            sessao.add(user)
            await sessao.commit()
            return str(user.id)
    finally:
        await eng.dispose()


class TestIssue120AuditoriaGuardaDispositivo:
    """Critério de aceite: a linha de auditoria traz os tres campos preenchidos."""

    async def test_alteracao_grava_os_tres_campos(self, client):
        uid = await _criar_usuario("ua.desktop120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Analista"},
            headers={"user-agent": UA_DESKTOP, "x-forwarded-for": "203.0.113.47"},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        linha = await _ultima_auditoria(uid)
        assert linha["user_agent"] == UA_DESKTOP
        assert linha["dispositivo"] == "desktop"
        assert linha["ip_address"] == "203.0.113.47"

    async def test_user_agent_de_celular_vira_mobile(self, client):
        uid = await _criar_usuario("ua.mobile120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Tecnico"},
            headers={"user-agent": UA_IPHONE},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        linha = await _ultima_auditoria(uid)
        assert linha["dispositivo"] == "mobile"
        assert linha["user_agent"] == UA_IPHONE

    async def test_primeiro_ip_do_x_forwarded_for(self, client):
        """Atras de proxy o header vem com a cadeia; vale o primeiro."""
        uid = await _criar_usuario("ua.xff120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Gestor"},
            headers={"user-agent": UA_DESKTOP, "x-forwarded-for": "198.51.100.9, 10.0.0.1, 172.16.0.5"},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        assert (await _ultima_auditoria(uid))["ip_address"] == "198.51.100.9"

    async def test_sem_user_agent_fica_nulo(self, client):
        """Sem o header, as duas colunas ficam null - e a alteracao nao falha."""
        uid = await _criar_usuario("ua.vazio120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Auxiliar"},
            headers={"user-agent": ""},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        linha = await _ultima_auditoria(uid)
        assert linha["user_agent"] is None
        assert linha["dispositivo"] is None

    async def test_user_agent_longo_nao_quebra_a_alteracao(self, client):
        """Por isso a coluna e Text: a auditoria nao pode derrubar a operacao."""
        uid = await _criar_usuario("ua.longo120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Diretor"},
            headers={"user-agent": "Mozilla/5.0 " + ("x" * 2000)},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        linha = await _ultima_auditoria(uid)
        assert len(linha["user_agent"]) > 1000, "o user-agent longo foi truncado"


class TestIssue120RotaDeLogs:
    """Item 3: os campos tem de sair na rota que a tela consome."""

    async def test_rota_de_auditoria_expoe_os_campos(self, client):
        uid = await _criar_usuario("ua.rota120@test.com")

        r = await client.patch(
            "/api/v1/usuarios/" + uid,
            json={"cargo": "Coordenador"},
            headers={"user-agent": UA_DESKTOP, "x-forwarded-for": "203.0.113.7"},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/auditoria/logs", params={"tabela_afetada": "usuarios"})
        assert r.status_code == status.HTTP_200_OK, r.text

        corpo = r.json()
        linhas = corpo["items"] if isinstance(corpo, dict) and "items" in corpo else corpo
        nossa = [x for x in linhas if x["registro_id"] == uid]
        assert nossa, "a alteracao nao apareceu na rota de logs"

        assert nossa[0]["user_agent"] == UA_DESKTOP
        assert nossa[0]["dispositivo"] == "desktop"
        assert nossa[0]["ip_address"] == "203.0.113.7"
