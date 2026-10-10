"""SUFRA public booking and smart seating layer — standard-library only."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .. import availability as av, bookings, canon, rtime
from ..database import engine
from ..live import hub
from ..models import DiningTable, Guest, Reservation, Role, Staff, TableStatus
from ..permissions import current_staff

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
TEMPLATES = Jinja2Templates(directory=str(BASE / "templates"))
MANAGERS = {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER}
TURNOVER_MINUTES = 15


def manager(staff: Staff = Depends(current_staff)) -> Staff:
    if staff.role not in MANAGERS:
        raise HTTPException(403, "Owner or manager access required.")
    return staff


def _end(res: Reservation) -> datetime:
    return res.starts_at + timedelta(minutes=int(getattr(res, "duration_minutes", 105) or 105))


def _overlaps(s: Session, table_id: int, when: datetime, duration: int,
              ignore_id: Optional[int] = None) -> bool:
    """Delegates to the one availability engine.

    This module used to carry its own copy of the overlap rules. Two copies of
    "is this table free?" is exactly how a system starts telling a guest and a
    manager different things, so there is now only one."""
    free, _why = av.table_is_free(s, table_id, when, duration, ignore_id)
    return not free


def _pref_score(t: DiningTable, party: int, preference: str) -> float:
    p = (preference or "best available").lower().strip()
    z = (t.zone or "").lower()
    score = 100.0 - max(0, t.seats - party) * 7.0  # keep large tables for large parties

    if "terrace" in p or "outside" in p:
        score += 120 if z == "terrace" else -55
    elif "quiet" in p:
        score += 110 if z == "private" else 48 if z == "main" else -70 if z == "bar" else 15
        # edges/corners of the floor are usually calmer than circulation through the middle
        edge = min(t.x, 1-t.x, t.y, 1-t.y)
        score += max(0, .25-edge) * 80
    elif "window" in p:
        score += 80 if z == "terrace" else 25
        edge = min(t.x, 1-t.x)
        score += max(0, .20-edge) * 150
    elif "bar" in p:
        score += 120 if z == "bar" else -50
    elif "private" in p:
        score += 140 if z == "private" else -80
    elif "main" in p:
        score += 80 if z == "main" else 0

    # Prefer table shapes that make sense for party size.
    if party >= 6 and t.shape == "banquette": score += 18
    if party <= 2 and t.shape == "round": score += 8
    return score


def smart_table(s: Session, party: int, when: datetime, preference: str = "", duration: int = 105,
                ignore_reservation_id: Optional[int] = None):
    """Rank the tables that the availability engine says can take this booking.

    Only the ordering is this module's own opinion; whether a table is free at
    all is decided in one place. "Imminent" is the one case where physical
    occupancy legitimately matters: you cannot seat a walk-in in forty minutes
    at a table that currently has people eating at it."""
    party = max(1, int(party))
    duration = max(45, min(300, int(duration)))
    imminent = abs((when - rtime.now()).total_seconds()) < 45 * 60
    grid = {r["number"]: r for r in
            av.availability(s, when, party, duration,
                            ignore_reservation_id=ignore_reservation_id)["tables"]}
    candidates = []
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if t.zone == canon.ARCHIVED_ZONE or t.seats < party:
            continue
        row = grid.get(t.number)
        if not row or not row["bookable"]:
            continue
        if imminent and t.status not in {TableStatus.AVAILABLE, TableStatus.RESERVED}:
            continue
        candidates.append((_pref_score(t, party, preference), t))
    if not candidates:
        return None, []
    candidates.sort(key=lambda x: (-x[0], x[1].seats, x[1].number))
    return candidates[0][1], [t for _, t in candidates]


def _contact_note(email: str, phone: str, preference: str, note: str) -> str:
    bits = []
    if preference: bits.append(f"Seating preference: {preference}")
    if email: bits.append(f"Email: {email}")
    if phone: bits.append(f"Phone: {phone}")
    if note: bits.append(note)
    return " | ".join(bits)


@router.get("/book", response_class=HTMLResponse)
@router.get("/reserve", response_class=HTMLResponse)
@router.get("/reservations", response_class=HTMLResponse)
def booking_page(request: Request):
    return TEMPLATES.TemplateResponse(request, "booking.html", {})


@router.get("/api/public/booking/availability")
def public_availability(at: str = Query(...), party: int = 2, preference: str = "", duration: int = 105):
    try:
        when = datetime.fromisoformat(at)
    except ValueError:
        raise HTTPException(400, "Choose a valid date and time.")
    if not 1 <= party <= 30 or not 60 <= duration <= 240:
        raise HTTPException(400, "Party size must be 1–30 and duration 60–240 minutes.")
    with Session(engine, expire_on_commit=False) as s:
        table, choices = smart_table(s, party, when, preference, duration)
        return {
            "available": bool(table),
            "suggested_table": table.number if table else None,
            "suggested_zone": table.zone if table else None,
            "matching_tables": [{"number": t.number, "zone": t.zone, "seats": t.seats} for t in choices[:8]],
            "reason": (f"Best match for {preference or 'best available'} while protecting nearby bookings."
                       if table else "No safe table currently fits that party and time."),
        }


@router.post("/api/public/booking")
async def create_public_booking(body: dict = Body(...)):
    """The simple booking page. Same engine, same rows, same rules as the
    3D scene and the manager's own book — including the past-time refusal and
    the transactional conflict check."""
    payload = dict(body)
    payload.setdefault("party_size", body.get("party"))
    payload.setdefault("special_request", body.get("note"))
    name = str(body.get("name") or "").strip()
    if name and not payload.get("first_name"):
        bits = name.split(" ", 1)
        payload["first_name"], payload["last_name"] = bits[0], (bits[1] if len(bits) > 1 else "")
    with Session(engine, expire_on_commit=False) as s:
        try:
            result = bookings.create_reservation(
                s, payload, source="website", actor="Booking page",
                notify_guest=bool(payload.get("email") or payload.get("phone")))
        except bookings.BookingError as err:
            raise HTTPException(err.status, err.message)
        except ValueError:
            raise HTTPException(400, "Choose a valid date and time.")
        res = result["reservation"]
        return {"ok": True, "booking_id": res["id"], "code": res["code"],
                "table": res["table_number"], "zone": res["zone_name"],
                "time": rtime.parse_local(res["at"]).strftime("%a %d %b · %H:%M"),
                "preference": res["preference"], "delivery": result.get("delivery"),
                "message": "Booking confirmed. SUFRA assigned Table %s in %s."
                           % (res["table_number"], res["zone_name"])}


@router.get("/api/enterprise-lite/booking-control")
def booking_control(_: Staff = Depends(manager)):
    now = rtime.now()
    with Session(engine, expire_on_commit=False) as s:
        guests = {g.id: g for g in s.exec(select(Guest)).all()}
        tables = {t.id: t for t in s.exec(select(DiningTable)).all()}
        rows = s.exec(select(Reservation).where(
            Reservation.starts_at >= now - timedelta(hours=3),
            Reservation.starts_at <= now + timedelta(days=7),
            Reservation.status.notin_(["cancelled"]),
        ).order_by(Reservation.starts_at)).all()
        out = []
        for r in rows:
            g = guests.get(r.guest_id)
            t = tables.get(r.table_id)
            pref = (g.seating_pref if g else "") or "Best available"
            suggestion, choices = smart_table(s, r.party_size, r.starts_at, pref,
                                               int(getattr(r, "duration_minutes", 105) or 105), r.id)
            out.append({
                "id": r.id, "name": g.name if g else "Guest", "party": r.party_size,
                "at": r.starts_at.isoformat(timespec="minutes"), "time": r.starts_at.strftime("%a %d %b · %H:%M"),
                "preference": pref, "status": r.status,
                "table_id": r.table_id, "table": t.number if t else None, "zone": t.zone if t else None,
                "suggested_table_id": suggestion.id if suggestion else None,
                "suggested_table": suggestion.number if suggestion else None,
                "choices": [{"id": x.id, "number": x.number, "zone": x.zone, "seats": x.seats} for x in choices[:12]],
            })
        return {"bookings": out}


@router.post("/api/enterprise-lite/reservations/{reservation_id}/assign")
async def override_assignment(reservation_id: int, body: dict = Body(...), actor: Staff = Depends(manager)):
    with Session(engine, expire_on_commit=False) as s:
        r = s.get(Reservation, reservation_id)
        if not r:
            raise HTTPException(404, "Booking not found.")
        # This screen addresses tables by database id, not by the number
        # painted on them; resolve it here so nothing downstream has to guess.
        target = s.get(DiningTable, int(body.get("table_id") or 0))
        if not target:
            raise HTTPException(404, "Table not found.")
        try:
            return bookings.relocate(s, r, target.number,
                                     actor=actor.name, force=bool(body.get("force")))
        except bookings.BookingError as err:
            raise HTTPException(err.status, err.message)
