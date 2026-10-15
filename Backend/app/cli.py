"""Команды обслуживания.

    python -m app.cli create-admin --email admin@example.com [--password ...] [--role admin|editor]
    python -m app.cli seed [--if-missing]  # создать или пересоздать демо-здание
    python -m app.cli export-demo     # сохранить демо-здание как пример JSON для импорта
    python -m app.cli test-email --to you@example.com   # проверить настройки SMTP
"""

import argparse
import asyncio
import getpass
import json
import sys

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Building, Role, User
from app.schemas import BuildingImport
from app.security import hash_password
from app.seed_data import DEMO_NAME, build_demo
from app.services import mailer
from app.services.importer import import_graph


async def create_admin(email: str, password: str | None, role: str) -> None:
    password = password or getpass.getpass("Пароль (мин. 10 символов): ")
    if len(password) < 10:
        sys.exit("Пароль должен быть не короче 10 символов")
    email = email.strip().lower()
    async with SessionLocal() as s:
        user = await s.scalar(select(User).where(func.lower(User.email) == email))
        if user:
            user.password_hash, user.role, user.is_active = hash_password(password), Role(role), True
            print(f"Пользователь {email} обновлён ({role})")
        else:
            s.add(User(email=email, password_hash=hash_password(password), role=Role(role), is_active=True))
            print(f"Пользователь {email} создан ({role})")
        await s.commit()


async def seed(if_missing: bool) -> None:
    data = BuildingImport.model_validate(build_demo())
    async with SessionLocal() as s:
        b = await s.scalar(select(Building).where(Building.name == DEMO_NAME))
        if b is not None and if_missing:
            print(f"Демо-здание уже есть (#{b.id}), пропускаю")
            return
        if b is None:
            b = Building(**data.model_dump(exclude={"graph"}))
            s.add(b)
            await s.flush()
        result = await import_graph(s, b, data.graph)
        await s.commit()
        print(f"Демо-здание #{b.id}: этажей {result.floors}, узлов {result.nodes}, рёбер {result.edges}")
        for key in ("ent_main", "ent_side", "r105", "r204", "r210", "r305", "el1"):
            print(f"  {key:10} -> node_id {result.node_ids[key]}")


def test_email(to: str) -> None:
    s = get_settings()
    if not mailer.is_configured():
        sys.exit("SMTP не настроен: задайте SMTP_HOST, SMTP_USER и SMTP_PASSWORD в .env")
    print(f"Отправляю через {s.smtp_host}:{s.smtp_port} ({s.smtp_security}) от {s.smtp_from or s.smtp_user} ...")
    try:
        mailer.send(mailer.test_mail(to))
    except Exception as exc:  # noqa: BLE001
        hint = ""
        if "535" in str(exc) or "Username and Password not accepted" in str(exc):
            hint = "\nДля Gmail нужен пароль приложения, а не обычный пароль: https://myaccount.google.com/apppasswords"
        sys.exit(f"Ошибка: {exc.__class__.__name__}: {exc}{hint}")
    print(f"Готово, проверьте ящик {to} (и папку «Спам»)")


def main() -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("--email", required=True)
    ca.add_argument("--password")
    ca.add_argument("--role", default="admin", choices=["admin", "editor"])
    sd = sub.add_parser("seed")
    sd.add_argument("--if-missing", action="store_true", help="Не трогать демо-здание, если оно уже есть")
    ex = sub.add_parser("export-demo")
    ex.add_argument("--out", default="-")
    te = sub.add_parser("test-email")
    te.add_argument("--to", required=True)
    args = p.parse_args()

    if args.cmd == "test-email":
        test_email(args.to)
        return

    if args.cmd == "export-demo":
        text = json.dumps(build_demo(), ensure_ascii=False, indent=2)
        if args.out == "-":
            print(text)
        else:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        return

    async def run():
        try:
            if args.cmd == "create-admin":
                await create_admin(args.email, args.password, args.role)
            elif args.cmd == "seed":
                await seed(args.if_missing)
        finally:
            await engine.dispose()

    asyncio.run(run())


if __name__ == "__main__":
    main()
