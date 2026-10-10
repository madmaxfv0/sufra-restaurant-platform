"""
SUFRA Restaurant OS — HTTP layer.

Five screens, one JSON API, one WebSocket. Every screen reads the same
snapshot endpoint, so the floor plan on the manager's laptop and the ticket
rail in the kitchen can never disagree.
"""

from __future__ import annotations

import asyncio
import os
import json
import traceback
import urllib.parse
import urllib.request
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from fastapi import Body, Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from . import allergens, availability as av, canon, events, intelligence as ai, lifecycle, netutil, rtime
from .database import create_db, engine, DB_PATH, IS_SQLITE
from .live import close_tasks, hub, open_task, simulation_loop, touch
from .ops_utils import ARCHIVED_ZONE, archived_menu_ids, unavailable_menu_ids
from .permissions import require_permission
from .models import (
    DiningTable, Feedback, Guest, Ingredient, ItemState, MenuItem, MenuContent, MenuSection,
    Notification, Order, OrderItem, Payment, Reservation, Role, Staff, TableStatus, Task, TaskKind,
    TranslationCache, WasteLog,
)

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if (IS_SQLITE and not DB_PATH.exists()
            and os.getenv("NOVA_SEED_DEMO", "").lower() in {"1", "true", "yes", "on"}):
        from .seed import build
        build()
    create_db()
    from .routers import sufra_upgrade, enterprise
    sufra_upgrade.ensure_schema()
    enterprise.ensure_schema()
    # The canonical layer: additive migration, then reconcile the table
    # registry with the physical room so SUFRA OS and SUFRA 360 describe one
    # restaurant with one identifier per table.
    canon.ensure_schema()
    canon.sync_table_registry()
    canon.relayout_floor()
    canon.repair_stale_service()
    # SUFRA ANBAR: warehouse tables, the widened supplier/purchasing columns,
    # and an InvItem profile for every ingredient that predates the module.
    from . import anbar
    anbar.ensure_schema()
    tasks = []
    # Exactly one scheduler in the whole system lives here: reservation
    # late/no-show automation and the T-15 reminder. SUFRA 360 runs none, so
    # no booking can be processed twice.
    tasks.append(asyncio.create_task(lifecycle.loop()))
    # The cross-process event tail: rows written by SUFRA 360 in another
    # process reach this server's websockets through it.
    tasks.append(asyncio.create_task(events.tail_loop()))
    if os.getenv("NOVA_SIMULATE", "0").lower() in {"1", "true", "yes", "on"}:
        tasks.append(asyncio.create_task(simulation_loop()))
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="SUFRA Restaurant OS", lifespan=lifespan)

# SUFRA 360 is a separate customer-facing application on its own port and
# origin; it talks to this API rather than the database, so it needs CORS.
# The origin list is an env var, not a hard-coded localhost, so a production
# deploy can point it at the real 360 domain without touching this file.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in
                   os.environ.get("SUFRA_360_ORIGIN", "http://127.0.0.1:8013").split(",") if o.strip()],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_credentials=True,
    allow_headers=["*"],
)

BUILD_ID = "20260902-sufra-pre-v7-server-hotfix"

@app.get("/api/build")
def api_build():
    return {"app": "SUFRA Restaurant OS", "build": BUILD_ID}


@app.middleware("http")
async def never_cache(request, call_next):
    """Never cache local UI assets and turn unexpected backend exceptions
    into useful JSON instead of a silent/request-timeout-looking failure."""
    try:
        response = await call_next(request)
    except Exception as exc:
        log = BASE.parent / "sufra_server_errors.log"
        try:
            with log.open("a", encoding="utf-8") as fh:
                fh.write(f"\n[{rtime.now().isoformat()}] {request.method} {request.url.path}\n")
                fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        except Exception:
            pass
        response = JSONResponse({
            "error": "The server could not complete that action.",
            "detail": str(exc),
            "path": request.url.path,
        }, status_code=500)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

class NoCacheStaticFiles(StaticFiles):
    """Every JS/CSS file in this project is actively being rewritten between
    sessions. Browsers happily cache static assets for a long time by
    default, which means a person can download a brand-new build and still
    silently run yesterday's JavaScript against today's HTML. Since this is
    a local demo, not a production site serving thousands of users, the
    tradeoff is easy: never cache, always serve what's actually on disk."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


# follow_symlink: a hosted deploy keeps static/uploads and static/generated on
# the persistent volume behind symlinks (deploy/entrypoint.sh), and StaticFiles
# 404s anything that resolves outside its directory unless this is set.
app.mount("/static", NoCacheStaticFiles(directory=str(BASE / "static"), follow_symlink=True), name="static")

from .routers import admin_api, auth_api, service_api, operations_v2          # noqa: E402, sufra_upgrade
app.include_router(auth_api.router)
app.include_router(admin_api.router)
app.include_router(service_api.router)
app.include_router(operations_v2.router)


from .routers import sufra_upgrade as _sufra_upgrade
sufra_upgrade = _sufra_upgrade  # minimal server hotfix
sufra_upgrade = _sufra_upgrade  # stable global alias used by table_payload
from .routers import enterprise as _enterprise
app.include_router(_sufra_upgrade.router)
from .routers import public_booking as _public_booking
app.include_router(_public_booking.router)
from .routers import media_v4 as _media_v4
app.include_router(_media_v4.router)
from .routers import public_v2 as _public_v2
app.include_router(_public_v2.router)
app.include_router(_enterprise.router)
from .routers import anbar as _anbar
app.include_router(_anbar.router)
def db() -> Session:
    return Session(engine, expire_on_commit=False)


def _currency() -> str:
    """The venue's own currency symbol, from restaurant settings.

    Money used to be printed with a hard-coded pound sign on every screen,
    which is simply the wrong currency for this restaurant. One setting, read
    once per page, and every figure agrees with the menu and the booking."""
    try:
        with db() as s:
            return canon.setting(s, "currency", "\u20bc")
    except Exception:
        return "\u20bc"


def staff_roster_for(scope: str) -> list[dict]:
    """Non-sensitive roster for login cards and staff identity UI.

    HR profile photos are merged here so an image uploaded in HR immediately
    becomes the employee's login/dashboard picture after the page is refreshed.
    PIN hashes and biometric credentials are never exposed.
    """
    allowed = {
        "waiter": {Role.WAITER, Role.BARTENDER},
        "admin": {Role.OWNER, Role.GENERAL_MANAGER, Role.RESTAURANT_MANAGER,
                  Role.HOST, Role.INVENTORY_MANAGER, Role.CASHIER, Role.KITCHEN},
    }.get(scope)
    with db() as s:
        rows = s.exec(select(Staff).order_by(Staff.role, Staff.name)).all()
        if allowed is not None:
            rows = [person for person in rows if person.role in allowed]

        profiles = {}
        try:
            from .enterprise_models import HRProfile
            profiles = {p.staff_id: p for p in s.exec(select(HRProfile)).all()}
        except Exception:
            try:
                from .enterprise_local_models import HRProfile
                profiles = {p.staff_id: p for p in s.exec(select(HRProfile)).all()}
            except Exception:
                profiles = {}

        out = []
        for person in rows:
            profile = profiles.get(person.id)
            # An employee HR has removed must not still be offered as a
            # sign-in profile — the account they were logged into is
            # invalidated at the moment of removal, but leaving them on
            # this roster would let a device that was never logged out
            # keep picking their card here forever.
            if profile is not None and getattr(profile, "status", "active") == "leaver":
                continue
            photo = str(getattr(profile, "photo_url", "") or "")
            out.append({
                "id": person.id, "name": person.name, "role": person.role.value,
                "avatar": person.avatar, "photo_url": photo,
                "section": person.section, "on_shift": person.on_shift,
            })
        return out


# ==================================================================== pages

def page(request: Request, name: str, **ctx):
    # Every server-rendered screen carries the venue's currency, so no template
    # or script has to hard-code a symbol.
    ctx.setdefault("currency", _currency())
    return templates.TemplateResponse(request, name, ctx)


@app.get("/")
def launcher(request: Request):
    """Pick an app: administration, waiter and guest, on one restaurant."""
    return page(request, "launcher.html")


# ---- admin app ----------------------------------------------------

ADMIN_PAGES = {
    "": ("command.html", "Command centre"),
    "operations": ("operations.html", "Live operations"),
    "floor": ("floor.html", "Floor"),
    "reservations": ("reservations.html", "Reservations"),
    "booking-control": ("booking_control.html", "Booking intelligence"),
    "orders": ("orders.html", "Orders"),
    "kitchen": ("kitchen.html", "Kitchen"),
    "menu": ("menu_admin.html", "Menu"),
    "inventory": ("inventory.html", "Inventory"),
    "anbar": ("anbar.html", "Warehouse"),
    "guests": ("guests.html", "Guests"),
    "staff": ("staff.html", "Staff"),
    "hr": ("hr.html", "HR & People"),
    "executive": ("executive.html", "Owner intelligence"),
    "analytics": ("analytics.html", "Analytics"),
    "finance": ("finance.html", "Finance"),
    "accounting": ("accounting.html", "Accounting"),
    "qr": ("qr.html", "Table QR ordering"),
    "suppliers": ("suppliers.html", "Suppliers"),
    "copilot": ("copilot.html", "AI Copilot"),
    "settings": ("settings.html", "Settings"),
}


@app.get("/admin")
@app.get("/admin/{section}")
def admin(request: Request, section: str = ""):
    if section not in ADMIN_PAGES:
        return JSONResponse({"error": f"No admin screen called '{section}'."}, 404)
    template, title = ADMIN_PAGES[section]
    return templates.TemplateResponse(
        request, f"admin/{template}", {
            "nav": section, "title": title,
            "staff_roster": staff_roster_for("admin"),
            "currency": _currency(),
        })


# ---- waiter app ---------------------------------------------------

@app.get("/waiter")
def waiter_app(request: Request):
    return page(request, "waiter/app.html", staff_roster=staff_roster_for("waiter"))


# ---- guest app ----------------------------------------------------

@app.get("/guest")
@app.get("/guest/{table_number}")
def guest_app(request: Request, table_number: int = 13):
    return page(request, "guest/app.html", table_number=table_number)


# Short QR-friendly link. A printed code says nova.app/t/12, nothing more.
@app.get("/t/{table_number}")
def qr_link(request: Request, table_number: int):
    return page(request, "guest/app.html", table_number=table_number)


# ==================================================================== KPIs

def kpis(s: Session) -> dict:
    today = date.today()
    start = datetime.combine(today, datetime.min.time())

    orders = s.exec(select(Order).where(
        Order.opened_at >= start, Order.paid == True  # noqa: E712
    )).all()
    order_ids = [o.id for o in orders]
    items = (s.exec(select(OrderItem).where(OrderItem.order_id.in_(order_ids))).all()
             if order_ids else [])
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}

    valid_items = [i for i in items if not i.void_reason and i.menu_item_id in menu]
    payment_total = s.exec(select(Payment).where(
        Payment.order_id.in_(order_ids))).all() if order_ids else []
    revenue = sum(p.amount for p in payment_total if p.amount > 0)
    food_cost = sum(menu[i.menu_item_id].food_cost * i.qty for i in valid_items)
    covers = sum(i.qty for i in valid_items if menu[i.menu_item_id].course == "Main")

    durations = [(o.closed_at - o.opened_at).total_seconds() / 60
                 for o in orders if o.closed_at]
    tables = [t for t in s.exec(select(DiningTable)).all() if t.zone != ARCHIVED_ZONE]
    busy = [t for t in tables if t.status != TableStatus.AVAILABLE]

    waste = s.exec(select(WasteLog).where(WasteLog.logged_on == today)).all()
    ings = {i.id: i for i in s.exec(select(Ingredient)).all()}
    waste_value = sum(w.qty * ings[w.ingredient_id].cost_per_unit
                      for w in waste if w.ingredient_id in ings)

    fb = s.exec(select(Feedback).where(Feedback.created_at >= start - timedelta(days=7))).all()
    sat = {k: round(20 * float(np.mean([getattr(f, k) for f in fb])), 1)
           for k in ("food", "service", "atmosphere", "speed")} if fb else {}

    open_tickets = s.exec(select(OrderItem).where(
        OrderItem.state.in_([ItemState.QUEUED, ItemState.COOKING]))).all()
    now = rtime.now()
    ticket_ages = [(now - t.fired_at).total_seconds() / 60 for t in open_tickets]

    return {
        "revenue": round(revenue, 2),
        "gross_margin": round(100 * (revenue - food_cost) / revenue, 1) if revenue else 0,
        "covers": covers,
        "spend_per_cover": round(revenue / covers, 2) if covers else 0,
        "occupancy": round(100 * len(busy) / len(tables)) if tables else 0,
        "tables_busy": len(busy),
        "tables_total": len(tables),
        "avg_duration": round(float(np.mean(durations))) if durations else 0,
        "waste_value": round(waste_value, 2),
        "satisfaction": round(float(np.mean(list(sat.values()))), 1) if sat else 0,
        "satisfaction_split": sat,
        "open_tickets": len(open_tickets),
        "oldest_ticket": round(max(ticket_ages)) if ticket_ages else 0,
        "clock": now.strftime("%H:%M"),
        "day": now.strftime("%A %-d %B"),
    }


def revenue_by_hour(s: Session) -> list[dict]:
    start = datetime.combine(date.today(), datetime.min.time())
    orders = {o.id: o for o in s.exec(select(Order).where(
        Order.opened_at >= start, Order.paid == True  # noqa: E712
    )).all()}
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    items = (s.exec(select(OrderItem).where(OrderItem.order_id.in_(list(orders)))).all()
             if orders else [])

    buckets: dict[int, float] = defaultdict(float)
    covers: dict[int, int] = defaultdict(int)
    payments = (s.exec(select(Payment).where(
        Payment.order_id.in_(list(orders)))).all() if orders else [])
    revenue_by_order = defaultdict(float)
    for payment in payments:
        if payment.amount > 0:
            revenue_by_order[payment.order_id] += payment.amount
    for order_id, order in orders.items():
        buckets[order.opened_at.hour] += revenue_by_order.get(order_id, 0.0)
    for i in items:
        o, m = orders.get(i.order_id), menu.get(i.menu_item_id)
        if not o or not m or i.void_reason:
            continue
        if m.course == "Main":
            covers[o.opened_at.hour] += i.qty
    hours = list(range(11, 24))
    return [{"hour": h, "revenue": round(buckets.get(h, 0.0), 2),
             "covers": covers.get(h, 0)} for h in hours]


def safe_reservation_overlay(s: Session, table_id: int, now: datetime):
    try:
        return sufra_upgrade.reservation_overlay(s, table_id, now)
    except Exception as exc:
        # A booking-label failure must never take down the operational floor.
        try:
            log = BASE.parent / "sufra_server_errors.log"
            with log.open("a", encoding="utf-8") as fh:
                fh.write(f"\n[{rtime.now().isoformat()}] reservation overlay table {table_id}: {exc}\n")
        except Exception:
            pass
        return None


def table_payload(s: Session) -> list[dict]:
    now = rtime.now()
    waiters = {w.id: w for w in s.exec(select(Staff)).all()}
    guests = {g.id: g for g in s.exec(select(Guest)).all()}
    tasks: dict[int, list[Task]] = defaultdict(list)
    for t in s.exec(select(Task).where(Task.done == False)).all():  # noqa: E712
        tasks[t.table_id].append(t)

    orders = s.exec(select(Order).where(Order.paid == False)).all()  # noqa: E712
    menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
    spend: dict[int, float] = defaultdict(float)
    for o in orders:
        for i in s.exec(select(OrderItem).where(OrderItem.order_id == o.id)).all():
            if i.menu_item_id in menu:
                spend[o.table_id] += menu[i.menu_item_id].price * i.qty

    out = []
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if t.zone == ARCHIVED_ZONE:
            continue
        g = guests.get(t.guest_id) if t.guest_id else None
        waited = ((now - t.last_touched_at).total_seconds() / 60
                  if t.last_touched_at else 0)
        limit = ai.SERVICE_LIMITS.get(t.status)
        out.append({
            "id": t.id, "number": t.number, "seats": t.seats, "zone": t.zone,
            "x": t.x, "y": t.y, "shape": t.shape, "status": t.status.value,
            "party": t.party_size,
            "waiter": waiters[t.waiter_id].name.split()[0] if t.waiter_id in waiters else "—",
            "minutes": round(waited),
            "seated_minutes": round((now - t.seated_at).total_seconds() / 60) if t.seated_at else 0,
            "spend": round(spend.get(t.id, 0.0), 2),
            "alert": bool(limit and waited > limit),
            "reservation": safe_reservation_overlay(s, t.id, now),
            "guest": ({"name": g.name, "vip": g.vip, "visits": g.visits,
                       "allergies": g.allergies, "likes": g.likes,
                       "pref": g.seating_pref, "note": g.note} if g else None),
            "tasks": [{"id": k.id, "kind": k.kind.value, "message": k.message,
                       "priority": k.priority,
                       "minutes": round((now - k.created_at).total_seconds() / 60)}
                      for k in sorted(tasks.get(t.id, []), key=lambda x: x.priority)],
        })
    return out


# ==================================================================== API

@app.get("/api/snapshot")
def api_snapshot():
    with db() as s:
        return {
            "kpis": kpis(s),
            "tables": table_payload(s),
            "insights": [i.dict() for i in ai.build_insights(s)],
            "stations": ai.station_pressure(s),
            "revenue_curve": revenue_by_hour(s),
            "forecast": ai.forecast_day(s),
        }


@app.get("/api/floor")
def api_floor():
    with db() as s:
        return {"tables": table_payload(s), "kpis": kpis(s)}


@app.get("/api/kitchen")
def api_kitchen():
    with db() as s:
        now = rtime.now()
        menu = {m.id: m for m in s.exec(select(MenuItem)).all()}
        tables = {t.id: t for t in s.exec(select(DiningTable)).all()}
        orders = {o.id: o for o in s.exec(select(Order)).all()}
        items = s.exec(select(OrderItem).where(OrderItem.state.in_(
            [ItemState.QUEUED, ItemState.COOKING, ItemState.READY]))).all()

        rail: dict[str, list] = defaultdict(list)
        for i in items:
            if i.void_reason:
                continue
            m, o = menu.get(i.menu_item_id), orders.get(i.order_id)
            if not m or not o:
                continue
            elapsed = (now - i.fired_at).total_seconds() / 60
            rail[i.station.value].append({
                "id": i.id, "dish": m.name, "qty": i.qty, "state": i.state.value,
                "table": tables[o.table_id].number if o.table_id in tables else "—",
                "elapsed": round(elapsed, 1),
                "promised": i.promised_minutes,
                "pressure": round(min(1.4, elapsed / max(1, i.promised_minutes)), 2),
                "allergens": m.tags, "note": i.note,
            })
        for station in rail:
            rail[station].sort(key=lambda t: -t["pressure"])
        return {"rail": rail, "stations": ai.station_pressure(s),
                "kpis": kpis(s)}


@app.get("/api/pass")
def api_pass():
    with db() as s:
        rows = table_payload(s)
        tasks = []
        for t in rows:
            for k in t["tasks"]:
                tasks.append({**k, "table": t["number"], "table_id": t["id"],
                              "zone": t["zone"]})
        # Anything left too long gets promoted, so nothing quietly rots.
        for k in tasks:
            if k["minutes"] > 5:
                k["priority"] = 1
        tasks.sort(key=lambda k: (k["priority"], -k["minutes"]))
        return {"tasks": tasks, "tables": rows, "kpis": kpis(s)}


@app.get("/api/insights")
def api_insights():
    with db() as s:
        return {"insights": [i.dict() for i in ai.build_insights(s)]}


@app.get("/api/forecast")
def api_forecast(days: int = 0, rain: float = 1.2, temp: float = 18.0,
                 holiday: bool = False, event: bool = False):
    with db() as s:
        return ai.forecast_day(s, date.today() + timedelta(days=days),
                               rain_mm=rain, temp_c=temp,
                               is_holiday=holiday, local_event=event)


@app.get("/api/inventory")
def api_inventory():
    with db() as s:
        outlook = {r["id"]: r for r in ai.inventory_outlook(s)}
        rows = []
        for i in s.exec(select(Ingredient)).all():
            o = outlook.get(i.id, {})
            rows.append({
                "id": i.id, "name": i.name, "unit": i.unit,
                "in_stock": round(i.in_stock, 2), "par": i.par_level,
                "supplier": i.supplier, "store": i.store,
                "cost": i.cost_per_unit,
                "required": o.get("required", 0.0),
                "shortfall": o.get("shortfall", 0.0),
                "order_qty": o.get("order_qty", 0.0),
                "days_cover": o.get("days_cover", 99),
                "status": o.get("status", "ok"),
            })
        rows.sort(key=lambda r: (-r["shortfall"], r["days_cover"]))
        basket = [r for r in rows if r["order_qty"] > 0]
        return {"rows": rows, "basket": basket,
                "basket_value": round(sum(r["order_qty"] * r["cost"] for r in basket), 2)}


@app.get("/api/menu-engineering")
def api_menu_engineering():
    with db() as s:
        return {"items": ai.menu_engineering(s)}


@app.get("/api/reservations")
def api_reservations():
    with db() as s:
        guests = {g.id: g for g in s.exec(select(Guest)).all()}
        rows = []
        for r in s.exec(select(Reservation).where(
                Reservation.starts_at >= rtime.now() - timedelta(hours=2),
                Reservation.starts_at <= rtime.now() + timedelta(hours=8)
        ).order_by(Reservation.starts_at)).all():
            g = guests.get(r.guest_id)
            rows.append({
                "id": r.id, "time": r.starts_at.strftime("%H:%M"),
                "party": r.party_size, "status": r.status, "occasion": r.occasion,
                "guest": g.name if g else "Walk-in",
                "vip": bool(g and g.vip), "visits": g.visits if g else 0,
                "allergies": g.allergies if g else "",
                "note": r.note or (g.note if g else ""),
                "risk": ai.no_show_risk(s, r),
            })
        return {"reservations": rows}


@app.get("/api/menu")
def api_menu():
    """Guest/waiter menu with availability, localized copy and photographs."""
    with db() as s:
        pressure = {p["station"]: p["load_now"] for p in ai.station_pressure(s)}
        blocked, block_reasons = unavailable_menu_ids(s)
        archived = archived_menu_ids(s)
        content = {c.menu_item_id: c for c in s.exec(select(MenuContent)).all()}
        out = []
        for m in s.exec(select(MenuItem)).all():
            if m.id in archived:
                continue
            queue = round(pressure.get(m.station.value, 0) * 8)
            low, high = ai.predict_prep_time(s, m, queue)
            c = content.get(m.id)
            # Local-only fallback: admins may upload a real dish photo.
            auto_photo = "/static/img/dish-placeholder.svg"
            out.append({
                "id": m.id, "name": m.name, "course": m.course, "price": m.price,
                "blurb": m.blurb, "tags": [t for t in m.tags.split(",") if t],
                "protein": m.protein_g, "kcal": m.kcal,
                "available": bool(m.available and m.id not in blocked),
                "unavailable_reason": block_reasons.get(m.id, ""),
                "wait": f"{low}–{high}", "station": m.station.value,
                "popularity": m.sold_30d, "hue": m.hue, "signature": m.signature,
                "image_url": (c.image_url if c and c.image_url else auto_photo),
                "image_source": (c.image_source if c else "auto"),
                "name_i18n": {
                    "en": m.name,
                    "az": (c.name_az if c and c.name_az else m.name),
                    "ru": (c.name_ru if c and c.name_ru else m.name),
                },
                "blurb_i18n": {
                    "en": m.blurb,
                    "az": (c.blurb_az if c and c.blurb_az else m.blurb),
                    "ru": (c.blurb_ru if c and c.blurb_ru else m.blurb),
                },
            })
        out.sort(key=lambda d: -d["popularity"])
        rows = s.exec(select(MenuSection).where(MenuSection.active == True)
                      .order_by(MenuSection.sort_order, MenuSection.name)).all()
        known = {r.name for r in rows}
        extra = sorted({d["course"] for d in out if d["course"] not in known})
        sections = [{"id": r.name, "name": r.name, "name_az": r.name_az, "name_ru": r.name_ru,
                     "sort_order": r.sort_order} for r in rows]
        sections += [{"id": c, "name": c, "name_az": "", "name_ru": "", "sort_order": 999}
                     for c in extra]
        return {"items": out, "sections": sections}

@app.post("/api/i18n/translate")
def api_translate(body: dict = Body(...)):
    """Online translation helper for staff-entered menu copy — dish names,
    descriptions, and now menu section names — into Azerbaijani or Russian.

    Every free translation API has a small daily quota that is shared
    across every caller on this network, not per SUFRA install — one busy
    afternoon of switching the dashboard between EN/AZ/RU can burn through
    a whole day's MyMemory allowance, since the site-wide live-UI
    translator asks for every visible phrase individually. A
    TranslationCache row is checked FIRST and, on a hit, answers instantly
    without touching either provider — so quota is only ever spent once
    per distinct phrase, forever, across every browser and every device
    this restaurant uses. Everything that gets a real translation below is
    written to that cache before it is returned.

    Tries two independent public services in turn (MyMemory, then Google's
    unofficial endpoint) and only reports translated: true when one of them
    actually returned different text. Both enforce daily/IP quotas with no
    advance warning — MyMemory returns its warning sentence AS the
    "translation" once exhausted, and Google returns an HTML "automated
    queries" block page instead of JSON — so a truthful attempt here means
    detecting those failure shapes explicitly rather than trusting "the
    response differs from the input". When BOTH fail this returns the
    English text UNCHANGED with translated: false, and the admin UI is
    required to surface that rather than silently accepting English text
    as if it had been translated.
    """
    text = str(body.get("text") or "").strip()
    target = str(body.get("target") or "").lower()
    source = str(body.get("source") or "en").lower()
    # Callers such as the site-wide live-UI translator send source:"auto" —
    # MyMemory has no "auto" detection and instead returns an error string
    # ("'AUTO' IS AN INVALID SOURCE LANGUAGE...") as if it were the
    # translatedText, which a naive "differs from input" check would accept
    # as a real translation. Every string in the app is EN-authored, so
    # anything other than a genuine az/ru/en source just means "en".
    if source not in {"az", "ru", "en"}:
        source = "en"
    if not text or target not in {"az", "ru", "en"}:
        return {"text": text, "translated": False}
    if target == source:
        return {"text": text, "translated": True}

    with db() as s:
        cached = s.exec(
            select(TranslationCache).where(
                TranslationCache.source_lang == source,
                TranslationCache.target_lang == target,
                TranslationCache.source_text == text,
            )
        ).first()
        if cached:
            return {"text": cached.translated_text, "translated": True, "via": "cache"}

    def remember(translated_text: str) -> None:
        with db() as s:
            s.add(TranslationCache(source_lang=source, target_lang=target,
                                    source_text=text, translated_text=translated_text))
            s.commit()

    # 1. MyMemory — a free, keyless translation API. No account needed for
    #    restaurant-menu volumes (a few thousand words a day).
    try:
        q = urllib.parse.urlencode({"q": text, "langpair": f"{source}|{target}"})
        req = urllib.request.Request(
            "https://api.mymemory.translated.net/get?" + q,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with netutil.urlopen(req, timeout=6) as r:
            payload = json.loads(r.read().decode("utf-8"))
        data = payload.get("responseData") or {}
        translated = data.get("translatedText", "")
        status = payload.get("responseStatus")
        # A non-200 responseStatus (or a match quality of 0 with an
        # all-caps error sentence) means MyMemory rejected the request —
        # the error TEXT still lands in translatedText, so it must be
        # rejected explicitly rather than treated as a translation just
        # because it differs from the input.
        looks_like_error = (
            translated.strip().startswith("'") or
            "INVALID SOURCE LANGUAGE" in translated.upper() or
            "INVALID TARGET LANGUAGE" in translated.upper() or
            "MYMEMORY WARNING" in translated.upper()
        )
        if (
            translated and not looks_like_error and
            (status is None or status in (200, "200")) and
            translated.strip().lower() != text.strip().lower()
        ):
            remember(translated)
            return {"text": translated, "translated": True, "via": "mymemory"}
    except Exception:
        pass

    # 2. Google's unofficial gtx endpoint, as a second attempt.
    try:
        q = urllib.parse.urlencode({
            "client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text
        })
        req = urllib.request.Request(
            "https://translate.googleapis.com/translate_a/single?" + q,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with netutil.urlopen(req, timeout=3.5) as r:
            raw = r.read().decode("utf-8")
        # Google returns an HTML "Sorry... automated queries" block page
        # instead of JSON once it decides this IP is a bot — json.loads on
        # that raises and is already caught below, but be explicit about it
        # so a future change to this endpoint can't accidentally treat HTML
        # as a translation.
        if raw.lstrip().startswith("<"):
            raise ValueError("blocked: got an HTML page instead of JSON")
        payload = json.loads(raw)
        translated = "".join(x[0] for x in (payload[0] or []) if x and x[0])
        if translated and translated.strip().lower() != text.strip().lower():
            remember(translated)
            return {"text": translated, "translated": True, "via": "google"}
    except Exception:
        pass

    return {"text": text, "translated": False}


@app.post("/api/menu/ask")
def api_menu_ask(body: dict = Body(...)):
    """
    The guest-side menu assistant. Scores dishes against what was asked,
    so the reason it gives is the reason it actually used.
    """
    q = (body.get("question") or "").lower()
    with db() as s:
        items = s.exec(select(MenuItem).where(MenuItem.available == True)).all()  # noqa: E712
        blocked, _ = unavailable_menu_ids(s)
        items = [m for m in items if m.id not in blocked]

        wants_light = any(w in q for w in ("light", "not heavy", "small", "fresh"))
        wants_protein = any(w in q for w in ("protein", "gym", "filling", "hearty"))
        strictly_vegan = "vegan" in q
        wants_veg = strictly_vegan or any(w in q for w in ("vegetarian", "plant", "veggie"))
        wants_gf = any(w in q for w in ("gluten", "coeliac", "celiac", "gf"))
        wants_halal = "halal" in q
        avoid_nuts = any(w in q for w in ("nut", "allerg"))
        wants_wine = any(w in q for w in ("wine", "pair", "pairing", "goes with"))
        wants_drink = wants_wine or any(w in q for w in ("drink", "cocktail", "aperitif"))
        wants_quick = any(w in q for w in ("quick", "fast", "hurry", "in a rush"))

        # Which part of the menu are they asking about?
        course_words = {
            "Main": ("main", "mains", "dinner", "entree"),
            "Starter": ("starter", "starters", "appetiser", "appetizer", "first course"),
            "Dessert": ("dessert", "pudding", "sweet", "afters"),
            "Side": ("side", "sides"),
            "Snack": ("snack", "nibble", "bar snack"),
            "Drink": ("drink", "wine", "cocktail", "aperitif"),
        }
        asked_course = next((c for c, words in course_words.items()
                             if any(w in q for w in words)), None)

        # Pairing: match the wine to what is on the plate, not to the price list.
        red_dishes = ("beef", "ribeye", "steak", "lamb", "duck", "truffle", "mushroom")
        white_dishes = ("bass", "sole", "turbot", "fish", "scallop", "tuna", "oyster",
                        "lobster", "crab", "chicken", "risotto", "cauliflower", "salad")
        pair_colour = ("red" if any(w in q for w in red_dishes) else
                       "white" if any(w in q for w in white_dishes) else None)

        scored = []
        for m in items:
            tags = set(m.tags.split(","))
            # "Vegan" means vegan. A parmesan risotto is not an acceptable
            # answer to that question, and getting it wrong is a real problem
            # for the guest, not a ranking miss.
            if strictly_vegan and "vegan" not in tags:
                continue
            if wants_veg and not ({"vegan", "vegetarian"} & tags):
                continue
            if wants_gf and "gf" not in tags:
                continue
            if wants_halal and m.course == "Main" and "halal" not in tags:
                continue
            if avoid_nuts and "nuts" in tags:
                continue
            if asked_course and m.course != asked_course:
                continue
            if wants_wine and "wine" not in tags:
                continue
            # Without a drinks question, don't answer a food question with coffee.
            if not wants_drink and not asked_course and m.course == "Drink":
                continue

            # "Light" is a constraint, not a preference. A 900-calorie turbot
            # is not a light dish however much protein it carries, so it is
            # excluded outright rather than out-scored.
            if wants_light and m.kcal > 520:
                continue
            # Asking for protein rules out garnishes. Six oysters are light,
            # but nobody asking for protein means four grams of it.
            if wants_protein and m.protein_g < 15:
                continue

            score, why = 0.0, []
            if wants_light and m.kcal:
                score += (600 - m.kcal) / 80
                why.append(f"{m.kcal} kcal")
            if wants_protein:
                # Protein per 100 kcal when lightness also matters, so the
                # answer is efficient protein rather than the biggest plate.
                score += (m.protein_g / max(m.kcal, 1) * 100 * 1.4
                          if wants_light else m.protein_g / 6)
                why.append(f"{m.protein_g}g protein")
            if wants_quick:
                score += (30 - m.base_minutes) / 4
                why.append(f"about {m.base_minutes} minutes")
            if pair_colour:
                if pair_colour in tags:
                    score += 12
                    why.append(f"a {pair_colour} that stands up to it")
                else:
                    score -= 6
            score += m.sold_30d / 60
            scored.append((score, m, why))

        scored.sort(key=lambda x: -x[0])
        picks = scored[:3]
        if not picks:
            return {"answer": "Nothing on tonight's menu fits that. Ask the floor and "
                              "the kitchen will usually build something.",
                    "picks": []}

        lead = picks[0][1]
        reason = ", ".join(picks[0][2]) or f"the kitchen sells {lead.sold_30d} a month"
        return {
            "answer": f"The {lead.name} — {reason}. {lead.blurb}",
            "picks": [{"id": m.id, "name": m.name, "price": m.price,
                       "blurb": m.blurb, "why": ", ".join(w) or "a house favourite",
                       "tags": [t for t in m.tags.split(",") if t]}
                      for _, m, w in picks],
        }


@app.post("/api/copilot")
def api_copilot(body: dict = Body(...)):
    with db() as s:
        return ai.copilot(s, body.get("question", ""))


# ------------------------------------------------------------------ actions

@app.post("/api/tables/{table_id}/status")
async def set_status(table_id: int, body: dict = Body(...),
                     actor=Depends(require_permission("can_set_table_state"))):
    """Occupied / free / any service state, from the floor plan or a tablet.

    This is PHYSICAL table state. It changes the live room in both SUFRA OS
    and SUFRA 360 immediately, and it never touches future availability: a
    table freed now is still protected for tonight's 21:00 booking.
    """
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "no such table"}, 404)
        try:
            wanted = TableStatus(str(body.get("status") or "").strip().lower())
        except ValueError:
            return JSONResponse({"error": "Choose a valid table status."}, 400)
        before = t.status
        t.status = wanted
        touch(t)
        if t.status == TableStatus.AVAILABLE:
            t.party_size, t.guest_id, t.seated_at = 0, None, None
            close_tasks(s, t.id)
        elif t.status == TableStatus.SEATED and not t.seated_at:
            t.seated_at = rtime.now()
            if body.get("party"):
                try:
                    t.party_size = max(1, min(t.seats, int(body["party"])))
                except (TypeError, ValueError):
                    pass
        s.add(t)
        # Seating or freeing a table also moves the booking sitting on it, so
        # the book and the room can never tell two different stories.
        linked = _reservation_on(s, t)
        if linked is not None:
            if wanted == TableStatus.SEATED and linked.status in ("confirmed", "late"):
                linked.status = "seated"
                linked.seated_at = rtime.now()
                linked.updated_at = rtime.now()
                s.add(linked)
                from .bookings import carry_allergies_to_table
                carry_allergies_to_table(s, linked, t)
            elif wanted == TableStatus.AVAILABLE and linked.status == "seated":
                linked.status = "completed"
                linked.completed_at = linked.left_at = rtime.now()
                linked.updated_at = rtime.now()
                s.add(linked)
        if before != wanted:
            title = ("Table marked occupied" if wanted in av.OCCUPIED_TABLE_STATUSES
                     else "Table marked free" if wanted == TableStatus.AVAILABLE
                     else "Table status changed")
            events.record(s, "table_status", title,
                          detail=wanted.value.replace("_", " "),
                          table_id=t.id, table_number=t.number,
                          reservation_id=linked.id if linked is not None else None,
                          actor=getattr(actor, "name", "Floor"),
                          severity="good" if wanted == TableStatus.AVAILABLE else "note")
        s.commit()
    await hub.send("state", {"changed": ["status"]})
    return {"ok": True}


def _reservation_on(s: Session, table: DiningTable):
    """The booking attached to this table right now.

    A party that has been marked seated owns the table until it is freed,
    whatever hour the booking was for. Otherwise this is the arrival closest
    to now, so seating a table also seats the booking that was expecting it.
    """
    from .bookings import seated_reservation_on
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



@app.post("/api/tables/{table_id}/move")
async def move_table(table_id: int, body: dict = Body(...)):
    with db() as s:
        t = s.get(DiningTable, table_id)
        if not t:
            return JSONResponse({"error": "no such table"}, 404)
        t.x = max(0.03, min(0.97, float(body["x"])))
        t.y = max(0.04, min(0.96, float(body["y"])))
        s.add(t)
        s.commit()
    await hub.send("state", {"changed": ["moved"]})
    return {"ok": True}


@app.post("/api/tasks/{task_id}/done")
async def finish_task(task_id: int):
    with db() as s:
        task = s.get(Task, task_id)
        if not task:
            return JSONResponse({"error": "no such task"}, 404)
        task.done = True
        s.add(task)
        t = s.get(DiningTable, task.table_id)
        if t:
            touch(t)
            if t.status == TableStatus.NEEDS_WAITER:
                t.status = TableStatus.DINING
            elif t.status == TableStatus.CLEANING and task.kind == TaskKind.CLEAR:
                t.status = TableStatus.AVAILABLE
                t.party_size, t.guest_id, t.seated_at = 0, None, None
            s.add(t)
            for n in s.exec(select(Notification).where(Notification.read == False)).all():  # noqa: E712
                if n.title.startswith(f"Table {t.number}:"):
                    n.read = True
                    s.add(n)
        s.commit()
    await hub.send("state", {"changed": ["task"]})
    return {"ok": True}


@app.post("/api/items/{item_id}/advance")
async def advance_item(item_id: int, actor=Depends(require_permission("can_manage_menu"))):
    """Kitchen taps a ticket: queued -> cooking -> ready -> served."""
    order = [ItemState.QUEUED, ItemState.COOKING, ItemState.READY, ItemState.SERVED]
    with db() as s:
        i = s.get(OrderItem, item_id)
        if not i:
            return JSONResponse({"error": "no such item"}, 404)
        idx = order.index(i.state)
        i.state = order[min(idx + 1, 3)]
        if i.state == ItemState.READY:
            i.ready_at = rtime.now()
            o = s.get(Order, i.order_id)
            t = s.get(DiningTable, o.table_id) if o else None
            if t:
                open_task(s, t, TaskKind.RUNNER,
                          f"Food ready at the pass for table {t.number}", 1)
        s.add(i)
        s.flush()
        from . import anbar
        anbar.consume_order(s, i.order_id, staff=actor, only_item_id=i.id)
        s.commit()
    await hub.send("state", {"changed": ["ticket"]})
    return {"ok": True}


@app.post("/api/guest/{table_number}/request")
async def guest_request(table_number: int, body: dict = Body(...)):
    """Guest taps a button on the QR menu. It lands on the floor in seconds."""
    kind = TaskKind(body.get("kind", "call"))
    label = {"call": "asked for a waiter", "water": "asked for still water",
             "cutlery": "needs cutlery", "bill": "asked for the bill"}[kind.value]
    with db() as s:
        t = s.exec(select(DiningTable).where(DiningTable.number == table_number)).first()
        if not t:
            return JSONResponse({"error": "no such table"}, 404)
        open_task(s, t, kind, f"Table {t.number} {label}", 1)
        if kind == TaskKind.BILL:
            t.status = TableStatus.BILL
        elif t.status in (TableStatus.DINING, TableStatus.SEATED):
            t.status = TableStatus.NEEDS_WAITER
        touch(t)
        s.add(t)
        level = "critical" if kind in (TaskKind.BILL, TaskKind.CALL) else "warning"
        s.add(Notification(level=level, title=f"Table {t.number}: {label}",
                           body=f"{t.zone} · assigned waiter request", audience="manager"))
        s.commit()
    await hub.send("state", {"changed": ["guest-request"]})
    return {"ok": True, "message": label}


@app.post("/api/guest/{table_number}/order")
async def guest_order(table_number: int, body: dict = Body(...)):
    """Guest sends their basket. Items are routed to stations immediately."""
    lines = body.get("items", [])
    with db() as s:
        t = s.exec(select(DiningTable).where(DiningTable.number == table_number)).first()
        if not t or not lines:
            return JSONResponse({"error": "nothing to send"}, 400)

        # A guest ordering for themselves gets a hard stop, not a warning they
        # can wave through: there is no waiter at the screen to take
        # responsibility for the override, so the answer is "speak to us".
        wanted = []
        for line in lines:
            try:
                wanted.append(int(line.get("id") or 0))
            except (AttributeError, TypeError, ValueError):
                continue
        # A guest may still order a dish that clashes with what this table
        # declared — it is their meal. What must never happen is the kitchen
        # cooking it without knowing, so every affected line goes to the pass
        # stamped with the reason, and a waiter is paged to the table.
        check = allergens.screen(s, t.id, wanted)
        allergen_note = {}
        for c in check["conflicts"]:
            stamp = "ALLERGY: %s declared %s — this dish %s" % (
                c["declared_by"], c["allergen"], c["evidence"])
            prev = allergen_note.get(c["menu_item_id"], "")
            allergen_note[c["menu_item_id"]] = (prev + " · " + stamp) if prev else stamp

        order = s.exec(select(Order).where(
            Order.table_id == t.id, Order.paid == False)).first()  # noqa: E712
        if not order:
            order = Order(table_id=t.id, waiter_id=t.waiter_id)
            s.add(order)
            s.commit()
            s.refresh(order)

        pressure = {p["station"]: p["now"] for p in ai.station_pressure(s)}
        longest = 0
        for line in lines:
            m = s.get(MenuItem, int(line["id"]))
            if not m:
                continue
            qty = max(1, int(line.get("qty", 1)))
            queue = pressure.get(m.station.value, 0)
            low, high = ai.predict_prep_time(s, m, queue)
            longest = max(longest, high)
            guest_note = str(line.get("note") or "")
            if m.id in allergen_note:
                guest_note = allergen_note[m.id] + (" · " + guest_note if guest_note else "")
            s.add(OrderItem(order_id=order.id, menu_item_id=m.id, qty=qty,
                            station=m.station, note=guest_note,
                            promised_minutes=high))
            pressure[m.station.value] = queue + qty
        if check["conflicts"]:
            open_task(s, t, TaskKind.CALL,
                      "Table %d ordered %s against a declared %s allergy"
                      % (t.number, check["conflicts"][0]["dish"],
                         check["conflicts"][0]["allergen"]), 1)
            events.record(s, "allergen_ordered", "Allergy warning on a guest order",
                          detail=allergens.sentence(check["conflicts"]),
                          table_id=t.id, table_number=t.number,
                          actor="Guest", source="guest", severity="critical")
        if t.status in (TableStatus.SEATED, TableStatus.ORDERING,
                        TableStatus.AVAILABLE, TableStatus.DINING):
            t.status = TableStatus.COOKING
            if not t.seated_at:
                t.seated_at = rtime.now()
                t.party_size = t.party_size or 2
        touch(t)
        s.add(t)
        s.commit()
    await hub.send("state", {"changed": ["order"]})
    return {"ok": True, "eta": longest}


@app.post("/api/feedback/{table_number}")
async def leave_feedback(table_number: int, body: dict = Body(...)):
    ratings = {}
    for field in ("food", "service", "atmosphere", "speed"):
        try:
            value = int(body.get(field, 5))
        except (TypeError, ValueError):
            return JSONResponse({"error": f"{field.title()} rating must be a number."}, 400)
        if not 1 <= value <= 5:
            return JSONResponse({"error": f"{field.title()} rating must be between 1 and 5."}, 400)
        ratings[field] = value
    comment = str(body.get("comment") or "").strip()
    if len(comment) > 2000:
        return JSONResponse({"error": "Feedback is too long."}, 400)
    with db() as s:
        s.add(Feedback(table_id=table_number,
                       **ratings, comment=comment))
        s.commit()
    return {"ok": True}


@app.post("/api/reset")
async def reset_demo(_=Depends(require_permission("can_manage_permissions"))):
    """Rebuild the demo restaurant from scratch."""
    if os.getenv("NOVA_ALLOW_DEMO_RESET", "").lower() not in {"1", "true", "yes", "on"}:
        return JSONResponse({"error": "Demo reset is disabled."}, status_code=403)
    from .seed import build
    build()
    await hub.send("state", {"changed": ["reset"]})
    return {"ok": True}


# ============================================================ public API
#
# SUFRA 360 is the customer-facing 3D application. It reads and writes the
# restaurant through app/routers/public_v2.py, against these same tables -
# there is no second reservation store, table list, waitlist or menu. The
# endpoints that used to live here have moved there so one module owns the
# whole contract; see canon.py for the canonical table registry.

# ==================================================================== socket

@app.websocket("/ws")
async def socket(ws: WebSocket):
    await hub.join(ws)
    try:
        while True:
            await ws.receive_text()      # keepalive; the server does the talking
    except WebSocketDisconnect:
        hub.leave(ws)
    except Exception:
        hub.leave(ws)
