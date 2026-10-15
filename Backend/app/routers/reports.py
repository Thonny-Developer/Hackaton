from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Building, Report, ReportStatus, Role, User
from app.ratelimit import limiter
from app.schemas import Page, ReportCreate, ReportOut, ReportUpdate
from app.security import EditorUser, OptionalUser
from app.services import mailer

router = APIRouter(prefix="/reports", tags=["reports"])


def report_out(r: Report, building_name: str | None) -> ReportOut:
    out = ReportOut.model_validate(r)
    out.building_name = building_name
    return out


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED,
             summary="Сообщить об изменении доступности здания")
@limiter.limit(get_settings().rate_limit_reports)
async def create_report(request: Request, data: ReportCreate, session: SessionDep, user: OptionalUser,
                        background: BackgroundTasks):
    """Можно и без входа. Сообщение попадает к редакторам со статусом `new` и на маршруты
    не влияет, пока его не проверят. С токеном оно появится в `GET /auth/me/reports`."""
    building = await get_or_404(session, Building, data.building_id, "Здание")
    r = Report(building_id=building.id, user_id=user.id if user else None, text=data.text, status=ReportStatus.new)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    if get_settings().notify_reports:
        to = list(await session.scalars(
            select(User.email).where(User.role == Role.admin, User.is_active.is_(True))
        ))
        if to:
            lines = [("Здание", building.name), ("Сообщение", r.text),
                     ("От", user.email if user else "без входа")]
            background.add_task(mailer.send_safe, mailer.obstacle_mail(to, "Новое сообщение о доступности", lines))
    return report_out(r, building.name)


@router.get("", response_model=Page[ReportOut], summary="Сообщения посетителей (для редакторов)")
async def list_reports(session: SessionDep, _: EditorUser, building_id: int | None = None,
                       status_: Annotated[ReportStatus | None, Query(alias="status")] = None,
                       limit: Limit = 50, offset: Offset = 0):
    stmt = select(Report, Building.name).join(Building, Building.id == Report.building_id).order_by(Report.id.desc())
    if building_id is not None:
        stmt = stmt.where(Report.building_id == building_id)
    if status_ is not None:
        stmt = stmt.where(Report.status == status_)
    rows, total = await paginate(session, stmt, limit, offset, scalars=False)
    return Page(items=[report_out(r, name) for r, name in rows], total=total, limit=limit, offset=offset)


@router.patch("/{report_id}", response_model=ReportOut, summary="Отметить сообщение проверенным или отклонённым")
async def update_report(report_id: int, data: ReportUpdate, session: SessionDep, _: EditorUser):
    r = await get_or_404(session, Report, report_id, "Сообщение")
    r.status = data.status
    await session.commit()
    await session.refresh(r)
    building = await session.get(Building, r.building_id)
    return report_out(r, building.name if building else None)
