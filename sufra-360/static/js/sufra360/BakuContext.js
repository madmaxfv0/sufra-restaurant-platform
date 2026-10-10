import * as THREE from '/static/vendor/three/three.module.js';

/**
 * The world beyond the restaurant.
 *
 * Rotating the camera used to find nothing: water stopped, and the scene ended.
 * This puts Baku on the horizon - a bay curving away, a city edge with towers,
 * the Flame Towers silhouette on the ridge, and a few boats out on the water.
 *
 * It is deliberately cheap. Everything sits 320-780 m out, where nobody can see
 * detail, so it is built from instanced boxes with no textures and no shadows:
 * about six draw calls for the entire city. The restaurant keeps the budget.
 */
export class BakuContext {
  constructor(scene, quality) {
    this.scene = scene;
    this.quality = quality || 'balanced';
    this.group = new THREE.Group();
    this.group.name = 'baku';
    scene.add(this.group);
    this.materials = [];
    this.windowMats = [];
    this.boats = [];
  }

  /**
   * @param quayX  the world x of the quay wall; the city sits out beyond it
   * @param centreZ the middle of the venue along the shore
   */
  build(quayX, centreZ) {
    const dense = this.quality === 'ultra' || this.quality === 'high';
    this.city(quayX, centreZ, dense);
    this.headland(quayX, centreZ);
    this.flameTowers(quayX, centreZ);
    this.vessels(quayX, centreZ, dense ? 7 : 4);
    return this;
  }

  /** a shared material per distance band, so the far city dims into the haze */
  band(colour, emissive) {
    const m = new THREE.MeshStandardMaterial({
      color: colour, roughness: 0.92, metalness: 0.0, fog: true,
    });
    m.userData.base = new THREE.Color(colour);     // setTime blends FROM this, never cumulatively
    if (emissive) { m.emissive = new THREE.Color(emissive); m.emissiveIntensity = 0.0; this.windowMats.push(m); }
    this.materials.push(m);
    return m;
  }

  /**
   * The city edge: two arcs of blocks around the bay. Baku's waterfront curves,
   * so these follow an arc rather than a straight line, which is most of what
   * makes a skyline read as a real place rather than a wall.
   */
  city(quayX, centreZ, dense) {
    const rings = [
      // [radius from the bay centre, count, min height, max height, colour, window colour]
      [340, dense ? 54 : 34, 14, 46, 0x2b3444, 0xffd9a0],
      [520, dense ? 46 : 28, 20, 72, 0x27303e, 0xffd0a0],
      [720, dense ? 34 : 20, 26, 96, 0x232b38, 0xffc890],
    ];
    // The bay opens west, so the city wraps the north, west and south horizon.
    // The arc is centred on the quay and swept AROUND west (a = 0 points west):
    // anchoring it 300 m out to sea while sweeping east put the inner ring's
    // towers at x ~ +25, i.e. eight metres off the east wall, which read as a
    // flat grey lid over the whole plot from any raised camera.
    const cx = quayX, cz = centreZ;
    const geo = new THREE.BoxGeometry(1, 1, 1);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0);
    const p = new THREE.Vector3(), sc = new THREE.Vector3();
    // nothing may stand nearer than this to the venue, whatever the arc maths says
    const KEEP_OUT = 260;

    rings.forEach(([radius, count, minH, maxH, colour, win], ring) => {
      const mat = this.band(colour, win);
      const im = new THREE.InstancedMesh(geo, mat, count);
      im.frustumCulled = false;
      im.castShadow = false; im.receiveShadow = false;
      for (let i = 0; i < count; i++) {
        // spread across the seaward arc, with a jitter so it is not a fence
        const t = i / (count - 1);
        const a = Math.PI + (-0.62 + t * 1.24) * Math.PI + (this.hash(i, ring) - 0.5) * 0.06;
        const r = radius * (0.9 + this.hash(i + 40, ring) * 0.24);
        const h = minH + this.hash(i + 80, ring) * (maxH - minH);
        const wdt = 12 + this.hash(i + 120, ring) * 26;
        const dep = 12 + this.hash(i + 160, ring) * 26;
        let px = cx + Math.cos(a) * r, pz = cz + Math.sin(a) * r;
        const d = Math.hypot(px - cx, pz - cz);
        if (d < KEEP_OUT) { const k = KEEP_OUT / (d || 1); px = cx + (px - cx) * k; pz = cz + (pz - cz) * k; }
        p.set(px, h / 2 - 1.5, pz);
        q.setFromAxisAngle(Y, a + Math.PI / 2 + (this.hash(i + 200, ring) - 0.5) * 0.5);
        sc.set(wdt, h, dep);
        m.compose(p, q, sc);
        im.setMatrixAt(i, m);
      }
      im.instanceMatrix.needsUpdate = true;
      this.group.add(im);
    });
  }

  /** the land the city sits on, so the towers do not float on the sea */
  headland(quayX, centreZ) {
    const cx = quayX, cz = centreZ;
    const mat = this.band(0x1e2530);
    // swept around west to sit under the city arc, which is anchored the same way
    const shape = new THREE.RingGeometry(280, 900, 64, 1, 0.28 * Math.PI, 1.44 * Math.PI);
    const land = new THREE.Mesh(shape, mat);
    land.rotation.x = -Math.PI / 2;
    land.position.set(cx, -1.2, cz);
    land.frustumCulled = false;
    land.receiveShadow = false;
    this.group.add(land);
  }

  /** the one silhouette that says Baku and nowhere else */
  flameTowers(quayX, centreZ) {
    const mat = this.band(0x2f3a4c, 0xff8a4a);
    const cx = quayX, cz = centreZ;
    const a = Math.PI - 0.16 * Math.PI;   // across the bay, north of west
    const r = 620;
    const bx = cx + Math.cos(a) * r, bz = cz + Math.sin(a) * r;
    for (let i = 0; i < 3; i++) {
      // a tapered flame profile: wide base, curved to a point
      const pts = [];
      for (let k = 0; k <= 12; k++) {
        const t = k / 12;
        const wdt = 20 * Math.pow(1 - t, 0.62) * (1 - 0.25 * Math.sin(t * Math.PI));
        pts.push(new THREE.Vector2(Math.max(0.5, wdt), t * 172));
      }
      const tower = new THREE.Mesh(new THREE.LatheGeometry(pts, 10), mat);
      const off = (i - 1) * 62;
      tower.position.set(bx + Math.sin(a) * off, 0, bz - Math.cos(a) * off);
      tower.rotation.y = a;
      tower.frustumCulled = false;
      this.group.add(tower);
    }
  }

  /** a few hulls out on the bay, drifting slowly */
  vessels(quayX, centreZ, count) {
    const hullMat = this.band(0x30393f);
    const deckMat = this.band(0xb9bfc4);
    const hull = new THREE.BoxGeometry(1, 1, 1);
    for (let i = 0; i < count; i++) {
      const g = new THREE.Group();
      const len = 14 + this.hash(i, 9) * 34;
      const h = new THREE.Mesh(hull, hullMat);
      h.scale.set(len, 4.5, len * 0.26);
      const d = new THREE.Mesh(hull, deckMat);
      d.scale.set(len * 0.34, 5.5, len * 0.2);
      d.position.set(-len * 0.12, 4.4, 0);
      g.add(h, d);
      const dist = 120 + this.hash(i + 30, 9) * 420;
      const along = (this.hash(i + 60, 9) - 0.5) * 700;
      g.position.set(quayX - dist, 1.6, centreZ + along);
      g.rotation.y = this.hash(i + 90, 9) * Math.PI * 2;
      g.frustumCulled = false;
      this.group.add(g);
      this.boats.push({ obj: g, speed: 0.25 + this.hash(i + 120, 9) * 0.5, phase: this.hash(i + 150, 9) * 6.28 });
    }
  }

  /** deterministic pseudo-random, so the skyline is the same on every reload */
  hash(i, salt) {
    const x = Math.sin(i * 127.1 + (salt || 0) * 311.7) * 43758.5453;
    return x - Math.floor(x);
  }

  /**
   * Lights come on as the sun goes down, and the whole city takes the colour of
   * the sky so it never looks pasted on.
   * @param dayness 1 at midday, 0 at night
   * @param haze the current sky colour
   */
  setTime(dayness, haze) {
    const night = 1 - dayness;
    for (const m of this.windowMats) m.emissiveIntensity = night * 0.75;
    // a fixed 18% of the sky colour, applied to the ORIGINAL colour each time.
    // (Build 11 lerped the live colour every frame, which converged the whole
    // city and headland to one flat tan within seconds.)
    if (haze) for (const m of this.materials) m.color.copy(m.userData.base).lerp(haze, 0.18);
  }

  update(dt, t) {
    for (const b of this.boats) {
      b.obj.position.z += Math.cos(b.obj.rotation.y) * b.speed * dt;
      b.obj.position.x -= Math.sin(b.obj.rotation.y) * b.speed * dt;
      b.obj.position.y = 1.6 + Math.sin(t * 0.6 + b.phase) * 0.25;
      b.obj.rotation.z = Math.sin(t * 0.5 + b.phase) * 0.015;
    }
  }
}
