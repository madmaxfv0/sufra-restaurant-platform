"""The canonical public API.

SUFRA 360 — and any other guest-facing surface — reads and writes the
restaurant through this router. There is no second reservation store, no
second table list and no second menu behind it: every endpoint here reads
the same rows the manager's screens read.

Nothing in a response carries staff-only information: no waiter identity,
no other guest's CRM note, no spend.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Body, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlmodel import Session, select

from .. import availability as av, bookings, canon, events, rtime
from ..database import engine
from ..models import (DiningTable, MenuContent, MenuItem, MenuSection,
                      Reservation, TableProfile, WaitlistEntry)
from ..ops_utils import unavailable_menu_ids

router = APIRouter()

COOKIE = "sufra_sid"


def db() -> Session:
    return Session(engine, expire_on_commit=False)


def session_id(request: Request, response: Response | None = None) -> str:
    sid = request.cookies.get(COOKIE)
    if not sid:
        sid = uuid.uuid4().hex
        if response is not None:
            response.set_cookie(COOKIE, sid, max_age=60 * 60 * 24 * 30,
                                samesite="lax", httponly=False)
    return sid


def _fail(err: bookings.BookingError):
    return JSONResponse({"ok": False, "error": err.code, "message": err.message},
                        status_code=err.status)


# ------------------------------------------------------------------ venue

@router.get("/api/public/venue")
def public_venue():
    with db() as s:
        cfg = canon.settings(s)
        service = canon.service_config(s)
        return {
            "restaurant": {
                "name": cfg["restaurant_name"], "tagline": cfg["restaurant_tagline"],
                "phone": cfg["phone"], "email": cfg["email"], "address": cfg["address"],
                "currency": cfg["currency"],
                "lat": float(cfg["latitude"]), "lng": float(cfg["longitude"]),
            },
            "timezone": rtime.TZ_NAME,
            "service": service,
            "slots": canon.slots(s),
            "hold_seconds": service["hold_seconds"],
            "grace_minutes": service["grace_minutes"],
            "today": rtime.today().isoformat(),
            "now": rtime.now().isoformat(timespec="seconds"),
            "min_time_today": rtime.now().strftime("%H:%M"),
        }


@router.get("/api/public/tables")
def public_tables():
    """The canonical table registry: one record per physical table."""
    with db() as s:
        return {"tables": canon.canonical_tables(s)}


@router.get("/api/public/live")
def public_live(request: Request):
    """Physical state of the room right now. Not bookability.

    Deliberately narrower than the staff view: a guest may see that a table
    is occupied, never who is sitting at it or under what booking.
    """
    with db() as s:
        state = av.live_state(s, session_id(request))
        for row in state["tables"]:
            row.pop("code", None)
            row.pop("guest_name", None)
            row.pop("reservation_id", None)
            row.pop("os_status", None)
        return state


@router.get("/api/public/availability")
def public_availability(request: Request, date: str = Query(...), time: str = "19:00",
                        party_size: int = 2, duration: Optional[int] = None):
    """Bookability for one chosen slot. Never reads current occupancy."""
    try:
        when = rtime.combine(datetime.fromisoformat(date).date(), time)
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "bad_date",
                             "message": "Choose a valid date and time."}, 400)
    with db() as s:
        return av.availability(s, when, int(party_size or 0), duration,
                               session_id(request))


# ------------------------------------------------------------------ holds

@router.post("/api/public/holds")
async def public_hold(request: Request, response: Response, body: dict = Body(...)):
    sid = session_id(request, response)
    try:
        when = rtime.combine(datetime.fromisoformat(str(body.get("date"))).date(),
                             str(body.get("time") or "19:00"))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "bad_date",
                             "message": "Choose a valid date and time."}, 400)
    with db() as s:
        try:
            table = bookings.resolve_table(s, body.get("table_id") or body.get("table_number"))
        except bookings.BookingError as err:
            return _fail(err)
        party = int(body.get("party_size") or 2)
        try:
            bookings.validate_slot(s, when, party, int(body.get("duration")
                                                       or canon.duration_for(s, party)))
        except bookings.BookingError as err:
            return _fail(err)
        result = av.create_hold(s, table.id, when, party, sid, body.get("duration"))
        if not result.get("ok"):
            s.rollback()
            return JSONResponse(result, 409)
        events.record(s, "table_held", "Table held", detail=when.strftime("%d %b %H:%M"),
                      table_id=table.id, table_number=table.number,
                      actor="Guest", source="sufra_360")
        s.commit()
        return result


@router.delete("/api/public/holds/{hold_id}")
async def public_release(request: Request, hold_id: str):
    with db() as s:
        result = av.release_hold(s, hold_id, session_id(request))
        if result.get("ok"):
            events.record(s, "hold_released", "Hold released", actor="Guest",
                          source="sufra_360")
        s.commit()
        return result


# ----------------------------------------------------------- reservations

@router.post("/api/public/reservations")
async def public_create(request: Request, response: Response, body: dict = Body(...)):
    sid = session_id(request, response)
    with db() as s:
        try:
            result = bookings.create_reservation(
                s, body, session_id=sid, source="sufra_360", actor="SUFRA 360")
        except bookings.BookingError as err:
            return _fail(err)
        except ValueError:
            return JSONResponse({"ok": False, "error": "bad_date",
                                 "message": "Choose a valid date and time."}, 400)
        r = s.get(Reservation, result["reservation"]["id"])
        result["calendar"] = {
            "ics": "/api/public/reservations/%s/calendar.ics" % r.code,
            "google": bookings.google_calendar_link(s, r),
        }
        return result


@router.get("/api/public/reservations/{code}")
def public_reservation(code: str):
    with db() as s:
        r = _by_code(s, code)
        if not r:
            return JSONResponse({"ok": False, "error": "not_found"}, 404)
        return {"ok": True, "reservation": bookings.public_dict(s, r),
                "calendar": {"ics": "/api/public/reservations/%s/calendar.ics" % r.code,
                             "google": bookings.google_calendar_link(s, r)}}


@router.post("/api/public/reservations/{code}/cancel")
async def public_cancel(code: str):
    with db() as s:
        r = _by_code(s, code)
        if not r:
            return JSONResponse({"ok": False, "error": "not_found"}, 404)
        try:
            return bookings.set_status(s, r, "cancelled", actor="Guest", source="sufra_360")
        except bookings.BookingError as err:
            return _fail(err)


@router.get("/api/public/reservations/{code}/calendar.ics")
def public_ics(code: str):
    with db() as s:
        r = _by_code(s, code)
        if not r:
            return PlainTextResponse("Not found", status_code=404)
        return Response(bookings.ics(s, r), media_type="text/calendar",
                        headers={"Content-Disposition":
                                 'attachment; filename="%s.ics"' % r.code})


def _by_code(s: Session, code: str) -> Optional[Reservation]:
    text = (code or "").strip()
    r = s.exec(select(Reservation).where(Reservation.code == text.upper())).first()
    if r is None and text.isdigit():
        r = s.get(Reservation, int(text))
    return r


# --------------------------------------------------------------- waitlist

@router.post("/api/public/waitlist")
async def public_waitlist(body: dict = Body(...)):
    with db() as s:
        try:
            return bookings.join_waitlist(s, body, source="sufra_360", actor="SUFRA 360")
        except bookings.BookingError as err:
            return _fail(err)


# ------------------------------------------------------------------- menu

# Built-in courses get a hand-written translation. A section a manager adds
# through "+ Section" carries its own name_az/name_ru (set when it is
# created or edited) and falls back to its English name until translated —
# never falls out of the menu entirely, which is what the old hardcoded
# six-course list did to anything outside it.
COURSE_TITLE = {
    "Snack": ("Snacks", "Qəlyanaltılar", "Закуски"),
    "Starter": ("To Begin", "Başlanğıc", "Начало"),
    "Main": ("Mains", "Əsas yeməklər", "Основные блюда"),
    "Side": ("Sides", "Əlavələr", "Гарниры"),
    "Dessert": ("Sweet", "Şirniyyat", "Десерты"),
    "Drink": ("Drinks", "İçkilər", "Напитки"),
}
DIET_WORDS = {"vegetarian", "vegan", "gluten_free", "gf", "halal", "kosher",
              "dairy_free", "nut_free"}


@router.get("/api/public/menu")
def public_menu():
    """One menu. The kitchen's own MenuItem rows, live.

    A dish taken off sale in the menu admin or flagged unavailable in the
    kitchen stops being offered here on the next read — there is no second
    copy of the menu to fall out of date.
    """
    with db() as s:
        cfg = canon.settings(s)
        unavailable, reasons = unavailable_menu_ids(s)
        content = {c.menu_item_id: c for c in s.exec(select(MenuContent)).all()}
        items = s.exec(select(MenuItem)).all()
        # The section list itself, not a hardcoded set of six — a section a
        # manager adds shows up here the moment it has a dish on it, same as
        # every built-in one.
        rows = s.exec(select(MenuSection).where(MenuSection.active == True)  # noqa: E712
                      .order_by(MenuSection.sort_order, MenuSection.name)).all()
        known_courses = {r.name for r in rows}
        # A dish whose course predates the section table somehow (a direct
        # DB edit, an old import) still has to be reachable rather than
        # silently dropped, so any course on an item that isn't a known
        # section becomes one, ordered after the configured ones.
        extra = sorted({m.course for m in items if m.course not in known_courses})
        sections = []
        for course, name_az, name_ru in (
            [(r.name, r.name_az, r.name_ru) for r in rows]
            + [(c, "", "") for c in extra]
        ):
            dishes = [m for m in items
                      if m.course == course and m.available and m.id not in unavailable]
            if not dishes:
                continue
            builtin = COURSE_TITLE.get(course)
            title_en = course
            title_az = name_az or (builtin[1] if builtin else course)
            title_ru = name_ru or (builtin[2] if builtin else course)
            if builtin and not name_az and not name_ru:
                title_en = builtin[0]
            sections.append({
                "id": course.lower().replace(" ", "-"), "name": title_en,
                "name_az": title_az, "name_ru": title_ru,
                "dishes": [_dish(m, content.get(m.id)) for m in
                           sorted(dishes, key=lambda x: (-x.signature, x.name))],
            })
        sold_out = [{"id": "n%03d" % i, "reason": reasons.get(i, "unavailable")}
                    for i in sorted(unavailable)]
        return {"venue": cfg["restaurant_name"], "currency": cfg["currency"],
                "note": "Browse only. Ordering happens in the dining room.",
                "sections": sections, "unavailable": sold_out,
                "updated": rtime.now().isoformat(timespec="seconds")}


def _dish(m: MenuItem, c: Optional[MenuContent]) -> dict:
    tags = [t.strip() for t in (m.tags or "").split(",") if t.strip()]
    return {
        "id": "n%03d" % m.id, "menu_item_id": m.id, "name": m.name,
        "name_az": (c.name_az if c and c.name_az else ""),
        "name_ru": (c.name_ru if c and c.name_ru else ""),
        "price": round(m.price, 2), "blurb": m.blurb or "",
        "blurb_az": (c.blurb_az if c and c.blurb_az else ""),
        "blurb_ru": (c.blurb_ru if c and c.blurb_ru else ""),
        "image": (c.image_url if c and c.image_url else getattr(m, "image_url", "") or ""),
        "course": m.course, "signature": bool(m.signature), "spice": m.spice,
        "kcal": m.kcal, "hue": m.hue, "available": bool(m.available),
        "diet": [t for t in tags if t in DIET_WORDS],
        "allergens": [t for t in tags if t not in DIET_WORDS],
    }

