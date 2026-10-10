"""
Admin API — everything the back-of-house app reads and writes.

Grouped by the screen that uses it, because that is how it gets debugged.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .. import availability as av, bookings, canon, intelligence as ai, rtime
from .. import events as event_bus   # `events` is already a route name on this router
from ..database import engine
from ..live import hub
from ..ops_utils import ARCHIVED_ZONE, archived_menu_ids, menu_sections, unavailable_menu_ids
from ..permissions import admin_staff, require_permission
from ..models import (
    AnalyticsEvent, DayStat, DiningTable, Feedback, Guest, Ingredient,
    ItemState, Location, MenuItem, Notification, Order, OrderItem, Payment,
    PriceHistory, PurchaseLine, PurchaseOrder, RecipeLine, Reservation, Role,
    Shift, Staff, Supplier, TableStatus, Task, WaitlistEntry, WasteLog,
)

from . import sufra_upgrade

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_staff)])


def db() -> Session:
    return Session(engine, expire_on_commit=False)


def money(x: float) -> float:
    return round(float(x or 0), 2)


# ==================================================================== reservations

@router.get("/reservations")
def reservations(day: str = "", days: int = 1,
                 staff: Staff = Depends(require_permission("can_view_reservations"))):
    """Calendar and timeline both read this. `day` is YYYY-MM-DD."""
    with db() as s:
        anchor = date.fromisoformat(day) if day else date.today()
        start = datetime.combine(anchor, datetime.min.time())
        end = start + timedelta(days=days)

        guests = {g.id: g for g in s.exec(select(Guest)).all()}
        tables = {t.id: t for t in s.exec(select(DiningTable)).all() if t.zone != ARCHIVED_ZONE}
        rows = []
        for r in s.exec(select(Reservation).where(
                Reservation.starts_at >= start,
                Reservation.starts_at < end).order_by(Reservation.starts_at)).all():
            g = guests.get(r.guest_id)
            row = bookings.manager_dict(s, r)
            row.update({
                "at": r.starts_at.isoformat(),
                "time": r.starts_at.strftime("%H:%M"),
                "hour": r.starts_at.hour + r.starts_at.minute / 60,
                "party": r.party_size,
                "deposit": r.deposit,
                "table": tables[r.table_id].number if r.table_id in tables else None,
                "guest": row["guest_name"] or (g.name if g else "Walk-in"),
                "guest_id": r.guest_id,
                "vip": bool(g and g.vip), "visits": g.visits if g else 0,
                "pref": r.preference or (g.seating_pref if g else ""),
                "risk": ai.no_show_risk(s, r),
                "ends": sufra_upgrade.reservation_end(r).strftime("%H:%M"),
                "left_at": r.left_at.isoformat() if getattr(r, "left_at", None) else None,
            })
            rows.append(row)

        # Cover count per half hour drives the timeline density bar.
        density: dict[str, int] = defaultdict(int)
        for r in rows:
            if r["status"] in ("cancelled", "no_show"):
                continue
            slot = r["time"][:3] + ("00" if int(r["time"][3:]) < 30 else "30")
            density[slot] += r["party"]

        waitlist = [{
            "id": w.id, "name": w.name, "party": w.party_size, "phone": w.phone,
            "email": getattr(w, "email", "") or "",
            "waiting": round((rtime.now() - w.added_at).total_seconds() / 60),
            "quoted": w.quoted_minutes, "status": w.status, "note": w.note,
            "source": getattr(w, "source", "walk-in") or "walk-in",
            "area": getattr(w, "area_pref", "") or "",
            "desired_at": (w.desired_at.isoformat(timespec="minutes")
                           if getattr(w, "desired_at", None) else None),
            "desired": (w.desired_at.strftime("%d %b %H:%M")
                        if getattr(w, "desired_at", None) else ""),
        } for w in s.exec(select(WaitlistEntry).where(
            WaitlistEntry.status == "waiting").order_by(WaitlistEntry.added_at)).all()]

        booked = sum(r["party"] for r in rows if r["status"] not in ("cancelled", "no_show"))
        # The book is what the floor still has to do. A party that has been
        # seated is on the floor, not on the book, and leaving it in the list
        # means a manager re-reads the same four bookings all night looking
        # for the one that has not arrived. Everything settled moves to
        # `closed`, which the screen keeps behind a disclosure.
        OPEN = {"confirmed", "late"}
        open_rows = [r for r in rows if (r["status"] or "") in OPEN]
        closed_rows = [r for r in rows if (r["status"] or "") not in OPEN]
        return {
            "day": anchor.isoformat(), "reservations": open_rows,
            "closed": closed_rows, "all_reservations": rows,
            "awaiting_decision": [r for r in open_rows if r.get("needs_decision")],
            "density": [{"slot": k, "covers": v} for k, v in sorted(density.items())],
            "waitlist": waitlist,
            "summary": {
                "bookings": len(rows), "covers": booked,
                "cancelled": sum(1 for r in rows if r["status"] == "cancelled"),
                "vips": sum(1 for r in rows if r["vip"]),
                "at_risk": sum(1 for r in rows if r["risk"] > 0.3),
                "awaiting_decision": sum(1 for r in rows if r.get("needs_decision")
                                         and (r["status"] or "") in ("confirmed", "late")),
                "seated": sum(1 for r in rows if r["status"] == "seated"),
                "capacity": sum(t.seats for t in tables.values()),
                "walkin_free": sum(1 for x in sufra_upgrade.walkin_availability(s) if x["walkin_free"]),
                "reserved_tables": sum(1 for x in sufra_upgrade.walkin_availability(s) if x["reservation"]),
            },
            "tables": sufra_upgrade.walkin_availability(s),
        }


def _actor(staff: Staff) -> str:
    return staff.name or "SUFRA"


def _err(exc: bookings.BookingError):
    return JSONResponse({"error": exc.message, "code": exc.code}, exc.status)


@router.post("/reservations")
async def create_reservation(body: dict = Body(...),
                             staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """Take a booking. Same engine, same rules, same rows as SUFRA 360."""
    with db() as s:
        payload = dict(body)
        payload.setdefault("party_size", body.get("party"))
        payload.setdefault("special_request", body.get("note"))
        payload.setdefault("preference", body.get("pref") or body.get("seating_pref"))
        source = (body.get("source") or "phone").strip().lower()
        if source not in bookings.SOURCES:
            return JSONResponse({"error": "Choose a valid booking source."}, 400)
        try:
            result = bookings.create_reservation(
                s, payload, source=source, actor=_actor(staff),
                notify_guest=bool(payload.get("email") or payload.get("phone")))
        except bookings.BookingError as exc:
            return _err(exc)
        except ValueError:
            return JSONResponse({"error": "Give a valid date and time for the booking."}, 400)
        r = s.get(Reservation, result["reservation"]["id"])
        if body.get("deposit"):
            try:
                r.deposit = round(float(body["deposit"]), 2)
                s.add(r)
                s.commit()
            except (TypeError, ValueError):
                pass
        res = result["reservation"]
    return {"ok": True, "id": res["id"], "table": res["table_number"],
            "duration": res["duration"], "code": res["code"],
            "delivery": result.get("delivery"),
            "message": "%s booked for %d · Table %s · %s" % (
                res["guest"]["first_name"], res["party_size"], res["table_number"],
                res["time"])}


@router.post("/reservations/{res_id}/status")
async def reservation_status(res_id: int, body: dict = Body(...),
                             staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """confirmed | late | seated | completed | cancelled | no_show."""
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r:
            return JSONResponse({"error": "That booking no longer exists."}, 404)
        try:
            return bookings.set_status(s, r, str(body.get("status") or ""),
                                       actor=_actor(staff))
        except bookings.BookingError as exc:
            return _err(exc)


@router.post("/reservations/{res_id}")
async def edit_reservation(res_id: int, body: dict = Body(...),
                           staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """Manager edit. Availability, capacity and conflict rules run again."""
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r:
            return JSONResponse({"error": "That booking no longer exists."}, 404)
        try:
            return bookings.update(s, r, body, actor=_actor(staff))
        except bookings.BookingError as exc:
            return _err(exc)
        except ValueError:
            return JSONResponse({"error": "Give a valid date and time."}, 400)


@router.post("/reservations/{res_id}/table")
async def move_reservation(res_id: int, body: dict = Body(...),
                           staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """Relocate a booking. Refused if the destination is not free for the
    SAME booking window, unless the manager explicitly forces it."""
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r:
            return JSONResponse({"error": "That booking no longer exists."}, 404)
        try:
            return bookings.relocate(s, r, body.get("table_id") or body.get("table_number"),
                                     actor=_actor(staff), force=bool(body.get("force")))
        except bookings.BookingError as exc:
            return _err(exc)


@router.get("/reservations/{res_id}/options")
def reservation_options(res_id: int,
                        staff: Staff = Depends(require_permission("can_view_reservations"))):
    """Which tables this booking could legally move to, for the picker."""
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r:
            return JSONResponse({"error": "That booking no longer exists."}, 404)
        grid = av.availability(s, r.starts_at, r.party_size,
                               av.reservation_duration(s, r),
                               ignore_reservation_id=r.id)
        return {"reservation": bookings.manager_dict(s, r),
                "current_table": (s.get(DiningTable, r.table_id).number
                                  if r.table_id else None),
                "choices": [x for x in grid["tables"] if x["bookable"]],
                "blocked": [x for x in grid["tables"] if not x["bookable"]]}


@router.post("/reservations/{res_id}/decision")
async def decide_reservation(res_id: int, body: dict = Body(...),
                             staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """Accept or decline a booking the restaurant did not take itself.

    Declining releases the table AND tells the guest — a booking somebody
    believes they hold must never just disappear.
    """
    decision = str(body.get("decision") or "").strip().lower()
    if decision not in {"accept", "decline"}:
        return JSONResponse({"error": "Choose accept or decline."}, 400)
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r:
            return JSONResponse({"error": "That booking no longer exists."}, 404)
        try:
            return bookings.decide(s, r, decision == "accept", actor=_actor(staff),
                                   reason=str(body.get("reason") or ""))
        except bookings.BookingError as exc:
            return _err(exc)


@router.post("/reservations/{res_id}/keep-table")
async def keep_table(res_id: int,
                     staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """"Keep this table assignment" — records the manager's decision."""
    with db() as s:
        r = s.get(Reservation, res_id)
        if not r or not r.table_id:
            return JSONResponse({"error": "That booking has no table to keep."}, 404)
        table = s.get(DiningTable, r.table_id)
        r.updated_at = rtime.now()
        s.add(r)
        event_bus.record(s, "reservation_updated", "Reservation updated",
                      detail="%s · table assignment kept by %s" % (r.code, _actor(staff)),
                      table_id=table.id, table_number=table.number,
                      reservation_id=r.id, actor=_actor(staff))
        s.commit()
        return {"ok": True, "table": table.number,
                "message": "Table %d kept for %s." % (table.number, r.code)}


@router.post("/waitlist")
async def add_waitlist(body: dict = Body(...),
                       staff: Staff = Depends(require_permission("can_modify_reservations"))):
    with db() as s:
        try:
            result = bookings.join_waitlist(s, body, source=(body.get("source") or "walk-in"),
                                            actor=_actor(staff))
        except bookings.BookingError as exc:
            return _err(exc)
        return {"ok": True, "quoted": result["quoted_minutes"], "id": result["id"]}


@router.post("/waitlist/{entry_id}/status")
async def waitlist_status(entry_id: int, body: dict = Body(...),
                          staff: Staff = Depends(require_permission("can_modify_reservations"))):
    with db() as s:
        w = s.get(WaitlistEntry, entry_id)
        if not w:
            return JSONResponse({"error": "Not on the list."}, 404)
        try:
            return bookings.waitlist_status(s, w, str(body.get("status") or ""),
                                            actor=_actor(staff))
        except bookings.BookingError as exc:
            return _err(exc)


@router.post("/waitlist/{entry_id}/convert")
async def waitlist_convert(entry_id: int, body: dict = Body(default={}),
                           staff: Staff = Depends(require_permission("can_modify_reservations"))):
    """Turn a waiting party into a real booking, with every rule applied."""
    with db() as s:
        w = s.get(WaitlistEntry, entry_id)
        if not w:
            return JSONResponse({"error": "Not on the list."}, 404)
        try:
            return bookings.convert_waitlist(s, w, body, actor=_actor(staff))
        except bookings.BookingError as exc:
            return _err(exc)


# ==================================================================== live operations

@router.get("/activity")
def live_events(limit: int = 40, after: int = 0,
                staff: Staff = Depends(require_permission("can_view_reservations"))):
    """The real activity stream. No generator, no filler: if nothing has
    happened, this is empty and the screen says the restaurant is quiet."""
    with db() as s:
        rows = event_bus.recent(s, limit=limit, after_id=after)
        return {"events": rows, "count": len(rows)}


# ==================================================================== orders

@router.get("/orders")
def orders(scope: str = "open",
           staff: Staff = Depends(require_permission("can_view_orders"))):
    with db() as s:
        menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
        tables = {t.id: t for t in s.exec(select(DiningTable)).all() if t.zone != ARCHIVED_ZONE}
        staff = {w.id: w for w in s.exec(select(Staff)).all()}
        start = datetime.combine(date.today(), datetime.min.time())

        q = select(Order).where(Order.opened_at >= start)
        if scope == "open":
            q = q.where(Order.paid == False)  # noqa: E712
        rows = []
        for o in s.exec(q.order_by(Order.opened_at.desc())).all():
            items = [i for i in s.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all() if not i.void_reason]
            total = sum(menu[i.menu_item_id].price * i.qty for i in items if i.menu_item_id in menu)
            paid = sum(p.amount for p in s.exec(
                select(Payment).where(Payment.order_id == o.id)).all())
            rows.append({
                "id": o.id,
                "table": tables[o.table_id].number if o.table_id in tables else "—",
                "waiter": staff[o.waiter_id].name if o.waiter_id in staff else "—",
                "opened": o.opened_at.strftime("%H:%M"),
                "minutes": round((rtime.now() - o.opened_at).total_seconds() / 60),
                "paid": o.paid, "total": money(total),
                "settled": money(paid), "outstanding": money(total - paid),
                "items": [{
                    "id": i.id, "name": menu[i.menu_item_id].name if i.menu_item_id in menu else "?",
                    "qty": i.qty, "state": i.state.value, "note": i.note,
                    "price": menu[i.menu_item_id].price if i.menu_item_id in menu else 0,
                    "station": i.station.value,
                } for i in items],
            })
        return {"orders": rows,
                "totals": {"open": sum(1 for r in rows if not r["paid"]),
                           "value": money(sum(r["total"] for r in rows)),
                           "outstanding": money(sum(r["outstanding"] for r in rows))}}


# ==================================================================== menu admin

@router.get("/menu")
def menu_admin(staff: Staff = Depends(require_permission("can_manage_menu"))):
    with db() as s:
        engineering = {m["id"]: m for m in ai.menu_engineering(s)}
        rows = []
        blocked, block_reasons = unavailable_menu_ids(s)
        archived = archived_menu_ids(s)
        for m in s.exec(select(MenuItem).order_by(MenuItem.course, MenuItem.name)).all():
            if m.id in archived:
                continue
            e = engineering.get(m.id, {})
            rows.append({
                "id": m.id, "name": m.name, "course": m.course,
                "station": m.station.value, "price": m.price, "cost": m.food_cost,
                "margin": money(m.price - m.food_cost),
                "margin_pct": round(100 * (m.price - m.food_cost) / m.price, 1) if m.price else 0,
                "minutes": m.base_minutes, "tags": [t for t in m.tags.split(",") if t],
                "kcal": m.kcal, "protein": m.protein_g, "blurb": m.blurb,
                "available": bool(m.available and m.id not in blocked), "base_available": m.available,
                "operational_reason": block_reasons.get(m.id, ""), "sold": m.sold_30d, "hue": m.hue,
                "spice": m.spice, "signature": m.signature,
                "class": e.get("class", ""), "advice": e.get("advice", ""),
                "revenue_30d": e.get("revenue_30d", 0),
            })
        sections = menu_sections(s)
        courses = sections or list(dict.fromkeys([r["course"] for r in rows]))
        return {"items": rows, "courses": courses}


@router.post("/menu/{item_id}")
async def update_menu_item(item_id: int, body: dict = Body(...), staff: Staff = Depends(require_permission("can_manage_menu"))):
    with db() as s:
        m = s.get(MenuItem, item_id)
        if not m:
            return JSONResponse({"error": "That dish is not on the menu."}, 404)
        for field in ("name", "blurb", "tags"):
            if field in body:
                value = str(body[field] or "").strip()
                if field == "name" and not value:
                    return JSONResponse({"error": "Dish name cannot be empty."}, 400)
                if len(value) > (160 if field == "name" else 2000):
                    return JSONResponse({"error": f"{field.replace('_', ' ').title()} is too long."}, 400)
                setattr(m, field, value)
        for field in ("price", "food_cost"):
            if field in body:
                try:
                    value = float(body[field])
                except (TypeError, ValueError):
                    return JSONResponse({"error": f"{field.replace('_', ' ').title()} must be a number."}, 400)
                if not np.isfinite(value) or value < 0:
                    return JSONResponse({"error": f"{field.replace('_', ' ').title()} must be non-negative."}, 400)
                setattr(m, field, value)
        for field in ("base_minutes", "kcal", "protein_g"):
            if field in body:
                try:
                    value = int(body[field])
                except (TypeError, ValueError):
                    return JSONResponse({"error": f"{field.replace('_', ' ').title()} must be a number."}, 400)
                if value < 0:
                    return JSONResponse({"error": f"{field.replace('_', ' ').title()} must be non-negative."}, 400)
                setattr(m, field, value)
        availability_changed = False
        if "available" in body:
            was = m.available
            m.available = bool(body["available"])
            availability_changed = was != m.available
        s.add(m)
        # SUFRA 360 reads the same rows, so this reaches the guest menu
        # immediately — there is no second copy of the menu to update.
        event_bus.record(s, "menu_availability" if availability_changed else "menu_updated",
                      "Menu availability changed" if availability_changed else "Menu item changed",
                      detail="%s%s" % (m.name, "" if not availability_changed else
                                       (" · available" if m.available else " · sold out")),
                      actor=_actor(staff),
                      severity="warning" if availability_changed and not m.available else "note")
        s.commit()
    await hub.send("state", {"changed": ["menu"]})
    return {"ok": True}


# ==================================================================== guests CRM

@router.get("/guests")
def guests(q: str = "", vip_only: bool = False,
           staff: Staff = Depends(require_permission("can_view_guest_profiles"))):
    with db() as s:
        rows = []
        res_by_guest: dict[int, list] = defaultdict(list)
        for r in s.exec(select(Reservation)).all():
            if r.guest_id:
                res_by_guest[r.guest_id].append(r)

        for g in s.exec(select(Guest)).all():
            if q and q.lower() not in g.name.lower():
                continue
            if vip_only and not g.vip:
                continue
            bookings = sorted(res_by_guest.get(g.id, []), key=lambda r: r.starts_at)
            rows.append({
                "id": g.id, "name": g.name, "visits": g.visits, "vip": g.vip,
                "allergies": g.allergies, "likes": g.likes,
                "pref": g.seating_pref, "avg_spend": g.avg_spend, "note": g.note,
                "lifetime": money(g.avg_spend * g.visits),
                "next": bookings[-1].starts_at.strftime("%-d %b %H:%M") if bookings else "",
                "bookings": len(bookings),
            })
        rows.sort(key=lambda r: (-r["lifetime"]))
        return {"guests": rows,
                "totals": {"count": len(rows),
                           "vips": sum(1 for r in rows if r["vip"]),
                           "lifetime": money(sum(r["lifetime"] for r in rows)),
                           "with_allergies": sum(1 for r in rows if r["allergies"])}}


@router.post("/guests/{guest_id}")
async def update_guest(guest_id: int, body: dict = Body(...),
                       staff: Staff = Depends(require_permission("can_view_guest_profiles"))):
    with db() as s:
        g = s.get(Guest, guest_id)
        if not g:
            return JSONResponse({"error": "No such guest."}, 404)
        for f in ("allergies", "likes", "seating_pref", "note"):
            if f in body:
                setattr(g, f, body[f])
        if "vip" in body:
            g.vip = bool(body["vip"])
        s.add(g)
        s.commit()
    return {"ok": True}


# ==================================================================== staff

@router.get("/staff")
def staff(week_offset: int = 0,
          actor: Staff = Depends(require_permission("can_view_staff"))):
    with db() as s:
        monday = date.today() - timedelta(days=date.today().weekday()) + timedelta(weeks=week_offset)
        week = [monday + timedelta(days=i) for i in range(7)]

        people = s.exec(select(Staff)).all()
        shifts = s.exec(select(Shift).where(Shift.day >= week[0],
                                            Shift.day <= week[-1])).all()
        by_person: dict[int, list] = defaultdict(list)
        for sh in shifts:
            by_person[sh.staff_id].append(sh)

        rows = []
        for p in people:
            mine = sorted(by_person.get(p.id, []), key=lambda x: x.day)
            hours = sum(x.end_hour - x.start_hour for x in mine if x.status in
                        ("scheduled", "confirmed"))
            rows.append({
                "id": p.id, "name": p.name, "role": p.role.value, "avatar": p.avatar,
                "on_shift": p.on_shift, "rating": p.rating, "rate": p.hourly_rate,
                "covers": p.covers_served,
                "avg_service": round(p.avg_service_seconds / 60, 1),
                "since": p.started_on.isoformat() if p.started_on else "",
                "hours": round(hours, 1), "cost": money(hours * p.hourly_rate),
                "shifts": [{
                    "id": x.id, "day": x.day.isoformat(), "dow": x.day.weekday(),
                    "start": x.start_hour, "end": x.end_hour, "status": x.status,
                    "label": f"{int(x.start_hour):02d}:{int(x.start_hour % 1 * 60):02d}"
                             f"–{int(x.end_hour):02d}:{int(x.end_hour % 1 * 60):02d}",
                } for x in mine],
            })
        rows.sort(key=lambda r: (r["role"], r["name"]))

        # What the demand model says each day needs, next to what is rostered.
        need = []
        for d in week:
            fc = ai.forecast_day(s, d)
            covers = fc["covers"]
            rostered = defaultdict(float)
            for sh in shifts:
                if sh.day == d and sh.status in ("scheduled", "confirmed"):
                    rostered[sh.role.value] += 1
            need.append({
                "day": d.isoformat(), "dow": d.strftime("%a"), "covers": covers,
                "waiters_needed": max(4, round(covers / 26)),
                "waiters_rostered": int(rostered.get("waiter", 0)),
                "chefs_needed": max(3, round(covers / 34)),
                "chefs_rostered": int(rostered.get("chef", 0)),
                "bar_needed": max(1, round(covers / 90)),
                "bar_rostered": int(rostered.get("bartender", 0)),
            })

        return {"week": [d.isoformat() for d in week], "staff": rows, "demand": need,
                "wage_bill": money(sum(r["cost"] for r in rows))}


@router.post("/shifts")
async def upsert_shift(body: dict = Body(...),
                       actor: Staff = Depends(require_permission("can_edit_staff"))):
    with db() as s:
        if body.get("id"):
            sh = s.get(Shift, int(body["id"]))
            if not sh:
                return JSONResponse({"error": "That shift is gone."}, 404)
        else:
            person = s.get(Staff, int(body["staff_id"]))
            if not person:
                return JSONResponse({"error": "No such person."}, 404)
            sh = Shift(staff_id=person.id, day=date.fromisoformat(body["day"]),
                       role=person.role)
        for f in ("start_hour", "end_hour"):
            if f in body:
                setattr(sh, f, float(body[f]))
        if "status" in body:
            sh.status = body["status"]
        s.add(sh)
        s.commit()
    return {"ok": True}


@router.post("/shifts/auto")
async def auto_roster(body: dict = Body(...),
                      actor: Staff = Depends(require_permission("can_edit_staff"))):
    """Fill the gaps the demand model reports, using who is actually available."""
    with db() as s:
        target = date.fromisoformat(body["day"])
        fc = ai.forecast_day(s, target)
        covers = fc["covers"]
        wants = {Role.WAITER: max(4, round(covers / 26)),
                 Role.KITCHEN: max(3, round(covers / 34)),
                 Role.BARTENDER: max(1, round(covers / 90))}

        existing = s.exec(select(Shift).where(Shift.day == target)).all()
        have = defaultdict(int)
        for sh in existing:
            if sh.status in ("scheduled", "confirmed"):
                have[sh.role] += 1

        added = 0
        for role, want in wants.items():
            gap = want - have[role]
            if gap <= 0:
                continue
            busy = {sh.staff_id for sh in existing}
            free = [p for p in s.exec(select(Staff).where(Staff.role == role)).all()
                    if p.id not in busy]
            for person in free[:gap]:
                s.add(Shift(staff_id=person.id, day=target, role=role,
                            start_hour=16.5, end_hour=23.5, status="scheduled",
                            note="Added by SUFRA from the demand forecast"))
                added += 1
        s.commit()
    if not added:
        return {"ok": True, "added": 0, "covers": covers,
                "message": f"Rota already covers {covers} forecast covers. Nothing to add."}
    return {"ok": True, "added": added, "covers": covers,
            "message": f"Added {added} shifts to cover {covers} forecast covers."}


# ==================================================================== analytics

@router.get("/analytics")
def analytics(days: int = 30,
              staff: Staff = Depends(require_permission("can_view_analytics"))):
    with db() as s:
        days = max(1, min(int(days), 366))
        start_day = date.today() - timedelta(days=days - 1)
        start = datetime.combine(start_day, datetime.min.time())
        paid_orders = s.exec(select(Order).where(
            Order.paid == True, Order.opened_at >= start  # noqa: E712
        )).all()
        order_ids = [o.id for o in paid_orders]
        items = (s.exec(select(OrderItem).where(
            OrderItem.order_id.in_(order_ids))).all() if order_ids else [])
        menu_by_id = {m.id: m for m in s.exec(select(MenuItem)).all()}
        paid_order_ids = {o.id for o in paid_orders}
        payments = (s.exec(select(Payment).where(
            Payment.order_id.in_(order_ids))).all() if order_ids else [])
        revenue_by_day: dict[date, float] = defaultdict(float)
        for payment in payments:
            if payment.order_id in paid_order_ids and payment.amount > 0:
                order = next((o for o in paid_orders if o.id == payment.order_id), None)
                if order:
                    revenue_by_day[order.opened_at.date()] += payment.amount
        covers_by_day: dict[date, int] = defaultdict(int)
        for item in items:
            if item.void_reason:
                continue
            menu_item = menu_by_id.get(item.menu_item_id)
            order = next((o for o in paid_orders if o.id == item.order_id), None)
            if menu_item and order and menu_item.course == "Main":
                covers_by_day[order.opened_at.date()] += item.qty
        operational_days = [
            d for d in (start_day + timedelta(days=i) for i in range(days))
            if d in revenue_by_day or d in covers_by_day
        ]
        rows = [{
            "day": d.isoformat(), "label": d.strftime("%-d %b"),
            "revenue": money(revenue_by_day.get(d, 0)),
            "covers": covers_by_day.get(d, 0),
            "spend": round(revenue_by_day.get(d, 0) / max(1, covers_by_day.get(d, 0)), 2),
        } for d in operational_days]
        menu = ai.menu_engineering(s)
        fb = s.exec(select(Feedback)).all()

        by_weekday = defaultdict(list)
        for r in rows:
            by_weekday[date.fromisoformat(r["day"]).weekday()].append(r["revenue"])

        waste = s.exec(select(WasteLog).where(
            WasteLog.logged_on >= date.today() - timedelta(days=days))).all()
        ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
        waste_reason = defaultdict(float)
        waste_item = defaultdict(float)
        for w in waste:
            ing = ings.get(w.ingredient_id)
            value = w.qty * (ing.cost_per_unit if ing else 0)
            waste_reason[w.reason] += value
            if ing:
                waste_item[ing.name] += value

        guests = s.exec(select(Guest)).all()
        repeat = sum(1 for g in guests if g.visits > 1)

        return {
            "trend": rows,
            "weekday": [{"dow": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][k],
                         "revenue": money(np.mean(v))}
                        for k, v in sorted(by_weekday.items())],
            "menu": menu[:14],
            "menu_classes": {k: sum(1 for m in menu if m["class"] == k)
                             for k in ("star", "workhorse", "hidden gem", "weak")},
            "waste": {"by_reason": [{"reason": k, "value": money(v)}
                                    for k, v in sorted(waste_reason.items(), key=lambda x: -x[1])],
                      "by_item": [{"name": k, "value": money(v)}
                                  for k, v in sorted(waste_item.items(), key=lambda x: -x[1])[:8]],
                      "total": money(sum(waste_reason.values()))},
            "retention": {"guests": len(guests), "repeat": repeat,
                          "rate": round(100 * repeat / max(1, len(guests)), 1),
                          "avg_visits": round(float(np.mean([g.visits for g in guests])), 1)},
            "satisfaction": {k: round(20 * float(np.mean([getattr(f, k) for f in fb])), 1)
                             for k in ("food", "service", "atmosphere", "speed")} if fb else {},
            "data_source": "paid orders and payment ledger only; seeded DayStat forecast history excluded",
            "operational_days": len(operational_days),
        }


@router.post("/waste")
async def log_waste(body: dict = Body(...),
                    staff: Staff = Depends(require_permission("can_edit_inventory"))):
    with db() as s:
        try:
            ingredient_id = int(body["ingredient_id"])
            qty = float(body.get("qty", 1))
        except (KeyError, TypeError, ValueError):
            return JSONResponse({"error": "Choose an ingredient and enter a valid quantity."}, 400)
        if qty <= 0 or not np.isfinite(qty):
            return JSONResponse({"error": "Waste quantity must be above zero."}, 400)
        ing = s.get(Ingredient, ingredient_id)
        if not ing:
            return JSONResponse({"error": "That ingredient no longer exists."}, 404)
        reason = str(body.get("reason") or "overproduction").strip()
        if len(reason) > 120:
            return JSONResponse({"error": "Waste reason is too long."}, 400)
        s.add(WasteLog(ingredient_id=ingredient_id, qty=qty, reason=reason))
        ing.in_stock = max(0.0, ing.in_stock - qty)
        s.add(ing)
        s.commit()
    return {"ok": True}


# ==================================================================== finance

def _anbar_finance(s: Session) -> dict:
    """Warehouse figures for the finance screen, computed by Anbar.

    Deliberately thin: valuation, waste and purchasing are calculated once,
    in the warehouse, and read here. Recomputing them with slightly
    different rules is how two screens end up disagreeing about the same
    month.
    """
    try:
        from .. import anbar
        val = anbar.valuation(s)
        month_start = date.today().replace(day=1)
        from ..anbar_models import GoodsReceipt
        receipts = s.exec(select(GoodsReceipt).where(
            GoodsReceipt.status == "confirmed",
            GoodsReceipt.delivered_on >= month_start)).all()
        return {
            "valuation": val["total"],
            "lines": val["items"],
            "by_category": val["by_category"][:8],
            "waste_today": anbar.waste_value(s, [
                w for w in anbar.waste_window(s, 1) if w.logged_on == date.today()]),
            "waste_30d": anbar.waste_value(s, anbar.waste_window(s, 30)),
            "purchases_month": money(sum(r.total_value for r in receipts)),
            "deliveries_month": len(receipts),
        }
    except Exception as exc:
        print("[finance] anbar figures unavailable:", exc)
        return {}


@router.get("/finance")
def finance(staff: Staff = Depends(require_permission("can_view_financials"))):
    with db() as s:
        start = datetime.combine(date.today(), datetime.min.time())
        pays = s.exec(select(Payment).where(
            Payment.created_at >= start, Payment.amount > 0)).all()
        payment_order_ids = {p.order_id for p in pays}
        paid_orders = (s.exec(select(Order).where(
            Order.paid == True, Order.id.in_(payment_order_ids)  # noqa: E712
        )).all() if payment_order_ids else [])
        order_ids = [o.id for o in paid_orders]
        pays = [p for p in pays if p.order_id in set(order_ids)]
        menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
        orders = paid_orders
        items = (s.exec(select(OrderItem).where(
            OrderItem.order_id.in_([o.id for o in orders]))).all() if orders else [])

        valid_items = [i for i in items if not i.void_reason and i.menu_item_id in menu]
        revenue = sum(p.amount for p in pays if p.amount > 0)
        cost = sum(menu[i.menu_item_id].food_cost * i.qty for i in valid_items)
        covers = sum(i.qty for i in valid_items if menu[i.menu_item_id].course == "Main")

        staff_today = s.exec(select(Shift).where(Shift.day == date.today())).all()
        people = {p.id: p for p in s.exec(select(Staff)).all()}
        wages = sum((sh.end_hour - sh.start_hour) * people[sh.staff_id].hourly_rate
                    for sh in staff_today if sh.staff_id in people
                    and sh.status in ("scheduled", "confirmed"))

        by_method = defaultdict(float)
        for p in pays:
            by_method[p.method] += p.amount
        tips = sum(p.tip for p in pays)

        pos = s.exec(select(PurchaseOrder).where(
            PurchaseOrder.status.in_(["sent", "draft"]))).all()

        return {
            "revenue": money(revenue), "food_cost": money(cost),
            "paid_orders": len(orders), "covers": covers,
            "gross_profit": money(revenue - cost),
            "gross_margin": round(100 * (revenue - cost) / revenue, 1) if revenue else 0,
            "wages": money(wages),
            "wage_pct": round(100 * wages / revenue, 1) if revenue else 0,
            "net": money(revenue - cost - wages),
            "tips": money(tips),
            "committed_spend": money(sum(p.total for p in pos)),
            # From SUFRA ANBAR. Read-only here: the warehouse owns these
            # numbers, finance just reports them, so there is exactly one
            # inventory valuation in the system rather than two that drift.
            "inventory": _anbar_finance(s),
            "by_method": [{"method": k, "value": money(v)}
                          for k, v in sorted(by_method.items(), key=lambda x: -x[1])],
            "payments": [{
                "id": p.id, "at": p.created_at.strftime("%H:%M"), "amount": money(p.amount),
                "tip": money(p.tip), "method": p.method, "kind": p.kind,
                "payer": p.payer, "ref": p.reference,
            } for p in sorted(pays, key=lambda p: p.created_at, reverse=True)[:40]],
        }


# ==================================================================== suppliers

@router.get("/suppliers")
def suppliers(staff: Staff = Depends(require_permission("can_view_inventory"))):
    with db() as s:
        ings = s.exec(select(Ingredient)).all()
        by_sup: dict[int, list] = defaultdict(list)
        for i in ings:
            if i.supplier_id:
                by_sup[i.supplier_id].append(i)

        # Price movement over six weeks, per supplier and per ingredient.
        cutoff = date.today() - timedelta(weeks=6)
        history = s.exec(select(PriceHistory).where(PriceHistory.on_day >= cutoff)).all()
        series: dict[int, list] = defaultdict(list)
        for h in history:
            series[h.ingredient_id].append(h)

        moves = []
        for ing in ings:
            pts = sorted(series.get(ing.id, []), key=lambda h: h.on_day)
            if len(pts) < 2 or not pts[0].price:
                continue
            change = (pts[-1].price - pts[0].price) / pts[0].price * 100
            moves.append({"ingredient": ing.name, "supplier": ing.supplier,
                          "from": round(pts[0].price, 2), "to": round(pts[-1].price, 2),
                          "change": round(change, 1), "unit": ing.unit})
        moves.sort(key=lambda m: -abs(m["change"]))

        pos = s.exec(select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())).all()
        sup_names = {x.id: x.name for x in s.exec(select(Supplier)).all()}

        rows = []
        for sup in s.exec(select(Supplier)).all():
            mine = by_sup.get(sup.id, [])
            their_pos = [p for p in pos if p.supplier_id == sup.id]
            rows.append({
                "id": sup.id, "name": sup.name, "category": sup.category,
                "contact": sup.contact, "lead": sup.lead_time_days,
                "reliability": sup.reliability, "quality": sup.quality,
                "lines": len(mine), "spend_90d": money(sum(p.total for p in their_pos)),
                "last_order": their_pos[0].created_at.strftime("%-d %b") if their_pos else "—",
                "score": round((sup.reliability * 0.5 + sup.quality * 0.5)
                               - sup.lead_time_days * 2),
            })
        rows.sort(key=lambda r: -r["score"])

        return {
            "suppliers": rows,
            "price_moves": moves[:12],
            "purchase_orders": [{
                "id": p.id, "supplier": sup_names.get(p.supplier_id, "—"),
                "created": p.created_at.strftime("%-d %b"), "status": p.status,
                "total": money(p.total), "raised_by": ("SUFRA" if p.raised_by == "NOVA" else p.raised_by),
                "deliver": p.deliver_on.strftime("%-d %b") if p.deliver_on else "—",
            } for p in pos[:20]],
        }


@router.post("/purchase-orders")
async def raise_po(body: dict = Body(...),
                   staff: Staff = Depends(require_permission("can_edit_inventory"))):
    """Turn the predicted shortfall into real orders, grouped by supplier."""
    with db() as s:
        rows = [r for r in ai.inventory_outlook(s) if r["order_qty"] > 0]
        if not rows:
            return {"ok": True, "created": 0,
                    "message": "Nothing is short. No orders raised."}

        ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
        sup_ids = {x.name: x.id for x in s.exec(select(Supplier)).all()}
        grouped: dict[int, list] = defaultdict(list)
        for r in rows:
            ing = ings.get(r["id"])
            sid = ing.supplier_id or sup_ids.get(r["supplier"])
            if sid:
                grouped[sid].append((ing, r["order_qty"]))

        created = 0
        for sid, lines in grouped.items():
            sup = s.get(Supplier, sid)
            po = PurchaseOrder(supplier_id=sid, status="sent",
                               deliver_on=date.today() + timedelta(
                                   days=sup.lead_time_days if sup else 1),
                               raised_by=body.get("by", "SUFRA"))
            s.add(po)
            s.commit()
            s.refresh(po)
            total = 0.0
            for ing, qty in lines:
                total += qty * ing.cost_per_unit
                s.add(PurchaseLine(order_id=po.id, ingredient_id=ing.id,
                                   qty=qty, unit_price=ing.cost_per_unit))
            po.total = money(total)
            s.add(po)
            created += 1
        s.add(Notification(level="good", title=f"{created} purchase orders sent",
                           body="Raised from tomorrow's forecast shortfall.",
                           audience="manager"))
        s.commit()
    await hub.send("state", {"changed": ["purchasing"]})
    return {"ok": True, "created": created,
            "message": f"{created} orders sent across {created} suppliers."}


# ==================================================================== settings

@router.get("/settings")
def settings(staff: Staff = Depends(require_permission("can_view_financials"))):
    with db() as s:
        locs = [{"id": l.id, "name": l.name, "city": l.city, "seats": l.seats,
                 "currency": l.currency, "home": l.is_home}
                for l in s.exec(select(Location)).all()]

        # Group comparison. Only the home branch has live data, so the others
        # are scaled from it — and the API says so rather than pretending.
        base = ai.forecast_day(s)
        scale = {"Waterfront": 1.0, "Old City": 0.62, "Sea Breeze": 1.34, "Ganja": 0.48}
        group = [{
            "name": l["name"], "city": l["city"],
            "revenue": money(base["revenue"] * scale.get(l["name"], 1)),
            "covers": round(base["covers"] * scale.get(l["name"], 1)),
            "spend": money(base["revenue"] / max(1, base["covers"])),
            "live": l["home"],
        } for l in locs]

        roles = [
            ("Owner", "Everything, every branch"),
            ("General manager", "One branch, all screens except billing settings"),
            ("Restaurant manager", "Floor, reservations, staff, kitchen"),
            ("Host", "Reservations, waitlist, seating"),
            ("Waiter", "Own tables, orders, requests"),
            ("Bartender", "Bar tickets, drinks orders"),
            ("Kitchen", "Kitchen display only"),
            ("Inventory manager", "Stock, suppliers, purchase orders"),
            ("Guest", "Menu, ordering, payment"),
        ]
        return {"locations": locs, "group": group,
                "roles": [{"role": r, "access": a} for r, a in roles],
                "note": "Only the home venue carries live service data in this build. "
                        "Other branches are scaled from its forecast."}


# ==================================================================== notifications

@router.get("/notifications")
def notifications(audience: str = "manager",
                  staff: Staff = Depends(require_permission("can_view_analytics"))):
    with db() as s:
        rows = s.exec(select(Notification).order_by(
            Notification.created_at.desc())).all()
        out = [{
            "id": n.id, "level": n.level, "title": n.title, "body": n.body,
            "read": n.read, "audience": n.audience,
            "ago": round((rtime.now() - n.created_at).total_seconds() / 60),
        } for n in rows if n.audience in (audience, "all")]
        return {"notifications": out[:30],
                "unread": sum(1 for n in out if not n["read"])}


@router.post("/notifications/{note_id}/read")
async def read_note(note_id: int,
                    staff: Staff = Depends(require_permission("can_view_analytics"))):
    with db() as s:
        n = s.get(Notification, note_id)
        if n:
            n.read = True
            s.add(n)
            s.commit()
    return {"ok": True}
