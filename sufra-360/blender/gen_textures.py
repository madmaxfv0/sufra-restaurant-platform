"""Generate the venue's own seamless cobble and grass PBR sets.

Authored here rather than downloaded, so the paving and lawn carry no
third-party licence. Both are wrapped (distances and strokes wrap at the tile
edge) so they tile without a visible seam, and each ships albedo, normal and
roughness under the names AssetManager.pbr() already expects.

    /Applications/Blender.app/Contents/MacOS/Blender --background \
        --python blender/gen_textures.py
"""
import math
import pathlib

import bpy
import numpy as np

OUT = pathlib.Path(__file__).resolve().parent.parent / "static" / "3d" / "textures"
N = 1024
rng = np.random.default_rng(7)


def blur(a, r):
    """Separable box blur, repeated - a cheap gaussian. np.roll wraps, which is
    what keeps the tile seamless; PIL is not available inside Blender."""
    a = np.clip(a, 0, 1).astype(np.float32)
    k = max(1, int(r))
    for _ in range(3):
        acc = np.zeros_like(a)
        for d in range(-k, k + 1):
            acc += np.roll(a, d, axis=0)
        a = acc / (2 * k + 1)
        acc = np.zeros_like(a)
        for d in range(-k, k + 1):
            acc += np.roll(a, d, axis=1)
        a = acc / (2 * k + 1)
    return a


def save(rgb, name):
    """Write an HxWx3 float array as a JPEG through Blender's image system."""
    h, w, _ = rgb.shape
    img = bpy.data.images.new(name, width=w, height=h, alpha=False)
    px = np.concatenate([np.clip(rgb, 0, 1),
                         np.ones((h, w, 1), np.float32)], axis=-1)
    # Blender images are bottom-up and want a flat RGBA float buffer
    img.pixels.foreach_set(np.ascontiguousarray(px[::-1]).reshape(-1).astype(np.float32))
    img.file_format = "JPEG"
    img.filepath_raw = str(OUT / f"{name}.jpg")
    img.save()


def to_normal(h, strength):
    gy, gx = np.gradient(h.astype(np.float32))
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(h)
    L = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / L * .5 + .5, ny / L * .5 + .5, nz / L * .5 + .5], -1)


def cobble():
    # A Voronoi of setts whose distances wrap, so the tile is seamless.
    pts = rng.random((190, 2)) * N
    yy, xx = np.mgrid[0:N, 0:N]
    d1 = np.full((N, N), 1e9)
    own = np.zeros((N, N), int)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(xx - px); dx = np.minimum(dx, N - dx)
        dy = np.abs(yy - py); dy = np.minimum(dy, N - dy)
        d = dx * dx + dy * dy
        m = d < d1
        own[m] = i
        d1 = np.where(m, d, d1)
    d1 = np.sqrt(d1)
    edge = np.zeros((N, N), bool)
    edge[:, :-1] |= own[:, :-1] != own[:, 1:]
    edge[:-1, :] |= own[:-1, :] != own[1:, :]
    mortar = blur(edge.astype(np.float32), 2.6)
    dome = np.clip(1 - d1 / 28, 0, 1) ** 0.55
    grain = blur(rng.random((N, N)), 1.1)
    height = np.clip(dome * (1 - mortar) - mortar * .5 + grain * .10, 0, 1)
    tone = rng.random(len(pts)) * .30 + .42
    base = tone[own]
    col = np.stack([base * .98 + grain * .10, base * .95 + grain * .09, base * .90 + grain * .08], -1)
    col *= (1 - mortar * .55)[..., None]
    col = np.clip(col * (.55 + dome[..., None] * .45), 0, 1)
    save(col, "cobble_albedo")
    save(to_normal(height, 3.0), "cobble_normal")
    r = np.clip(.55 + mortar * .35 - dome * .18, 0, 1)
    save(np.stack([r, r, r], -1), "cobble_rough")
    print("cobble set written")


def grass():
    g = np.zeros((N, N), np.float32)
    hh = np.zeros((N, N), np.float32)
    for _ in range(48000):
        x0, y0 = rng.integers(0, N, 2)
        L = int(rng.integers(9, 24))
        ang = rng.normal(-math.pi / 2, .5)
        shade = rng.random() * .55 + .35
        for s in range(L):
            x = int(x0 + math.cos(ang) * s * .55) % N      # wraps: seamless
            y = int(y0 + math.sin(ang) * s) % N
            v = shade * (.45 + .55 * s / L)
            if v > g[y, x]:
                g[y, x] = v
            if s / L > hh[y, x]:
                hh[y, x] = s / L
    g = blur(g, .6)
    patch = blur(rng.random((N, N)), 26)
    lush = .45 + patch * .55
    col = np.stack([.13 + g * .30 * lush + patch * .06,
                    .26 + g * .46 * lush,
                    .09 + g * .20 * lush], -1)
    save(col, "grass_albedo")
    save(to_normal(blur(hh, 1), 1.6), "grass_normal")
    r = np.clip(.72 + (1 - g) * .2, 0, 1)
    save(np.stack([r, r, r], -1), "grass_rough")
    print("grass set written")


if __name__ == "__main__":
    cobble()
    grass()
