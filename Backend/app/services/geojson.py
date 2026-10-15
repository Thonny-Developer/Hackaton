"""GeoJSON для Mapbox: маршрут и этаж. Координаты в порядке [lon, lat]."""

from datetime import datetime

from app.services.graph import VERTICAL_TYPES, Graph, obstacle_state


def _fc(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _point(coords, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": coords}, "properties": props}


def _line(coords, **props) -> dict:
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": props}


def route_geojson(graph: Graph, node_ids: list[int]) -> dict | None:
    """Линия маршрута отдельно для каждого этажа (фильтруйте по properties.level),
    плюс точки start, finish и transition (смена этажа). None, если хоть один узел без координат."""
    nodes = [graph.nodes[i] for i in node_ids]
    coords = [graph.node_geo(n) for n in nodes]
    if not nodes or any(c is None for c in coords):
        return None

    features: list[dict] = []
    run_start = 0
    for i in range(1, len(nodes) + 1):
        if i == len(nodes) or nodes[i].floor_id != nodes[run_start].floor_id:
            run = coords[run_start:i]
            if len(run) >= 2:
                n = nodes[run_start]
                features.append(_line(run, kind="route", floor_id=n.floor_id, level=n.level))
            if i < len(nodes):
                a, b = nodes[i - 1], nodes[i]
                features.append(_point(coords[i - 1], kind="transition", floor_id=a.floor_id, level=a.level,
                                       to_level=b.level, node_id=a.id))
            run_start = i

    first, last = nodes[0], nodes[-1]
    features.append(_point(coords[0], kind="start", floor_id=first.floor_id, level=first.level, node_id=first.id,
                           name=first.label))
    features.append(_point(coords[-1], kind="finish", floor_id=last.floor_id, level=last.level, node_id=last.id,
                           name=last.label))
    return _fc(features)


def floor_geojson(graph: Graph, floor_id: int, now: datetime) -> dict:
    """Узлы этажа точками, переходы внутри этажа линиями. Перекрытые препятствиями помечены blocked=true."""
    obst = obstacle_state(graph, now)
    features: list[dict] = []
    level = graph.floors[floor_id].level if floor_id in graph.floors else None

    for n in graph.nodes.values():
        if n.floor_id != floor_id or (c := graph.node_geo(n)) is None:
            continue
        blocker = obst.blocked_nodes.get(n.id)
        if blocker is None and n.type in VERTICAL_TYPES:
            # Сломанный лифт перекрывает рёбра шахты, а на карте его удобно показать на самом узле
            blocker = next((obst.blocked_edges[eid] for eid in graph.incident.get(n.id, [])
                            if eid in obst.blocked_edges and graph.edges[eid].type in VERTICAL_TYPES), None)
        features.append(_point(
            c, kind="node", id=n.id, type=n.type, name=n.name, ref=n.ref, level=level,
            is_accessible_entrance=n.is_accessible_entrance,
            blocked=blocker is not None, obstacle_id=blocker.id if blocker else None,
        ))

    for e in graph.edges.values():
        a, b = graph.nodes[e.a], graph.nodes[e.b]
        if a.floor_id != floor_id or b.floor_id != floor_id:
            continue
        ca, cb = graph.node_geo(a), graph.node_geo(b)
        if ca is None or cb is None:
            continue
        blocker = obst.edge_blocker(graph, e.id)
        narrowed = obst.narrowed_edges.get(e.id)
        features.append(_line(
            [ca, cb], kind="edge", id=e.id, type=e.type, level=level, length_m=e.length_m,
            width_cm=e.width_cm, steps=e.steps, slope_pct=e.slope_pct, threshold_cm=e.threshold_cm,
            bidirectional=e.bidirectional, vertical=e.type in VERTICAL_TYPES,
            blocked=blocker is not None, obstacle_id=blocker.id if blocker else None,
            narrowed_to_cm=narrowed[0] if narrowed else None,
        ))
    return _fc(features)
