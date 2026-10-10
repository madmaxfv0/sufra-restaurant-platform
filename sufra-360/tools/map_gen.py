"""
SUFRA Immersive - illustrated map generator (high detail).

Draws the venue from venue/*.json: sea with boats and wake, timber deck,
a full-height glass wall, herringbone floor, a stage, a marble bar with
stools, laid tables with plates, glasses and cutlery, and seated guests.

Outputs assets/map/ground.png at 2x.
"""
import json
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENUE = os.path.join(ROOT, "venue")
OUT = os.path.join(ROOT, "assets", "map")

S = 3                       # supersample
rnd = random.Random(20260903)

SEA_DEEP = (18, 54, 88)
SEA_MID = (38, 92, 136)
SEA_FOAM = (128, 178, 210)
DECK_WOOD = (156, 122, 84)
DECK_DARK = (112, 84, 56)
FLOOR = (138, 92, 54)
FLOOR_DARK = (102, 64, 36)
STONE = (176, 168, 154)
WALL = (34, 34, 40)
WALL_IN = (62, 58, 62)
GLASS = (150, 196, 214)
MARBLE = (216, 214, 210)
LINEN = (244, 232, 208)
CHAIR_W = (118, 82, 50)
CHAIR_D = (78, 52, 30)
SKIN = [(226, 190, 158), (198, 156, 122), (150, 108, 76), (108, 76, 52),
        (238, 208, 180), (172, 128, 92)]
HAIR = [(38, 28, 24), (72, 46, 28), (26, 22, 22), (140, 104, 62), (96, 66, 44),
        (52, 36, 30)]
CLOTH = [(62, 80, 122), (128, 62, 72), (58, 88, 78), (98, 84, 118), (52, 58, 70),
         (140, 110, 76), (86, 70, 62), (176, 88, 78), (70, 110, 128)]
GREEN = [(34, 66, 40), (48, 90, 48), (64, 116, 56), (86, 138, 66)]
LAMP = (255, 208, 142)


def px(v):
    return int(round(v * S))


def rect(d, box, fill, outline=None, width=1, radius=0):
    x1, y1, x2, y2 = [px(v) for v in box]
    if radius:
        d.rounded_rectangle([x1, y1, x2, y2], radius=px(radius), fill=fill,
                            outline=outline, width=max(1, px(width)))
    else:
        d.rectangle([x1, y1, x2, y2], fill=fill, outline=outline,
                    width=max(1, px(width)))


def circ(d, cx, cy, r, fill, outline=None, width=1):
    d.ellipse([px(cx - r), px(cy - r), px(cx + r), px(cy + r)],
              fill=fill, outline=outline, width=max(1, px(width)))


def line(d, x1, y1, x2, y2, fill, width=1):
    d.line([px(x1), px(y1), px(x2), px(y2)], fill=fill, width=max(1, px(width)))


def jit(c, a):
    return tuple(max(0, min(255, int(v + rnd.uniform(-a, a)))) for v in c)


# ------------------------------------------------------------------ pieces
def draw_sea(d, box, boats, jetty):
    x1, y1, x2, y2 = box
    for y in range(int(y1), int(y2)):
        t = (y - y1) / max(1.0, y2 - y1)
        c = (int(SEA_DEEP[0] + 8 * math.sin(t * 6)),
             int(SEA_DEEP[1] + 10 * math.sin(t * 5)),
             int(SEA_DEEP[2] + 12 * math.sin(t * 4)))
        line(d, x1, y, x2, y, c, 1)
    for i in range(1400):
        x = rnd.uniform(x1, x2)
        y = rnd.uniform(y1, y2)
        w = rnd.uniform(6, 30)
        line(d, x, y, x + w, y + rnd.uniform(-1, 1), jit(SEA_MID, 22),
             rnd.uniform(0.5, 1.6))
    for i in range(340):
        x = rnd.uniform(x1 + 4, x2 - 8)
        y = rnd.uniform(y1, y2)
        line(d, x, y, x + rnd.uniform(3, 11), y, jit(SEA_FOAM, 26), 0.8)

    # jetty
    jx1, jy1, jx2, jy2 = jetty
    rect(d, jetty, DECK_DARK)
    for x in range(int(jx1), int(jx2), 6):
        line(d, x, jy1, x, jy2, jit(DECK_WOOD, 14), 1.4)
    for x in range(int(jx1) + 4, int(jx2), 14):
        circ(d, x, jy1 - 3, 2.6, (62, 48, 38))
        circ(d, x, jy2 + 3, 2.6, (62, 48, 38))

    # boats with wake
    for (bx, by, ln, ang) in boats:
        a = math.radians(ang)
        dx, dy = math.sin(a), -math.cos(a)
        hx, hy = bx + dx * ln / 2, by + dy * ln / 2
        tx, ty = bx - dx * ln / 2, by - dy * ln / 2
        pxv, pyv = -dy, dx
        beam = ln * 0.30
        d.polygon([(px(hx), px(hy)),
                   (px(bx + pxv * beam / 2), px(by + pyv * beam / 2)),
                   (px(tx + pxv * beam * 0.34), px(ty + pyv * beam * 0.34)),
                   (px(tx - pxv * beam * 0.34), px(ty - pyv * beam * 0.34)),
                   (px(bx - pxv * beam / 2), px(by - pyv * beam / 2))],
                  fill=(232, 228, 216), outline=(150, 142, 128))
        d.polygon([(px(hx - dx * ln * 0.18), px(hy - dy * ln * 0.18)),
                   (px(bx + pxv * beam * 0.30), px(by + pyv * beam * 0.30)),
                   (px(tx + pxv * beam * 0.18), px(ty + pyv * beam * 0.18)),
                   (px(tx - pxv * beam * 0.18), px(ty - pyv * beam * 0.18)),
                   (px(bx - pxv * beam * 0.30), px(by - pyv * beam * 0.30))],
                  fill=(58, 72, 88))
        circ(d, bx, by, beam * 0.20, (188, 168, 132))
        for k in range(9):
            f = k / 9.0
            wx = tx - dx * (6 + f * 30)
            wy = ty - dy * (6 + f * 30)
            sp = beam * (0.5 + f * 1.5)
            line(d, wx - pxv * sp, wy - pyv * sp, wx + pxv * sp, wy + pyv * sp,
                 (110, 152, 186), 1.0)


def draw_deck(d, box):
    x1, y1, x2, y2 = box
    rect(d, box, DECK_WOOD)
    for y in range(int(y1), int(y2), 9):
        rect(d, (x1, y, x2, y + 8), jit(DECK_WOOD, 12))
        line(d, x1, y, x2, y, DECK_DARK, 0.7)
    for i in range(900):
        x, y = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        line(d, x, y, x + rnd.uniform(4, 12), y, jit(DECK_DARK, 12), 0.6)
    # rail along the water
    line(d, x1 + 2, y1, x1 + 2, y2, (74, 56, 40), 3)
    for y in range(int(y1), int(y2), 18):
        circ(d, x1 + 2, y, 2.6, (96, 74, 52))


def draw_herringbone(d, box, base, dark, step=11):
    x1, y1, x2, y2 = box
    rect(d, box, base)
    for j, y in enumerate(range(int(y1), int(y2) + step, step)):
        for i, x in enumerate(range(int(x1), int(x2) + step, step)):
            up = (i + j) % 2 == 0
            col = jit(base, 12)
            if up:
                pts = [(x, y + step), (x + step, y), (x + step, y + 3), (x + 3, y + step)]
            else:
                pts = [(x, y), (x + step, y + step), (x + step - 3, y + step), (x, y + 3)]
            d.polygon([(px(a), px(b)) for a, b in pts], fill=col)
    for i in range(2600):
        x, y = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        line(d, x, y, x + rnd.uniform(3, 10), y, jit(dark, 9), 0.6)


def draw_umbrella(d, cx, cy, r=46):
    circ(d, cx + 3, cy + 5, r, (30, 24, 20))
    circ(d, cx, cy, r, (236, 228, 210), outline=(196, 186, 166), width=1.2)
    for i in range(10):
        a = math.tau * i / 10
        line(d, cx, cy, cx + math.cos(a) * r, cy + math.sin(a) * r,
             (208, 198, 178), 1.1)
    circ(d, cx, cy, r * 0.5, (244, 238, 222))
    circ(d, cx, cy, 3.0, (120, 96, 68))


def draw_promenade(d, box):
    x1, y1, x2, y2 = box
    rect(d, box, (188, 172, 146))
    y, row = y1, 0
    while y < y2:
        x = x1 + (13 if row % 2 else 0)
        while x < x2:
            w = rnd.uniform(15, 25)
            rect(d, (x + 1, y + 1, x + w - 1, y + 11), jit((188, 172, 146), 12),
                 outline=jit((146, 130, 106), 10), width=0.5, radius=2)
            x += w
        y += 13
        row += 1
    rect(d, (x1 - 3, y1, x1 + 5, y2), (84, 76, 64))
    for y in range(int(y1), int(y2), 24):
        circ(d, x1 + 1, y + 12, 3.2, (52, 48, 44))


def draw_terrace(d, box):
    x1, y1, x2, y2 = box
    rect(d, box, (176, 150, 116))
    for y in range(int(y1), int(y2), 20):
        line(d, x1, y, x2, y, (146, 122, 92), 0.8)
    for x in range(int(x1), int(x2), 20):
        line(d, x, y1, x, y2, (146, 122, 92), 0.8)
    for i in range(1400):
        cx, cy = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        circ(d, cx, cy, rnd.uniform(0.7, 2.2), jit((176, 150, 116), 14))


def draw_flower_wall(d, box):
    x1, y1, x2, y2 = box
    n = int((abs(x2 - x1) + abs(y2 - y1)) * 2.4)
    for i in range(n):
        cx, cy = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        circ(d, cx, cy, rnd.uniform(2.6, 5.6), jit(rnd.choice(GREEN), 12))
    for i in range(int(n * 0.34)):
        circ(d, rnd.uniform(x1, x2), rnd.uniform(y1, y2), rnd.uniform(1.2, 2.4),
             rnd.choice([(198, 96, 148), (170, 92, 178), (216, 132, 100),
                         (232, 182, 100), (236, 226, 236)]))


def draw_lounge(d, box):
    x1, y1, x2, y2 = box
    for k in range(2):
        sx = x1 + 12 + k * 92
        rect(d, (sx, y1 + 16, sx + 74, y1 + 50), (58, 44, 36), radius=5)
        rect(d, (sx + 4, y1 + 22, sx + 70, y1 + 48), jit((162, 138, 108), 8), radius=4)
        for j in range(3):
            rect(d, (sx + 8 + j * 22, y1 + 25, sx + 26 + j * 22, y1 + 41),
                 jit((190, 168, 138), 10), radius=3)
    rect(d, (x1 + 46, y1 + 62, x1 + 116, y1 + 88), (66, 48, 36), radius=4)
    circ(d, x1 + 81, y1 + 75, 8, (188, 158, 110))
    # the duo's corner
    circ(d, x2 - 30, y2 - 34, 9, (44, 40, 42))
    circ(d, x2 - 30, y2 - 34, 3.2, (168, 164, 166))
    rect(d, (x2 - 58, y2 - 30, x2 - 44, y2 - 12), (36, 32, 34), radius=2)


def draw_kiosk(d, box):
    x1, y1, x2, y2 = box
    rect(d, box, (72, 56, 44), radius=3)
    for k in range(6):
        cx = x1 + 2 + k * (x2 - x1 - 4) / 6.0
        rect(d, (cx, y1 + 2, cx + (x2 - x1 - 4) / 6.0 - 1, y2 - 2),
             (206, 74, 66) if k % 2 == 0 else (238, 232, 220))


def draw_person(d, x, y, facing, seated=True, waiter=False, scale=1.35):
    """Top-down person: shoulders, head, hair, plus a shadow."""
    a = math.radians(facing)
    fx, fy = math.sin(a), -math.cos(a)
    sh = 6.0 * scale
    cloth = (226, 224, 220) if waiter else rnd.choice(CLOTH)
    # shadow
    circ(d, x + 1.2, y + 1.6, sh * 1.02, (26, 20, 16))
    # shoulders, slightly elliptical across the facing axis
    d.ellipse([px(x - sh), px(y - sh * 0.86), px(x + sh), px(y + sh * 0.86)],
              fill=cloth)
    # arms toward the table
    circ(d, x + fx * sh * 0.72 - fy * sh * 0.6, y + fy * sh * 0.72 + fx * sh * 0.6,
         sh * 0.28, jit(cloth, 12))
    circ(d, x + fx * sh * 0.72 + fy * sh * 0.6, y + fy * sh * 0.72 - fx * sh * 0.6,
         sh * 0.28, jit(cloth, 12))
    # head
    hx, hy = x + fx * sh * 0.14, y + fy * sh * 0.14
    circ(d, hx, hy, sh * 0.56, rnd.choice(SKIN))
    # hair, offset away from facing
    hair = rnd.choice(HAIR)
    circ(d, hx - fx * sh * 0.16, hy - fy * sh * 0.16, sh * 0.50, hair)
    circ(d, hx + fx * sh * 0.10, hy + fy * sh * 0.10, sh * 0.36,
         jit(rnd.choice(SKIN), 6))
    if waiter:
        # a tray
        circ(d, x + fx * sh * 1.5, y + fy * sh * 1.5, sh * 0.5, (218, 214, 206),
             outline=(160, 156, 150), width=0.7)


def draw_chair(d, sx, sy, yaw, size=10.0):
    a = math.radians(yaw)
    fx, fy = math.sin(a), -math.cos(a)
    px_, py_ = -fy, fx
    # legs
    for lx, ly in ((-0.62, -0.62), (0.62, -0.62), (-0.62, 0.62), (0.62, 0.62)):
        circ(d, sx + px_ * size * lx + fx * size * ly,
             sy + py_ * size * lx + fy * size * ly, size * 0.10, (54, 38, 26))
    # seat pad
    d.ellipse([px(sx - size * 0.62), px(sy - size * 0.62),
               px(sx + size * 0.62), px(sy + size * 0.62)], fill=jit(CHAIR_W, 10),
              outline=CHAIR_D, width=max(1, px(0.8)))
    circ(d, sx, sy, size * 0.40, jit((156, 118, 74), 10))
    # back rest, an arc away from the table
    bx, by = sx - fx * size * 0.62, sy - fy * size * 0.62
    d.ellipse([px(bx - size * 0.52), px(by - size * 0.52),
               px(bx + size * 0.52), px(by + size * 0.52)], fill=CHAIR_D)
    d.ellipse([px(bx - size * 0.34), px(by - size * 0.34),
               px(bx + size * 0.34), px(by + size * 0.34)], fill=jit(CHAIR_W, 8))


def draw_setting(d, cx, cy, ang, scale=1.0):
    """A laid cover: charger, plate, napkin, knife, fork, two glasses."""
    a = math.radians(ang)
    fx, fy = math.sin(a), -math.cos(a)
    rx, ry = -fy, fx
    s = scale
    # charger + plate
    circ(d, cx, cy, 5.2 * s, (238, 234, 226), outline=(198, 190, 176), width=0.7)
    circ(d, cx, cy, 3.6 * s, (250, 249, 246))
    circ(d, cx, cy, 1.9 * s, (240, 238, 232))
    # napkin
    d.polygon([(px(cx - rx * 1.4 * s), px(cy - ry * 1.4 * s)),
               (px(cx + rx * 1.4 * s), px(cy + ry * 1.4 * s)),
               (px(cx + rx * 1.0 * s + fx * 1.6 * s), px(cy + ry * 1.0 * s + fy * 1.6 * s)),
               (px(cx - rx * 1.0 * s + fx * 1.6 * s), px(cy - ry * 1.0 * s + fy * 1.6 * s))],
              fill=(226, 222, 212))
    # cutlery either side
    for sgn in (-1, 1):
        ox, oy = cx + rx * 7.0 * s * sgn, cy + ry * 7.0 * s * sgn
        line(d, ox - fx * 3.0 * s, oy - fy * 3.0 * s,
             ox + fx * 3.0 * s, oy + fy * 3.0 * s, (206, 206, 210), 1.0 * s)
        circ(d, ox + fx * 2.6 * s, oy + fy * 2.6 * s, 0.9 * s, (222, 222, 226))
    # glasses beyond the plate
    circ(d, cx + rx * 4.2 * s - fx * 5.4 * s, cy + ry * 4.2 * s - fy * 5.4 * s,
         1.8 * s, (206, 224, 232), outline=(170, 194, 206), width=0.6)
    circ(d, cx + rx * 6.6 * s - fx * 4.6 * s, cy + ry * 6.6 * s - fy * 4.6 * s,
         1.5 * s, (214, 206, 226), outline=(176, 168, 190), width=0.6)


def draw_table(d, t, seats, occupied):
    shape, w, h = t["shape"], t["w"], t["h"]
    # chairs first
    for s in seats:
        yaw = math.degrees(math.atan2(t["x"] - s["x"], -(t["y"] - s["y"]))) % 360
        draw_chair(d, s["x"], s["y"], yaw, 10.0 if t["max_party"] <= 4 else 9.2)

    # top with a soft drop shadow
    if shape == "round":
        r = w / 2
        circ(d, t["x"] + 1.6, t["y"] + 2.6, r + 1, (32, 24, 18))
        circ(d, t["x"], t["y"], r, LINEN, outline=(202, 192, 176), width=1.0)
        circ(d, t["x"], t["y"], r * 0.94, jit(LINEN, 4))
        # cloth fall
        for k in range(26):
            aa = 6.2832 * k / 26
            line(d, t["x"] + math.cos(aa) * r * 0.88, t["y"] + math.sin(aa) * r * 0.88,
                 t["x"] + math.cos(aa) * r, t["y"] + math.sin(aa) * r,
                 (222, 214, 200), 0.6)
    else:
        rect(d, (t["x"] - w / 2 + 1.6, t["y"] - h / 2 + 2.6,
                 t["x"] + w / 2 + 1.6, t["y"] + h / 2 + 2.6), (32, 24, 18), radius=3)
        rect(d, (t["x"] - w / 2, t["y"] - h / 2, t["x"] + w / 2, t["y"] + h / 2),
             LINEN, outline=(202, 192, 176), width=1.0, radius=3)

    # covers
    for s in seats:
        ang = math.degrees(math.atan2(s["x"] - t["x"], -(s["y"] - t["y"]))) % 360
        a = math.radians(ang)
        inset = (w / 2) * 0.56 if shape == "round" else min(w, h) * 0.28
        draw_setting(d, t["x"] + math.sin(a) * inset, t["y"] - math.cos(a) * inset,
                     ang, 1.0 if t["max_party"] <= 6 else 0.9)

    # centrepiece: candle in a holder, small vase
    circ(d, t["x"], t["y"], 3.0, (172, 138, 88))
    circ(d, t["x"], t["y"], 1.5, (255, 214, 150))
    if shape == "rect":
        for k in (-1, 1):
            circ(d, t["x"] + k * w * 0.24, t["y"], 2.6, (168, 134, 86))
            circ(d, t["x"] + k * w * 0.24, t["y"], 1.3, (255, 214, 150))

    # seated guests
    for s in seats:
        if s["id"] in occupied:
            yaw = math.degrees(math.atan2(t["x"] - s["x"], -(t["y"] - s["y"]))) % 360
            draw_person(d, s["x"], s["y"], yaw)


def draw_bar(d, counter, back):
    rect(d, counter, (40, 36, 40), radius=3)
    x1, y1, x2, y2 = counter
    rect(d, (x1 + 2, y1 + 2, x2 - 2, y2 - 2), MARBLE, radius=2)
    for i in range(500):
        vx, vy = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        line(d, vx, vy, vx + rnd.uniform(3, 14), vy + rnd.uniform(-3, 3),
             jit((190, 188, 186), 12), 0.6)
    # stools
    for y in range(int(y1) + 16, int(y2) - 8, 30):
        circ(d, x1 - 12, y, 6.0, (54, 40, 30))
        circ(d, x1 - 12, y, 4.2, jit((148, 112, 70), 10))
    # back bar shelving with bottles
    rect(d, back, (30, 26, 30), radius=2)
    bx1, by1, bx2, by2 = back
    for row in range(4):
        yy = by1 + 10 + row * (by2 - by1 - 18) / 4.0
        rect(d, (bx1 + 3, yy, bx2 - 3, yy + 3), (72, 56, 42))
        for k in range(9):
            cx = bx1 + 6 + k * (bx2 - bx1 - 12) / 9.0
            col = [(186, 142, 76), (138, 92, 58), (94, 128, 106), (168, 106, 90),
                   (208, 196, 168)][k % 5]
            rect(d, (cx, yy - 6, cx + 3, yy), col, radius=1)


def draw_stage(d, box):
    rect(d, box, (44, 34, 34), radius=3)
    x1, y1, x2, y2 = box
    rect(d, (x1 + 3, y1 + 3, x2 - 3, y2 - 3), (66, 44, 42), radius=2)
    for x in range(int(x1) + 5, int(x2) - 3, 7):
        line(d, x, y1 + 4, x, y2 - 4, (52, 36, 34), 0.8)
    # backdrop curtain
    for k in range(18):
        cx = x1 + 4 + k * (x2 - x1 - 8) / 18.0
        rect(d, (cx, y1 + 3, cx + 3.4, y1 + 16), jit((96, 38, 44), 10))
    # a piano, an amp, mic stands
    rect(d, (x1 + 16, y1 + 34, x1 + 60, y1 + 62), (26, 24, 26), radius=3)
    rect(d, (x1 + 20, y1 + 38, x1 + 56, y1 + 46), (232, 230, 226), radius=1)
    rect(d, (x2 - 40, y1 + 40, x2 - 20, y1 + 62), (32, 30, 32), radius=2)
    circ(d, x2 - 30, y1 + 51, 6, (54, 52, 54))
    for mx in (x1 + 78, x1 + 100):
        circ(d, mx, y1 + 52, 5.6, (40, 38, 40))
        circ(d, mx, y1 + 52, 2.0, (150, 148, 150))


def draw_glass_wall(d, box):
    x1, y1, x2, y2 = box
    rect(d, (x1 - 2.5, y1, x1 + 2.5, y2), (44, 46, 52))
    for y in range(int(y1), int(y2), 46):
        rect(d, (x1 - 2, y + 3, x1 + 2, y + 43), jit(GLASS, 16))
        line(d, x1 - 2.5, y, x1 + 2.5, y, (28, 30, 36), 1.6)
    line(d, x1 - 2.6, y1, x1 - 2.6, y2, (190, 220, 232), 0.8)


def draw_tree(d, cx, cy, r):
    circ(d, cx + 2, cy + 3, r, (22, 30, 26))
    for i in range(int(r * 2.4)):
        a = rnd.uniform(0, math.tau)
        dd = rnd.uniform(0, r * 0.66)
        circ(d, cx + math.cos(a) * dd, cy + math.sin(a) * dd,
             rnd.uniform(r * 0.26, r * 0.48), jit(rnd.choice(GREEN), 12))
    for i in range(int(r * 2.6)):
        a = rnd.uniform(0, math.tau)
        dd = rnd.uniform(0, r * 0.52)
        circ(d, cx + math.cos(a) * dd - 1.4, cy + math.sin(a) * dd - 1.8,
             rnd.uniform(0.9, 2.2), jit((118, 162, 86), 14))


def draw_planter(d, cx, cy, r):
    circ(d, cx + 1, cy + 2, r, (26, 22, 20))
    circ(d, cx, cy, r, (152, 132, 108), outline=(112, 94, 74), width=1.0)
    circ(d, cx, cy, r * 0.82, (72, 56, 42))
    for i in range(int(r * 3.4)):
        a = rnd.uniform(0, math.tau)
        dd = rnd.uniform(0, r * 0.74)
        circ(d, cx + math.cos(a) * dd, cy + math.sin(a) * dd,
             rnd.uniform(1.4, 3.0), jit(rnd.choice(GREEN), 12))


# ------------------------------------------------------------------ build
def build():
    floor = json.load(open(os.path.join(VENUE, "floor.json")))
    tables = json.load(open(os.path.join(VENUE, "tables.json")))
    seats = json.load(open(os.path.join(VENUE, "seats.json")))
    g = floor["geometry"]
    W, H = floor["map"]["width"], floor["map"]["height"]

    img = Image.new("RGB", (px(W), px(H)), (10, 16, 26))
    d = ImageDraw.Draw(img)
    lights = Image.new("RGB", img.size, (0, 0, 0))
    ld = ImageDraw.Draw(lights)

    def glow(cx, cy, r, colour):
        ld.ellipse([px(cx - r), px(cy - r), px(cx + r), px(cy + r)], fill=colour)

    draw_sea(d, g["water"], [], (0, 0, 0, 0))
    draw_promenade(d, g["promenade"])

    R = g["rooms"]
    rect(d, g["plot"], (54, 42, 32))
    rect(d, g["building"], (58, 44, 34))
    rect(d, R["garden"], (150, 112, 74))
    x1, y1, x2, y2 = R["garden"]
    for i in range(1200):
        cx, cy = rnd.uniform(x1, x2), rnd.uniform(y1, y2)
        circ(d, cx, cy, rnd.uniform(0.8, 2.6), jit((150, 112, 74), 16))
    draw_herringbone(d, (R["window"][0], R["window"][1], R["east"][2], R["east"][3]),
                     FLOOR, FLOOR_DARK)
    draw_herringbone(d, R["private"], (114, 70, 40), (84, 48, 26), 9)
    draw_terrace(d, R["terrace"])
    rect(d, R["wc"], STONE)
    x1, y1, x2, y2 = R["wc"]
    for y in range(int(y1), int(y2), 14):
        for x in range(int(x1), int(x2), 14):
            rect(d, (x + 1, y + 1, x + 13, y + 13), jit(STONE, 9),
                 outline=(146, 138, 126), width=0.5, radius=1)

    # walls
    rect(d, g["building"], None, outline=WALL, width=6)
    rect(d, R["private"], None, outline=WALL, width=4)
    rect(d, R["wc"], None, outline=WALL, width=4)
    line(d, R["garden"][0], R["garden"][3], R["garden"][2], R["garden"][3], WALL, 5)
    draw_lounge(d, R["lounge"])
    draw_bar(d, g["bar_counter"], g["back_bar"])
    rect(d, g["pass"], (48, 50, 54), radius=3)
    qx1, qy1, qx2, qy2 = g["pass"]
    rect(d, (qx1 + 3, qy1 + 3, qx2 - 3, qy2 - 3), (188, 192, 198), radius=2)
    for x in range(int(qx1) + 12, int(qx2) - 8, 18):
        for y in range(int(qy1) + 14, int(qy2) - 8, 20):
            circ(d, x, y, 4.4, (238, 236, 230), outline=(196, 194, 188), width=0.7)
    draw_flower_wall(d, (684, 300, 706, 860))
    draw_flower_wall(d, (256, 84, 682, 98))
    draw_kiosk(d, g["kiosk"])

    for cx, cy, r in g["trees"]:
        draw_tree(d, cx, cy, r)
    for cx, cy, r in [(268, 316, 11), (268, 836, 11), (676, 316, 10), (676, 836, 10),
                      (128, 292, 13), (128, 660, 13), (128, 1010, 13),
                      (272, 1024, 12), (668, 1024, 12), (272, 1226, 11),
                      (668, 1226, 11), (470, 1010, 10), (204, 300, 10),
                      (204, 760, 10), (300, 108, 10), (660, 108, 10)]:
        draw_planter(d, cx, cy, r)

    # entrance mat + steps
    ex, ey = g["entrance"]
    rect(d, (ex - 26, ey - 22, ex + 26, ey + 12), (96, 62, 52), radius=3)
    for i in range(4):
        rect(d, (ex - 30, ey + 14 + i * 7, ex + 30, ey + 20 + i * 7),
             (162, 154, 142), outline=(126, 118, 108), width=0.6, radius=1)

    for t in tables:
        if "umbrella" in t["tags"]:
            draw_umbrella(d, t["x"], t["y"], 46)

    # tables, with about a third of covers taken
    by_table = {}
    for s in seats:
        by_table.setdefault(s["table_id"], []).append(s)
    occupied = set()
    for t in tables:
        ss = by_table.get(t["id"], [])
        if rnd.random() < 0.55:
            k = rnd.choice([2, 2, 2, 3, 4])
            for s in ss[:min(k, len(ss))]:
                occupied.add(s["id"])
    for t in tables:
        draw_table(d, t, by_table.get(t["id"], []), occupied)

    # a few standing staff
    for (x, y, f) in [(600, 420, 250), (420, 1090, 20), (330, 640, 270),
                      (500, 250, 180), (250, 1140, 300)]:
        draw_person(d, x, y, f, waiter=True, scale=1.05)

    # ---- light layer
    for (cx, cy, outdoor) in g["lamps"]:
        circ(d, cx, cy, 4.4, (48, 42, 38))
        circ(d, cx, cy, 2.6, LAMP)
        glow(cx, cy, 17, (66, 44, 20))
        glow(cx, cy, 8, (168, 122, 62))
    for t in tables:
        r = max(t["w"], t["h"])
        glow(t["x"], t["y"], r * 0.52, (92, 56, 24))
        glow(t["x"], t["y"], 8, (186, 124, 54))
    glow(608, 456, 76, (52, 38, 22))
    glow(474, 178, 78, (58, 34, 34))
    glow(410, 1102, 66, (44, 38, 28))
    glow(430, 640, 260, (30, 22, 13))
    glow(300, 640, 220, (26, 20, 14))
    glow(g["entrance"][0], g["entrance"][1], 44, (68, 50, 24))
    glow(622, 850, 70, (46, 32, 18))
    lights = lights.filter(ImageFilter.GaussianBlur(px(10)))

    # ---- grade
    night = Image.merge("RGB", [
        img.getchannel("R").point(lambda v: int(v * 0.62)),
        img.getchannel("G").point(lambda v: int(v * 0.58)),
        img.getchannel("B").point(lambda v: int(v * 0.60)),
    ])
    lit = ImageChops.screen(night, lights)
    lit = ImageChops.add(lit, lights.point(lambda v: int(v * 0.14)))
    lit = ImageEnhance.Color(lit).enhance(1.20)
    lit = ImageEnhance.Contrast(lit).enhance(1.08)

    vg = Image.new("L", img.size, 0)
    ImageDraw.Draw(vg).ellipse([-px(W) * 0.30, -px(H) * 0.14,
                                px(W) * 1.30, px(H) * 1.14], fill=255)
    vg = vg.filter(ImageFilter.GaussianBlur(px(60)))
    lit = Image.composite(lit, Image.new("RGB", img.size, (5, 9, 17)), vg)

    os.makedirs(OUT, exist_ok=True)
    lit.resize((W * 2, H * 2), Image.LANCZOS).save(os.path.join(OUT, "ground.png"),
                                                   optimize=True)
    lights.resize((W, H), Image.LANCZOS).save(os.path.join(OUT, "lights.png"))
    print("map: ground.png %dx%d" % (W * 2, H * 2))


if __name__ == "__main__":
    build()
