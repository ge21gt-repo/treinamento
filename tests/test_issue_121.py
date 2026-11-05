"""Issue #121: desligar o acesso local quando o Keycloak for a unica porta.

O que a issue pede (item 1) e uma flag, `LOGIN_LOCAL_HABILITADO`, com padrao
VERDADEIRO. Com ela falsa, quatro rotas deixam de existir para o cliente:

    POST /auth/registro
    POST /auth/login
    POST /auth/esqueci-senha
    POST /auth/redefinir-senha

e `POST /auth/logout` continua funcionando.

O teste que mais importa aqui e o de nao-regressao: com o padrao de fabrica,
NADA muda. Por isso cada rota e exercitada nos dois estados, e a asercao do
estado ligado nao e "200", e sim "o codigo de erro proprio da rota" - 401 para
credencial errada, 400 para token invalido. Se a trava disparasse no estado
errado, esses numeros virariam 404 e o teste cai.

Os itens 2 e 3 da issue nao sao codigo: o 2 e o plano de migracao das contas
que so tem senha local (a infra recria no Keycloak, e o vinculo por e-mail do
`deps.py` ja cobre o primeiro login), e o 3 a propria issue manda para uma
issue separada.
"""

import pytest
from fastapi import status

from app.config import settings

_REGISTRO = "/api/v1/auth/registro"
_LOGIN = "/api/v1/auth/login"
_ESQUECI = "/api/v1/auth/esqueci-senha"
_REDEFINIR = "/api/v1/auth/redefinir-senha"
_LOGOUT = "/api/v1/auth/logout"
_ME = "/api/v1/usuarios/me"

# Corpos validos no formato, para que a recusa venha da trava e nao do Pydantic:
# um 422 de schema nao provaria nada sobre a flag.
_CORPO_REGISTRO = {
    "email": "ninguem-121@test.com",
    "senha": "SenhaForte123!",
    "nome_completo": "Ninguem da Issue 121",
    "perfil_solicitado": "participante",
    "aceite_lgpd": True,
}
_CORPO_LOGIN = {"email": "ninguem-121@test.com", "senha": "SenhaErrada123!"}
_CORPO_ESQUECI = {"email": "ninguem-121@test.com"}
_CORPO_REDEFINIR = {"token": "token-que-nao-existe", "nova_senha": "OutraSenha123!"}


class TestIssue121PadraoDeFabrica:
    """Com a flag no padrao, a issue nao pode ter mudado nada."""

    async def test_a_flag_nasce_ligada(self):
        # Se alguem trocar o padrao, o corte acontece sozinho no proximo deploy
        # e tira o acesso de quem ainda nao tem conta no Keycloak. O padrao e
        # parte do critério de aceite, por isso vale um teste proprio.
        assert settings.LOGIN_LOCAL_HABILITADO is True

    async def test_login_continua_respondendo_a_propria_rota(self, client):
        r = await client.post(_LOGIN, json=_CORPO_LOGIN)
        # 401 = a rota rodou e recusou a credencial. 404 seria a trava disparando.
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, r.text

    async def test_registro_continua_respondendo_a_propria_rota(self, client):
        r = await client.post(_REGISTRO, json={**_CORPO_REGISTRO, "perfil_solicitado": "invalido"})
        # 400 = a rota rodou e recusou o perfil.
        assert r.status_code == status.HTTP_400_BAD_REQUEST, r.text

    async def test_esqueci_senha_continua_respondendo_a_propria_rota(self, client):
        r = await client.post(_ESQUECI, json=_CORPO_ESQUECI)
        # A rota devolve a mensagem genérica mesmo para e-mail inexistente.
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_redefinir_senha_continua_respondendo_a_propria_rota(self, client):
        r = await client.post(_REDEFINIR, json=_CORPO_REDEFINIR)
        # 400 = a rota rodou e recusou o token.
        assert r.status_code == status.HTTP_400_BAD_REQUEST, r.text


class TestIssue121ComOCorteLigado:
    """Com a flag falsa, as quatro somem e o resto fica."""

    @pytest.fixture(autouse=True)
    def _desligar(self, monkeypatch):
        monkeypatch.setattr(settings, "LOGIN_LOCAL_HABILITADO", False)

    @pytest.mark.parametrize(
        "rota,corpo",
        [
            (_REGISTRO, _CORPO_REGISTRO),
            (_LOGIN, _CORPO_LOGIN),
            (_ESQUECI, _CORPO_ESQUECI),
            (_REDEFINIR, _CORPO_REDEFINIR),
        ],
    )
    async def test_as_quatro_rotas_nao_existem_mais(self, client, rota, corpo):
        r = await client.post(rota, json=corpo)
        assert r.status_code == status.HTTP_404_NOT_FOUND, (rota, r.text)
        # Mesmo corpo que o FastAPI da para um caminho inexistente: quem sonda a
        # API nao descobre que havia uma rota ali, desligada.
        assert r.json() == {"detail": "Not Found"}, (rota, r.text)

    async def test_logout_continua_de_pe(self, client):
        # A issue pede isto por escrito: a sessao do Keycloak precisa de um
        # lugar para terminar.
        r = await client.post(_LOGOUT)
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_o_resto_da_api_nao_e_afetado(self, client):
        # A flag tranca o acesso local, nao a plataforma. Este cliente entra
        # pelo override de get_current_user, que e o caminho do Keycloak.
        r = await client.get(_ME)
        assert r.status_code == status.HTTP_200_OK, r.text

    async def test_a_recusa_vem_antes_do_rate_limit(self, client):
        # /auth/esqueci-senha tem teto de 3/minuto. Se a trava estivesse DENTRO
        # do corpo da rota, o limitador correria primeiro e a quarta chamada
        # viraria 429 - e, pior, a rota desligada consumiria cota de quem usa a
        # API. Cinco chamadas, todas 404, provam que a recusa vem antes.
        for i in range(5):
            r = await client.post(_ESQUECI, json=_CORPO_ESQUECI)
            assert r.status_code == status.HTTP_404_NOT_FOUND, (i, r.status_code, r.text)
