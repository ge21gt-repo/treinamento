"""Testes das issues #106 (devolutiva sem nota), #107 (higienizacao da unidade),
#110 (curso_publicado na busca) e #111 (conteudo indisponivel no /consumo)."""

from fastapi import status

from app.services.sanitize import MAX_TEXTO, preparar_conteudo_texto


class TestPrepararConteudoTexto:
    """#107 — a unidade de higienizacao, sem HTTP."""

    def test_html_e_higienizado(self):
        assert "<script>" not in preparar_conteudo_texto("<p>x<script>alert(1)</script></p>", "html")

    def test_texto_puro_passa_intacto(self):
        assert preparar_conteudo_texto("<b>literal</b>", "texto") == "<b>literal</b>"

    def test_none_passa(self):
        assert preparar_conteudo_texto(None, "html") is None

    def test_limite_vale_para_html(self):
        try:
            preparar_conteudo_texto("a" * (MAX_TEXTO + 1), "html")
            raise AssertionError("deveria ter recusado")
        except ValueError as exc:
            assert "limite" in str(exc)

    def test_limite_vale_tambem_para_texto_puro(self):
        """Antes da #107 o limite so era aplicado no caminho html."""
        try:
            preparar_conteudo_texto("a" * (MAX_TEXTO + 1), "texto")
            raise AssertionError("deveria ter recusado")
        except ValueError as exc:
            assert "limite" in str(exc)


class TestIssue107HigienizacaoPeloFormatoFinal:
    """#107 — trocar o formato para html nao pode promover texto nao higienizado."""

    async def _unidade(self, client, titulo, **extra):
        r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0},
        )
        mid = r.json()["id"]
        payload = {"modulo_id": mid, "titulo": "U", "tipo": "texto", **extra}
        r = await client.post("/api/v1/cursos/unidades", json=payload)
        assert r.status_code == status.HTTP_201_CREATED, r.text
        return r.json()["id"]

    async def test_trocar_formato_para_html_higieniza_o_texto_gravado(self, client):
        """A sequencia de dois PATCH descrita na issue."""
        uid = await self._unidade(
            client,
            "C107a",
            formato_texto="texto",
            conteudo_texto="<img src=x onerror=alert(1)>",
        )
        # Passo 1: gravado como texto puro, nao higienizado (correto para texto).
        r = await client.patch(
            f"/api/v1/cursos/unidades/{uid}",
            json={"formato_texto": "texto", "conteudo_texto": "<img src=x onerror=alert(1)>"},
        )
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["conteudo_texto"] == "<img src=x onerror=alert(1)>"

        # Passo 2: troca SO o formato, sem reenviar o texto.
        r = await client.patch(f"/api/v1/cursos/unidades/{uid}", json={"formato_texto": "html"})
        assert r.status_code == status.HTTP_200_OK
        corpo = r.json()
        assert corpo["formato_texto"] == "html"
        assert "onerror" not in corpo["conteudo_texto"]
        assert "<img" not in corpo["conteudo_texto"]

    async def test_voltar_para_texto_nao_higieniza(self, client):
        uid = await self._unidade(client, "C107b", formato_texto="texto", conteudo_texto="a")
        r = await client.patch(
            f"/api/v1/cursos/unidades/{uid}",
            json={"formato_texto": "texto", "conteudo_texto": "<b>x</b>"},
        )
        assert r.json()["conteudo_texto"] == "<b>x</b>"

    async def test_patch_que_nao_toca_no_texto_preserva_o_texto(self, client):
        uid = await self._unidade(client, "C107c", formato_texto="html", conteudo_texto="<p>ok</p>")
        r = await client.patch(f"/api/v1/cursos/unidades/{uid}", json={"titulo": "Outro"})
        assert r.status_code == status.HTTP_200_OK
        assert r.json()["titulo"] == "Outro"
        assert r.json()["conteudo_texto"] == "<p>ok</p>"

    async def test_formato_invalido_recusado_no_patch(self, client):
        uid = await self._unidade(client, "C107d", formato_texto="texto", conteudo_texto="a")
        r = await client.patch(f"/api/v1/cursos/unidades/{uid}", json={"formato_texto": "markdown"})
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_formato_invalido_recusado_na_criacao(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "C107e", "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0},
        )
        mid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={"modulo_id": mid, "titulo": "U", "tipo": "texto", "formato_texto": "markdown"},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_texto_puro_acima_do_limite_recusado(self, client):
        uid = await self._unidade(client, "C107f", formato_texto="texto", conteudo_texto="a")
        r = await client.patch(
            f"/api/v1/cursos/unidades/{uid}",
            json={"formato_texto": "texto", "conteudo_texto": "a" * (MAX_TEXTO + 1)},
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def _marcar_indisponivel(conteudo_id: int):
    """`disponivel` nao e exposto por nenhuma rota de escrita (a issue 46 marca por
    fora), entao o teste grava direto. Engine propria, como as fixtures do conftest."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.config import settings

    engine = create_async_engine(settings.TEST_DATABASE_URL or settings.DATABASE_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE lms.conteudos SET disponivel = false WHERE id = :i"),
                {"i": conteudo_id},
            )
    finally:
        await engine.dispose()


class TestIssue111ConsumoRespeitaDisponivel:
    """#111 — /cursos/{id}/consumo monta o conteudo a mao e ignorava `disponivel`."""

    async def _curso_com_conteudos(self, client):
        r = await client.post(
            "/api/v1/cursos",
            json={"titulo": "C111", "descricao": "x", "ordem": 0, "publicado": True},
        )
        cid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0},
        )
        mid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={"modulo_id": mid, "titulo": "U", "tipo": "conteudo", "ordem": 0},
        )
        uid = r.json()["id"]
        ids = {}
        for nome, url in (("vivo", "https://x/ok.pdf"), ("morto", "https://x/sumiu.pdf")):
            r = await client.post(
                "/api/v1/conteudos",
                json={
                    "unidade_id": uid,
                    "tipo_midia": "pdf",
                    "titulo": nome,
                    "url_arquivo": url,
                    "ordem": 0,
                },
            )
            assert r.status_code in (200, 201), r.text
            ids[nome] = r.json()["id"]
        await _marcar_indisponivel(ids["morto"])
        return cid, ids

    async def test_consumo_devolve_disponivel_e_nao_gera_url_do_arquivo_morto(self, client):
        cid, ids = await self._curso_com_conteudos(client)
        r = await client.get(f"/api/v1/cursos/{cid}/consumo")
        assert r.status_code == status.HTTP_200_OK, r.text
        conteudos = {c["id"]: c for m in r.json()["modulos"] for u in m["unidades"] for c in u["conteudos"]}
        vivo = conteudos[ids["vivo"]]
        morto = conteudos[ids["morto"]]

        assert vivo["disponivel"] is True
        assert vivo["url_arquivo"] == "https://x/ok.pdf"

        # Antes da #111 este vinha com a URL, e a tela mostrava o NoSuchBucket cru.
        assert morto["disponivel"] is False
        assert morto["url_arquivo"] is None
