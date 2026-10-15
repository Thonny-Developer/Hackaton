import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import or_, select

from app.config import get_settings
from app.deps import SessionDep, get_or_404
from app.models import Edge, Floor, Node, Obstacle
from app.routers.buildings import edge_out, floor_out, node_out
from app.schemas import FloorDetail, FloorOut, FloorUpdate, ObstacleOut
from app.security import EditorUser
from app.services import storage
from app.services.geojson import floor_geojson
from app.services.graph_cache import bump_graph_version, get_graph

router = APIRouter(prefix="/floors", tags=["floors"])


@router.get("/{floor_id}", response_model=FloorDetail, summary="Этаж с узлами, рёбрами и активными препятствиями")
async def get_floor(floor_id: int, session: SessionDep):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    g = await get_graph(session, f.building_id)
    nodes = list(await session.scalars(select(Node).where(Node.floor_id == floor_id).order_by(Node.id)))
    node_ids = [n.id for n in nodes]
    edges = list(await session.scalars(
        select(Edge).where(or_(Edge.from_node_id.in_(node_ids), Edge.to_node_id.in_(node_ids))).order_by(Edge.id)
    )) if node_ids else []
    edge_ids = [e.id for e in edges]
    now = datetime.now(UTC)
    obstacles = list(await session.scalars(
        select(Obstacle).where(
            Obstacle.is_active.is_(True),
            Obstacle.starts_at <= now,
            (Obstacle.ends_at.is_(None)) | (Obstacle.ends_at > now),
            or_(Obstacle.node_id.in_(node_ids), Obstacle.edge_id.in_(edge_ids)),
        )
    )) if node_ids else []
    base = floor_out(f)
    return FloorDetail(
        **base.model_dump(),
        nodes=[node_out(n, g) for n in nodes],
        edges=[edge_out(e, g) for e in edges],
        obstacles=[ObstacleOut.model_validate(o) for o in obstacles],
    )


@router.get("/{floor_id}/geojson", summary="Этаж в GeoJSON для Mapbox (узлы, переходы, препятствия)",
            responses={409: {"description": "Этаж не привязан к карте"}})
async def get_floor_geojson(floor_id: int, session: SessionDep) -> dict:
    """FeatureCollection: узлы точками (`properties.kind = node`), переходы внутри этажа линиями
    (`kind = edge`). Перекрытые препятствиями объекты помечены `blocked: true`.
    Подставляется в Mapbox как `{type: "geojson", data: ...}`."""
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    if f.geo_origin_lat is None or f.geo_origin_lon is None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Этаж не привязан к карте: задайте geo_origin_lat, geo_origin_lon и geo_rotation_deg")
    g = await get_graph(session, f.building_id)
    return floor_geojson(g, floor_id, datetime.now(UTC))


@router.patch("/{floor_id}", response_model=FloorOut)
async def update_floor(floor_id: int, data: FloorUpdate, session: SessionDep, _: EditorUser):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    patch = data.model_dump(exclude_unset=True)
    if "level" in patch and patch["level"] != f.level and await session.scalar(
        select(Floor.id).where(Floor.building_id == f.building_id, Floor.level == patch["level"])
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Этаж с level={patch['level']} уже есть")
    for k, v in patch.items():
        # Привязку к карте можно сбросить через null, остальные поля обязательные
        if v is not None or k in ("geo_origin_lat", "geo_origin_lon"):
            setattr(f, k, v)
    await bump_graph_version(session, f.building_id)
    await session.commit()
    await session.refresh(f)
    return floor_out(f)


@router.delete("/{floor_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Удалить этаж вместе с его узлами и рёбрами")
async def delete_floor(floor_id: int, session: SessionDep, _: EditorUser):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    key = f.plan_object_key
    await bump_graph_version(session, f.building_id)
    await session.delete(f)
    await session.commit()
    if key:
        await run_in_threadpool(storage.delete_plan, key)


@router.post("/{floor_id}/plan", response_model=FloorOut, summary="Загрузить схему этажа (PNG/JPEG/WebP/SVG)")
async def upload_plan(floor_id: int, file: UploadFile, session: SessionDep, _: EditorUser):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    max_bytes = get_settings().plan_max_bytes
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Файл больше {max_bytes // 1024 // 1024} МБ")
    plan = await run_in_threadpool(storage.validate_plan, data)
    try:
        key = await run_in_threadpool(storage.put_plan, f.building_id, f.id, plan)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище схем недоступно") from None
    old = f.plan_object_key
    f.plan_object_key, f.plan_content_type = key, plan.content_type
    f.plan_width_px, f.plan_height_px = plan.width, plan.height
    await session.commit()
    if old:
        await run_in_threadpool(storage.delete_plan, old)
    await session.refresh(f)
    return floor_out(f)


@router.get("/{floor_id}/plan", summary="Файл схемы этажа", response_class=Response,
            responses={200: {"content": {"image/png": {}, "image/svg+xml": {}}}})
async def get_plan(floor_id: int, request: Request, session: SessionDep):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    if not f.plan_object_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Схема этажа не загружена")
    etag = '"' + hashlib.sha256(f.plan_object_key.encode()).hexdigest()[:32] + '"'
    headers = {
        "ETag": etag,
        # URL содержит ?v=<версия>, поэтому файл можно кэшировать надолго
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    try:
        data = await run_in_threadpool(storage.get_plan, f.plan_object_key)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище схем недоступно") from None
    return Response(data, media_type=f.plan_content_type or "application/octet-stream", headers=headers)


@router.delete("/{floor_id}/plan", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(floor_id: int, session: SessionDep, _: EditorUser):
    f = await get_or_404(session, Floor, floor_id, "Этаж")
    key = f.plan_object_key
    f.plan_object_key = f.plan_content_type = f.plan_width_px = f.plan_height_px = None
    await session.commit()
    if key:
        await run_in_threadpool(storage.delete_plan, key)
