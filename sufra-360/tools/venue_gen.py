"""
SUFRA Immersive - venue generator.

"Sufra Waterfront", laid out to match the reference composition:
water and a lamplit promenade down the west side, a walled garden court at
the north, the main dining room with a long bar spine through the middle,
a window row along the flower wall to the east, restrooms and a private
room at the south of the building, and an umbrella terrace beyond it.

Map space: 720 x 1280 units, origin top-left.  1 unit = 0.05 m.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENUE = os.path.join(ROOT, "venue")

MAP_W, MAP_H = 720, 1280
UNITS_TO_M = 0.05
BUILD = "6"

# ---------------------------------------------------------------- geometry
WATER = (0, 0, 62, MAP_H)
PROMENADE = (62, 0, 232, MAP_H)
PLOT = (236, 56, 704, 1244)
BUILDING = (246, 78, 692, 986)

ROOMS = {
    "garden":  (258, 92, 680, 298),      # walled court at the north
    "window":  (258, 302, 360, 848),     # west row, faces the promenade
    "main":    (360, 302, 560, 848),     # the spine, bar and pass
    "east":    (560, 302, 680, 848),     # east row along the flower wall
    "lounge":  (500, 96, 680, 296),      # sofas, where a duo plays
    "private": (286, 856, 470, 972),
    "wc":      (478, 856, 596, 934),
    "terrace": (250, 1000, 690, 1238),
}

BAR_COUNTER = (378, 420, 432, 660)
BACK_BAR = (446, 420, 496, 660)
PASS = (382, 700, 556, 792)
ENTRANCE = (652, 976)
FIREPLACE = (300, 800)

NOISE_SOURCES = [
    (410, 540, 1.00),    # bar
    (652, 976, 0.72),    # entrance
    (468, 746, 0.86),    # kitchen pass
    (590, 190, 0.80),    # lounge, live duo
]

WINDOWS = [
    (246, 302, 246, 848),     # west wall, promenade and water beyond
    (692, 302, 692, 848),     # east wall, the flower wall
    (258, 92, 680, 92),       # garden court, open to the north
]

TREES = [(120, 118, 46), (150, 248, 40), (108, 372, 44), (152, 470, 38),
         (112, 600, 46), (150, 700, 36), (110, 820, 44), (148, 930, 40),
         (112, 1050, 46), (150, 1170, 38), (198, 190, 27), (198, 560, 25),
         (198, 900, 26), (198, 1120, 24), (300, 132, 22), (648, 128, 20),
         (272, 1180, 20), (660, 1186, 20)]
LAMPS = [(80, 62, 1), (80, 192, 1), (80, 322, 1), (80, 452, 1), (80, 582, 1),
         (80, 712, 1), (80, 842, 1), (80, 972, 1), (80, 1102, 1), (80, 1232, 1),
         (214, 128, 1), (214, 418, 1), (214, 718, 1), (214, 1018, 1),
         (300, 200, 0), (600, 200, 0), (300, 560, 0), (620, 560, 0),
         (300, 900, 0), (620, 900, 0), (350, 1090, 1), (560, 1090, 1)]
BOATS = []
JETTY = (0, 0, 0, 0)
KIOSK = (66, 782, 100, 838)

WALK_PATHS = [
    [(652, 966), (600, 900), (540, 860), (500, 780), (470, 660), (440, 500), (430, 340)],
    [(300, 320), (300, 460), (304, 620), (312, 760), (330, 840)],
    [(620, 330), (626, 470), (626, 620), (612, 760), (570, 840)],
    [(340, 1080), (450, 1120), (600, 1104), (664, 1010)],
    [(120, 120), (140, 400), (130, 700), (150, 1000), (140, 1230)],
    [(200, 1200), (200, 900), (200, 600), (200, 300)],
    [(470, 160), (560, 180), (640, 200)],
    [(470, 300), (470, 420), (466, 620), (470, 780)],
]

# (id, label, zone, shape, w, h, min, max, x, y, rot, tags)
TABLE_DEFS = [
    # garden court, north
    ("t01", "1",  "garden", "round", 62, 62, 2, 4, 322, 168, 0, ["outside", "leafy"]),
    ("t02", "2",  "garden", "round", 62, 62, 2, 4, 440, 210, 0, ["outside", "leafy"]),
    ("t03", "3",  "garden", "round", 52, 52, 2, 2, 344, 262, 0, ["outside", "romantic"]),
    ("t04", "4",  "garden", "rect",  58, 96, 4, 6, 452, 122, 0, ["outside", "group"]),
    ("t05", "5",  "garden", "round", 52, 52, 2, 2, 556, 262, 0, ["outside", "romantic"]),
    ("t06", "6",  "lounge", "round", 56, 56, 2, 4, 592, 150, 0, ["lounge", "lively", "stage_view"]),
    ("t07", "7",  "lounge", "round", 56, 56, 2, 4, 654, 216, 0, ["lounge", "lively", "stage_view"]),

    # west row, windows onto the promenade and the water
    ("t08", "8",  "window", "round", 58, 58, 2, 4, 302, 372, 0, ["window", "water_view"]),
    ("t09", "9",  "window", "round", 58, 58, 2, 4, 302, 462, 0, ["window", "water_view"]),
    ("t10", "10", "window", "rect",  58, 150, 6, 8, 304, 596, 0, ["window", "water_view", "group"]),
    ("t11", "11", "window", "round", 58, 58, 2, 4, 302, 726, 0, ["window", "water_view"]),
    ("t12", "12", "window", "round", 52, 52, 2, 2, 302, 812, 0, ["window", "water_view", "romantic"]),

    # bar spine
    ("t13", "13", "bar", "round", 42, 42, 2, 2, 350, 452, 0, ["bar", "high_top", "lively"]),
    ("t14", "14", "bar", "round", 42, 42, 2, 2, 350, 528, 0, ["bar", "high_top", "lively"]),
    ("t15", "15", "bar", "round", 42, 42, 2, 2, 350, 604, 0, ["bar", "high_top", "lively"]),

    # east row along the flower wall
    ("t16", "16", "east", "round", 62, 62, 2, 4, 620, 372, 0, ["window", "garden_view"]),
    ("t17", "17", "east", "round", 62, 62, 2, 4, 620, 466, 0, ["window", "garden_view"]),
    ("t18", "18", "east", "round", 62, 62, 2, 4, 620, 560, 0, ["window", "garden_view"]),
    ("t19", "19", "east", "round", 62, 62, 2, 4, 620, 654, 0, ["window", "garden_view"]),
    ("t20", "20", "east", "round", 56, 56, 2, 2, 620, 780, 0, ["window", "quiet", "romantic"]),

    ("t21", "21", "private", "rect", 130, 62, 6, 10, 378, 912, 0, ["private", "quiet"]),

    # umbrella terrace, south
    ("t22", "22", "terrace", "round", 66, 66, 2, 4, 340, 1082, 0, ["outside", "umbrella"]),
    ("t23", "23", "terrace", "round", 66, 66, 2, 4, 452, 1128, 0, ["outside", "umbrella"]),
    ("t24", "24", "terrace", "round", 66, 66, 2, 4, 606, 1108, 0, ["outside", "umbrella"]),
    ("t25", "25", "terrace", "round", 50, 50, 2, 2, 330, 1186, 0, ["outside", "romantic"]),
]

ZONE_META = {
    "garden":  {"name": "Garden Court", "floor": 0, "outdoor": True,
                "blurb": "Walled court at the front, under the vines and string lights."},
    "lounge":  {"name": "The Lounge", "floor": 0, "outdoor": True,
                "blurb": "Low sofas in the corner of the court. A duo plays here on weekends."},
    "window":  {"name": "Promenade Windows", "floor": 0, "outdoor": False,
                "blurb": "West row. Windows onto the lamplit promenade and the water."},
    "bar":     {"name": "The Bar", "floor": 0, "outdoor": False,
                "blurb": "High tops along the marble counter."},
    "east":    {"name": "Flower Wall", "floor": 0, "outdoor": False,
                "blurb": "East row, windows onto the flowering wall."},
    "private": {"name": "Private Room", "floor": 0, "outdoor": False,
                "blurb": "A door that closes. Six to ten guests."},
    "terrace": {"name": "Umbrella Terrace", "floor": 0, "outdoor": True,
                "blurb": "Umbrella tables under the string lights, facing the water."},
}

EVENTS = {
    "dinner": {"name": "Seated dinner",
               "blurb": "Full a la carte service, every table laid.",
               "capacity": None, "min_spend": 0},
    "reception": {"name": "Standing reception",
                  "blurb": "Main room cleared, the bar and the garden court in play, canapes circulating.",
                  "capacity": 150, "min_spend": 4500,
                  "clear_zones": ["window", "east"]},
    "live_music": {"name": "Live music night",
                   "blurb": "A duo in the lounge corner of the court from 20:00.",
                   "capacity": 100, "min_spend": 3200,
                   "boost": {"stage_view": 2.5, "lively": 1.4}},
    "private_dinner": {"name": "Private dinner",
                       "blurb": "The private room, doors closed, set menu.",
                       "capacity": 10, "min_spend": 900,
                       "only_zones": ["private"]},
}

PRICING = {
    "currency": "GBP", "symbol": "\u00a3",
    "avg_per_head_dinner": 58,
    "set_menu": [{"name": "Three courses", "price": 45},
                 {"name": "Tasting menu", "price": 78},
                 {"name": "Canape package", "price": 32}],
    "deposit_per_head": 20, "private_room_hire": 350,
    "full_venue_hire": 6000, "service_charge_pct": 12.5,
}

LOGISTICS = {
    "seated_capacity": 0, "standing_capacity": 150,
    "step_free": True, "accessible_wc": True,
    "nearest_transport": "6 minutes on foot along the promenade",
    "parking": "Public car park 200 m north, 40 spaces",
    "load_in": "Service gate on the promenade side, 1.9 m clear",
    "av": "House PA in the court, two wireless mics, DI box in the lounge corner",
    "stage_size_m": "3.2 m x 2.4 m lounge corner, no riser",
    "curfew": "Amplified music until 22:30 outdoors, 23:00 indoors",
    "kitchen_last_orders": "21:45",
}


def dist(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def bearing(ax, ay, bx, by):
    return math.degrees(math.atan2(bx - ax, -(by - ay))) % 360


def dist_to_segment(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return dist(px, py, x1, y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return dist(px, py, x1 + t * dx, y1 + t * dy)


def nearest_window_point(x, y):
    best, bd = None, 1e9
    for (x1, y1, x2, y2) in WINDOWS:
        dx, dy = x2 - x1, y2 - y1
        t = 0.0 if (dx == 0 and dy == 0) else max(0.0, min(1.0, (
            (x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        cx, cy = x1 + t * dx, y1 + t * dy
        d = dist(x, y, cx, cy)
        if d < bd:
            best, bd = (cx, cy), d
    return best


def clamp01(v):
    return max(0.0, min(1.0, v))


def noise_at(x, y):
    total = 0.0
    for sx, sy, strength in NOISE_SOURCES:
        d = max(30.0, dist(x, y, sx, sy))
        total += strength * (150.0 / d) ** 1.35
    return clamp01(total / 4.0)


def seat_ring(t):
    n = t["max_party"]
    out = []
    if t["shape"] == "round":
        r = t["w"] / 2 + 19
        for i in range(n):
            a = (2 * math.pi * i / n) - math.pi / 2
            out.append((t["x"] + r * math.cos(a), t["y"] + r * math.sin(a)))
    else:
        w, h = t["w"], t["h"]
        vertical = h > w
        per = max(1, n // 2)
        for i in range(n):
            side, k = i % 2, i // 2
            f = (k + 0.5) / per
            if vertical:
                out.append((t["x"] + (w / 2 + 19) * (1 if side else -1),
                            t["y"] - h / 2 + f * h))
            else:
                out.append((t["x"] - w / 2 + f * w,
                            t["y"] + (h / 2 + 19) * (1 if side else -1)))
    return out[:n]


def build():
    tables, seats = [], []

    for (tid, label, zone, shape, w, h, mn, mx, x, y, rot, tags) in TABLE_DEFS:
        noise = noise_at(x, y)
        wd = dist(x, y, *nearest_window_point(x, y))
        outdoor = ZONE_META[zone]["outdoor"]
        water = "water_view" in tags or zone == "terrace"

        quiet = clamp01(1.0 - noise)
        window_prox = clamp01(1.0 - wd / 260.0)
        view = clamp01(0.24 + 0.48 * window_prox + (0.24 if water else 0.0) +
                       (0.10 if outdoor else 0.0))
        privacy = clamp01(0.28 + (0.50 if zone == "private" else 0) + 0.25 * quiet +
                          (0.10 if "romantic" in tags else 0) -
                          (0.22 if zone == "bar" else 0))
        romantic = clamp01(0.16 + 0.32 * quiet + 0.26 * view +
                           (0.26 if "romantic" in tags else 0))
        lively = clamp01(0.12 + 0.72 * noise + (0.18 if zone == "bar" else 0))
        business = clamp01(0.22 + 0.36 * quiet + 0.32 * privacy)
        family = clamp01(0.28 + 0.30 * (mx >= 4) + 0.22 * outdoor -
                         0.30 * (zone == "bar"))
        stage_view = clamp01(1.0 - dist(x, y, 590, 190) / 620.0)

        t = {
            "id": tid, "label": label, "zone": zone, "shape": shape,
            "min_party": mn, "max_party": mx,
            "x": x, "y": y, "w": w, "h": h, "rotation": rot,
            "world": {"x": round((x - MAP_W / 2) * UNITS_TO_M, 3), "y": 0.75,
                      "z": round((y - MAP_H / 2) * UNITS_TO_M, 3)},
            "tags": tags,
            "scores": {
                "quiet": round(quiet, 3), "noise": round(noise, 3),
                "view": round(view, 3), "privacy": round(privacy, 3),
                "romantic": round(romantic, 3), "lively": round(lively, 3),
                "business": round(business, 3), "family": round(family, 3),
                "window_proximity": round(window_prox, 3),
                "sea_view": round(1.0 if water else 0.35 * window_prox, 3),
                "stage_view": round(stage_view, 3),
            },
            "distances": {
                "window": round(wd, 1),
                "entrance": round(dist(x, y, *ENTRANCE), 1),
                "bar": round(dist(x, y, 410, 540), 1),
                "kitchen": round(dist(x, y, 468, 746), 1),
                "stage": round(dist(x, y, 590, 190), 1),
                "fireplace": round(dist(x, y, *FIREPLACE), 1),
            },
            "bearings": {
                "sea": round(bearing(x, y, 30, y), 1),
                "window": round(bearing(x, y, *nearest_window_point(x, y)), 1),
                "bar": round(bearing(x, y, 410, 540), 1),
                "stage": round(bearing(x, y, 590, 190), 1),
                "entrance": round(bearing(x, y, *ENTRANCE), 1),
                "kitchen": round(bearing(x, y, 468, 746), 1),
            },
            "accessible": zone != "bar",
            "premium_view": view > 0.78,
            "combinable_with": [],
            "verification": "PLACEHOLDER",
        }
        tables.append(t)

        labels = "ABCDEFGHIJ"
        for i, (sx, sy) in enumerate(seat_ring(t)):
            seats.append({
                "id": "%s-%s" % (tid, labels[i]), "table_id": tid,
                "label": "Seat %s" % labels[i],
                "x": round(sx, 1), "y": round(sy, 1),
                "eye": {"x": round((sx - MAP_W / 2) * UNITS_TO_M, 3), "y": 1.18,
                        "z": round((sy - MAP_H / 2) * UNITS_TO_M, 3)},
                "yaw": round(bearing(sx, sy, t["x"], t["y"]), 1),
                "pitch": 0.0,
                "panorama": "/assets/panoramas/%s.jpg?v=%s" % (tid, BUILD),
                "verification": "PLACEHOLDER",
            })

    for a in tables:
        for b in tables:
            if a is not b and a["zone"] == b["zone"] and \
                    dist(a["x"], a["y"], b["x"], b["y"]) < 140:
                a["combinable_with"].append(b["id"])

    LOGISTICS["seated_capacity"] = sum(t["max_party"] for t in tables)

    zones = [dict(id=z, bounds=ROOMS.get(z, ROOMS["main"]), **meta)
             for z, meta in ZONE_META.items()]

    floor = {
        "venue_id": "sufra-waterfront", "name": "Sufra Waterfront",
        "tagline": "Garden court, promenade windows and umbrella terrace",
        "address": "Bulvar, Baku",
        "timezone": "Asia/Baku", "weather_city": "Baku",
        "weather": {"lat": 40.4093, "lng": 49.8671},
        "map": {"width": MAP_W, "height": MAP_H,
                "image": "/assets/map/ground.png?v=" + BUILD,
                "units_to_m": UNITS_TO_M},
        "geometry": {
            "water": WATER, "sea": WATER, "promenade": PROMENADE, "plot": PLOT,
            "building": BUILDING, "rooms": ROOMS,
            "bar_counter": BAR_COUNTER, "back_bar": BACK_BAR, "pass": PASS,
            "wc": ROOMS["wc"], "kiosk": KIOSK,
            "entrance": ENTRANCE, "fireplace": FIREPLACE,
            "noise_sources": NOISE_SOURCES, "windows": WINDOWS,
            "trees": TREES, "lamps": LAMPS, "boats": BOATS, "jetty": JETTY,
            "walk_paths": WALK_PATHS,
        },
        "service": {"open": "12:00", "close": "23:00", "slot_minutes": 15,
                    "default_duration": 105, "turnover_buffer": 15,
                    "last_seating": "21:30"},
        "events": EVENTS, "pricing": PRICING, "logistics": LOGISTICS,
        "verification": "PLACEHOLDER",
    }

    os.makedirs(VENUE, exist_ok=True)
    for name, payload in (("floor", floor), ("tables", tables),
                          ("seats", seats), ("zones", zones)):
        json.dump(payload, open(os.path.join(VENUE, name + ".json"), "w"), indent=1)

    print("venue: %d tables, %d seats, seated capacity %d"
          % (len(tables), len(seats), LOGISTICS["seated_capacity"]))
    return floor, tables, seats


if __name__ == "__main__":
    build()
