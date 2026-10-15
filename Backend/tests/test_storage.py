"""Проверка загружаемых схем этажей (без MinIO)."""

import io

import pytest
from fastapi import HTTPException
from PIL import Image

from app.services.storage import validate_plan


def test_png_ok():
    buf = io.BytesIO()
    Image.new("RGB", (1000, 600), "white").save(buf, "PNG")
    plan = validate_plan(buf.getvalue())
    assert plan.content_type == "image/png" and (plan.width, plan.height) == (1000, 600)


def test_svg_sanitized():
    evil = b"""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 800 400">
  <script>alert(1)</script>
  <rect width="10" height="10" onclick="alert(2)"/>
  <a xlink:href="javascript:alert(3)"><text>x</text></a>
  <foreignObject><div>html</div></foreignObject>
  <image href="https://tracker.example/pixel.png"/>
</svg>"""
    plan = validate_plan(evil)
    out = plan.data.decode()
    assert plan.content_type == "image/svg+xml" and (plan.width, plan.height) == (800, 400)
    for bad in ("script", "onclick", "javascript:", "foreignObject", "tracker.example"):
        assert bad not in out


def test_xml_bomb_rejected():
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;">]>
<svg xmlns="http://www.w3.org/2000/svg">&lol2;</svg>"""
    with pytest.raises(HTTPException) as e:
        validate_plan(bomb)
    assert e.value.status_code == 415


def test_garbage_rejected():
    with pytest.raises(HTTPException):
        validate_plan(b"MZ\x90\x00 definitely not an image")
    with pytest.raises(HTTPException):
        validate_plan(b"\x89PNG\r\n\x1a\nbroken")
