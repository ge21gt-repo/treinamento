"""Issue #130 — catálogo: ordem estável, filtros e campos do cartão.

Cobre `GET /trilhas` (ordem, `ordenar`/`direcao`, `publicada`, `inscrito`,
`X-Total-Count`, `total_cursos`/`inscrito`/`progresso_pct`, `nivel` inválido) e
`GET /cursos` (participante só vê publicado).
"""

from fastapi import status

from app.api.deps import get_current_user
from app.main import app

_LIMITE = 200


def _como(usuario):
    """Troca o usuário autenticado nas rotas que usam get_current_user."""
    app.dependency_overrides[get_current_user] = lambda: usuario


async def _criar_trilha(client, titulo, *, publicada=True, nivel="iniciante", carga=None):
    r = await client.post(
        "/api/v1/trilhas",
        json={
            "titulo": titulo,
            "nivel": nivel,
            "carga_horaria_total": carga,
            "publicada": publicada,
        },
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def _criar_curso(client, titulo, *, publicado=True, trilha_id=None):
    r = await client.post(
        "/api/v1/cursos",
        json={"titulo": titulo, "publicado": publicado, "trilha_id": trilha_id},
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def test_participante_nao_recebe_rascunho(client, participante_user):
    publicada = await _criar_trilha(client, "Publicada", publicada=True)
    await _criar_trilha(client, "Rascunho", publicada=False)

    _como(participante_user)

    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE})
    assert r.status_code == status.HTTP_200_OK, r.text
    ids = [item["id"] for item in r.json()]
    assert ids == [publicada]
    assert r.headers["x-total-count"] == "1"

    # Nem pedindo publicada=false o rascunho aparece.
    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "publicada": "false"})
    assert [item["id"] for item in r.json()] == [publicada]
    assert r.headers["x-total-count"] == "1"


async def test_admin_consegue_pedir_rascunho(client):
    await _criar_trilha(client, "Pub", publicada=True)
    rascunho = await _criar_trilha(client, "Rasc", publicada=False)

    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "publicada": "false"})
    assert [item["id"] for item in r.json()] == [rascunho]


async def test_ordem_estavel_e_ordenar(client):
    for titulo in ["B", "A", "C"]:
        await _criar_trilha(client, titulo)

    primeira = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "ordenar": "titulo"})
    segunda = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "ordenar": "titulo"})
    titulos = [item["titulo"] for item in primeira.json()]
    assert titulos == ["A", "B", "C"], titulos
    assert titulos == [item["titulo"] for item in segunda.json()]

    desc = await client.get(
        "/api/v1/trilhas", params={"limit": _LIMITE, "ordenar": "titulo", "direcao": "desc"}
    )
    assert [item["titulo"] for item in desc.json()] == ["C", "B", "A"]


async def test_ordenar_invalido_422(client):
    r = await client.get("/api/v1/trilhas", params={"ordenar": "qualquer"})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_nivel_invalido_422(client):
    r = await client.get("/api/v1/trilhas", params={"nivel": "expert"})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    r = await client.post("/api/v1/trilhas", json={"titulo": "X", "nivel": "expert"})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_inscrito_e_campos_do_cartao(client, participante_user):
    trilha_id = await _criar_trilha(client, "Com curso")
    await _criar_curso(client, "Curso 1", trilha_id=trilha_id)

    _como(participante_user)

    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE})
    item = next(i for i in r.json() if i["id"] == trilha_id)
    assert item["total_cursos"] == 1
    assert item["inscrito"] is False
    assert item["progresso_pct"] is None

    r = await client.post(f"/api/v1/trilhas/{trilha_id}/inscrever")
    assert r.status_code == status.HTTP_201_CREATED, r.text

    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "inscrito": "true"})
    assert [i["id"] for i in r.json()] == [trilha_id]
    assert r.json()[0]["inscrito"] is True
    assert r.json()[0]["progresso_pct"] == 0.0
    assert r.headers["x-total-count"] == "1"

    r = await client.get("/api/v1/trilhas", params={"limit": _LIMITE, "inscrito": "false"})
    assert r.json() == []
    assert r.headers["x-total-count"] == "0"


async def test_skip_alem_do_total_mantem_contagem(client):
    await _criar_trilha(client, "Unica")

    r = await client.get("/api/v1/trilhas", params={"skip": 999, "limit": _LIMITE})
    assert r.status_code == status.HTTP_200_OK
    assert r.json() == []
    assert r.headers["x-total-count"] == "1"


async def test_cursos_participante_so_ve_publicado(client, participante_user, admin_user):
    publicado = await _criar_curso(client, "Publicado", publicado=True)
    await _criar_curso(client, "Rascunho", publicado=False)

    _como(participante_user)

    r = await client.get("/api/v1/cursos", params={"limit": _LIMITE})
    assert [item["id"] for item in r.json()] == [publicado]
    assert r.headers["x-total-count"] == "1"

    # admin continua vendo os dois
    _como(admin_user)
    r = await client.get("/api/v1/cursos", params={"limit": _LIMITE})
    assert len(r.json()) == 2
