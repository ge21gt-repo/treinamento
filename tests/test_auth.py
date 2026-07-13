import uuid

from app.schemas.usuario import EsqueciSenhaRequest, LoginRequest, RedefinirSenhaRequest, Token, UsuarioCreate, UsuarioRegistro
from app.services.auth import create_access_token, decode_token


def test_usuario_create_schema_aceite_lgpd():
    payload = UsuarioCreate(
        nome_completo="Teste",
        email="teste@test.com",
        senha="123456",
        aceite_lgpd=True,
    )
    assert payload.aceite_lgpd is True


def test_usuario_create_schema_sem_aceite_lgpd():
    payload = UsuarioCreate(
        nome_completo="Teste",
        email="teste@test.com",
        senha="123456",
    )
    assert payload.aceite_lgpd is False


def test_usuario_registro_schema_aceite_lgpd():
    payload = UsuarioRegistro(
        nome_completo="Teste",
        email="teste@test.com",
        senha="123456",
        perfil_solicitado="participante",
        aceite_lgpd=True,
    )
    assert payload.aceite_lgpd is True


def test_login_request_schema():
    payload = LoginRequest(email="teste@test.com", senha="123456")
    assert payload.email == "teste@test.com"
    assert payload.senha == "123456"


def test_esqueci_senha_schema():
    payload = EsqueciSenhaRequest(email="teste@test.com")
    assert payload.email == "teste@test.com"


def test_redefinir_senha_schema():
    payload = RedefinirSenhaRequest(token="abc123", nova_senha="nova456")
    assert payload.token == "abc123"
    assert payload.nova_senha == "nova456"


def test_token_schema():
    token = Token(access_token="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0")
    assert token.access_token.startswith("eyJ")
    assert token.token_type == "bearer"


def test_jwt_token_create_and_decode():
    user_id = str(uuid.uuid4())
    token = create_access_token({"sub": user_id})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == user_id
