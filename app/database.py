from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

connect_args: dict = {}
if settings.DATABASE_URL and ".flycast" in settings.DATABASE_URL:
    connect_args["ssl"] = False

engine = create_async_engine(
    settings.DATABASE_URL, echo=False, future=True, connect_args=connect_args,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session
