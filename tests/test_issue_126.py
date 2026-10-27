"""Issue #126: a lista de resultados mostrava "Reprovado" numa tentativa que
ja tinha sido substituida por uma mais recente.

Desde a #105 so a ultima tentativa vai para correcao, e a anterior deixa de
ficar "aguardando correcao" com a nota que tinha. Para quem tinha mais que a
nota minima e uma dissertativa sem corrigir, a lista passou a dizer
"nota 66,67, Reprovado" - verdade em cada campo, contraditoria na tela.

Opcao A da issue: campo `substituida`, sem mexer em `aprovado` nem na nota.
"""

from fastapi import status

from app.api.deps import get_current_user
from app.main import app

_RESULTADOS = "/api/v1/avaliacoes/meus-resultados"


class _ComoUsuario:
    """Troca o get_current_user e devolve o anterior no fim."""

    def __init__(self, user):
        self.user = user

    def __enter__(self):
        self.anterior = app.dependency_overrides.get(get_current_user)
        app.dependency_overrides[get_current_user] = lambda: self.user
        return self.user

    def __exit__(self, *exc):
        if self.anterior is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = self.anterior
        return False


async def _avaliacao(client, titulo, nota_minima=60, tentativas_max=3):
    """Curso -> modulo -> unidade -> avaliacao, com o autor ja inscrito."""
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
            "mostrar_gabarito": "sempre",
            "tentativas_max": tentativas_max,
        },
    )
    assert r.status_code in (200, 201), r.text
    await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    return curso_id, r.json()["id"]


async def _dissertativa(client, av_id, pontuacao=10):
    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={
            "avaliacao_id": av_id,
            "enunciado": "Explique",
            "tipo": "dissertativa",
            "pontuacao": pontuacao,
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


async def _objetiva(client, av_id, pontuacao=10):
    """Questao de multipla escolha; devolve (questao_id, alternativa_certa_id)."""
    r = await client.post(
        "/api/v1/avaliacoes/questoes",
        json={
            "avaliacao_id": av_id,
            "enunciado": "Qual?",
            "tipo": "multipla_escolha",
            "pontuacao": pontuacao,
        },
    )
    assert r.status_code in (200, 201), r.text
    q_id = r.json()["id"]
    r = await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_id, "texto": "certa", "correta": True, "ordem": 0},
    )
    assert r.status_code in (200, 201), r.text
    certa = r.json()["id"]
    await client.post(
        "/api/v1/avaliacoes/alternativas",
        json={"questao_id": q_id, "texto": "errada", "correta": False, "ordem": 1},
    )
    return q_id, certa


async def _submeter(client, av_id, respostas):
    r = await client.post(f"/api/v1/avaliacoes/{av_id}/submeter", json={"respostas": respostas})
    assert r.status_code in (200, 201), r.text
    return r.json()


async def _por_tentativa(client, av_id, rota=_RESULTADOS):
    """{tentativa_num: resultado} daquela avaliacao, pela rota pedida."""
    r = await client.get(rota)
    assert r.status_code == status.HTTP_200_OK, r.text
    return {res["tentativa_num"]: res for res in r.json() if res["avaliacao_id"] == av_id}


class TestIssue126CasoDoDev:
    """O caso concreto relatado: nota acima da minima, "Reprovado" na lista."""

    async def test_a_tentativa_superada_sai_marcada(self, client):
        """Reproduz a avaliacao 160 do dev: minima 60, duas objetivas certas e
        uma dissertativa sem correcao -> 20 de 30 = 66,67, nao aprovado."""
        _, av_id = await _avaliacao(client, "C126a", nota_minima=60)
        q1, certa1 = await _objetiva(client, av_id)
        q2, certa2 = await _objetiva(client, av_id)
        diss = await _dissertativa(client, av_id)
        respostas = [
            {"questao_id": q1, "alternativa_id": certa1},
            {"questao_id": q2, "alternativa_id": certa2},
            {"questao_id": diss, "resposta_texto": "R"},
        ]
        await _submeter(client, av_id, respostas)

        t1 = (await _por_tentativa(client, av_id))[1]
        # A contradicao da issue, antes de existir a segunda tentativa: aqui
        # ainda se explica pelo aguardando_correcao.
        assert float(t1["nota"]) == 66.67
        assert t1["aprovado"] is False
        assert t1["aguardando_correcao"] is True
        assert t1["substituida"] is False

        await _submeter(client, av_id, respostas)

        por_tentativa = await _por_tentativa(client, av_id)
        t1 = por_tentativa[1]
        # Agora o aguardando_correcao caiu (regra da #105) e so o campo novo
        # explica por que uma nota de 66,67 com minima 60 nao esta aprovada.
        assert t1["aguardando_correcao"] is False
        assert t1["substituida"] is True
        assert por_tentativa[2]["substituida"] is False

    async def test_a_nota_e_o_aprovado_nao_mudam(self, client):
        """Opcao A: o campo e informativo, nao reescreve o veredito."""
        _, av_id = await _avaliacao(client, "C126b", nota_minima=60)
        q1, certa1 = await _objetiva(client, av_id)
        diss = await _dissertativa(client, av_id)
        respostas = [
            {"questao_id": q1, "alternativa_id": certa1},
            {"questao_id": diss, "resposta_texto": "R"},
        ]
        await _submeter(client, av_id, respostas)
        antes = (await _por_tentativa(client, av_id))[1]

        await _submeter(client, av_id, respostas)
        depois = (await _por_tentativa(client, av_id))[1]

        assert depois["nota"] == antes["nota"]
        assert depois["aprovado"] == antes["aprovado"]
        assert depois["id"] == antes["id"]
        assert depois["substituida"] is True


class TestIssue126CriterioDeAceite:
    """Os casos que a issue pede explicitamente."""

    async def test_tentativa_unica_nao_e_marcada(self, client):
        _, av_id = await _avaliacao(client, "C126c")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])

        por_tentativa = await _por_tentativa(client, av_id)
        assert list(por_tentativa) == [1]
        assert por_tentativa[1]["substituida"] is False

    async def test_terceira_tentativa_marca_as_duas_anteriores(self, client):
        """O criterio e "existe tentativa de numero maior", nao "e a penultima"."""
        _, av_id = await _avaliacao(client, "C126d", tentativas_max=3)
        q_id = await _dissertativa(client, av_id)
        for _ in range(3):
            await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])

        marcadas = {n: r["substituida"] for n, r in (await _por_tentativa(client, av_id)).items()}
        assert marcadas == {1: True, 2: True, 3: False}

    async def test_substituida_e_aguardando_nunca_coexistem(self, client):
        """Invariante que vem da #105: tentativa substituida nao pende mais.

        Os dois campos saem do mesmo max(tentativa_num) justamente para nao
        poderem discordar.
        """
        _, av_id = await _avaliacao(client, "C126e", tentativas_max=3)
        q_id = await _dissertativa(client, av_id)
        for _ in range(3):
            await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])

        for res in (await _por_tentativa(client, av_id)).values():
            assert not (res["substituida"] and res["aguardando_correcao"]), res


class TestIssue126Escopo:
    """A conta e por (usuario, avaliacao) - nem global, nem so por usuario."""

    async def test_a_tentativa_de_outra_pessoa_nao_substitui(self, client, participante_user):
        """A outra pessoa chega a tentativa 2; a minha tentativa 1 nao e tocada.

        Com os dois na tentativa 1 o teste nao provava nada: o max global
        daria 1 de qualquer jeito. E preciso que o numero do outro seja maior.
        """
        curso_id, av_id = await _avaliacao(client, "C126f")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "admin"}])

        with _ComoUsuario(participante_user):
            r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
            assert r.status_code in (200, 201), r.text
            for _ in range(2):
                await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "outro"}])
            do_outro = await _por_tentativa(client, av_id)

        assert {n: r["substituida"] for n, r in do_outro.items()} == {1: True, 2: False}
        assert do_outro[1]["usuario_id"] == str(participante_user.id)

        meus = await _por_tentativa(client, av_id)
        assert list(meus) == [1]
        assert meus[1]["substituida"] is False

    async def test_tentativa_em_outra_avaliacao_nao_substitui(self, client):
        _, av_a = await _avaliacao(client, "C126g")
        _, av_b = await _avaliacao(client, "C126h")
        qa = await _dissertativa(client, av_a)
        qb = await _dissertativa(client, av_b)

        await _submeter(client, av_a, [{"questao_id": qa, "resposta_texto": "R"}])
        # Duas tentativas na avaliacao B nao podem marcar a unica da A.
        await _submeter(client, av_b, [{"questao_id": qb, "resposta_texto": "R"}])
        await _submeter(client, av_b, [{"questao_id": qb, "resposta_texto": "R"}])

        assert (await _por_tentativa(client, av_a))[1]["substituida"] is False
        marcadas_b = {n: r["substituida"] for n, r in (await _por_tentativa(client, av_b)).items()}
        assert marcadas_b == {1: True, 2: False}


class TestIssue126OutrasRotas:
    """O campo esta no ResultadoAvaliacaoRead, que serve tres listas."""

    async def test_resultados_da_avaliacao(self, client):
        _, av_id = await _avaliacao(client, "C126i")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])

        rota = f"/api/v1/avaliacoes/{av_id}/resultados"
        marcadas = {n: r["substituida"] for n, r in (await _por_tentativa(client, av_id, rota)).items()}
        assert marcadas == {1: True, 2: False}

    async def test_resultados_de_um_usuario(self, client, admin_user):
        _, av_id = await _avaliacao(client, "C126j")
        q_id = await _dissertativa(client, av_id)
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])
        await _submeter(client, av_id, [{"questao_id": q_id, "resposta_texto": "R"}])

        rota = f"/api/v1/avaliacoes/resultados/{admin_user.id}"
        marcadas = {n: r["substituida"] for n, r in (await _por_tentativa(client, av_id, rota)).items()}
        assert marcadas == {1: True, 2: False}
