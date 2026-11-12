"""Testes das issues #108 (reordenar questoes em lote) e #109 (gabarito oculto
ainda entregava explicacao e pontuacao por questao)."""

from fastapi import status


async def _avaliacao(client, titulo, mostrar_gabarito="sempre", nota_minima=50):
    r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0})
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
            "titulo": titulo,
            "tipo": "prova",
            "nota_minima": nota_minima,
            "mostrar_gabarito": mostrar_gabarito,
            "tentativas_max": 3,
        },
    )
    assert r.status_code in (200, 201), r.text
    return curso_id, r.json()["id"]


async def _questao_objetiva(client, av_id, enunciado, explicacao=None, pontuacao=10):
    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={
            "avaliacao_id": av_id,
            "enunciado": enunciado,
            "tipo": "multipla_escolha",
            "pontuacao": pontuacao,
            "explicacao": explicacao,
        },
    )
    assert r.status_code in (200, 201), r.text
    q_id = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_id, "texto": "certa", "correta": True, "ordem": 0},
    )
    certa = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_id, "texto": "errada", "correta": False, "ordem": 1},
    )
    return q_id, certa, r.json()["id"]


class TestIssue108ReordenarQuestoes:
    """#108 - PATCH /avaliacoes/questoes/reorder, numa transacao."""

    async def _tres_questoes(self, client, titulo):
        _, av_id = await _avaliacao(client, titulo)
        ids = []
        for i in range(3):
            r = await client.post(
                "/api/v1/avaliacoes/questoes",
                json={
                    "avaliacao_id": av_id,
                    "enunciado": f"Q{i}",
                    "tipo": "dissertativa",
                    "pontuacao": 10,
                    "ordem": i,
                },
            )
            ids.append(r.json()["id"])
        return av_id, ids

    async def _ordens(self, client, av_id):
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/questoes")
        assert r.status_code == status.HTTP_200_OK, r.text
        return {q["id"]: q["ordem"] for q in r.json()}

    async def test_reordena_as_tres_de_uma_vez(self, client):
        av_id, ids = await self._tres_questoes(client, "C108a")
        r = await client.patch(
            "/api/v1/avaliacoes/questoes/reorder",
            json=[{"id": ids[2], "ordem": 0}, {"id": ids[0], "ordem": 1}, {"id": ids[1], "ordem": 2}],
        )
        assert r.status_code == status.HTTP_204_NO_CONTENT, r.text
        ordens = await self._ordens(client, av_id)
        assert ordens[ids[2]] == 0
        assert ordens[ids[0]] == 1
        assert ordens[ids[1]] == 2

    async def test_questao_de_outra_avaliacao_recusa_sem_aplicar_nada(self, client):
        av_id, ids = await self._tres_questoes(client, "C108b")
        _, outros = await self._tres_questoes(client, "C108c")
        antes = await self._ordens(client, av_id)
        r = await client.patch(
            "/api/v1/avaliacoes/questoes/reorder",
            json=[{"id": ids[0], "ordem": 9}, {"id": outros[0], "ordem": 8}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text
        assert await self._ordens(client, av_id) == antes

    async def test_id_inexistente_recusa_sem_aplicar_nada(self, client):
        av_id, ids = await self._tres_questoes(client, "C108d")
        antes = await self._ordens(client, av_id)
        r = await client.patch(
            "/api/v1/avaliacoes/questoes/reorder",
            json=[{"id": ids[0], "ordem": 9}, {"id": 99999999, "ordem": 8}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert await self._ordens(client, av_id) == antes

    async def test_id_repetido_recusado(self, client):
        _, ids = await self._tres_questoes(client, "C108e")
        r = await client.patch(
            "/api/v1/avaliacoes/questoes/reorder",
            json=[{"id": ids[0], "ordem": 0}, {"id": ids[0], "ordem": 1}],
        )
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async def test_a_rota_nao_cai_no_path_param(self, client):
        """O trecho "reorder" nao pode ser lido como {questao_id}."""
        _, ids = await self._tres_questoes(client, "C108f")
        r = await client.patch("/api/v1/avaliacoes/questoes/reorder", json=[{"id": ids[0], "ordem": 0}])
        assert r.status_code == status.HTTP_204_NO_CONTENT


class TestIssue109GabaritoOcultoNaoVaza:
    """#109 - com o gabarito oculto, explicacao e pontuacao_obtida vazavam."""

    async def _submeter_errando(self, client, titulo, mostrar_gabarito):
        curso_id, av_id = await _avaliacao(client, titulo, mostrar_gabarito=mostrar_gabarito, nota_minima=100)
        q_obj, _certa, errada = await _questao_objetiva(
            client, av_id, "Qual?", explicacao="A resposta certa e a primeira alternativa."
        )
        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={"avaliacao_id": av_id, "enunciado": "Explique", "tipo": "dissertativa", "pontuacao": 10},
        )
        q_diss = r.json()["id"]
        await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
        r = await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={
                "respostas": [
                    {"questao_id": q_obj, "alternativa_id": errada},
                    {"questao_id": q_diss, "resposta_texto": "R"},
                ]
            },
        )
        assert r.status_code in (200, 201), r.text
        return av_id, q_obj, q_diss

    async def test_oculto_nao_manda_explicacao_nem_pontuacao_da_objetiva(self, client):
        av_id, q_obj, q_diss = await self._submeter_errando(client, "C109a", "apos_aprovacao")
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.status_code == status.HTTP_200_OK, r.text
        questoes = {q["id"]: q for q in r.json()["questoes"]}

        objetiva = questoes[q_obj]
        assert objetiva["explicacao"] is None
        # Antes da #109: vinha 0, o que diz "errou" - e em verdadeiro_falso
        # entregaria a resposta certa por exclusao.
        assert objetiva["pontuacao_obtida"] is None
        for a in objetiva["alternativas"]:
            assert a["correta"] is None
            assert a["comentario"] is None

        # A dissertativa e correcao do instrutor, nao gabarito: nao e ocultada.
        assert questoes[q_diss]["pontuacao_obtida"] is not None

    async def test_gabarito_visivel_mantem_tudo(self, client):
        av_id, q_obj, _ = await self._submeter_errando(client, "C109b", "sempre")
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        objetiva = {q["id"]: q for q in r.json()["questoes"]}[q_obj]
        assert objetiva["explicacao"] == "A resposta certa e a primeira alternativa."
        assert objetiva["pontuacao_obtida"] == 0
        assert any(a["correta"] is not None for a in objetiva["alternativas"])

    async def test_nota_total_continua_vindo_com_gabarito_oculto(self, client):
        """O total nao e gabarito: a nota geral segue na resposta."""
        av_id, _, _ = await self._submeter_errando(client, "C109c", "apos_aprovacao")
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.json()["nota"] is not None
