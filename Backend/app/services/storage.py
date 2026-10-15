"""Схемы этажей в MinIO. Наружу MinIO не открыт: файлы отдаёт сам API."""

import io
import logging
import re
import uuid
import warnings
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from defusedxml import ElementTree as SafeET
from fastapi import HTTPException, status
from minio import Minio
from minio.error import S3Error
from PIL import Image

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_PIXELS = 60_000_000
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
for prefix, ns in (("", SVG_NS), ("xlink", XLINK_NS),
                   ("inkscape", "http://www.inkscape.org/namespaces/inkscape"),
                   ("sodipodi", "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd")):
    ET.register_namespace(prefix, ns)

FORBIDDEN_SVG_TAGS = {"script", "foreignObject", "iframe", "embed", "object", "audio", "video", "handler", "listener"}


@dataclass
class ValidatedPlan:
    data: bytes
    content_type: str
    ext: str
    width: int | None
    height: int | None


_client: Minio | None = None


def client() -> Minio:
    global _client
    if _client is None:
        s = get_settings()
        _client = Minio(s.minio_endpoint, access_key=s.minio_access_key, secret_key=s.minio_secret_key,
                        secure=s.minio_secure)
    return _client


def ensure_bucket() -> None:
    s = get_settings()
    try:
        if not client().bucket_exists(s.minio_bucket):
            client().make_bucket(s.minio_bucket)
    except Exception as exc:  # noqa: BLE001 - при старте MinIO может быть ещё недоступен
        log.warning("MinIO недоступен при старте: %s", exc)


def _bad(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, msg)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _sanitize_svg(data: bytes) -> tuple[bytes, int | None, int | None]:
    try:
        root = SafeET.fromstring(data)
    except Exception:  # noqa: BLE001 - defusedxml бросает разные исключения на вредный XML
        raise _bad("Некорректный SVG") from None
    if _local(root.tag) != "svg":
        raise _bad("Корневой элемент должен быть <svg>")

    for parent in list(root.iter()):
        for child in list(parent):
            if _local(child.tag) in FORBIDDEN_SVG_TAGS:
                parent.remove(child)
    for el in root.iter():
        for attr in list(el.attrib):
            name, value = _local(attr).lower(), el.attrib[attr].strip().lower()
            if name.startswith("on"):
                del el.attrib[attr]
            elif name == "href" and not (value.startswith("#") or value.startswith("data:image/")):
                del el.attrib[attr]
        if _local(el.tag) == "style" and el.text and ("@import" in el.text or "url(" in el.text):
            el.text = re.sub(r"@import[^;]*;?|url\([^)]*\)", "", el.text)

    def num(v: str | None) -> int | None:
        m = re.match(r"^\s*([\d.]+)\s*(px)?\s*$", v or "")
        return int(float(m.group(1))) if m else None

    w, h = num(root.get("width")), num(root.get("height"))
    if (w is None or h is None) and root.get("viewBox"):
        parts = re.split(r"[\s,]+", root.get("viewBox").strip())
        if len(parts) == 4:
            try:
                w, h = int(float(parts[2])), int(float(parts[3]))
            except ValueError:
                pass
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), w, h


def validate_plan(data: bytes) -> ValidatedPlan:
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пустой файл")
    head = data[:16]
    raster = None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        raster = ("image/png", "png")
    elif head.startswith(b"\xff\xd8\xff"):
        raster = ("image/jpeg", "jpg")
    elif head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        raster = ("image/webp", "webp")

    if raster:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as img:
                    w, h = img.size
                    if w * h > MAX_PIXELS:
                        raise _bad("Слишком большое изображение")
                    img.verify()
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            raise _bad("Файл повреждён или не является изображением") from None
        return ValidatedPlan(data, raster[0], raster[1], w, h)

    text_head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text_head.startswith(b"<?xml") or text_head.startswith(b"<svg") or text_head.startswith(b"<!--"):
        clean, w, h = _sanitize_svg(data)
        return ValidatedPlan(clean, "image/svg+xml", "svg", w, h)

    raise _bad("Поддерживаются PNG, JPEG, WebP и SVG")


def put_plan(building_id: int, floor_id: int, plan: ValidatedPlan) -> str:
    key = f"buildings/{building_id}/floors/{floor_id}/{uuid.uuid4().hex}.{plan.ext}"
    client().put_object(get_settings().minio_bucket, key, io.BytesIO(plan.data), len(plan.data),
                        content_type=plan.content_type)
    return key


def get_plan(key: str) -> bytes:
    resp = client().get_object(get_settings().minio_bucket, key)
    try:
        return resp.read()
    finally:
        resp.close()
        resp.release_conn()


def delete_plan(key: str) -> None:
    try:
        client().remove_object(get_settings().minio_bucket, key)
    except S3Error as exc:
        log.warning("Не удалось удалить %s: %s", key, exc)


def plan_url(floor_id: int, key: str | None) -> str | None:
    if not key:
        return None
    version = key.rsplit("/", 1)[-1].split(".", 1)[0]
    return f"/api/v1/floors/{floor_id}/plan?v={version}"
