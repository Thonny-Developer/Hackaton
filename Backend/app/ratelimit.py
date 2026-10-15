from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

_s = get_settings()

# IP берётся из request.client. За Caddy его подставляет uvicorn (--proxy-headers),
# поэтому заголовок X-Forwarded-For от клиента напрямую не подделать.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_s.rate_limit_default],
    storage_uri=_s.redis_url or "memory://",
    headers_enabled=False,
    enabled=_s.env != "test",
    # Если Redis упал, лучше пропустить запрос, чем положить весь API
    swallow_errors=True,
    in_memory_fallback_enabled=True,
)
