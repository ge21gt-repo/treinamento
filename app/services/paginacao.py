from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


async def count_query(db: AsyncSession, query) -> int:
    count_q = select(func.count()).select_from(query.subquery())
    return await db.scalar(count_q) or 0


def apply_search(query, search_cols: list[Any], q: str | None):
    if q and search_cols:
        filters = [col.ilike(f"%{q}%") for col in search_cols]
        query = query.filter(or_(*filters))
    return query
