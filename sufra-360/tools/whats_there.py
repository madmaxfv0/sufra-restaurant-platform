"""Name the object painting a given pixel.

Casts a ray through one screen point in a chosen capture view and reports what
it hits, which beats hiding meshes one at a time: the scene animates, so exact
pixel comparison flags everything as changed.

    python3 tools/whats_there.py from_water 900 200
"""
import json
import sys

from playwright.sync_api import sync_playwright

from capture_360 import FLAGS, VIEWS

RAY = """([p, t, u, v]) => {
  const a = window.sufra360;
  const T = window.__T__;
  a.cam.idle = false; a.cam.glide = null;
  if (!a.cam.__free) { a.cam.__free = true; a.cam.update = () => {}; }
  const cam = a.sm.camera;
  cam.position.set(p[0], p[1], p[2]);
  cam.lookAt(t[0], t[1], t[2]);
  cam.updateMatrixWorld(true);
  const rc = new T.Raycaster();
  rc.setFromCamera(new T.Vector2(u, v), cam);
  const hits = rc.intersectObjects(a.sm.scene.children, true).slice(0, 6);
  return hits.map(h => {
    const o = h.object, m = Array.isArray(o.material) ? o.material[0] : o.material;
    const chain = [];
    for (let n = o; n; n = n.parent) if (n.name) chain.unshift(n.name);
    return { dist: +h.distance.toFixed(1),
             path: chain.join('/') || '(unnamed)',
             geom: o.geometry ? o.geometry.type : '?',
             mat: m ? m.type : null,
             color: m && m.color ? '#' + m.color.getHexString() : null,
             map: m && m.map ? 'textured' : 'flat',
             point: [+h.point.x.toFixed(1), +h.point.y.toFixed(1), +h.point.z.toFixed(1)] };
  });
}"""


def main():
    view = sys.argv[1] if len(sys.argv) > 1 else "from_water"
    px = int(sys.argv[2]) if len(sys.argv) > 2 else 640
    py = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    W, H = 1280, 800
    ndc = [px / W * 2 - 1, -(py / H * 2 - 1)]
    pos, tgt = VIEWS[view]

    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": W, "height": H})
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
        page.evaluate("""async () => { window.__T__ = await import('/static/vendor/three/three.module.js'); }""")
        hits = page.evaluate(RAY, [list(pos), list(tgt), ndc[0], ndc[1]])
        browser.close()

    print(f"view {view}, pixel ({px},{py}) -> ndc {ndc[0]:.3f},{ndc[1]:.3f}")
    print(json.dumps(hits, indent=1))


if __name__ == "__main__":
    main()
