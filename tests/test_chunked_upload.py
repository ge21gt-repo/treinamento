class TestChunkedUpload:
    """Testa o fluxo completo de upload chunked (retomável)."""

    async def _setup(self, client):
        r = await client.post(
            "/api/v1/cursos", json={"titulo": "Curso Chunk", "descricao": "x", "ordem": 0}
        )
        curso_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": curso_id, "titulo": "Mod", "descricao": "x", "ordem": 0},
        )
        mod_id = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={"modulo_id": mod_id, "titulo": "Unid", "tipo": "conteudo", "ordem": 0},
        )
        return r.json()["id"]

    async def test_chunked_flow_completo(self, client):
        uni_id = await self._setup(client)

        # 1. Iniciar
        r = await client.post(
            "/api/v1/conteudos/upload/iniciar",
            json={"filename": "teste.txt", "folder": "pdfs", "total_chunks": 3},
        )
        assert r.status_code == 200, r.text
        upload_id = r.json()["upload_id"]
        assert r.json()["total_chunks"] == 3

        # 2. Enviar chunks fora de ordem
        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/chunk?chunk_index=2",
            content=b"!",
        )
        assert r.status_code == 204, r.text

        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/chunk?chunk_index=0",
            content=b"Hello ",
        )
        assert r.status_code == 204, r.text

        # 3. Status ainda incompleto
        r = await client.get(f"/api/v1/conteudos/upload/{upload_id}/status")
        assert r.status_code == 200
        data = r.json()
        assert data["complete"] is False
        assert data["missing_chunks"] == [1]

        # 4. Enviar chunk faltante
        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/chunk?chunk_index=1",
            content=b"World",
        )
        assert r.status_code == 204, r.text

        # 5. Status completo
        r = await client.get(f"/api/v1/conteudos/upload/{upload_id}/status")
        assert r.json()["complete"] is True
        assert r.json()["missing_chunks"] == []

        # 6. Completar → cria Conteudo
        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/completar"
            f"?unidade_id={uni_id}&tipo_midia=pdf&titulo=Chunked%20Test&ordem=0",
        )
        assert r.status_code == 201, r.text
        conteudo = r.json()
        assert conteudo["titulo"] == "Chunked Test"

        # 7. Verificar arquivo no disco
        import os

        path = "." + conteudo["url_arquivo"]
        assert os.path.exists(path), f"Arquivo nao encontrado: {path}"
        with open(path) as f:
            assert f.read() == "Hello World!"

    async def test_chunk_idempotente(self, client):
        """Mesmo chunk enviado 2x não causa erro."""
        r = await client.post(
            "/api/v1/conteudos/upload/iniciar",
            json={"filename": "dup.txt", "folder": "pdfs", "total_chunks": 1},
        )
        upload_id = r.json()["upload_id"]

        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/chunk?chunk_index=0",
            content=b"duplicado",
        )
        assert r.status_code == 204

        r = await client.post(
            f"/api/v1/conteudos/upload/{upload_id}/chunk?chunk_index=0",
            content=b"duplicado",
        )
        assert r.status_code == 204  # idempotente

    async def test_status_upload_inexistente_404(self, client):
        r = await client.get("/api/v1/conteudos/upload/invalido/status")
        assert r.status_code == 404
