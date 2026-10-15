"""Граф здания в памяти и поиск маршрута (Dijkstra).

Модуль не знает про БД и HTTP: на вход структуры данных, на выход путь
или диагностика, почему пути нет. Так его легко тестировать.
"""

import heapq
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.services.profiles import Profile

VERTICAL_TYPES = {"elevator", "lift"}
ELEVATOR_WAIT_S = 30.0
ELEVATOR_PER_FLOOR_S = 6.0
LIFT_WAIT_S = 45.0
LIFT_PER_FLOOR_S = 20.0
STAIRS_PER_FLOOR_S = 25.0
STEP_S = 1.0
DOOR_S = 3.0


@dataclass(slots=True)
class GNode:
    id: int
    floor_id: int
    level: int
    type: str
    name: str | None
    ref: str | None
    x: float
    y: float
    lat: float | None = None
    lon: float | None = None
    is_accessible_entrance: bool = False

    @property
    def label(self) -> str | None:
        if self.name and self.ref and self.ref not in self.name:
            return f"{self.name} ({self.ref})"
        return self.name or self.ref


@dataclass(slots=True)
class GEdge:
    id: int
    a: int
    b: int
    type: str
    length_m: float
    bidirectional: bool = True
    width_cm: float | None = None
    steps: int = 0
    slope_pct: float = 0.0
    threshold_cm: float = 0.0
    description: str | None = None


@dataclass(slots=True)
class GObstacle:
    id: int
    type: str
    node_id: int | None = None
    edge_id: int | None = None
    description: str | None = None
    reduced_width_cm: float | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    def active_at(self, now: datetime) -> bool:
        if self.starts_at and self.starts_at > now:
            return False
        return not (self.ends_at and self.ends_at <= now)


@dataclass
class Graph:
    building_id: int
    version: int
    nodes: dict[int, GNode] = field(default_factory=dict)
    edges: dict[int, GEdge] = field(default_factory=dict)
    obstacles: list[GObstacle] = field(default_factory=list)
    # node_id -> [(сосед, edge_id)] с учётом направленности рёбер
    adj: dict[int, list[tuple[int, int]]] = field(default_factory=dict)
    # Все инцидентные рёбра без учёта направления (для препятствий на узлах)
    incident: dict[int, list[int]] = field(default_factory=dict)

    def build_index(self) -> None:
        self.adj = {nid: [] for nid in self.nodes}
        self.incident = {nid: [] for nid in self.nodes}
        for e in self.edges.values():
            if e.a not in self.nodes or e.b not in self.nodes:
                continue
            self.adj[e.a].append((e.b, e.id))
            if e.bidirectional:
                self.adj[e.b].append((e.a, e.id))
            self.incident[e.a].append(e.id)
            self.incident[e.b].append(e.id)


def edge_length(ax: float, ay: float, bx: float, by: float, a_level: int, b_level: int,
                meters_per_px: float, floor_height_m: float) -> float:
    """Длина ребра, если её не задали вручную."""
    if a_level != b_level:
        return abs(a_level - b_level) * floor_height_m
    return math.hypot(bx - ax, by - ay) * meters_per_px


# ---------- Препятствия ----------

@dataclass
class ObstacleState:
    blocked_edges: dict[int, GObstacle] = field(default_factory=dict)
    blocked_nodes: dict[int, GObstacle] = field(default_factory=dict)
    narrowed_edges: dict[int, tuple[float, GObstacle]] = field(default_factory=dict)

    def edge_blocker(self, graph: Graph, edge_id: int) -> GObstacle | None:
        if edge_id in self.blocked_edges:
            return self.blocked_edges[edge_id]
        e = graph.edges[edge_id]
        return self.blocked_nodes.get(e.a) or self.blocked_nodes.get(e.b)


def _shaft_edges(graph: Graph, start: int) -> set[int]:
    """Все рёбра лифтовой шахты, в которую входит узел (лифт сломан на всех этажах).
    Обход идёт только через узлы типа elevator/lift, чтобы не задеть соседние шахты через коридор."""
    seen_nodes, result, stack = {start}, set(), [start]
    while stack:
        n = stack.pop()
        for eid in graph.incident.get(n, []):
            e = graph.edges[eid]
            if e.type not in VERTICAL_TYPES:
                continue
            result.add(eid)
            other = e.b if e.a == n else e.a
            if other not in seen_nodes and graph.nodes[other].type in VERTICAL_TYPES:
                seen_nodes.add(other)
                stack.append(other)
    return result


def obstacle_state(graph: Graph, now: datetime) -> ObstacleState:
    st = ObstacleState()
    for o in graph.obstacles:
        if not o.active_at(now):
            continue
        if o.reduced_width_cm is not None:
            targets = [o.edge_id] if o.edge_id else graph.incident.get(o.node_id, [])
            for eid in targets:
                if eid in graph.edges:
                    prev = st.narrowed_edges.get(eid)
                    if prev is None or o.reduced_width_cm < prev[0]:
                        st.narrowed_edges[eid] = (o.reduced_width_cm, o)
            continue
        if o.edge_id is not None:
            if o.edge_id in graph.edges:
                st.blocked_edges[o.edge_id] = o
                e = graph.edges[o.edge_id]
                if e.type in VERTICAL_TYPES:
                    for end in (e.a, e.b):
                        if graph.nodes[end].type in VERTICAL_TYPES:
                            for eid in _shaft_edges(graph, end):
                                st.blocked_edges.setdefault(eid, o)
        elif o.node_id in graph.nodes:
            node = graph.nodes[o.node_id]
            if node.type in VERTICAL_TYPES:
                # Сломанный лифт: сама площадка у лифта проходима, недоступны поездки
                for eid in _shaft_edges(graph, node.id):
                    st.blocked_edges.setdefault(eid, o)
            else:
                st.blocked_nodes[o.node_id] = o
    return st


# ---------- Профиль ----------

@dataclass(slots=True)
class Violation:
    code: str  # stairs | steps | too_narrow | too_steep | threshold | elevator_not_allowed
    edge_id: int
    value: float | None = None
    limit: float | None = None


def effective_width(edge: GEdge, obst: ObstacleState) -> float | None:
    narrowed = obst.narrowed_edges.get(edge.id)
    if narrowed is None:
        return edge.width_cm
    if edge.width_cm is None:
        return narrowed[0]
    return min(edge.width_cm, narrowed[0])


def profile_violations(edge: GEdge, profile: Profile, obst: ObstacleState) -> list[Violation]:
    v: list[Violation] = []
    if edge.type == "stairs" and not profile.allow_stairs:
        v.append(Violation("stairs", edge.id, edge.steps or None))
    elif profile.max_steps is not None and edge.steps > profile.max_steps:
        v.append(Violation("steps", edge.id, edge.steps, profile.max_steps))
    width = effective_width(edge, obst)
    if profile.min_width_cm is not None and width is not None and width < profile.min_width_cm:
        v.append(Violation("too_narrow", edge.id, width, profile.min_width_cm))
    if profile.max_slope_pct is not None and edge.slope_pct > profile.max_slope_pct:
        v.append(Violation("too_steep", edge.id, edge.slope_pct, profile.max_slope_pct))
    if profile.max_threshold_cm is not None and edge.threshold_cm > profile.max_threshold_cm:
        v.append(Violation("threshold", edge.id, edge.threshold_cm, profile.max_threshold_cm))
    if edge.type in VERTICAL_TYPES and not profile.allow_elevator:
        v.append(Violation("elevator_not_allowed", edge.id))
    return v


# ---------- Стоимость и Dijkstra ----------

def approach_wait(a: GNode, b: GNode) -> float:
    """Ожидание кабины, если ребро a -> b подводит к узлу лифта или подъёмника."""
    if a.type in VERTICAL_TYPES:
        return 0.0
    if b.type == "elevator":
        return ELEVATOR_WAIT_S
    if b.type == "lift":
        return LIFT_WAIT_S
    return 0.0


def traverse_cost(graph: Graph, edge: GEdge, frm: int, to: int, profile: Profile) -> float:
    """Оценка времени прохода ребра в секундах (в направлении frm -> to)."""
    a, b = graph.nodes[frm], graph.nodes[to]
    floors = abs(a.level - b.level)
    # Ожидание кабины считаем один раз: либо на подходе к узлу-лифту (ниже),
    # либо здесь, если ребро лифта/подъёмника соединяет обычные узлы
    if edge.type == "elevator":
        cost = ELEVATOR_PER_FLOOR_S * max(floors, 1)
        if a.type not in VERTICAL_TYPES:
            cost += ELEVATOR_WAIT_S
        return cost
    if edge.type == "lift":
        cost = LIFT_PER_FLOOR_S * max(floors, 1)
        if a.type not in VERTICAL_TYPES:
            cost += LIFT_WAIT_S
        return cost
    if edge.type == "stairs" and floors:
        return STAIRS_PER_FLOOR_S * floors
    cost = edge.length_m / profile.speed_mps
    # Подходим к лифту: тут и тратится время на ожидание кабины
    cost += approach_wait(a, b)
    if edge.type == "ramp":
        cost *= 1.3
    elif edge.type == "door":
        cost += DOOR_S
    cost += edge.steps * STEP_S
    # Чем ближе к лимиту уклона, тем менее желателен пандус
    if profile.max_slope_pct and edge.slope_pct:
        cost *= 1 + 0.5 * (edge.slope_pct / profile.max_slope_pct)
    return cost


EdgeFilter = Callable[[GEdge], bool]


def dijkstra(graph: Graph, start: int, goal: int, allowed: EdgeFilter, profile: Profile,
             blocked_nodes: set[int] | frozenset = frozenset()) -> tuple[list[int], list[int], float] | None:
    dist: dict[int, float] = {start: 0.0}
    prev: dict[int, tuple[int, int]] = {}
    heap: list[tuple[float, int]] = [(0.0, start)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == goal:
            break
        if d > dist.get(u, math.inf):
            continue
        for v, eid in graph.adj.get(u, ()):
            if v in blocked_nodes and v != goal:
                continue
            edge = graph.edges[eid]
            if not allowed(edge):
                continue
            nd = d + traverse_cost(graph, edge, u, v, profile)
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = (u, eid)
                heapq.heappush(heap, (nd, v))
    if goal not in dist:
        return None
    nodes, edges = [goal], []
    cur = goal
    while cur != start:
        p, eid = prev[cur]
        nodes.append(p)
        edges.append(eid)
        cur = p
    nodes.reverse()
    edges.reverse()
    return nodes, edges, dist[goal]


# ---------- Поиск маршрута с диагностикой ----------

@dataclass
class Problem:
    kind: str  # constraint | obstacle
    code: str
    edge_id: int | None = None
    node_id: int | None = None
    obstacle: GObstacle | None = None
    value: float | None = None
    limit: float | None = None


@dataclass
class RouteResult:
    found: bool
    node_ids: list[int] = field(default_factory=list)
    edge_ids: list[int] = field(default_factory=list)
    cost_s: float = 0.0
    reason: str | None = None
    problems: list[Problem] = field(default_factory=list)
    warnings: list[Problem] = field(default_factory=list)


def find_route(graph: Graph, start: int, goal: int, profile: Profile, now: datetime) -> RouteResult:
    obst = obstacle_state(graph, now)

    for nid, code in ((start, "start_blocked"), (goal, "goal_blocked")):
        if nid in obst.blocked_nodes:
            return RouteResult(False, reason=code,
                               problems=[Problem("obstacle", obst.blocked_nodes[nid].type, node_id=nid,
                                                 obstacle=obst.blocked_nodes[nid])])

    if start == goal:
        return RouteResult(True, [start], [], 0.0)

    blocked_nodes = set(obst.blocked_nodes)

    def ok_profile(e: GEdge) -> bool:
        return not profile_violations(e, profile, obst)

    def ok_obstacles(e: GEdge) -> bool:
        return e.id not in obst.blocked_edges

    path = dijkstra(graph, start, goal, lambda e: ok_profile(e) and ok_obstacles(e), profile, blocked_nodes)
    if path:
        nodes, edges, cost = path
        return RouteResult(True, nodes, edges, cost, warnings=_warnings(graph, edges, profile, obst))

    # Пути нет: выясняем почему, чтобы честно объяснить пользователю
    any_path = dijkstra(graph, start, goal, lambda e: True, profile)
    if any_path is None:
        return RouteResult(False, reason="not_connected")

    profile_only = dijkstra(graph, start, goal, ok_profile, profile)
    if profile_only:
        return RouteResult(False, reason="blocked_by_obstacles",
                           problems=_obstacle_problems(graph, profile_only[1], obst))

    obstacles_only = dijkstra(graph, start, goal, ok_obstacles, profile, blocked_nodes)
    if obstacles_only:
        return RouteResult(False, reason="no_accessible_path",
                           problems=_constraint_problems(graph, obstacles_only[1], profile, obst))

    return RouteResult(False, reason="no_accessible_path_and_obstacles",
                       problems=_constraint_problems(graph, any_path[1], profile, obst)
                       + _obstacle_problems(graph, any_path[1], obst))


def _constraint_problems(graph: Graph, edge_ids: list[int], profile: Profile, obst: ObstacleState) -> list[Problem]:
    out = []
    for eid in edge_ids:
        for v in profile_violations(graph.edges[eid], profile, obst):
            out.append(Problem("constraint", v.code, edge_id=eid, value=v.value, limit=v.limit))
    return out


def _obstacle_problems(graph: Graph, edge_ids: list[int], obst: ObstacleState) -> list[Problem]:
    out, seen = [], set()
    for eid in edge_ids:
        o = obst.edge_blocker(graph, eid)
        if o and o.id not in seen:
            seen.add(o.id)
            out.append(Problem("obstacle", o.type, edge_id=eid, node_id=o.node_id, obstacle=o))
    return out


def _warnings(graph: Graph, edge_ids: list[int], profile: Profile, obst: ObstacleState) -> list[Problem]:
    out = []
    for eid in edge_ids:
        e = graph.edges[eid]
        if profile.min_width_cm and effective_width(e, obst) is None and e.type not in VERTICAL_TYPES:
            out.append(Problem("warning", "width_unknown", edge_id=eid, limit=profile.min_width_cm))
        if eid in obst.narrowed_edges:
            width, o = obst.narrowed_edges[eid]
            out.append(Problem("warning", "narrowed", edge_id=eid, obstacle=o, value=width))
    return out
