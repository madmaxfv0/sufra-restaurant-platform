"""Headless capture of the live SUFRA 360 scene.

Renders the real WebGL canvas in Chromium (SwiftShader) and writes PNGs to
captures/, so scene changes can be judged visually without a GPU or a human.

    python3 tools/capture_360.py [--url http://127.0.0.1:8013/360] [--tag before]
"""
import argparse
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "captures"

# name -> (camera position, orbit target), in metres.
# Scene coords come from venue/floor.json: x_m = (u - 360) * 0.05, z_m = (v - 640) * 0.05.
# So the building spans x -5.7..16.6, z -28.1..17.3; the promenade is x -14.9..-6.4;
# the bar counter sits at x 0.9..3.6, z -11..1; the terrace at x -5.5..16.5, z 18..30.
VIEWS = {
    # near-plan, framed like references/target_restaurant.jpg: the plot is
    # x -6.2..17.2 by z -29.2..30.2, so ~85 m up covers its 59 m length at fov 38.
    "plan":        ((5.5, 86, 6.0), (5.5, 0, -4.0)),
    "overview":    ((-34, 46, 44), (5, 0, -4)),
    # eye height, INSIDE the shell: the building spans x -5.7..16.6, z -28.1..17.3,
    # so anything with z > 17.3 is outside the south wall looking at plaster.
    "interior":    ((5.0, 2.4, 9.0), (4.0, 1.1, -10.0)),
    "window_row":  ((-3.5, 2.2, 6.0), (-4.5, 1.1, -12.0)),
    "bar":         ((7.0, 2.0, -3.0), (2.2, 1.1, -6.0)),
    "kitchen_pass": ((8.0, 2.2, 10.0), (5.0, 1.2, 5.0)),
    "terrace":     ((5.0, 3.0, 34.0), (5.0, 1.0, 22.0)),
    "garden":      ((5.0, 2.6, -14.0), (5.0, 1.2, -25.0)),
    "promenade":   ((-11.0, 1.7, 15.0), (-11.0, 1.6, -15.0)),
    "from_water":  ((-42, 11, 2), (5, 3, -4)),
    "horizon":     ((-9, 2.4, 4), (-70, 4, -6)),
}

FLAGS = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8013/360")
    ap.add_argument("--tag", default="now", help="subfolder under captures/")
    ap.add_argument("--settle", type=float, default=6.0, help="seconds to let the scene build")
    ap.add_argument("--time", default=None, choices=["auto", "day", "sunset", "night"])
    ap.add_argument("--weather", default=None, help="value from the #wx-demo select, e.g. clear")
    ap.add_argument("--views", default=None, help="comma-separated subset of VIEWS")
    args = ap.parse_args()

    dest = OUT / args.tag
    dest.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)

        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

        page.goto(args.url, wait_until="load", timeout=120_000)

        # the entry gate enables its button only once boot() has settled
        try:
            page.wait_for_function(
                "() => { const b = document.querySelector('#entry-go');"
                "return b && !b.disabled; }",
                timeout=180_000,
            )
        except Exception:
            print("!! entry gate never enabled - capturing anyway", file=sys.stderr)
        # click if we can, but never let the branded overlay block the lens
        page.evaluate(
            """() => { const b = document.querySelector('#entry-go'); if (b) b.click();
                 for (const id of ['entry', 'loader']) {
                   const el = document.getElementById(id); if (el) el.remove(); } }"""
        )

        if args.time:
            page.evaluate(
                """(t) => { const b = document.querySelector(`#scene-menu [data-time="${t}"]`);
                      if (b) b.click(); }""", args.time)
        if args.weather:
            page.evaluate(
                """(w) => { const s = document.querySelector('#wx-demo');
                      if (s) { s.value = w; s.dispatchEvent(new Event('change', { bubbles: true })); } }""",
                args.weather)

        page.wait_for_timeout(int(args.settle * 1000))

        # diagnostics overlay carries the scene stats we want in the report
        stats = page.evaluate(
            """() => { const a = window.sufra360; if (!a) return null;
                 const i = a.sm.renderer.info;
                 return { calls: i.render.calls, tris: i.render.triangles,
                          geometries: i.memory.geometries, textures: i.memory.textures,
                          programs: i.programs ? i.programs.length : null,
                          quality: a.quality, useGLB: a.useGLB,
                          tables: a.tm ? Object.keys(a.tm.byId).length : 0,
                          notes: a.notes.slice(0, 20),
                          failedStages: a.stages.filter(s => !s.ok).map(s => s.name) }; }"""
        )

        wanted = set(args.views.split(",")) if args.views else set(VIEWS)
        for name, (pos, tgt) in ((k, v) for k, v in VIEWS.items() if k in wanted):
            page.evaluate(
                # CameraController.update() clamps polar angle to 1.14 rad and the
                # orbit target to the property, so an eye-level view asking to look
                # west gets silently lifted to ~30 m and aimed at the water. Detach
                # it once, then drive the camera directly.
                """([p, t]) => { const a = window.sufra360; if (!a) return;
                     a.cam.idle = false; a.cam.glide = null;
                     if (!a.cam.__free) { a.cam.__free = true; a.cam.update = () => {}; }
                     a.sm.camera.position.set(p[0], p[1], p[2]);
                     a.sm.camera.lookAt(t[0], t[1], t[2]);
                     a.sm.camera.updateMatrixWorld(true); }""",
                [list(pos), list(tgt)],
            )
            page.wait_for_timeout(900)
            page.screenshot(path=str(dest / f"{name}.png"), timeout=180_000, animations="disabled")
            print("wrote", dest / f"{name}.png")

        browser.close()

    print("\n--- scene stats ---")
    print(stats)
    if errors:
        print("\n--- console errors (%d) ---" % len(errors))
        for e in dict.fromkeys(errors):
            print(" ", e[:300])


if __name__ == "__main__":
    main()
