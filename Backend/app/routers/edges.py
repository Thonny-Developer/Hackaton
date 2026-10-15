from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Edge, Node
from app.routers.buildings import edge_out
from app.schemas import EdgeCreate, EdgeOut, EdgeUpdate, Page
from app.security import EditorUser
from app.services.graph_cache import bump_graph_version, get_graph

router = APIRouter(prefix="/edges", tags=["edges"])


@router.get("", response_model=Page[EdgeOut])
async def list_edges(session: SessionDep, building_id: int | None = None, floor_id: int | None = None,
                     node_id: int | None = None, limit: Limit = 200, offset: Offset = 0):
    stmt = select(Edge).order_by(Edge.id)
    if building_id is not None:
        stmt = stmt.where(Edge.building_id == building_id)
    if node_id is not None:
        stmt = stmt.where(or_(Edge.from_node_id == node_id, Edge.to_node_id == node_id))
    if floor_id is not None:
        on_floor = select(Node.id).where(Node.floor_id == floor_id)
        stmt = stmt.where(or_(Edge.from_node_id.in_(on_floor), Edge.to_node_id.in_(on_floor)))
    items, total = await paginate(session, stmt, limit, offset)
    graphs: dict = {}
    out = []
    for e in items:
        if e.building_id not in graphs:
            graphs[e.building_id] = await get_graph(session, e.building_id)
        out.append(edge_out(e, graphs[e.building_id]))
    return Page(items=out, total=total, limit=limit, offset=offset)


@router.post("", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def create_edge(data: EdgeCreate, session: SessionDep, _: EditorUser):
    a = await get_or_404(session, Node, data.from_node_id, "Узел")
    b = await get_or_404(session, Node, data.to_node_id, "Узел")
    if a.building_id != b.building_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Узлы находятся в разных зданиях")
    edge = Edge(building_id=a.building_id, **data.model_dump())
    session.add(edge)
    await bump_graph_version(session, a.building_id)
    await session.commit()
    return edge_out(edge, await get_graph(session, a.building_id))


@router.get("/{edge_id}", response_model=EdgeOut)
async def get_edge(edge_id: int, session: SessionDep):
    edge = await get_or_404(session, Edge, edge_id, "Ребро")
    return edge_out(edge, await get_graph(session, edge.building_id))


@router.patch("/{edge_id}", response_model=EdgeOut)
async def update_edge(edge_id: int, data: EdgeUpdate, session: SessionDep, _: EditorUser):
    edge = await get_or_404(session, Edge, edge_id, "Ребро")
    for k, v in data.model_dump(exclude_unset=True).items():
        # length_m, width_cm и description можно сбросить в null, остальные поля обязательные
        if v is None and k not in ("length_m", "width_cm", "description"):
            continue
        setattr(edge, k, v)
    await bump_graph_version(session, edge.building_id)
    await session.commit()
    await session.refresh(edge)
    return edge_out(edge, await get_graph(session, edge.building_id))


@router.delete("/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(edge_id: int, session: SessionDep, _: EditorUser):
    edge = await get_or_404(session, Edge, edge_id, "Ребро")
    await bump_graph_version(session, edge.building_id)
    await session.delete(edge)
    await session.commit()
