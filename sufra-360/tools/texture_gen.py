"""
Procedural PBR texture set for SUFRA 360. Generated once and shipped; the
app never needs numpy at runtime. Each set: *_albedo.jpg, *_normal.jpg,
*_rough.jpg, tileable. Leaf and flower cards carry alpha (PNG).
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "static", "3d", "textures")
N = 1024
rng = np.random.default_rng(2026)


def noise(size, octaves=5, persistence=0.55, seed=0):
    """Tileable fractal value noise."""
    r = np.random.default_rng(seed)
    total = np.zeros((size, size), np.float32)
    amp, freq, norm = 1.0, 4, 0.0
    for _ in range(octaves):
        base = r.random((freq, freq), dtype=np.float32)
        img = Image.fromarray((base * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
        total += np.asarray(img, np.float32) / 255.0 * amp
        norm += amp
        amp *= persistence
        freq *= 2
    return total / norm


def normal_from_height(h, strength=2.0):
    h = h.astype(np.float32)
    dx = np.roll(h, -1, 1) - np.roll(h, 1, 1)
    dy = np.roll(h, -1, 0) - np.roll(h, 1, 0)
    nx, ny, nz = -dx * strength, -dy * strength, np.ones_like(h)
    l = np.sqrt(nx * nx + ny * ny + nz * nz)
    n = np.stack([nx / l, ny / l, nz / l], -1)
    return Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8))


def save_set(name, albedo, height, rough, nstrength=2.0):
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(np.clip(albedo, 0, 255).astype(np.uint8)).save(
        os.path.join(OUT, name + "_albedo.jpg"), quality=86)
    normal_from_height(height, nstrength).save(os.path.join(OUT, name + "_normal.jpg"), quality=88)
    Image.fromarray(np.clip(rough * 255, 0, 255).astype(np.uint8)).save(
        os.path.join(OUT, name + "_rough.jpg"), quality=80)
    print("  ", name)


def cells(size, n, seed):
    """Voronoi-ish stone cells: returns (cell id map, distance-to-edge)."""
    r = np.random.default_rng(seed)
    pts = r.random((n, 2)) * size
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d1 = np.full((size, size), 1e9, np.float32)
    d2 = np.full((size, size), 1e9, np.float32)
    cid = np.zeros((size, size), np.int32)
    for i, (px, py) in enumerate(pts):
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                d = (xx - (px + ox)) ** 2 + (yy - (py + oy)) ** 2
                m = d < d1
                d2 = np.where(m, d1, np.minimum(d2, d))
                cid = np.where(m, i, cid)
                d1 = np.where(m, d, d1)
    edge = np.sqrt(d2) - np.sqrt(d1)
    return cid, edge


def cobbles():
    cid, edge = cells(N, 220, 11)
    joint = np.clip(edge / 7.0, 0, 1)
    tone = (np.random.default_rng(3).random(300)[cid % 300] * 0.35 + 0.65)
    grain = noise(N, 6, 0.5, 4)
    base = np.stack([182, 166, 142], -1)[None, None] * (tone * (0.85 + 0.3 * grain))[..., None]
    mortar = np.array([96, 88, 78])[None, None]
    albedo = base * joint[..., None] + mortar * (1 - joint[..., None])
    height = joint * (0.55 + 0.45 * grain)
    rough = 0.72 + 0.2 * (1 - joint) + 0.08 * grain
    save_set("cobble", albedo, height, rough, 3.0)


def terrace_stone():
    t = 128
    yy, xx = np.mgrid[0:N, 0:N]
    gx = (xx % t) / t; gy = (yy % t) / t
    joint = np.clip(np.minimum(np.minimum(gx, 1 - gx), np.minimum(gy, 1 - gy)) * t / 4.0, 0, 1)
    tile_id = (xx // t) + 8 * (yy // t)
    tone = np.random.default_rng(5).random(64)[tile_id % 64] * 0.25 + 0.75
    grain = noise(N, 5, 0.6, 9)
    albedo = np.stack([196, 176, 148], -1)[None, None] * (tone * (0.86 + 0.22 * grain))[..., None]
    albedo = albedo * joint[..., None] + np.array([118, 104, 88])[None, None] * (1 - joint[..., None])
    height = joint * (0.7 + 0.3 * grain)
    rough = 0.62 + 0.18 * grain + 0.15 * (1 - joint)
    save_set("terrace", albedo, height, rough, 2.2)


def gravel():
    g1 = noise(N, 7, 0.62, 21); g2 = noise(N, 3, 0.5, 22)
    albedo = np.stack([158, 128, 94], -1)[None, None] * (0.72 + 0.5 * g1)[..., None]
    albedo[..., 2] *= (0.9 + 0.2 * g2)
    save_set("gravel", albedo, g1, 0.85 + 0.1 * g2, 2.6)


def plaster():
    g = noise(N, 6, 0.5, 31); s = noise(N, 2, 0.5, 32)
    albedo = np.stack([226, 214, 196], -1)[None, None] * (0.9 + 0.12 * g + 0.04 * s)[..., None]
    save_set("plaster", albedo, g * 0.5, 0.78 + 0.1 * g, 0.9)


def marble():
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32) / N
    warp = noise(N, 5, 0.6, 41)
    veins = np.abs(np.sin((xx * 3 + yy * 1.5 + warp * 2.2) * math.pi))
    veins = np.clip(1 - veins ** 0.12, 0, 1)
    g = noise(N, 6, 0.5, 42)
    albedo = np.stack([228, 226, 222], -1)[None, None] * (0.94 + 0.06 * g)[..., None]
    albedo = albedo * (1 - 0.45 * veins[..., None]) + np.array([96, 92, 100])[None, None] * 0.45 * veins[..., None]
    save_set("marble", albedo, g * 0.15, 0.22 + 0.08 * g, 0.5)


def herringbone():
    # planks 128 x 32, alternating diagonals
    yy, xx = np.mgrid[0:N, 0:N]
    u = (xx + yy) // 128; v = (xx - yy) // 32
    plank = (u * 31 + v * 17) % 97
    tone = np.random.default_rng(7).random(97)[plank] * 0.3 + 0.7
    grain = noise(N, 6, 0.55, 51)
    streak = noise(N, 4, 0.4, 52)
    ju = ((xx + yy) % 128) / 128.0; jv = ((xx - yy) % 32) / 32.0
    joint = np.clip(np.minimum(np.minimum(ju, 1 - ju) * 40, np.minimum(jv, 1 - jv) * 12), 0, 1)
    albedo = np.stack([142, 92, 52], -1)[None, None] * (tone * (0.8 + 0.28 * grain + 0.1 * streak))[..., None]
    albedo = albedo * (0.55 + 0.45 * joint[..., None])
    save_set("herringbone", albedo, joint * (0.6 + 0.4 * grain), 0.48 + 0.2 * grain, 1.6)


def linen():
    g = noise(N, 7, 0.7, 61)
    yy, xx = np.mgrid[0:N, 0:N]
    weave = ((np.sin(xx * 0.8) * np.sin(yy * 0.8)) * 0.5 + 0.5)
    albedo = np.stack([240, 232, 214], -1)[None, None] * (0.92 + 0.06 * g + 0.02 * weave)[..., None]
    save_set("linen", albedo, weave * 0.3 + g * 0.2, 0.86 + 0.08 * g, 0.7)


def leaf_card():
    """Alpha leaf cluster card for instanced foliage."""
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = random.Random(71)
    for k in range(38):
        cx, cy = r.uniform(80, 432), r.uniform(80, 432)
        ang = r.uniform(0, 360)
        L, W = r.uniform(70, 120), r.uniform(28, 46)
        leaf = Image.new("RGBA", (int(L * 1.4), int(W * 1.4)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(leaf)
        g = (int(r.uniform(38, 86)), int(r.uniform(96, 150)), int(r.uniform(38, 70)), 255)
        ld.ellipse([L * 0.2, W * 0.2, L * 1.2, W * 1.2], fill=g)
        ld.line([L * 0.2, W * 0.7, L * 1.2, W * 0.7], fill=(g[0] + 30, g[1] + 30, g[2] + 20, 255), width=2)
        leaf = leaf.rotate(ang, expand=True, resample=Image.BICUBIC)
        im.alpha_composite(leaf, (int(cx - leaf.width / 2), int(cy - leaf.height / 2)))
    im.save(os.path.join(OUT, "leaf_card.png"))
    # matching normal-ish tint map not needed; roughness constant in material
    print("   leaf_card.png")


def flower_card():
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = random.Random(72)
    for k in range(9):
        cx, cy = r.uniform(40, 216), r.uniform(40, 216)
        col = r.choice([(214, 96, 150), (178, 92, 190), (232, 138, 92), (240, 196, 92), (244, 240, 236)])
        for p in range(6):
            a = p / 6 * 6.2832
            d.ellipse([cx + math.cos(a) * 10 - 8, cy + math.sin(a) * 10 - 8,
                       cx + math.cos(a) * 10 + 8, cy + math.sin(a) * 10 + 8], fill=col + (255,))
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(250, 214, 96, 255))
    im.save(os.path.join(OUT, "flower_card.png"))
    print("   flower_card.png")


def bark():
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    ridges = noise(N, 6, 0.55, 81)
    streak = np.abs(np.sin(xx * 0.08 + ridges * 6.0))
    albedo = np.stack([92, 70, 52], -1)[None, None] * (0.7 + 0.5 * ridges - 0.25 * streak)[..., None]
    save_set("bark", albedo, ridges * (1 - 0.5 * streak), 0.86 + 0.1 * ridges, 3.0)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for fn in (cobbles, terrace_stone, gravel, plaster, marble, herringbone, linen, bark,
               leaf_card, flower_card):
        fn()
