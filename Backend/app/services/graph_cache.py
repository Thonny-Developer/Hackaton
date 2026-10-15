"""Кэш графов зданий в памяти процесса.

Перед построением маршрута читаем только buildings.graph_version (один запрос по PK).
Если версия изменилась (кто-то правил узлы, рёбра, препятствия), граф перечитывается.
Так кэш корректен даже при нескольких воркерах uvicorn.
"""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Building, Edge, Floor, Node, Obstacle
from app.services.graph import GEdge, GFloor, GNode, GObstacle, Graph, edge_length

_cache: dict[int, Graph] = {}
_locks: dict[int, asyncio.Lock] = {}


async def bump_graph_version(session: AsyncSession, building_id: int) -> None:
    """Вызывать в той же транзакции, что и изменение графа."""
    await session.execute(
        update(Building).where(Building.id == building_id).values(graph_version=Building.graph_version + 1)
    )


async def load_graph(session: AsyncSession, building_id: int, version: int) -> Graph:
    floors = {f.id: f for f in (await session.scalars(select(Floor).where(Floor.building_id == building_id)))}
    nodes = list(await session.scalars(select(Node).where(Node.building_id == building_id)))
    edges = list(await session.scalars(select(Edge).where(Edge.building_id == building_id)))
    now = datetime.now(UTC)
    obstacles = list(await session.scalars(
        select(Obstacle).where(
            Obstacle.building_id == building_id,
            Obstacle.is_active.is_(True),
            (Obstacle.ends_at.is_(None)) | (Obstacle.ends_at > now),
        )
    ))

    g = Graph(building_id=building_id, version=version)
    for f in floors.values():
        g.floors[f.id] = GFloor(f.id, f.level, f.meters_per_px, f.height_m, f.geo_origin_lat, f.geo_origin_lon,
                                f.geo_rotation_deg or 0.0)
    for n in nodes:
        g.nodes[n.id] = GNode(n.id, n.floor_id, floors[n.floor_id].level, n.type.value, n.name, n.ref,
                              n.x, n.y, n.lat, n.lon, n.is_accessible_entrance)
    for e in edges:
        a, b = g.nodes.get(e.from_node_id), g.nodes.get(e.to_node_id)
        if a is None or b is None:
            continue
        g.edges[e.id] = GEdge(e.id, a.id, b.id, e.type.value, effective_edge_length(e, a, b, floors),
                              e.bidirectional, e.width_cm, e.steps, e.slope_pct, e.threshold_cm, e.description)
    for o in obstacles:
        g.obstacles.append(GObstacle(o.id, o.type.value, o.node_id, o.edge_id, o.description,
                                     o.reduced_width_cm, _aware(o.starts_at), _aware(o.ends_at)))
    g.build_index()
    return g


def effective_edge_length(e: Edge, a, b, floors: dict[int, Floor]) -> float:
    if e.length_m is not None:
        return e.length_m
    fa = floors[a.floor_id]
    return round(edge_length(a.x, a.y, b.x, b.y, a.level, b.level, fa.meters_per_px, fa.height_m), 2)


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite в тестах возвращает naive datetime
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def get_graph(session: AsyncSession, building_id: int) -> Graph | None:
    version = await session.scalar(select(Building.graph_version).where(Building.id == building_id))
    if version is None:
        return None
    cached = _cache.get(building_id)
    if cached and cached.version == version:
        return cached
    lock = _locks.setdefault(building_id, asyncio.Lock())
    async with lock:
        cached = _cache.get(building_id)
        if cached and cached.version == version:
            return cached
        g = await load_graph(session, building_id, version)
        _cache[building_id] = g
        return g


def clear_cache() -> None:
    _cache.clear()
