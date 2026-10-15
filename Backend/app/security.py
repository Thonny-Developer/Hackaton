import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Role, User

_hasher = PasswordHasher()
# Хэш-пустышка: при несуществующем email тратим столько же времени, сколько при неверном пароле
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user: User) -> tuple[str, int]:
    s = get_settings()
    ttl = s.jwt_ttl_minutes * 60
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "role": user.role.value, "iat": now, "exp": now + timedelta(seconds=ttl)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256"), ttl


RESET_PURPOSE = "password_reset"


def _password_fingerprint(user: User) -> str:
    # После смены пароля отпечаток меняется, и старая ссылка сброса перестаёт работать
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def create_reset_token(user: User) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "purpose": RESET_PURPOSE, "fp": _password_fingerprint(user),
               "iat": now, "exp": now + timedelta(minutes=s.password_reset_ttl_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def check_reset_token(token: str) -> tuple[int, str] | None:
    """Возвращает (user_id, отпечаток пароля) или None, если токен недействителен."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"],
                             options={"require": ["exp", "sub", "purpose", "fp"]})
        if payload["purpose"] != RESET_PURPOSE:
            return None
        return int(payload["sub"]), payload["fp"]
    except (jwt.PyJWTError, ValueError):
        return None


def reset_token_matches(user: User, fp: str) -> bool:
    return user.is_active and _password_fingerprint(user) == fp


_unauthorized = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Требуется авторизация",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if not token:
        raise _unauthorized
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        user_id = int(payload["sub"])
        # Токен сброса пароля не даёт доступа к API
        if payload.get("purpose"):
            raise ValueError
    except (jwt.PyJWTError, ValueError):
        raise _unauthorized from None
    # Пользователя перечитываем из БД, чтобы отключение аккаунта или смена роли работали сразу
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized
    return user


async def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User | None:
    """Для публичных эндпоинтов: без токена None, с недействительным токеном 401."""
    return await get_current_user(token, session) if token else None


def require_role(*roles: Role):
    async def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return checker


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
EditorUser = Annotated[User, Depends(require_role(Role.admin, Role.editor))]
AdminUser = Annotated[User, Depends(require_role(Role.admin))]
