"""Интеграционные тесты API на демо-здании (SQLite вместо PostgreSQL)."""


async def route(client, a, b, profile="default", lang="ru", **extra):
    r = await client.post(f"/route?lang={lang}", json={"from_node": a, "to_node": b, "profile": profile, **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Авторизация ----------

async def test_login_wrong_password(client):
    r = await client.post("/auth/login", data={"username": "admin@test.kz", "password": "wrong-password"})
    assert r.status_code == 401


async def test_write_requires_token(client):
    r = await client.post("/buildings", json={"name": "X"})
    assert r.status_code == 401
    r = await client.post("/buildings", json={"name": "X"}, headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_editor_cannot_manage_users(client, editor_h, admin_h):
    assert (await client.get("/users", headers=editor_h)).status_code == 403
    assert (await client.get("/users", headers=admin_h)).status_code == 200


async def test_editor_cannot_delete_building(client, editor_h, demo):
    r = await client.delete(f"/buildings/{demo['building_id']}", headers=editor_h)
    assert r.status_code == 403


async def test_me(client, editor_h):
    r = await client.get("/auth/me", headers=editor_h)
    assert r.json()["role"] == "editor"


# ---------- Чтение ----------

async def test_buildings_and_floors(client, demo):
    r = await client.get("/buildings")
    assert r.json()["total"] >= 1
    floors = (await client.get(f"/buildings/{demo['building_id']}/floors")).json()
    assert [f["level"] for f in floors] == [1, 2, 3]
    detail = (await client.get(f"/floors/{floors[0]['id']}")).json()
    assert any(n["name"] == "Библиотека" for n in detail["nodes"])
    assert all(e["effective_length_m"] is not None for e in detail["edges"])
    # Вертикальные рёбра этажа тоже отдаются, чтобы фронт мог нарисовать переходы
    assert any(e["type"] == "elevator" for e in detail["edges"])


async def test_graph_export(client, demo):
    g = (await client.get(f"/buildings/{demo['building_id']}/graph")).json()
    assert len(g["floors"]) == 3 and len(g["nodes"]) > 20


async def test_profiles(client):
    r = await client.get("/profiles?lang=kk")
    ids = {p["id"]: p for p in r.json()}
    assert ids["wheelchair"]["params"]["min_width_cm"] == 90
    assert ids["wheelchair"]["title"] == "Мүгедектер арбасы"


async def test_search(client, demo):
    hits = (await client.get("/search", params={"q": "204"})).json()
    assert hits[0]["node_id"] == demo["r204"]
    hits = (await client.get("/search", params={"q": "библ"})).json()
    assert hits and hits[0]["node_id"] == demo["r105"]
    # Спецсимволы LIKE экранируются и не находят всё подряд
    assert (await client.get("/search", params={"q": "%"})).json() == []
    assert (await client.get("/search", params={"q": "x" * 101})).status_code == 422


# ---------- Маршруты ----------

async def test_default_vs_wheelchair(client, demo):
    plain = await route(client, demo["r105"], demo["r204"])
    wheel = await route(client, demo["r105"], demo["r204"], "wheelchair")
    assert plain["found"] and wheel["found"]
    plain_actions = [s["action"] for s in plain["steps"]]
    wheel_actions = [s["action"] for s in wheel["steps"]]
    assert "stairs_up" in plain_actions and "elevator_up" not in plain_actions
    assert "elevator_up" in wheel_actions and "stairs_up" not in wheel_actions
    assert plain["floors"] == [1, 2] and wheel["floors"] == [1, 2]
    assert wheel["steps"][-1]["text"] == "Вы на месте: «Компьютерный класс (204)»"
    # Рёбра отдаются по ходу маршрута
    for i, e in enumerate(wheel["edges"]):
        assert e["from_node_id"] == wheel["nodes"][i]["id"]


async def test_route_languages(client, demo):
    kk = await route(client, demo["r105"], demo["r204"], "wheelchair", lang="kk")
    en = await route(client, demo["r105"], demo["r204"], "wheelchair", lang="en")
    assert any(s["text"] == "Лифтпен 2-қабатқа көтеріліңіз" for s in kk["steps"])
    assert any(s["text"] == "Take the elevator up to floor 2" for s in en["steps"])


async def test_narrow_lab_is_honestly_unreachable(client, demo):
    res = await route(client, demo["r105"], demo["r210"], "wheelchair")
    assert not res["found"]
    assert res["reason"]["code"] == "no_accessible_path"
    detail = res["reason"]["details"][0]
    assert detail["code"] == "too_narrow" and detail["value"] == 70
    assert "70 см" in detail["message"] and "90 см" in detail["message"]


async def test_deanery_lift_vs_steps(client, demo):
    plain = await route(client, demo["r105"], demo["r305"])
    wheel = await route(client, demo["r105"], demo["r305"], "wheelchair")
    assert "steps" in [s["action"] for s in plain["steps"]]
    assert "lift_same" in [s["action"] for s in wheel["steps"]]


async def test_main_entrance_has_steps(client, demo):
    res = await route(client, demo["ent_main"], demo["r105"], "wheelchair")
    assert not res["found"]
    assert res["reason"]["details"][0]["code"] in ("steps", "stairs")
    res = await route(client, demo["ent_side"], demo["r105"], "wheelchair")
    assert res["found"] and "ramp" in [s["action"] for s in res["steps"]]


async def test_overrides(client, demo):
    res = await route(client, demo["r105"], demo["r210"], "wheelchair", overrides={"min_width_cm": 65})
    assert res["found"] and res["params"]["min_width_cm"] == 65


async def test_unknown_node(client, demo):
    r = await client.post("/route", json={"from_node": demo["r105"], "to_node": 999999})
    assert r.status_code == 404


async def test_bad_profile(client, demo):
    r = await client.post("/route", json={"from_node": demo["r105"], "to_node": demo["r204"], "profile": "rocket"})
    assert r.status_code == 422


# ---------- Препятствия ----------

async def test_obstacle_lifecycle(client, editor_h, demo):
    r = await client.post("/obstacles", headers=editor_h, json={
        "node_id": demo["el1"], "type": "elevator_broken", "description": "Ждём запчасть",
    })
    assert r.status_code == 201, r.text
    oid = r.json()["id"]

    wheel = await route(client, demo["r105"], demo["r204"], "wheelchair")
    assert not wheel["found"]
    assert wheel["reason"]["code"] == "blocked_by_obstacles"
    d = wheel["reason"]["details"][0]
    assert d["obstacle_id"] == oid and "лифт не работает: Ждём запчасть" in d["message"]
    # Обычный маршрут по лестнице не меняется
    assert (await route(client, demo["r105"], demo["r204"]))["found"]

    active = (await client.get("/obstacles", params={"building_id": demo["building_id"]})).json()
    assert any(o["id"] == oid for o in active["items"])

    r = await client.patch(f"/obstacles/{oid}", headers=editor_h, json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert (await route(client, demo["r105"], demo["r204"], "wheelchair"))["found"]
    assert (await client.delete(f"/obstacles/{oid}", headers=editor_h)).status_code == 204


async def test_obstacle_needs_one_target(client, editor_h, demo):
    r = await client.post("/obstacles", headers=editor_h, json={"type": "repair"})
    assert r.status_code == 422
    r = await client.post("/obstacles", headers=editor_h,
                          json={"type": "repair", "node_id": demo["r101"], "edge_id": 1})
    assert r.status_code == 422


# ---------- CRUD и кэш графа ----------

async def test_crud_updates_routes(client, editor_h, demo):
    floors = (await client.get(f"/buildings/{demo['building_id']}/floors")).json()
    f2 = floors[1]["id"]
    r = await client.post("/nodes", headers=editor_h,
                          json={"floor_id": f2, "type": "room", "name": "Новая аудитория", "ref": "220", "x": 700, "y": 150})
    assert r.status_code == 201
    new_id = r.json()["id"]

    res = await route(client, demo["r105"], new_id)
    assert res["reason"]["code"] == "not_connected"

    r = await client.post("/edges", headers=editor_h,
                          json={"from_node_id": demo["c2_wc"], "to_node_id": new_id, "type": "door", "width_cm": 100})
    assert r.status_code == 201
    edge = r.json()
    assert edge["length_m"] is None and edge["effective_length_m"] == 7.5  # 150 px * 0.05

    assert (await route(client, demo["r105"], new_id, "wheelchair"))["found"]

    r = await client.patch(f"/edges/{edge['id']}", headers=editor_h, json={"width_cm": 60})
    assert r.json()["width_cm"] == 60
    assert not (await route(client, demo["r105"], new_id, "wheelchair"))["found"]

    assert (await client.delete(f"/nodes/{new_id}", headers=editor_h)).status_code == 204
    assert (await client.get(f"/edges/{edge['id']}")).status_code == 404


async def test_edge_between_buildings_rejected(client, editor_h, demo):
    b = (await client.post("/buildings", headers=editor_h, json={"name": "Другое здание"})).json()
    f = (await client.post(f"/buildings/{b['id']}/floors", headers=editor_h, json={"level": 1})).json()
    n = (await client.post("/nodes", headers=editor_h,
                           json={"floor_id": f["id"], "type": "room", "name": "Каб", "x": 1, "y": 1})).json()
    r = await client.post("/edges", headers=editor_h,
                          json={"from_node_id": demo["r105"], "to_node_id": n["id"], "type": "corridor"})
    assert r.status_code == 400
    res = await route(client, demo["r105"], n["id"])
    assert res["reason"]["code"] == "different_buildings"
    dup = await client.post(f"/buildings/{b['id']}/floors", headers=editor_h, json={"level": 1})
    assert dup.status_code == 409


async def test_import_validation(client, editor_h):
    bad = {"name": "Плохое", "graph": {
        "floors": [{"key": "f1", "level": 1}],
        "nodes": [{"key": "a", "floor": "f9", "type": "room", "x": 0, "y": 0}],
        "edges": [{"from": "a", "to": "zzz", "type": "corridor"}],
    }}
    r = await client.post("/buildings/import", headers=editor_h, json=bad)
    assert r.status_code == 422
    assert any("f9" in e for e in r.json()["detail"])


async def test_pagination_limits(client):
    assert (await client.get("/nodes", params={"limit": 1000})).status_code == 422
    r = (await client.get("/nodes", params={"limit": 5})).json()
    assert len(r["items"]) == 5 and r["total"] > 5


# ---------- Маршрут с улицы (без ключей внешних API) ----------

async def test_full_route_picks_accessible_entrance(client, demo):
    near_main = {"lat": 51.0905, "lon": 71.4181}
    r = await client.post("/route/full", json={"from_location": near_main, "to_node": demo["r204"],
                                               "profile": "wheelchair"})
    body = r.json()
    assert r.status_code == 200 and body["found"]
    assert body["entrance"]["id"] == demo["ent_side"]
    assert body["outdoor"]["provider"] == "straight_line"
    assert body["notices"]

    r = await client.post("/route/full", json={"from_location": near_main, "to_node": demo["r204"]})
    assert r.json()["entrance"]["id"] == demo["ent_main"]


async def test_integrations_status(client):
    assert (await client.get("/integrations/status")).json() == {"dgis": False, "ors": False}


async def test_dgis_search_needs_editor(client):
    assert (await client.get("/integrations/2gis/buildings", params={"q": "college"})).status_code == 401
