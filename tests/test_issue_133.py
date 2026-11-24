"""Issue #133 — capa do video.

Coluna `capa_url` (migration), `capa_acesso` computado, `POST/DELETE
/conteudos/{id}/capa` (video, JPEG/PNG/WebP, 5MB) e o campo repetido no
dicionario do `/consumo`.
"""

from fastapi import status

_PNG = ("capa.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")


async def _conteudo(client, *, tipo="video", unidade_id=None) -> int:
    r = await client.post(
        "/api/v1/conteudos",
        json={
            "unidade_id": unidade_id,
            "tipo_midia": tipo,
            "titulo": f"Conteudo {tipo}",
            "url_arquivo": "https://exemplo/a.mp4" if tipo == "video" else "https://exemplo/a.pdf",
            "ordem": 0,
        },
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def test_envia_capa_em_conteudo_de_video(client):
    conteudo_id = await _conteudo(client)

    r = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})

    assert r.status_code == status.HTTP_200_OK, r.text
    corpo = r.json()
    assert corpo["capa_url"], corpo
    assert corpo["capa_acesso"], corpo

    await client.delete(f"/api/v1/conteudos/{conteudo_id}/capa")


async def test_capa_recusada_em_conteudo_que_nao_e_video(client):
    conteudo_id = await _conteudo(client, tipo="pdf")

    r = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text


async def test_capa_recusada_para_tipo_de_arquivo_invalido(client):
    conteudo_id = await _conteudo(client)

    r = await client.post(
        f"/api/v1/conteudos/{conteudo_id}/capa",
        files={"arquivo": ("a.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text


async def test_capa_acima_de_5mb_recusada(client):
    conteudo_id = await _conteudo(client)
    grande = ("grande.png", b"0" * (6 * 1024 * 1024), "image/png")

    r = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": grande})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, r.text


async def test_substituir_capa_troca_a_url(client):
    conteudo_id = await _conteudo(client)

    primeira = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})
    segunda = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})

    assert primeira.status_code == 200, primeira.text
    assert segunda.status_code == 200, segunda.text
    assert primeira.json()["capa_url"] != segunda.json()["capa_url"]


async def test_remove_capa(client):
    conteudo_id = await _conteudo(client)
    await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})

    r = await client.delete(f"/api/v1/conteudos/{conteudo_id}/capa")
    assert r.status_code == status.HTTP_204_NO_CONTENT, r.text

    r = await client.get(f"/api/v1/conteudos/{conteudo_id}")
    assert r.json()["capa_url"] is None
    assert r.json()["capa_acesso"] is None


async def test_capa_aparece_no_consumo(client):
    r = await client.post("/api/v1/cursos", json={"titulo": "Curso 133", "ordem": 0})
    curso_id = r.json()["id"]
    r = await client.post(
        "/api/v1/cursos/modulos", json={"curso_id": curso_id, "titulo": "M", "ordem": 0}
    )
    modulo_id = r.json()["id"]
    r = await client.post(
        "/api/v1/cursos/unidades",
        json={"modulo_id": modulo_id, "titulo": "U", "tipo": "conteudo", "ordem": 0},
    )
    unidade_id = r.json()["id"]
    conteudo_id = await _conteudo(client, unidade_id=unidade_id)

    capa = await client.post(f"/api/v1/conteudos/{conteudo_id}/capa", files={"arquivo": _PNG})
    assert capa.status_code == 200, capa.text
    esperado = capa.json()["capa_url"]

    r = await client.get(f"/api/v1/cursos/{curso_id}/consumo")
    assert r.status_code == status.HTTP_200_OK, r.text
    conteudos = r.json()["modulos"][0]["unidades"][0]["conteudos"]
    item = next(c for c in conteudos if c["id"] == conteudo_id)
    assert item["capa_url"] == esperado
    assert item["capa_acesso"]
