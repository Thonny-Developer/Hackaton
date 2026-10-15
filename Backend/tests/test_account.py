"""Аккаунты посетителей: регистрация, профиль, избранное, сообщения о доступности."""

from app.services import mailer


async def _register(client, email: str, name: str = "Анна") -> dict:
    r = await client.post("/auth/register", json={"name": name, "email": email, "password": "visitor-pass-1"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_register_login_and_profile(client):
    h = await _register(client, "Visitor@Test.kz")
    me = (await client.get("/auth/me", headers=h)).json()
    assert me["email"] == "visitor@test.kz" and me["name"] == "Анна"
    assert me["role"] == "user" and me["accessibility_prefs"] == []

    r = await client.post("/auth/login", data={"username": "visitor@test.kz", "password": "visitor-pass-1"})
    assert r.status_code == 200

    r = await client.patch("/auth/me", headers=h,
                           json={"name": " Анна К. ", "accessibility_prefs": ["noSteps", "elevator", "noSteps"]})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Анна К." and r.json()["accessibility_prefs"] == ["noSteps", "elevator"]


async def test_register_validation(client):
    r = await client.post("/auth/register", json={"name": "Б", "email": "short@test.kz", "password": "short"})
    assert r.status_code == 422
    await _register(client, "dup@test.kz")
    r = await client.post("/auth/register", json={"name": "Б", "email": "DUP@test.kz", "password": "visitor-pass-1"})
    assert r.status_code == 409


async def test_email_change_conflict(client):
    h = await _register(client, "changer@test.kz")
    r = await client.patch("/auth/me", headers=h, json={"email": "admin@test.kz"})
    assert r.status_code == 409
    r = await client.patch("/auth/me", headers=h, json={"email": "Changed@test.kz"})
    assert r.status_code == 200 and r.json()["email"] == "changed@test.kz"
    r = await client.patch("/auth/me", headers=h, json={"accessibility_prefs": ["teleport"]})
    assert r.status_code == 422


async def test_visitor_cannot_edit_graph(client, demo):
    h = await _register(client, "nosy@test.kz")
    r = await client.post("/buildings", json={"name": "Моё здание"}, headers=h)
    assert r.status_code == 403
    assert (await client.get("/reports", headers=h)).status_code == 403


async def test_favorites(client, demo):
    h = await _register(client, "fan@test.kz")
    b = demo["building_id"]
    assert (await client.get("/auth/me/favorites")).status_code == 401
    assert (await client.put(f"/auth/me/favorites/{b}", headers=h)).status_code == 204
    assert (await client.put(f"/auth/me/favorites/{b}", headers=h)).status_code == 204
    favs = (await client.get("/auth/me/favorites", headers=h)).json()
    assert [f["id"] for f in favs] == [b]
    assert (await client.put("/auth/me/favorites/999999", headers=h)).status_code == 404
    assert (await client.delete(f"/auth/me/favorites/{b}", headers=h)).status_code == 204
    assert (await client.get("/auth/me/favorites", headers=h)).json() == []


async def test_reports(client, demo, editor_h):
    h = await _register(client, "reporter@test.kz")
    b = demo["building_id"]
    mailer.outbox.clear()
    r = await client.post("/reports", headers=h, json={"building_id": b, "text": "Не работает лифт"})
    assert r.status_code == 201, r.text
    report = r.json()
    assert report["status"] == "new" and report["building_name"]
    assert mailer.outbox and "Не работает лифт" in mailer.outbox[0].text

    # Без входа тоже можно, но в чужой профиль сообщение не попадёт
    r = await client.post("/reports", json={"building_id": b, "text": "Вход заблокирован"})
    assert r.status_code == 201 and r.json()["user_id"] is None

    mine = (await client.get("/auth/me/reports", headers=h)).json()
    assert mine["total"] == 1 and mine["items"][0]["text"] == "Не работает лифт"

    r = await client.patch(f"/reports/{report['id']}", headers=editor_h, json={"status": "confirmed"})
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    new = (await client.get("/reports", headers=editor_h, params={"status": "new"})).json()
    assert all(i["status"] == "new" for i in new["items"]) and new["total"] >= 1

    assert (await client.post("/reports", json={"building_id": 999999, "text": "abc"})).status_code == 404
