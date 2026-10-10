"""Report what the parkland scatter actually placed: count, extent, height range.

Guessing at the density from the placement maths is how the first pass ended up
with a band of fifteen trees on the horizon; this reads the live InstancedMesh.

    python3 tools/probe_park.py
"""
import json

from playwright.sync_api import sync_playwright

from capture_360 import FLAGS

PROBE = """() => {
  const a = window.sufra360;
  const g = a.sm.scene.getObjectByName('parkland');
  if (!g) return { error: 'no parkland group in the scene' };
  const T = window.__T__;
  const m = new T.Matrix4(), p = new T.Vector3(), q = new T.Quaternion(), s = new T.Vector3();
  const out = { meshes: g.children.length, instances: 0, tris: 0, pts: [] };
  // Each species contributes one InstancedMesh per sub-mesh - trunk, branch,
  // leaf - and all of them carry the SAME per-tree transforms, so counting
  // every child reported 753 trees where there are 252. Dedupe on the species
  // tag buildParkland writes into userData. (An earlier attempt keyed on
  // instanceMatrix.uuid, which three.js does not put on BufferAttributes: the
  // key came back undefined for every mesh and collapsed the count to one
  // species' worth.)
  const seen = new Set();
  for (const im of g.children) {
    out.instances += 0;
    const idx = im.geometry.index;
    out.tris += (idx ? idx.count : im.geometry.attributes.position.count) / 3 * im.count;
    const key = im.userData.species;   // set by buildParkland
    if (seen.has(key)) continue;
    seen.add(key);
    out.instances += im.count;
    for (let i = 0; i < im.count; i++) {
      im.getMatrixAt(i, m); m.decompose(p, q, s);
      out.pts.push([+p.x.toFixed(1), +p.y.toFixed(2), +p.z.toFixed(1), +s.x.toFixed(3)]);
    }
  }
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
        # the scatter is a deferred background job and lands 15-20 s in under
        # SwiftShader; polling beats a fixed sleep that was silently too short
        page.wait_for_function(
            "() => { const a = window.sufra360;"
            "        return !!(a && a.sm.scene.getObjectByName('parkland')); }",
            timeout=120_000)
        page.evaluate("""async () => { window.__T__ = await import('/static/vendor/three/three.module.js'); }""")
        r = page.evaluate(PROBE)
        b.close()

    if "error" in r:
        print(r["error"])
        return
    pts = r.pop("pts")
    xs = [p[0] for p in pts]; zs = [p[2] for p in pts]
    ys = [p[1] for p in pts]; sc = [p[3] for p in pts]
    print(json.dumps(r, indent=1))
    print(f"trees placed   {len(pts)}")
    print(f"x range        {min(xs):8.1f} .. {max(xs):8.1f}")
    print(f"z range        {min(zs):8.1f} .. {max(zs):8.1f}")
    print(f"base y range   {min(ys):8.2f} .. {max(ys):8.2f}")
    print(f"scale range    {min(sc):8.3f} .. {max(sc):8.3f}")
    print(f"total triangles {r['tris']:,.0f}")


if __name__ == "__main__":
    main()
