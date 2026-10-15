from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Base, get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]

M = TypeVar("M", bound=Base)


async def get_or_404(session: AsyncSession, model: type[M], obj_id: int, what: str = "Объект") -> M:
    obj = await session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{what} #{obj_id} не найден")
    return obj


async def paginate(session: AsyncSession, stmt: Select, limit: int, offset: int,
                   scalars: bool = True) -> tuple[list, int]:
    """scalars=False возвращает строки целиком, когда в select несколько колонок."""
    total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    page = stmt.limit(limit).offset(offset)
    items = list(await session.scalars(page)) if scalars else list(await session.execute(page))
    return items, total or 0
