"""Разбор ответов 2GIS на записанных образцах, без сети."""

import httpx
import pytest

from app.config import get_settings
from app.services import external

SUGGEST_BODY = {
    "meta": {"code": 200},
    "result": {"items": [
        {"type": "building", "id": "1", "name": "проспект Мангилик Ел, 55/1",
         "full_name": "Астана, проспект Мангилик Ел, 55/1", "address_name": "проспект Мангилик Ел, 55/1",
         "point": {"lat": 51.091184, "lon": 71.417607}},
        {"type": "user_query", "search_attributes": {"suggested_text": "мангилик ел 55"}},
        {"type": "branch", "id": "2", "name": "Хан Шатыр, торгово-развлекательный центр",
         "address_name": "проспект Туран, 37", "point": {"lat": 51.13213, "lon": 71.402828}},
        {"type": "brand", "id": "3", "name": "Хан Шатыр, торгово-развлекательный центр",
         "point": {"lat": 51.13213, "lon": 71.402828}},
    ]},
}

ROUTE_BODY = {
    "status": "OK",
    "result": [{
        "total_distance": 2104, "total_duration": 1683,
        "begin_pedestrian_path": {"geometry": {"selection": "LINESTRING(71.417606 51.091183, 71.417922 51.091512)"}},
        "end_pedestrian_path": {"geometry": {"selection": "LINESTRING(71.396078 51.090477, 71.395814 51.090674)"}},
        "maneuvers": [
            {"type": "begin", "comment": "start", "outcoming_path_comment": "2 км прямо",
             "outcoming_path": {"distance": 2061, "geometry": [
                 {"selection": "LINESTRING(71.417922 51.091512, 71.417111 51.091714)"},
                 {"selection": "LINESTRING(71.417111 51.091714, 71.396078 51.090477)"}]}},
            {"type": "crossroad", "comment": "Поворот налево на ул. Сыганак", "outcoming_path_comment": "40 м прямо",
             "outcoming_path": {"distance": 40, "geometry": []}},
            {"type": "end", "comment": "finish", "outcoming_path_comment": "Вы на месте!"},
        ],
    }],
}


@pytest.fixture
def fake_2gis(monkeypatch):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        body = SUGGEST_BODY if request.url.path.endswith("/suggests") else ROUTE_BODY
        return httpx.Response(200, json=body)

    monkeypatch.setattr(get_settings(), "dgis_api_key", "test-key")
    monkeypatch.setattr(external, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(external, "_cache", external._TTLCache())
    return sent


async def test_suggest_keeps_only_items_with_point(fake_2gis):
    items = await external.dgis_suggest("мангилик", 51.09, 71.41, "ru_KZ")
    assert [i.id for i in items] == ["1", "2"]
    # Адрес совпадает с названием, поэтому второй строкой идёт полное имя с городом
    assert items[0].address == "Астана, проспект Мангилик Ел, 55/1"
    assert items[1].address == "проспект Туран, 37"
    assert fake_2gis[0].url.params["location"] == "71.41,51.09"


async def test_walk_route_geometry_and_steps(fake_2gis):
    r = await external.dgis_walk_route((51.091184, 71.417607), (51.090675, 71.395815), "ru")
    assert r.distance_m == 2104 and r.duration_s == 1683
    assert r.geometry[0] == [71.417606, 51.091183] and r.geometry[-1] == [71.395814, 51.090674]
    assert [s.text for s in r.steps] == ["2 км прямо", "Поворот налево на ул. Сыганак", "Вы на месте!"]


async def test_walk_route_avoid_stairs_filter(fake_2gis):
    import json

    await external.dgis_walk_route((51.0, 71.0), (51.01, 71.01), "ru", avoid_stairs=True)
    await external.dgis_walk_route((51.0, 71.0), (51.01, 71.01), "ru")
    bodies = [json.loads(req.content) for req in fake_2gis]
    assert bodies[0]["filters"] == ["ban_stairway"]
    assert "filters" not in bodies[1]


async def test_outdoor_route_endpoint(client, fake_2gis):
    payload = {"from_location": {"lat": 51.091184, "lon": 71.417607},
               "to_location": {"lat": 51.090675, "lon": 71.395815}, "profile": "wheelchair"}
    r = await client.post("/route/outdoor", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route"]["provider"] == "2gis" and not body["route"]["accessibility_checked"]
    assert body["notices"]

    far = {**payload, "to_location": {"lat": 43.24, "lon": 76.89}}
    assert (await client.post("/route/outdoor", json=far)).status_code == 422


async def test_suggest_endpoint(client, fake_2gis):
    r = await client.get("/geo/suggest", params={"q": "мангилик", "lat": 51.09, "lon": 71.41})
    assert r.status_code == 200
    assert r.json()[1]["name"].startswith("Хан Шатыр")
