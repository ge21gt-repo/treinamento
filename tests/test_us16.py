"""Testes US-16: dashboards e analytics."""

from datetime import datetime, timedelta, timezone

from fastapi import status

pytestmark = __import__("pytest").mark.db


class TestColetaMetricas:
    """T-16.1 — coleta automatica de metricas de engajamento"""

    async def test_coletar_metricas_diarias(self, client, admin_user):
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.models.gamificacao import PontosXP
        from app.models.log import LogAcesso, MetricaEngajamento
        from app.services.analytics import coletar_metricas_diarias

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        dia = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        data_dia = datetime.combine(dia, datetime.min.time(), tzinfo=timezone.utc)
        try:
            session.add(LogAcesso(usuario_id=admin_user.id, acao="login", ip_address="127.0.0.1", criado_em=data_dia))
            session.add(PontosXP(usuario_id=admin_user.id, quantidade=50, origem="curso_concluido", criado_em=data_dia))
            await session.commit()

            n = await coletar_metricas_diarias(session, dia)
            await session.commit()
            assert n >= 1, "Deve agregar ao menos o admin"

            row = (
                await session.execute(
                    select(MetricaEngajamento).where(
                        MetricaEngajamento.usuario_id == admin_user.id,
                        MetricaEngajamento.data_referencia == dia,
                    )
                )
            ).scalar_one_or_none()
            assert row is not None, "Linha de metrica deve existir"
            assert row.xp_ganho == 50, f"XP do dia deve ser 50, veio {row.xp_ganho}"

            # idempotente: rodar de novo nao duplica
            n2 = await coletar_metricas_diarias(session, dia)
            await session.commit()
            total = (
                await session.execute(
                    select(MetricaEngajamento.id).where(
                        MetricaEngajamento.usuario_id == admin_user.id,
                        MetricaEngajamento.data_referencia == dia,
                    )
                )
            ).scalars().all()
            assert len(total) == 1, "Coleta repetida nao deve duplicar linhas"
        finally:
            await session.close()
            await engine.dispose()

    async def test_endpoint_coletar_manual(self, client, admin_user):
        r = await client.post("/api/v1/dashboard/metricas/coletar?dias=3")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert "usuarios_agregados" in data
        assert data["dias_coletados"] == 3

class TestKPIs:
    """T-16.2 — KPIs do dashboard principal (inscritos, concluidos, evasao)"""

    async def test_kpis_sem_dados(self, client):
        r = await client.get("/api/v1/dashboard/kpis")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        for chave in ("total_inscritos", "total_concluidos", "evasao_pct", "taxa_conclusao_pct", "nota_media"):
            assert chave in data, f"Falta {chave}"
        assert data["total_inscritos"] == 0
        assert data["evasao_pct"] == 0.0

    async def test_kpis_com_inscricoes_e_conclusao(self, client):
        # curso 1: concluido | curso 2: inscrito apenas (evasao)
        ids = []
        for titulo in ("Curso KPI A", "Curso KPI B"):
            r = await client.post("/api/v1/cursos", json={"titulo": titulo, "descricao": "x", "ordem": 0, "publicado": True})
            cid = r.json()["id"]
            r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
            assert r.status_code == status.HTTP_201_CREATED, r.text
            ids.append(cid)

        # concluir o curso A (1 unidade)
        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": ids[0], "titulo": "M", "descricao": "x", "ordem": 0})
        mid = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mid, "titulo": "U", "tipo": "conteudo", "ordem": 0})
        uid = r.json()["id"]
        r = await client.post(f"/api/v1/cursos/unidades/{uid}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get("/api/v1/dashboard/kpis")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["total_inscritos"] == 2
        assert data["total_concluidos"] == 1
        assert data["taxa_conclusao_pct"] == 50.0
        assert data["evasao_pct"] == 50.0

    async def test_kpis_filtro_por_curso(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso KPI Filtro", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.get(f"/api/v1/dashboard/kpis?curso_id={cid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["total_inscritos"] == 1


class TestGraficosTemporal:
    """T-16.3 — series temporais de acesso e participacao"""

    async def test_temporal_sem_dados(self, client):
        r = await client.get("/api/v1/dashboard/graficos/temporal?periodo=dia")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["periodo"] == "dia"
        assert isinstance(data["acessos"], list)
        assert isinstance(data["inscricoes"], list)

    async def test_temporal_com_acessos(self, client, admin_user):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from app.config import settings
        from app.models.log import LogAcesso

        engine = create_async_engine(settings.TEST_DATABASE_URL)
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        session = maker()
        try:
            session.add(LogAcesso(usuario_id=admin_user.id, acao="login", ip_address="127.0.0.1"))
            await session.commit()
        finally:
            await session.close()
            await engine.dispose()

        r = await client.get("/api/v1/dashboard/graficos/temporal?periodo=dia")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert len(data["acessos"]) >= 1, "Deve haver pelo menos 1 bucket de acesso"
        assert sum(b["total"] for b in data["acessos"]) >= 1

    async def test_temporal_periodo_invalido(self, client):
        r = await client.get("/api/v1/dashboard/graficos/temporal?periodo=ano")
        assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestRelatorioDesempenho:
    """T-16.4 — desempenho por curso/trilha"""

    async def test_desempenho_requer_curso_ou_trilha(self, client):
        r = await client.get("/api/v1/dashboard/relatorios/desempenho")
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    async def test_desempenho_por_curso(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Desempenho", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.post("/api/v1/cursos/modulos", json={"curso_id": cid, "titulo": "M", "descricao": "x", "ordem": 0})
        mid = r.json()["id"]
        r = await client.post("/api/v1/cursos/unidades", json={"modulo_id": mid, "titulo": "U", "tipo": "conteudo", "ordem": 0})
        uid = r.json()["id"]
        r = await client.post(f"/api/v1/cursos/unidades/{uid}/concluir")
        assert r.status_code == status.HTTP_200_OK, r.text

        r = await client.get(f"/api/v1/dashboard/relatorios/desempenho?curso_id={cid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert len(data["cursos"]) == 1
        curso = data["cursos"][0]
        assert curso["inscritos"] == 1
        assert curso["concluidos"] == 1
        assert curso["taxa_conclusao_pct"] == 100.0

    async def test_desempenho_por_trilha(self, client):
        r = await client.post("/api/v1/trilhas", json={"titulo": "Trilha Desempenho", "descricao": "x", "nivel": "iniciante", "publicada": True})
        tid = r.json()["id"]
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso da Trilha", "descricao": "x", "ordem": 0, "trilha_id": tid, "publicado": True})
        cid = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        r = await client.get(f"/api/v1/dashboard/relatorios/desempenho?trilha_id={tid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["trilha"] is not None
        assert data["trilha"]["trilha_id"] == tid
        assert len(data["cursos"]) == 1


class TestRelatorioPresenca:
    """T-16.5 — presenca consolidada por periodo"""

    async def test_presenca_consolidada(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Presenca", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.post(
            f"/api/v1/cursos/{cid}/aulas",
            json={"curso_id": cid, "titulo": "Aula 1", "data_hora": "2026-08-25T10:00:00Z", "duracao_minutos": 60},
        )
        assert r.status_code == status.HTTP_201_CREATED, r.text
        aula_id = r.json()["id"]
        r = await client.post("/api/v1/cursos/inscricoes", json={"curso_id": cid})
        assert r.status_code == status.HTTP_201_CREATED, r.text

        # registrar presenca na aula
        r = await client.post(f"/api/v1/cursos/aulas/{aula_id}/entrar")
        assert r.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED), r.text

        r = await client.get("/api/v1/dashboard/relatorios/presenca")
        assert r.status_code == status.HTTP_200_OK, r.text
        data = r.json()
        assert data["resumo"]["total_presencas"] >= 1
        assert any(a["aula_id"] == aula_id for a in data["aulas"])

    async def test_presenca_filtro_por_curso(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Presenca 2", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.get(f"/api/v1/dashboard/relatorios/presenca?curso_id={cid}")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert isinstance(r.json()["aulas"], list)


class TestExportacao:
    """T-16.6 — exportacao CSV/PDF dos relatorios"""

    async def test_desempenho_csv(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Exp CSV", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.get(f"/api/v1/dashboard/relatorios/desempenho?curso_id={cid}&formato=csv")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "text/csv" in r.headers.get("content-type", ""), r.headers.get("content-type")
        assert "curso" in r.text

    async def test_desempenho_pdf(self, client):
        r = await client.post("/api/v1/cursos", json={"titulo": "Curso Exp PDF", "descricao": "x", "ordem": 0, "publicado": True})
        cid = r.json()["id"]
        r = await client.get(f"/api/v1/dashboard/relatorios/desempenho?curso_id={cid}&formato=pdf")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "application/pdf" in r.headers.get("content-type", ""), r.headers.get("content-type")

    async def test_presenca_csv(self, client):
        r = await client.get("/api/v1/dashboard/relatorios/presenca?formato=csv")
        assert r.status_code == status.HTTP_200_OK, r.text
        assert "text/csv" in r.headers.get("content-type", "")
