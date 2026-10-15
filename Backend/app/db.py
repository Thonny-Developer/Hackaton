from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    if url.startswith("sqlite"):
        # SQLite используется только в тестах, внешние ключи там по умолчанию выключены
        eng = create_async_engine(url)

        @event.listens_for(eng.sync_engine, "connect")
        def _sqlite_setup(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")
            # Встроенный lower() в SQLite понимает только ASCII, а поиск у нас по-русски
            conn.create_function("lower", 1, lambda s: s.lower() if isinstance(s, str) else s)

        return eng
    return create_async_engine(url, pool_size=10, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)


engine = _make_engine(get_settings().database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
