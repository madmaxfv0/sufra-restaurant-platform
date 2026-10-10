"""The reservation service: one lifecycle, one set of rules, one writer.

Every surface — SUFRA 360, the manager's book, the phone-booking modal, the
waitlist conversion — comes through here, so the rules cannot drift apart.

Lifecycle
    confirmed → seated → completed
    confirmed → late   → seated | no_show
    confirmed → cancelled
A reservation in cancelled / no_show / completed no longer protects its
table (see availability.RELEASED_STATUSES) but the row is never deleted:
the book keeps its history.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from . import allergens as allergen_check, availability as av, canon, dblock, events, notify, rtime
from .models import (DiningTable, Guest, Notification, Reservation, TableHold,
                     TableNote, TableProfile, TableStatus, WaitlistEntry)

# Bookings the restaurant did not take itself. They are confirmed to the
# guest straight away, but somebody on the floor still has to see them.
SELF_SERVE_SOURCES = {"sufra_360", "website"}

STATUSES = ("confirmed", "late", "seated", "completed", "cancelled", "no_show")
SOURCES = {"website", "phone", "walk-in", "instagram", "concierge", "sufra_360", "waitlist"}


class BookingError(Exception):
    def __init__(self, message: str, code: str = "refused", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


# ------------------------------------------------------------- validation

def validate_slot(s: Session, when: datetime, party: int, duration: int) -> None:
    """Everything that makes a requested slot illegal, in one place.

    This runs on the server for every booking path, including the ones a
    guest could reach with a hand-written request. A disabled button in the
    browser is a courtesy, never the rule.
    """
    cfg = canon.service_config(s)
    now = rtime.now()
    if when < now:
        raise BookingError("That time has already passed. Please choose a later time.",
                           "past", 400)
    if when > now + timedelta(days=365):
        raise BookingError("Bookings open up to a year ahead.", "too_far", 400)
    if not 1 <= party <= cfg["max_party"]:
        raise BookingError("Party size must be between 1 and %d." % cfg["max_party"],
                           "party", 400)
    if not 45 <= duration <= 300:
        raise BookingError("Booking length must be between 45 and 300 minutes.",
                           "duration", 400)
    open_min = rtime.minutes_of(rtime.combine(when.date(), cfg["open"]))
    last_min = rtime.minutes_of(rtime.combine(when.date(), cfg["last_seating"]))
    if not open_min <= rtime.minutes_of(when) <= last_min:
        raise BookingError("We seat between %s and %s." % (cfg["open"], cfg["last_seating"]),
                           "closed", 400)


def resolve_table(s: Session, table_ref) -> DiningTable:
    """Accept a table number, an OS row id or a scene id — one table out."""
    t = None
    if isinstance(table_ref, str):
        number = canon.number_from_scene_id(table_ref)
        if number is not None:
            t = s.exec(select(DiningTable).where(DiningTable.number == number)).first()
    elif table_ref is not None:
        t = s.exec(select(DiningTable).where(DiningTable.number == int(table_ref))).first()
        if t is None:
            t = s.get(DiningTable, int(table_ref))
    if not t or t.zone == canon.ARCHIVED_ZONE:
        raise BookingError("That table is not on the floor.", "unknown_table", 404)
    return t


def table_profile(s: Session, table_id: int) -> Optional[TableProfile]:
    return s.exec(select(TableProfile).where(TableProfile.table_id == table_id)).first()


def best_table(s: Session, when: datetime, party: int, duration: int,
               preference: str = "", ignore_reservation_id: Optional[int] = None,
               session_id: str = "") -> Optional[DiningTable]:
    """Smallest safe table that fits, biased by the guest's own preference."""
    grid = av.availability(s, when, party, duration, session_id, ignore_reservation_id)
    free = {r["number"] for r in grid["tables"] if r["bookable"]}
    if not free:
        return None
    pref = (preference or "").lower()
    best, best_score = None, -1e9
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if t.number not in free:
            continue
        p = table_profile(s, t.id)
        score = 100.0 - max(0, t.seats - party) * 6.0
        area = (p.area if p else (t.zone or "").lower())
        import json as _json
        sc = _json.loads(p.scores) if p and p.scores else {}
        for words, key in (("quiet calm sakit тих", "quiet"),
                           ("romantic date anniversary romantik роман", "romantic"),
                           ("window pəncərə окн", "window_proximity"),
                           ("view mənzərə вид", "view"),
                           ("sea water dəniz море", "sea_view"),
                           ("private privacy özəl приват", "privacy"),
                           ("lively canlı живо", "lively")):
            if any(w in pref for w in words.split()):
                score += 40 * float(sc.get(key, 0))
        for words, zone in (("terrace outdoor teras террас", "terrace"),
                            ("garden bağ сад", "garden"),
                            ("bar counter бар", "bar"),
                            ("private özəl приват", "private")):
            if any(w in pref for w in words.split()) and area == zone:
                score += 60
        if "accessible" in pref or "wheelchair" in pref:
            score += 80 if (p and p.accessible) else -80
        if score > best_score:
            best, best_score = t, score
    return best


# --------------------------------------------------------------- creation

def _guest_row(s: Session, first: str, last: str, email: str, phone: str,
               allergies: str, preference: str, note: str) -> Guest:
    name = (" ".join(x for x in [first, last] if x)).strip() or "Guest"
    guest = None
    if email:
        for g in s.exec(select(Guest).where(Guest.name == name)).all():
            if email.lower() in (g.note or "").lower():
                guest = g
                break
    if guest is None:
        guest = s.exec(select(Guest).where(Guest.name == name)).first()
    contact = " · ".join(x for x in [phone, email] if x)
    if guest is None:
        guest = Guest(name=name, visits=0, allergies=allergies[:2000],
                      seating_pref=preference[:200], note=(contact + (" · " + note if note else ""))[:2000])
        s.add(guest)
        s.flush()
    else:
        if allergies:
            guest.allergies = allergies[:2000]
        if preference:
            guest.seating_pref = preference[:200]
        if contact and contact not in (guest.note or ""):
            guest.note = ((guest.note + " · ") if guest.note else "") + contact
        s.add(guest)
    return guest


def create_reservation(s: Session, payload: dict, *, session_id: str = "",
                       source: str = "sufra_360", actor: str = "SUFRA 360",
                       notify_guest: bool = True) -> dict:
    """Create one booking, race-safe, with the guest's own details attached."""
    first = str(payload.get("first_name") or "").strip()
    last = str(payload.get("last_name") or "").strip()
    if not first and payload.get("name"):
        bits = str(payload["name"]).strip().split(" ", 1)
        first, last = bits[0], (bits[1] if len(bits) > 1 else "")
    email = str(payload.get("email") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    if not first:
        raise BookingError("A first name is required.", "missing_fields")
    if source == "sufra_360":
        if not last:
            raise BookingError("A last name is required.", "missing_fields")
        if "@" not in email or "." not in email.split("@")[-1]:
            raise BookingError("That email address does not look right.", "bad_email")
        if len(phone) < 6:
            raise BookingError("A mobile number is required.", "missing_fields")

    try:
        party = int(payload.get("party_size") or payload.get("party") or 2)
    except (TypeError, ValueError):
        raise BookingError("Party size must be a number.", "party")

    when = payload.get("_when")
    if when is None:
        if payload.get("date") and payload.get("time"):
            when = rtime.combine(datetime.fromisoformat(str(payload["date"])).date(),
                                 str(payload["time"]))
        elif payload.get("at") or payload.get("starts_at"):
            when = rtime.parse_local(str(payload.get("at") or payload.get("starts_at")))
        else:
            raise BookingError("Choose a date and a time.", "bad_date")
    when = when.replace(second=0, microsecond=0)

    duration = int(payload.get("duration") or canon.duration_for(s, party))
    validate_slot(s, when, party, duration)

    table = resolve_table(s, payload.get("table_id") or payload.get("table_number")
                          or payload.get("table")) if (
        payload.get("table_id") or payload.get("table_number") or payload.get("table")) else None
    preference = str(payload.get("preference") or "").strip()
    if table is None:
        table = best_table(s, when, party, duration, preference, session_id=session_id)
        if table is None:
            raise BookingError(
                "No table can take that party at that time. Try another time, or join the waitlist.",
                "no_capacity", 409)
    if party > table.seats:
        raise BookingError("Table %d seats up to %d." % (table.number, table.seats),
                           "capacity", 409)
    p = table_profile(s, table.id)
    if p is not None and p.blocked:
        raise BookingError("Table %d is out of service." % table.number, "blocked", 409)
    # The house keeps its larger tables for larger parties, and the 3D room
    # already shows that as "wrong size". A guest must not be able to book past
    # it; staff can still seat whoever they like at whatever table.
    minimum = min(int(p.min_party) if p else 1, table.seats)
    if source in ("sufra_360", "website") and party < minimum:
        raise BookingError("Table %d seats %d–%d." % (table.number, minimum, table.seats),
                           "capacity", 409)

    idem = str(payload.get("idempotency_key") or "").strip()
    if idem:
        prev = s.exec(select(Reservation).where(Reservation.idempotency_key == idem)).first()
        if prev:
            return {"ok": True, "replayed": True, "reservation": public_dict(s, prev)}

    guest = _guest_row(s, first, last, email, phone,
                       str(payload.get("allergies") or ""), preference,
                       str(payload.get("special_request") or ""))
    s.commit()

    now = rtime.now()
    lang = notify._lang(payload.get("language") or "en")
    token = secrets.token_urlsafe(18)
    note = " · ".join(x for x in [
        ("Preference: " + preference) if preference else "",
        str(payload.get("special_request") or ""),
    ] if x)

    # --- the critical section ------------------------------------------
    # Everything above is validation; from here the answer to "is this
    # table free?" must not change before the row exists.
    with dblock.immediate() as con:
        if con is None:                                   # PostgreSQL path
            free, why = av.table_is_free(s, table.id, when, duration, None, session_id)
            if not free:
                raise BookingError("Table %d is no longer free at %s."
                                   % (table.number, when.strftime("%H:%M")), "conflict", 409)
            r = Reservation(guest_id=guest.id, table_id=table.id, party_size=party,
                            starts_at=when, status="confirmed", duration_minutes=duration,
                            source=source, note=note, occasion=str(payload.get("occasion") or ""),
                            staff_decision=("pending" if source in SELF_SERVE_SOURCES else "accepted"))
            s.add(r)
            s.commit()
            s.refresh(r)
            reservation_id = r.id
        else:
            buf = canon.int_setting(s, "turnover_buffer", 15)
            end = when + timedelta(minutes=duration + buf)
            start = when - timedelta(minutes=buf)
            for row in con.execute(
                    "SELECT id,starts_at,duration_minutes,status FROM reservation "
                    "WHERE table_id=? AND starts_at BETWEEN ? AND ?",
                    (table.id, dblock.ts(when - timedelta(hours=8)),
                     dblock.ts(when + timedelta(hours=8)))):
                if (row["status"] or "").lower() in av.RELEASED_STATUSES:
                    continue
                rs = dblock.parse_ts(row["starts_at"])
                if rs is None:
                    continue
                re_ = rs + timedelta(minutes=int(row["duration_minutes"] or duration) + buf)
                if start < re_ and rs < end:
                    raise BookingError("Table %d is no longer free at %s."
                                       % (table.number, when.strftime("%H:%M")),
                                       "conflict", 409)
            for row in con.execute(
                    "SELECT session_id,starts_at,duration_minutes FROM tablehold "
                    "WHERE table_id=? AND status='held' AND expires_at>?",
                    (table.id, dblock.ts(now))):
                if session_id and row["session_id"] == session_id:
                    continue
                hs = dblock.parse_ts(row["starts_at"])
                if hs is None:
                    continue
                he = hs + timedelta(minutes=int(row["duration_minutes"] or duration) + buf)
                if start < he and hs < end:
                    raise BookingError("Someone else is completing a booking for table %d."
                                       % table.number, "conflict", 409)

            cur = con.execute(
                "INSERT INTO reservation (guest_id,table_id,party_size,starts_at,status,"
                "occasion,note,deposit,source,created_at,no_show_risk,duration_minutes,"
                "code,first_name,last_name,email,phone,allergies,dietary,accessibility,"
                "high_chairs,special_request,preference,language,marketing_opt_in,"
                "guest_confirmation_status,confirm_token,updated_at,idempotency_key,"
                "staff_decision,decided_by,decline_reason) "
                "VALUES (?,?,?,?,'confirmed',?,?,0,?,?,0,?,'',?,?,?,?,?,?,?,?,?,?,?,?,"
                "'pending',?,?,?,?,'','')",
                (guest.id, table.id, party, dblock.ts(when),
                 str(payload.get("occasion") or ""), note, source, dblock.ts(now), duration,
                 first, last, email, phone, str(payload.get("allergies") or ""),
                 str(payload.get("dietary") or ""), str(payload.get("accessibility") or ""),
                 int(payload.get("high_chairs") or 0), str(payload.get("special_request") or ""),
                 preference, lang, 1 if payload.get("marketing_opt_in") else 0,
                 token, dblock.ts(now), idem,
                 # named in the INSERT: a database created fresh has no column
                 # default for these, only one migrated by canon.ensure_schema does
                 "pending" if source in SELF_SERVE_SOURCES else "accepted"))
            reservation_id = cur.lastrowid
            con.execute("UPDATE reservation SET code=? WHERE id=?",
                        (canon.booking_code(reservation_id), reservation_id))
            con.execute("UPDATE tablehold SET status='converted' "
                        "WHERE session_id=? AND status='held'", (session_id,))
    # --- end critical section ------------------------------------------

    s.expire_all()
    r = s.get(Reservation, reservation_id)
    if r.table_id and when - now <= timedelta(minutes=90):
        t = s.get(DiningTable, r.table_id)
        if t and t.status == TableStatus.AVAILABLE:
            t.status = TableStatus.RESERVED
            s.add(t)
    events.record(s, "reservation_created", "Reservation created",
                  detail="%s · %s · %d %s" % (
                      r.code, when.strftime("%d %b %H:%M"), party,
                      "guest" if party == 1 else "guests"),
                  table_id=table.id, table_number=table.number,
                  reservation_id=r.id, actor=actor, source=source,
                  audience="staff", severity="good")
    s.add(Notification(level="note", title="%s %s booked for %d" % (first, last, party),
                       body="%s · Table %d · %s" % (when.strftime("%a %d %b %H:%M"),
                                                    table.number, r.code),
                       audience="manager"))
    s.commit()

    # No email or SMS is sent to guests anywhere in SUFRA — the booking is
    # confirmed the moment it is made, and this response is the
    # confirmation. notify_guest is kept in the signature for callers that
    # still pass it, but nothing sends because of it any more.
    return {"ok": True, "reservation": public_dict(s, r), "delivery": None}


# ------------------------------------------------------------ transitions

def set_status(s: Session, r: Reservation, status: str, *, actor: str = "SUFRA",
               source: str = "sufra_os") -> dict:
    status = (status or "").strip().lower()
    if status == "left":
        status = "completed"
    if status not in STATUSES:
        raise BookingError("Choose a valid booking status.", "bad_status")
    if (r.status or "") in ("cancelled", "no_show") and status not in ("cancelled", "no_show"):
        raise BookingError("A cancelled or no-show booking cannot be reopened.",
                           "closed", 409)
    now = rtime.now()
    table = s.get(DiningTable, r.table_id) if r.table_id else None
    r.status = status
    r.updated_at = now

    kind, title, severity = "reservation_updated", "Reservation updated", "note"
    if status == "seated":
        r.seated_at = now
        kind, title, severity = "guest_seated", "Guest seated", "good"
        carry_allergies_to_table(s, r, table)
        if table:
            table.status = TableStatus.SEATED
            table.party_size = r.party_size
            table.guest_id = r.guest_id
            table.seated_at = now
            table.last_touched_at = now
            s.add(table)
    elif status == "completed":
        r.completed_at = now
        r.left_at = now
        kind, title = "reservation_completed", "Reservation completed"
        if table:
            table.status = TableStatus.AVAILABLE
            table.party_size = 0
            table.guest_id = None
            table.seated_at = None
            table.last_touched_at = now
            s.add(table)
    elif status == "cancelled":
        r.cancelled_at = now
        kind, title, severity = "reservation_cancelled", "Reservation cancelled", "warning"
        _release_table_if_idle(s, table, now)
    elif status == "no_show":
        r.no_show_at = now
        kind, title, severity = "guest_no_show", "Guest marked no-show", "warning"
        _release_table_if_idle(s, table, now)
    elif status == "late":
        kind, title, severity = "guest_late", "Guest marked late", "warning"

    s.add(r)
    events.record(s, kind, title, detail="%s · %s" % (r.code, r.starts_at.strftime("%H:%M")),
                  table_id=table.id if table else None,
                  table_number=table.number if table else None,
                  reservation_id=r.id, actor=actor, source=source, severity=severity)
    s.commit()
    return {"ok": True, "status": r.status, "reservation": public_dict(s, r)}


def seated_reservation_on(s: Session, table_id: int) -> Optional[Reservation]:
    """The party actually sitting at this table, if the book knows about one."""
    rows = s.exec(select(Reservation).where(
        Reservation.table_id == table_id, Reservation.status == "seated")).all()
    return max(rows, key=lambda r: r.seated_at or r.starts_at) if rows else None


def carry_allergies_to_table(s: Session, r: Reservation,
                             table: Optional[DiningTable]) -> Optional[TableNote]:
    """Put what the guest told us at booking onto the table they sit at.

    An allergy written into a booking three weeks ago is no use to the
    waiter unless it is in front of them when the party arrives. Seating a
    booking therefore writes it onto the table as an unacknowledged allergy
    note, which the order pad already refuses to send past until somebody
    has read it. Caller commits.
    """
    if table is None:
        return None
    declared = " · ".join(x for x in [
        (r.allergies or "").strip(),
        (r.special_request or "").strip() if allergen_check.looks_like_allergy(r.special_request or "") else "",
        (r.dietary or "").strip() if allergen_check.looks_like_allergy(r.dietary or "") else "",
    ] if x)
    found, unknown = allergen_check.parse(declared)
    if not found and not unknown:
        return None

    guest = (" ".join(x for x in [r.first_name, r.last_name] if x)).strip() or "Guest"
    message = "%s (booking %s): %s" % (guest, r.code or "", declared)
    existing = s.exec(select(TableNote).where(
        TableNote.table_id == table.id, TableNote.kind == "allergy",
        TableNote.message == message)).first()
    if existing:
        return existing

    note = TableNote(table_id=table.id, author_id=None, author_name="From the booking",
                     kind="allergy", message=message, acknowledged=False)
    s.add(note)
    events.record(s, "allergy_flagged", "Allergy on this table",
                  detail=message, table_id=table.id, table_number=table.number,
                  reservation_id=r.id, actor="SUFRA", severity="warning")
    return note


def _release_table_if_idle(s: Session, table: Optional[DiningTable], now: datetime) -> None:
    """A released booking must stop holding a table it never occupied.

    Only the reserved/available states are touched: a table with people
    physically sitting at it stays occupied whatever the book says.
    """
    if table is None:
        return
    if table.status == TableStatus.RESERVED:
        table.status = TableStatus.AVAILABLE
        table.party_size = 0
        table.guest_id = None
        table.last_touched_at = now
        s.add(table)


def decide(s: Session, r: Reservation, accept: bool, *, actor: str = "SUFRA",
           reason: str = "") -> dict:
    """Accept a self-serve booking, or decline it and tell the guest.

    Declining is a cancellation with a reason attached and a message to the
    guest — quietly dropping a table somebody believes they have booked is
    the one outcome this must never produce.
    """
    now = rtime.now()
    table = s.get(DiningTable, r.table_id) if r.table_id else None
    r.staff_decision = "accepted" if accept else "declined"
    r.decided_at = now
    r.decided_by = actor
    r.updated_at = now

    if accept:
        s.add(r)
        events.record(s, "reservation_accepted", "Reservation accepted",
                      detail="%s · %s" % (r.code, r.source.replace("_", " ")),
                      table_id=table.id if table else None,
                      table_number=table.number if table else None,
                      reservation_id=r.id, actor=actor, severity="good")
        s.commit()
        return {"ok": True, "decision": "accepted",
                "message": "%s accepted." % r.code,
                "reservation": manager_dict(s, r)}

    r.decline_reason = (reason or "").strip()
    r.status = "cancelled"
    r.cancelled_at = now
    s.add(r)
    _release_table_if_idle(s, table, now)
    events.record(s, "reservation_declined", "Reservation declined",
                  detail="%s · %s" % (r.code, r.decline_reason or "no reason given"),
                  table_id=table.id if table else None,
                  table_number=table.number if table else None,
                  reservation_id=r.id, actor=actor, severity="warning")
    s.commit()
    # No automatic email/SMS goes out — a declined booking is staff's own
    # call to make with the guest, by phone or however they normally reach
    # them.
    return {"ok": True, "decision": "declined", "delivery": None,
            "message": "%s declined. Let the guest know directly." % r.code,
            "reservation": manager_dict(s, r)}


def relocate(s: Session, r: Reservation, table_ref, *, actor: str = "SUFRA",
             force: bool = False) -> dict:
    target = resolve_table(s, table_ref)
    if r.table_id == target.id:
        return {"ok": True, "unchanged": True, "table": target.number}
    if r.party_size > target.seats:
        raise BookingError("Table %d seats up to %d." % (target.number, target.seats),
                           "capacity", 409)
    duration = av.reservation_duration(s, r)
    free, why = av.table_is_free(s, target.id, r.starts_at, duration, r.id)
    if not free and not force:
        raise BookingError("Table %d conflicts with another booking at that time."
                           % target.number, "conflict", 409)
    previous = s.get(DiningTable, r.table_id) if r.table_id else None
    r.table_id = target.id
    r.updated_at = rtime.now()
    s.add(r)
    if previous and previous.id != target.id:
        _release_table_if_idle(s, previous, rtime.now())
    if (r.status or "") == "seated":
        if previous:
            previous.status = TableStatus.AVAILABLE
            previous.party_size = 0
            previous.guest_id = None
            s.add(previous)
        target.status = TableStatus.SEATED
        target.party_size = r.party_size
        target.guest_id = r.guest_id
        target.seated_at = r.seated_at or rtime.now()
        s.add(target)
    events.record(s, "reservation_moved", "Reservation moved",
                  detail="%s · Table %s → Table %d" % (
                      r.code, previous.number if previous else "—", target.number),
                  table_id=target.id, table_number=target.number,
                  reservation_id=r.id, actor=actor, severity="note")
    s.commit()
    return {"ok": True, "table": target.number, "conflict_overridden": bool(not free)}


EDITABLE = ("first_name", "last_name", "email", "phone", "allergies", "dietary",
            "accessibility", "special_request", "preference", "occasion",
            "language", "note")


def update(s: Session, r: Reservation, body: dict, *, actor: str = "SUFRA") -> dict:
    """Manager edit. Re-runs every availability rule the booking must obey."""
    now = rtime.now()
    party = int(body.get("party_size") or body.get("party") or r.party_size)
    duration = int(body.get("duration") or av.reservation_duration(s, r))
    when = r.starts_at
    if body.get("at"):
        when = rtime.parse_local(str(body["at"])).replace(second=0, microsecond=0)
    elif body.get("date") or body.get("time"):
        day = (datetime.fromisoformat(str(body["date"])).date() if body.get("date")
               else r.starts_at.date())
        when = rtime.combine(day, str(body.get("time") or r.starts_at.strftime("%H:%M")))

    moved = when != r.starts_at or party != r.party_size or duration != av.reservation_duration(s, r)
    if moved and (r.status or "") in ("confirmed", "late"):
        validate_slot(s, when, party, duration)

    table = s.get(DiningTable, r.table_id) if r.table_id else None
    if body.get("table_id") or body.get("table_number") or body.get("table"):
        table = resolve_table(s, body.get("table_id") or body.get("table_number")
                              or body.get("table"))
    if table is None:
        raise BookingError("Assign a table before saving.", "unknown_table", 400)
    if party > table.seats:
        raise BookingError("Table %d seats up to %d." % (table.number, table.seats),
                           "capacity", 409)
    free, _ = av.table_is_free(s, table.id, when, duration, r.id)
    if not free and not body.get("force"):
        raise BookingError("Table %d already has a booking overlapping that time."
                           % table.number, "conflict", 409)

    previous_table = r.table_id
    r.starts_at = when
    r.party_size = party
    r.duration_minutes = duration
    r.table_id = table.id
    for field in EDITABLE:
        if field in body and body[field] is not None:
            setattr(r, field, str(body[field])[:2000])
    if "high_chairs" in body:
        r.high_chairs = int(body.get("high_chairs") or 0)
    r.updated_at = now
    s.add(r)
    if previous_table and previous_table != table.id:
        _release_table_if_idle(s, s.get(DiningTable, previous_table), now)
    guest = s.get(Guest, r.guest_id) if r.guest_id else None
    if guest:
        name = (" ".join(x for x in [r.first_name, r.last_name] if x)).strip()
        if name:
            guest.name = name
        if r.allergies:
            guest.allergies = r.allergies
        if r.preference:
            guest.seating_pref = r.preference
        s.add(guest)
    events.record(s, "reservation_updated", "Reservation updated",
                  detail="%s · %s · %d guests · Table %d" % (
                      r.code, when.strftime("%d %b %H:%M"), party, table.number),
                  table_id=table.id, table_number=table.number,
                  reservation_id=r.id, actor=actor)
    s.commit()
    return {"ok": True, "reservation": public_dict(s, r),
            "conflict_overridden": bool(not free)}


def confirm_attendance(s: Session, token: str) -> Optional[Reservation]:
    r = s.exec(select(Reservation).where(Reservation.confirm_token == token)).first()
    if not r or not token:
        return None
    if r.guest_confirmation_status != "confirmed":
        r.guest_confirmation_status = "confirmed"
        r.guest_confirmed_at = rtime.now()
        r.updated_at = rtime.now()
        s.add(r)
        t = s.get(DiningTable, r.table_id) if r.table_id else None
        events.record(s, "guest_confirmed", "Guest confirmed attendance",
                      detail=r.code, table_id=t.id if t else None,
                      table_number=t.number if t else None, reservation_id=r.id,
                      actor="Guest", source="guest", severity="good")
        s.commit()
    return r


# ---------------------------------------------------------------- waitlist

def join_waitlist(s: Session, body: dict, *, source: str = "sufra_360",
                  actor: str = "SUFRA 360") -> dict:
    name = str(body.get("name") or " ".join(
        x for x in [body.get("first_name"), body.get("last_name")] if x)).strip()
    if not name:
        raise BookingError("A name is required to join the waitlist.", "missing_fields")
    try:
        party = int(body.get("party_size") or body.get("party") or 2)
    except (TypeError, ValueError):
        raise BookingError("Party size must be a number.", "party")
    if not 1 <= party <= canon.int_setting(s, "max_party", 20):
        raise BookingError("Party size must be between 1 and %d."
                           % canon.int_setting(s, "max_party", 20), "party")
    desired = None
    if body.get("date") and body.get("time"):
        desired = rtime.combine(datetime.fromisoformat(str(body["date"])).date(),
                                str(body["time"]))
    elif body.get("at"):
        desired = rtime.parse_local(str(body["at"]))
    if desired is not None and desired < rtime.now():
        raise BookingError("That time has already passed. Please choose a later time.",
                           "past")

    free = sum(1 for row in av.live_state(s)["tables"] if row["state"] == "AVAILABLE")
    quoted = 10 if free >= 3 else 25 if free >= 1 else 45
    entry = WaitlistEntry(
        name=name[:160], party_size=party, phone=str(body.get("phone") or "")[:80],
        email=str(body.get("email") or "")[:160],
        note=str(body.get("note") or body.get("special_request") or "")[:1000],
        quoted_minutes=quoted, status="waiting", added_at=rtime.now(),
        desired_at=desired, area_pref=str(body.get("area") or body.get("preference") or "")[:120],
        source=source, language=notify._lang(body.get("language") or "en"))
    s.add(entry)
    s.flush()
    events.record(s, "waitlist_added", "Waitlist entry added",
                  detail="%s · %d %s%s" % (name, party, "guest" if party == 1 else "guests",
                                           (" · " + desired.strftime("%d %b %H:%M")) if desired else ""),
                  waitlist_id=entry.id, actor=actor, source=source, severity="note")
    s.add(Notification(level="note", title="Waitlist · %s" % name,
                       body="%d guests · quoted %d minutes" % (party, quoted),
                       audience="manager"))
    s.commit()
    return {"ok": True, "id": entry.id, "quoted_minutes": quoted,
            "position": len(s.exec(select(WaitlistEntry).where(
                WaitlistEntry.status == "waiting")).all())}


def waitlist_status(s: Session, entry: WaitlistEntry, status: str, *,
                    actor: str = "SUFRA") -> dict:
    status = (status or "").strip().lower()
    if status not in {"waiting", "called", "seated", "left"}:
        raise BookingError("Choose a valid waitlist status.", "bad_status")
    entry.status = status
    s.add(entry)
    events.record(s, "waitlist_updated", "Waitlist entry closed" if status in ("seated", "left")
                  else "Waitlist entry added",
                  detail="%s · %s" % (entry.name, status), waitlist_id=entry.id, actor=actor)
    s.commit()
    return {"ok": True, "status": status}


def convert_waitlist(s: Session, entry: WaitlistEntry, body: dict, *,
                     actor: str = "SUFRA") -> dict:
    payload = {
        "name": entry.name, "first_name": entry.name.split(" ")[0],
        "last_name": " ".join(entry.name.split(" ")[1:]),
        "email": entry.email, "phone": entry.phone,
        "party_size": entry.party_size, "language": entry.language or "en",
        "special_request": entry.note, "preference": entry.area_pref,
        "table_id": body.get("table_id") or body.get("table_number"),
    }
    when = body.get("at") or (entry.desired_at.isoformat() if entry.desired_at else None)
    if when:
        payload["at"] = when
    else:
        payload["_when"] = rtime.now().replace(second=0, microsecond=0) + timedelta(minutes=5)
    result = create_reservation(s, payload, source="waitlist", actor=actor,
                                notify_guest=bool(entry.email or entry.phone))
    entry.status = "seated"
    entry.converted_reservation_id = result["reservation"]["id"]
    s.add(entry)
    events.record(s, "waitlist_converted", "Waitlist converted to reservation",
                  detail="%s · %s" % (entry.name, result["reservation"]["code"]),
                  waitlist_id=entry.id, reservation_id=entry.converted_reservation_id,
                  table_number=result["reservation"].get("table_number"),
                  actor=actor, severity="good")
    s.commit()
    return result


# ------------------------------------------------------------ presentation

def public_dict(s: Session, r: Reservation) -> dict:
    """What a guest may see about their own booking."""
    table = s.get(DiningTable, r.table_id) if r.table_id else None
    p = table_profile(s, table.id) if table else None
    return {
        "id": r.id, "code": r.code or canon.booking_code(r.id),
        "status": r.status,
        "date": r.starts_at.date().isoformat(),
        "time": r.starts_at.strftime("%H:%M"),
        "at": r.starts_at.isoformat(timespec="minutes"),
        "end_time": (r.starts_at + timedelta(minutes=av.reservation_duration(s, r))).strftime("%H:%M"),
        "duration": av.reservation_duration(s, r),
        "party_size": r.party_size,
        "table_number": table.number if table else None,
        "table_id": canon.scene_id_for(table.number) if table else None,
        "table_label": str(table.number) if table else None,
        "zone": (p.area if p else (table.zone if table else "")),
        "zone_name": (p.area_name if p else (table.zone if table else "")),
        "guest": {"first_name": r.first_name, "last_name": r.last_name,
                  "email": r.email, "phone": r.phone},
        "occasion": r.occasion, "allergies": r.allergies, "dietary": r.dietary,
        "accessibility": r.accessibility, "high_chairs": r.high_chairs,
        "special_request": r.special_request, "preference": r.preference,
        "language": r.language or "en",
        "guest_confirmation_status": r.guest_confirmation_status,
        "created_at": (r.created_at or r.starts_at).isoformat(timespec="seconds"),
    }


def manager_dict(s: Session, r: Reservation) -> dict:
    """Everything the floor needs, including how late somebody now is."""
    out = public_dict(s, r)
    now = rtime.now()
    guest = s.get(Guest, r.guest_id) if r.guest_id else None
    minutes_late = 0
    if (r.status or "") in ("confirmed", "late") and now > r.starts_at:
        minutes_late = int((now - r.starts_at).total_seconds() // 60)
    out.update({
        "source": r.source, "note": r.note, "deposit": r.deposit,
        "vip": bool(guest and guest.vip), "visits": guest.visits if guest else 0,
        "guest_name": (" ".join(x for x in [r.first_name, r.last_name] if x)).strip()
                      or (guest.name if guest else "Guest"),
        "phone": r.phone or "", "email": r.email or "",
        "minutes_late": minutes_late,
        "staff_decision": r.staff_decision or "accepted",
        "needs_decision": (r.staff_decision or "") == "pending",
        "decided_by": r.decided_by, "decline_reason": r.decline_reason,
        "source_label": {"sufra_360": "SUFRA 360", "website": "the website",
                         "waitlist": "the waitlist"}.get(r.source, r.source),
        "reminder_sent_at": r.reminder_sent_at.isoformat(timespec="minutes") if r.reminder_sent_at else None,
        "guest_confirmed_at": r.guest_confirmed_at.isoformat(timespec="minutes") if r.guest_confirmed_at else None,
        "seated_at": r.seated_at.isoformat(timespec="minutes") if r.seated_at else None,
        "completed_at": r.completed_at.isoformat(timespec="minutes") if r.completed_at else None,
        "updated_at": r.updated_at.isoformat(timespec="minutes") if r.updated_at else None,
    })
    return out


# ------------------------------------------------------------- calendar

def ics(s: Session, r: Reservation) -> str:
    """A standard calendar event in the restaurant's own timezone."""
    cfg = canon.settings(s)
    table = s.get(DiningTable, r.table_id) if r.table_id else None
    p = table_profile(s, table.id) if table else None
    start = rtime.to_utc(r.starts_at).strftime("%Y%m%dT%H%M%SZ")
    end = rtime.to_utc(r.starts_at + timedelta(
        minutes=av.reservation_duration(s, r))).strftime("%Y%m%dT%H%M%SZ")
    stamp = rtime.to_utc(rtime.now()).strftime("%Y%m%dT%H%M%SZ")
    desc = " \\n".join(x for x in [
        "Reservation %s" % (r.code or canon.booking_code(r.id)),
        "%d %s" % (r.party_size, "guest" if r.party_size == 1 else "guests"),
        ("Table %d · %s" % (table.number, (p.area_name if p else table.zone))) if table else "",
        ("Occasion: %s" % r.occasion) if r.occasion else "",
        ("Notes: %s" % r.special_request) if r.special_request else "",
        "Telephone %s" % cfg["phone"],
    ] if x)
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SUFRA//Reservations//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
        "UID:%s@sufra" % (r.code or canon.booking_code(r.id)),
        "DTSTAMP:%s" % stamp, "DTSTART:%s" % start, "DTEND:%s" % end,
        "SUMMARY:%s — %s" % (cfg["restaurant_name"], r.code or canon.booking_code(r.id)),
        "LOCATION:%s" % cfg["address"].replace(",", "\\,"),
        "DESCRIPTION:%s" % desc.replace(",", "\\,"),
        "END:VEVENT", "END:VCALENDAR", ""])


def google_calendar_link(s: Session, r: Reservation) -> str:
    import urllib.parse
    cfg = canon.settings(s)
    table = s.get(DiningTable, r.table_id) if r.table_id else None
    start = rtime.to_utc(r.starts_at).strftime("%Y%m%dT%H%M%SZ")
    end = rtime.to_utc(r.starts_at + timedelta(
        minutes=av.reservation_duration(s, r))).strftime("%Y%m%dT%H%M%SZ")
    q = urllib.parse.urlencode({
        "action": "TEMPLATE",
        "text": "%s — %s" % (cfg["restaurant_name"], r.code or canon.booking_code(r.id)),
        "dates": "%s/%s" % (start, end),
        "location": cfg["address"],
        "details": "%d guests%s · %s" % (
            r.party_size, (" · Table %d" % table.number) if table else "",
            r.code or canon.booking_code(r.id)),
        "ctz": rtime.TZ_NAME,
    })
    return "https://calendar.google.com/calendar/render?" + q
