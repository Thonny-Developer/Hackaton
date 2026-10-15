from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import SessionDep
from app.models import User
from app.ratelimit import limiter
from app.schemas import TokenOut, UserOut
from app.security import create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Вход для админов и редакторов")
@limiter.limit(get_settings().rate_limit_login)
async def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep):
    """Принимает form-data `username` (email) и `password`, как требует OAuth2.
    Кнопка Authorize в Swagger работает с этим эндпоинтом напрямую."""
    email = form.username.strip().lower()[:254]
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if not verify_password(form.password[:128], user.password_hash if user else None) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")
    token, ttl = create_access_token(user)
    return TokenOut(access_token=token, expires_in=ttl)


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return user
