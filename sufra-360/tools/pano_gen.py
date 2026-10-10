"""
SUFRA Immersive - seat panorama generator.

Renders one equirectangular 360 image per table into assets/panoramas/.
Features are placed at the table's real compass bearings, so the window,
the bar and the entrance appear in the direction they actually are.

Equirect mapping:  x = yaw / 360 * W        (0 = map north / up)
                   y = (90 - pitch) / 180 * H
"""
import json
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENUE = os.path.join(ROOT, "venue")
OUT = os.path.join(ROOT, "assets", "panoramas")

W, H = 2048, 1024
HORIZON = int(H * 0.50)


def yx(yaw):
    return (yaw % 360) / 360.0 * W


def py(pitch):
    return (90 - pitch) / 180.0 * H


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(d, y0, y1, c0, c1):
    y0, y1 = int(y0), int(y1)
    if y1 <= y0:
        return
    for y in range(y0, y1):
        t = (y - y0) / float(y1 - y0)
        d.line([0, y, W, y], fill=lerp(c0, c1, t))


def wrapped(fn, yaw, half_deg, *a, **k):
    """Call fn(x_left, x_right) for a yaw span, handling the 0/360 seam."""
    cx = yx(yaw)
    hw = half_deg / 360.0 * W
    x0, x1 = cx - hw, cx + hw
    spans = []
    if x0 < 0:
        spans += [(x0 + W, W), (0, x1)]
    elif x1 > W:
        spans += [(x0, W), (0, x1 - W)]
    else:
        spans += [(x0, x1)]
    for s in spans:
        if s[1] - s[0] < 6:
            continue
        fn(s[0], s[1], *a, **k)


# ------------------------------------------------------------------ pieces
def draw_window(d, x0, x1, indoor=True):
    top, bot = py(26), py(-14)
    d.rectangle([x0, top, x1, bot], fill=(38, 34, 42))
    inset = (x1 - x0) * 0.055
    inset = min(inset, (x1 - x0) * 0.3)
    d.rectangle([x0 + inset, top + 14, x1 - inset, bot - 14], fill=(20, 34, 58))
    # night outside, warmer near the bottom (street lamps)
    n = int(bot - top - 28)
    for i in range(max(1, n)):
        t = i / float(max(1, n))
        y = top + 14 + i
        d.line([x0 + inset, y, x1 - inset, y],
               fill=lerp((16, 28, 52), (58, 62, 74), t ** 2))
    # mullions
    mid = (x0 + x1) / 2
    d.line([mid, top, mid, bot], fill=(38, 34, 42), width=9)
    d.line([x0, (top + bot) / 2, x1, (top + bot) / 2], fill=(38, 34, 42), width=7)
    # a few warm points outside
    for k in range(6):
        gx = x0 + (x1 - x0) * (0.12 + 0.15 * k)
        gy = bot - 30 - (k % 3) * 16
        d.ellipse([gx - 5, gy - 5, gx + 5, gy + 5], fill=(210, 170, 110))
    # curtain
    if indoor:
        d.polygon([(x0 - 22, top - 10), (x0 + 26, top - 10),
                   (x0 + 14, bot + 8), (x0 - 30, bot + 8)], fill=(92, 40, 44))
        d.polygon([(x1 + 22, top - 10), (x1 - 26, top - 10),
                   (x1 - 14, bot + 8), (x1 + 30, bot + 8)], fill=(92, 40, 44))


def draw_open_view(d, x0, x1, water=False):
    """Terrace / garden: open air instead of a wall."""
    top, bot = py(56), py(-16)
    n = int(bot - top)
    for i in range(max(1, n)):
        t = i / float(max(1, n))
        col = lerp((16, 26, 48), (36, 58, 88), t) if not water else \
            lerp((14, 24, 46), (28, 62, 104), t)
        d.line([x0, top + i, x1, top + i], fill=col)
    if water:
        for k in range(48):
            wx = x0 + (x1 - x0) * ((k * 37) % 100) / 100.0
            wy = bot - 8 - (k % 7) * 9
            d.line([wx, wy, wx + 26, wy], fill=(70, 118, 160))
    # far shoreline lights
    for k in range(22):
        gx = x0 + (x1 - x0) * (k / 22.0)
        gy = py(1.5)
        d.ellipse([gx - 4, gy - 4, gx + 4, gy + 4], fill=(190, 156, 96))


def draw_wall(d, x0, x1, base, panel):
    top, bot = py(40), py(-16)
    d.rectangle([x0, top, x1, bot], fill=base)
    d.rectangle([x0, py(4), x1, bot], fill=panel)
    d.line([x0, py(4), x1, py(4)], fill=lerp(panel, (255, 255, 255), 0.18), width=6)
    # framed pictures
    step = (x1 - x0) / 5.0
    for k in range(5):
        cx = x0 + step * (k + 0.5)
        w, h = step * 0.26, 78 + (k % 3) * 26
        d.rectangle([cx - w, py(20) - h / 2, cx + w, py(20) + h / 2],
                    fill=(58, 44, 34), outline=(150, 118, 72), width=5)
        d.rectangle([cx - w + 9, py(20) - h / 2 + 9, cx + w - 9, py(20) + h / 2 - 9],
                    fill=(96, 82, 66))


def draw_stage_band(d, x0, x1):
    d.rectangle([x0, py(24), x1, py(-16)], fill=(48, 30, 32))
    ins = min(10.0, (x1 - x0) * 0.18)
    for k in range(14):
        cx = x0 + ins + k * max(1.0, (x1 - x0 - ins * 2)) / 14.0
        d.rectangle([cx, py(24), cx + 5, py(6)], fill=(104, 40, 46))
    d.rectangle([x0, py(6), x1, py(-16)], fill=(66, 46, 44))
    mid = (x0 + x1) / 2
    d.ellipse([mid - 26, py(2) - 26, mid + 26, py(2) + 26], fill=(38, 34, 36))
    d.ellipse([mid - 10, py(2) - 10, mid + 10, py(2) + 10], fill=(150, 148, 150))


def draw_bar(d, x0, x1):
    d.rectangle([x0, py(6), x1, py(-16)], fill=(30, 28, 34))
    d.rectangle([x0, py(6), x1, py(3)], fill=(196, 198, 206))
    # bottle shelves
    for row in range(3):
        yy = py(20 - row * 6)
        ins = min(20.0, (x1 - x0) * 0.2)
        d.rectangle([x0 + ins, yy, x1 - ins, yy + 9], fill=(74, 58, 44))
        for k in range(26):
            bx = x0 + ins * 1.6 + k * (max(1.0, x1 - x0 - ins * 3.4) / 26.0)
            hgt = 30 + (k * 7) % 22
            col = [(184, 142, 78), (140, 92, 60), (96, 128, 108), (168, 108, 92)][k % 4]
            d.rectangle([bx, yy - hgt, bx + 11, yy], fill=col)


def draw_doorway(d, x0, x1):
    d.rectangle([x0, py(20), x1, py(-16)], fill=(26, 24, 28))
    ins = min(16.0, (x1 - x0) * 0.2)
    d.rectangle([x0 + ins, py(16), x1 - ins, py(-16)], fill=(48, 42, 40))
    d.ellipse([(x0 + x1) / 2 - 30, py(22) - 30, (x0 + x1) / 2 + 30, py(22) + 30],
              fill=(198, 156, 96))


def draw_plants(d, x0, x1, n=5):
    for k in range(n):
        cx = x0 + (x1 - x0) * ((k + 0.5) / n)
        base = py(-13)
        d.rectangle([cx - 26, base - 34, cx + 26, base], fill=(126, 96, 66))
        for j in range(26):
            a = (j * 2.3)
            px_ = cx + math.cos(a) * (10 + (j % 5) * 7)
            py_ = base - 44 - (j % 6) * 11
            r = 12 + (j % 4) * 4
            d.ellipse([px_ - r, py_ - r, px_ + r, py_ + r],
                      fill=[(38, 74, 44), (52, 96, 52), (66, 116, 60)][j % 3])


def draw_far_tables(d, n=9):
    for k in range(n):
        cx = W * (k + 0.5) / n
        cy = py(-9)
        d.ellipse([cx - 52, cy - 16, cx + 52, cy + 16], fill=(226, 216, 196))
        d.ellipse([cx - 8, cy - 12, cx + 8, cy + 4], fill=(240, 196, 130))


def draw_ceiling(d, style, lamp_yaws):
    if style == "open":
        vgrad(d, 0, py(40), (8, 14, 30), (18, 30, 54))
        # string lights
        for k in range(140):
            a = k / 140.0 * 360.0
            x = yx(a)
            yy = py(46 + 7 * math.sin(k * 0.55))
            d.ellipse([x - 6, yy - 6, x + 6, yy + 6], fill=(255, 214, 150))
    else:
        vgrad(d, 0, py(40), (30, 22, 18), (58, 40, 30))
        for k in range(90):
            yy = py(88 - k * 0.5)
            d.line([0, yy, W, yy], fill=(46, 32, 24))
    for a in lamp_yaws:
        x = yx(a)
        yy = py(52)
        d.ellipse([x - 46, yy - 26, x + 46, yy + 26], fill=(120, 84, 44))
        d.ellipse([x - 26, yy - 16, x + 26, yy + 16], fill=(255, 226, 170))
        d.line([x, 0, x, yy], fill=(46, 38, 30), width=6)


def draw_table_foreground(d, zone):
    top = py(-44)
    linen = (206, 190, 162) if zone != "bar" else (176, 170, 172)
    n = int(H - top)
    for i in range(n):
        t = i / float(n)
        d.line([0, top + i, W, top + i], fill=lerp(lerp(linen, (150, 132, 108), 0.35),
                                                   linen, min(1.0, t * 1.6)))
    d.line([0, top, W, top], fill=(198, 184, 160), width=8)
    # place settings around the rim
    for k in range(8):
        cx = W * (k + 0.5) / 8
        cy = py(-56)
        d.ellipse([cx - 70, cy - 26, cx + 70, cy + 26], fill=(240, 236, 228),
                  outline=(190, 176, 152), width=4)
        d.ellipse([cx - 32, cy - 12, cx + 32, cy + 12], fill=(222, 214, 198))
        d.ellipse([cx + 92, cy - 20, cx + 108, cy + 20], fill=(198, 194, 188))
    # candle at nadir
    for k in range(3):
        cx, cy = W * (0.25 + 0.25 * k), py(-74)
        d.ellipse([cx - 46, cy - 18, cx + 46, cy + 18], fill=(168, 132, 82))
        d.ellipse([cx - 24, cy - 10, cx + 24, cy + 10], fill=(255, 206, 132))


def build_one(t, zones):
    img = Image.new("RGB", (W, H), (24, 20, 26))
    d = ImageDraw.Draw(img)
    zone = t["zone"]
    b = t["bearings"]
    outdoor = zone in ("terrace", "garden", "lounge")

    lamp_yaws = [(b["window"] + o) % 360 for o in (35, 145, 250)]
    draw_ceiling(d, "open" if outdoor else "beam", lamp_yaws)

    # wall band all around
    base, panel = {
        "window": ((84, 58, 42), (108, 74, 52)),
        "east":   ((80, 56, 40), (104, 72, 50)),
        "garden": ((48, 64, 46), (60, 80, 56)),
        "lounge": ((62, 50, 44), (82, 64, 56)),
        "main":   ((78, 54, 40), (100, 70, 50)),
        "bar": ((44, 40, 48), (58, 52, 60)),
        "private": ((72, 40, 44), (94, 52, 56)),
        "terrace": ((52, 60, 62), (66, 74, 74)),
    }.get(zone, ((78, 54, 40), (100, 70, 50)))
    d.rectangle([0, py(40), W, py(-16)], fill=base)
    wrapped(lambda x0, x1: draw_wall(d, x0, x1, base, panel), 0, 180)

    # floor
    fl = (150, 132, 108) if outdoor else (104, 66, 38)
    vgrad(d, py(-16), py(-30), lerp(fl, (0, 0, 0), 0.45), fl)

    draw_far_tables(d)

    # features at their real bearings
    if outdoor:
        wrapped(lambda x0, x1: draw_open_view(d, x0, x1, water=False), b["window"], 46)
        wrapped(lambda x0, x1: draw_open_view(d, x0, x1, water=True), b["sea"], 32)
        wrapped(lambda x0, x1: draw_plants(d, x0, x1, 6), (b["window"] + 90) % 360, 44)
    else:
        # the glass wall is wide and the sea is behind it
        wrapped(lambda x0, x1: draw_window(d, x0, x1), b["sea"], 58)
        wrapped(lambda x0, x1: draw_open_view(d, x0, x1, water=True), b["sea"], 34)
        wrapped(lambda x0, x1: draw_plants(d, x0, x1, 4), (b["sea"] + 110) % 360, 26)

    # the stage, where it is visible
    if t["distances"]["stage"] < 520:
        wrapped(lambda x0, x1: draw_stage_band(d, x0, x1), b["stage"], 14)

    if zone != "private":
        wrapped(lambda x0, x1: draw_bar(d, x0, x1), b["bar"], 26 if zone == "bar" else 15)
    wrapped(lambda x0, x1: draw_doorway(d, x0, x1), b["entrance"], 11)

    draw_table_foreground(d, zone)

    # light falloff away from the pendants, then grain
    import random as _r
    rr = _r.Random(hash(t["id"]) & 0xffff)
    shade = Image.new("L", (W, 1), 255)
    sp = shade.load()
    for x in range(W):
        a = x / float(W) * 360.0
        best = min(min(abs(a - l), 360 - abs(a - l)) for l in lamp_yaws)
        sp[x, 0] = int(255 * (0.62 + 0.38 * math.cos(min(best, 90) / 90.0 * 1.4)))
    shade = shade.resize((W, H))
    img = ImageChops.multiply(img, Image.merge("RGB", [shade] * 3))
    gd = ImageDraw.Draw(img)
    for _ in range(2600):
        gx, gy = rr.uniform(0, W), rr.uniform(0, H)
        v = rr.randint(-14, 14)
        gd.point((gx, gy), fill=(128 + v, 124 + v, 120 + v))

    # warm grade + glow bloom
    glow = img.filter(ImageFilter.GaussianBlur(26))
    img = ImageChops.add(img, glow.point(lambda v: int(v * 0.22)))
    img = ImageEnhance.Color(img).enhance(1.12)

    # equirect poles must not show hard seams: blur the top and bottom rows
    topband = img.crop((0, 0, W, 70)).filter(ImageFilter.GaussianBlur(22))
    img.paste(topband, (0, 0))
    botband = img.crop((0, H - 70, W, H)).filter(ImageFilter.GaussianBlur(22))
    img.paste(botband, (0, H - 70))
    return img


def build():
    tables = json.load(open(os.path.join(VENUE, "tables.json")))
    zones = {z["id"]: z for z in json.load(open(os.path.join(VENUE, "zones.json")))}
    os.makedirs(OUT, exist_ok=True)
    for t in tables:
        img = build_one(t, zones)
        img.save(os.path.join(OUT, "%s.jpg" % t["id"]), quality=80, optimize=True)
    print("panoramas: %d written" % len(tables))


if __name__ == "__main__":
    build()
