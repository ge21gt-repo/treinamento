import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.gamificacao import Badge, Missao, Nivel, PontosXP, Streak, UsuarioBadge, UsuarioMissao
from app.models.usuario import Usuario
from app.services.gamificacao import calcular_nivel
from app.services.rbac import Permissoes
from app.schemas.gamificacao import (
    BadgeCreate,
    BadgePerfilRead,
    BadgeRead,
    HistoricoXPRead,
    LeaderboardEntry,
    MissaoCreate,
    MissaoRead,
    MissaoUpdate,
    NivelCreate,
    NivelInfo,
    NivelRead,
    PerfilGamificadoRead,
    PontosXPCreate,
    PontosXPRead,
    ProximoNivelInfo,
    StreakPerfilRead,
    StreakRead,
    UsuarioBadgeCreate,
    UsuarioBadgeRead,
    UsuarioMissaoCreate,
    UsuarioMissaoRead,
    UsuarioMissaoUpdate,
)

router = APIRouter(prefix="/gamificacao", tags=["Gamificacao"])


# --- Niveis ---


@router.get("/niveis", response_model=list[NivelRead])
async def listar_niveis(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Nivel).order_by(Nivel.ordem))
    return result.scalars().all()


@router.post("/niveis", response_model=NivelRead, status_code=status.HTTP_201_CREATED)
async def criar_nivel(
    payload: NivelCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    nivel = Nivel(**payload.model_dump())
    db.add(nivel)
    await db.commit()
    await db.refresh(nivel)
    return nivel


# --- XP ---


@router.post("/xp", response_model=PontosXPRead, status_code=status.HTTP_201_CREATED)
async def adicionar_xp(
    payload: PontosXPCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    pontos = PontosXP(**payload.model_dump())
    db.add(pontos)
    await db.commit()
    await db.refresh(pontos)
    return pontos


@router.get("/xp/{usuario_id}", response_model=list[PontosXPRead])
async def listar_xp_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_LISTAR)),
):
    result = await db.execute(
        select(PontosXP).where(PontosXP.usuario_id == usuario_id).order_by(PontosXP.criado_em.desc())
    )
    return result.scalars().all()


@router.get("/xp/{usuario_id}/total")
async def xp_total_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_LISTAR)),
):
    result = await db.execute(
        select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == usuario_id)
    )
    total = result.scalar()
    nivel_result = await db.execute(select(Nivel).where(Nivel.xp_minimo <= total).order_by(Nivel.ordem.desc()).limit(1))
    nivel = nivel_result.scalar_one_or_none()
    return {"usuario_id": str(usuario_id), "xp_total": total, "nivel": nivel.nome if nivel else "Iniciante"}


# --- Leaderboard ---


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    stmt = (
        select(
            PontosXP.usuario_id,
            Usuario.nome_completo,
            func.coalesce(func.sum(PontosXP.quantidade), 0).label("xp_total"),
        )
        .join(Usuario, Usuario.id == PontosXP.usuario_id)
        .group_by(PontosXP.usuario_id, Usuario.nome_completo)
        .order_by(func.sum(PontosXP.quantidade).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    niveis = await db.execute(select(Nivel).order_by(Nivel.ordem.desc()))
    niveis_list = niveis.scalars().all()

    entries = []
    for row in rows:
        nivel_nome = "Iniciante"
        for n in niveis_list:
            if row.xp_total >= n.xp_minimo:
                nivel_nome = n.nome
                break
        entries.append(
            LeaderboardEntry(
                usuario_id=row.usuario_id,
                nome_completo=row.nome_completo,
                xp_total=row.xp_total,
                nivel=nivel_nome,
            )
        )
    return entries


# --- Perfil ---


@router.get("/perfil", response_model=PerfilGamificadoRead)
async def perfil_gamificado(
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    xp_total = await db.scalar(
        select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == usuario.id)
    ) or 0

    nivel_atual, proximo = await calcular_nivel(db, usuario.id)

    badge_rows = await db.execute(
        select(
            Badge.id,
            Badge.nome,
            Badge.descricao,
            Badge.icone_url,
            UsuarioBadge.conquistado_em,
        )
        .join(UsuarioBadge, UsuarioBadge.badge_id == Badge.id)
        .where(UsuarioBadge.usuario_id == usuario.id)
        .order_by(UsuarioBadge.conquistado_em.desc())
    )
    badges = [
        BadgePerfilRead(
            id=row.id,
            nome=row.nome,
            descricao=row.descricao,
            icone_url=row.icone_url,
            conquistado_em=row.conquistado_em,
        )
        for row in badge_rows
    ]

    streak_row = await db.execute(select(Streak).where(Streak.usuario_id == usuario.id))
    streak = streak_row.scalar_one_or_none()
    streak_data = StreakPerfilRead(
        dias_consecutivos=streak.dias_consecutivos if streak else 0,
        maior_streak=streak.maior_streak if streak else 0,
    )

    historico_rows = await db.execute(
        select(PontosXP)
        .where(PontosXP.usuario_id == usuario.id)
        .order_by(PontosXP.criado_em.desc())
        .limit(10)
    )
    historico = [
        HistoricoXPRead(
            quantidade=h.quantidade,
            origem=h.origem,
            descricao=h.descricao,
            criado_em=h.criado_em,
        )
        for h in historico_rows.scalars()
    ]

    proximo_nivel = None
    if proximo:
        xp_restante = max(0, proximo.xp_minimo - xp_total)
        intervalo = proximo.xp_minimo - nivel_atual.xp_minimo
        progresso_pct = round(min(100, (xp_total - nivel_atual.xp_minimo) / intervalo * 100), 1) if intervalo > 0 else 0
        proximo_nivel = ProximoNivelInfo(
            nome=proximo.nome,
            ordem=proximo.ordem,
            xp_minimo=proximo.xp_minimo,
            xp_restante=xp_restante,
            progresso_pct=progresso_pct,
        )

    return PerfilGamificadoRead(
        usuario_id=usuario.id,
        nome_completo=usuario.nome_completo,
        xp_total=xp_total,
        nivel_atual=NivelInfo(
            nome=nivel_atual.nome,
            ordem=nivel_atual.ordem,
            xp_minimo=nivel_atual.xp_minimo,
            icone_url=nivel_atual.icone_url,
        ),
        proximo_nivel=proximo_nivel,
        badges=badges,
        streak=streak_data,
        historico_recente=historico,
    )


# --- Badges ---


@router.get("/badges", response_model=list[BadgeRead])
async def listar_badges(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Badge).where(Badge.ativo))
    return result.scalars().all()


@router.post("/badges", response_model=BadgeRead, status_code=status.HTTP_201_CREATED)
async def criar_badge(
    payload: BadgeCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    badge = Badge(**payload.model_dump())
    db.add(badge)
    await db.commit()
    await db.refresh(badge)
    return badge


@router.post("/badges/atribuir", response_model=UsuarioBadgeRead, status_code=status.HTTP_201_CREATED)
async def atribuir_badge(
    payload: UsuarioBadgeCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    ub = UsuarioBadge(**payload.model_dump())
    db.add(ub)
    await db.commit()
    await db.refresh(ub)
    return ub


@router.get("/badges/{usuario_id}", response_model=list[UsuarioBadgeRead])
async def badges_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_LISTAR)),
):
    result = await db.execute(select(UsuarioBadge).where(UsuarioBadge.usuario_id == usuario_id))
    return result.scalars().all()


# --- Missoes ---


@router.get("/missoes", response_model=list[MissaoRead])
async def listar_missoes(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Missao).where(Missao.ativa))
    return result.scalars().all()


@router.post("/missoes", response_model=MissaoRead, status_code=status.HTTP_201_CREATED)
async def criar_missao(
    payload: MissaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    missao = Missao(**payload.model_dump())
    db.add(missao)
    await db.commit()
    await db.refresh(missao)
    return missao


@router.patch("/missoes/{missao_id}", response_model=MissaoRead)
async def atualizar_missao(
    missao_id: int,
    payload: MissaoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_EDITAR)),
):
    result = await db.execute(select(Missao).where(Missao.id == missao_id))
    missao = result.scalar_one_or_none()
    if not missao:
        raise HTTPException(status_code=404, detail="Missao nao encontrada")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(missao, field, value)
    await db.commit()
    await db.refresh(missao)
    return missao


@router.post("/missoes/participar", response_model=UsuarioMissaoRead, status_code=status.HTTP_201_CREATED)
async def participar_missao(
    payload: UsuarioMissaoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_CRIAR)),
):
    um = UsuarioMissao(**payload.model_dump())
    db.add(um)
    await db.commit()
    await db.refresh(um)
    return um


@router.patch("/missoes/usuario/{usuario_missao_id}", response_model=UsuarioMissaoRead)
async def atualizar_progresso_missao(
    usuario_missao_id: int,
    payload: UsuarioMissaoUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_EDITAR)),
):
    result = await db.execute(select(UsuarioMissao).where(UsuarioMissao.id == usuario_missao_id))
    um = result.scalar_one_or_none()
    if not um:
        raise HTTPException(status_code=404, detail="Registro nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(um, field, value)
    await db.commit()
    await db.refresh(um)
    return um


# --- Streaks ---


@router.get("/streaks/{usuario_id}", response_model=StreakRead)
async def obter_streak(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.GAMIFICACAO_LISTAR)),
):
    result = await db.execute(select(Streak).where(Streak.usuario_id == usuario_id))
    streak = result.scalar_one_or_none()
    if not streak:
        raise HTTPException(status_code=404, detail="Streak nao encontrado")
    return streak
