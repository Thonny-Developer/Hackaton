from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import case, func, or_, select

from app.config import get_settings
from app.deps import SessionDep
from app.models import Building, Floor, Node, NodeType
from app.ratelimit import limiter
from app.schemas import (
    ProfileOut,
    RouteEdge,
    RouteIssue,
    RouteNode,
    RouteReason,
    RouteRequest,
    RouteResponse,
    RouteStep,
    SearchHit,
)
from app.services.geo import floor_lonlat
from app.services.geojson import route_geojson
from app.services.graph import Graph, Problem, RouteResult, find_route
from app.services.graph_cache import get_graph
from app.services.i18n import Lang, normalize_lang, t
from app.services.instructions import build_steps, problem_message
from app.services.profiles import PRESETS, Profile, resolve_profile

router = APIRouter(tags=["route"])
_s = get_settings()

LangQuery = Annotated[str, Query(pattern="^(ru|kk|kz|en)$", description="Язык инструкций: ru, kk (или kz), en")]


@router.get("/profiles", response_model=list[ProfileOut], summary="Готовые профили доступности")
async def list_profiles(lang: LangQuery = "ru"):
    lg = normalize_lang(lang)
    return [ProfileOut(id=k, title=v["title"][lg], params=v["profile"]) for k, v in PRESETS.items()]


@router.get("/search", response_model=list[SearchHit], summary="Поиск помещения по названию или номеру")
@limiter.limit(_s.rate_limit_search)
async def search(request: Request, session: SessionDep,
                 q: Annotated[str, Query(min_length=1, max_length=100)],
                 building_id: int | None = None,
                 limit: Annotated[int, Query(ge=1, le=50)] = 20):
    q = q.strip()
    if not q:
        return []
    ref_l, q_l = func.lower(Node.ref), q.lower()
    rank = case(
        (ref_l == q_l, 0),
        (ref_l.startswith(q_l, autoescape=True), 1),
        (func.lower(Node.name) == q_l, 2),
        else_=3,
    )
    stmt = (
        select(Node, Floor, Building.name)
        .join(Floor, Floor.id == Node.floor_id)
        .join(Building, Building.id == Node.building_id)
        .where(Node.type != NodeType.corridor)
        .where(or_(Node.name.icontains(q, autoescape=True), Node.ref.icontains(q, autoescape=True)))
        .order_by(rank, Floor.level, Node.ref, Node.name, Node.id)
        .limit(limit)
    )
    if building_id is not None:
        stmt = stmt.where(Node.building_id == building_id)
    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(node_id=n.id, building_id=n.building_id, building_name=bname, floor_id=n.floor_id, level=fl.level,
                  type=n.type, name=n.name, ref=n.ref, x=n.x, y=n.y,
                  geo=[n.lon, n.lat] if n.lat is not None and n.lon is not None else floor_lonlat(fl, n.x, n.y))
        for n, fl, bname in rows
    ]


@router.post("/route", response_model=RouteResponse, summary="Построить маршрут с учётом профиля доступности",
             responses={404: {"description": "Узел не найден"}})
@limiter.limit(_s.rate_limit_route)
async def build_route(request: Request, data: RouteRequest, session: SessionDep, lang: LangQuery = "ru"):
    """Если маршрута нет, ответ всё равно 200, но `found=false`, а в `reason` указаны код,
    понятное объяснение и конкретные места, которые мешают (лестница, узкий проход, сломанный лифт)."""
    lg = normalize_lang(lang)
    profile = resolve_profile(data.profile, data.overrides)

    rows = dict((await session.execute(
        select(Node.id, Node.building_id).where(Node.id.in_([data.from_node, data.to_node]))
    )).all())
    for nid in (data.from_node, data.to_node):
        if nid not in rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Узел #{nid} не найден")

    building_id = rows[data.from_node]
    base = RouteResponse(found=False, building_id=building_id, profile=data.profile, params=profile)
    if rows[data.to_node] != building_id:
        base.reason = RouteReason(code="different_buildings", message=t(lg, "different_buildings"), details=[])
        return base

    graph = await get_graph(session, building_id)
    if graph is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Здание не найдено")
    res =await run_in_threadpool(find_route, graph, data.from_node, data.to_node, profile, datetime.now(UTC))
    return render_route(graph, res, base, profile, lg)


def _issue(graph: Graph, p: Problem, lang: Lang) -> RouteIssue:
    return RouteIssue(
        kind=p.kind, code=p.code, message=problem_message(graph, p, lang), edge_id=p.edge_id, node_id=p.node_id,
        obstacle_id=p.obstacle.id if p.obstacle else None, value=p.value, limit=p.limit,
    )


def render_route(graph: Graph, res: RouteResult, base: RouteResponse, profile: Profile, lang: Lang) -> RouteResponse:
    if not res.found:
        base.reason = RouteReason(code=res.reason, message=t(lang, res.reason),
                                  details=[_issue(graph, p, lang) for p in res.problems])
        return base

    steps = build_steps(graph, res, profile, lang)
    floors: list[int] = []
    for nid in res.node_ids:
        lvl = graph.nodes[nid].level
        if not floors or floors[-1] != lvl:
            floors.append(lvl)

    base.found = True
    base.total_distance_m = round(sum(graph.edges[e].length_m for e in res.edge_ids), 1)
    base.estimated_time_s = round(res.cost_s)
    base.floors = floors
    base.nodes = [RouteNode(id=n.id, floor_id=n.floor_id, level=n.level, type=n.type, name=n.name, ref=n.ref,
                            x=n.x, y=n.y, geo=graph.node_geo(n)) for n in (graph.nodes[i] for i in res.node_ids)]
    base.geojson = route_geojson(graph, res.node_ids)
    base.edges = []
    for i, eid in enumerate(res.edge_ids):
        e = graph.edges[eid]
        # Направление ребра отдаём по ходу маршрута, а не как оно хранится в БД
        base.edges.append(RouteEdge(id=e.id, from_node_id=res.node_ids[i], to_node_id=res.node_ids[i + 1],
                                    type=e.type, length_m=e.length_m))
    base.steps = [RouteStep(action=s.action, text=s.text, floor_id=s.floor_id, level=s.level, to_level=s.to_level,
                            distance_m=round(s.distance_m, 1), duration_s=round(s.duration_s), node_ids=s.node_ids,
                            edge_ids=s.edge_ids) for s in steps]
    base.warnings = [_issue(graph, w, lang) for w in res.warnings]
    return base
