import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import engine
from app.ratelimit import limiter
from app.routers import (
    account,
    auth,
    buildings,
    edges,
    floors,
    integrations,
    nodes,
    obstacles,
    reports,
    route,
    users,
)
from app.services import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = get_settings()

DESCRIPTION = """
REST API навигатора доступной среды **Sapa**.

* Читать данные и строить маршруты может кто угодно (с ограничением частоты запросов).
* Изменять граф и препятствия могут только `editor` и `admin`: получите токен через
  `POST /api/v1/auth/login` (или кнопку **Authorize**) и передавайте его в `Authorization: Bearer <token>`.
* Координаты узлов `x`/`y` задаются в пикселях схемы этажа, масштаб хранится в `floor.meters_per_px`.
* Язык инструкций выбирается параметром `?lang=ru|kk|en`.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.env != "test":
        await run_in_threadpool(storage.ensure_bucket)
    yield
    await engine.dispose()


app = FastAPI(
    title="Sapa API",
    version="1.0.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.state.limiter = limiter

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": f"Слишком много запросов: {exc.detail}. Попробуйте позже."},
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": "60"})


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    logging.getLogger("app").info("IntegrityError: %s", exc.orig)
    return JSONResponse({"detail": "Конфликт данных: нарушено ограничение целостности (дубликат или неверная ссылка)"},
                        status_code=status.HTTP_409_CONFLICT)


api = APIRouter(prefix="/api/v1")
for r in (auth, account, users, buildings, floors, nodes, edges, obstacles, reports, route, integrations):
    api.include_router(r.router)
app.include_router(api)


@app.get("/api/health", tags=["system"], summary="Проверка живости API и БД")
@limiter.exempt
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)
    return {"status": "ok", "db": True}
