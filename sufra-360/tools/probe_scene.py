"""Introspect the live SUFRA 360 scene graph.

Lists the largest meshes with their material colour, texture and world size, so
placeholder-grade geometry can be identified by measurement instead of by eye.

    python3 tools/probe_scene.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

FLAGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]

PROBE = """() => {
  const a = window.sufra360;
  if (!a) return { error: 'app not ready' };
  const THREE = a.sm.scene.constructor;
  const out = [];
  const box = new (window.__THREE_BOX3__)();
  a.sm.scene.traverse(o => {
    if (!o.isMesh && !o.isInstancedMesh) return;
    let size;
    try {
      box.setFromObject(o);
      if (!isFinite(box.min.x) || !isFinite(box.max.x)) return;
      size = { x: box.max.x - box.min.x, y: box.max.y - box.min.y, z: box.max.z - box.min.z };
    } catch (e) { return; }
    const footprint = size.x * size.z;
    if (footprint < 9) return;               // ignore anything under ~3x3 m
    const m = Array.isArray(o.material) ? o.material[0] : o.material;
    out.push({
      name: o.name || '(unnamed)',
      type: o.geometry ? o.geometry.type : '?',
      size: [+size.x.toFixed(1), +size.y.toFixed(1), +size.z.toFixed(1)],
      footprint: Math.round(footprint),
      pos: [+o.position.x.toFixed(1), +o.position.y.toFixed(1), +o.position.z.toFixed(1)],
      mat: m ? m.type : null,
      color: m && m.color ? '#' + m.color.getHexString() : null,
      map: m && m.map ? (m.map.name || (m.map.image && m.map.image.currentSrc) || 'texture') : null,
      visible: o.visible,
    });
  });
  out.sort((x, y) => y.footprint - x.footprint);
  return { meshes: out.slice(0, 40),
           fog: a.sm.scene.fog ? { color: '#' + a.sm.scene.fog.color.getHexString(),
                                   near: a.sm.scene.fog.near, far: a.sm.scene.fog.far } : null,
           bg: a.sm.scene.background && a.sm.scene.background.isColor
                 ? '#' + a.sm.scene.background.getHexString() : String(a.sm.scene.background && a.sm.scene.background.type),
           exposure: a.sm.renderer.toneMappingExposure };
}"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=FLAGS)
        page = browser.new_page(viewport={"width": 900, "height": 600})
        page.goto("http://127.0.0.1:8013/360", wait_until="load", timeout=120_000)
        try:
            page.wait_for_function(
                "() => { const b=document.querySelector('#entry-go'); return b && !b.disabled; }",
                timeout=180_000)
        except Exception:
            print("!! entry gate never enabled", file=sys.stderr)
        page.evaluate("""() => { const b=document.querySelector('#entry-go'); if(b) b.click();
                          for (const id of ['entry','loader']) { const e=document.getElementById(id); if(e) e.remove(); } }""")
        page.wait_for_timeout(6000)
        # Box3 isn't on window; grab it off a known module-scope object
        page.evaluate("""async () => {
            const T = await import('/static/vendor/three/three.module.js');
            window.__THREE_BOX3__ = T.Box3; }""")
        data = page.evaluate(PROBE)
        browser.close()

    print(json.dumps(data, indent=1))


if __name__ == "__main__":
    main()
