import uuid

from app.models.curso import AulaSincrona, MensagemCurso
from app.schemas.curso import (
    AulaSincronaCreate, AulaSincronaRead, AulaSincronaUpdate,
    CursoArvoreRead, CursoArvoreItem, ModuloArvoreRead,
    MensagemCursoCreate, MensagemCursoRead,
    ReorderItem,
)


def test_aula_sincrona_schema_create():
    now = "2026-07-10T14:00:00Z"
    payload = AulaSincronaCreate(
        curso_id=1, titulo="Aula 1", data_hora=now,
        link_externo="https://zoom.us/j/123", duracao_minutos=60,
    )
    assert payload.titulo == "Aula 1"
    assert payload.status == "agendada"


def test_aula_sincrona_schema_update():
    payload = AulaSincronaUpdate(status="encerrada")
    assert payload.status == "encerrada"
    assert payload.titulo is None


def test_aula_sincrona_schema_read():
    now = "2026-07-10T14:00:00Z"
    data = {
        "id": 1, "curso_id": 1, "titulo": "Aula 1",
        "data_hora": now, "status": "agendada",
        "criado_por": None, "criado_em": now,
    }
    obj = AulaSincronaRead(**data)
    assert obj.id == 1
    assert obj.titulo == "Aula 1"


def test_mensagem_curso_schema_create():
    payload = MensagemCursoCreate(texto="Ola pessoal!")
    assert payload.texto == "Ola pessoal!"


def test_mensagem_curso_schema_read():
    data = {
        "id": 1, "curso_id": 1, "usuario_id": str(uuid.uuid4()),
        "texto": "teste", "criado_em": "2026-07-06T12:00:00Z",
    }
    obj = MensagemCursoRead(**data)
    assert obj.texto == "teste"


def test_reorder_item_schema():
    payload = ReorderItem(id=5, ordem=1)
    assert payload.id == 5
    assert payload.ordem == 1


def test_curso_arvore_item_schema():
    item = CursoArvoreItem(id=1, titulo="Intro", tipo="video", ordem=0, conteudo_url="https://exemplo.com/video.mp4")
    assert item.tipo == "video"
    assert item.conteudo_url == "https://exemplo.com/video.mp4"


def test_modulo_arvore_read_schema():
    item = CursoArvoreItem(id=1, titulo="Unid 1", tipo="pdf", ordem=0)
    modulo = ModuloArvoreRead(id=1, titulo="Mod 1", ordem=0, unidades=[item])
    assert len(modulo.unidades) == 1
    assert modulo.unidades[0].tipo == "pdf"


def test_curso_arvore_read_schema():
    item = CursoArvoreItem(id=1, titulo="Unid 1", tipo="pdf", ordem=0)
    modulo = ModuloArvoreRead(id=1, titulo="Mod 1", ordem=0, unidades=[item])
    curso = CursoArvoreRead(id=1, titulo="Curso Teste", modulos=[modulo])
    assert curso.titulo == "Curso Teste"
    assert len(curso.modulos) == 1


def test_aula_sincrona_model_fields():
    assert hasattr(AulaSincrona, "id")
    assert hasattr(AulaSincrona, "curso_id")
    assert hasattr(AulaSincrona, "titulo")
    assert hasattr(AulaSincrona, "data_hora")
    assert hasattr(AulaSincrona, "status")
    assert hasattr(AulaSincrona, "link_externo")
    assert hasattr(AulaSincrona, "criado_por")


def test_mensagem_curso_model_fields():
    assert hasattr(MensagemCurso, "id")
    assert hasattr(MensagemCurso, "curso_id")
    assert hasattr(MensagemCurso, "usuario_id")
    assert hasattr(MensagemCurso, "texto")
    assert hasattr(MensagemCurso, "criado_em")
