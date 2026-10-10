"""Availability, holds and the live floor — two different questions.

The bug this module exists to kill: "table 4 has people sitting at it right
now" was being used to answer "can I book table 4 at nine o'clock tonight?".
Those are different questions with different answers, so they get different
functions here and are never mixed:

  live_state()    what is physically happening at each table RIGHT NOW.
                  Driven by DiningTable.status, which waiters and managers
                  set. Colours the digital twin.

  availability()  can this table be BOOKED for a chosen date and time.
                  Driven by reservations, live holds, capacity and whether
                  the table is in service. Never looks at current occupancy.

A reservation stops blocking a slot the moment it is cancelled, marked a
no-show or completed — that is a status test, not a clock test, so history
is preserved while the table is released.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from . import canon, rtime
from .models import (DiningTable, Reservation, TableHold, TableProfile,
                     TableStatus)

# A reservation in one of these states no longer protects its table.
RELEASED_STATUSES = {"cancelled", "no_show", "completed", "left"}
# ...and one in these states still does.
BLOCKING_STATUSES = {"confirmed", "late", "seated", "pending"}

OCCUPIED_TABLE_STATUSES = {
    TableStatus.SEATED, TableStatus.ORDERING, TableStatus.COOKING,
    TableStatus.READY, TableStatus.DINING, TableStatus.NEEDS_WAITER,
    TableStatus.BILL,
}


# ------------------------------------------------------------------- holds

def sweep_holds(s: Session) -> int:
    now = rtime.now()
    stale = s.exec(select(TableHold).where(
        TableHold.status == "held", TableHold.expires_at <= now)).all()
    for h in stale:
        h.status = "expired"
        s.add(h)
    return len(stale)


def live_holds(s: Session, ignore_session: str = "") -> list[TableHold]:
    now = rtime.now()
    rows = s.exec(select(TableHold).where(
        TableHold.status == "held", TableHold.expires_at > now)).all()
    if ignore_session:
        rows = [h for h in rows if h.session_id != ignore_session]
    return rows


# ------------------------------------------------------ overlap arithmetic

def reservation_duration(s: Session, r: Reservation) -> int:
    return int(getattr(r, "duration_minutes", 0) or canon.duration_for(s, r.party_size))


def _overlaps(a_start: datetime, a_minutes: int,
              b_start: datetime, b_minutes: int, buffer_minutes: int) -> bool:
    a_end = a_start + timedelta(minutes=a_minutes + buffer_minutes)
    b_end = b_start + timedelta(minutes=b_minutes + buffer_minutes)
    return a_start < b_end and b_start < a_end


def blocking_reservations(s: Session, when: datetime, span_hours: int = 8) -> list[Reservation]:
    lo = when - timedelta(hours=span_hours)
    hi = when + timedelta(hours=span_hours)
    rows = s.exec(select(Reservation).where(
        Reservation.starts_at >= lo, Reservation.starts_at <= hi)).all()
    return [r for r in rows if (r.status or "confirmed").lower() not in RELEASED_STATUSES]


def table_is_free(s: Session, table_id: int, when: datetime, duration: int,
                  ignore_reservation_id: Optional[int] = None,
                  ignore_session: str = "",
                  reservations: Optional[list[Reservation]] = None,
                  holds: Optional[list[TableHold]] = None,
                  buffer_minutes: Optional[int] = None) -> tuple[bool, str]:
    """Can this table take a booking for [when, when+duration)?"""
    buf = canon.int_setting(s, "turnover_buffer", 15) if buffer_minutes is None else buffer_minutes
    rows = reservations if reservations is not None else blocking_reservations(s, when)
    for r in rows:
        if r.table_id != table_id or (ignore_reservation_id and r.id == ignore_reservation_id):
            continue
        if _overlaps(when, duration, r.starts_at, reservation_duration(s, r), buf):
            return False, "already booked"
    hold_rows = holds if holds is not None else live_holds(s)
    for h in hold_rows:
        if h.table_id != table_id or (ignore_session and h.session_id == ignore_session):
            continue
        if _overlaps(when, duration, h.starts_at, h.duration_minutes, buf):
            return False, "someone is booking it right now"
    return True, ""


# ------------------------------------------------------- the two questions

def availability(s: Session, when: datetime, party: int = 0,
                 duration: Optional[int] = None, session_id: str = "",
                 ignore_reservation_id: Optional[int] = None) -> dict:
    """Bookability of every table for one chosen slot. Never reads occupancy."""
    cfg = canon.service_config(s)
    duration = int(duration or canon.duration_for(s, party or 2))
    reservations = blocking_reservations(s, when)
    holds = live_holds(s)
    profiles = {p.table_id: p for p in s.exec(select(TableProfile)).all()}
    now = rtime.now()
    past = when < now - timedelta(minutes=1)

    open_min = rtime.minutes_of(rtime.combine(when.date(), cfg["open"]))
    last_min = rtime.minutes_of(rtime.combine(when.date(), cfg["last_seating"]))
    want_min = rtime.minutes_of(when)
    closed = not (open_min <= want_min <= last_min)

    rows = []
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if t.zone == canon.ARCHIVED_ZONE:
            continue
        p = profiles.get(t.id)
        state, reason, until = "AVAILABLE", "", None

        if p is not None and p.blocked:
            state, reason = "BLOCKED", (p.blocked_reason or "out of service")
        elif past:
            state, reason = "PAST", "that time has already passed"
        elif closed:
            state, reason = "CLOSED", "we are not seating at that time"
        elif party and not (min(p.min_party if p else 1, t.seats) <= party <= t.seats):
            state, reason = "INCOMPATIBLE", "seats %d–%d" % (
                min(p.min_party if p else 1, t.seats), t.seats)

        if state == "AVAILABLE":
            for r in reservations:
                if r.table_id != t.id or (ignore_reservation_id and r.id == ignore_reservation_id):
                    continue
                if _overlaps(when, duration, r.starts_at, reservation_duration(s, r),
                             cfg["turnover_buffer"]):
                    state, reason = "RESERVED", "already booked"
                    until = (r.starts_at + timedelta(minutes=reservation_duration(s, r))).strftime("%H:%M")
                    break

        if state == "AVAILABLE":
            for h in holds:
                if h.table_id != t.id:
                    continue
                if _overlaps(when, duration, h.starts_at, h.duration_minutes,
                             cfg["turnover_buffer"]):
                    mine = session_id and h.session_id == session_id
                    state = "HELD_BY_YOU" if mine else "HELD"
                    reason = ("you are holding this table" if mine
                              else "someone is booking it right now")
                    until = h.expires_at.isoformat(timespec="seconds")
                    break

        nxt = None
        if state in ("RESERVED", "HELD"):
            step = max(5, cfg["slot_minutes"])
            for m in range(want_min, last_min + 1, step):
                cand = rtime.combine(when.date(), rtime.hhmm(m))
                free, _ = table_is_free(s, t.id, cand, duration, ignore_reservation_id,
                                        session_id, reservations, holds,
                                        cfg["turnover_buffer"])
                if free:
                    nxt = rtime.hhmm(m)
                    break

        rows.append({
            "table_id": canon.scene_id_for(t.number), "number": t.number,
            "os_table_id": t.id, "label": str(t.number),
            "zone": (p.area if p and p.area else (t.zone or "").lower()),
            "seats": t.seats, "state": state, "bookable": state in ("AVAILABLE", "HELD_BY_YOU"),
            "reason": reason, "until": until, "next_available": nxt,
        })

    return {
        "date": when.date().isoformat(), "time": when.strftime("%H:%M"),
        "at": when.isoformat(timespec="minutes"),
        "party_size": party, "duration": duration,
        "is_past": past, "is_closed": closed,
        "server_now": now.isoformat(timespec="seconds"),
        "tables": rows,
        "available": sum(1 for r in rows if r["bookable"]),
    }


def live_state(s: Session, session_id: str = "") -> dict:
    """What the room is doing right now. Physical occupancy only.

    `session_id` lets the room tell a guest apart from everyone else: a
    table THEY are holding is theirs to book, and showing it as "being
    booked" alongside a waitlist offer is the room arguing with itself.
    """
    now = rtime.now()
    cfg = canon.service_config(s)
    profiles = {p.table_id: p for p in s.exec(select(TableProfile)).all()}
    horizon = now + timedelta(minutes=90)
    upcoming: dict[int, list[Reservation]] = {}
    for r in s.exec(select(Reservation).where(
            Reservation.starts_at >= now - timedelta(hours=6),
            Reservation.starts_at <= horizon)).all():
        if (r.status or "").lower() in RELEASED_STATUSES or r.table_id is None:
            continue
        upcoming.setdefault(r.table_id, []).append(r)
    held = {h.table_id: h.session_id for h in live_holds(s)}

    rows, guests_now = [], 0
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if t.zone == canon.ARCHIVED_ZONE:
            continue
        p = profiles.get(t.id)
        mine = sorted(upcoming.get(t.id, []), key=lambda r: r.starts_at)
        seated = next((r for r in mine if (r.status or "") == "seated"), None)
        soon = next((r for r in mine if (r.status or "") in ("confirmed", "late")
                     and now <= r.starts_at <= horizon), None)
        late = next((r for r in mine if (r.status or "") == "late"), None)

        if p is not None and p.blocked:
            state = "BLOCKED"
        elif t.status in OCCUPIED_TABLE_STATUSES:
            state = "OCCUPIED"
        elif t.status == TableStatus.CLEANING:
            state = "CLEANING"
        elif late is not None:
            state = "LATE"
        elif soon is not None:
            state = "RESERVED_SOON"
        elif t.id in held:
            state = "HELD_BY_YOU" if (session_id and held[t.id] == session_id) else "HELD"
        else:
            state = "AVAILABLE"

        party = t.party_size or (seated.party_size if seated else 0)
        if state == "OCCUPIED":
            guests_now += party

        since = t.seated_at.strftime("%H:%M") if t.seated_at else None
        until = None
        if seated:
            until = (seated.starts_at + timedelta(minutes=reservation_duration(s, seated))).strftime("%H:%M")
        elif t.seated_at:
            until = (t.seated_at + timedelta(minutes=cfg["default_duration"])).strftime("%H:%M")

        until_next = None
        if state == "AVAILABLE":
            future = [r.starts_at for r in mine if r.starts_at > now]
            until_next = ("free until %s" % min(future).strftime("%H:%M")) if future else "free all evening"

        rows.append({
            "table_id": canon.scene_id_for(t.number), "number": t.number,
            "os_table_id": t.id, "label": str(t.number),
            "zone": (p.area if p and p.area else (t.zone or "").lower()),
            "state": state, "os_status": t.status.value, "guests": party,
            "since": since, "until": until, "until_next": until_next,
            "elapsed_min": round((now - t.seated_at).total_seconds() / 60) if t.seated_at else None,
            "upcoming": soon.starts_at.strftime("%H:%M") if soon else None,
            "reservation_id": (seated or late or soon).id if (seated or late or soon) else None,
            "code": (seated or late or soon).code if (seated or late or soon) else None,
            "guest_name": ((seated or late or soon).last_name or None) if (seated or late or soon) else None,
        })

    open_min = rtime.minutes_of(rtime.combine(now.date(), cfg["open"]))
    close_min = rtime.minutes_of(rtime.combine(now.date(), cfg["close"]))
    n = rtime.minutes_of(now)
    if not (open_min <= n < close_min):
        service = "closed"
    elif n < 16 * 60:
        service = "lunch"
    else:
        service = "dinner"

    counts = {
        "tables": len(rows),
        "occupied": sum(1 for r in rows if r["state"] == "OCCUPIED"),
        "available": sum(1 for r in rows if r["state"] == "AVAILABLE"),
        "reserved_soon": sum(1 for r in rows if r["state"] in ("RESERVED_SOON", "LATE")),
        "held": sum(1 for r in rows if r["state"] in ("HELD", "HELD_BY_YOU")),
        "cleaning": sum(1 for r in rows if r["state"] == "CLEANING"),
        "guests": guests_now,
    }
    seats = sum(t.seats for t in s.exec(select(DiningTable)).all() if t.zone != canon.ARCHIVED_ZONE)
    counts["load_pct"] = int(round(100.0 * guests_now / max(1, seats)))
    # A monotonic revision so another process can tell in one cheap read
    # whether anything has actually changed since it last looked.
    from .models import LiveEvent
    last = s.exec(select(LiveEvent.id).order_by(LiveEvent.id.desc()).limit(1)).first()
    return {"at": now.isoformat(timespec="seconds"), "date": now.date().isoformat(),
            "service": service, "revision": int(last or 0),
            "tables": rows, "counts": counts}


# ------------------------------------------------------------ hold writing

def create_hold(s: Session, table_id: int, when: datetime, party: int,
                session_id: str, duration: Optional[int] = None,
                source: str = "sufra_360") -> dict:
    """Take a courtesy hold. Caller commits."""
    cfg = canon.service_config(s)
    duration = int(duration or canon.duration_for(s, party))
    t = s.get(DiningTable, table_id)
    if not t or t.zone == canon.ARCHIVED_ZONE:
        return {"ok": False, "error": "unknown_table"}
    if when < rtime.now() - timedelta(minutes=1):
        return {"ok": False, "error": "past"}
    if party and not (1 <= party <= t.seats):
        return {"ok": False, "error": "capacity",
                "message": "Table %d seats up to %d." % (t.number, t.seats)}

    sweep_holds(s)
    for h in s.exec(select(TableHold).where(
            TableHold.status == "held", TableHold.session_id == session_id)).all():
        h.status = "released"
        s.add(h)

    free, why = table_is_free(s, table_id, when, duration, None, session_id)
    if not free:
        return {"ok": False, "error": "held" if "booking it" in why else "reserved",
                "message": "Table %d is not free at %s." % (t.number, when.strftime("%H:%M"))}

    hold = TableHold(id=secrets.token_hex(8), table_id=table_id, starts_at=when,
                     duration_minutes=duration, party_size=party or 2,
                     session_id=session_id, status="held",
                     expires_at=rtime.now() + timedelta(seconds=cfg["hold_seconds"]),
                     created_at=rtime.now(), source=source)
    s.add(hold)
    return {"ok": True, "hold": {
        "id": hold.id, "table_id": canon.scene_id_for(t.number), "number": t.number,
        "date": when.date().isoformat(), "time": when.strftime("%H:%M"),
        "duration": duration, "party_size": hold.party_size,
        "expires_at": hold.expires_at.isoformat(timespec="seconds"),
        "seconds_remaining": cfg["hold_seconds"]}}


def release_hold(s: Session, hold_id: str, session_id: str = "") -> dict:
    h = s.get(TableHold, hold_id)
    if not h:
        return {"ok": False, "error": "not_found"}
    if session_id and h.session_id != session_id:
        return {"ok": False, "error": "not_yours"}
    h.status = "released"
    s.add(h)
    return {"ok": True}
