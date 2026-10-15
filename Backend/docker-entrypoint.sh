#!/bin/sh
set -e

# Миграции применяются один раз при старте контейнера, до запуска воркеров
alembic upgrade head

if [ "${SEED_DEMO:-false}" = "true" ]; then
    python -m app.cli seed --if-missing
fi

# --proxy-headers: реальный IP клиента берётся из X-Forwarded-For, который выставляет Caddy.
# API не публикуется наружу, поэтому подделать этот заголовок в обход Caddy нельзя.
exec uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers "${WORKERS:-2}" \
    --proxy-headers --forwarded-allow-ips "*" \
    --limit-concurrency "${LIMIT_CONCURRENCY:-200}" \
    --timeout-keep-alive 5 \
    --no-server-header
