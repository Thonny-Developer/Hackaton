from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import Limit, Offset, SessionDep, get_or_404, paginate
from app.models import Role, User
from app.schemas import Page, UserCreate, UserOut, UserUpdate
from app.security import AdminUser, hash_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
async def list_users(session: SessionDep, _: AdminUser, limit: Limit = 50, offset: Offset = 0):
    items, total = await paginate(session, select(User).order_by(User.id), limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, session: SessionDep, _: AdminUser):
    email = data.email.lower()
    if await session.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже есть")
    user = User(email=email, name=data.name, password_hash=hash_password(data.password), role=data.role,
                is_active=True)
    session.add(user)
    await session.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: int, data: UserUpdate, session: SessionDep, admin: AdminUser):
    user = await get_or_404(session, User, user_id, "Пользователь")
    if user.id == admin.id and (data.role not in (None, Role.admin) or data.is_active is False):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя понизить или отключить самого себя")
    if data.password:
        user.password_hash = hash_password(data.password)
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await session.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, session: SessionDep, admin: AdminUser):
    user = await get_or_404(session, User, user_id, "Пользователь")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя удалить самого себя")
    await session.delete(user)
    await session.commit()
