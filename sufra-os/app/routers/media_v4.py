"""SUFRA V4 local media helpers.

Menu photographs are explicit uploads only. If a dish has no uploaded image,
the guest menu receives the local default placeholder from main.py.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from ..database import engine
from ..models import MenuContent, MenuItem
from ..permissions import require_permission

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "static" / "uploads" / "menu"
UPLOADS.mkdir(parents=True, exist_ok=True)


def _decode_image(raw: str) -> tuple[str, bytes]:
    m = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", str(raw or ""), re.I | re.S)
    if not m:
        raise HTTPException(400, "Choose a PNG, JPEG or WebP image.")
    ext = "jpg" if m.group(1).lower() in {"jpeg", "jpg"} else m.group(1).lower()
    try:
        data = base64.b64decode(m.group(2), validate=False)
    except Exception:
        raise HTTPException(400, "The image could not be read.")
    if len(data) > 8_000_000:
        raise HTTPException(413, "Dish photo is larger than 8 MB.")
    return ext, data


@router.post("/api/v4/menu/{item_id}/photo")
def upload_menu_photo(item_id: int, body: dict = Body(...), _=Depends(require_permission("can_manage_menu"))):
    ext, data = _decode_image(body.get("data_url"))
    with Session(engine, expire_on_commit=False) as s:
        item = s.get(MenuItem, item_id)
        if not item:
            raise HTTPException(404, "Dish not found.")
        filename = f"dish-{item_id}-{int(datetime.now().timestamp())}.{ext}"
        (UPLOADS / filename).write_bytes(data)
        url = f"/static/uploads/menu/{filename}"
        row = s.exec(select(MenuContent).where(MenuContent.menu_item_id == item_id)).first()
        if not row:
            row = MenuContent(menu_item_id=item_id)
        row.image_url = url
        row.image_source = "upload"
        row.updated_at = datetime.now()
        s.add(row)
        s.commit()
        return {"ok": True, "image_url": url, "message": f"Photo updated for {item.name}."}


@router.post("/api/v4/menu/{item_id}/photo/reset")
def reset_menu_photo(item_id: int, _=Depends(require_permission("can_manage_menu"))):
    with Session(engine, expire_on_commit=False) as s:
        row = s.exec(select(MenuContent).where(MenuContent.menu_item_id == item_id)).first()
        if row:
            row.image_url = ""
            row.image_source = "default"
            row.updated_at = datetime.now()
            s.add(row)
            s.commit()
    return {"ok": True, "message": "Dish returned to the default food image."}
