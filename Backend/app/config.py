from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
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
    rate_limit_register: str = "5/minute"
    rate_limit_reports: str = "10/hour"
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

    # Почта. Без SMTP_HOST письма не отправляются (в dev текст письма пишется в лог).
    # Gmail: smtp.gmail.com, 587, starttls, SMTP_USER = адрес Gmail, SMTP_PASSWORD = пароль приложения
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_user: str = ""
    smtp_password: str = ""
    # Отправитель: адрес, «Имя <адрес>» или только имя (тогда адрес берётся из SMTP_USER). Пусто = SMTP_USER
    smtp_from: str = Field("", validation_alias=AliasChoices("SMTP_FROM", "MAIL_FROM", "smtp_from"))
    # Короткая форма: SMTP_TLS=true -> starttls (или ssl на порту 465), false -> без шифрования
    smtp_tls: bool | None = None
    smtp_timeout_s: float = 10.0
    # Адрес сайта для ссылок в письмах (сброс пароля)
    public_url: str = "http://localhost"
    password_reset_ttl_minutes: int = 30
    rate_limit_forgot: str = "3/minute"
    notify_obstacles: bool = True
    notify_reports: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def apply_smtp_tls(self):
        if self.smtp_tls is not None:
            self.smtp_security = ("ssl" if self.smtp_port == 465 else "starttls") if self.smtp_tls else "none"
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod and (s.jwt_secret == INSECURE_SECRET or len(s.jwt_secret) < 32):
        raise RuntimeError("JWT_SECRET должен быть задан (не короче 32 символов) в prod")
    return s
