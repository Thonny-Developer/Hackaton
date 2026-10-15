import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="sapa-test-"), "test.db")
os.environ["ENV"] = "test"
# TEST_DATABASE_URL позволяет прогнать тесты на настоящем PostgreSQL (база будет очищена)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{_db}"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret!"
os.environ["DGIS_API_KEY"] = ""
os.environ["ORS_API_KEY"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.services.graph_cache import clear_cache  # noqa: E402

ADMIN = ("admin@test.kz", "admin-password-1")
EDITOR = ("editor@test.kz", "editor-password-1")


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        s.add(User(email=ADMIN[0], password_hash=hash_password(ADMIN[1]), role=Role.admin))
        s.add(User(email=EDITOR[0], password_hash=hash_password(EDITOR[1]), role=Role.editor))
        await s.commit()
    yield
    clear_cache()
    await engine.dispose()


@pytest.fixture(scope="session")
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def _token(client, creds) -> dict:
    r = await client.post("/auth/login", data={"username": creds[0], "password": creds[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
async def admin_h(client):
    return await _token(client, ADMIN)


@pytest.fixture(scope="session")
async def editor_h(client):
    return await _token(client, EDITOR)


@pytest.fixture(scope="session")
async def demo(client, editor_h):
    """Демо-здание, загруженное через API импорта. Возвращает node_ids по ключам."""
    from app.seed_data import build_demo

    r = await client.post("/buildings/import", json=build_demo(), headers=editor_h)
    assert r.status_code == 201, r.text
    ids = r.json()["node_ids"]
    b = (await client.get(f"/nodes/{ids['r105']}")).json()["building_id"]
    return {"building_id": b, **ids}
