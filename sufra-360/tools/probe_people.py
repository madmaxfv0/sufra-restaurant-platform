"""Report the state of the guest characters and the big outdoor materials.

The promenade captures showed figures lying flat, so this reads the live
objects rather than inferring from the code: which clips actually bound to the
skeleton, what is playing, and where each character's feet are.

    python3 tools/probe_people.py
"""
import json
import sys

from playwright.sync_api import sync_playwright

from capture_360 import FLAGS

PROBE = """() => {
  const a = window.sufra360, T = window.__T__;
  const out = { people: null, materials: [] };
  const p = a.people;
  if (p) {
    const pool = (p.pool || []).map(x => ({
      clips: Object.keys(x.clips || {}), height: x.height,
      size: [+x.size.x.toFixed(2), +x.size.y.toFixed(2), +x.size.z.toFixed(2)],
    }));
    const sample = [];
    const push = (o, kind) => {
      if (!o || !o.obj) return;
      const b = new T.Box3().setFromObject(o.obj);
      const acts = [];
      if (o.mixer) o.mixer._actions.forEach(ac => {
        if (ac.isRunning()) acts.push(ac._clip.name + '@' + ac.weight.toFixed(2));
      });
      sample.push({ kind,
        pos: [+o.obj.position.x.toFixed(1), +o.obj.position.y.toFixed(2), +o.obj.position.z.toFixed(1)],
        rotX: +o.obj.rotation.x.toFixed(2), rotZ: +o.obj.rotation.z.toFixed(2),
        scale: +o.obj.scale.y.toFixed(3),
        footY: +b.min.y.toFixed(2), headY: +b.max.y.toFixed(2),
        playing: acts });
    };
    let seatedN = 0;
    for (const k of Object.keys(p.guests || {})) for (const g of p.guests[k]) { seatedN++; if (sample.length < 4) push(g, 'seated'); }
    (p.waiters || []).slice(0, 5).forEach(w => push(w, 'walker'));   // addWalkers fills 'waiters'
    out.people = { pool, seated: seatedN, walkers: (p.waiters || []).length, sample };
  }
  const want = /gravel|cobble|plaster|terrace|stone|paving|brick/i;
  const seen = new Set();
  a.sm.scene.traverse(o => {
    const ms = o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
    for (const m of ms) {
      if (!m || seen.has(m.uuid)) continue;
      const tex = m.map && m.map.image && m.map.image.src ? m.map.image.src.split('/').pop() : null;
      if (!(want.test(o.name || '') || want.test(m.name || '') || (tex && want.test(tex)))) continue;
      seen.add(m.uuid);
      out.materials.push({ obj: o.name || '(unnamed)', mat: m.name || '(unnamed)', tex,
        color: m.color ? '#' + m.color.getHexString() : null,
        rough: m.roughness, metal: m.metalness, vcol: !!m.vertexColors });
    }
  });
  return out;
}"""


def main():
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=FLAGS)
        page = b.new_page(viewport={"width": 1280, "height": 800})
        page.goto("http://127.0.0.1:8013/360", wait_until="load", timeout=120_000)
        page.wait_for_function(
            "() => { const b=document.querySelector('#entry-go'); return b && !b.disabled; }",
            timeout=180_000)
        page.evaluate("""() => { const b=document.querySelector('#entry-go'); if(b) b.click(); }""")
        page.wait_for_function(
            "() => { const p = window.sufra360.people;"
            "        return !!(p && p.enabled); }", timeout=120_000)
        page.wait_for_timeout(3000)
        page.evaluate("""async () => { window.__T__ = await import('/static/vendor/three/three.module.js'); }""")
        print(json.dumps(page.evaluate(PROBE), indent=1))
        b.close()


if __name__ == "__main__":
    main()
