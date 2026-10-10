"""
Waiter and guest APIs.

Both apps touch the same orders and the same tables, from opposite sides of
the pass. Keeping them in one file makes the shared payment and split logic
impossible to let drift apart.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, Header
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .. import allergens, events, intelligence as ai, rtime
from ..database import engine
from ..live import close_tasks, hub, open_task, touch
from ..ops_utils import ARCHIVED_ZONE, archived_menu_ids, unavailable_menu_ids
from ..models import (
    AuditLog, DiningTable, Feedback, Guest, ItemState, MenuItem, Notification,
    Order, OrderItem, Payment, Reservation, Staff, Role, TableNote, TableStatus,
    Task, TaskKind,
)
from ..permissions import current_staff, has_permission, require_permission

router = APIRouter()

VOID_REASONS = {"Guest changed mind", "Incorrect item entered", "Allergy correction",
                "Manager request", "Kitchen issue"}


def payment_actor(authorization: str = Header(default="")):
    """Payments are the one workspace guests and staff both touch. A guest
    paying from their own phone sends no Authorization header at all — that
    is always allowed. A staff member acting from the waiter app sends one,
    and that one has to actually carry the payment permission."""
    if not authorization.strip():
        return None
    staff = current_staff(authorization)
    if not has_permission(staff.role, "can_take_payment"):
        from fastapi import HTTPException
        raise HTTPException(403, "Your role doesn't allow taking payment.")
    return staff


def db() -> Session:
    return Session(engine, expire_on_commit=False)


def money(x: float) -> float:
    return round(float(x or 0), 2)


def bill_for(s: Session, table: DiningTable) -> dict:
    """The single source of truth for what a table owes. Both apps use it."""
    order = s.exec(select(Order).where(
        Order.table_id == table.id, Order.paid == False)).first()  # noqa: E712
    if not order:
        return {"order_id": None, "lines": [], "total": 0.0, "paid": 0.0,
                "outstanding": 0.0, "party": table.party_size, "payments": []}

    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    lines = []
    for i in s.exec(select(OrderItem).where(OrderItem.order_id == order.id)).all():
        if i.void_reason:
            continue
        m = menu.get(i.menu_item_id)
        if not m:
            continue
        lines.append({"id": i.id, "name": m.name, "qty": i.qty, "price": m.price,
                      "line_total": money(m.price * i.qty), "note": i.note,
                      "state": i.state.value, "course": m.course,
                      "seat": i.seat, "course_no": i.course_no,
                      "fired_at": i.fired_at.strftime("%H:%M")})
    total = money(sum(l["line_total"] for l in lines))
    pays = s.exec(select(Payment).where(Payment.order_id == order.id)).all()
    paid = money(sum(p.amount for p in pays))
    tip_paid = money(sum(p.tip for p in pays))
    return {
        "order_id": order.id, "lines": lines, "total": total, "paid": paid,
        "tip_paid": tip_paid, "grand_paid": money(paid + tip_paid),
        "outstanding": money(max(0.0, total - paid)),
        "party": max(1, table.party_size),
        "payments": [{"payer": p.payer, "amount": money(p.amount),
                      "tip": money(p.tip), "total_with_tip": money(p.amount+p.tip),
                      "method": p.method, "at": p.created_at.strftime("%H:%M")} for p in pays],
    }


# ==================================================================== waiter
# Staff sign-in itself lives in routers/auth_api.py (/api/auth/roster,
# /api/auth/login) and is shared with the admin app. Everything below
# assumes the caller already has a valid session.

@router.get("/api/waiter/board")
def waiter_board(staff: Staff = Depends(current_staff)):
    """Live service board scoped to the signed-in employee."""
    with db() as s:
        now = rtime.now()
        staff_map = {p.id: p for p in s.exec(select(Staff)).all()}
        guests = {g.id: g for g in s.exec(select(Guest)).all()}
        menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
        open_orders = s.exec(select(Order).where(Order.paid == False)).all()  # noqa: E712
        by_table = {o.table_id: o for o in open_orders}
        spend, ready_items = defaultdict(float), defaultdict(list)
        for o in open_orders:
            for i in s.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all():
                if i.void_reason:
                    continue
                m = menu.get(i.menu_item_id)
                if not m: continue
                spend[o.table_id] += m.price * i.qty
                if i.state == ItemState.READY:
                    ready_items[o.table_id].append({"id": i.id, "name": m.name, "qty": i.qty, "seat": i.seat})
        tasks_by_table = defaultdict(list)
        for task in s.exec(select(Task).where(Task.done == False)).all():  # noqa: E712
            tasks_by_table[task.table_id].append(task)
        tables, queue = [], []
        for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
            if t.zone == ARCHIVED_ZONE:
                continue
            mine = t.waiter_id == staff.id
            g = guests.get(t.guest_id) if t.guest_id else None
            waited = round((now - t.last_touched_at).total_seconds()/60) if t.last_touched_at else 0
            limit = ai.SERVICE_LIMITS.get(t.status)
            row = {
                "id":t.id,"number":t.number,"seats":t.seats,"zone":t.zone,"x":t.x,"y":t.y,"shape":t.shape,
                "status":t.status.value,"party":t.party_size,"mine":mine,
                "waiter":staff_map[t.waiter_id].name.split()[0] if t.waiter_id in staff_map else "—",
                "waiter_id":t.waiter_id,"minutes":waited,"alert":bool(limit and waited>limit),
                "spend":money(spend.get(t.id,0)),"seated_minutes":round((now-t.seated_at).total_seconds()/60) if t.seated_at else 0,
                "has_order":t.id in by_table,"ready":ready_items.get(t.id,[]),
                "guest":({"name":g.name,"vip":g.vip,"visits":g.visits,"allergies":g.allergies,"likes":g.likes,"pref":g.seating_pref,"note":g.note} if g else None),
                "tasks":[{"id":k.id,"kind":k.kind.value,"message":k.message,"priority":k.priority,
                          "minutes":round((now-k.created_at).total_seconds()/60)} for k in tasks_by_table.get(t.id,[])],
            }
            tables.append(row)
            for k in row["tasks"]:
                queue.append({**k,"table":t.number,"table_id":t.id,"zone":t.zone,"mine":mine,
                              "priority":1 if k["minutes"]>5 else k["priority"]})
            if row["alert"] and not row["tasks"]:
                queue.append({"id":f"risk-{t.id}","kind":"checkin","message":f"Table {t.number} has been {t.status.value.replace('_',' ')} for {waited} min",
                              "priority":1 if waited>(limit or 5)*1.6 else 2,"minutes":waited,"table":t.number,"table_id":t.id,"zone":t.zone,"mine":mine,"soft":True})
        queue.sort(key=lambda k:(0 if k["mine"] else 1,k["priority"],-k["minutes"]))
        mine_tables=[t for t in tables if t["mine"] and t["status"]!="available"]
        return {"staff":{"id":staff.id,"name":staff.name,"section":staff.section,"role":staff.role.value},
                "tables":tables,"queue":queue,"summary":{"open_tasks":len([k for k in queue if k["mine"] and not k.get("soft")]),
                "my_tables":len(mine_tables),"my_covers":sum(t["party"] for t in mine_tables),"my_spend":money(sum(t["spend"] for t in mine_tables)),
                "at_pass":sum(len(t["ready"]) for t in mine_tables),"late":sum(1 for t in mine_tables if t["alert"])}}


@router.get("/api/waiter/menu")
def waiter_menu(staff: Staff = Depends(current_staff)):
    """The order pad. Grouped by course, with allergens front and centre."""
    with db() as s:
        pressure = {p["station"]: p["now"] for p in ai.station_pressure(s)}
        out = []
        blocked, block_reasons = unavailable_menu_ids(s)
        archived = archived_menu_ids(s)
        for m in s.exec(select(MenuItem).order_by(MenuItem.course, MenuItem.name)).all():
            if m.id in archived:
                continue
            low, high = ai.predict_prep_time(s, m, pressure.get(m.station.value, 0))
            out.append({
                "id": m.id, "name": m.name, "course": m.course, "price": m.price,
                "station": m.station.value, "available": bool(m.available and m.id not in blocked),
                "unavailable_reason": block_reasons.get(m.id, ""),
                "tags": [t for t in m.tags.split(",") if t],
                "wait": f"{low}–{high}", "sold": m.sold_30d, "hue": m.hue,
            })
        return {"items": out,
                "courses": ["Snack", "Starter", "Main", "Side", "Dessert", "Drink"]}


@router.post("/api/waiter/order")
async def waiter_order(body: dict = Body(...),
                        staff: Staff = Depends(require_permission("can_create_order"))):
    """Send a course. Each line can carry a seat number and a course number,
    so the bill and the kitchen both know what round something belongs to."""
    with db() as s:
        t = s.get(DiningTable, int(body.get("table_id", 0)))
        lines = body.get("items", [])
        if not t:
            return JSONResponse({"error": "Pick a table before sending."}, 400)
        if t.zone == ARCHIVED_ZONE:
            return JSONResponse({"error": "That table is no longer active."}, 400)
        if not lines:
            return JSONResponse({"error": "The pad is empty."}, 400)
        unread_allergy = s.exec(select(TableNote).where(
            TableNote.table_id == t.id, TableNote.kind == "allergy",
            TableNote.acknowledged == False)).first()  # noqa: E712
        if unread_allergy:
            return JSONResponse({
                "error": f"Acknowledge the allergy note before sending: "
                         f"\u201c{unread_allergy.message}\u201d",
                "note_id": unread_allergy.id, "needs_ack": True}, 400)

        # Inspect the whole pad against everything this table has declared —
        # on the booking, in a booking note, on the guest's profile or written
        # on the table by staff — before any of it reaches the kitchen. Tags
        # AND recipes, so an untagged dish that actually contains scallops is
        # still caught. A waiter can send anyway, but only deliberately, and
        # the override is recorded on the table.
        wanted_ids = []
        for line in lines:
            if isinstance(line, dict):
                try:
                    wanted_ids.append(int(line.get("id") or 0))
                except (TypeError, ValueError):
                    pass
        check = allergens.screen(s, t.id, wanted_ids)
        if check["conflicts"] and not body.get("allergen_override"):
            return JSONResponse({
                "error": allergens.sentence(check["conflicts"]),
                "allergen_conflicts": check["conflicts"],
                "declared": check["declared"]["allergens"],
                "unrecognised": check["unrecognised"],
                "needs_allergen_override": True}, 409)
        # Whether it was overridden or waved through, the line that clashes
        # goes to the pass carrying the reason. A ticket rail is the last
        # place anybody sees this dish before it is cooked.
        allergen_note: dict[int, str] = {}
        for c in check["conflicts"]:
            stamp = "ALLERGY: %s declared %s — this dish %s" % (
                c["declared_by"], c["allergen"], c["evidence"])
            prev = allergen_note.get(c["menu_item_id"], "")
            allergen_note[c["menu_item_id"]] = (prev + " · " + stamp) if prev else stamp

        if check["conflicts"] and body.get("allergen_override"):
            # Recorded as an internal note, not an allergy one: this is the
            # audit trail of a decision, and filing it as a declaration would
            # feed the dish names in it straight back into the next screening
            # ("Tuna Crudo" read as a fish allergy).
            s.add(TableNote(
                table_id=t.id, author_id=staff.id, author_name=staff.name,
                kind="internal", acknowledged=True,
                message="Sent against an allergy warning: " +
                        "; ".join("%s (%s)" % (c["dish"], c["allergen"])
                                  for c in check["conflicts"])))
            events.record(s, "allergen_override", "Allergy warning overridden",
                          detail=allergens.sentence(check["conflicts"]),
                          table_id=t.id, table_number=t.number,
                          actor=staff.name or "Waiter", severity="critical")

        validated_lines = []
        for line in lines:
            if not isinstance(line, dict):
                return JSONResponse({"error": "Each order line must be an object."}, 400)
            try:
                menu_id = int(line["id"])
                qty = int(line.get("qty", 1))
                seat = int(line.get("seat", 0))
            except (KeyError, TypeError, ValueError):
                return JSONResponse({"error": "Each order line needs a valid dish, quantity and seat."}, 400)
            if not 1 <= qty <= 50:
                return JSONResponse({"error": "Quantity must be between 1 and 50."}, 400)
            if seat < 0 or (t.seats and seat > t.seats):
                return JSONResponse({"error": f"Seat must be between 1 and {t.seats}, or 0 for shared."}, 400)
            note = str(line.get("note") or "").strip()
            if len(note) > 500:
                return JSONResponse({"error": "Item notes are too long."}, 400)
            try:
                course_no = int(body.get("course_no", line.get("course_no", 1)))
            except (TypeError, ValueError):
                return JSONResponse({"error": "Course number must be a number."}, 400)
            if not 1 <= course_no <= 10:
                return JSONResponse({"error": "Course number must be between 1 and 10."}, 400)
            validated_lines.append((menu_id, qty, seat, note, course_no))

        # merge the allergy stamp into each affected line's own note
        validated_lines = [
            (mid, q, st, ((allergen_note[mid] + (" · " + n if n else "")) if mid in allergen_note else n), c)
            for (mid, q, st, n, c) in validated_lines]

        blocked, block_reasons = unavailable_menu_ids(s)
        for menu_id, _, _, _, _ in validated_lines:
            menu_item = s.get(MenuItem, menu_id)
            if not menu_item:
                return JSONResponse({"error": "That dish no longer exists."}, 404)
            if not menu_item.available or menu_item.id in blocked:
                return JSONResponse({
                    "error": f"{menu_item.name} is no longer available. "
                              + block_reasons.get(menu_item.id, "Ask the kitchen for an alternative.")
                }, 409)

        order = s.exec(select(Order).where(
            Order.table_id == t.id, Order.paid == False)).first()  # noqa: E712
        if not order:
            order = Order(table_id=t.id, waiter_id=staff.id or t.waiter_id)
            s.add(order)
            s.commit()
            s.refresh(order)

        rush = bool(body.get("priority"))
        pressure = {p["station"]: p["now"] for p in ai.station_pressure(s)}
        longest = 0
        added = 0
        for menu_id, qty, seat, note, course_no in validated_lines:
            m = s.get(MenuItem, menu_id)
            if not m:
                return JSONResponse({"error": "That dish no longer exists."}, 404)
            queue = pressure.get(m.station.value, 0)
            low, high = ai.predict_prep_time(s, m, queue)
            if rush:
                high = max(3, round(high * 0.7))     # kitchen agrees to jump it
            longest = max(longest, high)
            s.add(OrderItem(order_id=order.id, menu_item_id=m.id, qty=qty,
                            station=m.station, note=note, seat=seat, course_no=course_no,
                            promised_minutes=high))
            added += 1
            pressure[m.station.value] = queue + qty

        if not added:
            return JSONResponse({"error": "No valid dishes were selected."}, 400)

        if t.status in (TableStatus.SEATED, TableStatus.ORDERING,
                        TableStatus.AVAILABLE, TableStatus.DINING):
            t.status = TableStatus.COOKING
            t.seated_at = t.seated_at or rtime.now()
            t.party_size = t.party_size or len(lines)
        close_tasks(s, t.id, TaskKind.CALL)
        touch(t)
        s.add(t)
        if rush:
            s.add(Notification(level="warning", title=f"Table {t.number} pushed to the front",
                               body="Waiter asked the kitchen for priority.",
                               audience="kitchen"))
        s.commit()
    await hub.send("state", {"changed": ["order"]})
    return {"ok": True, "eta": longest,
            "message": f"Sent. About {longest} minutes." + (" Marked priority." if rush else "")}


@router.post("/api/waiter/item/{item_id}")
async def modify_item(item_id: int, body: dict = Body(...),
                       staff: Staff = Depends(require_permission("can_edit_order"))):
    """Change a line before the kitchen has touched it, or void it with a
    reason. Once the kitchen has started, further changes need a manager —
    that approval flow is the next phase; for now this stops here with an
    honest message rather than pretending to apply the change."""
    with db() as s:
        i = s.get(OrderItem, item_id)
        if not i:
            return JSONResponse({"error": "That line is gone."}, 404)
        order = s.get(Order, i.order_id)
        table = s.get(DiningTable, order.table_id) if order else None
        if not order or order.paid or not table:
            return JSONResponse({"error": "That bill is already closed."}, 400)
        if i.void_reason:
            return JSONResponse({"error": "That line has already been voided."}, 409)

        if body.get("void"):
            reason = (body.get("reason") or "").strip()
            if i.state != ItemState.QUEUED:
                return JSONResponse({
                    "error": "Kitchen has already started this item. "
                             "Voiding it now needs a manager's approval.",
                    "needs_manager": True}, 400)
            if reason not in VOID_REASONS:
                return JSONResponse({
                    "error": "Choose a reason for the void.",
                    "reasons": sorted(VOID_REASONS)}, 400)
            s.add(AuditLog(staff_id=staff.id, action="void_item",
                           entity_type="order_item", entity_id=i.id,
                           detail=f"{i.qty} × item #{i.menu_item_id} — {reason}"))
            # Keep the line for auditability and reporting; operational views
            # already exclude lines with a void reason.
            i.void_reason = reason
            s.add(i)
            s.commit()
            await hub.send("state", {"changed": ["order"]})
            return {"ok": True, "message": "Line voided."}

        if ("qty" in body or "note" in body) and i.state != ItemState.QUEUED:
            return JSONResponse({
                "error": "Kitchen has already started this item.",
                "needs_manager": True}, 400)
        if "qty" in body:
            try:
                qty = int(body["qty"])
            except (TypeError, ValueError):
                return JSONResponse({"error": "Quantity must be a number."}, 400)
            if not 1 <= qty <= 50:
                return JSONResponse({"error": "Quantity must be between 1 and 50."}, 400)
            i.qty = qty
        if "note" in body:
            i.note = str(body["note"] or "").strip()
            if len(i.note) > 500:
                return JSONResponse({"error": "Item notes are too long."}, 400)
        if "seat" in body:
            try:
                seat = int(body["seat"])
            except (TypeError, ValueError):
                return JSONResponse({"error": "Seat must be a number."}, 400)
            i.seat = seat
            if seat < 0 or (table.seats and seat > table.seats):
                return JSONResponse({"error": f"Seat must be between 1 and {table.seats}, or 0 for shared."}, 400)
        if body.get("serve"):
            i.state = ItemState.SERVED
        s.add(i)
        s.commit()
    await hub.send("state", {"changed": ["order"]})
    return {"ok": True}


@router.post("/api/waiter/table/{table_id}/serve")
async def serve_table(table_id: int, staff: Staff = Depends(current_staff)):
    """Everything at the pass has been carried and put down."""
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        order = s.exec(select(Order).where(
            Order.table_id == t.id, Order.paid == False)).first()  # noqa: E712
        count = 0
        if order:
            for i in s.exec(select(OrderItem).where(
                    OrderItem.order_id == order.id,
                    OrderItem.state == ItemState.READY)).all():
                i.state = ItemState.SERVED
                s.add(i)
                count += 1
        close_tasks(s, t.id, TaskKind.RUNNER)
        if t.status == TableStatus.READY:
            t.status = TableStatus.DINING
        touch(t)
        s.add(t)
        s.commit()
    await hub.send("state", {"changed": ["served"]})
    return {"ok": True, "message": f"{count} dishes marked served."}


@router.post("/api/waiter/table/{table_id}/state")
async def set_table_state(table_id: int, body: dict = Body(...),
                          staff: Staff = Depends(require_permission("can_set_table_state"))):
    """SEATED / FREE from the tablet.

    This is the physical room, not the book: it turns the table's lamp in
    SUFRA OS and SUFRA 360 at once, and carries the booking sitting on that
    table with it so the two can never disagree. Future reservations on the
    same table are untouched.
    """
    wanted = str(body.get("state") or "").strip().lower()
    if wanted in ("occupied", "seat", "seated"):
        wanted = "seated"
    elif wanted in ("free", "available", "complete", "completed"):
        wanted = "available"
    else:
        return JSONResponse({"error": "Choose SEATED or FREE."}, 400)

    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        now = rtime.now()
        linked = _booking_on(s, t)
        if wanted == "seated":
            t.status = TableStatus.SEATED
            t.seated_at = now
            try:
                party = int(body.get("party") or (linked.party_size if linked else 0) or t.party_size or 2)
            except (TypeError, ValueError):
                party = t.party_size or 2
            t.party_size = max(1, min(t.seats, party))
            if linked is not None:
                t.guest_id = linked.guest_id
                if linked.status in ("confirmed", "late"):
                    linked.status = "seated"
                    linked.seated_at = now
                    linked.updated_at = now
                    s.add(linked)
                    from ..bookings import carry_allergies_to_table
                    carry_allergies_to_table(s, linked, t)
            message = f"Table {t.number} is occupied."
            title, kind, severity = "Table marked occupied", "table_status", "note"
        else:
            t.status = TableStatus.AVAILABLE
            t.party_size = 0
            t.guest_id = None
            t.seated_at = None
            close_tasks(s, t.id)
            if linked is not None and linked.status == "seated":
                linked.status = "completed"
                linked.completed_at = linked.left_at = now
                linked.updated_at = now
                s.add(linked)
            message = f"Table {t.number} is free."
            title, kind, severity = "Table marked free", "table_status", "good"
        touch(t)
        s.add(t)
        events.record(s, kind, title, detail=(linked.code if linked is not None else ""),
                      table_id=t.id, table_number=t.number,
                      reservation_id=linked.id if linked is not None else None,
                      actor=staff.name or "Waiter", severity=severity)
        s.commit()
    await hub.send("state", {"changed": ["status"]})
    return {"ok": True, "state": wanted, "message": message}


def _booking_on(s: Session, table: DiningTable):
    """The booking attached to this table right now.

    A party that has been marked seated owns the table until it is freed,
    whatever hour the booking was for. Otherwise this is the arrival closest
    to now, so seating a table also seats the booking that was expecting it.
    """
    from ..bookings import seated_reservation_on
    seated = seated_reservation_on(s, table.id)
    if seated is not None:
        return seated
    now = rtime.now()
    rows = s.exec(select(Reservation).where(
        Reservation.table_id == table.id,
        Reservation.starts_at >= now - timedelta(hours=4),
        Reservation.starts_at <= now + timedelta(hours=2))).all()
    live = [r for r in rows if (r.status or "") in ("confirmed", "late")]
    return min(live, key=lambda r: abs((r.starts_at - now).total_seconds())) if live else None



@router.post("/api/waiter/table/{table_id}/move")
async def move_party(table_id: int, body: dict = Body(...),
                      staff: Staff = Depends(current_staff)):
    """Move a party to another table, carrying the order and the guest with it."""
    with db() as s:
        src = s.get(DiningTable, table_id)
        dst = s.exec(select(DiningTable).where(
            DiningTable.number == int(body.get("to", 0)))).first()
        if not src or not dst:
            return JSONResponse({"error": "Pick a table that exists."}, 404)
        if dst.status != TableStatus.AVAILABLE:
            return JSONResponse({"error": f"Table {dst.number} is not free."}, 400)
        if dst.seats < src.party_size:
            return JSONResponse(
                {"error": f"Table {dst.number} seats {dst.seats}, party is {src.party_size}."}, 400)

        for o in s.exec(select(Order).where(
                Order.table_id == src.id, Order.paid == False)).all():  # noqa: E712
            o.table_id = dst.id
            s.add(o)
        for k in s.exec(select(Task).where(Task.table_id == src.id,
                                           Task.done == False)).all():  # noqa: E712
            k.table_id = dst.id
            k.message = k.message.replace(f"table {src.number}", f"table {dst.number}")
            s.add(k)

        dst.status, src.status = src.status, TableStatus.CLEANING
        dst.party_size, src.party_size = src.party_size, 0
        dst.guest_id, src.guest_id = src.guest_id, None
        dst.seated_at, src.seated_at = src.seated_at, None
        dst.waiter_id = src.waiter_id
        touch(dst)
        touch(src)
        s.add(dst)
        s.add(src)
        open_task(s, src, TaskKind.CLEAR, f"Clear and reset table {src.number}", 3)
        s.commit()
        msg = f"Party moved from {src.number} to {dst.number}."
    await hub.send("state", {"changed": ["moved-party"]})
    return {"ok": True, "message": msg}


@router.post("/api/waiter/table/{table_id}/manager")
async def call_manager(table_id: int, body: dict = Body(...),
                        staff: Staff = Depends(current_staff)):
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        reason = body.get("reason", "Waiter needs a manager")
        s.add(Notification(level="critical", title=f"Manager needed at table {t.number}",
                           body=reason, audience="manager"))
        open_task(s, t, TaskKind.CALL, f"Manager requested at table {t.number}: {reason}", 1)
        s.commit()
    await hub.send("state", {"changed": ["manager"]})
    return {"ok": True, "message": "A manager has been paged."}


@router.get("/api/waiter/table/{table_id}/allergens")
def table_allergens(table_id: int, items: str = "", staff: Staff = Depends(current_staff)):
    """What this table cannot eat, and which of these dishes break it.

    `items` is an optional comma-separated list of menu item ids, so the
    order pad can colour a dish the moment it is tapped rather than waiting
    for the ticket to be refused.
    """
    ids = []
    for part in (items or "").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        result = allergens.screen(s, table_id, ids)
        return {
            "table": t.number,
            "guest": result["declared"]["guest"],
            "declared": result["declared"]["allergens"],
            "entries": result["declared"]["entries"],
            "unrecognised": result["unrecognised"],
            "unacknowledged": result["declared"]["unacknowledged"],
            "conflicts": result["conflicts"],
            "message": allergens.sentence(result["conflicts"]),
        }


@router.get("/api/waiter/table/{table_id}/notes")
def table_notes(table_id: int, staff: Staff = Depends(current_staff)):
    with db() as s:
        rows = s.exec(select(TableNote).where(TableNote.table_id == table_id)
                      .order_by(TableNote.created_at.desc())).all()
        return {"notes": [{
            "id": n.id, "kind": n.kind, "message": n.message,
            "author": n.author_name, "acknowledged": n.acknowledged,
            "at": n.created_at.strftime("%H:%M"),
        } for n in rows]}


@router.post("/api/waiter/table/{table_id}/notes")
async def add_table_note(table_id: int, body: dict = Body(...),
                          staff: Staff = Depends(current_staff)):
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "Write the note first."}, 400)
    kind = body.get("kind", "service")
    with db() as s:
        n = TableNote(table_id=table_id, author_id=staff.id, author_name=staff.name,
                      kind=kind, message=message,
                      acknowledged=(kind != "allergy"))
        s.add(n)
        s.commit()
    await hub.send("state", {"changed": ["notes"]})
    return {"ok": True}


@router.post("/api/waiter/notes/{note_id}/ack")
async def ack_note(note_id: int, staff: Staff = Depends(current_staff)):
    with db() as s:
        n = s.get(TableNote, note_id)
        if not n:
            return JSONResponse({"error": "That note is gone."}, 404)
        n.acknowledged = True
        s.add(n)
        s.commit()
    return {"ok": True}


@router.get("/api/waiter/bill/{table_id}")
def waiter_bill(table_id: int, staff: Staff = Depends(current_staff)):
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        return {"table": t.number, **bill_for(s, t)}


# ==================================================================== payments
# Shared by both apps so a split started on a phone can be finished on a tablet.

@router.post("/api/pay/{table_id}")
async def take_payment(table_id: int, body: dict = Body(...),
                        actor: Staff = Depends(payment_actor)):
    """
    kind: full | equal | item | custom
      equal  -> needs `splits` and optionally `paying` (how many shares now)
      item   -> needs `item_ids`
      custom -> needs `amount`

    Called from the guest phone with no Authorization header (a guest is
    always allowed to pay their own bill) or from the waiter tablet with
    one, in which case payment_actor has already checked can_take_payment.
    """
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "No such table."}, 404)
        bill = bill_for(s, t)
        if not bill["order_id"]:
            return JSONResponse({"error": "Nothing to pay for on this table."}, 400)

        kind = body.get("kind", "full")
        if kind not in {"full", "equal", "item", "custom"}:
            return JSONResponse({"error": "Choose a valid payment split."}, 400)
        method = str(body.get("method", "card") or "card").strip().lower()
        if method not in {"card", "applepay", "googlepay", "cash", "qr"}:
            return JSONResponse({"error": "Choose a valid payment method."}, 400)
        try:
            tip_pct = float(body.get("tip_pct", 0) or 0)
        except (TypeError, ValueError):
            return JSONResponse({"error": "Tip percentage must be a number."}, 400)
        if not math.isfinite(tip_pct) or not 0 <= tip_pct <= 100:
            return JSONResponse({"error": "Tip percentage must be between 0 and 100."}, 400)
        outstanding = bill["outstanding"]
        if outstanding <= 0.01:
            return JSONResponse({"error": "This bill has already been settled."}, 409)

        if kind == "equal":
            try:
                splits = int(body.get("splits", bill["party"]))
                paying_input = int(body.get("paying", 1))
            except (TypeError, ValueError):
                return JSONResponse({"error": "Split counts must be numbers."}, 400)
            if not 1 <= splits <= 50:
                return JSONResponse({"error": "Splits must be between 1 and 50."}, 400)
            paying = max(1, min(splits, paying_input))
            amount = money(bill["total"] / splits * paying)
            payer = f"{paying} of {splits} shares"
        elif kind == "item":
            try:
                ids = {int(x) for x in body.get("item_ids", [])}
            except (TypeError, ValueError):
                return JSONResponse({"error": "Choose valid bill items."}, 400)
            known_ids = {line["id"] for line in bill["lines"]}
            if not ids or not ids.issubset(known_ids):
                return JSONResponse({"error": "Choose only items on this bill."}, 400)
            amount = money(sum(l["line_total"] for l in bill["lines"] if l["id"] in ids))
            payer = f"{len(ids)} item{'s' if len(ids) != 1 else ''}"
            if not amount:
                return JSONResponse({"error": "Select at least one item to pay for."}, 400)
        elif kind == "custom":
            try:
                amount = money(float(body.get("amount", 0)))
            except (TypeError, ValueError):
                return JSONResponse({"error": "Enter a valid amount."}, 400)
            payer = "Custom amount"
            if amount <= 0:
                return JSONResponse({"error": "Enter an amount above zero."}, 400)
        else:
            amount = outstanding
            payer = "Full bill"

        if amount > outstanding + 0.01:
            amount = outstanding
        if amount <= 0 or not math.isfinite(amount):
            return JSONResponse({"error": "Payment amount must be above zero."}, 400)
        tip = money(amount * tip_pct / 100)

        # Build the reference here and keep it as a plain string. Reading it
        # off the model after the session closes raises DetachedInstanceError.
        reference = f"NV{rtime.now().strftime('%H%M%S')}"
        s.add(Payment(order_id=bill["order_id"], amount=amount, tip=tip,
                      method=method, kind=kind, payer=payer,
                      reference=reference))
        s.flush()

        remaining = money(bill["total"] - bill["paid"] - amount)
        if remaining <= 0.01:
            order = s.get(Order, bill["order_id"])
            order.paid = True
            order.closed_at = rtime.now()
            order.tip = money(sum(x.tip for x in s.exec(
                select(Payment).where(Payment.order_id == order.id)).all()))
            s.add(order)
            close_tasks(s, t.id, TaskKind.BILL)
            t.status = TableStatus.CLEANING
            touch(t)
            s.add(t)
            open_task(s, t, TaskKind.CLEAR, f"Clear and reset table {t.number}", 3)
        settled_order_id = bill["order_id"] if remaining <= 0.01 else None
        s.commit()
    # A settled bill is the point the restaurant has definitively sold the
    # food, so it is where Anbar explodes the recipes and takes the
    # ingredients out of stock. Keyed per order line, so re-settling or a
    # retried request cannot deduct anything twice.
    if settled_order_id:
        from .. import anbar
        anbar.consume_order_safe(settled_order_id)
    await hub.send("state", {"changed": ["payment"]})
    return {"ok": True, "paid": amount, "tip": tip, "remaining": max(0.0, remaining),
            "settled": remaining <= 0.01, "reference": reference,
            "message": (f"£{amount:.2f} taken" + (f" plus £{tip:.2f} tip" if tip else "")
                        + (". Bill settled." if remaining <= 0.01
                           else f". £{remaining:.2f} still to pay."))}


# ==================================================================== guest

@router.get("/api/guest/{table_number}/state")
def guest_state(table_number: int):
    """Everything the phone needs: my order, how it's going, what I owe."""
    with db() as s:
        t = s.exec(select(DiningTable).where(
            DiningTable.number == table_number)).first()
        if not t or t.zone == ARCHIVED_ZONE:
            return JSONResponse({"error": "That table code is not in use."}, 404)

        bill = bill_for(s, t)
        stages = {"queued": "with the kitchen", "cooking": "being cooked",
                  "ready": "on its way", "served": "at your table"}
        progress = [{"name": l["name"], "qty": l["qty"],
                     "stage": stages.get(l["state"], l["state"])} for l in bill["lines"]]
        eta = 0
        order = s.get(Order, bill["order_id"]) if bill["order_id"] else None
        if order:
            now = rtime.now()
            for i in s.exec(select(OrderItem).where(
                    OrderItem.order_id == order.id,
                    OrderItem.state.in_([ItemState.QUEUED, ItemState.COOKING]))).all():
                left = i.promised_minutes - (now - i.fired_at).total_seconds() / 60
                eta = max(eta, round(max(0, left)))

        return {"table": t.number, "seats": t.seats, "zone": t.zone,
                "status": t.status.value, "progress": progress, "eta": eta,
                "open_requests": [k.kind.value for k in s.exec(
                    select(Task).where(Task.table_id == t.id,
                                       Task.done == False)).all()],  # noqa: E712
                **bill}


@router.post("/api/guest/{table_number}/feedback")
async def guest_feedback(table_number: int, body: dict = Body(...)):
    with db() as s:
        scores = {k: max(1, min(5, int(body.get(k, 5))))
                  for k in ("food", "service", "atmosphere", "speed")}
        comment = (body.get("comment") or "").strip()
        s.add(Feedback(table_id=table_number, comment=comment, **scores))

        # A poor score is an operational event, not a survey row. Tell someone
        # while the guest is still in the building.
        if min(scores.values()) <= 2:
            weak = min(scores, key=scores.get)
            s.add(Notification(
                level="critical", title=f"Table {table_number} rated {weak} poorly",
                body=comment or "No comment left. Worth a visit to the table now.",
                audience="manager"))
        s.commit()
    await hub.send("state", {"changed": ["feedback"]})
    return {"ok": True, "message": "Thank you — that goes straight to the manager on duty."}
