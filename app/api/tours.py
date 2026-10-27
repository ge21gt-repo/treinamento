"""Metricas de uso dos tours de ajuda (issue #125).

Duas rotas: o front despeja eventos em lote, e o painel "Uso dos tours" da
pagina Ajuda le o resumo agregado. A tabela nao guarda `usuario_id`, por
decisao de produto da issue - ver o docstring de app/models/tour.py.
"""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_permissao
from app.api.rate_limit import chave_por_token, limiter
from app.models.tour import TourEvento
from app.models.usuario import Usuario
from app.schemas.tour import (
    TourEventosLote,
    TourResumoItem,
    TourResumoRead,
    TourResumoTour,
)
from app.services.rbac import Permissoes

router = APIRouter(prefix="/tours", tags=["Tours de ajuda"])


@router.post("/eventos", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute", key_func=chave_por_token)
async def registrar_eventos(
    request: Request,
    payload: TourEventosLote,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    """Grava um lote de eventos de tour (ate 50 por pedido).

    So exige login, e nao permissao: quem gera o evento e qualquer pessoa que
    use a plataforma. O que a rota NAO grava e o ponto da issue - nem
    `usuario_id`, nem IP, nem user-agent.

    A validacao esta toda no schema, entao um evento invalido no meio do lote
    derruba o pedido inteiro com 422 antes de chegar aqui: ou grava tudo, ou
    nao grava nada.

    O limite e por token, nao por IP como o resto do projeto: atras do ingress
    um predio inteiro divide um IP, e este e o unico endpoint que o front
    chama de poucos em poucos segundos.
    """
    if not payload.eventos:
        return
    db.add_all([TourEvento(**e.model_dump()) for e in payload.eventos])
    await db.commit()


def _periodo(de: date | None, ate: date | None) -> tuple[datetime | None, datetime | None]:
    """Converte as datas em instantes, com `ate` incluindo o dia inteiro.

    Sem isto, `ate=2026-10-27` cortaria tudo o que aconteceu naquele dia depois
    da meia-noite - que e praticamente o dia todo.
    """
    inicio = datetime.combine(de, time.min, tzinfo=timezone.utc) if de else None
    fim = datetime.combine(ate + timedelta(days=1), time.min, tzinfo=timezone.utc) if ate else None
    return inicio, fim


def _acumular(item: TourResumoItem, evento: str, passo: int | None, util: bool | None, quantos: int) -> None:
    """Soma uma linha agregada no item do resumo.

    `passo_visto` entra na tabela mas nao no resumo: a issue nao o pede em
    nenhum dos campos. Fica gravado para quem quiser olhar depois.
    """
    if evento == "convite_exibido":
        item.convites_exibidos += quantos
    elif evento == "convite_adiado":
        item.adiados += quantos
    elif evento == "convite_dispensado":
        item.dispensados += quantos
    elif evento == "tour_iniciado":
        item.iniciados += quantos
    elif evento == "tour_concluido":
        item.concluidos += quantos
    elif evento == "tour_fechado":
        # Chave em texto: JSON nao tem chave inteira, e o front leria "3"
        # de um jeito e 3 de outro dependendo do serializador.
        chave = str(passo) if passo is not None else "desconhecido"
        item.fechados_por_passo[chave] = item.fechados_por_passo.get(chave, 0) + quantos
    elif evento == "tour_util":
        if util is True:
            item.util_sim += quantos
        elif util is False:
            item.util_nao += quantos


@router.get("/resumo", response_model=TourResumoRead)
async def resumo_tours(
    de: date | None = Query(None, description="Primeiro dia considerado (inclusive)"),
    ate: date | None = Query(None, description="Ultimo dia considerado (inclusive)"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.AJUDA_METRICAS)),
):
    """Contagens por tour e, dentro de cada tour, por papel.

    Uma consulta agregada so, agrupando no banco: a tabela cresce rapido e
    trazer linha por linha para contar em Python nao se sustentaria.
    """
    inicio, fim = _periodo(de, ate)

    consulta = select(
        TourEvento.tour_id,
        TourEvento.papel,
        TourEvento.evento,
        TourEvento.passo,
        TourEvento.util,
        func.count().label("quantos"),
    ).group_by(
        TourEvento.tour_id,
        TourEvento.papel,
        TourEvento.evento,
        TourEvento.passo,
        TourEvento.util,
    )
    if inicio is not None:
        consulta = consulta.where(TourEvento.criado_em >= inicio)
    if fim is not None:
        consulta = consulta.where(TourEvento.criado_em < fim)

    linhas = (await db.execute(consulta)).all()

    por_tour: dict[str, TourResumoTour] = {}
    for tour_id, papel, evento, passo, util, quantos in linhas:
        tour = por_tour.get(tour_id)
        if tour is None:
            tour = TourResumoTour(tour_id=tour_id)
            por_tour[tour_id] = tour
        if papel not in tour.por_papel:
            tour.por_papel[papel] = TourResumoItem()
        _acumular(tour, evento, passo, util, quantos)
        _acumular(tour.por_papel[papel], evento, passo, util, quantos)

    return TourResumoRead(
        de=inicio,
        ate=fim,
        tours=sorted(por_tour.values(), key=lambda t: t.tour_id),
    )

