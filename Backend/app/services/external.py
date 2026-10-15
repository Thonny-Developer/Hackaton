"""Клиенты внешних API: 2GIS (здания, пеший маршрут) и OpenRouteService (маршрут для коляски).

Ключи живут только на сервере. Ответы кэшируются в памяти, чтобы не тратить квоту
на одинаковые запросы.
"""

import logging
import math
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import httpx

from app.config import get_settings
from app.services.profiles import Profile

log = logging.getLogger(__name__)

DGIS_CATALOG = "https://catalog.api.2gis.com/3.0/items"
DGIS_ROUTING = "https://routing.api.2gis.com/routing/7.0.0/global"
ORS_WHEELCHAIR = "https://api.openrouteservice.org/v2/directions/wheelchair/geojson"


class ExternalError(Exception):
    pass


@dataclass
class ExtBuilding:
    external_id: str
    name: str
    address: str | None
    lat: float | None
    lon: float | None


@dataclass
class OutdoorStep:
    text: str
    distance_m: float


@dataclass
class OutdoorRoute:
    provider: str  # 2gis | ors
    accessibility_checked: bool
    distance_m: float
    duration_s: float
    geometry: list[list[float]] = field(default_factory=list)  # [[lon, lat], ...]
    steps: list[OutdoorStep] = field(default_factory=list)


class _TTLCache:
    def __init__(self, maxsize: int = 1000, ttl: float = 600):
        self.maxsize, self.ttl = maxsize, ttl
        self.data: OrderedDict = OrderedDict()

    def get(self, key):
        item = self.data.get(key)
        if item is None or item[0] < time.monotonic():
            self.data.pop(key, None)
            return None
        self.data.move_to_end(key)
        return item[1]

    def set(self, key, value):
        self.data[key] = (time.monotonic() + self.ttl, value)
        self.data.move_to_end(key)
        while len(self.data) > self.maxsize:
            self.data.popitem(last=False)


_cache = _TTLCache()
_client: httpx.AsyncClient | None = None


def http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=get_settings().external_timeout_s,
                                    limits=httpx.Limits(max_connections=20))
    return _client


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _dgis_key() -> str:
    key = get_settings().dgis_api_key
    if not key:
        raise ExternalError("Ключ 2GIS не настроен (DGIS_API_KEY)")
    return key


def _parse_item(it: dict) -> ExtBuilding:
    point = it.get("point") or {}
    return ExtBuilding(
        external_id=str(it["id"]),
        name=it.get("name") or it.get("full_name") or it.get("address_name") or "Здание",
        address=it.get("address_name") or it.get("full_address_name"),
        lat=point.get("lat"),
        lon=point.get("lon"),
    )


async def _dgis_items(url: str, params: dict) -> list[dict]:
    try:
        r = await http().get(url, params=params)
    except httpx.HTTPError as exc:
        raise ExternalError(f"2GIS недоступен: {exc.__class__.__name__}") from None
    if r.status_code != 200:
        raise ExternalError(f"2GIS ответил {r.status_code}")
    body = r.json()
    code = (body.get("meta") or {}).get("code", 200)
    if code == 404:
        return []
    if code != 200:
        raise ExternalError(f"2GIS: {(body.get('meta') or {}).get('error', {}).get('message', code)}")
    return (body.get("result") or {}).get("items") or []


async def dgis_search_buildings(q: str, lat: float | None, lon: float | None, locale: str) -> list[ExtBuilding]:
    params = {"q": q, "type": "building", "fields": "items.point,items.address", "page_size": 10,
              "locale": locale, "key": _dgis_key()}
    if lat is not None and lon is not None:
        params["location"] = f"{lon},{lat}"
    cache_key = ("search", q.lower(), lat and round(lat, 3), lon and round(lon, 3), locale)
    if (hit := _cache.get(cache_key)) is not None:
        return hit
    items = [_parse_item(it) for it in await _dgis_items(DGIS_CATALOG, params) if it.get("id")]
    _cache.set(cache_key, items)
    return items


async def dgis_get_building(external_id: str, locale: str) -> ExtBuilding | None:
    params = {"id": external_id, "fields": "items.point,items.address", "locale": locale, "key": _dgis_key()}
    items = await _dgis_items(f"{DGIS_CATALOG}/byid", params)
    return _parse_item(items[0]) if items else None


_WKT_POINT = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")


def _wkt_coords(wkt: str) -> list[list[float]]:
    return [[float(a), float(b)] for a, b in _WKT_POINT.findall(wkt or "")]


async def dgis_walk_route(src: tuple[float, float], dst: tuple[float, float], lang: str) -> OutdoorRoute:
    cache_key = ("2gis", round(src[0], 5), round(src[1], 5), round(dst[0], 5), round(dst[1], 5), lang)
    if (hit := _cache.get(cache_key)) is not None:
        return hit
    body = {
        "points": [{"type": "walking", "lat": src[0], "lon": src[1]}, {"type": "walking", "lat": dst[0], "lon": dst[1]}],
        "transport": "walking",
        "locale": {"ru": "ru", "kk": "kk", "en": "en"}.get(lang, "ru"),
    }
    try:
        r = await http().post(DGIS_ROUTING, params={"key": _dgis_key()}, json=body)
    except httpx.HTTPError as exc:
        raise ExternalError(f"2GIS Routing недоступен: {exc.__class__.__name__}") from None
    if r.status_code != 200:
        raise ExternalError(f"2GIS Routing ответил {r.status_code}")
    data = r.json()
    results = data.get("result") or []
    if not results:
        raise ExternalError("2GIS не нашёл пеший маршрут")
    best = results[0]
    geometry: list[list[float]] = []
    steps: list[OutdoorStep] = []
    for m in best.get("maneuvers") or []:
        path = m.get("outcoming_path") or {}
        for g in path.get("geometry") or []:
            geometry.extend(_wkt_coords(g.get("selection", "")))
        text = m.get("comment") or m.get("outcoming_path_comment")
        if text:
            steps.append(OutdoorStep(text=text, distance_m=float(path.get("distance") or 0)))
    route = OutdoorRoute("2gis", False, float(best.get("total_distance") or 0), float(best.get("total_duration") or 0),
                         geometry, steps)
    _cache.set(cache_key, route)
    return route


def _ors_restrictions(p: Profile) -> dict:
    """ORS принимает только фиксированные значения, поэтому округляем в строгую сторону."""
    restrictions: dict = {}
    if p.max_slope_pct is not None:
        allowed = [v for v in (3, 6, 10, 15) if v <= p.max_slope_pct]
        restrictions["maximum_incline"] = allowed[-1] if allowed else 3
    if p.max_threshold_cm is not None:
        # Порог внутри здания и бордюр на улице не одно и то же, но 3 см это минимум, который принимает ORS
        cm = p.max_threshold_cm
        restrictions["maximum_sloped_kerb"] = 0.03 if cm <= 3 else 0.06 if cm <= 6 else 0.1
    if p.min_width_cm:
        restrictions["minimum_width"] = round(p.min_width_cm / 100, 2)
    return restrictions


async def ors_wheelchair_route(src: tuple[float, float], dst: tuple[float, float], profile: Profile,
                               lang: str) -> OutdoorRoute:
    key = get_settings().ors_api_key
    if not key:
        raise ExternalError("Ключ OpenRouteService не настроен (ORS_API_KEY)")
    restrictions = _ors_restrictions(profile)
    cache_key = ("ors", round(src[0], 5), round(src[1], 5), round(dst[0], 5), round(dst[1], 5), lang,
                 tuple(sorted(restrictions.items())))
    if (hit := _cache.get(cache_key)) is not None:
        return hit
    body = {
        "coordinates": [[src[1], src[0]], [dst[1], dst[0]]],
        "instructions": True,
        "language": "ru" if lang in ("ru", "kk") else "en",
        "options": {"profile_params": {"restrictions": restrictions}},
    }
    try:
        r = await http().post(ORS_WHEELCHAIR, json=body, headers={"Authorization": key})
    except httpx.HTTPError as exc:
        raise ExternalError(f"OpenRouteService недоступен: {exc.__class__.__name__}") from None
    if r.status_code == 404 or (r.status_code == 400 and "route" in r.text.lower()):
        raise ExternalError("OpenRouteService не нашёл доступный уличный маршрут")
    if r.status_code != 200:
        raise ExternalError(f"OpenRouteService ответил {r.status_code}")
    feature = (r.json().get("features") or [{}])[0]
    props = feature.get("properties") or {}
    summary = props.get("summary") or {}
    steps = [OutdoorStep(s.get("instruction", ""), float(s.get("distance") or 0))
             for seg in props.get("segments") or [] for s in seg.get("steps") or []]
    route = OutdoorRoute("ors", True, float(summary.get("distance") or 0), float(summary.get("duration") or 0),
                         (feature.get("geometry") or {}).get("coordinates") or [], steps)
    _cache.set(cache_key, route)
    return route
