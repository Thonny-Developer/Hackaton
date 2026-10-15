from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # dev | prod | test
    database_url: str = "postgresql+asyncpg://sapa:sapa@localhost:5432/sapa"

    jwt_secret: str = INSECURE_SECRET
    jwt_ttl_minutes: int = 12 * 60

    # Пустая строка = лимиты хранятся в памяти процесса (годится только для одного воркера)
    redis_url: str = ""
    rate_limit_default: str = "120/minute"
    rate_limit_route: str = "30/minute"
    rate_limit_search: str = "60/minute"
    rate_limit_login: str = "5/minute"
    rate_limit_outdoor: str = "10/minute"

    # Через запятую: CORS_ORIGINS=https://sapa.kz,http://localhost:5173
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000", "http://localhost:5173"]

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "sapa"
    minio_secret_key: str = "sapa-minio-secret"
    minio_bucket: str = "floor-plans"
    minio_secure: bool = False
    plan_max_bytes: int = 10 * 1024 * 1024

    # Внешние API (этап 2). Без ключа соответствующая функция отключена.
    dgis_api_key: str = ""
    ors_api_key: str = ""
    external_timeout_s: float = 8.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and (s.jwt_secret == INSECURE_SECRET or len(s.jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET должен быть задан (не короче 32 символов) в prod")
    return s
