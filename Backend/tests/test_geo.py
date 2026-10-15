"""Привязка схемы к карте и GeoJSON для Mapbox."""

import pytest

from app.services.external import haversine_m
from app.services.geo import to_lonlat

O = (51.0, 71.0)


def test_origin_and_scale():
    assert to_lonlat(0, 0, 0.05, *O, 0) == [71.0, 51.0]
    lon, lat = to_lonlat(2000, 0, 0.05, *O, 0)  # 100 м на восток
    assert lat == pytest.approx(51.0) and haversine_m(51.0, 71.0, lat, lon) == pytest.approx(100, abs=0.1)
    lon, lat = to_lonlat(0, 2000, 0.05, *O, 0)  # y вниз по схеме = на юг
    assert lat < 51.0 and lon == pytest.approx(71.0)


def test_rotation_clockwise():
    # Поворот на 90° по часовой: ось x схемы смотрит на юг
    lon, lat = to_lonlat(2000, 0, 0.05, *O, 90)
    assert lon == pytest.approx(71.0, abs=1e-7) and lat < 51.0


def test_not_georeferenced():
    assert to_lonlat(10, 10, 0.05, None, None, 0) is None


async def test_nodes_have_geo(client, demo):
    n = (await client.get(f"/nodes/{demo['ent_side']}")).json()
    assert n["lat"] is None and n["geo"] is not None
    hit = (await client.get("/search", params={"q": "204"})).json()[0]
    assert len(hit["geo"]) == 2


async def test_floor_geojson(client, editor_h, demo):
    floors = (await client.get(f"/buildings/{demo['building_id']}/floors")).json()
    f1 = floors[0]
    assert f1["geo_origin_lat"] == 51.09115 and f1["plan_corners"] is None  # схема ещё не загружена
    fc = (await client.get(f"/floors/{f1['id']}/geojson")).json()
    kinds = {f["properties"]["kind"] for f in fc["features"]}
    assert fc["type"] == "FeatureCollection" and kinds == {"node", "edge"}

    o = (await client.post("/obstacles", headers=editor_h,
                           json={"node_id": demo["el1"], "type": "elevator_broken"})).json()
    fc = (await client.get(f"/floors/{f1['id']}/geojson")).json()
    lift = next(f for f in fc["features"] if f["properties"].get("id") == demo["el1"] and f["properties"]["kind"] == "node")
    assert lift["properties"]["blocked"] and lift["properties"]["obstacle_id"] == o["id"]
    await client.delete(f"/obstacles/{o['id']}", headers=editor_h)


async def test_floor_without_georef(client, editor_h):
    b = (await client.post("/buildings", headers=editor_h, json={"name": "Без привязки"})).json()
    f = (await client.post(f"/buildings/{b['id']}/floors", headers=editor_h, json={"level": 1})).json()
    assert (await client.get(f"/floors/{f['id']}/geojson")).status_code == 409
    r = await client.patch(f"/floors/{f['id']}", headers=editor_h,
                           json={"geo_origin_lat": 51.1, "geo_origin_lon": 71.4, "geo_rotation_deg": 15})
    assert r.json()["geo_rotation_deg"] == 15
    assert (await client.get(f"/floors/{f['id']}/geojson")).status_code == 200


async def test_route_geojson(client, demo):
    r = (await client.post("/route", json={"from_node": demo["r105"], "to_node": demo["r204"],
                                           "profile": "wheelchair"})).json()
    feats = r["geojson"]["features"]
    lines = [f for f in feats if f["properties"]["kind"] == "route"]
    assert [f["properties"]["level"] for f in lines] == [1, 2]
    assert {f["properties"]["kind"] for f in feats} == {"route", "transition", "start", "finish"}
    assert all(n["geo"] for n in r["nodes"])
