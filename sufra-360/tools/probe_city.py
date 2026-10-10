"""Where did the Baku massing actually end up?

Reads every instance matrix out of the live BakuContext meshes and reports the
world-space bounds, so the skyline can be checked against the venue plot by
number instead of by squinting at a screenshot.

    python3 tools/probe_city.py
"""
import json

from playwright.sync_api import sync_playwright

FLAGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

PROBE = """async () => {
  const T = await import('/static/vendor/three/three.module.js');
  const a = window.sufra360;
  const baku = a.sm.scene.getObjectByName('baku');
  if (!baku) return { error: 'no baku group' };
  const m = new T.Matrix4(), p = new T.Vector3(), s = new T.Vector3(), q = new T.Quaternion();
  const out = [];
  baku.traverse(o => {
    if (o.isInstancedMesh) {
      let near = 0, minX = 1e9, maxX = -1e9, maxH = 0;
      for (let i = 0; i < o.count; i++) {
        o.getMatrixAt(i, m); m.decompose(p, q, s);
        minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
        maxH = Math.max(maxH, s.y);
        if (p.x > -60 && Math.abs(p.z) < 120) near++;
      }
      out.push({ kind: 'instanced', count: o.count, x: [+minX.toFixed(0), +maxX.toFixed(0)],
                 tallest: +maxH.toFixed(0), overVenue: near });
    } else if (o.isMesh) {
      out.push({ kind: o.geometry.type, pos: [+o.position.x.toFixed(0), +o.position.y.toFixed(0),
                 +o.position.z.toFixed(0)] });
    }
  });
  // and what the horizon camera is actually pointed at
  const cam = a.sm.camera, dir = new T.Vector3();
  cam.getWorldDirection(dir);
  return { meshes: out,
           camera: { pos: [+cam.position.x.toFixed(1), +cam.position.y.toFixed(1), +cam.position.z.toFixed(1)],
                     dir: [+dir.x.toFixed(2), +dir.y.toFixed(2), +dir.z.toFixed(2)], fov: cam.fov },
           fog: a.sm.scene.fog ? { type: a.sm.scene.fog.type || 'FogExp2',
                                   density: a.sm.scene.fog.density, far: a.sm.scene.fog.far } : null };
}"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": 900, "height": 600})
        page.goto("http://127.0.0.1:8013/360", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const b=document.querySelector('#entry-go'); return b && !b.disabled; }",
            timeout=180_000)
        page.evaluate("""() => { const b=document.querySelector('#entry-go'); if(b) b.click();
                     for (const id of ['entry','loader']) { const e=document.getElementById(id); if(e) e.remove(); } }""")
        page.wait_for_timeout(6000)
        page.evaluate("""() => { const a = window.sufra360; a.cam.glide = null;
                     a.sm.camera.position.set(-9, 2.4, 4);
                     a.cam.controls.target.set(-70, 4, -6); a.cam.controls.update(); }""")
        page.wait_for_timeout(800)
        print(json.dumps(page.evaluate(PROBE), indent=1))
        browser.close()


if __name__ == "__main__":
    main()
