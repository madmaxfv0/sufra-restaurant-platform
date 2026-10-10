"""Canonical restaurant state: schema, settings and the one table registry.

SUFRA OS owns the restaurant. SUFRA 360 renders it. Both read and write the
same nova.db, so this module is the only place that decides what a table,
a reservation or a venue setting actually is.

Everything here is additive against an existing database: new columns are
added with ALTER TABLE when missing, new tables by SQLModel.create_all.
No reservation, guest, menu row or booking history is ever rewritten.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from sqlmodel import Session, SQLModel, select

from .database import DB_PATH, IS_SQLITE, engine
from .models import DiningTable, RestaurantSetting, TableProfile
from . import rtime

BASE = Path(__file__).resolve().parent
ARCHIVED_ZONE = "__ARCHIVED__"

# The 3D scene's own geometry file. Read once to seed the canonical table
# registry; after that the database is the source of truth and this file is
# only re-read to pick up genuinely new tables.
VENUE_DIR = Path(os.getenv(
    "SUFRA_360_VENUE",
    str(BASE.parent.parent / "sufra-360" / "venue")))

# scene area -> the operational zone the floor plan and the seating engine use
AREA_TO_ZONE = {
    "garden": "Terrace", "lounge": "Terrace", "terrace": "Terrace",
    "window": "Main", "east": "Main", "main": "Main",
    "bar": "Bar", "private": "Private",
}

DEFAULT_SETTINGS = {
    "restaurant_name": "SUFRA Waterfront",
    "restaurant_tagline": "Seaside kitchen & garden room",
    "timezone": rtime.TZ_NAME,
    "currency": "₼",
    "phone": "+994 12 000 00 00",
    "email": "reservations@sufra.az",
    "address": "Baku Boulevard, Baku, Azerbaijan",
    "latitude": "40.4093",
    "longitude": "49.8671",
    "open": "12:00",
    "last_seating": "22:30",
    "close": "23:30",
    "slot_minutes": "15",
    "default_duration": "105",
    "turnover_buffer": "15",
    "hold_seconds": "300",
    "grace_minutes": "30",          # no-show policy
    "reminder_minutes": "15",       # T-15 confirmation nudge
    "max_party": "20",
}


# ------------------------------------------------------------------ schema

RESERVATION_COLUMNS = [
    ("code", "TEXT NOT NULL DEFAULT ''"),
    ("first_name", "TEXT NOT NULL DEFAULT ''"),
    ("last_name", "TEXT NOT NULL DEFAULT ''"),
    ("email", "TEXT NOT NULL DEFAULT ''"),
    ("phone", "TEXT NOT NULL DEFAULT ''"),
    ("allergies", "TEXT NOT NULL DEFAULT ''"),
    ("dietary", "TEXT NOT NULL DEFAULT ''"),
    ("accessibility", "TEXT NOT NULL DEFAULT ''"),
    ("high_chairs", "INTEGER NOT NULL DEFAULT 0"),
    ("special_request", "TEXT NOT NULL DEFAULT ''"),
    ("preference", "TEXT NOT NULL DEFAULT ''"),
    ("language", "TEXT NOT NULL DEFAULT 'en'"),
    ("marketing_opt_in", "INTEGER NOT NULL DEFAULT 0"),
    ("guest_confirmation_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("guest_confirmed_at", "DATETIME"),
    ("confirm_token", "TEXT NOT NULL DEFAULT ''"),
    ("reminder_sent_at", "DATETIME"),
    ("late_notified_at", "DATETIME"),
    ("seated_at", "DATETIME"),
    ("completed_at", "DATETIME"),
    ("cancelled_at", "DATETIME"),
    ("no_show_at", "DATETIME"),
    ("updated_at", "DATETIME"),
    ("idempotency_key", "TEXT NOT NULL DEFAULT ''"),
    # A booking the restaurant did not take itself needs somebody to say yes.
    ("staff_decision", "TEXT NOT NULL DEFAULT ''"),
    ("decided_at", "DATETIME"),
    ("decided_by", "TEXT NOT NULL DEFAULT ''"),
    ("decline_reason", "TEXT NOT NULL DEFAULT ''"),
]

WAITLIST_COLUMNS = [
    ("email", "TEXT NOT NULL DEFAULT ''"),
    ("desired_at", "DATETIME"),
    ("area_pref", "TEXT NOT NULL DEFAULT ''"),
    ("source", "TEXT NOT NULL DEFAULT 'walk-in'"),
    ("language", "TEXT NOT NULL DEFAULT 'en'"),
    ("converted_reservation_id", "INTEGER"),
]

MENU_SECTION_COLUMNS = [
    ("name_az", "TEXT NOT NULL DEFAULT ''"),
    ("name_ru", "TEXT NOT NULL DEFAULT ''"),
]


def ensure_schema() -> None:
    """Idempotent migration. Safe to run on every boot."""
    SQLModel.metadata.create_all(engine)
    if not IS_SQLITE:
        return
    con = sqlite3.connect(str(DB_PATH))
    try:
        def cols(table: str) -> set[str]:
            return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}

        for table, spec in (("reservation", RESERVATION_COLUMNS),
                            ("waitlistentry", WAITLIST_COLUMNS),
                            ("menusection", MENU_SECTION_COLUMNS)):
            present = cols(table)
            for name, ddl in spec:
                if name not in present:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        con.execute("CREATE INDEX IF NOT EXISTS ix_res_table_start "
                    "ON reservation(table_id, starts_at)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_res_code ON reservation(code)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_hold_table ON tablehold(table_id, status)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_liveevent_at ON liveevent(id)")
        con.commit()
    finally:
        con.close()
    _seed_settings()
    backfill_reservation_identity()
    seed_menu_sections()


def _seed_settings() -> None:
    with Session(engine, expire_on_commit=False) as s:
        have = {r.key for r in s.exec(select(RestaurantSetting)).all()}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in have:
                s.add(RestaurantSetting(key=key, value=value))
        s.commit()


# ---------------------------------------------------------------- settings

def settings(s: Session) -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in s.exec(select(RestaurantSetting)).all():
        if row.value != "":
            out[row.key] = row.value
    return out


def setting(s: Session, key: str, default: str = "") -> str:
    row = s.get(RestaurantSetting, key)
    return row.value if row and row.value != "" else DEFAULT_SETTINGS.get(key, default)


def int_setting(s: Session, key: str, default: int) -> int:
    try:
        return int(float(setting(s, key, str(default))))
    except (TypeError, ValueError):
        return default


def service_config(s: Session) -> dict:
    cfg = settings(s)
    return {
        "open": cfg["open"], "last_seating": cfg["last_seating"], "close": cfg["close"],
        "slot_minutes": int(cfg["slot_minutes"]),
        "default_duration": int(cfg["default_duration"]),
        "turnover_buffer": int(cfg["turnover_buffer"]),
        "hold_seconds": int(cfg["hold_seconds"]),
        "grace_minutes": int(cfg["grace_minutes"]),
        "reminder_minutes": int(cfg["reminder_minutes"]),
        "max_party": int(cfg["max_party"]),
    }


def slots(s: Session) -> list[str]:
    cfg = service_config(s)
    start = rtime.minutes_of(rtime.combine(rtime.today(), cfg["open"]))
    end = rtime.minutes_of(rtime.combine(rtime.today(), cfg["last_seating"]))
    step = max(5, cfg["slot_minutes"])
    return [rtime.hhmm(m) for m in range(start, end + 1, step)]


def duration_for(s: Session, party: int) -> int:
    """The house's own booking length. One rule, used by every surface."""
    base = int_setting(s, "default_duration", 105)
    if party <= 2:
        return max(60, base - 15)
    if party <= 4:
        return base
    if party <= 6:
        return base + 15
    return base + 30


# ------------------------------------------------------- booking reference

def booking_code(reservation_id: int) -> str:
    return "SF%05d" % int(reservation_id)


def backfill_reservation_identity() -> None:
    """Give historic reservations a booking reference and a confirm token.

    Existing rows are not rewritten in any other way: name/contact fields
    stay whatever they were, only the identifiers that new code needs are
    filled in.
    """
    import secrets
    from .models import Guest, Reservation
    with Session(engine, expire_on_commit=False) as s:
        rows = s.exec(select(Reservation).where(
            (Reservation.code == "") | (Reservation.code == None))).all()  # noqa: E711
        guests = {g.id: g for g in s.exec(select(Guest)).all()}
        for r in rows:
            r.code = booking_code(r.id)
            if not (r.confirm_token or ""):
                r.confirm_token = secrets.token_urlsafe(18)
            if not (r.first_name or r.last_name):
                g = guests.get(r.guest_id)
                name = (g.name if g else "").strip()
                bits = name.split(" ", 1)
                r.first_name = bits[0] if bits else ""
                r.last_name = bits[1] if len(bits) > 1 else ""
            if not r.updated_at:
                r.updated_at = r.created_at or rtime.now()
            s.add(r)
        if rows:
            s.commit()


# ------------------------------------------------- canonical table registry

def _load_scene_tables() -> list[dict]:
    path = VENUE_DIR / "tables.json"
    if not path.exists():
        return []
    try:
        return json.load(open(path))
    except Exception:
        return []


def _load_scene_zones() -> dict:
    path = VENUE_DIR / "zones.json"
    if not path.exists():
        return {}
    try:
        return {z["id"]: z for z in json.load(open(path))}
    except Exception:
        return {}


def _load_seat_counts() -> dict[str, int]:
    """Physical chairs actually modelled in the room — the real capacity."""
    path = VENUE_DIR / "seats.json"
    if not path.exists():
        return {}
    try:
        counts: dict[str, int] = {}
        for seat in json.load(open(path)):
            counts[seat["table_id"]] = counts.get(seat["table_id"], 0) + 1
        return counts
    except Exception:
        return {}


def _map_size() -> tuple[float, float]:
    path = VENUE_DIR / "floor.json"
    try:
        m = (json.load(open(path)).get("map") or {})
        return (float(m.get("width") or m.get("w") or 940),
                float(m.get("height") or m.get("h") or 940))
    except Exception:
        return 940.0, 940.0


def sync_table_registry(force_geometry: bool = False) -> dict:
    """Reconcile DiningTable + TableProfile against the room's geometry.

    Runs once at boot. It never deletes a table and never touches a
    reservation: it fills in the profile the 3D scene needs, and brings the
    operational record's capacity, zone and floor position into line with
    the physical room so the two applications describe one restaurant.
    """
    scene = _load_scene_tables()
    if not scene:
        return {"synced": 0, "reason": "no scene geometry available"}
    zones = _load_scene_zones()
    chairs = _load_seat_counts()
    map_w, map_h = _map_size()

    created = updated = 0
    with Session(engine, expire_on_commit=False) as s:
        by_number = {t.number: t for t in s.exec(select(DiningTable)).all()}
        profiles = {p.table_id: p for p in s.exec(select(TableProfile)).all()}

        for row in scene:
            try:
                number = int(str(row.get("label") or row["id"][1:]))
            except (TypeError, ValueError):
                continue
            zone_meta = zones.get(row.get("zone") or "", {})
            seats = int(chairs.get(row["id"]) or row.get("max_party") or 2)
            op_zone = AREA_TO_ZONE.get(row.get("zone") or "", "Main")

            table = by_number.get(number)
            if table is None:
                table = DiningTable(number=number, seats=seats, zone=op_zone,
                                    shape=row.get("shape") or "round")
                s.add(table)
                s.flush()
                by_number[number] = table
                created += 1
            elif table.zone != ARCHIVED_ZONE:
                # Capacity and area come from the room itself, so a party of
                # six can never be offered a table with four chairs in it.
                changed = False
                if table.seats != seats:
                    table.seats = seats
                    changed = True
                if table.zone != op_zone:
                    table.zone = op_zone
                    changed = True
                if force_geometry or (table.x, table.y) == (0.5, 0.5):
                    table.x = round(min(0.97, max(0.03, float(row["x"]) / map_w)), 4)
                    table.y = round(min(0.96, max(0.04, float(row["y"]) / map_h)), 4)
                    changed = True
                if changed:
                    s.add(table)
                    updated += 1

            p = profiles.get(table.id) or TableProfile(table_id=table.id)
            p.scene_id = row["id"]
            p.label = str(row.get("label") or number)
            p.area = row.get("zone") or ""
            p.area_name = zone_meta.get("name") or p.area.title()
            p.area_blurb = zone_meta.get("blurb") or ""
            p.outdoor = bool(zone_meta.get("outdoor"))
            p.min_party = int(row.get("min_party") or 1)
            p.max_party = seats
            p.accessible = bool(row.get("accessible"))
            p.premium_view = bool(row.get("premium_view"))
            p.shape = row.get("shape") or "round"
            p.map_x, p.map_y = float(row.get("x") or 0), float(row.get("y") or 0)
            p.map_w, p.map_h = float(row.get("w") or 0), float(row.get("h") or 0)
            p.rotation = float(row.get("rotation") or 0)
            world = row.get("world") or {}
            p.world_x = float(world.get("x") or 0)
            p.world_y = float(world.get("y") or 0)
            p.world_z = float(world.get("z") or 0)
            p.tags = ",".join(row.get("tags") or [])
            p.combinable = ",".join(row.get("combinable_with") or [])
            p.scores = json.dumps(row.get("scores") or {})
            p.distances = json.dumps(row.get("distances") or {})
            p.bearings = json.dumps(row.get("bearings") or {})
            p.verification = row.get("verification") or "PLACEHOLDER"
            p.updated_at = rtime.now()
            s.add(p)
        s.commit()
    return {"synced": len(scene), "created": created, "updated": updated}


def scene_id_for(number: int) -> str:
    return "t%02d" % int(number)


def number_from_scene_id(scene_id: str) -> Optional[int]:
    text = str(scene_id or "")
    if text.startswith("t") and text[1:].isdigit():
        return int(text[1:])
    if text.isdigit():
        return int(text)
    return None


def table_public(t: DiningTable, p: Optional[TableProfile], cfg: dict | None = None) -> dict:
    """The one table shape both applications render from."""
    scores = json.loads(p.scores) if p and p.scores else {}
    distances = json.loads(p.distances) if p and p.distances else {}
    bearings = json.loads(p.bearings) if p and p.bearings else {}
    return {
        "id": p.scene_id if p and p.scene_id else scene_id_for(t.number),
        "table_id": p.scene_id if p and p.scene_id else scene_id_for(t.number),
        "number": t.number,
        "os_table_id": t.id,
        "label": (p.label if p and p.label else str(t.number)),
        "zone": (p.area if p and p.area else (t.zone or "main").lower()),
        "operational_zone": t.zone,
        "zone_name": (p.area_name if p and p.area_name else t.zone),
        "zone_blurb": (p.area_blurb if p else ""),
        "outdoor": bool(p.outdoor) if p else (t.zone == "Terrace"),
        "shape": (p.shape if p and p.shape else t.shape),
        "seats": t.seats,
        "min_party": min(int(p.min_party) if p else 1, t.seats),
        "max_party": t.seats,
        "accessible": bool(p.accessible) if p else True,
        "premium_view": bool(p.premium_view) if p else False,
        "blocked": bool(p.blocked) if p else False,
        "blocked_reason": (p.blocked_reason if p else ""),
        "x": p.map_x if p else t.x,
        "y": p.map_y if p else t.y,
        "w": p.map_w if p else 0,
        "h": p.map_h if p else 0,
        "rotation": p.rotation if p else 0,
        "floor_x": t.x, "floor_y": t.y,
        "world": {"x": p.world_x, "y": p.world_y, "z": p.world_z} if p else None,
        "tags": [x for x in (p.tags.split(",") if p and p.tags else []) if x],
        "combinable_with": [x for x in (p.combinable.split(",") if p and p.combinable else []) if x],
        "scores": scores, "distances": distances, "bearings": bearings,
        "verification": (p.verification if p else "PLACEHOLDER"),
    }


def canonical_tables(s: Session, include_archived: bool = False) -> list[dict]:
    profiles = {p.table_id: p for p in s.exec(select(TableProfile)).all()}
    rows = []
    for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
        if not include_archived and t.zone == ARCHIVED_ZONE:
            continue
        rows.append(table_public(t, profiles.get(t.id)))
    return rows


# --------------------------------------------------- operational floor plan
# The 3D room is a tall, narrow waterfront space; the manager's floor plan is
# a wide board. They are two renderings of one canonical table set, so the
# scene keeps its own metric coordinates in TableProfile while the floor plan
# keeps a readable layout here. What both must agree on — and now do — is
# which zone a table belongs to. This lays the board out to match the zones
# once, then never touches it again so a manager's own drag is preserved.

# One band per zone, laid out so no two rows of tables touch. Nothing hangs
# below a table any more, so these only have to clear the chips themselves.
FLOOR_BANDS = {
    "Terrace": (0.08, 0.92, 0.09, 0.27, 7),
    "Main":    (0.08, 0.74, 0.45, 0.67, 6),
    "Bar":     (0.08, 0.50, 0.86, 0.94, 4),
    "Private": (0.82, 0.94, 0.45, 0.67, 1),
}


def relayout_floor(force: bool = False) -> dict:
    """Group the floor board by canonical zone. Runs once unless forced."""
    with Session(engine, expire_on_commit=False) as s:
        if not force and setting(s, "floor_relayout", "") == "v1":
            return {"relaid": 0, "reason": "already laid out"}
        by_zone: dict[str, list[DiningTable]] = {}
        for t in s.exec(select(DiningTable).order_by(DiningTable.number)).all():
            if t.zone == ARCHIVED_ZONE:
                continue
            by_zone.setdefault(t.zone, []).append(t)
        moved = 0
        for zone, tables in by_zone.items():
            x0, x1, y0, y1, per_row = FLOOR_BANDS.get(zone, (0.06, 0.94, 0.34, 0.70, 6))
            rows = max(1, -(-len(tables) // per_row))
            for i, t in enumerate(tables):
                col, row = i % per_row, i // per_row
                cols = min(per_row, len(tables) - row * per_row)
                t.x = round(x0 + (x1 - x0) * ((col + 0.5) / max(1, cols)), 4)
                t.y = round(y0 + (y1 - y0) * ((row + 0.5) / rows), 4)
                s.add(t)
                moved += 1
        row = s.get(RestaurantSetting, "floor_relayout")
        if row is None:
            s.add(RestaurantSetting(key="floor_relayout", value="v1"))
        else:
            row.value = "v1"
            s.add(row)
        s.commit()
    return {"relaid": moved}


def repair_stale_service() -> dict:
    """Clear physical occupancy left behind by a previous run.

    A table cannot really have been "seated" since last week. Anything older
    than one full service is stale state, not a party, and it would otherwise
    keep a real table dark in both applications. Reservations are untouched.
    """
    from datetime import timedelta
    from .models import TableStatus
    cutoff = rtime.now() - timedelta(hours=10)
    cleared = closed = 0
    with Session(engine, expire_on_commit=False) as s:
        for t in s.exec(select(DiningTable)).all():
            if t.zone == ARCHIVED_ZONE or t.status == DiningTable.__fields__["status"].default:
                pass
            stale_seat = t.seated_at is not None and t.seated_at < cutoff
            stale_touch = (t.seated_at is None and t.last_touched_at is not None
                           and t.last_touched_at < cutoff
                           and t.status.value not in ("available",))
            if stale_seat or stale_touch:
                t.status = TableStatus.AVAILABLE
                t.party_size = 0
                t.guest_id = None
                t.seated_at = None
                t.last_touched_at = rtime.now()
                s.add(t)
                cleared += 1
        # Nobody has been standing at the door since last week. A waitlist
        # entry still "waiting" from a previous service is residue, and it
        # reads as a party quoted 35 minutes who has now waited 15,000.
        from .models import WaitlistEntry
        for w in s.exec(select(WaitlistEntry).where(WaitlistEntry.status == "waiting")).all():
            if w.added_at and w.added_at < cutoff:
                w.status = "left"
                s.add(w)
                closed += 1

        # An unpaid order from days ago is not an open ticket, it is residue
        # from a previous run. Leaving it makes the kitchen board and the
        # Command Center lie about the current service.
        from .models import ItemState, Order, OrderItem
        for o in s.exec(select(Order).where(Order.paid == False)).all():   # noqa: E712
            if o.opened_at and o.opened_at < cutoff:
                o.paid = True
                o.closed_at = o.closed_at or rtime.now()
                s.add(o)
                closed += 1
        for i in s.exec(select(OrderItem).where(
                OrderItem.state.in_([ItemState.QUEUED, ItemState.COOKING]))).all():
            if i.fired_at and i.fired_at < cutoff:
                i.state = ItemState.SERVED
                i.ready_at = i.ready_at or i.fired_at
                s.add(i)
                closed += 1
        if cleared or closed:
            s.commit()
    return {"cleared": cleared, "closed": closed}


def seed_menu_sections() -> None:
    """Every course a dish currently uses gets a MenuSection row.

    /api/public/menu (SUFRA 360, the guest booking site — anywhere a guest
    reads the menu) groups dishes by walking THIS table, not a hardcoded
    list, so a manager's own "+ Section" survives to every guest surface.
    That only works if the table is never empty, so this runs at boot —
    not lazily the first time somebody happens to open the menu admin
    screen — and it is additive: it only ever adds a row, never removes
    or reorders one a manager already has.
    """
    from .models import MenuItem, MenuSection
    with Session(engine, expire_on_commit=False) as s:
        existing = {x.name for x in s.exec(select(MenuSection)).all()}
        seen_courses: list[str] = []
        for m in s.exec(select(MenuItem)).all():
            if m.course and m.course not in seen_courses:
                seen_courses.append(m.course)
        added = False
        for idx, name in enumerate(seen_courses):
            if name not in existing:
                s.add(MenuSection(name=name, sort_order=idx * 10))
                added = True
        if added:
            s.commit()