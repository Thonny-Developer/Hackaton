"""Превращает найденный путь в пошаговые инструкции, а проблемы в понятный текст."""

import math
from dataclasses import dataclass, field

from app.services.graph import VERTICAL_TYPES, GNode, Graph, Problem, RouteResult, approach_wait, traverse_cost
from app.services.i18n import NODE_TYPE_NAMES, OBSTACLE_NAMES, Lang, fmt_num, t
from app.services.profiles import Profile

TURN_THRESHOLD_DEG = 40
NAMED_TYPES = {"room", "entrance", "elevator", "stairs", "ramp", "lift", "toilet"}


@dataclass
class Step:
    action: str
    text: str
    floor_id: int
    level: int
    node_ids: list[int]
    edge_ids: list[int] = field(default_factory=list)
    distance_m: float = 0.0
    duration_s: float = 0.0
    to_level: int | None = None


def node_label(n: GNode, lang: Lang) -> str:
    return n.label or NODE_TYPE_NAMES[lang].get(n.type, n.type)


def _target_name(n: GNode, lang: Lang) -> str | None:
    if n.label:
        return n.label
    if n.type in NAMED_TYPES:
        return NODE_TYPE_NAMES[lang][n.type]
    return None


def _turn(p: GNode, q: GNode, r: GNode) -> str | None:
    v1 = (q.x - p.x, q.y - p.y)
    v2 = (r.x - q.x, r.y - q.y)
    if math.hypot(*v1) < 1e-6 or math.hypot(*v2) < 1e-6:
        return None
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    angle = math.degrees(math.atan2(cross, dot))
    if abs(angle) < TURN_THRESHOLD_DEG:
        return None
    # Ось y на схеме направлена вниз, поэтому положительный угол означает поворот направо
    return "turn_right" if angle > 0 else "turn_left"


def build_steps(graph: Graph, res: RouteResult, profile: Profile, lang: Lang) -> list[Step]:
    nodes = [graph.nodes[n] for n in res.node_ids]
    edges = [graph.edges[e] for e in res.edge_ids]
    first, last = nodes[0], nodes[-1]

    if not edges:
        return [Step("arrive", t(lang, "same_node", name=node_label(first, lang)), first.floor_id, first.level, [first.id])]

    steps = [Step("start", t(lang, "start", name=node_label(first, lang), level=first.level),
                  first.floor_id, first.level, [first.id])]

    def cost(k: int) -> float:
        # Ожидание лифта относим к шагу «лифт», а не к подходу к нему
        return (traverse_cost(graph, edges[k], nodes[k].id, nodes[k + 1].id, profile)
                - approach_wait(nodes[k], nodes[k + 1]))

    def wait_before(k: int) -> float:
        return approach_wait(nodes[k - 1], nodes[k]) if k > 0 else 0.0

    def is_vertical(k: int) -> bool:
        return edges[k].type in VERTICAL_TYPES or nodes[k].level != nodes[k + 1].level

    def is_special(k: int) -> bool:
        e = edges[k]
        return is_vertical(k) or e.type in ("ramp", "stairs") or e.steps > 0

    i = 0
    while i < len(edges):
        e, a = edges[i], nodes[i]

        if is_vertical(i):
            j = i
            while j + 1 < len(edges) and edges[j + 1].type == e.type and is_vertical(j + 1):
                j += 1
            end = nodes[j + 1]
            kind = e.type if e.type in ("elevator", "lift", "stairs", "ramp") else "stairs"
            if end.level == a.level:
                action = "lift_same" if kind == "lift" else "steps"
                text = t(lang, "lift_same") if kind == "lift" else t(lang, "steps", n=e.steps or "?")
            else:
                action = f"{kind}_{'up' if end.level > a.level else 'down'}"
                text = t(lang, action, to=end.level)
            steps.append(Step(action, text, a.floor_id, a.level, [n.id for n in nodes[i:j + 2]],
                              [x.id for x in edges[i:j + 1]], sum(x.length_m for x in edges[i:j + 1]),
                              wait_before(i) + sum(cost(k) for k in range(i, j + 1)), to_level=end.level))
            i = j + 1
            continue

        if e.type == "ramp":
            j = i
            while j + 1 < len(edges) and edges[j + 1].type == "ramp" and not is_vertical(j + 1):
                j += 1
            dist = sum(x.length_m for x in edges[i:j + 1])
            steps.append(Step("ramp", t(lang, "ramp", dist=round(dist)), a.floor_id, a.level,
                              [n.id for n in nodes[i:j + 2]], [x.id for x in edges[i:j + 1]], dist,
                              sum(cost(k) for k in range(i, j + 1))))
            i = j + 1
            continue

        if e.type == "stairs" or e.steps > 0:
            steps.append(Step("steps", t(lang, "steps", n=e.steps or "?"), a.floor_id, a.level,
                              [a.id, nodes[i + 1].id], [e.id], e.length_m, cost(i)))
            i += 1
            continue

        # Обычный проход: склеиваем рёбра, пока нет поворота или особого участка
        j, turn = i, None
        while True:
            if j + 1 >= len(edges):
                break
            turn = _turn(nodes[j], nodes[j + 1], nodes[j + 2]) if not is_vertical(j + 1) else None
            if turn or is_special(j + 1):
                break
            j += 1
        end = nodes[j + 1]
        dist = sum(x.length_m for x in edges[i:j + 1])
        if dist >= 1:
            name = _target_name(end, lang) if (turn or j + 1 == len(edges) or is_special(j + 1)) else None
            text = t(lang, "walk_to", dist=round(dist), name=name) if name else t(lang, "walk", dist=round(dist))
            steps.append(Step("walk", text, a.floor_id, a.level, [n.id for n in nodes[i:j + 2]],
                              [x.id for x in edges[i:j + 1]], dist, sum(cost(k) for k in range(i, j + 1))))
        if turn:
            steps.append(Step(turn, t(lang, turn), end.floor_id, end.level, [end.id]))
        i = j + 1

    steps.append(Step("arrive", t(lang, "arrive", name=node_label(last, lang)), last.floor_id, last.level, [last.id]))
    return steps


def _where(graph: Graph, p: Problem, lang: Lang) -> str:
    if p.edge_id is not None and p.edge_id in graph.edges:
        e = graph.edges[p.edge_id]
        a, b = graph.nodes[e.a], graph.nodes[e.b]
        if a.level != b.level:
            lo, hi = sorted((a.level, b.level))
            return t(lang, "where_floors", a=lo, b=hi)
        for n in (a, b):
            if n.label:
                return t(lang, "where_node", name=n.label)
        return t(lang, "where_floor", level=a.level)
    if p.node_id is not None and p.node_id in graph.nodes:
        n = graph.nodes[p.node_id]
        return t(lang, "where_node", name=node_label(n, lang))
    return ""


def problem_message(graph: Graph, p: Problem, lang: Lang) -> str:
    where = _where(graph, p, lang)
    if p.kind == "obstacle":
        o = p.obstacle
        desc = f": {o.description}" if o and o.description else ""
        return t(lang, "p_obstacle", kind=OBSTACLE_NAMES[lang].get(p.code, p.code), desc=desc, where=where)
    if p.kind == "warning":
        return t(lang, f"w_{p.code}", value=fmt_num(p.value), where=where)
    return t(lang, f"p_{p.code}", value=fmt_num(p.value), limit=fmt_num(p.limit), where=where)
