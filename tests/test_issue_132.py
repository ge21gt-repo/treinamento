"""Issue #132 — agenda de aulas ao vivo.

A aula que ja comecou nao pode sumir da lista; o status e calculado na leitura;
`passadas=true` devolve as encerradas (sem as canceladas).
"""

from datetime import datetime, timedelta, timezone

from fastapi import status

_PROXIMAS = "/api/v1/cursos/aulas/proximas"


def _iso(minutos: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutos)).isoformat()


async def _curso_inscrito(client) -> int:
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso 132", "ordem": 0})
    assert r.status_code == 201, r.text
    curso_id = r.json()["id"]
    r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": curso_id})
    assert r.status_code == 201, r.text
    return curso_id


async def _aula(client, curso_id, titulo, inicio_min, duracao=60, **extra):
    corpo = {
        "curso_id": curso_id,
        "titulo": titulo,
        "data_hora": _iso(inicio_min),
        "duracao_minutos": duracao,
        **extra,
    }
    r = await client.post(f"/api/v1/cursos/{curso_id}/aulas", json=corpo)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_aula_em_andamento_continua_na_lista(client):
    curso_id = await _curso_inscrito(client)
    aula_id = await _aula(client, curso_id, "Rolando", inicio_min=-10)

    r = await client.get(_PROXIMAS)
    assert r.status_code == status.HTTP_200_OK, r.text
    item = next((a for a in r.json() if a["id"] == aula_id), None)
    assert item is not None, "a aula em andamento sumiu da lista"
    assert item["status"] == "em_andamento", item


async def test_aula_futura_vem_agendada(client):
    curso_id = await _curso_inscrito(client)
    aula_id = await _aula(client, curso_id, "Futura", inicio_min=60)

    r = await client.get(_PROXIMAS)
    item = next(a for a in r.json() if a["id"] == aula_id)
    assert item["status"] == "agendada", item


async def test_aula_encerrada_sai_da_lista_e_entra_em_passadas(client):
    curso_id = await _curso_inscrito(client)
    aula_id = await _aula(client, curso_id, "Encerrada", inicio_min=-180)

    r = await client.get(_PROXIMAS)
    assert all(a["id"] != aula_id for a in r.json()), "aula encerrada ainda na lista de proximas"

    r = await client.get(_PROXIMAS, params={"passadas": "true"})
    item = next((a for a in r.json() if a["id"] == aula_id), None)
    assert item is not None, "aula encerrada nao apareceu em passadas"
    assert item["status"] == "concluida", item


async def test_passadas_vem_da_mais_recente_para_a_mais_antiga(client):
    curso_id = await _curso_inscrito(client)
    antiga = await _aula(client, curso_id, "Antiga", inicio_min=-300)
    recente = await _aula(client, curso_id, "Recente", inicio_min=-120)

    r = await client.get(_PROXIMAS, params={"passadas": "true"})
    ids = [a["id"] for a in r.json() if a["id"] in (antiga, recente)]
    assert ids == [recente, antiga], ids


async def test_cancelada_nao_entra_em_passadas(client):
    curso_id = await _curso_inscrito(client)
    await _aula(client, curso_id, "Cancelada", inicio_min=-180, status="cancelada")

    r = await client.get(_PROXIMAS, params={"passadas": "true"})
    assert all(a["status"] != "cancelada" for a in r.json())


async def test_status_cancelada_manual_nao_e_sobrescrito(client):
    curso_id = await _curso_inscrito(client)
    aula_id = await _aula(client, curso_id, "Cancelada futura", inicio_min=60, status="cancelada")

    r = await client.get(_PROXIMAS)
    item = next(a for a in r.json() if a["id"] == aula_id)
    assert item["status"] == "cancelada", item


async def test_limit_configuravel(client):
    curso_id = await _curso_inscrito(client)
    for i in range(3):
        await _aula(client, curso_id, f"Futura {i}", inicio_min=60 + i)

    r = await client.get(_PROXIMAS, params={"limit": 2})
    assert len(r.json()) == 2


async def test_listar_aulas_do_curso_tambem_calcula_status(client):
    curso_id = await _curso_inscrito(client)
    em_andamento = await _aula(client, curso_id, "Rolando", inicio_min=-10)
    encerrada = await _aula(client, curso_id, "Encerrada", inicio_min=-180)

    r = await client.get(f"/api/v1/cursos/{curso_id}/aulas")
    assert r.status_code == status.HTTP_200_OK, r.text
    por_id = {a["id"]: a for a in r.json()}
    assert por_id[em_andamento]["status"] == "em_andamento"
    assert por_id[encerrada]["status"] == "concluida"
