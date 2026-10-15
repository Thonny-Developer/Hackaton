from fastapi import APIRouter, status
from sqlalchemy import delete, select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Building, Favorite, Report
from app.routers.reports import report_out
from app.schemas import BuildingOut, Page, ReportOut
from app.security import CurrentUser

router = APIRouter(prefix="/auth/me", tags=["account"])


@router.get("/favorites", response_model=list[BuildingOut], summary="Избранные здания")
async def list_favorites(user: CurrentUser, session: SessionDep):
    stmt = (
        select(Building)
        .join(Favorite, Favorite.building_id == Building.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    )
    return list(await session.scalars(stmt))


@router.put("/favorites/{building_id}", status_code=status.HTTP_204_NO_CONTENT,
            summary="Добавить здание в избранное (повторный вызов ничего не меняет)")
async def add_favorite(building_id: int, user: CurrentUser, session: SessionDep):
    await get_or_404(session, Building, building_id, "Здание")
    if await session.get(Favorite, (user.id, building_id)) is None:
        session.add(Favorite(user_id=user.id, building_id=building_id))
        await session.commit()


@router.delete("/favorites/{building_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Убрать здание из избранного")
async def remove_favorite(building_id: int, user: CurrentUser, session: SessionDep):
    await session.execute(delete(Favorite).where(Favorite.user_id == user.id, Favorite.building_id == building_id))
    await session.commit()


@router.get("/reports", response_model=Page[ReportOut], summary="Мои сообщения о доступности")
async def my_reports(user: CurrentUser, session: SessionDep, limit: Limit = 50, offset: Offset = 0):
    stmt = (
        select(Report, Building.name)
        .join(Building, Building.id == Report.building_id)
        .where(Report.user_id == user.id)
        .order_by(Report.id.desc())
    )
    rows, total = await paginate(session, stmt, limit, offset, scalars=False)
    return Page(items=[report_out(r, name) for r, name in rows], total=total, limit=limit, offset=offset)
