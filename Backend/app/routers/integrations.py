"""Этап 2: здания и подсказки адресов из 2GIS, уличный маршрут и маршрут «улица → доступный вход → аудитория»."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import get_settings
from app.deps import SessionDep, get_or_404
from app.models import Building, Node, NodeType
from app.ratelimit import limiter
from app.routers.route import LangQuery, render_route
from app.schemas import BuildingOut, Lat, Lon, ProfileName, RouteNode, RouteResponse
from app.security import EditorUser
from app.services import external
from app.services.graph import find_route
from app.services.graph_cache import get_graph
from app.services.i18n import normalize_lang
from app.services.profiles import ProfileOverrides, resolve_profile

router = APIRouter(tags=["integrations"])
_s = get_settings()

DGIS_LOCALES = {"ru": "ru_KZ", "kk": "kk_KZ", "en": "en_KZ"}
# Дальше пешком не ходят, а запрос к 2GIS всё равно тратит квоту
MAX_WALK_M = 30_000


class IntegrationStatus(BaseModel):
    dgis: bool
    ors: bool


class ExtBuildingOut(BaseModel):
    external_id: str
    name: str
    address: str | None
    lat: float | None
    lon: float | None


class DgisImportRequest(BaseModel):
    external_id: str = Field(min_length=1, max_length=128)
    name: str | None = Field(None, max_length=200, description="Переопределить название из 2GIS")


class LatLon(BaseModel):
    lat: Lat
    lon: Lon


class FullRouteRequest(BaseModel):
    from_location: LatLon
    to_node: int
    profile: ProfileName = "default"
    overrides: ProfileOverrides | None = None


class SuggestionOut(BaseModel):
    id: str = Field(description="id объекта в 2GIS")
    type: str = Field(description="building, branch, street, adm_div, station...")
    name: str
    address: str | None = Field(description="Вторая строка подсказки")
    lat: float
    lon: float


class OutdoorRouteRequest(BaseModel):
    from_location: LatLon
    to_location: LatLon
    profile: ProfileName = "default"
    overrides: ProfileOverrides | None = None


class OutdoorStepOut(BaseModel):
    text: str
    distance_m: float


class OutdoorOut(BaseModel):
    provider: Literal["2gis", "ors", "straight_line"]
    accessibility_checked: bool = Field(description="true только если уличный маршрут учитывал ограничения профиля")
    distance_m: float
    duration_s: float
    geometry: list[list[float]] = Field(description="[[lon, lat], ...]")
    steps: list[OutdoorStepOut]


class OutdoorRouteResponse(BaseModel):
    route: OutdoorOut
    notices: list[str] = Field(default_factory=list)


class FullRouteResponse(BaseModel):
    found: bool
    entrance: RouteNode | None = None
    outdoor: OutdoorOut | None = None
    indoor: RouteResponse
    total_time_s: float = 0
    notices: list[str] = Field(default_factory=list, description="Что пошло не так с уличной частью, если пошло")


@router.get("/integrations/status", response_model=IntegrationStatus, summary="Какие внешние API подключены")
async def integration_status():
    return IntegrationStatus(dgis=bool(_s.dgis_api_key), ors=bool(_s.ors_api_key))


@router.get("/integrations/2gis/buildings", response_model=list[ExtBuildingOut],
            summary="Найти здание в 2GIS (для админки)")
async def dgis_search(_: EditorUser, q: Annotated[str, Query(min_length=2, max_length=200)],
                      lat: Lat | None = None, lon: Lon | None = None, lang: LangQuery = "ru"):
    try:
        found = await external.dgis_search_buildings(q, lat, lon, DGIS_LOCALES[normalize_lang(lang)])
    except external.ExternalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return [ExtBuildingOut(**b.__dict__) for b in found]


@router.get("/geo/suggest", response_model=list[SuggestionOut],
            summary="Подсказки адресов и мест при вводе (2GIS)")
@limiter.limit(_s.rate_limit_search)
async def geo_suggest(request: Request, q: Annotated[str, Query(min_length=2, max_length=200)],
                      lat: Lat | None = None, lon: Lon | None = None, lang: LangQuery = "ru"):
    """Отдаёт только варианты с координатами. `lat`/`lon` поднимают выше то, что рядом (центр карты
    или пользователь). Вызывайте с задержкой после ввода, а не на каждую букву."""
    if not _s.dgis_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Подсказки адресов отключены: нет ключа 2GIS")
    try:
        found = await external.dgis_suggest(q.strip(), lat, lon, DGIS_LOCALES[normalize_lang(lang)])
    except external.ExternalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    return [SuggestionOut(**it.__dict__) for it in found]


def _outdoor_out(r: external.OutdoorRoute) -> OutdoorOut:
    return OutdoorOut(provider=r.provider, accessibility_checked=r.accessibility_checked,
                      distance_m=round(r.distance_m, 1), duration_s=round(r.duration_s),
                      geometry=r.geometry, steps=[OutdoorStepOut(**s.__dict__) for s in r.steps])


@router.post("/route/outdoor", response_model=OutdoorRouteResponse,
             summary="Пеший маршрут по улице между двумя точками (2GIS)")
@limiter.limit(_s.rate_limit_outdoor)
async def outdoor_route(request: Request, data: OutdoorRouteRequest, lang: LangQuery = "ru"):
    """Если профиль запрещает лестницы, 2GIS строит путь без лестниц. Бордюры и уклоны 2GIS
    не учитывает, поэтому `accessibility_checked` всегда false."""
    if not _s.dgis_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Уличные маршруты отключены: нет ключа 2GIS")
    lg = normalize_lang(lang)
    profile = resolve_profile(data.profile, data.overrides)
    src = (data.from_location.lat, data.from_location.lon)
    dst = (data.to_location.lat, data.to_location.lon)
    if external.haversine_m(*src, *dst) > MAX_WALK_M:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Точки дальше {MAX_WALK_M // 1000} км друг от друга, пеший маршрут не строим")
    try:
        r = await external.dgis_walk_route(src, dst, lg, avoid_stairs=not profile.allow_stairs)
    except external.ExternalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    notices = []
    if data.profile != "default" or data.overrides:
        notices.append("Уличный участок построен без учёта бордюров и уклонов, будьте внимательны")
    return OutdoorRouteResponse(route=_outdoor_out(r), notices=notices)


@router.post("/integrations/2gis/import", response_model=BuildingOut, status_code=status.HTTP_201_CREATED,
             summary="Создать здание по id из 2GIS")
async def dgis_import(data: DgisImportRequest, session: SessionDep, _: EditorUser):
    exists = await session.scalar(
        select(Building).where(Building.external_source == "2gis", Building.external_id == data.external_id)
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Здание уже импортировано: #{exists.id}")
    try:
        ext = await external.dgis_get_building(data.external_id, DGIS_LOCALES["ru"])
    except external.ExternalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    if ext is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "В 2GIS нет объекта с таким id")
    b = Building(name=data.name or ext.name, address=ext.address, lat=ext.lat, lon=ext.lon,
                 external_source="2gis", external_id=ext.external_id)
    session.add(b)
    await session.commit()
    return b


@router.post("/route/full", response_model=FullRouteResponse,
             summary="Маршрут с улицы: от координат пользователя через доступный вход до аудитории")
@limiter.limit(_s.rate_limit_outdoor)
async def full_route(request: Request, data: FullRouteRequest, session: SessionDep, lang: LangQuery = "ru"):
    """Выбирает вход здания, для которого существует внутренний маршрут под профиль, и строит до него
    уличный участок. Для профилей с ограничениями используется OpenRouteService (wheelchair), а если его
    ключа нет, то 2GIS с пометкой `accessibility_checked=false`. Без ключей уличная часть оценивается по прямой."""
    lg = normalize_lang(lang)
    profile = resolve_profile(data.profile, data.overrides)
    target = await get_or_404(session, Node, data.to_node, "Узел")
    graph = await get_graph(session, target.building_id)
    now = datetime.now(UTC)
    src = (data.from_location.lat, data.from_location.lon)

    restricted = data.profile != "default" or bool(data.overrides)
    # Координаты входа: заданные вручную или вычисленные по привязке этажа к карте
    geo = {n.id: graph.node_geo(n) for n in graph.nodes.values() if n.type == NodeType.entrance.value}
    candidates = [graph.nodes[i] for i, c in geo.items()
                  if c is not None and (graph.nodes[i].is_accessible_entrance or not restricted)]

    def street_m(n) -> float:
        return external.haversine_m(src[0], src[1], geo[n.id][1], geo[n.id][0])

    # Не больше 5 ближайших входов, чтобы запрос не стоил десятков поисков по графу
    candidates.sort(key=street_m)
    candidates = candidates[:5]

    # Внутренний маршрут от каждого входа, затем выбор по сумме «улица по прямой + внутри»
    options = []
    for ent in candidates:
        res = await run_in_threadpool(find_route, graph, ent.id, target.id, profile, now)
        if res.found:
            street_s = street_m(ent) * 1.3 / profile.speed_mps
            options.append((street_s + res.cost_s, ent, res))

    base = RouteResponse(found=False, building_id=target.building_id, profile=data.profile, params=profile)
    if not options:
        if not candidates:
            notice = "У здания нет отмеченных доступных входов с координатами" if restricted \
                else "У здания нет входов с координатами"
            return FullRouteResponse(found=False, indoor=base, notices=[notice])
        # Покажем, почему не вышло, на примере ближайшего входа
        nearest = candidates[0]
        res = await run_in_threadpool(find_route, graph, nearest.id, target.id, profile, now)
        return FullRouteResponse(found=False, indoor=render_route(graph, res, base, profile, lg))

    _, entrance, res = min(options, key=lambda o: o[0])
    indoor = render_route(graph, res, base, profile, lg)
    dst = (geo[entrance.id][1], geo[entrance.id][0])

    notices: list[str] = []
    outdoor = None
    providers = []
    if restricted and _s.ors_api_key:
        providers.append(lambda: external.ors_wheelchair_route(src, dst, profile, lg))
    if _s.dgis_api_key:
        providers.append(lambda: external.dgis_walk_route(src, dst, lg, avoid_stairs=not profile.allow_stairs))
    for call in providers:
        try:
            outdoor = _outdoor_out(await call())
            break
        except external.ExternalError as exc:
            notices.append(str(exc))
    if outdoor is None:
        dist = external.haversine_m(src[0], src[1], dst[0], dst[1])
        outdoor = OutdoorOut(provider="straight_line", accessibility_checked=False, distance_m=round(dist, 1),
                             duration_s=round(dist * 1.3 / profile.speed_mps),
                             geometry=[[src[1], src[0]], [dst[1], dst[0]]], steps=[])
        notices.append("Уличный маршрут не построен, расстояние оценено по прямой")
    elif restricted and not outdoor.accessibility_checked:
        notices.append("Уличный участок построен без учёта бордюров и уклонов, будьте внимательны")

    entrance_out = RouteNode(id=entrance.id, floor_id=entrance.floor_id, level=entrance.level, type=entrance.type,
                             name=entrance.name, ref=entrance.ref, x=entrance.x, y=entrance.y, geo=geo[entrance.id])
    return FullRouteResponse(found=True, entrance=entrance_out, outdoor=outdoor, indoor=indoor,
                             total_time_s=outdoor.duration_s + indoor.estimated_time_s, notices=notices)
