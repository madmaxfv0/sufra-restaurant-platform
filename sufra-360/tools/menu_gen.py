"""
SUFRA Immersive - menu artwork.

Renders a plate illustration per dish (assets/menu/<id>.png) plus the
wordmark (assets/menu/wordmark.png).  Dish appearance is derived from the
dish's own tags, so adding a dish to menu.json gets you a matching plate.
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENUE = os.path.join(ROOT, "venue")
OUT = os.path.join(ROOT, "assets", "menu")

W, H = 640, 480

HERO = {
    "seafood":  [(226, 148, 122), (206, 118, 96), (238, 178, 150)],
    "fish":     [(214, 168, 148), (188, 140, 122), (232, 196, 176)],
    "meat":     [(126, 68, 48), (98, 50, 36), (150, 88, 62)],
    "poultry":  [(202, 158, 96), (176, 130, 74), (222, 184, 122)],
    "veg":      [(112, 148, 76), (86, 122, 58), (146, 178, 100)],
    "grain":    [(220, 196, 148), (196, 168, 118), (236, 216, 176)],
    "dough":    [(216, 178, 122), (188, 148, 96), (234, 202, 152)],
    "sweet":    [(206, 158, 122), (176, 126, 94), (232, 190, 156)],
}
SAUCE = {
    "tomato": (176, 62, 46), "cream": (238, 228, 206), "herb": (96, 132, 62),
    "citrus": (226, 182, 74), "berry": (132, 52, 82), "none": None,
}


def plate(d, cx, cy, r, tone=(246, 243, 236)):
    d.ellipse([cx - r - 10, cy - r * 0.62 + 12, cx + r + 10, cy + r * 0.62 + 22],
              fill=(34, 28, 34))
    d.ellipse([cx - r, cy - r * 0.62, cx + r, cy + r * 0.62], fill=tone,
              outline=(206, 198, 184), width=3)
    d.ellipse([cx - r * 0.72, cy - r * 0.45, cx + r * 0.72, cy + r * 0.45],
              fill=tuple(int(v * 0.985) for v in tone))


def build_dish(dish, rnd):
    img = Image.new("RGB", (W, H), (18, 22, 32))
    d = ImageDraw.Draw(img)
    # backdrop
    for y in range(H):
        t = y / float(H)
        d.line([0, y, W, y], fill=(int(18 + 26 * t), int(22 + 24 * t), int(32 + 26 * t)))
    for _ in range(900):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        v = rnd.randint(-8, 10)
        d.point((x, y), fill=(46 + v, 44 + v, 52 + v))

    cx, cy, r = W / 2, H / 2 + 16, 168
    bowl = "bowl" in dish.get("form", "")
    plate(d, cx, cy, r, (240, 236, 228) if not bowl else (232, 226, 220))

    sauce = SAUCE.get(dish.get("sauce", "none"))
    if sauce:
        for k in range(7):
            a = math.tau * k / 7
            sx = cx + math.cos(a) * r * 0.32
            sy = cy + math.sin(a) * r * 0.20
            rr = r * rnd.uniform(0.20, 0.32)
            d.ellipse([sx - rr, sy - rr * 0.62, sx + rr, sy + rr * 0.62], fill=sauce)

    cols = HERO.get(dish.get("hero", "veg"), HERO["veg"])
    form = dish.get("form", "mound")
    if form == "fillet":
        d.rounded_rectangle([cx - 96, cy - 46, cx + 96, cy + 46], radius=26, fill=cols[0])
        d.rounded_rectangle([cx - 88, cy - 38, cx + 88, cy + 8], radius=20, fill=cols[2])
        for k in range(7):
            d.line([cx - 74 + k * 25, cy - 30, cx - 60 + k * 25, cy + 30],
                   fill=cols[1], width=6)
    elif form == "dumplings":
        for k in range(7):
            a = math.tau * k / 7
            sx, sy = cx + math.cos(a) * 62, cy + math.sin(a) * 38
            d.ellipse([sx - 34, sy - 26, sx + 34, sy + 26], fill=cols[0],
                      outline=cols[1], width=3)
            d.arc([sx - 26, sy - 20, sx + 26, sy + 14], 200, 340, fill=cols[2], width=5)
    elif form == "skewer":
        for k in range(3):
            ox = (k - 1) * 54
            d.line([cx + ox, cy - 96, cx + ox, cy + 78], fill=(196, 190, 178), width=6)
            for j in range(4):
                sy = cy - 62 + j * 44
                d.rounded_rectangle([cx + ox - 26, sy - 20, cx + ox + 26, sy + 20],
                                    radius=9, fill=cols[j % 3])
    elif form == "bowl_soup":
        d.ellipse([cx - r * 0.66, cy - r * 0.42, cx + r * 0.66, cy + r * 0.42],
                  fill=sauce or cols[0])
        for k in range(14):
            a = rnd.uniform(0, math.tau)
            dd = rnd.uniform(0, r * 0.5)
            sx, sy = cx + math.cos(a) * dd, cy + math.sin(a) * dd * 0.62
            d.ellipse([sx - 13, sy - 9, sx + 13, sy + 9], fill=cols[k % 3])
    elif form == "cake":
        d.polygon([(cx - 84, cy + 46), (cx + 84, cy + 46), (cx + 62, cy - 62),
                   (cx - 62, cy - 62)], fill=cols[0])
        for k in range(4):
            yy = cy + 30 - k * 26
            d.rectangle([cx - 80 + k * 5, yy - 7, cx + 80 - k * 5, yy + 7], fill=cols[2])
    else:  # mound
        for k in range(20):
            a = rnd.uniform(0, math.tau)
            dd = rnd.uniform(0, r * 0.42)
            sx, sy = cx + math.cos(a) * dd, cy + math.sin(a) * dd * 0.62
            rr = rnd.uniform(16, 30)
            d.ellipse([sx - rr, sy - rr * 0.78, sx + rr, sy + rr * 0.78],
                      fill=cols[k % 3])

    # garnish
    for k in range(int(9 + 6 * ("herby" in dish.get("tags", [])))):
        a = rnd.uniform(0, math.tau)
        dd = rnd.uniform(r * 0.10, r * 0.50)
        sx, sy = cx + math.cos(a) * dd, cy + math.sin(a) * dd * 0.62
        d.ellipse([sx - 7, sy - 4, sx + 7, sy + 4], fill=(120, 168, 88))
    if "citrus" in dish.get("tags", []):
        d.ellipse([cx + r * 0.46, cy - 18, cx + r * 0.46 + 44, cy + 26],
                  fill=(240, 202, 92), outline=(214, 172, 62), width=3)

    glow = img.filter(ImageFilter.GaussianBlur(16))
    from PIL import ImageChops, ImageEnhance
    img = ImageChops.add(img, glow.point(lambda v: int(v * 0.16)))
    return ImageEnhance.Color(img).enhance(1.06)


def build_wordmark():
    img = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    gold = (216, 178, 108, 255)
    # geometric wordmark: S U F R A as inscribed strokes
    x = 60
    for ch in "SUFRA":
        d.text((x, 96), ch, fill=gold)
        x += 150
    # decorative rules
    d.line([60, 214, 840, 214], fill=(216, 178, 108, 160), width=3)
    d.line([60, 226, 840, 226], fill=(216, 178, 108, 80), width=2)
    img.save(os.path.join(OUT, "wordmark.png"))


def build():
    os.makedirs(OUT, exist_ok=True)
    menu = json.load(open(os.path.join(VENUE, "menu.json")))
    n = 0
    for section in menu["sections"]:
        for dish in section["dishes"]:
            rnd = random.Random(hash(dish["id"]) & 0xffffff)
            build_dish(dish, rnd).save(
                os.path.join(OUT, "%s.jpg" % dish["id"]), quality=82, optimize=True)
            n += 1
    build_wordmark()
    print("menu: %d dish images" % n)


if __name__ == "__main__":
    build()
