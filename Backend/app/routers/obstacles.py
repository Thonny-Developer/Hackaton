from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Building, Edge, Floor, Node, Obstacle, Role, User
from app.schemas import ObstacleCreate, ObstacleOut, ObstacleUpdate, Page
from app.security import EditorUser
from app.services import mailer
from app.services.graph_cache import bump_graph_version

router = APIRouter(prefix="/obstacles", tags=["obstacles"])


@router.get("", response_model=Page[ObstacleOut], summary="Список препятствий")
async def list_obstacles(session: SessionDep, building_id: int | None = None,
                         state: Literal["active", "inactive", "all"] = "active",
                         limit: Limit = 100, offset: Offset = 0):
    """`state=active` (по умолчанию) возвращает препятствия, действующие прямо сейчас,
    `inactive` снятые, истёкшие и запланированные, `all` все."""
    stmt = select(Obstacle).order_by(Obstacle.id.desc())
    if building_id is not None:
        stmt = stmt.where(Obstacle.building_id == building_id)
    now = datetime.now(UTC)
    current = (
        Obstacle.is_active.is_(True)
        & (Obstacle.starts_at <= now)
        & (Obstacle.ends_at.is_(None) | (Obstacle.ends_at > now))
    )
    if state == "active":
        stmt = stmt.where(current)
    elif state == "inactive":
        stmt = stmt.where(~current)
    items, total = await paginate(session, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ObstacleOut, status_code=status.HTTP_201_CREATED,
             summary="Отметить препятствие (сразу влияет на маршруты)")
async def create_obstacle(data: ObstacleCreate, session: SessionDep, user: EditorUser, background: BackgroundTasks):
    if data.node_id is not None:
        target = await get_or_404(session, Node, data.node_id, "Узел")
    else:
        target = await get_or_404(session, Edge, data.edge_id, "Ребро")
    payload = data.model_dump(exclude_none=True)
    o = Obstacle(building_id=target.building_id, created_by_id=user.id, is_active=True, **payload)
    session.add(o)
    await bump_graph_version(session, target.building_id)
    await session.commit()
    await session.refresh(o)
    if get_settings().notify_obstacles:
        mail = await _obstacle_mail(session, o, target, user)
        if mail:
            background.add_task(mailer.send_safe, mail)
    return o


# Казахстан с 2024 года живёт в одном часовом поясе UTC+5
KZ_TZ = timezone(timedelta(hours=5))

OBSTACLE_TITLES = {"elevator_broken": "Лифт не работает", "repair": "Ремонт", "blocked": "Проход перекрыт",
                   "narrowed": "Проход сужен", "other": "Препятствие"}


async def _obstacle_mail(session, o: Obstacle, target, author: User) -> mailer.Mail | None:
    """Письмо всем активным админам, кроме автора: на маршрутах это отразится сразу."""
    to = list(await session.scalars(
        select(User.email).where(User.role == Role.admin, User.is_active.is_(True), User.id != author.id)
    ))
    if not to:
        return None
    building = await session.get(Building, o.building_id)
    nodes = [target] if isinstance(target, Node) else [await session.get(Node, target.from_node_id),
                                                       await session.get(Node, target.to_node_id)]
    floors = {n.floor_id: await session.get(Floor, n.floor_id) for n in nodes}
    where = " → ".join(
        f"{n.name or n.ref or n.type.value} ({floors[n.floor_id].level} этаж)" for n in nodes
    )
    lines = [("Здание", building.name), ("Где", where)]
    if o.description:
        lines.append(("Описание", o.description))
    if o.reduced_width_cm:
        lines.append(("Ширина прохода", f"{o.reduced_width_cm:g} см"))
    if o.ends_at:
        lines.append(("До", _aware(o.ends_at).astimezone(KZ_TZ).strftime("%d.%m.%Y %H:%M (UTC+5)")))
    lines.append(("Отметил", author.email))
    return mailer.obstacle_mail(to, OBSTACLE_TITLES.get(o.type.value, "Препятствие"), lines)


@router.get("/{obstacle_id}", response_model=ObstacleOut)
async def get_obstacle(obstacle_id: int, session: SessionDep):
    return await get_or_404(session, Obstacle, obstacle_id, "Препятствие")


@router.patch("/{obstacle_id}", response_model=ObstacleOut, summary="Изменить или снять препятствие (is_active=false)")
async def update_obstacle(obstacle_id: int, data: ObstacleUpdate, session: SessionDep, _: EditorUser):
    o = await get_or_404(session, Obstacle, obstacle_id, "Препятствие")
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is None and k in ("type", "is_active", "starts_at"):
            continue
        setattr(o, k, v)
    if o.ends_at and o.starts_at and _aware(o.ends_at) <= _aware(o.starts_at):
        raise HTTPException(422, "ends_at должен быть позже starts_at")
    await bump_graph_version(session, o.building_id)
    await session.commit()
    await session.refresh(o)
    return o


@router.delete("/{obstacle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_obstacle(obstacle_id: int, session: SessionDep, _: EditorUser):
    o = await get_or_404(session, Obstacle, obstacle_id, "Препятствие")
    await bump_graph_version(session, o.building_id)
    await session.delete(o)
    await session.commit()


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
