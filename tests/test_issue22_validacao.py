"""Testes para Issue #22: validacao de campos unicos e mensagens de erro"""

from httpx import ASGITransport, AsyncClient

from app.main import app


class TestValidacaoCamposUnicos:
    """Registro deve validar email, CPF e telefone duplicados com 409"""

    async def test_registro_cpf_duplicado_rejeitado(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "CPF 1",
                    "email": "cpf1@test.com",
                    "cpf": "111.111.111-11",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "CPF 2",
                    "email": "cpf2@test.com",
                    "cpf": "111.111.111-11",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "CPF ja cadastrado"

    async def test_registro_telefone_duplicado_rejeitado(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel 1",
                    "email": "tel1@test.com",
                    "telefone": "11999999999",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Tel 2",
                    "email": "tel2@test.com",
                    "telefone": "11999999999",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Telefone ja cadastrado"

    async def test_registro_email_duplicado_retorna_409(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Duplicado",
                    "email": "dup@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Duplicado 2",
                    "email": "dup@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Email ja cadastrado"

    async def test_registro_com_perfil_email_duplicado_retorna_409(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "User",
                    "email": "user@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro-com-perfil",
                json={
                    "nome_completo": "User Solic",
                    "email": "user@test.com",
                    "senha": "123456",
                    "perfil_solicitado": "instrutor",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Email ja cadastrado"

    async def test_registro_com_perfil_cpf_duplicado_rejeitado(self, db_clean):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Orig",
                    "email": "orig@test.com",
                    "cpf": "222.222.222-22",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/auth/registro-com-perfil",
                json={
                    "nome_completo": "Solic",
                    "email": "solic@test.com",
                    "cpf": "222.222.222-22",
                    "senha": "123456",
                    "perfil_solicitado": "instrutor",
                    "aceite_lgpd": True,
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "CPF ja cadastrado"


class TestValidacaoSubordinado:
    """Criar subordinado deve validar campos unicos"""

    async def test_criar_subordinado_email_duplicado_retorna_409(self, db_clean, admin_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r1 = await ac.post(
                "/api/v1/auth/registro",
                json={
                    "nome_completo": "Existente",
                    "email": "existente@test.com",
                    "senha": "123456",
                    "aceite_lgpd": True,
                },
            )
            assert r1.status_code == 201

            r2 = await ac.post(
                "/api/v1/usuarios/criar-subordinado",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={
                    "nome_completo": "Sub",
                    "email": "existente@test.com",
                    "senha": "123456",
                },
            )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "Email ja cadastrado"
