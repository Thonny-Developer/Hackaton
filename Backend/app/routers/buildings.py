from fastapi import APIRouter, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Building, Edge, Floor, Node
from app.schemas import (
    BuildingCreate,
    BuildingImport,
    BuildingOut,
    BuildingUpdate,
    EdgeOut,
    FloorCreate,
    FloorOut,
    GraphExport,
    GraphImport,
    ImportResult,
    NodeOut,
    Page,
)
from app.security import AdminUser, EditorUser
from app.services import storage
from app.services.graph_cache import bump_graph_version, get_graph
from app.services.importer import import_graph

router = APIRouter(prefix="/buildings", tags=["buildings"])


def floor_out(f: Floor) -> FloorOut:
    out = FloorOut.model_validate(f)
    out.plan_url = storage.plan_url(f.id, f.plan_object_key)
    return out


@router.get("", response_model=Page[BuildingOut], summary="Список зданий")
async def list_buildings(session: SessionDep, q: str | None = Query(None, max_length=100),
                         limit: Limit = 50, offset: Offset = 0):
    stmt = select(Building).order_by(Building.name, Building.id)
    if q:
        stmt = stmt.where(Building.name.icontains(q, autoescape=True))
    items, total = await paginate(session, stmt, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=BuildingOut, status_code=status.HTTP_201_CREATED)
async def create_building(data: BuildingCreate, session: SessionDep, _: EditorUser):
    b = Building(**data.model_dump())
    session.add(b)
    await session.commit()
    return b


@router.post("/import", response_model=ImportResult, status_code=status.HTTP_201_CREATED,
             summary="Создать здание вместе с графом из JSON")
async def import_building(data: BuildingImport, session: SessionDep, _: EditorUser):
    b = Building(**data.model_dump(exclude={"graph"}))
    session.add(b)
    await session.flush()
    result = await import_graph(session, b, data.graph)
    await session.commit()
    return result


@router.get("/{building_id}", response_model=BuildingOut)
async def get_building(building_id: int, session: SessionDep):
    return await get_or_404(session, Building, building_id, "Здание")


@router.patch("/{building_id}", response_model=BuildingOut)
async def update_building(building_id: int, data: BuildingUpdate, session: SessionDep, _: EditorUser):
    b = await get_or_404(session, Building, building_id, "Здание")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(b, k, v)
    await session.commit()
    await session.refresh(b)
    return b


@router.delete("/{building_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить здание (только admin)")
async def delete_building(building_id: int, session: SessionDep, _: AdminUser):
    b = await get_or_404(session, Building, building_id, "Здание")
    keys = list(await session.scalars(
        select(Floor.plan_object_key).where(Floor.building_id == b.id, Floor.plan_object_key.is_not(None))
    ))
    await session.delete(b)
    await session.commit()
    for key in keys:
        await run_in_threadpool(storage.delete_plan, key)


@router.get("/{building_id}/floors", response_model=list[FloorOut])
async def list_floors(building_id: int, session: SessionDep):
    await get_or_404(session, Building, building_id, "Здание")
    floors = await session.scalars(select(Floor).where(Floor.building_id == building_id).order_by(Floor.level))
    return [floor_out(f) for f in floors]


@router.post("/{building_id}/floors", response_model=FloorOut, status_code=status.HTTP_201_CREATED)
async def create_floor(building_id: int, data: FloorCreate, session: SessionDep, _: EditorUser):
    await get_or_404(session, Building, building_id, "Здание")
    if await session.scalar(select(Floor.id).where(Floor.building_id == building_id, Floor.level == data.level)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Этаж с level={data.level} уже есть")
    f = Floor(building_id=building_id, **data.model_dump())
    session.add(f)
    await bump_graph_version(session, building_id)
    await session.commit()
    return floor_out(f)


@router.get("/{building_id}/graph", response_model=GraphExport, summary="Весь граф здания одним ответом")
async def export_graph(building_id: int, session: SessionDep):
    b = await get_or_404(session, Building, building_id, "Здание")
    g = await get_graph(session, building_id)
    floors = await session.scalars(select(Floor).where(Floor.building_id == building_id).order_by(Floor.level))
    nodes = await session.scalars(select(Node).where(Node.building_id == building_id).order_by(Node.id))
    edges = await session.scalars(select(Edge).where(Edge.building_id == building_id).order_by(Edge.id))
    return GraphExport(
        building=BuildingOut.model_validate(b),
        floors=[floor_out(f) for f in floors],
        nodes=[NodeOut.model_validate(n) for n in nodes],
        edges=[edge_out(e, g) for e in edges],
    )


@router.put("/{building_id}/graph", response_model=ImportResult, summary="Заменить граф здания (импорт JSON)")
async def replace_graph(building_id: int, data: GraphImport, session: SessionDep, _: EditorUser):
    """Удаляет все узлы, рёбра и препятствия здания и загружает граф заново.
    Этажи сопоставляются по `level`, поэтому загруженные схемы сохраняются."""
    b = await get_or_404(session, Building, building_id, "Здание")
    result = await import_graph(session, b, data)
    await session.commit()
    return result


def edge_out(e: Edge, g) -> EdgeOut:
    out = EdgeOut.model_validate(e)
    if g and e.id in g.edges:
        out.effective_length_m = g.edges[e.id].length_m
    return out
