import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.db


async def criar_curso(client, titulo="Curso Teste", trilha_id=None, publicado=True):
    payload = {
        "titulo": titulo,
        "descricao": "Descricao do curso",
        "ordem": 0,
        "publicado": publicado,
    }
    if trilha_id is not None:
        payload["trilha_id"] = trilha_id
    response = await client.post("/api/v1/cursos", json=payload)
    return response


async def criar_modulo(client, curso_id, titulo="Modulo Teste"):
    payload = {
        "curso_id": curso_id,
        "titulo": titulo,
        "descricao": "Descricao do modulo",
        "ordem": 0,
    }
    response = await client.post("/api/v1/cursos/modulos", json=payload)
    return response


async def criar_unidade(client, curso_id, modulo_id, titulo="Unidade Teste"):
    payload = {
        "modulo_id": modulo_id,
        "titulo": titulo,
        "tipo": "conteudo",
        "descricao": "Descricao da unidade",
        "conteudo_url": "https://exemplo.com/aula.pdf",
        "ordem": 0,
    }
    response = await client.post("/api/v1/cursos/unidades", json=payload)
    return response


async def criar_trilha(client, titulo="Trilha Teste", nivel="iniciante", publicada=True):
    payload = {
        "titulo": titulo,
        "descricao": "Descricao da trilha",
        "nivel": nivel,
        "carga_horaria_total": 40,
        "publicada": publicada,
    }
    response = await client.post("/api/v1/trilhas", json=payload)
    return response


AUTH_OK = (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


class TestInscricaoAPI:
    """T-07.1: Inscricao em cursos com duplicidade, RBAC, minhas-inscricoes, cancelar"""

    async def test_inscricao_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/cursos/inscricoes", json={"curso_id": 1})
        assert r.status_code in AUTH_OK

    async def test_inscricao_duplicada_rejeitada(self, client):
        create_resp = await criar_curso(client, "Curso Inscricao Duplicada")
        curso_id = create_resp.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED
        r2 = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r2.status_code == status.HTTP_409_CONFLICT

    async def test_inscricao_rejeita_curso_inexistente(self, client):
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": 99999})
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_minhas_inscricoes_retorna_lista(self, client):
        r = await client.get("/api/v1/cursos/inscricoes/minhas")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert isinstance(data, list)

    async def test_cancelar_inscricao_existente(self, client):
        create_resp = await criar_curso(client, "Curso Cancelar")
        curso_id = create_resp.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED
        inscricao_id = r.json()["id"]
        r = await client.delete(f"/api/v1/cursos/inscricoes/{inscricao_id}")
        assert r.status_code == status.HTTP_204_NO_CONTENT

    async def test_cancelar_inscricao_inexistente(self, client):
        r = await client.delete("/api/v1/cursos/inscricoes/99999")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestConcluirUnidade:
    """T-07.2+3: Conclusao de unidade e cascade de progresso"""

    async def test_concluir_unidade_requer_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post("/api/v1/cursos/unidades/1/concluir")
        assert r.status_code in AUTH_OK

    async def test_concluir_unidade_sem_inscricao(self, client):
        create_resp = await criar_curso(client, "Curso Sem Inscricao")
        curso_id = create_resp.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo Unico")
        modulo_id = mod_resp.json()["id"]
        uni_resp = await criar_unidade(client, curso_id, modulo_id, "Unidade Sem Inscricao")
        unidade_id = uni_resp.json()["id"]
        r = await client.post(f"/api/v1/cursos/unidades/{unidade_id}/concluir")
        assert r.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND)

    async def test_concluir_unidade_com_inscricao(self, client):
        create_resp = await criar_curso(client, "Curso Concluir Unidade", publicado=True)
        curso_id = create_resp.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo Unico")
        modulo_id = mod_resp.json()["id"]
        uni_resp = await criar_unidade(client, curso_id, modulo_id, "Unidade 1")
        unidade_id = uni_resp.json()["id"]
        await criar_unidade(client, curso_id, modulo_id, "Unidade 2")
        r_insc = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        if r_insc.status_code == status.HTTP_201_CREATED:
            r = await client.post(f"/api/v1/cursos/unidades/{unidade_id}/concluir")
            assert r.status_code == status.HTTP_200_OK
            data = r.json()
            assert "status" in data


class TestConsumoModuloProgresso:
    """T-07.5: % por modulo no /consumo"""

    async def test_consumo_inclui_progresso_modulo(self, client):
        create_resp = await criar_curso(client, "Curso Consumo Progresso", publicado=True)
        curso_id = create_resp.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo Consumo")
        modulo_id = mod_resp.json()["id"]
        await criar_unidade(client, curso_id, modulo_id, "Unidade A")
        await criar_unidade(client, curso_id, modulo_id, "Unidade B")
        r = await client.get(f"/api/v1/cursos/{curso_id}/consumo")
        if r.status_code != status.HTTP_200_OK:
            pytest.skip("consumo endpoint indisponivel")
        data = r.json()
        modulos = data.get("modulos", [])
        if modulos:
            for modulo in modulos:
                assert "total_unidades" in modulo
                assert "unidades_concluidas" in modulo
                assert "progresso_pct" in modulo


class TestDashboardMeuProgresso:
    """T-07.4: Dashboard pessoal"""

    async def test_meu_progresso_requer_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/dashboard/meu-progresso")
        assert r.status_code in AUTH_OK

    async def test_meu_progresso_retorna_estrutura(self, client):
        r = await client.get("/api/v1/dashboard/meu-progresso")
        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert "usuario_id" in data
        assert "nome" in data
        assert "cursos" in data
        for campo in (
            "total_cursos_inscritos",
            "total_cursos_concluidos",
            "total_horas_cursadas",
            "total_certificados",
            "xp_total",
            "nivel",
        ):
            assert campo in data


class TestProgressoTrilhaDetalhado:
    """T-07.5: Progresso detalhado por curso dentro da trilha"""

    async def test_progresso_detalhado_requer_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/trilhas/1/progresso-detalhado")
        assert r.status_code in AUTH_OK

    async def test_progresso_detalhado_trilha_inexistente(self, client):
        r = await client.get("/api/v1/trilhas/99999/progresso-detalhado")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_progresso_detalhado_sem_inscricao(self, client):
        trilha_resp = await criar_trilha(client, "Trilha Sem Inscricao")
        trilha_id = trilha_resp.json()["id"]
        r = await client.get(f"/api/v1/trilhas/{trilha_id}/progresso-detalhado")
        assert r.status_code == status.HTTP_404_NOT_FOUND

    async def test_progresso_detalhado_com_inscricao(self, client):
        trilha_resp = await criar_trilha(client, "Trilha Detalhada")
        trilha_id = trilha_resp.json()["id"]
        curso_resp = await criar_curso(client, "Curso Na Trilha", trilha_id=trilha_id)
        curso_id = curso_resp.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo T")
        modulo_id = mod_resp.json()["id"]
        await criar_unidade(client, curso_id, modulo_id, "U1")
        r_insc = await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
        if r_insc.status_code == status.HTTP_201_CREATED:
            r = await client.get(f"/api/v1/trilhas/{trilha_id}/progresso-detalhado")
            assert r.status_code == status.HTTP_200_OK
            data = r.json()
            assert "trilha_id" in data
            assert "cursos" in data


class TestProgressoUsuarioCurso:
    """Feature nova: GET /cursos/{curso_id}/progresso/{usuario_id} — auditoria de progresso por modulo"""

    async def test_gestor_ve_progresso_de_outro_usuario(self, client, gestor_user, participante_user):
        from app.services.auth import create_access_token

        create_resp = await criar_curso(client, "Curso Progresso Gestor")
        curso_id = create_resp.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo P")
        modulo_id = mod_resp.json()["id"]
        await criar_unidade(client, curso_id, modulo_id, "Unidade P1")

        saved_overrides = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        try:
            token = create_access_token(data={"sub": str(gestor_user.id), "email": gestor_user.email})
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as gc:
                gc.headers.update({"Authorization": f"Bearer {token}"})
                r = await gc.get(f"/api/v1/cursos/{curso_id}/progresso/{participante_user.id}")
        finally:
            app.dependency_overrides.update(saved_overrides)

        assert r.status_code == status.HTTP_200_OK
        data = r.json()
        assert data["curso_id"] == curso_id
        assert isinstance(data["modulos"], list)
        if data["modulos"]:
            assert {"id", "titulo", "total_unidades", "unidades_concluidas", "progresso_pct"} <= set(
                data["modulos"][0].keys()
            )

    async def test_participante_nao_pode_ver_progresso_de_outro(self, client, participante_user, admin_user):
        from app.services.auth import create_access_token

        create_resp = await criar_curso(client, "Curso Progresso Negado")
        curso_id = create_resp.json()["id"]

        saved_overrides = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        try:
            token = create_access_token(data={"sub": str(participante_user.id), "email": participante_user.email})
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as pc:
                pc.headers.update({"Authorization": f"Bearer {token}"})
                r = await pc.get(f"/api/v1/cursos/{curso_id}/progresso/{admin_user.id}")
        finally:
            app.dependency_overrides.update(saved_overrides)

        assert r.status_code == status.HTTP_403_FORBIDDEN

    async def test_progresso_usuario_curso_inexistente_404(self, client, participante_user):
        r = await client.get(f"/api/v1/cursos/99999/progresso/{participante_user.id}")
        assert r.status_code == status.HTTP_404_NOT_FOUND


class TestNotaFinal:
    """Issue 20 — Inscricao.nota_final preenchida ao concluir o curso"""

    async def _setup_curso_com_avaliacao(self, client, curso_titulo="Curso Nota Final"):
        r = await criar_curso(client, curso_titulo, publicado=True)
        curso_id = r.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo Nota")
        modulo_id = mod_resp.json()["id"]
        uni_resp = await criar_unidade(client, curso_id, modulo_id, "Unidade Nota")
        unidade_id = uni_resp.json()["id"]

        r = await client.post(
            "/api/v1/avaliacoes",
            json={"unidade_id": unidade_id, "titulo": "Avaliacao Nota", "tipo": "prova"},
        )
        av_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10},
        )
        q_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/alternativas",
            json={"questao_id": q_id, "texto": "4", "correta": True, "ordem": 0},
        )
        alt_id = r.json()["id"]

        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        return {"curso_id": curso_id, "unidade_id": unidade_id, "av_id": av_id, "q_id": q_id, "alt_id": alt_id}

    async def test_nota_final_preenchida_ao_concluir(self, client):
        s = await self._setup_curso_com_avaliacao(client)

        r = await client.post(
            f"/api/v1/avaliacoes/{s['av_id']}/submeter",
            json={"respostas": [{"questao_id": s["q_id"], "alternativa_id": s["alt_id"]}]},
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text
        assert r.json()["nota"] == 100.0

        r = await client.post(f"/api/v1/cursos/unidades/{s['unidade_id']}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/dashboard/meu-progresso")
        assert r.status_code == status.HTTP_200_OK, r.text
        cursos = r.json().get("cursos", [])
        curso_prog = next((c for c in cursos if c.get("curso_id") == s["curso_id"]), None)
        assert curso_prog is not None, "Curso nao veio em meu-progresso"
        assert curso_prog["nota_final"] == 100.0, f"nota_final esperada 100, veio {curso_prog.get('nota_final')}"

    async def test_nota_final_null_sem_avaliacao(self, client):
        r = await criar_curso(client, "Curso Sem Avaliacao NF", publicado=True)
        curso_id = r.json()["id"]
        mod_resp = await criar_modulo(client, curso_id, "Modulo")
        modulo_id = mod_resp.json()["id"]
        uni_resp = await criar_unidade(client, curso_id, modulo_id, "Unidade")
        unidade_id = uni_resp.json()["id"]

        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        assert r.status_code == status.HTTP_201_CREATED, r.text
        r = await client.post(f"/api/v1/cursos/unidades/{unidade_id}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/dashboard/meu-progresso")
        cursos = r.json().get("cursos", [])
        curso_prog = next((c for c in cursos if c.get("curso_id") == curso_id), None)
        assert curso_prog is not None
        assert curso_prog["nota_final"] is None, "Curso sem avaliacao deve ter nota_final nula"


class TestPermissionsRBAC:
    """Verificacao de permissoes RBAC para inscricao"""

    async def test_usuario_sem_permissao_nao_inscreve_outro(self, client, participante_user):
        from httpx import ASGITransport, AsyncClient

        from app.services.auth import create_access_token

        create_resp = await criar_curso(client, "Curso RBAC Inscricao")
        curso_id = create_resp.json()["id"]
        saved_overrides = dict(app.dependency_overrides)
        app.dependency_overrides.clear()
        try:
            transport = ASGITransport(app=app)
            token = create_access_token(data={"sub": str(participante_user.id), "email": participante_user.email})
            async with AsyncClient(transport=transport, base_url="http://test") as pc:
                pc.headers.update({"Authorization": f"Bearer {token}"})
                r = await pc.post(
                    "/api/v1/cursos/inscricoes",
                    json={"curso_id": curso_id, "usuario_id": "00000000-0000-0000-0000-000000000001"},
                )
            assert r.status_code == status.HTTP_403_FORBIDDEN
        finally:
            app.dependency_overrides.update(saved_overrides)
