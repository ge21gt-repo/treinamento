"""Testes da issue #105 (so a ultima tentativa vai para correcao) e do ajuste
da regra mostrar_gabarito='ao_esgotar_tentativas' decidido na #109."""

from fastapi import status


async def _avaliacao(client, titulo, tentativas_max=3, mostrar_gabarito="sempre"):
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
            "nota_minima": 50,
            "mostrar_gabarito": mostrar_gabarito,
            "tentativas_max": tentativas_max,
        },
    )
    assert r.status_code in (200, 201), r.text
    await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    return curso_id, r.json()["id"]


async def _dissertativa(client, av_id, enunciado="Explique"):
    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={"avaliacao_id": av_id, "enunciado": enunciado, "tipo": "dissertativa", "pontuacao": 10},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _submeter(client, av_id, q_id, texto="R"):
    r = await client.post(
        f"/api/v1/avaliacoes/{av_id}/submeter",
        json={"respostas": [{"questao_id": q_id, "resposta_texto": texto}]},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


class TestIssue105SoUltimaTentativaVaiParaCorrecao:
    """#105 - tentativa superada nao pende mais, nem para o instrutor nem para o aluno."""

    async def test_fila_da_avaliacao_traz_so_a_ultima(self, client):
        _, av_id = await _avaliacao(client, "C105a")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, q_id, "tentativa 1")
        await _submeter(client, av_id, q_id, "tentativa 2")

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/correcoes-pendentes")
        assert r.status_code == status.HTTP_200_OK, r.text
        tentativas = [i["tentativa_num"] for i in r.json()]
        assert tentativas == [2]

    async def test_inbox_global_traz_so_a_ultima(self, client):
        _, av_id = await _avaliacao(client, "C105b")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, q_id, "tentativa 1")
        await _submeter(client, av_id, q_id, "tentativa 2")

        r = await client.get("/api/v1/avaliacoes/correcoes-pendentes")
        assert r.status_code == status.HTTP_200_OK, r.text
        desta = [i for i in r.json() if i["avaliacao_id"] == av_id]
        assert [i["tentativa_num"] for i in desta] == [2]

    async def test_meus_resultados_pende_so_na_ultima(self, client):
        _, av_id = await _avaliacao(client, "C105c")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, q_id, "tentativa 1")
        await _submeter(client, av_id, q_id, "tentativa 2")

        r = await client.get("/api/v1/avaliacoes/meus-resultados")
        assert r.status_code == status.HTTP_200_OK, r.text
        pendencia = {
            res["tentativa_num"]: res["aguardando_correcao"]
            for res in r.json()
            if res["avaliacao_id"] == av_id
        }
        assert pendencia == {1: False, 2: True}

    async def test_correcao_ja_feita_na_tentativa_1_continua_valendo(self, client):
        """Decisao registrada na #105: a correcao nao e descartada, a tentativa so deixa de pender."""
        _, av_id = await _avaliacao(client, "C105d")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, q_id, "tentativa 1")

        fila = (await client.get(f"/api/v1/avaliacoes/{av_id}/correcoes-pendentes")).json()
        assert [i["tentativa_num"] for i in fila] == [1]
        resposta_id = fila[0]["resposta_id"]
        r = await client.patch(
            f"/api/v1/avaliacoes/respostas/{resposta_id}/corrigir",
            json={"pontuacao_atribuida": 8},
        )
        assert r.status_code == status.HTTP_200_OK, r.text

        await _submeter(client, av_id, q_id, "tentativa 2")

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.status_code == status.HTTP_200_OK, r.text
        questao = {q["id"]: q for q in r.json()["questoes"]}[q_id]
        assert float(questao["pontuacao_obtida"]) == 8.0
        assert r.json()["aguardando_correcao"] is False

    async def test_tentativa_unica_continua_pendendo(self, client):
        """Nao regride a #88: com uma tentativa so, ela e a ultima e pende."""
        _, av_id = await _avaliacao(client, "C105e")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, q_id, "tentativa 1")

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/correcoes-pendentes")
        assert [i["tentativa_num"] for i in r.json()] == [1]
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.json()["aguardando_correcao"] is True


class TestIssue109RegraAoEsgotarTentativas:
    """#109 - a regra conta as tentativas feitas, nao a tentativa aberta."""

    async def test_quem_esgotou_ve_o_gabarito_da_primeira_tentativa(self, client):
        _, av_id = await _avaliacao(
            client, "C109d", tentativas_max=2, mostrar_gabarito="ao_esgotar_tentativas"
        )
        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={
                "avaliacao_id": av_id,
                "enunciado": "Qual?",
                "tipo": "multipla_escolha",
                "pontuacao": 10,
                "explicacao": "A certa e a primeira.",
            },
        )
        q_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/alternativas",
            json={"questao_id": q_id, "texto": "certa", "correta": True, "ordem": 0},
        )
        certa = r.json()["id"]
        for _ in range(2):
            r = await client.post(
                f"/api/v1/avaliacoes/{av_id}/submeter",
                json={"respostas": [{"questao_id": q_id, "alternativa_id": certa}]},
            )
            assert r.status_code in (200, 201), r.text

        # Antes: o gabarito da tentativa 1 ficava trancado para sempre, mesmo
        # com a pessoa sem nenhuma tentativa restante.
        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        assert r.status_code == status.HTTP_200_OK, r.text
        questao = {q["id"]: q for q in r.json()["questoes"]}[q_id]
        assert questao["explicacao"] == "A certa e a primeira."
        assert any(a["correta"] is not None for a in questao["alternativas"])

    async def test_com_tentativa_sobrando_segue_oculto(self, client):
        _, av_id = await _avaliacao(
            client, "C109e", tentativas_max=3, mostrar_gabarito="ao_esgotar_tentativas"
        )
        r = await client.post(
            "/api/v1/avaliacoes/questoes",
            json={
                "avaliacao_id": av_id,
                "enunciado": "Qual?",
                "tipo": "multipla_escolha",
                "pontuacao": 10,
                "explicacao": "A certa e a primeira.",
            },
        )
        q_id = r.json()["id"]
        r = await client.post(
            "/api/v1/avaliacoes/alternativas",
            json={"questao_id": q_id, "texto": "certa", "correta": True, "ordem": 0},
        )
        certa = r.json()["id"]
        await client.post(
            f"/api/v1/avaliacoes/{av_id}/submeter",
            json={"respostas": [{"questao_id": q_id, "alternativa_id": certa}]},
        )

        r = await client.get(f"/api/v1/avaliacoes/{av_id}/resultado/1")
        questao = {q["id"]: q for q in r.json()["questoes"]}[q_id]
        assert questao["explicacao"] is None
        assert all(a["correta"] is None for a in questao["alternativas"])
