from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "checks" in data
    assert data["checks"]["database"]["status"] == "ok"


async def test_health_reporta_estado_das_migrations():
    """O deploy nao roda `alembic upgrade head` e o create_all nao adiciona coluna:
    schema atrasado precisa ficar visivel em vez de virar 500 num endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    migrations = response.json()["checks"]["migrations"]
    assert migrations["status"] in ("ok", "pendente", "error")
    assert migrations["detail"]
    if migrations["status"] == "pendente":
        # quando atrasado, o detalhe tem que dizer o que fazer
        assert "alembic upgrade head" in migrations["detail"] or "alembic_version" in migrations["detail"]


async def test_health_migrations_nao_derruba_o_status_geral():
    """O deploy usa /health como gate (exige 200) -- schema atrasado nao pode
    reprovar o deploy, so aparecer no payload."""
    from app.services.health import check_migrations

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    body = response.json()
    if body["checks"]["migrations"]["status"] != "ok":
        assert body["status"] == "ok", "migrations pendente nao deve degradar o status geral"
    assert callable(check_migrations)


async def test_health_live():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_ready():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
