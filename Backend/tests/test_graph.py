"""Юнит-тесты движка маршрутизации без БД и HTTP."""

from datetime import UTC, datetime, timedelta

from app.services.graph import GEdge, GNode, GObstacle, Graph, find_route
from app.services.instructions import build_steps
from app.services.profiles import PRESETS, ProfileOverrides, resolve_profile

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
DEFAULT = PRESETS["default"]["profile"]
WHEEL = PRESETS["wheelchair"]["profile"]


def make_graph(obstacles=()) -> Graph:
    """Два этажа: A (1 эт.) -> коридор -> лестница рядом / лифт подальше -> B (2 эт.)."""
    g = Graph(building_id=1, version=1)
    nodes = [
        GNode(1, 10, 1, "room", "Аудитория", "101", 0, 0),
        GNode(2, 10, 1, "corridor", None, None, 0, 100),
        GNode(3, 10, 1, "stairs", "Лестница", None, 50, 100),
        GNode(4, 10, 1, "elevator", "Лифт", None, 400, 100),
        GNode(5, 20, 2, "stairs", "Лестница", None, 50, 100),
        GNode(6, 20, 2, "elevator", "Лифт", None, 400, 100),
        GNode(7, 20, 2, "corridor", None, None, 200, 100),
        GNode(8, 20, 2, "room", "Аудитория", "204", 200, 0),
        GNode(9, 20, 2, "room", "Лаборатория", "210", 300, 0),
        GNode(10, 10, 1, "room", "Изолированная", "999", 900, 900),
    ]
    edges = [
        GEdge(1, 1, 2, "door", 5, width_cm=90),
        GEdge(2, 2, 3, "corridor", 2.5, width_cm=200),
        GEdge(3, 2, 4, "corridor", 20, width_cm=200),
        GEdge(4, 3, 5, "stairs", 3.5, width_cm=140, steps=20),
        GEdge(5, 4, 6, "elevator", 3.5, width_cm=100),
        GEdge(6, 5, 7, "corridor", 7.5, width_cm=200),
        GEdge(7, 6, 7, "corridor", 10, width_cm=200),
        GEdge(8, 7, 8, "door", 5, width_cm=90),
        GEdge(9, 7, 9, "door", 5, width_cm=70),
    ]
    g.nodes = {n.id: n for n in nodes}
    g.edges = {e.id: e for e in edges}
    g.obstacles = list(obstacles)
    g.build_index()
    return g


def test_default_takes_stairs_wheelchair_takes_elevator():
    g = make_graph()
    plain = find_route(g, 1, 8, DEFAULT, NOW)
    wheel = find_route(g, 1, 8, WHEEL, NOW)
    assert plain.found and 4 in plain.edge_ids
    assert wheel.found and 5 in wheel.edge_ids and 4 not in wheel.edge_ids


def test_broken_elevator_is_reported():
    g = make_graph([GObstacle(1, "elevator_broken", node_id=6, description="Ремонт до пятницы")])
    res = find_route(g, 1, 8, WHEEL, NOW)
    assert not res.found
    assert res.reason == "blocked_by_obstacles"
    assert res.problems[0].obstacle.id == 1
    # Обычному пользователю сломанный лифт не мешает
    assert find_route(g, 1, 8, DEFAULT, NOW).found


def test_narrow_door_gives_constraint_reason():
    res = find_route(make_graph(), 1, 9, WHEEL, NOW)
    assert not res.found and res.reason == "no_accessible_path"
    assert any(p.code == "too_narrow" and p.value == 70 and p.limit == 90 for p in res.problems)


def test_not_connected():
    res = find_route(make_graph(), 1, 10, DEFAULT, NOW)
    assert not res.found and res.reason == "not_connected"


def test_obstacle_time_window():
    past = GObstacle(1, "elevator_broken", node_id=4, ends_at=NOW - timedelta(minutes=1))
    future = GObstacle(2, "elevator_broken", node_id=4, starts_at=NOW + timedelta(hours=1))
    assert find_route(make_graph([past, future]), 1, 8, WHEEL, NOW).found


def test_narrowed_passage():
    narrowed = GObstacle(1, "narrowed", edge_id=7, reduced_width_cm=80)
    g = make_graph([narrowed])
    assert not find_route(g, 1, 8, WHEEL, NOW).found
    res = find_route(g, 1, 8, resolve_profile("default", ProfileOverrides(allow_stairs=False)), NOW)
    assert res.found and any(w.code == "narrowed" for w in res.warnings)


def test_blocked_goal():
    g = make_graph([GObstacle(1, "repair", node_id=8)])
    res = find_route(g, 1, 8, DEFAULT, NOW)
    assert res.reason == "goal_blocked"


def test_one_way_edge():
    g = make_graph()
    g.edges[1].bidirectional = False
    g.build_index()
    assert find_route(g, 1, 8, DEFAULT, NOW).found
    assert find_route(g, 8, 1, DEFAULT, NOW).reason == "not_connected"


def test_override_removes_limit():
    # Явный null снимает ограничение по ширине, двери 70 см становятся допустимы
    p = resolve_profile("wheelchair", ProfileOverrides.model_validate({"min_width_cm": None}))
    assert p.min_width_cm is None and p.allow_stairs is False
    assert find_route(make_graph(), 1, 9, p, NOW).found


def test_instructions_ru_and_turns():
    g = make_graph()
    res = find_route(g, 1, 8, WHEEL, NOW)
    steps = build_steps(g, res, WHEEL, "ru")
    actions = [s.action for s in steps]
    assert actions[0] == "start" and actions[-1] == "arrive"
    assert "elevator_up" in actions
    assert any(s.text == "Поднимитесь на лифте на 2 этаж" for s in steps)
    # 1 -> 2 идёт на юг (y растёт), затем 2 -> 4 на восток: на схеме это поворот налево
    assert "turn_left" in actions


def test_instructions_kk_en():
    g = make_graph()
    res = find_route(g, 1, 8, DEFAULT, NOW)
    kk = build_steps(g, res, DEFAULT, "kk")
    en = build_steps(g, res, DEFAULT, "en")
    assert any("қабатқа көтеріліңіз" in s.text for s in kk)
    assert any(s.text == "Take the stairs up to floor 2" for s in en)


def test_same_node():
    g = make_graph()
    res = find_route(g, 1, 1, DEFAULT, NOW)
    assert res.found and res.edge_ids == []
    assert build_steps(g, res, DEFAULT, "ru")[0].action == "arrive"


def test_elevator_wait_goes_to_elevator_step():
    g = make_graph()
    res = find_route(g, 1, 8, WHEEL, NOW)
    steps = build_steps(g, res, WHEEL, "ru")
    lift = next(s for s in steps if s.action == "elevator_up")
    assert lift.duration_s >= 30
    # Сумма шагов совпадает с общей оценкой времени
    assert abs(sum(s.duration_s for s in steps) - res.cost_s) < 1e-6
