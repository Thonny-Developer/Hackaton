"""Отправка писем через SMTP (по умолчанию Gmail).

Письма уходят в фоне (BackgroundTasks), поэтому медленный или недоступный почтовый сервер
не тормозит API. Ошибка отправки только пишется в лог.
"""

import html
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from app.config import get_settings

log = logging.getLogger(__name__)

BRAND = "SeeWay"


@dataclass
class Mail:
    to: list[str]
    subject: str
    text: str
    html: str | None = None


# В тестах письма складываются сюда вместо отправки
outbox: list[Mail] = []


def is_configured() -> bool:
    return bool(get_settings().smtp_host)


def _sender() -> str:
    s = get_settings()
    value = s.smtp_from.strip()
    if "<" in value:  # уже «Имя <адрес>»
        return value
    if "@" in value:  # только адрес
        return formataddr((BRAND, value))
    # Только имя (или пусто): адрес отправителя берём из логина SMTP
    return formataddr((value or BRAND, s.smtp_user))


def send(mail: Mail) -> None:
    """Отправить письмо. Бросает исключение при ошибке (нужно для команды test-email)."""
    s = get_settings()
    if s.env == "test":
        outbox.append(mail)
        return
    if not s.smtp_host:
        if s.is_prod:
            log.warning("SMTP не настроен, письмо «%s» не отправлено", mail.subject)
        else:
            log.info("SMTP не настроен. Письмо для %s: %s\n%s", ", ".join(mail.to), mail.subject, mail.text)
        return

    msg = EmailMessage()
    msg["From"] = _sender()
    msg["To"] = ", ".join(mail.to)
    msg["Subject"] = mail.subject
    msg["Message-ID"] = make_msgid(domain=(s.smtp_user or "localhost").rsplit("@", 1)[-1])
    msg.set_content(mail.text)
    if mail.html:
        msg.add_alternative(mail.html, subtype="html")

    ctx = ssl.create_default_context()
    if s.smtp_security == "ssl":
        server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s, context=ctx)
    else:
        server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_s)
    with server:
        if s.smtp_security == "starttls":
            server.starttls(context=ctx)
        if s.smtp_user:
            password = s.smtp_password
            # Google показывает пароль приложения группами через пробел, сами пробелы в пароль не входят
            if "gmail" in s.smtp_host:
                password = password.replace(" ", "")
            server.login(s.smtp_user, password)
        server.send_message(msg)
    log.info("Письмо «%s» отправлено: %d получателей", mail.subject, len(mail.to))


def send_safe(mail: Mail) -> None:
    """Для фоновых задач: ошибки не роняют процесс, а пишутся в лог."""
    try:
        send(mail)
    except Exception:  # noqa: BLE001
        log.exception("Не удалось отправить письмо «%s»", mail.subject)


# ---------- Шаблоны ----------

def _layout(title: str, body_html: str) -> str:
    return f"""<!doctype html><html><body style="margin:0;background:#f4f5f7;font-family:Arial,sans-serif;color:#1f2328">
<div style="max-width:520px;margin:24px auto;background:#fff;border-radius:12px;padding:28px">
<div style="font-size:18px;font-weight:bold;margin-bottom:16px">{BRAND}</div>
<div style="font-size:20px;font-weight:bold;margin-bottom:12px">{html.escape(title)}</div>
{body_html}
<div style="margin-top:28px;font-size:12px;color:#6b7280">Это автоматическое письмо, отвечать на него не нужно.</div>
</div></body></html>"""


def password_reset_mail(to: str, link: str, ttl_minutes: int) -> Mail:
    text = (
        f"Здравствуйте!\n\nКто-то запросил сброс пароля для {to} в {BRAND}.\n"
        f"Чтобы задать новый пароль, откройте ссылку (действует {ttl_minutes} минут):\n\n{link}\n\n"
        "Если это были не вы, просто проигнорируйте письмо, пароль останется прежним."
    )
    body = (
        f"<p>Кто-то запросил сброс пароля для <b>{html.escape(to)}</b>.</p>"
        f'<p><a href="{html.escape(link)}" style="display:inline-block;background:#1e6fd9;color:#fff;'
        f'padding:12px 20px;border-radius:8px;text-decoration:none">Задать новый пароль</a></p>'
        f"<p style=\"color:#6b7280\">Ссылка действует {ttl_minutes} минут. Если это были не вы, "
        "просто проигнорируйте письмо, пароль останется прежним.</p>"
    )
    return Mail([to], f"{BRAND}: сброс пароля", text, _layout("Сброс пароля", body))


def obstacle_mail(to: list[str], title: str, lines: list[tuple[str, str]]) -> Mail:
    text = title + "\n\n" + "\n".join(f"{k}: {v}" for k, v in lines)
    rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#6b7280">{html.escape(k)}</td>'
        f"<td style=\"padding:4px 0\">{html.escape(v)}</td></tr>" for k, v in lines
    )
    return Mail(to, f"{BRAND}: {title}", text, _layout(title, f"<table>{rows}</table>"))


def test_mail(to: str) -> Mail:
    text = f"Это тестовое письмо от {BRAND}. Если вы его видите, SMTP настроен правильно."
    return Mail([to], f"{BRAND}: проверка почты", text, _layout("Проверка почты", f"<p>{text}</p>"))
