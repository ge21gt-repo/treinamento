import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.certificado import Certificado
from app.models.curso import (
    AulaSincrona,
    Curso,
    Inscricao,
    InscricaoTrilha,
    MensagemCurso,
    Modulo,
    PresencaAula,
    ProgressoUnidade,
    TrilhaAprendizagem,
    Unidade,
)
from app.models.avaliacao import ResultadoAvaliacao
from app.models.gamificacao import Nivel, PontosXP
from app.models.log import LogAcesso, MetricaEngajamento
from app.models.sessao import SessaoAoVivo
from app.models.usuario import Usuario
from app.schemas.log import LogAcessoRead, MetricaEngajamentoRead
from app.services.paginacao import count_query
from app.services.rbac import Permissoes

router = APIRouter(prefix="/dashboard", tags=["Dashboard e Analytics"])


@router.get("/resumo")
async def resumo_geral(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_RESUMO)),
):
    total_usuarios = (await db.execute(select(func.count(Usuario.id)))).scalar()
    total_cursos = (await db.execute(select(func.count(Curso.id)))).scalar()
    total_trilhas = (await db.execute(select(func.count(TrilhaAprendizagem.id)))).scalar()
    total_inscricoes = (await db.execute(select(func.count(Inscricao.id)))).scalar()
    total_certificados = (await db.execute(select(func.count(Certificado.id)))).scalar()
    total_sessoes = (await db.execute(select(func.count(SessaoAoVivo.id)))).scalar()
    return {
        "total_usuarios": total_usuarios,
        "total_cursos": total_cursos,
        "total_trilhas": total_trilhas,
        "total_inscricoes": total_inscricoes,
        "total_certificados": total_certificados,
        "total_sessoes_ao_vivo": total_sessoes,
    }


@router.get("/meu-progresso")
async def meu_progresso(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    inscricoes = await db.execute(
        select(Inscricao).where(Inscricao.usuario_id == current_user.id).order_by(Inscricao.data_inscricao.desc())
    )
    cursos_list = []
    total_horas = 0
    for i in inscricoes.scalars().all():
        curso = await db.execute(select(Curso).where(Curso.id == i.curso_id))
        c = curso.scalar_one_or_none()
        if c:
            cursos_list.append(
                {
                    "curso_id": i.curso_id,
                    "titulo": c.titulo,
                    "status": i.status,
                    "progresso_pct": float(i.progresso_pct),
                    "data_inscricao": i.data_inscricao.isoformat(),
                    "data_conclusao": i.data_conclusao.isoformat() if i.data_conclusao else None,
                    "nota_final": float(i.nota_final) if i.nota_final else None,
                }
            )
            if i.status == "concluido" and c.carga_horaria:
                total_horas += c.carga_horaria

    certificados = await db.execute(select(func.count(Certificado.id)).where(Certificado.usuario_id == current_user.id))
    total_certificados = certificados.scalar() or 0

    xp = await db.execute(
        select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(PontosXP.usuario_id == current_user.id)
    )
    total_xp = xp.scalar() or 0

    niveis = await db.execute(select(Nivel).order_by(Nivel.xp_minimo.desc()))
    nivel_atual = "Iniciante"
    for n in niveis.scalars().all():
        if total_xp >= n.xp_minimo:
            nivel_atual = n.nome
            break

    ultimos_acessos = await db.execute(
        select(LogAcesso).where(LogAcesso.usuario_id == current_user.id).order_by(LogAcesso.criado_em.desc()).limit(5)
    )

    return {
        "usuario_id": str(current_user.id),
        "nome": current_user.nome_completo,
        "cursos": cursos_list,
        "total_cursos_inscritos": len(cursos_list),
        "total_cursos_concluidos": sum(1 for c in cursos_list if c["status"] == "concluido"),
        "total_horas_cursadas": total_horas,
        "total_certificados": total_certificados,
        "xp_total": total_xp,
        "nivel": nivel_atual,
        "ultimos_acessos": [{"data": la.criado_em.isoformat(), "ip": la.ip_address} for la in ultimos_acessos.scalars().all()],
    }


@router.get("/metricas/{usuario_id}", response_model=list[MetricaEngajamentoRead])
async def metricas_usuario(
    usuario_id: uuid.UUID,
    limit: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_METRICAS)),
):
    result = await db.execute(
        select(MetricaEngajamento)
        .where(MetricaEngajamento.usuario_id == usuario_id)
        .order_by(MetricaEngajamento.data_referencia.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/metricas/{usuario_id}/totais")
async def metricas_totais(
    usuario_id: uuid.UUID,
    de: datetime | None = Query(None, description="Inicio do periodo (ISO)"),
    ate: datetime | None = Query(None, description="Fim do periodo (ISO)"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_METRICAS)),
):
    """Totais de engajamento calculados na hora (issue #98).

    Conta nas tabelas de origem (ProgressoUnidade, ResultadoAvaliacao,
    MensagemCurso, PresencaAula, PontosXP) com periodo `de`/`ate` — sem
    depender do consolidado diario. Sem `de`/`ate`, o periodo inteiro.
    """
    inicio = de or datetime.min.replace(tzinfo=timezone.utc)
    fim = ate or datetime.now(timezone.utc)

    conteudos = (
        await db.execute(
            select(func.count(ProgressoUnidade.id)).where(
                ProgressoUnidade.usuario_id == usuario_id,
                ProgressoUnidade.concluido_em >= inicio,
                ProgressoUnidade.concluido_em <= fim,
            )
        )
    ).scalar() or 0

    avaliacoes = (
        await db.execute(
            select(func.count(ResultadoAvaliacao.id)).where(
                ResultadoAvaliacao.usuario_id == usuario_id,
                ResultadoAvaliacao.realizado_em >= inicio,
                ResultadoAvaliacao.realizado_em <= fim,
            )
        )
    ).scalar() or 0

    mensagens = (
        await db.execute(
            select(func.count(MensagemCurso.id)).where(
                MensagemCurso.usuario_id == usuario_id,
                MensagemCurso.criado_em >= inicio,
                MensagemCurso.criado_em <= fim,
            )
        )
    ).scalar() or 0

    sessoes = (
        await db.execute(
            select(func.count(PresencaAula.id)).where(
                PresencaAula.usuario_id == usuario_id,
                PresencaAula.hora_entrada >= inicio,
                PresencaAula.hora_entrada <= fim,
            )
        )
    ).scalar() or 0

    xp = (
        await db.execute(
            select(func.coalesce(func.sum(PontosXP.quantidade), 0)).where(
                PontosXP.usuario_id == usuario_id,
                PontosXP.criado_em >= inicio,
                PontosXP.criado_em <= fim,
            )
        )
    ).scalar() or 0

    return {
        "usuario_id": str(usuario_id),
        "de": inicio.isoformat(),
        "ate": fim.isoformat(),
        "conteudos_acessados": conteudos,
        "avaliacoes_realizadas": avaliacoes,
        "mensagens_enviadas": mensagens,
        "sessoes_assistidas": sessoes,
        "xp_ganho": xp,
    }


@router.get("/relatorios/conteudos-acessados")
async def relatorio_conteudos_acessados(
    usuario_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_RELATORIOS)),
):
    """Conteudos (unidades) acessados por um usuario entre cursos (issue #77).

    Lista as unidades com progresso registrado (nao_iniciado/excluido), com o
    titulo do curso, modulo e unidade, para o card 'Conteudos acessados' do
    relatorio por aluno. Ordenado pela data de conclusao mais recente.
    """
    query = (
        select(Unidade, Modulo, Curso, ProgressoUnidade)
        .join(Modulo, Modulo.id == Unidade.modulo_id)
        .join(Curso, Curso.id == Modulo.curso_id)
        .join(ProgressoUnidade, ProgressoUnidade.unidade_id == Unidade.id)
        .where(ProgressoUnidade.usuario_id == usuario_id)
        .order_by(ProgressoUnidade.concluido_em.desc().nullslast())
    )
    total = await count_query(db, query)
    result = await db.execute(query.offset(skip).limit(limit))
    linhas = result.all()
    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "curso_id": curso.id,
            "curso": curso.titulo,
            "modulo_id": modulo.id,
            "modulo": modulo.titulo,
            "unidade_id": unidade.id,
            "unidade": unidade.titulo,
            "tipo": unidade.tipo,
            "status": progresso.status,
            "tempo_gasto": progresso.tempo_gasto,
            "concluido_em": progresso.concluido_em.isoformat() if progresso.concluido_em else None,
        }
        for unidade, modulo, curso, progresso in linhas
    ]


@router.post("/metricas/coletar")
async def coletar_metricas_manual(
    dias: int = Query(1, ge=1, le=90, description="Quantos dias retroativos coletar"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_METRICAS)),
):
    """Coleta manual das metricas de engajamento (T-16.1). Executa o backlog."""
    from app.services.analytics import coletar_backlog

    total = await coletar_backlog(db, dias)
    await db.commit()
    return {"usuarios_agregados": total, "dias_coletados": dias}


@router.get("/logs", response_model=list[LogAcessoRead])
async def listar_logs(
    usuario_id: uuid.UUID | None = None,
    acao: str | None = Query(None, description="Filtra por acao (ex: login)"),
    data_inicio: datetime | None = Query(None, description="Filtra a partir desta data (ISO)"),
    data_fim: datetime | None = Query(None, description="Filtra ate esta data (ISO)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_LOGS)),
):
    query = select(LogAcesso)
    if usuario_id is not None:
        query = query.where(LogAcesso.usuario_id == usuario_id)
    if acao is not None:
        query = query.where(LogAcesso.acao == acao)
    if data_inicio is not None:
        query = query.where(LogAcesso.criado_em >= data_inicio)
    if data_fim is not None:
        query = query.where(LogAcesso.criado_em <= data_fim)
    total = await count_query(db, query)
    result = await db.execute(query.order_by(LogAcesso.criado_em.desc()).offset(skip).limit(limit))
    items = result.scalars().all()
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/relatorios/presenca")
async def relatorio_presenca_consolidado(
    data_inicio: datetime | None = Query(None),
    data_fim: datetime | None = Query(None),
    curso_id: int | None = Query(None),
    trilha_id: int | None = Query(None, description="Filtra por trilha (issue #79)"),
    formato: str = Query("json", pattern="^(json|csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_RELATORIOS)),
):
    """Relatorio de presenca consolidado por periodo (T-16.5)."""
    filtro = []
    if data_inicio is not None:
        filtro.append(PresencaAula.hora_entrada >= data_inicio)
    if data_fim is not None:
        filtro.append(PresencaAula.hora_entrada <= data_fim)

    query = select(
        AulaSincrona.id.label("aula_id"),
        AulaSincrona.titulo.label("aula"),
        AulaSincrona.curso_id,
        func.count(PresencaAula.id).label("total_presencas"),
        func.count(PresencaAula.id).filter(PresencaAula.presente.is_(True)).label("presentes"),
    ).join(PresencaAula, PresencaAula.aula_id == AulaSincrona.id)
    if curso_id is not None:
        query = query.where(AulaSincrona.curso_id == curso_id)
    if trilha_id is not None:
        query = query.join(Curso, Curso.id == AulaSincrona.curso_id).where(Curso.trilha_id == trilha_id)
    linhas = await db.execute(
        query.where(*filtro).group_by(AulaSincrona.id).order_by(AulaSincrona.id)
    )
    aulas = []
    total_presencas = 0
    total_presentes = 0
    for row in linhas.all():
        total_presencas += row.total_presencas or 0
        total_presentes += row.presentes or 0
        aulas.append(
            {
                "aula_id": row.aula_id,
                "aula": row.aula,
                "curso_id": row.curso_id,
                "total_presencas": row.total_presencas or 0,
                "presentes": row.presentes or 0,
            }
        )
    if formato == "csv":
        return _csv_stream(["aula_id", "aula", "curso_id", "total_presencas", "presentes"], aulas)
    if formato == "pdf":
        return _pdf_simples("Presenca Consolidada", ["aula", "total_presencas", "presentes"], aulas)
    return {
        "data_inicio": data_inicio.isoformat() if data_inicio else None,
        "data_fim": data_fim.isoformat() if data_fim else None,
        "aulas": aulas,
        "resumo": {"total_aulas": len(aulas), "total_presencas": total_presencas, "total_presentes": total_presentes},
    }


def _csv_stream(colunas: list[str], linhas: list[dict]) -> StreamingResponse:
    """Gera CSV em streaming (T-16.6)."""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=colunas, extrasaction='ignore')
    writer.writeheader()
    for linha in linhas:
        writer.writerow(linha)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")


def _pdf_simples(titulo: str, colunas: list[str], linhas: list[dict]) -> StreamingResponse:
    """Gera PDF simples em streaming via reportlab (T-16.6)."""
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    estilos = getSampleStyleSheet()
    elementos = [Paragraph(titulo, estilos["Title"])]
    dados = [colunas] + [[str(linha.get(c, "")) for c in colunas] for linha in linhas]
    tabela = Table(dados)
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    elementos.append(tabela)
    doc.build(elementos)
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/pdf")


@router.get("/relatorios/desempenho")
async def relatorio_desempenho(
    curso_id: int | None = Query(None, description="Filtra por curso"),
    trilha_id: int | None = Query(None, description="Filtra por trilha"),
    ativo: bool | None = Query(None, description="Filtra cursos ativos (publicados) ou inativos (issue #93)"),
    data_inicio: datetime | None = Query(None),
    data_fim: datetime | None = Query(None),
    formato: str = Query("json", pattern="^(json|csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_RELATORIOS)),
):
    """Relatorio de desempenho por curso ou trilha (T-16.4), com status ativo/inativo (issue #93)."""
    if curso_id is None and trilha_id is None:
        raise HTTPException(status_code=400, detail="Informe curso_id ou trilha_id")

    filtro = []
    if curso_id is not None:
        filtro.append(Inscricao.curso_id == curso_id)
    if trilha_id is not None:
        filtro.append(Curso.trilha_id == trilha_id)
    if ativo is not None:
        filtro.append(Curso.publicado.is_(ativo))
    if data_inicio is not None:
        filtro.append(Inscricao.data_inscricao >= data_inicio)
    if data_fim is not None:
        filtro.append(Inscricao.data_inscricao <= data_fim)

    linhas = await db.execute(
        select(
            Curso.id.label("curso_id"),
            Curso.titulo.label("curso"),
            Curso.trilha_id,
            Curso.publicado.label("ativo"),
            func.count(Inscricao.id).label("inscritos"),
            func.count(Inscricao.id).filter(Inscricao.status == "concluido").label("concluidos"),
            func.avg(Inscricao.nota_final).filter(Inscricao.nota_final.isnot(None)).label("nota_media"),
        )
        .outerjoin(Inscricao, Inscricao.curso_id == Curso.id)
        .where(*filtro)
        .group_by(Curso.id)
        .order_by(Curso.id)
    )
    cursos = []
    for row in linhas.all():
        inscritos = row.inscritos or 0
        concluidos = row.concluidos or 0
        cursos.append(
            {
                "curso_id": row.curso_id,
                "curso": row.curso,
                "trilha_id": row.trilha_id,
                "ativo": bool(row.ativo),
                "inscritos": inscritos,
                "concluidos": concluidos,
                "evasao_pct": round((inscritos - concluidos) / inscritos * 100, 2) if inscritos else 0.0,
                "taxa_conclusao_pct": round(concluidos / inscritos * 100, 2) if inscritos else 0.0,
                "nota_media": float(row.nota_media) if row.nota_media is not None else None,
            }
        )

    trilha = None
    if trilha_id is not None:
        t = await db.execute(select(TrilhaAprendizagem).where(TrilhaAprendizagem.id == trilha_id))
        t_obj = t.scalar_one_or_none()
        if t_obj:
            insc_trilha = await db.execute(
                select(func.count(InscricaoTrilha.id)).where(
                    InscricaoTrilha.trilha_id == trilha_id,
                    InscricaoTrilha.status == "concluido",
                )
            )
            trilha = {
                "trilha_id": t_obj.id,
                "titulo": t_obj.titulo,
                "cursos": len(cursos),
                "concluidas": insc_trilha.scalar() or 0,
            }

    if formato == "csv":
        return _csv_stream(
            ["curso_id", "curso", "ativo", "inscritos", "concluidos", "evasao_pct", "taxa_conclusao_pct", "nota_media"],
            cursos,
        )
    if formato == "pdf":
        return _pdf_simples(
            "Desempenho por Curso",
            ["curso", "ativo", "inscritos", "concluidos", "evasao_pct", "taxa_conclusao_pct", "nota_media"],
            cursos,
        )
    return {"cursos": cursos, "trilha": trilha}


@router.get("/relatorios/acessos")
async def relatorio_acessos_plataforma(
    data_inicio: datetime | None = Query(None),
    data_fim: datetime | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    formato: str = Query("json", pattern="^(json|csv|pdf)$"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_RELATORIOS)),
):
    """Relatorio de quem acessou a plataforma, agregado por usuario (issue #93).

    Agrupa `lms.log_acesso` por usuario: total de acessos, ultimo acesso e
    acao mais recente. Complementa o `GET /dashboard/logs` (log cru) com uma
    visao consolidada para o gestor.
    """
    filtro = []
    if data_inicio is not None:
        filtro.append(LogAcesso.criado_em >= data_inicio)
    if data_fim is not None:
        filtro.append(LogAcesso.criado_em <= data_fim)

    base = (
        select(LogAcesso.usuario_id, func.count(LogAcesso.id).label("total_acessos"),
               func.max(LogAcesso.criado_em).label("ultimo_acesso"))
        .where(*filtro)
        .group_by(LogAcesso.usuario_id)
        .subquery()
    )
    total = await db.execute(
        select(func.count()).select_from(select(base.c.usuario_id).subquery())
    )
    total_acessos = total.scalar() or 0

    linhas = await db.execute(
        select(
            base.c.usuario_id.label("usuario_id"),
            Usuario.nome_completo.label("nome"),
            Usuario.email.label("email"),
            base.c.total_acessos,
            base.c.ultimo_acesso,
        )
        .join(Usuario, Usuario.id == base.c.usuario_id)
        .order_by(base.c.total_acessos.desc())
        .offset(skip)
        .limit(limit)
    )
    itens = [
        {
            "usuario_id": str(r.usuario_id),
            "nome": r.nome,
            "email": r.email,
            "total_acessos": r.total_acessos,
            "ultimo_acesso": r.ultimo_acesso.isoformat() if r.ultimo_acesso else None,
        }
        for r in linhas.all()
    ]
    response.headers["X-Total-Count"] = str(total_acessos)

    if formato == "csv":
        return _csv_stream(
            ["usuario_id", "nome", "email", "total_acessos", "ultimo_acesso"], itens
        )
    if formato == "pdf":
        return _pdf_simples(
            "Acessos a Plataforma",
            ["nome", "email", "total_acessos", "ultimo_acesso"], itens
        )
    return {
        "data_inicio": data_inicio.isoformat() if data_inicio else None,
        "data_fim": data_fim.isoformat() if data_fim else None,
        "total_usuarios": total_acessos,
        "acessos": itens,
    }


@router.get("/graficos/temporal")
async def grafico_temporal(
    periodo: str = Query("semana", pattern="^(dia|semana|mes)$", description="Agregacao temporal"),
    data_inicio: datetime | None = Query(None),
    data_fim: datetime | None = Query(None),
    curso_id: int | None = Query(None),
    trilha_id: int | None = Query(None, description="Filtra por trilha (issue #79)"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_GRAFICOS)),
):
    """Series temporais de acesso e participacao (T-16.3)."""
    agora = datetime.now(timezone.utc)
    if data_fim is None:
        data_fim = agora
    if data_inicio is None:
        if periodo == "dia":
            data_inicio = data_fim - timedelta(days=7)
        elif periodo == "mes":
            data_inicio = data_fim - timedelta(days=180)
        else:
            data_inicio = data_fim - timedelta(days=30)

    expr = func.date_trunc("day", LogAcesso.criado_em)
    if periodo == "semana":
        expr = func.date_trunc("week", LogAcesso.criado_em)
    elif periodo == "mes":
        expr = func.date_trunc("month", LogAcesso.criado_em)

    # Issue #97: quando ha curso_id/trilha_id, a serie "acessos" nao deve mostrar
    # o total da plataforma inteira. log_acesso nao guarda curso/trilha, entao
    # passamos a contar ATIVIDADE real do recorte (progresso de unidade +
    # mensagens do curso + presencas), via modulos.curso_id. Sem filtro, mantem
    # o log_acesso normal (acessos reais).
    if curso_id is not None or trilha_id is not None:
        curso_filtro = []
        if curso_id is not None:
            curso_filtro.append(Modulo.curso_id == curso_id)
        if trilha_id is not None:
            curso_filtro.append(Curso.trilha_id == trilha_id)

        # Cada fonte tem a propria coluna de data, entao o bucket sai da propria tabela (correcao do dev, issue #97)
        trunc = {"dia": "day", "semana": "week", "mes": "month"}[periodo]
        recorte = []
        if curso_id is not None:
            recorte.append(Curso.id == curso_id)
        if trilha_id is not None:
            recorte.append(Curso.trilha_id == trilha_id)

        b1 = func.date_trunc(trunc, ProgressoUnidade.concluido_em)
        q1 = (
            select(b1.label("bucket"), func.count(ProgressoUnidade.id).label("total"))
            .join(Unidade, Unidade.id == ProgressoUnidade.unidade_id)
            .join(Modulo, Modulo.id == Unidade.modulo_id)
            .join(Curso, Curso.id == Modulo.curso_id)
            .where(ProgressoUnidade.concluido_em >= data_inicio, ProgressoUnidade.concluido_em <= data_fim, *recorte)
            .group_by(b1)
        )
        b2 = func.date_trunc(trunc, MensagemCurso.criado_em)
        q2 = (
            select(b2.label("bucket"), func.count(MensagemCurso.id).label("total"))
            .join(Curso, Curso.id == MensagemCurso.curso_id)
            .where(MensagemCurso.criado_em >= data_inicio, MensagemCurso.criado_em <= data_fim, *recorte)
            .group_by(b2)
        )
        b3 = func.date_trunc(trunc, PresencaAula.hora_entrada)
        q3 = (
            select(b3.label("bucket"), func.count(PresencaAula.id).label("total"))
            .join(AulaSincrona, AulaSincrona.id == PresencaAula.aula_id)
            .join(Curso, Curso.id == AulaSincrona.curso_id)
            .where(PresencaAula.hora_entrada >= data_inicio, PresencaAula.hora_entrada <= data_fim, *recorte)
            .group_by(b3)
        )
        fontes = union_all(q1, q2, q3).subquery()
        acessos = await db.execute(
            select(fontes.c.bucket, func.sum(fontes.c.total)).group_by(fontes.c.bucket).order_by(fontes.c.bucket)
        )
        serie_acessos = [{"bucket": b.isoformat(), "total": int(t)} for b, t in acessos.all()]
    else:
        acessos = await db.execute(
            select(expr.label("bucket"), func.count(LogAcesso.id))
            .where(LogAcesso.criado_em >= data_inicio, LogAcesso.criado_em <= data_fim)
            .group_by(expr)
            .order_by(expr)
        )
        serie_acessos = [{"bucket": b.isoformat(), "total": t} for b, t in acessos.all()]

    expr_insc = func.date_trunc("day", Inscricao.data_inscricao)
    if periodo == "semana":
        expr_insc = func.date_trunc("week", Inscricao.data_inscricao)
    elif periodo == "mes":
        expr_insc = func.date_trunc("month", Inscricao.data_inscricao)
    insc_query = select(expr_insc.label("bucket"), func.count(Inscricao.id)).where(
        Inscricao.data_inscricao >= data_inicio, Inscricao.data_inscricao <= data_fim
    )
    if curso_id is not None:
        insc_query = insc_query.where(Inscricao.curso_id == curso_id)
    if trilha_id is not None:
        insc_query = insc_query.join(Curso, Curso.id == Inscricao.curso_id).where(Curso.trilha_id == trilha_id)
    inscricoes = await db.execute(insc_query.group_by(expr_insc).order_by(expr_insc))
    serie_inscricoes = [{"bucket": b.isoformat(), "total": t} for b, t in inscricoes.all()]

    return {
        "periodo": periodo,
        "data_inicio": data_inicio.isoformat(),
        "data_fim": data_fim.isoformat(),
        "acessos": serie_acessos,
        "inscricoes": serie_inscricoes,
    }


@router.get("/kpis")
async def kpis_dashboard(
    data_inicio: datetime | None = Query(None, description="Filtra a partir desta data (ISO)"),
    data_fim: datetime | None = Query(None, description="Filtra ate esta data (ISO)"),
    curso_id: int | None = Query(None, description="Restringe a um curso"),
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_KPIS)),
):
    """KPIs do dashboard principal (T-16.2): inscritos, concluidos, evasao, taxa, nota media."""
    filtro_insc = []
    if curso_id is not None:
        filtro_insc.append(Inscricao.curso_id == curso_id)
    if data_inicio is not None:
        filtro_insc.append(Inscricao.data_inscricao >= data_inicio)
    if data_fim is not None:
        filtro_insc.append(Inscricao.data_inscricao <= data_fim)

    total_inscritos = (
        await db.execute(select(func.count(Inscricao.id)).where(*filtro_insc))
    ).scalar() or 0

    filtro_concluidos = list(filtro_insc) + [Inscricao.status == "concluido"]
    total_concluidos = (
        await db.execute(select(func.count(Inscricao.id)).where(*filtro_concluidos))
    ).scalar() or 0

    nota_media = (
        await db.execute(
            select(func.avg(Inscricao.nota_final)).where(*filtro_concluidos, Inscricao.nota_final.isnot(None))
        )
    ).scalar()

    evasao_pct = round((total_inscritos - total_concluidos) / total_inscritos * 100, 2) if total_inscritos else 0.0
    taxa_conclusao = round(total_concluidos / total_inscritos * 100, 2) if total_inscritos else 0.0

    return {
        "total_inscritos": total_inscritos,
        "total_concluidos": total_concluidos,
        "evasao_pct": evasao_pct,
        "taxa_conclusao_pct": taxa_conclusao,
        "nota_media": float(nota_media) if nota_media is not None else None,
    }


@router.get("/cursos/{curso_id}/stats")
async def stats_curso(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.DASHBOARD_STATS)),
):
    total_inscritos = (
        await db.execute(select(func.count(Inscricao.id)).where(Inscricao.curso_id == curso_id))
    ).scalar()
    concluidos = (
        await db.execute(
            select(func.count(Inscricao.id)).where(Inscricao.curso_id == curso_id, Inscricao.status == "concluido")
        )
    ).scalar()
    nota_media = (
        await db.execute(
            select(func.avg(Inscricao.nota_final)).where(
                Inscricao.curso_id == curso_id, Inscricao.nota_final.isnot(None)
            )
        )
    ).scalar()
    return {
        "curso_id": curso_id,
        "total_inscritos": total_inscritos,
        "total_concluidos": concluidos,
        "nota_media": float(nota_media) if nota_media else None,
        "taxa_conclusao": round((concluidos / total_inscritos * 100), 2) if total_inscritos else 0,
    }
