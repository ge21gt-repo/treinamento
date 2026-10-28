"""Issue #125: medir o uso dos tours de ajuda sem identificar a pessoa.

A decisao de produto da issue e guardar SO contagens - a linha nao tem
usuario_id, nem IP, nem user-agent. O teste
`test_a_tabela_nao_tem_coluna_de_pessoa` existe para isso nao voltar por
descuido: e o criterio de aceite "nenhuma linha da tabela tem usuario_id",
conferido no information_schema, que e mais forte que conferir uma linha.
"""

import os

from fastapi import status
from sqlalchemy import text

from app.api.deps import get_current_user
from app.main import app
from app.services.auth import create_access_token

_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
if _URL.startswith("postgres://"):
    _URL = _URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif _URL.startswith("postgresql://"):
    _URL = _URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_URL = _URL.split("?")[0]

_EVENTOS = "/api/v1/tours/eventos"
_RESUMO = "/api/v1/tours/resumo"


class _ComoUsuario:
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


async def _consultar(sql, parametros=None):
    from sqlalchemy.ext.asyncio import create_async_engine

    eng = create_async_engine(_URL)
    try:
        async with eng.begin() as conn:
            return (await conn.execute(text(sql), parametros or {})).all()
    finally:
        await eng.dispose()


async def _quantos_eventos(tour_id=None):
    if tour_id:
        linhas = await _consultar(
            "SELECT count(*) FROM lms.tour_eventos WHERE tour_id = :t", {"t": tour_id}
        )
    else:
        linhas = await _consultar("SELECT count(*) FROM lms.tour_eventos")
    return linhas[0][0]


def _ev(tour_id, evento, papel="instrutor", **extra):
    return {"tour_id": tour_id, "papel": papel, "evento": evento, **extra}


async def _enviar(client, eventos):
    return await client.post(_EVENTOS, json={"eventos": eventos})


async def _tour_do_resumo(client, tour_id, **params):
    r = await client.get(_RESUMO, params=params or None)
    assert r.status_code == status.HTTP_200_OK, r.text
    for t in r.json()["tours"]:
        if t["tour_id"] == tour_id:
            return t
    return None


class TestIssue125Privacidade:
    """A decisão de produto: contagens, sem ligar nada à pessoa."""

    async def test_a_tabela_nao_tem_coluna_de_pessoa(self, client):
        linhas = await _consultar(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'lms' AND table_name = 'tour_eventos' "
            "ORDER BY column_name"
        )
        colunas = [c[0] for c in linhas]
        assert colunas, "a tabela tour_eventos nao existe"
        for proibida in ("usuario_id", "ip_address", "user_agent", "dispositivo"):
            assert proibida not in colunas, (proibida, colunas)
        assert colunas == ["criado_em", "evento", "id", "papel", "passo", "tour_id", "util"]

    async def test_a_rota_de_eventos_fica_fora_do_log_acesso(self, client, admin_token):
        """O middleware grava log_acesso em todo POST autenticado - com
        usuario_id, IP e user-agent. O front manda lote de poucos em poucos
        segundos, por aba aberta: seria uma linha por lote, ligando a pessoa ao
        uso dos tours pelo horario, que e o oposto do que a issue decidiu. A
        rota ficou fora dessa gravacao.

        Chama `_registrar_acesso_escrita` direto, com await, em vez de medir
        pelo efeito de um POST. A gravacao real roda em task de fundo
        (`_disparar_log_acesso` -> create_task), entao contar linhas logo
        depois da resposta e uma corrida que o teste sempre ganha: a primeira
        versao deste teste passava mesmo com a excecao removida.
        """
        from app.main import _registrar_acesso_escrita

        cabecalho = f"Bearer {admin_token}"
        antes = (await _consultar("SELECT count(*) FROM lms.log_acesso"))[0][0]

        await _registrar_acesso_escrita("POST", _EVENTOS, cabecalho)
        assert (await _consultar("SELECT count(*) FROM lms.log_acesso"))[0][0] == antes

        # A outra direcao, para provar que a excecao e desta rota e nao um
        # middleware que parou de gravar: uma rota qualquer continua gravando.
        await _registrar_acesso_escrita("POST", "/api/v1/cursos", cabecalho)
        depois = (await _consultar("SELECT count(*) FROM lms.log_acesso"))[0][0]
        assert depois == antes + 1

        caminhos = await _consultar(
            "SELECT recurso_tipo FROM lms.log_acesso ORDER BY id DESC LIMIT 1"
        )
        assert caminhos[0][0] == "/api/v1/cursos"


class TestIssue125CriterioDeAceite:
    async def test_lote_valido_aparece_no_resumo(self, client):
        """O critério literal da issue: 1 iniciado, 2 passo_visto, 1 concluído."""
        r = await _enviar(
            client,
            [
                _ev("avaliacao-criar", "tour_iniciado"),
                _ev("avaliacao-criar", "passo_visto", passo=1),
                _ev("avaliacao-criar", "passo_visto", passo=2),
                _ev("avaliacao-criar", "tour_concluido"),
            ],
        )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

        tour = await _tour_do_resumo(client, "avaliacao-criar")
        assert tour is not None, "o tour nao apareceu no resumo"
        assert tour["iniciados"] == 1
        assert tour["concluidos"] == 1

    async def test_evento_invalido_nao_grava_o_lote(self, client):
        """422 e nada gravado - nem os eventos válidos que vinham no lote."""
        r = await _enviar(
            client,
            [
                _ev("menu", "tour_iniciado"),
                _ev("menu", "evento_que_nao_existe"),
                _ev("menu", "tour_concluido"),
            ],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _quantos_eventos("menu") == 0

    async def test_participante_recebe_403_no_resumo(self, client, participante_user):
        with _ComoUsuario(participante_user):
            r = await client.get(_RESUMO)
        assert r.status_code == status.HTTP_403_FORBIDDEN, r.text

    async def test_participante_pode_enviar_evento(self, client, participante_user):
        """O POST exige só login: quem gera o evento é qualquer pessoa."""
        with _ComoUsuario(participante_user):
            r = await _enviar(client, [_ev("menu-participante", "convite_exibido", papel="participante")])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        assert await _quantos_eventos("menu-participante") == 1


class TestIssue125Validacao:
    async def test_lote_de_51_recusado(self, client):
        eventos = [_ev("menu", "convite_exibido") for _ in range(51)]
        r = await _enviar(client, eventos)
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await _quantos_eventos("menu") == 0

    async def test_lote_de_50_aceito(self, client):
        """O limite é 50, não 49."""
        eventos = [_ev("menu-50", "convite_exibido") for _ in range(50)]
        r = await _enviar(client, eventos)
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        assert await _quantos_eventos("menu-50") == 50

    async def test_lote_vazio_passa_sem_gravar(self, client):
        """O front esvazia a fila ao sair da página; fila vazia não é erro."""
        antes = await _quantos_eventos()
        r = await _enviar(client, [])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        assert await _quantos_eventos() == antes

    async def test_papel_desconhecido_recusado(self, client):
        r = await _enviar(client, [_ev("menu", "tour_iniciado", papel="sindico")])
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

    async def test_tour_id_fora_do_padrao_recusado(self, client):
        for ruim in ("Menu", "menu_principal", "menu com espaco", "", "m" * 65):
            r = await _enviar(client, [{"tour_id": ruim, "papel": "instrutor", "evento": "tour_iniciado"}])
            assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, (ruim, r.text)

    async def test_passo_so_nos_eventos_que_o_aceitam(self, client):
        r = await _enviar(client, [_ev("menu", "tour_iniciado", passo=2)])
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

        r = await _enviar(client, [_ev("menu-passo", "tour_fechado", passo=2)])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

    async def test_util_so_em_tour_util(self, client):
        r = await _enviar(client, [_ev("menu", "tour_concluido", util=True)])
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text

        r = await _enviar(client, [_ev("menu-util", "tour_util", util=True)])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

    async def test_campo_fora_do_schema_recusado(self, client):
        r = await _enviar(
            client,
            [{"tour_id": "menu", "papel": "instrutor", "evento": "tour_iniciado", "usuario_id": "x"}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text


class TestIssue125Resumo:
    async def test_fechados_por_passo_e_util(self, client):
        r = await _enviar(
            client,
            [
                _ev("correcao", "tour_fechado", passo=2),
                _ev("correcao", "tour_fechado", passo=2),
                _ev("correcao", "tour_fechado", passo=5),
                _ev("correcao", "tour_util", util=True),
                _ev("correcao", "tour_util", util=True),
                _ev("correcao", "tour_util", util=False),
            ],
        )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

        tour = await _tour_do_resumo(client, "correcao")
        assert tour["fechados_por_passo"] == {"2": 2, "5": 1}
        assert tour["util_sim"] == 2
        assert tour["util_nao"] == 1

    async def test_o_mesmo_total_por_papel(self, client):
        r = await _enviar(
            client,
            [
                _ev("menu-papeis", "tour_iniciado", papel="instrutor"),
                _ev("menu-papeis", "tour_iniciado", papel="gestor"),
                _ev("menu-papeis", "tour_concluido", papel="gestor"),
            ],
        )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

        tour = await _tour_do_resumo(client, "menu-papeis")
        assert tour["iniciados"] == 2
        assert tour["por_papel"]["instrutor"]["iniciados"] == 1
        assert tour["por_papel"]["gestor"]["iniciados"] == 1
        assert tour["por_papel"]["gestor"]["concluidos"] == 1
        assert tour["por_papel"]["instrutor"]["concluidos"] == 0

    async def test_resumo_por_periodo(self, client):
        r = await _enviar(client, [_ev("periodo", "tour_iniciado")])
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

        # Janela antiga: o evento de hoje nao entra.
        assert await _tour_do_resumo(client, "periodo", de="2020-01-01", ate="2020-01-31") is None

        # `ate` igual a hoje tem de incluir o dia inteiro, e nao parar na
        # meia-noite - que era o erro facil aqui.
        hoje = (await _consultar("SELECT current_date"))[0][0].isoformat()
        tour = await _tour_do_resumo(client, "periodo", de=hoje, ate=hoje)
        assert tour is not None, "o evento de hoje ficou fora da janela de hoje"
        assert tour["iniciados"] == 1

    async def test_resumo_vazio_quando_nao_ha_evento(self, client):
        r = await client.get(_RESUMO)
        assert r.status_code == status.HTTP_200_OK, r.text
        assert r.json()["tours"] == []


class TestIssue125LimiteDeTaxa:
    async def test_limite_por_token_e_nao_por_ip(self, client, admin_user):
        """60 por minuto, contados por token.

        Usa um token proprio para nao gastar o balde dos outros testes deste
        arquivo, e e justamente isso que mostra que a chave e o token: o
        cliente, o IP e o usuario sao os mesmos, so o token muda.
        """
        token = create_access_token(data={"sub": str(admin_user.id), "email": admin_user.email})
        cabecalho = {"Authorization": f"Bearer {token}"}
        corpo = {"eventos": [_ev("limite", "convite_exibido")]}

        for i in range(60):
            r = await client.post(_EVENTOS, json=corpo, headers=cabecalho)
            assert r.status_code == status.HTTP_204_NO_CONTENT, (i, r.text)

        r = await client.post(_EVENTOS, json=corpo, headers=cabecalho)
        assert r.status_code == status.HTTP_429_TOO_MANY_REQUESTS, r.text
