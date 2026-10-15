"""Импорт графа здания одним JSON. Используется для seed и для загрузки реальных схем."""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Building, Edge, Floor, Node
from app.schemas import GraphImport, ImportResult
from app.services.graph_cache import bump_graph_version


def _check(data: GraphImport) -> None:
    errors: list[str] = []
    floor_keys = [f.key for f in data.floors]
    if len(set(floor_keys)) != len(floor_keys):
        errors.append("Повторяющиеся key у этажей")
    levels = [f.level for f in data.floors]
    if len(set(levels)) != len(levels):
        errors.append("Повторяющиеся level у этажей")
    node_keys = [n.key for n in data.nodes]
    if len(set(node_keys)) != len(node_keys):
        errors.append("Повторяющиеся key у узлов")
    fk, nk = set(floor_keys), set(node_keys)
    errors += [f"Узел {n.key}: нет этажа {n.floor}" for n in data.nodes if n.floor not in fk]
    for e in data.edges:
        if e.from_ not in nk or e.to not in nk:
            errors.append(f"Ребро {e.from_}->{e.to}: неизвестный узел")
        elif e.from_ == e.to:
            errors.append(f"Ребро {e.from_}->{e.to}: петля")
    if errors:
        raise HTTPException(422, errors[:50])


async def import_graph(session: AsyncSession, building: Building, data: GraphImport) -> ImportResult:
    """Заменяет граф здания. Этажи сопоставляются по level, чтобы не терять загруженные схемы."""
    _check(data)

    await session.execute(delete(Edge).where(Edge.building_id == building.id))
    await session.execute(delete(Node).where(Node.building_id == building.id))
    existing = {f.level: f for f in await session.scalars(select(Floor).where(Floor.building_id == building.id))}
    wanted = {f.level for f in data.floors}
    for level, floor in existing.items():
        if level not in wanted:
            await session.delete(floor)
    await session.flush()

    floors: dict[str, Floor] = {}
    for f in data.floors:
        floor = existing.get(f.level) or Floor(building_id=building.id, level=f.level)
        for k, v in f.model_dump(exclude={"key", "level"}).items():
            setattr(floor, k, v)
        session.add(floor)
        floors[f.key] = floor
    await session.flush()

    nodes: dict[str, Node] = {}
    for n in data.nodes:
        node = Node(building_id=building.id, floor_id=floors[n.floor].id,
                    **n.model_dump(exclude={"key", "floor"}))
        session.add(node)
        nodes[n.key] = node
    await session.flush()

    for e in data.edges:
        session.add(Edge(building_id=building.id, from_node_id=nodes[e.from_].id, to_node_id=nodes[e.to].id,
                         **e.model_dump(exclude={"from_", "to"})))
    await session.flush()
    await bump_graph_version(session, building.id)

    return ImportResult(floors=len(floors), nodes=len(nodes), edges=len(data.edges),
                        node_ids={k: v.id for k, v in nodes.items()})
