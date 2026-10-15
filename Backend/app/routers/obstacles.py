from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Edge, Node, Obstacle
from app.schemas import ObstacleCreate, ObstacleOut, ObstacleUpdate, Page
from app.security import EditorUser
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
async def create_obstacle(data: ObstacleCreate, session: SessionDep, user: EditorUser):
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
    return o


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
