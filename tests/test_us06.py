"""Testes reais US-06 — upload, conteudo, entrega, SCORM via API"""

import io


async def criar_curso(client, titulo="Curso Conteudo"):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
    return r.json()["id"]


async def criar_modulo(client, curso_id):
    r = await client.post(
        "/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "descricao": "x", "ordem": 0}
    )
    return r.json()["id"]


async def criar_unidade(client, modulo_id):
    r = await client.post(
        "/api/v1/cursos/unidades",
        json={
            "modulo_id": modulo_id,
            "titulo": "U",
            "tipo": "conteudo",
            "descricao": "x",
            "conteudo_url": "https://exemplo.com/aula.pdf",
            "ordem": 0,
        },
    )
    return r.json()["id"]


class TestConteudoUpload:
    async def test_upload_pdf(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            f"/api/v1/conteudos/upload?unidade_id={uni_id}&tipo_midia=pdf&titulo=Material+PDF",
            files={"arquivo": ("test.pdf", io.BytesIO(b"%PDF-1.4 fake pdf"), "application/pdf")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["tipo_midia"] == "pdf"
        assert "url_arquivo" in data

    async def test_upload_video(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            f"/api/v1/conteudos/upload?unidade_id={uni_id}&tipo_midia=video&titulo=Video+Aula",
            files={"arquivo": ("aula.mp4", io.BytesIO(b"fake mp4 content"), "video/mp4")},
        )
        assert r.status_code == 201
        assert r.json()["tipo_midia"] == "video"

    async def test_upload_mime_invalido_rejeitado(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            f"/api/v1/conteudos/upload?unidade_id={uni_id}&tipo_midia=video&titulo=Invalido",
            files={"arquivo": ("malware.exe", io.BytesIO(b"evil"), "application/x-msdownload")},
        )
        assert r.status_code == 422


class TestConteudoCRUD:
    async def test_criar_conteudo_sem_arquivo(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uni_id,
                "tipo_midia": "link",
                "titulo": "Link Externo",
                "url_arquivo": "https://youtube.com/watch?v=123",
            },
        )
        assert r.status_code == 201
        assert r.json()["titulo"] == "Link Externo"

    async def test_listar_conteudos_por_unidade(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uni_id,
                "tipo_midia": "link",
                "titulo": "Link 1",
                "url_arquivo": "https://example.com/1",
            },
        )
        r = await client.get(f"/api/v1/conteudos?unidade_id={uni_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    async def test_obter_conteudo_por_id(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uni_id,
                "tipo_midia": "link",
                "titulo": "Link Unico",
                "url_arquivo": "https://example.com/unique",
            },
        )
        cid = r.json()["id"]
        r = await client.get(f"/api/v1/conteudos/{cid}")
        assert r.status_code == 200
        assert r.json()["id"] == cid

    async def test_atualizar_conteudo(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uni_id,
                "tipo_midia": "link",
                "titulo": "Original",
                "url_arquivo": "https://example.com/1",
            },
        )
        cid = r.json()["id"]
        r = await client.patch(f"/api/v1/conteudos/{cid}", json={"titulo": "Atualizado"})
        assert r.status_code == 200
        assert r.json()["titulo"] == "Atualizado"

    async def test_deletar_conteudo(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uni_id,
                "tipo_midia": "link",
                "titulo": "Deletar",
                "url_arquivo": "https://example.com/del",
            },
        )
        cid = r.json()["id"]
        r = await client.delete(f"/api/v1/conteudos/{cid}")
        assert r.status_code == 204

    async def test_deletar_conteudo_inexistente(self, client):
        r = await client.delete("/api/v1/conteudos/99999")
        assert r.status_code == 404


class TestMateriais:
    async def test_upload_material(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            f"/api/v1/conteudos/materiais/upload?curso_id={curso_id}&titulo=Apoio&tipo=pdf",
            files={"arquivo": ("apoio.pdf", io.BytesIO(b"fake pdf"), "application/pdf")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["titulo"] == "Apoio"
        assert "url_arquivo" in data

    async def test_listar_materiais_por_curso(self, client):
        curso_id = await criar_curso(client)
        await client.post(
            f"/api/v1/conteudos/materiais/upload?curso_id={curso_id}&titulo=Material1&tipo=pdf",
            files={"arquivo": ("m1.pdf", io.BytesIO(b"pdf1"), "application/pdf")},
        )
        r = await client.get(f"/api/v1/conteudos/materiais/{curso_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    async def test_criar_material_sem_arquivo(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            "/api/v1/conteudos/materiais",
            json={
                "curso_id": curso_id,
                "titulo": "Link Externo",
                "tipo": "link",
                "url_arquivo": "https://example.com",
            },
        )
        assert r.status_code == 201

    async def test_atualizar_material(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            "/api/v1/conteudos/materiais",
            json={
                "curso_id": curso_id,
                "titulo": "Original",
                "tipo": "link",
                "url_arquivo": "https://example.com/1",
            },
        )
        mid = r.json()["id"]
        r = await client.patch(f"/api/v1/conteudos/materiais/{mid}", json={"titulo": "Atualizado"})
        assert r.status_code == 200
        assert r.json()["titulo"] == "Atualizado"

    async def test_deletar_material(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            "/api/v1/conteudos/materiais",
            json={
                "curso_id": curso_id,
                "titulo": "Deletar",
                "tipo": "link",
                "url_arquivo": "https://example.com/del",
            },
        )
        mid = r.json()["id"]
        r = await client.delete(f"/api/v1/conteudos/materiais/{mid}")
        assert r.status_code == 204


class TestEntregas:
    async def test_entrega_upload(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            f"/api/v1/entregas/upload?unidade_id={uni_id}&titulo=Exercicio&descricao=Resolucao",
            files={"arquivo": ("ex.pdf", io.BytesIO(b"fake entrega"), "application/pdf")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["titulo"] == "Exercicio"
        assert data["status"] == "pendente"

    async def test_listar_minhas_entregas(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        await client.post(
            f"/api/v1/entregas/upload?unidade_id={uni_id}&titulo=Entrega&descricao=x",
            files={"arquivo": ("ex.pdf", io.BytesIO(b"data"), "application/pdf")},
        )
        r = await client.get("/api/v1/entregas/minhas")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    async def test_entrega_corrigir(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        r = await client.post(
            f"/api/v1/entregas/upload?unidade_id={uni_id}&titulo=Corrigir&descricao=x",
            files={"arquivo": ("ex.pdf", io.BytesIO(b"data"), "application/pdf")},
        )
        eid = r.json()["id"]
        r = await client.patch(f"/api/v1/entregas/{eid}/corrigir", json={"nota": 9.5, "feedback": "Excelente"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "corrigido"
        assert data["nota"] == 9.5

    async def test_listar_entregas_por_unidade(self, client):
        curso_id = await criar_curso(client)
        mod_id = await criar_modulo(client, curso_id)
        uni_id = await criar_unidade(client, mod_id)
        await client.post(
            f"/api/v1/entregas/upload?unidade_id={uni_id}&titulo=EntregaU&descricao=x",
            files={"arquivo": ("ex.pdf", io.BytesIO(b"data"), "application/pdf")},
        )
        r = await client.get(f"/api/v1/entregas/unidade/{uni_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestSCORM:
    async def test_upload_scorm_zip(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            f"/api/v1/scorm/upload?curso_id={curso_id}&titulo=Pacote+SCORM",
            files={"arquivo": ("curso.zip", io.BytesIO(b"PK fake zip content"), "application/zip")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["titulo"] == "Pacote SCORM"
        assert "id" in data

    async def test_launch_scorm_requer_pacote_existente(self, client):
        r = await client.get("/api/v1/scorm/99999/launch")
        assert r.status_code == 404

    async def test_tracking_scorm(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            f"/api/v1/scorm/upload?curso_id={curso_id}&titulo=SCORM+Tracking",
            files={"arquivo": ("track.zip", io.BytesIO(b"PK zip"), "application/zip")},
        )
        pid = r.json()["id"]
        r = await client.post(
            f"/api/v1/scorm/{pid}/tracking",
            json={
                "sco_id": "sco1",
                "status": "concluido",
                "score_raw": 85.0,
                "progresso_pct": 100.0,
            },
        )
        assert r.status_code == 201
        assert r.json()["status"] == "concluido"

    async def test_relatorio_scorm_por_curso(self, client):
        curso_id = await criar_curso(client)
        r = await client.post(
            f"/api/v1/scorm/upload?curso_id={curso_id}&titulo=SCORM+Relatorio",
            files={"arquivo": ("rel.zip", io.BytesIO(b"PK zip"), "application/zip")},
        )
        assert r.status_code == 201
        r = await client.get(f"/api/v1/scorm/cursos/{curso_id}/relatorio")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
