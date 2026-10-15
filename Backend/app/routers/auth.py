from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import SessionDep
from app.models import Role, User
from app.ratelimit import limiter
from app.schemas import MeUpdate, RegisterRequest, TokenOut, UserOut
from app.security import (
    CurrentUser,
    check_reset_token,
    create_access_token,
    create_reset_token,
    hash_password,
    reset_token_matches,
    verify_password,
)
from app.services import mailer

router = APIRouter(prefix="/auth", tags=["auth"])


async def _email_taken(session, email: str, except_id: int | None = None) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email)
    if except_id is not None:
        stmt = stmt.where(User.id != except_id)
    return await session.scalar(stmt) is not None


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED,
             summary="Регистрация посетителя")
@limiter.limit(get_settings().rate_limit_register)
async def register(request: Request, data: RegisterRequest, session: SessionDep):
    """Создаёт аккаунт с ролью `user` и сразу возвращает токен, отдельный вход не нужен.
    Такой аккаунт может хранить избранное и настройки доступности, но не может менять граф."""
    email = data.email.lower()
    if await _email_taken(session, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже зарегистрирован")
    user = User(email=email, name=data.name, password_hash=hash_password(data.password), role=Role.user,
                is_active=True, accessibility_prefs=[])
    session.add(user)
    await session.commit()
    token, ttl = create_access_token(user)
    return TokenOut(access_token=token, expires_in=ttl)


@router.post("/login", response_model=TokenOut, summary="Вход по email и паролю")
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
async def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut, summary="Изменить имя, email или настройки доступности")
async def update_me(data: MeUpdate, user: CurrentUser, session: SessionDep):
    if data.email is not None:
        email = data.email.lower()
        if await _email_taken(session, email, except_id=user.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Этот email уже занят другим пользователем")
        user.email = email
    if data.name is not None:
        user.name = data.name
    if data.accessibility_prefs is not None:
        # Порядок как пришёл, без повторов
        user.accessibility_prefs = list(dict.fromkeys(data.accessibility_prefs))
    await session.commit()
    await session.refresh(user)
    return user


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2000)
    password: str = Field(min_length=10, max_length=128)


class Message(BaseModel):
    detail: str


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED,
             summary="Письмо со ссылкой для сброса пароля")
@limiter.limit(get_settings().rate_limit_forgot)
async def forgot_password(request: Request, data: ForgotPasswordRequest, session: SessionDep,
                          background: BackgroundTasks):
    """Ответ всегда одинаковый, есть такой пользователь или нет, чтобы по API нельзя было
    проверить, зарегистрирован ли адрес. Ссылка ведёт на `{PUBLIC_URL}/reset-password?token=...`."""
    s = get_settings()
    email = data.email.lower()
    user = await session.scalar(select(User).where(func.lower(User.email) == email))
    if user and user.is_active:
        link = f"{s.public_url.rstrip('/')}/reset-password?{urlencode({'token': create_reset_token(user)})}"
        background.add_task(mailer.send_safe, mailer.password_reset_mail(user.email, link, s.password_reset_ttl_minutes))
    return Message(detail="Если такой адрес зарегистрирован, мы отправили на него письмо со ссылкой")


@router.post("/reset-password", response_model=Message, summary="Задать новый пароль по ссылке из письма")
@limiter.limit(get_settings().rate_limit_login)
async def reset_password(request: Request, data: ResetPasswordRequest, session: SessionDep):
    """Ссылка одноразовая: после смены пароля токен из неё перестаёт работать."""
    checked = check_reset_token(data.token)
    user = await session.get(User, checked[0]) if checked else None
    if user is None or not reset_token_matches(user, checked[1]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна или устарела, запросите новую")
    user.password_hash = hash_password(data.password)
    await session.commit()
    return Message(detail="Пароль изменён, теперь можно войти")
