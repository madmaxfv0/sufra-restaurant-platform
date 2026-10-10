"""Identify which mesh is painting a region of the frame.

Renders the plan view, samples a probe pixel, then hides each large mesh in turn
and re-samples. The mesh whose removal changes that pixel is the culprit.

    python3 tools/find_grey.py
"""
from playwright.sync_api import sync_playwright

FLAGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
PROBE_PX = (1100, 300)          # inside the grey mass, plan view
VIEW = ((5.5, 86, 6.0), (5.5, 0, -4.0))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto("http://127.0.0.1:8013/360", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const b=document.querySelector('#entry-go'); return b && !b.disabled; }",
            timeout=180_000)
        page.evaluate("""() => { const b=document.querySelector('#entry-go'); if(b) b.click();
                     for (const id of ['entry','loader']) { const e=document.getElementById(id); if(e) e.remove(); } }""")
        page.evaluate("""(t) => { const b=document.querySelector(`#scene-menu [data-time="${t}"]`); if(b) b.click(); }""", "day")
        page.evaluate("""(w) => { const s=document.querySelector('#wx-demo');
                     if (s) { s.value=w; s.dispatchEvent(new Event('change',{bubbles:true})); } }""", "clear")
        page.wait_for_timeout(6000)
        page.evaluate("""([p,t]) => { const a=window.sufra360; a.cam.glide=null;
                     a.sm.camera.position.set(p[0],p[1],p[2]);
                     a.cam.controls.target.set(t[0],t[1],t[2]); a.cam.controls.update(); }""",
                      [list(VIEW[0]), list(VIEW[1])])
        page.wait_for_timeout(1500)

        # index the big meshes once so we can toggle them by handle
        page.evaluate("""async () => {
            const T = await import('/static/vendor/three/three.module.js');
            const a = window.sufra360, box = new T.Box3();
            window.__big__ = [];
            a.sm.scene.traverse(o => {
              if (!(o.isMesh || o.isInstancedMesh) || !o.visible) return;
              box.setFromObject(o);
              if (!isFinite(box.min.x)) return;
              const sx = box.max.x-box.min.x, sz = box.max.z-box.min.z;
              if (sx*sz < 400) return;
              const m = Array.isArray(o.material) ? o.material[0] : o.material;
              window.__big__.push({ o, label: `${o.geometry.type} ${sx.toFixed(0)}x${sz.toFixed(0)} `
                 + `pos(${o.position.x.toFixed(0)},${o.position.y.toFixed(1)},${o.position.z.toFixed(0)}) `
                 + (m && m.color ? '#'+m.color.getHexString() : m ? m.type : '?') });
            });
            return window.__big__.length; }""")

        def sample():
            buf = page.screenshot(timeout=180_000, animations="disabled")
            from PIL import Image
            import io
            return Image.open(io.BytesIO(buf)).convert("RGB").getpixel(PROBE_PX)

        base = sample()
        print("probe pixel with everything visible:", "#%02x%02x%02x" % base)

        n = page.evaluate("() => window.__big__.length")
        print(f"testing {n} meshes with footprint > 400 m^2\n")
        for i in range(n):
            label = page.evaluate("(i) => window.__big__[i].label", i)
            page.evaluate("(i) => { window.__big__[i].o.visible = false; }", i)
            page.wait_for_timeout(400)
            got = sample()
            page.evaluate("(i) => { window.__big__[i].o.visible = true; }", i)
            changed = got != base
            print(("*** " if changed else "    ") + f"{label:<62} -> #%02x%02x%02x" % got
                  + ("   <-- THIS ONE" if changed else ""))

        browser.close()


if __name__ == "__main__":
    main()
