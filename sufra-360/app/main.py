"""SUFRA 360 — the customer-facing 3D restaurant.

It renders the room. It does not own the restaurant: tables, availability,
reservations, holds, the waitlist, the menu, the opening hours and the
clock all come from SUFRA OS through app/nova.py, against the same rows the
manager, the waiter and the Command Center read. There is no second
database here and no second copy of any restaurant state.
"""
import asyncio
import datetime
import json
import os
import uuid
from typing import Optional

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import booking, db, nova, weather

ROOT = db.ROOT
STATIC = os.path.join(ROOT, "static")
ASSETS = os.path.join(ROOT, "assets")

BUILD = "13"


def _ws_available():
    """uvicorn needs websockets or wsproto to accept an upgrade. Without one
    the /ws route 404s, so say so instead of letting the client retry forever."""
    for mod in ("websockets", "wsproto"):
        try:
            __import__(mod)
            return True
        except ImportError:
            pass
    return False


WS_OK = _ws_available()

app = FastAPI(title="SUFRA 360", version="2.0.0")


def _nova_error(exc):
    """Never invent an answer when the restaurant cannot be reached."""
    if isinstance(exc, nova.NovaRefused):
        payload = dict(exc.payload)
        payload.setdefault("ok", False)
        return JSONResponse(payload, exc.status)
    return JSONResponse({"ok": False, "error": "restaurant_unavailable",
                         "message": "The restaurant system is not responding. "
                                    "Please try again in a moment."}, 503)


# ------------------------------------------------------------- realtime hub
class Hub:
    def __init__(self):
        self.clients = set()
        self.lock = asyncio.Lock()

    async def join(self, ws):
        async with self.lock:
            self.clients.add(ws)

    async def leave(self, ws):
        async with self.lock:
            self.clients.discard(ws)

    async def publish(self, kind, data):
        msg = json.dumps({"type": kind, "data": data,
                          "at": datetime.datetime.now().isoformat(timespec="seconds")})
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.leave(ws)


hub = Hub()


def emit(kind, data):
    try:
        asyncio.get_running_loop().create_task(hub.publish(kind, data))
    except RuntimeError:
        pass


# ------------------------------------------------------------------ session
def session_of(request: Request, response: Response = None):
    """One id per browser, for the whole request. The middleware puts it on
    request.state BEFORE the endpoint runs, so the very first request a
    browser makes already holds tables under the id it will keep."""
    return getattr(request.state, "sid", None) or request.cookies.get("sufra_sid") \
        or uuid.uuid4().hex


@app.middleware("http")
async def session_and_cache(request: Request, call_next):
    sid = request.cookies.get("sufra_sid")
    fresh = not sid
    if fresh:
        sid = uuid.uuid4().hex
    request.state.sid = sid

    resp = await call_next(request)

    if fresh:
        resp.set_cookie("sufra_sid", sid, max_age=60 * 60 * 24 * 30,
                        samesite="lax", httponly=False)
    path = request.url.path
    if path.startswith("/api") or path.startswith("/static") or \
            path.endswith(".html") or "." not in path.rsplit("/", 1)[-1]:
        # a cached old app.js against a new index.html is the worst kind of bug
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


async def _os_bridge(interval: float = 2.0):
    """Live updates across two processes.

    SUFRA OS keeps a monotonic revision that changes only when something in
    the restaurant really happened — a table seated, a booking made, a menu
    item pulled. Watching it here and pushing to this app's own sockets is
    what makes a waiter's tap in SUFRA OS light up a guest's 3D room without
    a reload, and without either process guessing.
    """
    last = None
    while True:
        try:
            state = nova.live()
            rev = state.get("revision")
            if last is not None and rev != last:
                await hub.publish("STATE", {"revision": rev,
                                            "counts": state.get("counts")})
            last = rev
        except Exception:
            last = None                       # re-sync on the next good read
        await asyncio.sleep(interval)


@app.on_event("startup")
async def startup():
    status = nova.health()
    if status.get("reachable"):
        print("[sufra360] restaurant: %s (%s) via %s"
              % (status["restaurant"], status["timezone"], status["base"]))
    else:
        print("[sufra360] SUFRA OS is not reachable at %s — %s"
              % (status["base"], status.get("detail")))
    asyncio.ensure_future(_os_bridge())


# ------------------------------------------------------------------ venue
@app.get("/api/public/venue")
def api_venue():
    """Scene geometry plus the restaurant's own service configuration.

    Opening hours, booking length, the hold window, the grace policy, the
    restaurant's name and its clock all come from SUFRA OS: change them in
    the manager's settings and the 3D scene follows, with no second edit.
    """
    try:
        os_venue = nova.venue()
        floor, tables, seats, zones = booking.venue()
    except Exception as exc:
        return _nova_error(exc)
    scene = dict(floor)
    scene["name"] = os_venue["restaurant"]["name"]
    scene["timezone"] = os_venue["timezone"]
    scene["currency"] = os_venue["restaurant"]["currency"]
    scene["phone"] = os_venue["restaurant"]["phone"]
    scene["address"] = os_venue["restaurant"]["address"]
    return {"venue": scene, "zones": zones,
            "restaurant": os_venue["restaurant"],
            "service": os_venue["service"], "slots": os_venue["slots"],
            "hold_seconds": os_venue["hold_seconds"],
            "grace_minutes": os_venue["grace_minutes"],
            "timezone": os_venue["timezone"],
            "realtime": WS_OK,
            "poll_seconds": 20 if WS_OK else 8,
            "today": os_venue["today"],
            "now": os_venue["now"],
            "min_time_today": os_venue["min_time_today"]}


@app.get("/api/public/tables")
def api_tables():
    try:
        return booking.venue()[1]
    except Exception as exc:
        return _nova_error(exc)


@app.get("/api/public/tables/{table_id}")
def api_table(table_id: str):
    t = booking.table_map().get(table_id)
    if not t:
        return JSONResponse({"error": "not_found"}, 404)
    return t


@app.get("/api/public/tables/{table_id}/seats")
def api_seats(table_id: str):
    return [s for s in booking.venue()[2] if s["table_id"] == table_id]


@app.get("/api/public/seats")
def api_all_seats():
    """Every seat of every table in one response: the 360 scene used to make
    one request per table at boot, which is 25 round trips before it can draw."""
    return booking.venue()[2]


@app.get("/api/public/google")
def api_google():
    """Google integration status. The key is needed client-side by the Maps
    Embed API, which is what it is designed for; restrict it by HTTP referrer
    in the Google Cloud console."""
    path = os.path.join(db.VENUE, "google.json")
    try:
        cfg = json.load(open(path))
    except Exception:
        cfg = {}
    key = (cfg.get("api_key") or "").strip()
    return {
        # keyless embeds need no key, so the real venue works out of the box
        "enabled": bool(key) or cfg.get("mode") == "keyless",
        "mode": "api" if key else (cfg.get("mode") or "off"),
        "use_real": bool(cfg.get("use_real")),
        "display_name": cfg.get("display_name") or "",
        "display_city": cfg.get("display_city") or "",
        "api_key": key,
        "place_id": cfg.get("place_id") or "",
        "place_query": cfg.get("place_query") or "",
        "location": cfg.get("location") or {},
        "exterior_pano_id": cfg.get("exterior_pano_id") or "",
        "interior_pano_id": cfg.get("interior_pano_id") or "",
        "table_panos": cfg.get("table_panos") or {},
        "video_360": cfg.get("video_360") or {},
        "licence": ("Google imagery is embedded through the Maps Embed API and "
                    "is never downloaded, cached or modified."),
    }


@app.get("/api/public/real-venue")
def api_real_venue():
    """A real, existing venue with a real 3D walkthrough, embedded live from
    the provider's own viewer. We never download or alter their capture."""
    try:
        cfg = json.load(open(os.path.join(db.VENUE, "real_venue.json")))
    except Exception:
        cfg = {"enabled": False}
    return cfg


@app.get("/api/weather")
def api_weather():
    floor = booking.venue()[0]
    w = floor.get("weather") or {}
    return weather.current(w.get("lat", 40.4093), w.get("lng", 49.8671),
                           floor.get("timezone", "Asia/Baku"),
                           floor.get("weather_city", ""))


@app.get("/api/public/live")
def api_live(request: Request):
    """The digital twin: what every table is PHYSICALLY doing right now.

    This is not bookability. A table occupied at two o'clock can still be
    reserved for nine; that question is answered by /api/public/availability
    against the chosen date and time.
    """
    try:
        return nova.live(session_of(request))
    except Exception as exc:
        return _nova_error(exc)


@app.get("/api/public/menu")
def api_menu():
    """One menu, SUFRA OS's own dish records.

    A price change or a sold-out flag in the kitchen reaches this screen on
    the next read. There is no menu file in this application any more.
    """
    try:
        return nova.menu()
    except Exception as exc:
        return _nova_error(exc)


# ------------------------------------------------------------ availability
@app.get("/api/public/availability")
def api_availability(request: Request, date: str, time: str = "19:00",
                     party_size: int = 2, duration: Optional[int] = None):
    """Bookability for a chosen date and time — never current occupancy."""
    try:
        return nova.availability(date, time, party_size, duration,
                                 session_of(request))
    except Exception as exc:
        return _nova_error(exc)


@app.post("/api/public/recommend-tables")
async def api_recommend(request: Request):
    b = await request.json()
    try:
        return booking.recommend(
            b.get("date"), b.get("time", "19:00"), int(b.get("party_size") or 2),
            preset=b.get("preference"), free_text=b.get("notes"),
            duration=b.get("duration"), session_id=session_of(request),
            limit=int(b.get("limit") or 6), event=b.get("event"))
    except Exception as exc:
        return _nova_error(exc)


# ------------------------------------------------------------------ holds
@app.post("/api/public/holds")
async def api_hold(request: Request):
    b = await request.json()
    sid = session_of(request)
    try:
        r = nova.post("/api/public/holds", {
            "table_id": b.get("table_id"), "date": b.get("date"),
            "time": b.get("time", "19:00"),
            "party_size": int(b.get("party_size") or 2),
            "duration": b.get("duration")}, sid)
    except Exception as exc:
        return _nova_error(exc)
    emit("TABLE_HELD", {"table_id": b.get("table_id"), "date": b.get("date"),
                        "time": b.get("time")})
    return r


@app.delete("/api/public/holds/{hold_id}")
def api_hold_release(request: Request, hold_id: str):
    try:
        r = nova.delete("/api/public/holds/" + hold_id, session_of(request))
    except Exception as exc:
        return _nova_error(exc)
    emit("HOLD_RELEASED", {"hold_id": hold_id})
    return r


# ------------------------------------------------------------ reservations
@app.post("/api/public/reservations")
async def api_reserve(request: Request):
    """Create the booking — in SUFRA OS, as an ordinary reservation row.

    Every rule applies here because it is the same engine the manager's own
    booking screen uses: opening hours, capacity, no bookings in the past,
    turnover protection and a final conflict check inside the database
    writer lock so two guests cannot win the same table.
    """
    b = await request.json()
    sid = session_of(request)
    try:
        r = nova.post("/api/public/reservations", b, sid)
    except Exception as exc:
        return _nova_error(exc)
    res = r.get("reservation") or {}
    emit("RESERVATION_CREATED", {"table_id": res.get("table_id"),
                                 "date": res.get("date"), "time": res.get("time")})
    return r


@app.get("/api/public/reservations/{code}")
def api_reservation(code: str):
    try:
        return nova.get("/api/public/reservations/" + code)
    except Exception as exc:
        return _nova_error(exc)


@app.get("/api/public/reservations/{code}/calendar.ics")
def api_reservation_ics(code: str):
    """Add to calendar. The event is generated by SUFRA OS in the
    restaurant's own timezone, so it lands at the right hour anywhere."""
    try:
        body, ctype = nova.raw("/api/public/reservations/%s/calendar.ics" % code)
    except Exception as exc:
        return _nova_error(exc)
    return Response(body, media_type="text/calendar",
                    headers={"Content-Disposition":
                             'attachment; filename="%s.ics"' % code})


@app.post("/api/public/reservations/{code}/cancel")
def api_cancel(code: str):
    try:
        r = nova.post("/api/public/reservations/%s/cancel" % code)
    except Exception as exc:
        return _nova_error(exc)
    emit("RESERVATION_CANCELLED", {"code": code})
    return r


# --------------------------------------------------------------- waitlist
@app.post("/api/public/waitlist")
async def api_waitlist(request: Request):
    """Join the restaurant's ONE waitlist — the same list the host works
    from in SUFRA OS. There is no 360-only waiting list."""
    b = await request.json()
    try:
        r = nova.post("/api/public/waitlist", b, session_of(request))
    except Exception as exc:
        return _nova_error(exc)
    emit("WAITLIST_ADDED", {"party_size": b.get("party_size")})
    return r


# ------------------------------------------------- conversational venue guide
GUIDE_INTENTS = [
    (("non-smoking", "non smoking", "no smoking", "indoor", "inside"), "indoor",
     "Indoor tables, non-smoking."),
    (("smoking", "smoke"), "terrace", "Outdoor tables, where smoking is permitted."),
    (("shade", "shaded", "umbrella", "out of the sun"), "shade", "Tables under cover."),
    (("family", "families", "kids", "children"), "family", "Family tables."),
    (("water", "sea", "waterfront", "closer to the water", "by the water"), "sea",
     "Closest to the water."),
    (("quietest", "quiet", "least noisy", "not noisy", "calm"), "quiet", "Here are the quietest tables free then."),
    (("romantic", "date", "anniversary", "proposal"), "romantic",
     "These read most romantic at that time."),
    (("terrace", "outside", "outdoor", "al fresco"), "terrace",
     "Terrace tables, facing the water."),
    (("garden",), "garden", "The garden room, under the vines."),
    (("window",), "window", "Window tables."),
    (("private", "privacy"), "private", "The private room and the most secluded tables."),
    (("bar", "counter"), "bar", "At the bar."),
    (("view", "best view"), "view", "Best views in the room."),
    (("lively", "buzzy", "atmosphere"), "lively", "The livelier end of the room."),
    (("accessible", "wheelchair", "step free"), "accessible",
     "Step-free tables."),
]


def _has(q, phrase):
    """Word-boundary match. Stops 'spaces' matching the token 'pa'."""
    import re
    return re.search(r"\b" + re.escape(phrase) + r"\b", q) is not None


FACT_INTENTS = [
    (("capacity", "how many people", "how many guests", "how many can", "fit",
      "hold", "max"), "capacity"),
    (("price", "pricing", "cost", "how much", "per head", "budget", "spend",
      "deposit", "hire", "minimum"), "pricing"),
    (("layout", "flow", "spaces", "rooms", "walkthrough", "walk through",
      "describe", "tour"), "flow"),
    (("parking", "transport", "get there", "load in", "load-in", "access",
      "step free", "wheelchair", "curfew", "pa", "sound", "av", "microphone",
      "stage size", "last orders", "logistics"), "logistics"),
    (("reception", "standing", "canape", "canapes", "drinks party"), "reception"),
    (("live music", "band", "dj", "gig", "music night"), "live_music"),
]


def _facts_answer(kind, floor, tables):
    p = floor["pricing"]; lg = floor["logistics"]; sym = p["symbol"]
    if kind == "capacity":
        by_zone = {}
        for t in tables:
            by_zone[t["zone"]] = by_zone.get(t["zone"], 0) + t["max_party"]
        parts = ", ".join("%s %d" % (z, n) for z, n in sorted(
            by_zone.items(), key=lambda kv: -kv[1]))
        return ("%d seated across %d tables, %d standing for a reception. "
                "By area: %s. Private room seats %d."
                % (lg["seated_capacity"], len(tables), lg["standing_capacity"],
                   parts, max(t["max_party"] for t in tables if t["zone"] == "private")))
    if kind == "pricing":
        menus = ", ".join("%s %s%d" % (m["name"], sym, m["price"])
                          for m in p["set_menu"])
        return ("Around %s%d a head for dinner. Set menus: %s. Deposit %s%d a head. "
                "Private room hire %s%d, full venue %s%d. Service %.1f%%."
                % (sym, p["avg_per_head_dinner"], menus, sym, p["deposit_per_head"],
                   sym, p["private_room_hire"], sym, p["full_venue_hire"],
                   p["service_charge_pct"]))
    if kind == "logistics":
        return ("Step-free throughout with an accessible WC. %s. %s. Load-in: %s. "
                "Stage %s with %s. %s. Kitchen last orders %s."
                % (lg["nearest_transport"], lg["parking"], lg["load_in"],
                   lg["stage_size_m"], lg["av"], lg["curfew"],
                   lg["kitchen_last_orders"]))
    if kind == "flow":
        return ("You come in at the south end into the lobby, past the kitchen pass. "
                "The bar is on your right along the east wall. The main floor opens "
                "ahead of you, and the whole west wall is glass onto the water with "
                "the front row of tables against it. The stage sits at the north end "
                "facing back down the room. The deck runs outside the glass, over the "
                "water. The private room is off the east side, behind its own door.")
    ev = floor["events"][kind]
    return ("%s. %s Capacity %s, minimum spend %s%s."
            % (ev["name"], ev["blurb"], ev.get("capacity") or "n/a",
               floor["pricing"]["symbol"], ev.get("min_spend") or 0))


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a couple": 2, "couple": 2}


def _party_from(q, default):
    """'for two', 'table for 4', 'party of six', '6 people', '4 guests'."""
    import re
    m = re.search(r"\b(?:for|of|seats?)\s+(\d{1,2})\b", q)
    if m:
        return max(1, min(20, int(m.group(1))))
    m = re.search(r"\b(\d{1,2})\s+(?:people|guests|persons|of us|pax|covers)\b", q)
    if m:
        return max(1, min(20, int(m.group(1))))
    for word, n in WORD_NUMBERS.items():
        if re.search(r"\b(?:for|of)\s+" + re.escape(word) + r"\b", q) or \
                re.search(r"\b" + re.escape(word) + r"\s+(?:people|guests|of us)\b", q):
            return n
    return default


def _time_from(q, default):
    """'at 8', 'at 20:30', '7pm', 'lunch', 'tonight'."""
    import re
    m = re.search(r"\b(?:at|around|about)\s+(\d{1,2})(?::(\d{2}))?\s*(pm|am)?\b", q)
    if not m:
        m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(pm|am)\b", q)
    if m:
        h = int(m.group(1)); mi = int(m.group(2) or 0); ap = m.group(3)
        if ap == "pm" and h < 12:
            h += 12
        if not ap and h <= 9:            # "at 8" in a restaurant means 20:00
            h += 12
        if 0 <= h < 24 and 0 <= mi < 60:
            return "%02d:%02d" % (h, mi)
    if "lunch" in q:
        return "13:00"
    if "tonight" in q or "dinner" in q or "evening" in q:
        return default if default >= "17:00" else "19:30"
    return default


# what an enumerating question ("which tables are ...") filters on:
# (phrases, predicate on attributes, label, score key to rank by when the strict filter finds fewer than 3)
ENUM_FILTERS = [
    (("non-smoking", "non smoking", "no smoking", "nonsmoking"), lambda a: not a["smoking"], "non-smoking", None),
    (("smoking",), lambda a: a["smoking"], "where smoking is permitted (outdoors)", None),
    (("water", "sea", "waterfront", "harbour", "harbor"), lambda a: a["near_water"], "closest to the water", "sea_view"),
    (("shade", "shaded", "covered", "umbrella", "out of the sun"), lambda a: a["shade"] == "covered", "under cover or shade", None),
    (("privacy", "private", "secluded", "discreet"), lambda a: a["privacy"] != "open room", "the most private", "privacy"),
    (("romantic", "date", "anniversary"), lambda a: a["romantic"], "best for a romantic dinner", "romantic"),
    (("family", "families", "kids", "children"), lambda a: a["family"], "family friendly", "family"),
    (("quiet", "quietest", "least noisy", "not noisy", "calm"), lambda a: a["noise"] == "quiet", "quiet", "quiet"),
    (("lively", "buzzy", "atmosphere"), lambda a: a["noise"] == "lively", "at the lively end", "lively"),
    (("indoor", "inside", "indoors"), lambda a: a["indoor"], "indoors", None),
    (("outdoor", "outside", "outdoors", "terrace", "al fresco"), lambda a: a["outdoor"], "outdoors", None),
    (("accessible", "wheelchair", "step free", "step-free"), lambda a: a["accessible"], "step-free", None),
    (("window",), lambda a: a["window"], "by a window", "window_proximity"),
    (("group", "large", "big table", "party"), lambda a: a["group"], "sized for a group", None),
    (("view",), lambda a: a["premium_view"], "with the best views", "view"),
]


def _is_enumeration(q):
    return q.startswith(("which tables", "what tables", "show tables", "show me tables",
                         "show me the tables", "list", "show all", "which ones", "how many tables"))


@app.post("/api/public/guide")
async def api_guide(request: Request):
    b = await request.json()
    q = (b.get("question") or "").lower().strip()
    date = b.get("date")
    party = _party_from(q, int(b.get("party_size") or 2))
    time_ = _time_from(q, b.get("time", "19:00"))
    sid = session_of(request)
    tmap = booking.table_map()
    ctx = {"party_size": party, "time": time_}

    # "show me table 14" / "tell me about table 14"
    import re
    m = re.search(r"table\s*(\d+)", q)
    if m:
        want = m.group(1)
        for t in booking.venue()[1]:
            if t["label"] == want:
                av = booking.availability(date, time_, party, session_id=sid)
                st = next(r for r in av["tables"] if r["table_id"] == t["id"])
                status = {"AVAILABLE": "Free", "RESERVED": "Already booked",
                          "HELD": "Being booked by someone else",
                          "HELD_BY_YOU": "Held by you",
                          "BLOCKED": "Out of service",
                          "PAST": "That time has already passed",
                          "CLOSED": "We are not seating at that time",
                          "INCOMPATIBLE": "Wrong size for a party of %d" % party
                          }.get(st["state"], st["state"].title())
                nxt = (" Next free at %s." % st["next_available"]) if st.get("next_available") else ""
                return dict(ctx, message="%s %s at %s.%s" % (booking.describe_table(t), status, time_, nxt),
                            highlight=[t["id"]], focus=t["id"], tables=[],
                            attributes=t.get("attributes"))
        return dict(ctx, message="There's no table %s here." % want, highlight=[], tables=[])

    floor, all_tables, _s, _z = booking.venue()

    # "which tables are non-smoking?" - an enumeration, not a recommendation
    if _is_enumeration(q):
        for phrases, pred, label, score_key in ENUM_FILTERS:
            if any(_has(q, w) for w in phrases):
                hits = [t for t in all_tables if pred(t["attributes"])]
                if score_key and len(hits) < 3:
                    hits = sorted(all_tables, key=lambda t: -t["scores"].get(score_key, 0))[:4]
                if not hits:
                    return dict(ctx, message="No tables are %s." % label, highlight=[], tables=[])
                live = api_live()
                lmap = {r["table_id"]: r for r in live["tables"]}
                free = [t for t in hits if lmap.get(t["id"], {}).get("state") == "AVAILABLE"]
                names = ", ".join(t["label"] for t in hits)
                if len(hits) == 1:
                    msg = "Table %s is %s. It is %s right now." % (names, label, "free" if free else "busy")
                else:
                    msg = "%d tables are %s: %s. %s free right now." % (
                        len(hits), label, names,
                        {0: "None are", 1: "One of them is"}.get(len(free), "%d of them are" % len(free)))
                return dict(ctx, message=msg, highlight=[t["id"] for t in hits],
                            focus=(free or hits)[0]["id"],
                            tables=[{"id": t["id"], "label": t["label"], "zone": t["zone"],
                                     "why": [label] + ([] if lmap.get(t["id"], {}).get("state") == "AVAILABLE" else ["busy now"]),
                                     "state": lmap.get(t["id"], {}).get("state")} for t in hits[:8]])

    if "reserved soon" in q or "arriving" in q or "coming up" in q or "booked soon" in q:
        live = api_live()
        soon = [t for t in live["tables"] if t["state"] == "RESERVED_SOON"]
        occ = [t for t in live["tables"] if t["state"] == "OCCUPIED"]
        if not soon:
            return dict(ctx, message="No reservations arriving in the next 30 minutes. %d tables are seated right now."
                        % len(occ), highlight=[t["table_id"] for t in occ], tables=[])
        return dict(ctx, message="Arriving soon: " + ", ".join("Table %s at %s (%d guests)" % (t["label"], t["upcoming"], t["guests"]) for t in soon),
                    highlight=[t["table_id"] for t in soon], focus=soon[0]["table_id"],
                    tables=[{"id": t["table_id"], "label": t["label"], "zone": t["zone"],
                             "why": ["arriving %s" % t["upcoming"], "%d guests" % t["guests"]], "state": "RESERVED_SOON"} for t in soon])
    for phrases, kind in FACT_INTENTS:
        if any(_has(q, w) for w in phrases):
            msg = _facts_answer(kind, floor, all_tables)
            hl = []
            if kind in ("reception", "live_music"):
                cfg = floor["events"][kind]
                only = cfg.get("only_zones"); clear = cfg.get("clear_zones") or []
                hl = [t["id"] for t in all_tables
                      if (not only or t["zone"] in only) and t["zone"] not in clear]
            elif kind == "capacity":
                hl = [t["id"] for t in all_tables]
            return dict(ctx, message=msg, highlight=hl, tables=[], kind=kind)

    preset = None
    lead = "Here's what I'd suggest."
    for phrases, p, text in GUIDE_INTENTS:
        if any(_has(q, w) for w in phrases):
            preset, lead = p, text
            break

    rec = booking.recommend(date, time_, party, preset=preset, free_text=q,
                            session_id=sid, limit=4, event=b.get("event"))
    if not rec["recommended"]:
        alt = rec["unavailable"][:3]
        nxt = [a for a in alt if a.get("next_available")]
        hint = (" Table %s frees up at %s." % (nxt[0]["label"], nxt[0]["next_available"])) if nxt else ""
        return dict(ctx, message="Nothing free at %s for a party of %d.%s Try another time." % (time_, party, hint),
                    highlight=[a["table_id"] for a in alt], tables=[], alternatives=alt)

    top = rec["recommended"][0]["table"]
    names = ", ".join("Table %s" % e["table"]["label"] for e in rec["recommended"])
    msg = "%s %s." % (lead, names)
    if top.get("attributes"):
        a = top["attributes"]
        msg += " Table %s: %s, %s, %s." % (top["label"], a["zone_name"], a["noise"],
                                            "non-smoking" if not a["smoking"] else "smoking permitted")
    return dict(ctx,
        message=msg,
        highlight=[e["table"]["id"] for e in rec["recommended"]],
        focus=top["id"],
        tables=[{"id": e["table"]["id"], "label": e["table"]["label"],
                 "zone": e["table"]["zone"], "why": e["why"],
                 "score": e["score"], "state": e["state"]} for e in rec["recommended"]],
        attributes=top.get("attributes"),
    )


# ------------------------------------------------------------------ socket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    await hub.join(ws)
    try:
        await ws.send_text(json.dumps({"type": "HELLO", "data": {"ok": True}}))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await hub.leave(ws)


# ------------------------------------------------------------------ static
app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/health")
def health():
    status = nova.health()
    out = {"ok": bool(status.get("reachable")), "build": BUILD, "realtime": WS_OK,
           "restaurant_os": status}
    if status.get("reachable"):
        out["venue"] = status["restaurant"]
        out["tables"] = len(nova.tables())
    return out


@app.get("/360")
def sufra360():
    return FileResponse(os.path.join(STATIC, "360.html"))


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/360", status_code=302)


# The 2D floor map and the separate reservation page are no longer part of the
# guest journey: SUFRA 360 is the only customer-facing experience. These routes
# stay so old links, bookmarks and confirmation emails keep working, but they
# land in the 3D scene instead of the old interface.
@app.get("/map")
@app.get("/explore")
@app.get("/reserve")
def legacy_2d(table: Optional[str] = None, date: Optional[str] = None,
              time: Optional[str] = None, party: Optional[int] = None):
    from fastapi.responses import RedirectResponse
    q = []
    if table:
        q.append("table=" + table)
    if date:
        q.append("date=" + date)
    if time:
        q.append("time=" + time)
    if party:
        q.append("party=%d" % party)
    # carrying the table through means an old "reserve table 12" link opens the
    # 3D scene already focused on table 12 with its booking drawer open
    return RedirectResponse("/360" + ("?" + "&".join(q) if q else ""), status_code=302)


# The 3D room now carries the menu and the About panel itself, in all three
# languages. These paths stay so old links keep working, but they land in the
# scene rather than on the superseded 2D page.
@app.get("/menu")
@app.get("/about")
def legacy_pages():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/360", status_code=302)


@app.get("/booking/{code}")
def booking_lookup(code: Optional[str] = None):
    """An old confirmation link. Kept working for guests holding one."""
    return FileResponse(os.path.join(STATIC, "index.html"))
