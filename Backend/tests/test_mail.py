"""Почта: сброс пароля и уведомления о препятствиях (письма попадают в mailer.outbox)."""

import re
from urllib.parse import unquote

from app.services import mailer


def _token_from(mail) -> str:
    return unquote(re.search(r"reset-password\?token=([^\s\"&]+)", mail.text).group(1))


async def test_password_reset_flow(client, admin_h):
    r = await client.post("/users", headers=admin_h,
                          json={"email": "forgetful@test.kz", "password": "old-password-123", "role": "editor"})
    assert r.status_code == 201
    mailer.outbox.clear()

    r = await client.post("/auth/forgot-password", json={"email": "Forgetful@test.kz"})
    assert r.status_code == 202
    assert len(mailer.outbox) == 1 and mailer.outbox[0].to == ["forgetful@test.kz"]
    mail = mailer.outbox[0]
    assert "http://localhost/reset-password?token=" in mail.text and mail.html
    token = _token_from(mail)

    # Токен сброса не годится как токен входа
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401

    r = await client.post("/auth/reset-password", json={"token": token, "password": "new-password-456"})
    assert r.status_code == 200
    login = await client.post("/auth/login", data={"username": "forgetful@test.kz", "password": "new-password-456"})
    assert login.status_code == 200

    # Ссылка одноразовая
    r = await client.post("/auth/reset-password", json={"token": token, "password": "another-password-789"})
    assert r.status_code == 400


async def test_forgot_unknown_email_looks_the_same(client):
    mailer.outbox.clear()
    r = await client.post("/auth/forgot-password", json={"email": "nobody@test.kz"})
    assert r.status_code == 202 and mailer.outbox == []


async def test_reset_with_garbage_token(client):
    r = await client.post("/auth/reset-password", json={"token": "not-a-real-token", "password": "whatever-123"})
    assert r.status_code == 400


async def test_obstacle_notifies_admins(client, editor_h, demo):
    mailer.outbox.clear()
    r = await client.post("/obstacles", headers=editor_h, json={
        "node_id": demo["el1"], "type": "elevator_broken", "description": "Ждём запчасть",
        "ends_at": "2026-10-20T13:00:00Z",
    })
    assert r.status_code == 201
    assert len(mailer.outbox) == 1
    mail = mailer.outbox[0]
    assert "admin@test.kz" in mail.to and "editor@test.kz" not in mail.to
    assert "Лифт не работает" in mail.subject
    assert "Ждём запчасть" in mail.text and "20.10.2026 18:00 (UTC+5)" in mail.text
    await client.delete(f"/obstacles/{r.json()['id']}", headers=editor_h)
