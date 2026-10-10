"""The room, described — and the preference engine that reads it.

What changed, and why it matters: this module used to own a database of
its own with its own reservations, holds and tables. It no longer owns any
restaurant state at all. Tables, availability, holds, reservations, the
waitlist and the menu all come from SUFRA OS through app/nova.py, so there
is exactly one restaurant behind both applications.

What stays here is what SUFRA 360 genuinely owns: the geometry of the room
(walls, seats, zones — the 3D scene), the plain-language description of
what each table *is*, and the preference language the guide speaks.
"""
import json
import os

from . import db, nova

ROOT = db.ROOT
VENUE = db.VENUE

_floor = None
_seats = None
_zones = None


def geometry():
    """Scene geometry: the parts of the venue that are architecture, not state."""
    global _floor, _seats, _zones
    if _floor is None:
        _floor = json.load(open(os.path.join(VENUE, "floor.json")))
        _seats = json.load(open(os.path.join(VENUE, "seats.json")))
        _zones = json.load(open(os.path.join(VENUE, "zones.json")))
    return _floor, _seats, _zones


def venue():
    """(floor, tables, seats, zones) — tables always straight from SUFRA OS."""
    floor, seats, zones = geometry()
    zmeta = {z["id"]: z for z in zones}
    tables = [dict(t) for t in nova.tables()]
    for t in tables:
        t["attributes"] = table_attributes(t, zmeta.get(t["zone"], {}), floor)
    return floor, tables, seats, zones


def table_map():
    return {t["id"]: t for t in venue()[1]}


# ------------------------------------------------------ table attributes
def table_attributes(t, zone, floor=None):
    """One plain-language description of what a table IS, derived from the
    canonical record. The 360 panel, the hover card and the guide all read
    this, so they can never disagree."""
    sc = t.get("scores") or {}
    tags = t.get("tags") or []
    outdoor = bool(t.get("outdoor", zone.get("outdoor")))
    u = ((floor or {}).get("map") or {}).get("units_to_m", 0.05)
    d = t.get("distances") or {}
    noise = sc.get("noise", 0.4)
    noise_level = "lively" if noise > 0.62 else "moderate" if noise > 0.36 else "quiet"
    near_water = sc.get("sea_view", 0) >= 0.6
    covered = ("umbrella" in tags) or not outdoor
    privacy = ("private room" if t["zone"] == "private"
               else "semi-private" if sc.get("privacy", 0) > 0.7 else "open room")
    best = []
    if sc.get("romantic", 0) > 0.7:
        best.append("a date")
    if t["max_party"] >= 6:
        best.append("a group")
    if sc.get("quiet", 0) > 0.75:
        best.append("quiet conversation")
    if sc.get("business", 0) > 0.62:
        best.append("a working dinner")
    if sc.get("family", 0) > 0.6:
        best.append("families")
    if near_water:
        best.append("watching the water")
    if t["zone"] == "bar":
        best.append("drinks and small plates")
    if sc.get("stage_view", 0) > 0.7:
        best.append("live music nights")
    return {
        "indoor": not outdoor,
        "outdoor": outdoor,
        "smoking": outdoor,                       # smoking only outdoors
        "shade": "covered" if covered else "open air",
        "near_water": near_water,
        "noise": noise_level,
        "privacy": privacy,
        "romantic": sc.get("romantic", 0) > 0.72,
        "family": sc.get("family", 0) > 0.6,
        "group": t["max_party"] >= 6,
        "accessible": bool(t.get("accessible")),
        "window": sc.get("window_proximity", 0) > 0.6 and not outdoor,
        "premium_view": bool(t.get("premium_view")),
        "bar_m": int(round(d.get("bar", 0) * u)),
        "kitchen_m": int(round(d.get("kitchen", 0) * u)),
        "entrance_m": int(round(d.get("entrance", 0) * u)),
        "water_m": int(round(max(0.0, (t.get("x", 0) - 62) * u))),
        "best_for": best[:4],
        "seats": "%d–%d" % (t["min_party"], t["max_party"]),
        "zone_name": t.get("zone_name") or zone.get("name") or t["zone"],
        "setting": ("outdoors" if outdoor else "indoors"),
    }


def describe_table(t):
    """A one-paragraph, human answer for 'tell me about table 12'."""
    a = t.get("attributes") or {}
    bits = ["Table %s is in the %s, %s" % (t["label"], a.get("zone_name", t["zone"]), a.get("setting", "")),
            "seats %s" % a.get("seats", ""),
            a.get("noise", "") + (" and near the water" if a.get("near_water") else ""),
            ("smoking permitted" if a.get("smoking") else "non-smoking"),
            a.get("shade", ""), a.get("privacy", "")]
    if a.get("accessible"):
        bits.append("step-free")
    text = ", ".join(b for b in bits if b) + "."
    if a.get("best_for"):
        text += " Best for " + ", ".join(a["best_for"][:3]) + "."
    return text


# ------------------------------------------------------------------ time
# The clock, the opening hours and the booking length are the restaurant's,
# not this application's: they come from SUFRA OS so a change in the manager's
# settings reaches the 3D scene without a second edit.

def to_min(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def to_hhmm(minutes):
    return "%02d:%02d" % (int(minutes) // 60, int(minutes) % 60)


def service():
    return nova.venue()["service"]


def slots(date=None):
    return nova.venue()["slots"]


def buffer_min():
    return service()["turnover_buffer"]


def hold_seconds():
    return nova.venue()["hold_seconds"]


def today():
    return nova.venue()["today"]


def availability(date, time_hhmm, party_size, duration=None, session_id=None):
    return nova.availability(date, time_hhmm, party_size, duration, session_id)


# ------------------------------------------------------ preference ranking
LEXICON = [
    (("quiet", "peaceful", "calm", "not noisy", "away from noise", "sedate"),
     {"quiet": 2.4, "lively": -1.6}),
    (("lively", "buzzy", "buzz", "atmosphere", "energetic", "fun", "vibe"),
     {"lively": 2.2, "quiet": -1.2}),
    (("romantic", "date", "anniversary", "proposal", "propose", "engagement",
      "intimate", "candlelit"), {"romantic": 2.8, "privacy": 1.4, "quiet": 1.0}),
    (("window", "by the window", "near a window"), {"window_proximity": 2.8}),
    (("view", "best view", "scenic", "looking out"), {"view": 2.6}),
    (("water", "sea", "seaside", "waterfront", "harbour", "harbor", "sea view",
      "ocean", "view of the water"), {"sea_view": 3.0, "view": 1.6}),
    (("stage", "band", "live music", "music"), {"stage_view": 2.6, "lively": 1.0}),
    (("terrace", "outside", "outdoor", "al fresco", "fresh air", "patio"),
     {"_zone_terrace": 3.0, "_zone_garden": 2.0}),
    (("garden", "greenery", "plants", "leafy"), {"_zone_garden": 2.8}),
    (("private", "privacy", "discreet", "own room", "closed door", "secluded"),
     {"privacy": 3.0, "_zone_private": 2.4}),
    (("bar", "at the bar", "counter", "high top", "drinks"),
     {"_zone_bar": 3.0, "lively": 1.2}),
    (("business", "work dinner", "client", "meeting", "colleagues"),
     {"business": 2.6, "quiet": 1.2, "privacy": 1.0}),
    (("family", "kids", "children", "child", "high chair", "toddler"),
     {"family": 2.4, "quiet": 0.6}),
    (("accessible", "wheelchair", "step free", "step-free", "mobility"),
     {"_accessible": 99.0}),
    (("fireplace", "fire", "by the fire"), {"_fireplace": 2.4}),
    (("not near the entrance", "away from the door", "away from the entrance",
      "not by the door"), {"_far_entrance": 2.2}),
    (("not near the kitchen", "away from the kitchen"), {"_far_kitchen": 2.0}),
    (("big table", "large table", "group", "party of", "celebration"),
     {"_capacity": 1.6}),
    (("best available", "anything", "whatever", "surprise me", "no preference"),
     {}),
]

PRESETS = {
    "best": {},
    "quiet": {"quiet": 2.4, "lively": -1.2},
    "window": {"window_proximity": 2.8, "view": 1.2},
    "terrace": {"_zone_terrace": 3.0},
    "garden": {"_zone_garden": 2.8},
    "private": {"privacy": 3.0, "_zone_private": 2.4},
    "bar": {"_zone_bar": 3.0, "lively": 1.2},
    "romantic": {"romantic": 2.8, "privacy": 1.4},
    "lively": {"lively": 2.2},
    "accessible": {"_accessible": 99.0},
    "view": {"view": 2.6},
    "sea": {"sea_view": 3.0, "view": 1.4},
    "stage": {"stage_view": 2.6},
    "indoor": {"_indoor": 99.0},
    "shade": {"_shade": 99.0},
    "family": {"family": 2.6, "quiet": 0.4},
}

REASON_TEXT = {
    "quiet": "quiet corner", "lively": "lively spot",
    "romantic": "romantic", "privacy": "private",
    "window_proximity": "by a window", "view": "strong view",
    "business": "good for a working dinner", "family": "family friendly",
    "sea_view": "sea view", "stage_view": "facing the stage",
    "_zone_terrace": "out on the deck", "_zone_garden": "in the garden room",
    "_zone_private": "in the private room", "_zone_bar": "at the bar",
    "_accessible": "step-free access", "_fireplace": "near the fireplace",
    "_indoor": "indoors, non-smoking", "_shade": "under cover",
    "_far_entrance": "away from the entrance", "_far_kitchen": "away from the kitchen",
    "_capacity": "sized for your party",
}


def _word(text, phrase):
    import re
    return re.search(r"\b" + re.escape(phrase) + r"\b", text) is not None


def parse_preference(free_text, preset=None):
    weights = dict(PRESETS.get(preset or "best", {}))
    matched = []
    text = (free_text or "").lower()
    for phrases, w in LEXICON:
        if any(_word(text, p) for p in phrases):
            matched.append(phrases[0])
            for k, v in w.items():
                weights[k] = weights.get(k, 0) + v
    return weights, matched


def score_table(t, weights, party_size):
    sc = t.get("scores") or {}
    dist = t.get("distances") or {}
    tags = t.get("tags") or []
    total, why = 0.0, []
    for key, w in weights.items():
        if key.startswith("_"):
            if key == "_zone_terrace":
                v = 1.0 if t["zone"] == "terrace" else 0.0
            elif key == "_zone_garden":
                v = 1.0 if t["zone"] == "garden" else 0.0
            elif key == "_zone_private":
                v = 1.0 if t["zone"] == "private" else 0.0
            elif key == "_zone_bar":
                v = 1.0 if t["zone"] == "bar" else 0.0
            elif key == "_accessible":
                v = 1.0 if t.get("accessible") else 0.0
            elif key == "_fireplace":
                v = max(0.0, 1.0 - dist.get("fireplace", 400) / 400.0)
            elif key == "_far_entrance":
                v = min(1.0, dist.get("entrance", 0) / 600.0)
            elif key == "_far_kitchen":
                v = min(1.0, dist.get("kitchen", 0) / 500.0)
            elif key == "_capacity":
                v = 1.0 if t["max_party"] >= (party_size or 2) + 2 else 0.4
            elif key == "_indoor":
                v = 0.0 if t["zone"] in ("garden", "lounge", "terrace") else 1.0
            elif key == "_shade":
                v = 1.0 if ("umbrella" in tags or t["zone"] not in ("garden", "lounge", "terrace")) else 0.0
            else:
                v = 0.0
        else:
            v = sc.get(key, 0.0)
        total += w * v
        if w > 0 and v > 0.55 and key in REASON_TEXT:
            why.append(REASON_TEXT[key])

    # capacity efficiency: don't burn an eight-top on a couple
    if party_size:
        waste = t["max_party"] - party_size
        total -= 0.42 * max(0, waste)
        if waste == 0:
            why.append("exactly the right size")
    total += 0.5 * sc.get("view", 0)
    return total, why


def event_config(event):
    return (geometry()[0].get("events") or {}).get(event or "dinner") or {}


def recommend(date, time_hhmm, party_size, preset=None, free_text=None,
              duration=None, session_id=None, limit=6, event=None):
    """Rank the tables that are genuinely bookable for the chosen slot.

    Bookability comes from SUFRA OS; the ordering is this application's own
    reading of the room. A table the OS says is taken can never be
    recommended, however well it scores.
    """
    date = date or today()
    avail = availability(date, time_hhmm, party_size, duration, session_id)
    tmap = table_map()
    weights, matched = parse_preference(free_text, preset)

    cfg = event_config(event)
    for k, v in (cfg.get("boost") or {}).items():
        weights[k] = weights.get(k, 0) + v
    only_zones = cfg.get("only_zones")
    clear_zones = cfg.get("clear_zones") or []

    eligible, blocked = [], []
    for row in avail["tables"]:
        t = tmap.get(row["table_id"])
        if not t:
            continue
        if only_zones and t["zone"] not in only_zones:
            continue
        if t["zone"] in clear_zones:
            continue
        if row["bookable"]:
            score, why = score_table(t, weights, party_size)
            eligible.append({"table": t, "score": round(score, 3), "why": why[:3],
                             "state": row["state"]})
        else:
            blocked.append({"table_id": t["id"], "label": t["label"],
                            "state": row["state"], "reason": row["reason"],
                            "next_available": row["next_available"]})
    eligible.sort(key=lambda e: -e["score"])
    return {
        "date": avail["date"], "time": avail["time"], "party_size": party_size,
        "duration": avail["duration"],
        "matched_preferences": matched,
        "weights": weights,
        "recommended": eligible[:limit],
        "eligible_count": len(eligible),
        "unavailable": blocked,
        "is_past": avail.get("is_past", False),
        "is_closed": avail.get("is_closed", False),
        "event": event or "dinner",
        "event_config": cfg,
    }


def day_summary(date):
    live = nova.live()
    return {"date": date, "counts": live["counts"]}
