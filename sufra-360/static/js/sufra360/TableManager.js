import * as THREE from '/static/vendor/three/three.module.js';

// Status is read off the lamp, so the light has to actually carry to the
// tabletop and the glassware. Intensities were tuned for an ambient candle
// and the colour barely showed; these are roughly doubled and the distance
// widened so a plate near the lamp picks up the tint without the whole table
// turning green or red.
// Two vocabularies, one lamp. LIVE state (what the room is doing now) and
// SLOT state (whether this table can take the chosen booking) both land here,
// and both mean the same thing to a guest looking at the room: green = you
// can have it, red = you cannot.
const LAMP = {
  // live
  AVAILABLE:     { color: 0x5ff2a8, light: 0x3fe090, intensity: 3.2 },
  OCCUPIED:      { color: 0xff5c4a, light: 0xff3b2a, intensity: 3.6 },
  RESERVED_SOON: { color: 0xffb84a, light: 0xffa030, intensity: 3.2 },
  LATE:          { color: 0xffb84a, light: 0xffa030, intensity: 3.0 },
  CLEANING:      { color: 0x7fb4ff, light: 0x6aa0ff, intensity: 2.2 },
  HELD:          { color: 0xffb84a, light: 0xffa030, intensity: 2.6 },
  // chosen slot
  RESERVED:      { color: 0xff5c4a, light: 0xff3b2a, intensity: 3.4 },
  HELD_BY_YOU:   { color: 0x5ff2a8, light: 0x3fe090, intensity: 3.6 },
  INCOMPATIBLE:  { color: 0x6e737d, light: 0x5c616a, intensity: 1.2 },
  BLOCKED:       { color: 0x6e737d, light: 0x5c616a, intensity: 0.9 },
  PAST:          { color: 0x6e737d, light: 0x5c616a, intensity: 0.9 },
  CLOSED:        { color: 0x6e737d, light: 0x5c616a, intensity: 0.9 },
  UNKNOWN:       { color: 0xffd9a8, light: 0xffc27a, intensity: 1.4 },
};

// Which real chair model each room gets. Heights are the seat-to-back-top
// measurement so a chair never ends up giant or doll-sized next to a 0.75 m
// table: dining chairs ~0.90 m, the lounge armchair lower and wider, bar
// stools taller to meet a 1.05 m counter.
const CHAIR_MODEL = {
  // One designer chair throughout: the ProVis piece is a real 0.81 m dining
  // chair with a walnut frame, cane back and upholstered seat, which is what
  // the rooms were missing. Heights stay per-room so the terrace and bar can
  // still differ.
  window:  { name: 'provisChair', height: 0.86 },
  east:    { name: 'provisChair', height: 0.86 },
  main:    { name: 'provisChair', height: 0.86 },
  private: { name: 'provisChair', height: 0.88 },
  garden:  { name: 'provisChair', height: 0.84 },
  lounge:  { name: 'provisChair', height: 0.84 },
  terrace: { name: 'provisChair', height: 0.84 },
  bar:     { name: 'barStool',    height: 0.78 },
};

// chair upholstery and frame by room, like the reference: velvet indoors, rattan in the court, bistro on the terrace
const CHAIR_STYLE = {
  window:  { cushion: 0x2f3d63, frame: 0x3a2618, seat: 0x33406a },
  east:    { cushion: 0x2f3d63, frame: 0x3a2618, seat: 0x33406a },
  main:    { cushion: 0x2f3d63, frame: 0x3a2618, seat: 0x33406a },
  private: { cushion: 0x6d2c33, frame: 0x2b1a12, seat: 0x74323a },
  garden:  { cushion: 0xe6d9bf, frame: 0xb08856, seat: 0xd9c7a5 },
  lounge:  { cushion: 0xc9a468, frame: 0x2a2a2e, seat: 0xb9955c },
  terrace: { cushion: 0xe8dfcf, frame: 0x1e1f23, seat: 0xded3bf },
  bar:     { cushion: 0x8a6440, frame: 0x2a2a2e, seat: 0x8a6440 },
};

/**
 * Every real table from the venue API becomes a laid table: a linen top, a
 * dining chair per seat (built here, sized like a real chair and always
 * facing its table), a hurricane lantern whose glass carries the status
 * colour, a votive, napkins, and the Kenney tableware GLBs when they arrive.
 */
export class TableManager {
  constructor(scene, assets, materials, venue, tables, seats, quality, Q, halos) {
    this.scene = scene; this.assets = assets; this.mats = materials;
    this.venue = venue; this.tables = tables; this.seats = seats;
    this.quality = quality; this.Q = Q || {}; this.halos = halos;
    const m = venue.map; this.mapW = m.width; this.mapH = m.height; this.u = m.units_to_m;
    this.byId = {};
    this.group = new THREE.Group(); this.group.name = 'tables';
    scene.add(this.group);
    this.hitboxes = [];
    this.K = 0.36;                                   // map footprint -> real furniture size
    this.nodes = null;                               // set by useNodes() when a Blender venue is loaded
  }

  X(mx) { return (mx - this.mapW / 2) * this.u; }
  Z(my) { return (my - this.mapH / 2) * this.u; }

  /**
   * Use the furniture from the Blender venue instead of building it here.
   * Call this before build(). Everything the guest interacts with - the
   * click target, the highlight ring, the status lamp - is then attached to
   * your objects, and nothing procedural is created.
   */
  useNodes(tables, lamps, seats) {
    this.nodes = { tables: tables || {}, lamps: lamps || {}, seats: seats || {} };
  }

  /** the short build used when a Blender venue supplies the furniture */
  async buildOverlay() {
    const wp = new THREE.Vector3();
    const box = new THREE.Box3();
    const size = new THREE.Vector3();
    const seatsByTable = {};
    for (const s of this.seats) (seatsByTable[s.table_id] = seatsByTable[s.table_id] || []).push(s);
    let missing = 0;

    for (const t of this.tables) {
      const node = this.nodes.tables[t.id];
      let x, z, topY, radius;

      if (node) {
        node.getWorldPosition(wp);
        box.setFromObject(node); box.getSize(size);
        x = wp.x; z = wp.z;
        topY = box.max.y;
        radius = Math.max(size.x, size.z) / 2;
      } else {
        // the model does not contain this table: fall back to the data position,
        // so a half-finished Blender file still gives you a clickable restaurant
        missing++;
        x = this.X(t.x); z = this.Z(t.y);
        topY = t.zone === 'bar' ? 1.05 : 0.76;
        radius = Math.max(t.w, t.h) * this.u * this.K / 2;
      }

      const group = new THREE.Group();
      group.position.set(x, 0, z);
      group.userData.tableId = t.id;

      // click target
      const hit = new THREE.Mesh(
        new THREE.CylinderGeometry(radius + 0.5, radius + 0.5, 1.5, 12),
        new THREE.MeshBasicMaterial({ visible: false }));
      hit.position.y = 0.75; hit.userData.tableId = t.id;
      group.add(hit);
      this.hitboxes.push(hit);

      // highlight ring
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(radius + 0.16, 0.014, 6, 48),
        new THREE.MeshBasicMaterial({ color: 0xf0d9a8, transparent: true, opacity: 0 }));
      ring.rotation.x = Math.PI / 2; ring.position.y = topY + 0.02;
      group.add(ring);

      // the status lamp: your Blender lamp if you named one, otherwise a small
      // flame here so the table still reports its state
      const lamp = this.nodes.lamps[t.id];
      let flame = null, flameMat = null, lampY = topY + 0.13;
      const lampMats = [];
      if (lamp) {
        lamp.node.getWorldPosition(wp);
        lampY = wp.y;
        for (const mesh of lamp.meshes) {
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          for (const m of mats) {
            if (!m) continue;
            // clone so two tables sharing one Blender material can differ
            const c = m.clone();
            c.emissive = c.emissive || new THREE.Color(0xffc27a);
            mesh.material = Array.isArray(mesh.material) ? mesh.material.map(() => c) : c;
            lampMats.push(c);
          }
        }
      }
      if (!lampMats.length) {
        flameMat = new THREE.MeshStandardMaterial({ color: 0xffd9a8, emissive: 0xffc27a, emissiveIntensity: 1.4, roughness: 0.4 });
        flame = new THREE.Mesh(new THREE.SphereGeometry(0.03, 10, 8), flameMat);
        flame.position.set(x - group.position.x, lampY, z - group.position.z);
        group.add(flame);
        lampMats.push(flameMat);
      }

      const light = new THREE.PointLight(0xffc27a, 0.7, t.zone === 'bar' ? 2.0 : 2.9, 2);
      light.position.set(0, lampY + 0.15, 0);
      light.visible = false;
      group.add(light);
      const halo = this.halos ? this.halos.add(new THREE.Vector3(x, lampY, z), 0xffc27a, 0.42) : -1;

      // where guests sit, taken from your seat empties when they exist
      const chairs = [];
      for (const s of seatsByTable[t.id] || []) {
        const sn = this.nodes.seats[s.id];
        if (sn) {
          sn.getWorldPosition(wp);
          const e = new THREE.Euler().setFromQuaternion(sn.getWorldQuaternion(new THREE.Quaternion()), 'YXZ');
          chairs.push({ pos: wp.clone(), yaw: e.y });
        } else {
          chairs.push({ pos: new THREE.Vector3(this.X(s.x), 0.1, this.Z(s.y)), yaw: 0 });
        }
      }

      this.group.add(group);
      this.byId[t.id] = {
        node: group, flame, flameMat, lampMats, light, halo, ring, table: t,
        state: 'UNKNOWN', chairs, cur: new THREE.Color(0xffc27a), tgt: new THREE.Color(0xffc27a),
        tgtI: 0.9, pos: new THREE.Vector3(x, topY, z),
      };
    }

    // raycasting can happen before the first render, so make the matrices current now
    this.group.updateMatrixWorld(true);

    if (missing) {
      console.warn('[SUFRA 360] %d of %d tables are not in the Blender model (looked for table_<id>). ' +
                   'Those fall back to their database position.', missing, this.tables.length);
    }
    return this;
  }

  /** phase 1: everything that does not need a download. Fast, so the room fills within a second. */
  async build() {
    if (this.nodes) return this.buildOverlay();
    const linen = await this.mats.pbr('linen', { repeat: [2, 2], roughness: 0.9, fallback: 0xece4d2 });
    const woodTop = await this.mats.threeSet('hardwood2', { repeat: [1, 1], fallback: 0x6a4a2c });
    const pedestal = new THREE.MeshStandardMaterial({ color: 0x2b2a2e, metalness: 0.6, roughness: 0.45 });
    // A marble top for the round covers and a brass edge band. Linen alone
    // read as a flat pale disc from above - the reference's tables show stone
    // with a visible rim and a warm metal edge, which is what makes a two-top
    // look like restaurant furniture rather than a painted cylinder.
    // A single marble tile stretched over a 1 m round top read as a dark
    // mottled blotch - the "weird map inside the tables". Tiled tighter and
    // lightened, it reads as polished stone instead.
    const marbleTop = await this.mats.scanned('marble', 'Marble', { repeat: [3, 3], env: 1.1, roughness: 0.14, tint: 0xf2efe8, fallback: 0xf0ece4 });
    const brassEdge = new THREE.MeshStandardMaterial({ color: 0xb08d4a, metalness: 0.9, roughness: 0.26, envMapIntensity: 1.2 });
    const brass = new THREE.MeshStandardMaterial({ color: 0xb08d4a, metalness: 0.85, roughness: 0.3 });
    const glass = this.mats.glass({ color: 0xfff4e0, opacity: 0.28 });
    const candleGeo = new THREE.SphereGeometry(0.03, 10, 8);
    const legGeo = new THREE.CylinderGeometry(0.03, 0.035, 0.74, 8);

    this.chairT = {};             // zone style key -> transforms
    this.coverT = [];             // laid covers: {pos, yaw, ux,uz, rx,rz, table}
    this.lanternT = []; this.votiveT = []; this.saltT = []; this.napkinT = [];
    this.coverOwner = [];
    const seatsByTable = {};
    for (const s of this.seats) (seatsByTable[s.table_id] = seatsByTable[s.table_id] || []).push(s);

    for (const t of this.tables) {
      const x = this.X(t.x), z = this.Z(t.y);
      const w = t.w * this.u * this.K, d = t.h * this.u * this.K;
      const isBar = t.zone === 'bar';
      const topY = isBar ? 1.05 : 0.76;
      const node = new THREE.Group();
      node.position.set(x, 0, z);
      node.userData.tableId = t.id;

      // ---- top
      if (t.shape === 'round') {
        const r = w / 2;
        const pts = [new THREE.Vector2(0, 0), new THREE.Vector2(r - 0.02, 0), new THREE.Vector2(r, 0.015),
                     new THREE.Vector2(r, 0.035), new THREE.Vector2(r - 0.02, 0.045), new THREE.Vector2(0, 0.045)];
        const top = new THREE.Mesh(new THREE.LatheGeometry(pts, 40), isBar ? woodTop : marbleTop);
        top.position.y = topY; top.castShadow = true; top.receiveShadow = true;
        node.add(top);
        // brass edge band around the rim, catching the lamp
        const band = new THREE.Mesh(new THREE.TorusGeometry(r - 0.004, 0.011, 6, 44), brassEdge);
        band.rotation.x = Math.PI / 2; band.position.y = topY + 0.026;
        node.add(band);
        // a cloth drop below the rim, like a real dressed table
        if (!isBar) {
          const skirt = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.97, 0.16, 40, 1, true), linen);
          skirt.position.y = topY - 0.08; skirt.material = linen; node.add(skirt);
        }
        // The pedestal is the ProVis walnut-and-brass base, instanced below.
        // Its own glass top did not survive the FBX export, which suits us -
        // the marble top above is the one the status lamp lights.
        (this.baseT = this.baseT || []).push({
          position: new THREE.Vector3(x, 0, z),
          rotationY: (x * 1.7 + z * 0.9) % 6.283,
          scale: Math.min(1.25, Math.max(0.8, (w / 2) / 0.62)),
        });
      } else {
        // walnut top with a linen runner and four turned legs
        const top = new THREE.Mesh(new THREE.BoxGeometry(w, 0.05, d), woodTop);
        top.position.y = topY - 0.025; top.castShadow = true; top.receiveShadow = true;
        const runner = new THREE.Mesh(new THREE.BoxGeometry(w > d ? w * 0.96 : w * 0.42, 0.01, w > d ? d * 0.42 : d * 0.96), linen);
        runner.position.y = topY + 0.005;
        // a brass lip along the long edges, the way a fitted restaurant table
        // is finished, so the top is not one flat plank
        for (const sz2 of [-1, 1]) {
          const lip = new THREE.Mesh(new THREE.BoxGeometry(w, 0.016, 0.018), brassEdge);
          lip.position.set(0, topY - 0.006, sz2 * (d / 2 - 0.009));
          node.add(lip);
        }
        node.add(top, runner);
        for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
          const leg = new THREE.Mesh(legGeo, pedestal);
          leg.position.set(sx * (w / 2 - 0.12), 0.37, sz * (d / 2 - 0.12)); leg.castShadow = true;
          node.add(leg);
        }
      }

      // ---- hurricane lantern: brass foot, glass chimney, flame; the flame material is per table
      const lx = t.shape === 'round' ? 0 : 0.0, lz = t.shape === 'round' ? 0 : 0.0;
      this.lanternT.push({ position: new THREE.Vector3(x + lx, topY + 0.045, z + lz), rotationY: 0 });
      const flameMat = new THREE.MeshStandardMaterial({ color: 0xffd9a8, emissive: 0xffc27a, emissiveIntensity: 1.4, roughness: 0.4 });
      const flame = new THREE.Mesh(candleGeo, flameMat);
      flame.position.set(lx, topY + 0.045 + 0.085, lz);
      node.add(flame);
      const light = new THREE.PointLight(0xffc27a, 0.7, isBar ? 2.0 : 2.9, 2);
      light.position.set(lx, topY + 0.2, lz);
      light.visible = false;                                   // cullLights switches the nearest ones on
      node.add(light);
      const halo = this.halos ? this.halos.add(new THREE.Vector3(x + lx, topY + 0.14, z + lz), 0xffc27a, 0.42) : -1;

      // a second small light on the table: a votive, and salt & pepper
      if (!isBar) {
        this.votiveT.push({ position: new THREE.Vector3(x + 0.22, topY + 0.045, z - 0.12), rotationY: 0 });
        this.saltT.push({ position: new THREE.Vector3(x - 0.24, topY + 0.045, z + 0.1), rotationY: 0 });
        this.saltT.push({ position: new THREE.Vector3(x - 0.19, topY + 0.045, z + 0.14), rotationY: 0 });
      }

      // ---- seats: chairs and covers
      const seats = seatsByTable[t.id] || [];
      const style = CHAIR_STYLE[t.zone] || CHAIR_STYLE.main;
      const styleKey = t.zone === 'lounge' ? 'lounge' : (t.zone in CHAIR_STYLE ? t.zone : 'main');
      const chairsHere = [];
      // Chair positions are derived from the table's own geometry, not from
      // the stored seat coordinates. Those coordinates are operational - they
      // record which seat is which for a booking - and their distance from the
      // table centre was never meant to be a placement: using it put chairs a
      // metre and a half off a 1.2 m table, which is the scattered look in the
      // dining room. Seat COUNT still comes from the data, so capacity and
      // seat identity are unchanged.
      const nSeats = seats.length;
      for (let si = 0; si < nSeats; si++) {
        const s = seats[si];
        let ux, uz, dx, dz, rDir;
        if (t.shape === 'round') {
          // spread evenly round the rim, starting off-axis so a 4-top does not
          // line its chairs up with the room grid
          const a = (si / nSeats) * Math.PI * 2 + 0.39;
          ux = Math.cos(a); uz = Math.sin(a);
          dx = ux; dz = uz; rDir = w / 2;
        } else {
          // down the long sides first, then the two ends, the way a rectangular
          // table is actually laid
          const perSide = Math.max(1, Math.floor((nSeats - (nSeats > 3 ? 2 : 0)) / 2));
          const ends = nSeats - perSide * 2;
          if (si < perSide * 2) {
            const side = si % 2 === 0 ? -1 : 1;
            const k = Math.floor(si / 2);
            const along = perSide === 1 ? 0 : (k / (perSide - 1) - 0.5) * (w - 0.55);
            dx = 0; dz = side; ux = along; uz = side; rDir = d / 2;
            var alongOffset = along;
          } else {
            dx = (si - perSide * 2) === 0 ? -1 : 1; dz = 0;
            ux = dx; uz = 0; rDir = w / 2;
            var alongOffset = 0;
          }
        }
        // 0.16 m from the table edge to the chair's front: tucked in, the way a
        // laid cover reads, with room to pull the chair back
        const gap = (isBar ? 0.34 : 0.16) + 0.24;      // + half the chair depth
        let sx, sz;
        if (t.shape === 'round') {
          sx = x + ux * (rDir + gap); sz = z + uz * (rDir + gap);
        } else if (dz !== 0) {
          sx = x + (typeof alongOffset === 'number' ? alongOffset : 0);
          sz = z + dz * (rDir + gap);
        } else {
          sx = x + dx * (rDir + gap); sz = z;
        }
        const fx = -dx, fz = -dz;                      // the chair faces the table
        const yaw = Math.atan2(fx, fz);
        if (!isBar) {
          (this.chairT[styleKey] = this.chairT[styleKey] || []).push({ position: new THREE.Vector3(sx, 0.1, sz), rotationY: yaw });
        }
        chairsHere.push({ pos: new THREE.Vector3(sx, 0.1, sz), yaw });
        // the laid cover, slightly inside the rim: plate, cutlery either side, glasses beyond, napkin on the plate
        // the cover sits in front of its own chair, just inside the rim
        const inset = Math.max(0.18, rDir - 0.22);
        const cx = x - fx * inset + (t.shape !== 'round' && dz !== 0 ? (sx - x) : 0);
        const cz = z - fz * inset + (t.shape !== 'round' && dx !== 0 ? (sz - z) : 0);
        const rx = -fz, rz = fx;                          // to the right of the seat
        const ty = topY + 0.045;
        this.coverT.push({ x: cx, z: cz, y: ty, yaw, fx, fz, rx, rz, table: t.id, zone: t.zone });
        this.napkinT.push({ position: new THREE.Vector3(cx, ty + 0.014, cz), rotationY: yaw + 0.35 });
        this.coverOwner.push(t.id);
      }

      // ---- hitbox and hover ring
      const hit = new THREE.Mesh(new THREE.CylinderGeometry(Math.max(w, d) / 2 + 0.5, Math.max(w, d) / 2 + 0.5, 1.5, 12),
        new THREE.MeshBasicMaterial({ visible: false }));
      hit.position.y = 0.75; hit.userData.tableId = t.id;
      node.add(hit);
      this.hitboxes.push(hit);
      const ring = new THREE.Mesh(new THREE.TorusGeometry(Math.max(w, d) / 2 + 0.16, 0.014, 6, 48),
        new THREE.MeshBasicMaterial({ color: 0xf0d9a8, transparent: true, opacity: 0 }));
      ring.rotation.x = Math.PI / 2; ring.position.y = topY + 0.02;
      node.add(ring);

      this.group.add(node);
      this.byId[t.id] = { node, flame, flameMat, lampMats: [flameMat], light, halo, ring, table: t, state: 'UNKNOWN', chairs: chairsHere,
                          cur: new THREE.Color(0xffc27a), tgt: new THREE.Color(0xffc27a), tgtI: 0.9, pos: new THREE.Vector3(x, topY, z) };
    }


    // the ProVis table base under every round cover
    if (this.baseT && this.baseT.length) {
      this.assets.instance('provisTable', this.baseT, { height: 0.70, castShadow: true, face: false })
        .then(g => { if (g) this.group.add(g); }).catch(() => {});
    }

    // ---- chairs. Real scanned furniture per room style, instanced. The
    // primitive box chair below is kept purely as a fallback: if a GLB fails
    // to download the room still has seating rather than bare tables.
    // Orientation is not guessed - AssetManager.measureFacing works out each
    // model's own forward axis once and instance() folds it into every yaw.
    for (const key in this.chairT) {
      const list = this.chairT[key];
      if (!list.length) continue;
      const model = CHAIR_MODEL[key] || CHAIR_MODEL.main;
      const placeholder = this.buildChairs(list, CHAIR_STYLE[key] || CHAIR_STYLE.main, key === 'lounge');
      this.group.add(placeholder);
      this.assets.instance(model.name, list, { height: model.height, castShadow: true })
        .then(g => {
          if (!g) return;                            // download failed: keep the boxes
          this.group.remove(placeholder);
          placeholder.traverse(o => { if (o.geometry) o.geometry.dispose(); });
          this.group.add(g);
        })
        .catch(() => {});
    }
    this.group.add(this.buildLanterns(this.lanternT, brass, glass));
    if (this.votiveT.length) this.group.add(this.buildVotives(this.votiveT, glass));
    if (this.saltT.length) this.group.add(this.instanced(new THREE.CylinderGeometry(0.014, 0.016, 0.06, 8),
      new THREE.MeshStandardMaterial({ color: 0xe9e4da, roughness: 0.35 }), this.saltT, 0.03));
    if (this.napkinT.length) this.group.add(this.instanced(new THREE.BoxGeometry(0.09, 0.012, 0.15),
      new THREE.MeshStandardMaterial({ color: 0xf3eee4, roughness: 0.95 }), this.napkinT, 0.006));
    return this;
  }

  /** phase 2: the Kenney tableware GLBs. Runs after the scene is visible; adds when ready. */
  async buildTableware() {
    if (this.nodes) return 0;                      // your Blender model already has the covers
    const plateT = [], wineT = [], waterT = [], forkT = [], knifeT = [], dishT = [], cupT = [], bottleT = [];
    // A real plated main - meat / grain / veg, cycled per seat rather than
    // per table so a four-top does not eat identically - shown ONLY when the
    // table is occupied, same toggle as the olive starter dish.
    const mealMeatT = [], mealGrainT = [], mealVegT = [];
    for (const c of this.coverT) {
      const p = (ax, az) => new THREE.Vector3(c.x + c.fx * ax + c.rx * az, c.y, c.z + c.fz * ax + c.rz * az);
      plateT.push({ position: p(0, 0), rotationY: c.yaw });
      forkT.push({ position: p(0, -0.16), rotationY: c.yaw + Math.PI / 2 });
      knifeT.push({ position: p(0, 0.16), rotationY: c.yaw + Math.PI / 2 });
      wineT.push({ position: p(0.14, 0.13), rotationY: 0 });
      waterT.push({ position: p(0.18, 0.23), rotationY: 0 });
      dishT.push({ position: p(0, 0).setY(c.y + 0.012), rotationY: c.yaw, scale: 1 });
      if (c.zone === 'garden' || c.zone === 'lounge') cupT.push({ position: p(0.04, -0.2), rotationY: c.yaw });
      const mealPos = { position: p(0, 0).setY(c.y + 0.013), rotationY: c.yaw, table: c.table };
      const mealVariant = (c.table.charCodeAt(1) + c.table.length + this.coverOwner.length) % 3;
      (mealVariant === 0 ? mealMeatT : mealVariant === 1 ? mealGrainT : mealVegT).push(mealPos);
    }
    // Centrepieces and food, as a small set of reusable variants cycled by
    // table index rather than a hand-made layout per table: four variants
    // across 25 tables reads as a laid room, and every one is still just an
    // extra instance on an existing InstancedMesh.
    const vaseT = [], vaseBrassT = [], lampT = [], pomT = [], appleT = [];
    for (const t of this.tables) {
      const e = this.byId[t.id]; if (!e || t.zone === 'bar' || !e.chairs.length) continue;
      bottleT.push({ position: new THREE.Vector3(e.pos.x + 0.16, e.pos.y + 0.045, e.pos.z + 0.18), rotationY: 0, table: t.id });
      const centre = new THREE.Vector3(e.pos.x, e.pos.y + 0.045, e.pos.z);
      const variant = (t.id.charCodeAt(1) + t.id.charCodeAt(2)) % 4;
      const yaw = (e.pos.x * 1.7 + e.pos.z) % 6.28;
      // every table keeps a lamp - it is the status lamp's physical body and
      // the reference has one on every cover
      lampT.push({ position: centre.clone().add(new THREE.Vector3(0.16, 0, -0.14)), rotationY: yaw });
      if (variant === 0) vaseT.push({ position: centre.clone(), rotationY: yaw });
      else if (variant === 1) vaseBrassT.push({ position: centre.clone(), rotationY: yaw });
      else if (variant === 2) {
        vaseT.push({ position: centre.clone(), rotationY: yaw });
        pomT.push({ position: centre.clone().add(new THREE.Vector3(-0.16, 0, 0.10)), rotationY: yaw });
      } else {
        // a bowl of fruit: the food variant, offset so it never sits on top of
        // the bottle already placed at +0.16/+0.18
        pomT.push({ position: centre.clone().add(new THREE.Vector3(-0.1, 0, -0.06)), rotationY: yaw });
        appleT.push({ position: centre.clone().add(new THREE.Vector3(-0.02, 0, 0.02)), rotationY: yaw * 1.3 });
      }
    }
    const A = this.assets;
    const jobs = [
      ['plateDinner', plateT, { width: 0.26, castShadow: false }],
      ['fork', forkT, { width: 0.18, castShadow: false }],
      ['knife', knifeT, { width: 0.2, castShadow: false }],
      ['glassWine', wineT, { height: 0.15, castShadow: false }],
      ['glassWater', waterT, { height: 0.09, castShadow: false }],
      ['cupSaucer', cupT, { width: 0.13, castShadow: false }],
      ['dishOlives', dishT, { width: 0.22, castShadow: false }],
      ['wineRed', bottleT, { height: 0.3, castShadow: false }],
      ['vaseCeramic', vaseT, { height: 0.22, castShadow: false }],
      ['vaseBrass', vaseBrassT, { height: 0.26, castShadow: false }],
      ['tableLamp', lampT, { height: 0.34, castShadow: false }],
      ['foodPomegranate', pomT, { height: 0.09, castShadow: false }],
      ['foodApple', appleT, { height: 0.08, castShadow: false }],
      ['dishMeat', mealMeatT, { width: 0.24, castShadow: false }],
      ['dishGrain', mealGrainT, { width: 0.24, castShadow: false }],
      ['dishVeg', mealVegT, { width: 0.24, castShadow: false }],
    ];
    const results = await Promise.all(jobs.map(([name, list, opts]) => list.length ? A.instance(name, list, opts).catch(() => null) : null));
    const placed = [];
    results.forEach((g, i) => {
      const name = jobs[i][0];
      if (!g) { if (name === 'plateDinner') this.fallbackPlates(plateT); return; }
      if (name === 'dishOlives') { this.food = g; this.foodT = dishT; }
      if (name === 'wineRed') { this.bottles = g; this.bottleT = bottleT; }
      if (name === 'dishMeat') { this.mealMeat = g; this.mealMeatT = mealMeatT; }
      if (name === 'dishGrain') { this.mealGrain = g; this.mealGrainT = mealGrainT; }
      if (name === 'dishVeg') { this.mealVeg = g; this.mealVegT = mealVegT; }
      placed.push(g);
    });
    for (const p of placed) this.group.add(p);
    this.setSeatedVisuals(this._states || {});
    return placed.length;
  }

  /** a dining chair: four legs, seat, cushion, tilted backrest. Sized 0.46 x 0.9 x 0.48 m. */
  buildChairs(list, style, arm) {
    const g = new THREE.Group(); g.name = 'chairs';
    const frame = new THREE.MeshStandardMaterial({ color: style.frame, roughness: 0.55, metalness: style.frame === 0x1e1f23 || style.frame === 0x2a2a2e ? 0.6 : 0.05 });
    const cushion = new THREE.MeshStandardMaterial({ color: style.cushion, roughness: 0.92 });
    const seatMat = new THREE.MeshStandardMaterial({ color: style.seat, roughness: 0.9 });
    const W = arm ? 0.6 : 0.46, D = arm ? 0.6 : 0.48;
    const parts = [
      // [geometry, material, local offset (x,y,z), tilt]
      [new THREE.BoxGeometry(W, 0.05, D), frame, [0, 0.44, 0], 0],
      [new THREE.BoxGeometry(W - 0.04, 0.045, D - 0.04), seatMat, [0, 0.49, 0], 0],
      [new THREE.BoxGeometry(W - 0.02, 0.42, 0.05), cushion, [0, 0.74, -D / 2 + 0.025], -0.1],
      [new THREE.BoxGeometry(W, 0.06, 0.06), frame, [0, 0.96, -D / 2 + 0.02], -0.1],
      [new THREE.CylinderGeometry(0.018, 0.022, 0.44, 6), frame, [W / 2 - 0.03, 0.22, D / 2 - 0.03], 0],
      [new THREE.CylinderGeometry(0.018, 0.022, 0.44, 6), frame, [-W / 2 + 0.03, 0.22, D / 2 - 0.03], 0],
      [new THREE.BoxGeometry(0.035, 0.98, 0.035), frame, [W / 2 - 0.03, 0.49, -D / 2 + 0.03], 0],
      [new THREE.BoxGeometry(0.035, 0.98, 0.035), frame, [-W / 2 + 0.03, 0.49, -D / 2 + 0.03], 0],
    ];
    if (arm) {
      parts.push([new THREE.BoxGeometry(0.06, 0.28, D - 0.08), cushion, [W / 2 - 0.03, 0.62, 0], 0]);
      parts.push([new THREE.BoxGeometry(0.06, 0.28, D - 0.08), cushion, [-W / 2 + 0.03, 0.62, 0], 0]);
    }
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
    const tilt = new THREE.Quaternion(), yawQ = new THREE.Quaternion(), Y = new THREE.Vector3(0, 1, 0), Xa = new THREE.Vector3(1, 0, 0);
    for (const [geo, mat, off, tx] of parts) {
      const im = new THREE.InstancedMesh(geo, mat, list.length);
      im.castShadow = true; im.receiveShadow = true;
      list.forEach((c, i) => {
        yawQ.setFromAxisAngle(Y, c.rotationY);
        tilt.setFromAxisAngle(Xa, tx);
        q.copy(yawQ).multiply(tilt);
        p.set(off[0], off[1], off[2]).applyQuaternion(yawQ).add(c.position);
        m.compose(p, q, s);
        im.setMatrixAt(i, m);
      });
      im.instanceMatrix.needsUpdate = true;
      g.add(im);
    }
    return g;
  }

  buildLanterns(list, brass, glass) {
    const g = new THREE.Group(); g.name = 'lanterns';
    g.add(this.instanced(new THREE.CylinderGeometry(0.052, 0.06, 0.02, 14), brass, list, 0.01));
    g.add(this.instanced(new THREE.CylinderGeometry(0.038, 0.042, 0.15, 14, 1, true), glass, list, 0.095));
    g.add(this.instanced(new THREE.CylinderGeometry(0.03, 0.05, 0.02, 14), brass, list, 0.18));
    g.add(this.instanced(new THREE.CylinderGeometry(0.008, 0.008, 0.05, 6), brass, list, 0.035));
    return g;
  }

  buildVotives(list, glass) {
    const g = new THREE.Group(); g.name = 'votives';
    g.add(this.instanced(new THREE.CylinderGeometry(0.03, 0.026, 0.05, 12, 1, true), glass, list, 0.025));
    const flame = new THREE.MeshStandardMaterial({ color: 0xffe0b0, emissive: 0xffb86a, emissiveIntensity: 2.2 });
    g.add(this.instanced(new THREE.SphereGeometry(0.012, 8, 6), flame, list, 0.03));
    if (this.halos) for (const v of list) this.halos.add(v.position.clone().add(new THREE.Vector3(0, 0.04, 0)), 0xffb86a, 0.16);
    return g;
  }

  instanced(geo, mat, list, y) {
    const im = new THREE.InstancedMesh(geo, mat, list.length);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
    const Y = new THREE.Vector3(0, 1, 0);
    list.forEach((c, i) => {
      q.setFromAxisAngle(Y, c.rotationY || 0);
      p.copy(c.position); p.y += y || 0;
      m.compose(p, q, s); im.setMatrixAt(i, m);
    });
    im.instanceMatrix.needsUpdate = true;
    im.castShadow = false; im.receiveShadow = true;
    return im;
  }

  fallbackPlates(list) {
    const mat = new THREE.MeshStandardMaterial({ color: 0xf4f1ea, roughness: 0.3 });
    const geo = new THREE.CylinderGeometry(0.13, 0.11, 0.012, 24);
    this.group.add(this.instanced(geo, mat, list, 0.006));
  }

  /** food on the plates and a bottle on the table only where someone is seated */
  setSeatedVisuals(stateById) {
    this._states = stateById;
    const hide = new THREE.Matrix4().makeScale(0.0001, 0.0001, 0.0001);
    const apply = (group, list) => {
      if (!group) return;
      group.children.forEach(im => {
        if (!im.isInstancedMesh) return;
        if (!im.userData.full) { im.userData.full = []; for (let i = 0; i < im.count; i++) { const m = new THREE.Matrix4(); im.getMatrixAt(i, m); im.userData.full.push(m); } }
        list.forEach((t, i) => {
          const id = t.table || this.coverOwner[i];
          const on = stateById[id] === 'OCCUPIED';
          im.setMatrixAt(i, on ? im.userData.full[i] : hide);
        });
        im.instanceMatrix.needsUpdate = true;
      });
    };
    apply(this.food, this.foodT || []);
    apply(this.bottles, this.bottleT || []);
    apply(this.mealMeat, this.mealMeatT || []);
    apply(this.mealGrain, this.mealGrainT || []);
    apply(this.mealVeg, this.mealVegT || []);
  }

  /** live feed -> lamp colours, with a 300-700 ms fade rather than a switch */
  applyLive(rows) {
    const states = {};
    for (const r of rows) states[r.table_id] = r.state;
    this.setSeatedVisuals(states);
    for (const r of rows) {
      const e = this.byId[r.table_id];
      if (!e) continue;
      e.live = r;
      if (e.state !== r.state) {
        e.state = r.state;
        const L = LAMP[r.state] || LAMP.UNKNOWN;
        e.tgt.set(L.light); e.tgtI = L.intensity;
        e.fadeFrom = e.cur.clone(); e.fadeStart = performance.now(); e.fadeMs = 320 + Math.random() * 380;
      }
    }
  }

  hover(id) {
    for (const k in this.byId) { const e = this.byId[k]; if (k !== this.pinned) e.ring.material.opacity = k === id ? 0.55 : 0; }
  }

  update(dt, t) {
    const white = TableManager._white || (TableManager._white = new THREE.Color(0xffffff));
    for (const k in this.byId) {
      const e = this.byId[k];
      if (e.fadeStart) {
        const kk = Math.min(1, (performance.now() - e.fadeStart) / e.fadeMs);
        const ease = kk * (2 - kk);
        // dip through dark so the change reads as a lamp, not a colour swap
        const dip = 1 - 0.6 * Math.sin(kk * Math.PI);
        e.cur.lerpColors(e.fadeFrom, e.tgt, ease);
        for (const m of (e.lampMats || [e.flameMat])) {
          if (!m) continue;
          if (m.emissive) m.emissive.copy(e.cur);
          if (m.color) m.color.copy(e.cur).lerp(white, 0.5);
        }
        e.light.color.copy(e.cur); e.light.intensity = e.tgtI * dip;
        if (this.halos) this.halos.setColor(e.halo, e.cur);
        if (kk >= 1) e.fadeStart = 0;
      } else {
        // candle-like breathing
        const f = 1 + 0.06 * Math.sin(t * 5.3 + e.pos.x) * Math.sin(t * 1.7 + e.pos.z);
        e.light.intensity = e.tgtI * f;
        for (const m of (e.lampMats || [e.flameMat])) {
          if (m && m.emissiveIntensity !== undefined) m.emissiveIntensity = 2.6 * f;
        }
      }
    }
  }
}
