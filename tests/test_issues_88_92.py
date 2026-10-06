"""Testes das issues #88 (nota), #89/#92 (MIME), #90 (comentario alternativa),
#91 (rich text na unidade) e #102 (busca de conteudos com contexto de curso)."""

from fastapi import status

from app.services.sanitize import sanitizar_html
from app.services.storage import normalizar_mime


class TestNormalizarMime:
    """#92 (zip do Windows) e #89 (PDF)."""

    def test_zip_windows(self):
        assert normalizar_mime("application/x-zip-compressed", "p.zip") == "application/zip"

    def test_pdf_alias(self):
        assert normalizar_mime("application/x-pdf", "a.pdf") == "application/pdf"

    def test_octet_stream_por_extensao(self):
        assert normalizar_mime("application/octet-stream", "a.pdf") == "application/pdf"
        assert normalizar_mime(None, "a.zip") == "application/zip"
        assert normalizar_mime("", "a.pdf") == "application/pdf"

    def test_tipo_desconhecido_passa(self):
        assert normalizar_mime("text/plain", "a.txt") == "text/plain"


class TestSanitizarHtml:
    """#91."""

    def test_mantem_tags_permitidas(self):
        assert sanitizar_html("<p>Oi <strong>b</strong></p>") == "<p>Oi <strong>b</strong></p>"

    def test_remove_script(self):
        assert "<script>" not in sanitizar_html("<script>alert(1)</script>x")

    def test_remove_javascript_href(self):
        assert sanitizar_html('<a href="javascript:alert(1)">x</a>') == "x"

    def test_link_http_ok(self):
        assert sanitizar_html('<a href="https://x.com" onclick="e">l</a>') == '<a href="https://x.com">l</a>'

    def test_none(self):
        assert sanitizar_html(None) is None


async def _setup_avaliacao_mista(client, nota_minima=50, mostrar_gabarito="sempre"):
    """Avaliacao com 1 objetiva (10pts) + 1 dissertativa (10pts)."""
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso 88", "descricao": "x", "ordem": 0})
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
    uni_id = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes",
        json={
            "unidade_id": uni_id,
            "titulo": "Mista",
            "tipo": "prova",
            "nota_minima": nota_minima,
            "mostrar_gabarito": mostrar_gabarito,
        },
    )
    av_id = r.json()["id"]

    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={"avaliacao_id": av_id, "enunciado": "2+2?", "tipo": "multipla_escolha", "pontuacao": 10},
    )
    q_obj = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_obj, "texto": "4", "correta": True, "ordem": 0},
    )
    alt_certa = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_obj, "texto": "5", "correta": False, "comentario": "Errado", "ordem": 1},
    )
    alt_errada = r.json()["id"]

    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={"avaliacao_id": av_id, "enunciado": "Explique", "tipo": "dissertativa", "pontuacao": 10},
    )
    q_diss = r.json()["id"]

    await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    return {
        "curso_id": curso_id,
        "uni_id": uni_id,
        "av_id": av_id,
        "q_obj": q_obj,
        "alt_certa": alt_certa,
        "alt_errada": alt_errada,
        "q_diss": q_diss,
    }


class TestIssue88NotaTotal:
    """#88 — o total considera todas as questoes da avaliacao."""

    async def test_dissertativa_pendente_entra_no_total(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Resposta"},
                ]
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        d = r.json()
        assert d["nota"] == 50.0
        assert d["aprovado"] is False
        assert d["aguardando_correcao"] is True

    async def test_responder_so_a_objetiva_nao_infla_nota(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={"respostas": [{"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]}]},
        )
        assert r.json()["nota"] == 50.0

    async def test_corrigir_ultima_aprova_e_enxerga_feedback(self, client):
        setup = await _setup_avaliacao_mista(client)
        await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_certa"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "Boa"},
                ]
            },
        )
        pend = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/correcoes-pendentes")
        resp_id = pend.json()[0]["resposta_id"]
        r = await client.patch(
            f"/api/v1/avaliacoes/respostas/{resp_id}/corrigir", json={"pontuacao_atribuida": 10}
        )
        assert r.status_code == status.HTTP_200_OK
        res = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/resultado/1")
        d = res.json()
        assert float(d["nota"]) == 100.0
        assert d["aprovado"] is True
        assert d["aguardando_correcao"] is False


class TestIssue90ComentarioAlternativa:
    """#90 — comentario por alternativa."""

    async def test_grava_comentario_da_alternativa(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.post(
            "/api/v1/avaliacoes/alternativas",
            json={"questao_id": setup["q_obj"], "texto": "2", "correta": False, "comentario": "Muito baixo", "ordem": 2},
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["comentario"] == "Muito baixo"

    async def test_responder_nao_vaza_comentario_nem_correta(self, client):
        setup = await _setup_avaliacao_mista(client)
        r = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/responder")
        assert r.status_code == status.HTTP_200_OK
        alternativas = [a for q in r.json().get("questoes", []) for a in q.get("alternativas", [])]
        assert alternativas
        for a in alternativas:
            assert "correta" not in a
            assert "comentario" not in a

    async def test_feedback_mostra_comentario(self, client):
        setup = await _setup_avaliacao_mista(client)
        await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_errada"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "R"},
                ]
            },
        )
        r = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/resultado/1")
        comentarios = [a.get("comentario") for q in r.json()["questoes"] for a in q["alternativas"]]
        assert "Errado" in comentarios

    async def test_mostrar_gabarito_apos_aprovacao_oculta(self, client):
        setup = await _setup_avaliacao_mista(client, mostrar_gabarito="apos_aprovacao")
        await client.post(
            f"/api/v1/avaliacoes/{setup['av_id']}/submeter",
            json={
                "respostas": [
                    {"questao_id": setup["q_obj"], "alternativa_id": setup["alt_errada"]},
                    {"questao_id": setup["q_diss"], "resposta_texto": "R"},
                ]
            },
        )
        r = await client.get(f"/api/v1/avaliacoes/{setup['av_id']}/resultado/1")
        for q in r.json()["questoes"]:
            for a in q["alternativas"]:
                assert a["correta"] is None
                assert a["comentario"] is None


class TestIssue91RichText:
    """#91 — conteudo_texto/format_texto na unidade."""

    async def _curso_modulo(self, client, titulo):
        r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
        cid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0},
        )
        return r.json()["id"]

    async def test_html_sanitizado(self, client):
        mid = await self._curso_modulo(client, "C91")
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={
                "modulo_id": mid,
                "titulo": "U",
                "tipo": "texto",
                "formato_texto": "html",
                "conteudo_texto": "<p>Ola<script>alert(1)</script></p>",
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert "<script>" not in r.json()["conteudo_texto"]
        assert r.json()["formato_texto"] == "html"

    async def test_texto_plano_preservado(self, client):
        mid = await self._curso_modulo(client, "C91b")
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={
                "modulo_id": mid,
                "titulo": "U",
                "tipo": "texto",
                "formato_texto": "texto",
                "conteudo_texto": "<b>literal</b>",
            },
        )
        assert r.status_code == status.HTTP_201_CREATED
        assert r.json()["conteudo_texto"] == "<b>literal</b>"


class TestIssue102BuscaConteudos:
    """#102 — a busca devolve o contexto de curso e respeita publicacao."""

    async def _conteudo(self, client, publicado):
        r = await client.post(
            "/api/v1/cursos",
            json={"titulo": "Curso Busca", "descricao": "x", "ordem": 0, "publicado": publicado},
        )
        cid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/modulos",
            json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0},
        )
        mid = r.json()["id"]
        r = await client.post(
            "/api/v1/cursos/unidades",
            json={"modulo_id": mid, "titulo": "Unidade X", "tipo": "conteudo", "ordem": 0},
        )
        uid = r.json()["id"]
        r = await client.post(
            "/api/v1/conteudos",
            json={
                "unidade_id": uid,
                "tipo_midia": "pdf",
                "titulo": "Material palavra-chave",
                "url_arquivo": "https://x/a.pdf",
                "ordem": 0,
            },
        )
        return cid, r.json()["id"]

    async def test_listagem_traz_contexto_do_curso(self, client):
        cid, _ = await self._conteudo(client, publicado=True)
        r = await client.get("/api/v1/conteudos", params={"q": "palavra-chave"})
        assert r.status_code == status.HTTP_200_OK
        items = r.json()
        assert len(items) == 1
        assert items[0]["curso_id"] == cid
        assert items[0]["curso_titulo"] == "Curso Busca"
        assert items[0]["unidade_titulo"] == "Unidade X"

    async def test_admin_ve_rascunho(self, client):
        cid, _ = await self._conteudo(client, publicado=False)
        r = await client.get("/api/v1/conteudos", params={"q": "palavra-chave"})
        assert len(r.json()) == 1
