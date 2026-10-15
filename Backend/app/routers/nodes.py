from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Floor, Node, NodeType
from app.routers.buildings import node_out
from app.schemas import NodeCreate, NodeOut, NodeUpdate, Page
from app.security import EditorUser
from app.services.graph_cache import bump_graph_version, get_graph

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.get("", response_model=Page[NodeOut])
async def list_nodes(session: SessionDep, building_id: int | None = None, floor_id: int | None = None,
                     type: NodeType | None = Query(None), limit: Limit = 200, offset: Offset = 0):
    stmt = select(Node).order_by(Node.id)
    if building_id is not None:
        stmt = stmt.where(Node.building_id == building_id)
    if floor_id is not None:
        stmt = stmt.where(Node.floor_id == floor_id)
    if type is not None:
        stmt = stmt.where(Node.type == type)
    items, total = await paginate(session, stmt, limit, offset)
    graphs: dict = {}
    out = []
    for n in items:
        if n.building_id not in graphs:
            graphs[n.building_id] = await get_graph(session, n.building_id)
        out.append(node_out(n, graphs[n.building_id]))
    return Page(items=out, total=total, limit=limit, offset=offset)


@router.post("", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def create_node(data: NodeCreate, session: SessionDep, _: EditorUser):
    floor = await get_or_404(session, Floor, data.floor_id, "Этаж")
    node = Node(building_id=floor.building_id, **data.model_dump())
    session.add(node)
    await bump_graph_version(session, floor.building_id)
    await session.commit()
    return node_out(node, await get_graph(session, node.building_id))


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(node_id: int, session: SessionDep):
    node = await get_or_404(session, Node, node_id, "Узел")
    return node_out(node, await get_graph(session, node.building_id))


@router.patch("/{node_id}", response_model=NodeOut)
async def update_node(node_id: int, data: NodeUpdate, session: SessionDep, _: EditorUser):
    node = await get_or_404(session, Node, node_id, "Узел")
    patch = data.model_dump(exclude_unset=True)
    if patch.get("floor_id") is not None and patch["floor_id"] != node.floor_id:
        floor = await get_or_404(session, Floor, patch["floor_id"], "Этаж")
        if floor.building_id != node.building_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Узел нельзя перенести в другое здание")
    for k, v in patch.items():
        # Обязательные поля не обнуляем, необязательные (name, ref, lat...) можно стереть через null
        if v is None and k in ("floor_id", "type", "x", "y", "is_accessible_entrance"):
            continue
        setattr(node, k, v)
    await bump_graph_version(session, node.building_id)
    await session.commit()
    await session.refresh(node)
    return node_out(node, await get_graph(session, node.building_id))


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить узел и все его рёбра")
async def delete_node(node_id: int, session: SessionDep, _: EditorUser):
    node = await get_or_404(session, Node, node_id, "Узел")
    await bump_graph_version(session, node.building_id)
    await session.delete(node)
    await session.commit()
