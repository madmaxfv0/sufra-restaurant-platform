import * as THREE from '/static/vendor/three/three.module.js';

/**
 * Builds the venue from venue/floor.json geometry. Map units -> metres.
 *
 * Two phases so the room appears fast:
 *   buildBase()  - ground, floors, walls, glass, bar, pass, quay   (no downloads except textures)
 *   buildDecor() - everything the reference image has that a plan does not:
 *                  lamp posts with lanterns, tree rings, benches, planter troughs,
 *                  hedges, pendants over the bar, glass rack, rugs, wall art,
 *                  a fire bowl in the lounge, terrace heaters, the lit SUFRA sign,
 *                  potted plants in every room corner, the kiosk, the entrance.
 * Furniture arrives from TableManager; trees from FoliageSystem.
 */
export class RestaurantBuilder {
  constructor(scene, assets, materials, venue, Q, halos) {
    this.scene = scene;
    this.assets = assets;
    this.mats = materials;
    this.venue = venue;
    this.Q = Q || {};
    this.halos = halos;
    const m = venue.map;
    this.mapW = m.width; this.mapH = m.height; this.u = m.units_to_m;
    this.group = new THREE.Group();
    this.group.name = 'restaurant';
    scene.add(this.group);
    this.emissives = [];          // lamps that flicker: {mat, light, base, phase, halo}
    this.lampLights = [];         // every point light the app may cull by distance
    this.stringLightMats = [];
    this.stringHalos = [];
    this.umbrellas = [];
    this.shrubSpots = [];
    this.flames = [];
    this._geo = {};
  }

  X(mx) { return (mx - this.mapW / 2) * this.u; }
  Z(my) { return (my - this.mapH / 2) * this.u; }
  W(units) { return units * this.u; }

  /**
   * Height of the far ground at a world point, in metres.
   *
   * The land plane and the parkland scatter both read this, so a scattered
   * tree stands on the surface rather than hovering over it or sinking into
   * it. It is analytic on purpose: no texture to sample, no order dependency
   * between the two systems that use it.
   *
   * It returns exactly 0 within 70 m of the plot. The promenade, the kerb, the
   * quay face and the apron are all flat slabs placed at fixed heights out to
   * about 62 m, and any relief under them would open gaps.
   */
  groundY(x, z) {
    const d = Math.hypot(x - (this.quayX == null ? 0 : this.quayX), z);
    const ramp = Math.min(1, Math.max(0, (d - 70) / 60));
    if (ramp <= 0) return 0;
    const n = Math.sin(x * 0.0125 + 0.7) * Math.cos(z * 0.0091 - 1.4) * 0.62
            + Math.sin(x * 0.0308 - 2.2) * Math.sin(z * 0.0271 + 0.5) * 0.26
            + Math.sin((x + z) * 0.0173) * 0.18;
    return n * ramp * ramp;
  }
  G(key, make) { return this._geo[key] || (this._geo[key] = make()); }

  slab(box, mat, y, thickness, receive) {
    const [x1, y1, x2, y2] = box;
    const w = this.W(x2 - x1), d = this.W(y2 - y1);
    const g = new THREE.BoxGeometry(w, thickness, d);
    const m = new THREE.Mesh(g, mat);
    m.position.set(this.X((x1 + x2) / 2), y - thickness / 2, this.Z((y1 + y2) / 2));
    m.receiveShadow = receive !== false;
    this.group.add(m);
    return m;
  }

  wallSegment(x1, y1, x2, y2, h, thick, mat, y0) {
    const ax = this.X(x1), az = this.Z(y1), bx = this.X(x2), bz = this.Z(y2);
    const len = Math.hypot(bx - ax, bz - az);
    const g = new THREE.BoxGeometry(len, h, thick);
    const m = new THREE.Mesh(g, mat);
    m.position.set((ax + bx) / 2, (y0 || 0) + h / 2, (az + bz) / 2);
    m.rotation.y = -Math.atan2(bz - az, bx - ax);
    m.castShadow = true; m.receiveShadow = true;
    this.group.add(m);
    return m;
  }

  glassWall(x1, y1, x2, y2, h, y0) {
    const m = this.wallSegment(x1, y1, x2, y2, h, 0.04, this.glassMat, y0);
    m.castShadow = false; m.receiveShadow = false;
    // mullions and a top rail
    const ax = this.X(x1), az = this.Z(y1), bx = this.X(x2), bz = this.Z(y2);
    const len = Math.hypot(bx - ax, bz - az), n = Math.max(2, Math.round(len / 2.3));
    const frame = this.frameMat;
    const geo = this.G('mullion' + h.toFixed(2), () => new THREE.BoxGeometry(0.08, h, 0.08));
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const p = new THREE.Mesh(geo, frame);
      p.position.set(ax + (bx - ax) * t, (y0 || 0) + h / 2, az + (bz - az) * t);
      p.castShadow = true;
      this.group.add(p);
    }
    const rail = new THREE.Mesh(new THREE.BoxGeometry(len, 0.1, 0.1), frame);
    rail.position.set((ax + bx) / 2, (y0 || 0) + h, (az + bz) / 2); rail.rotation.y = -Math.atan2(bz - az, bx - ax);
    this.group.add(rail);
    return m;
  }

  // =============================================================== phase 1
  async buildBase() {
    const g = this.venue.geometry;
    const R = g.rooms;

    // ---- materials (generated PBR sets where the project has them; sensible colours where it does not)
    const [cobble, terrace, gravel, wood, plaster, marble, tiles, brick, stone, herringbone] = await Promise.all([
      this.mats.pbr('cobble', { repeat: [4, 14], outdoor: true, wetRough: 0.18, normalScale: 1.4, fallback: 0x8f8375 }),
      this.mats.pbr('terrace', { repeat: [5, 3], outdoor: true, wetRough: 0.2, fallback: 0xb59a78 }),
      this.mats.pbr('gravel', { repeat: [5, 3], outdoor: true, wetRough: 0.35, roughness: 0.95, fallback: 0x9b8b72 }),
      this.mats.scanned('wood', 'WoodFloor043', { repeat: [4, 8], env: 0.8, normalScale: 1.2, fallback: 0x7a5636 }),
      this.mats.pbr('stucco', { repeat: [11, 3.2], roughness: 0.93, normalScale: 2.2, tint: 0xd8cdb8, env: 0.25, fallback: 0xd0c5b0 }),
      this.mats.scanned('marble', 'Marble', { repeat: [1, 2], roughness: 0.35, env: 1.4, fallback: 0xe6e2da }),
      this.mats.scanned('tiles', 'Tiles', { repeat: [3, 2], env: 0.6, fallback: 0xbdb6a8 }),
      this.mats.threeSet('brick', { repeat: [6, 1], fallback: 0x8a5a48 }),
      this.mats.pbr('terrace', { repeat: [2, 26], outdoor: true, wetRough: 0.2, tint: 0xd9d2c4, fallback: 0xbfb6a6 }),
      this.mats.pbr('herringbone', { repeat: [3, 5], roughness: 0.5, env: 0.7, fallback: 0x6b4a30 }),
    ]);
    this.dark = new THREE.MeshStandardMaterial({ color: 0x1e2026, roughness: 0.6, metalness: 0.2 });
    // the bar/pass base cabinets were this flat navy slab with no map - a
    // visible grey box front-on. Give it the same dark-wood panel look as a
    // real counter kick panel: reuse the scanned wood, tinted near-black.
    this.darkPanel = await this.mats.pbr('paving', { repeat: [3, 1.4], roughness: 0.55, metalness: 0.1, tint: 0x24211c, fallback: 0x1e2026 });
    this.frameMat = new THREE.MeshStandardMaterial({ color: 0x2b2d33, roughness: 0.5, metalness: 0.7 });
    this.brass = new THREE.MeshStandardMaterial({ color: 0xb08d4a, metalness: 0.85, roughness: 0.32 });
    this.iron = new THREE.MeshStandardMaterial({ color: 0x1b1c20, metalness: 0.75, roughness: 0.4 });
    this.glassMat = this.mats.glass();
    this.lampGlass = this.mats.glass({ color: 0xfff1d6, opacity: 0.3 });
    this.wood = wood; this.plaster = plaster; this.marble = marble;
    const wallMat = plaster;

    // ---- the land. It starts AT the quay (build 11 ran it under the water, and
    // the swell dipped below it, which showed as a black wedge) and runs 320 m
    // inland and along the shore, so it meets the city rather than a void.
    // Near the plot it is dark paving; further out it reads as park.
    const quayX = this.X(g.water[2]);
    this.quayX = quayX;      // groundY() below reads it, so it has to be set first
    const LAND = 640;
    // Scanned grass (ambientCG Grass004, CC0). This used to be the gravel set
    // with a green tint multiplied over it, which is why it read as dirt: the
    // albedo carried pebble shapes, not blades. repeat 150 puts one 2 m grass
    // tile every 2.1 m across the 320 m plane, which holds up to about 40 m
    // out and reads as texture beyond that.
    // Scanned sets shared by the promenade extension, the kerbs and the quay
    // faces. Built once here and read by shoreline() and quayEdge() through
    // this.pavingMat / kerbMat / concreteMat, so the whole waterfront is one
    // set of materials rather than five anonymous grey boxes.
    const [pavingMat, kerbMat, concreteMat, apronMat] = await Promise.all([
      this.mats.pbr('paving',   { repeat: [3, 22], outdoor: true, wetRough: 0.16, normalScale: 1.3, fallback: 0x8f8375 }),
      this.mats.pbr('concrete', { repeat: [1, 30], outdoor: true, wetRough: 0.2, tint: 0xbdb4a6, fallback: 0x8c8378 }),
      this.mats.pbr('concrete', { repeat: [1, 26], outdoor: true, wetRough: 0.25, tint: 0x7d7568, roughness: 0.95, fallback: 0x5e5a54 }),
      this.mats.pbr('concrete', { repeat: [26, 46], outdoor: true, wetRough: 0.3, tint: 0x8d8b84, roughness: 0.92, fallback: 0x4a4c52 }),
    ]);
    this.pavingMat = pavingMat; this.kerbMat = kerbMat;
    this.concreteMat = concreteMat; this.apronMat = apronMat;

    const park = await this.mats.pbr('grass', { repeat: [150, 150], outdoor: true, wetRough: 0.5, roughness: 0.92, fallback: 0x5c7a3e });
    // 320 x 640 m of dead-flat single-tint quad was the largest remaining
    // placeholder in the scene: from the water it read as a sand-coloured
    // slab. It now carries the same gentle relief the parkland scatter plants
    // on (see groundY) plus per-vertex colour drift, so the far ground has
    // form and hue variation instead of one value. 48 x 96 segments is 9 k
    // triangles - nothing, next to what it buys.
    // The material is only ever used here (AssetManager.pbr caches on the
    // options object, and this tint/repeat pair is unique), so switching it to
    // vertex colours cannot leak into another surface. It is deliberately not
    // cloned: cloning would drop it out of the outdoor wet-weather list.
    park.vertexColors = true;
    const baseGeo = new THREE.PlaneGeometry(320, LAND, 48, 96);
    const pos = baseGeo.attributes.position;
    const col = new Float32Array(pos.count * 3);
    const c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      // the plane is rotated -90 about X, so local (x, y) lands at world (x + cx, -y)
      const wx = pos.getX(i) + quayX + 160, wz = -pos.getY(i);
      const h = this.groundY(wx, wz);
      pos.setZ(i, h);                                  // local +z becomes world +y
      // Vertex colour MULTIPLIES the albedo and the material tint, so it has to
      // sit around 1.0. The first attempt used a 0.3-0.7 olive here and turned
      // the whole far ground into a near-black band under daylight.
      // Hollows read damper and greener, rises drier and paler.
      // Two octaves at 180 m and 70 m. The first attempt used a single 0.013
      // term - a 480 m wavelength, longer than the visible ground, so the
      // mottling averaged out to a flat tone and bought nothing.
      const drift = Math.sin(wx * 0.035 + 2.1) * Math.sin(wz * 0.029 - 0.4)
                  + 0.55 * Math.sin(wx * 0.091 - 1.1) * Math.sin(wz * 0.084 + 2.6);
      const v = 0.92 + h * 0.10 + drift * 0.17;
      c.setRGB(v * (1 + drift * 0.05 + h * 0.03),
               v * (1 + drift * 0.01),
               v * (1 - drift * 0.06 - h * 0.04));
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    }
    baseGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    baseGeo.computeVertexNormals();
    const base = new THREE.Mesh(baseGeo, park);
    base.rotation.x = -Math.PI / 2; base.position.set(quayX + 160, -0.06, 0); base.receiveShadow = true;
    this.group.add(base);
    // A narrow paved apron hugging the plot, not a slab around it. It used to
    // be mapW+14 x mapH+40 - 50 by 104 metres of dark concrete - which from
    // any distance read as the restaurant standing on a black platform with
    // grass beyond it. It is now the plot footprint plus a 3 m margin, so the
    // lawn runs right up to the building.
    const [plx1, ply1, plx2, ply2] = g.plot;
    const apron = new THREE.Mesh(
      new THREE.PlaneGeometry(this.W(plx2 - plx1) + 6, this.W(ply2 - ply1) + 6),
      this.apronMat || new THREE.MeshStandardMaterial({ color: 0x4a4c52, roughness: 0.95 }));
    apron.rotation.x = -Math.PI / 2;
    apron.position.set(this.X((plx1 + plx2) / 2), -0.03, this.Z((ply1 + ply2) / 2));
    apron.receiveShadow = true;
    this.group.add(apron);

    // ---- promenade (cobbles) with a pale stone band along the water, plot, building floors
    this.slab(g.promenade, cobble, 0.06, 0.12);
    this.slab([g.promenade[0], g.promenade[1], g.promenade[0] + 26, g.promenade[3]], stone, 0.075, 0.03);
    this.slab(g.plot, gravel, 0.04, 0.10);
    this.slab(R.garden, gravel, 0.08, 0.06);
    // a flagstone walk through the court to the dining room opening
    this.slab([R.garden[0] + 170, R.garden[1] + 8, R.garden[2] - 170, R.garden[3]], stone, 0.085, 0.02);
    this.slab([R.window[0], R.window[1], R.east[2], R.east[3]], wood, 0.10, 0.10);
    this.slab(R.private, wood, 0.10, 0.10);
    this.slab(R.terrace, terrace, 0.08, 0.10);
    this.slab(R.wc, tiles, 0.10, 0.10);
    this.slab(R.lounge, gravel, 0.09, 0.02);
    // The reference's service corridor (bar + kitchen) runs on a distinct
    // herringbone floor, not the same boards as the dining room. Painted
    // after the wood slab so it wins in that footprint - one bounding box
    // over the bar counter, the back bar and the pass, with a small margin
    // so the seam sits under the counter fronts rather than mid-aisle.
    const svcX1 = Math.min(g.bar_counter[0], g.back_bar[0], g.pass[0]) - 6;
    const svcY1 = Math.min(g.bar_counter[1], g.back_bar[1], g.pass[1]) - 6;
    const svcX2 = Math.max(g.bar_counter[2], g.back_bar[2], g.pass[2]) + 6;
    const svcY2 = Math.max(g.bar_counter[3], g.back_bar[3], g.pass[3]) + 6;
    this.slab([svcX1, svcY1, svcX2, svcY2], herringbone, 0.11, 0.03);

    // ---- walls: building perimeter with the window walls as glass
    const [bx1, by1, bx2, by2] = g.building;
    const H = 3.2;
    this.wallSegment(bx1, by1, bx2, by1, 1.1, 0.3, brick, 0.08);                 // garden front, low + planted
    this.wallSegment(bx1, by2, bx2, by2, H, 0.3, wallMat, 0.08);                 // south
    this.wallSegment(bx1, by1, bx1, R.window[1], H, 0.3, wallMat, 0.08);         // west, solid
    this.glassWall(bx1, R.window[1], bx1, R.window[3], H * 0.9, 0.1);            // west, glass along the row
    this.wallSegment(bx1, R.window[3], bx1, by2, H, 0.3, wallMat, 0.08);
    this.wallSegment(bx2, by1, bx2, R.east[1], H, 0.3, wallMat, 0.08);           // east
    this.glassWall(bx2, R.east[1], bx2, R.east[3], H * 0.9, 0.1);
    this.wallSegment(bx2, R.east[3], bx2, by2, H, 0.3, wallMat, 0.08);
    // garden court / dining divide with a wide opening
    this.wallSegment(R.garden[0], R.garden[3], R.garden[0] + 140, R.garden[3], H, 0.25, wallMat, 0.08);
    this.wallSegment(R.garden[2] - 140, R.garden[3], R.garden[2], R.garden[3], H, 0.25, wallMat, 0.08);
    // private room
    const P = R.private;
    this.wallSegment(P[0], P[1], P[2], P[1], H, 0.2, wallMat, 0.08);
    this.wallSegment(P[0], P[1], P[0], P[3], H, 0.2, wallMat, 0.08);
    this.wallSegment(P[2], P[1], P[2], P[3] - 40, H, 0.2, wallMat, 0.08);
    // wc block
    const W = g.wc;
    this.wallSegment(W[0], W[1], W[2], W[1], H, 0.2, wallMat, 0.08);
    this.wallSegment(W[0], W[1], W[0], W[3], H, 0.2, wallMat, 0.08);
    this.wallSegment(W[2], W[1], W[2], W[3], H, 0.2, wallMat, 0.08);
    this.wallSegment(W[0], W[3], W[2], W[3], H, 0.2, wallMat, 0.08);

    // ---- bar: one enlarged marble counter, folding the old back_bar strip
    // into the same footprint. They used to be two separate fixtures (a
    // 2.7 m guest-side counter and a 2.5 m service strip behind it, 0.7 m
    // apart) with a wall-mounted shelving unit standing on the back strip.
    // That shelving unit's carcass was a solid slab nearly as thick as it was
    // tall - a 3 m dark monolith with a flat roof-like top sitting in the
    // dining room. It is gone, and its footprint is now part of one
    // continuous bar: the guest edge stays exactly where it was (this.X
    // (C[0]) is unchanged, so the stools do not move), and the counter now
    // runs back to where the shelving used to stand.
    const C = [Math.min(g.bar_counter[0], g.back_bar[0]), g.bar_counter[1],
               Math.max(g.bar_counter[2], g.back_bar[2]), g.bar_counter[3]];
    this.barFootprint = C;
    this.slab(C, this.darkPanel, 1.05, 0.95);
    this.slab([C[0] - 4, C[1] - 4, C[2] + 4, C[3] + 4], marble, 1.11, 0.06);
    const K = g.pass;
    // The pass was two large dark slabs - the "two big blocks" in the middle
    // of the room. The authored kitchen run occupies this footprint now, so
    // only a steel service ledge along its front edge remains.
    this.steel = new THREE.MeshStandardMaterial({ color: 0xc9ccd2, metalness: 0.85, roughness: 0.32, envMapIntensity: 1.0 });
    // The steel ledge that used to run along the pass is gone: with the
    // authored kitchen standing here it read as a bare white plank lying on
    // the floorboards.

    this.quayEdge(g.water, g.promenade);
    return this;
  }

  // =============================================================== phase 2
  async buildDecor() {
    const g = this.venue.geometry, R = g.rooms;
    this.shoreline(g);
    this.planters(g);
    this.planterTroughs(g, R);
    this.treeRings(g.trees, g.promenade);
    this.streetLamps(g.lamps);
    this.benches();
    this.stringLights(R.terrace, 3.0);
    this.stringLights(R.garden, 3.1);
    this.entrance(g.entrance);
    this.kiosk(g.kiosk);
    this.trim(R, g);
    this.barDetails(g);
    this.passDetails(g.pass);
    this.pendants(this.barFootprint);
    this.rugsAndArt(R, g);
    this.fireBowl(R.lounge);
    this.heaters(R.terrace);
    this.hostStand(g.entrance);
    this.cornerPlants(R, g);
    this.lounge(R.lounge);
    return this;
  }

  /**
   * The promenade does not stop at the plot. Paving, kerb, bollards, lamps,
   * tree pits and benches carry on 140 m in both directions along the water,
   * with a strip of park behind them, so the restaurant sits on a real
   * waterfront rather than a 64 m island. All instanced: five draw calls.
   */
  shoreline(g) {
    const [px1, py1, px2, py2] = g.promenade;
    const w = this.W(px2 - px1);
    const cx = this.X((px1 + px2) / 2);
    const REACH = 140;
    const cobble = this.group.children.find(o => o.name === 'promenade_ext_mat');
    // These two were untinted flat greys - no map, no normal - which is what
    // made the promenade extension read as poured concrete either side of a
    // cobbled plot. Both now use the scanned sets, reusing the cached
    // materials so this stays the same number of draw calls.
    const paving = this.pavingMat || new THREE.MeshStandardMaterial({ color: 0x6f6862, roughness: 0.95 });
    const stone = this.kerbMat || new THREE.MeshStandardMaterial({ color: 0x8c8378, roughness: 0.9 });
    for (const dir of [-1, 1]) {
      const z0 = dir < 0 ? this.Z(py1) - REACH / 2 : this.Z(py2) + REACH / 2;
      const strip = new THREE.Mesh(new THREE.BoxGeometry(w, 0.12, REACH), paving);
      strip.position.set(cx, 0.0, z0); strip.receiveShadow = true;
      const band = new THREE.Mesh(new THREE.BoxGeometry(this.W(26), 0.03, REACH), stone);
      band.position.set(this.X(px1 + 13), 0.075 - 0.015, z0); band.receiveShadow = true;
      const kerb = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.14, REACH), stone);
      kerb.position.set(this.quayX + 0.06, 0.07, z0);
      const face = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.9, REACH), this.concreteMat || new THREE.MeshStandardMaterial({ color: 0x5e5a54, roughness: 0.95 }));
      face.position.set(this.quayX - 0.08, -0.45, z0);
      this.group.add(strip, band, kerb, face);
    }
    // lamps, tree pits and benches continue at the same rhythm as the plot
    const lampGeo = this.G('lpPost', () => new THREE.CylinderGeometry(0.035, 0.07, 1, 8));
    const headGeo = this.G('lpHead', () => new THREE.CylinderGeometry(0.16, 0.12, 0.34, 6, 1, true));
    const rimGeo = new THREE.CylinderGeometry(1.0, 1.05, 0.14, 20, 1, true);
    const lampT = [], headT = [], rimT = [];
    const lampX = this.X(80), treeX = this.X(150);
    for (const dir of [-1, 1]) {
      for (let k = 0; k < 11; k++) {
        const z = dir < 0 ? this.Z(py1) - 6 - k * 13 : this.Z(py2) + 6 + k * 13;
        lampT.push(z); headT.push(z);
        if (k % 2 === 0) rimT.push(z + 6);
        if (this.halos) this.halos.add(new THREE.Vector3(lampX, 3.54, z), 0xffc57a, 1.4);
      }
    }
    const m = new THREE.Matrix4();
    const posts = new THREE.InstancedMesh(lampGeo, this.iron, lampT.length);
    const heads = new THREE.InstancedMesh(headGeo, this.lampGlass, headT.length);
    const bulbs = new THREE.InstancedMesh(this.G('lpCore', () => new THREE.CylinderGeometry(0.05, 0.05, 0.16, 8)),
      new THREE.MeshStandardMaterial({ color: 0xffe2b0, emissive: 0xffc57a, emissiveIntensity: 2.4 }), headT.length);
    lampT.forEach((z, i) => {
      m.makeScale(1, 3.4, 1).setPosition(lampX, 1.7, z); posts.setMatrixAt(i, m);
      m.identity().setPosition(lampX, 3.54, z); heads.setMatrixAt(i, m); bulbs.setMatrixAt(i, m);
    });
    posts.instanceMatrix.needsUpdate = true; heads.instanceMatrix.needsUpdate = true; bulbs.instanceMatrix.needsUpdate = true;
    posts.castShadow = true;
    const rims = new THREE.InstancedMesh(rimGeo, new THREE.MeshStandardMaterial({ color: 0x9a8f80, roughness: 0.9 }), rimT.length);
    rimT.forEach((z, i) => { m.identity().setPosition(treeX, 0.13, z); rims.setMatrixAt(i, m); });
    rims.instanceMatrix.needsUpdate = true;
    this.group.add(posts, heads, bulbs, rims);
    // the trees themselves are added by FoliageSystem from extraTrees
    this.extraTrees = rimT.map(z => [treeX, z, 3.4 + ((z * 7) % 5) * 0.3]);
  }

  /** the lounge corner of the court: a low table and the duo's corner; the sofa GLB lands here later */
  lounge(box) {
    const [x1, y1, x2, y2] = box;
    const cx = this.X((x1 + x2) / 2), cz = this.Z(y1 + 40);
    const low = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.05, 24),
      new THREE.MeshStandardMaterial({ color: 0x3b2a1f, roughness: 0.45, envMapIntensity: 0.9 }));
    low.position.set(cx, 0.44, cz - 0.35); low.castShadow = true;
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.05, 0.4, 10), this.iron);
    leg.position.set(cx, 0.22, cz - 0.35);
    this.group.add(low, leg);
    this.loungeSeats = [{ position: new THREE.Vector3(cx - 0.95, 0.1, cz), rotationY: Math.PI * 0.85 },
                        { position: new THREE.Vector3(cx + 0.95, 0.1, cz), rotationY: -Math.PI * 0.85 },
                        { position: new THREE.Vector3(cx, 0.1, cz - 1.15), rotationY: Math.PI }];
    // the duo's corner: a rug, a mic stand, an amp
    const rug = new THREE.Mesh(new THREE.CircleGeometry(1.1, 28), new THREE.MeshStandardMaterial({ color: 0x5a2f2b, roughness: 1 }));
    rug.rotation.x = -Math.PI / 2; rug.position.set(this.X(x2 - 30), 0.115, this.Z(y2 - 34)); rug.receiveShadow = true;
    const mic = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 1.5, 6), this.iron);
    mic.position.set(this.X(x2 - 30), 0.85, this.Z(y2 - 34));
    const micHead = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), this.iron);
    micHead.position.set(this.X(x2 - 30), 1.62, this.Z(y2 - 34));
    const amp = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.45, 0.35), new THREE.MeshStandardMaterial({ color: 0x1a1a1c, roughness: 0.8 }));
    amp.position.set(this.X(x2 - 54), 0.33, this.Z(y2 - 20)); amp.castShadow = true;
    this.group.add(rug, mic, micHead, amp);
  }

  /** real sofas / plants / benches when the GLBs arrive; nothing waits for them */
  async buildModels() {
    const jobs = [];
    if (this.loungeSeats) jobs.push(this.assets.instance('chairSheen', this.loungeSeats, { height: 0.95, tint: 0xc9a468, roughness: 0.7 }).then(g => { if (g) this.group.add(g); }));
    if (this.plantSpots && this.plantSpots.length) {
      jobs.push(this.assets.instance('plant', this.plantSpots, { height: 1.1, castShadow: true }).then(g => { if (g) this.group.add(g); }));
    }
    // ---- interior fit-out: real furniture along the room edges, real plants,
    // real shelving on the back bar, real sconces on the walls. All instanced
    // through AssetManager so each model is one draw call however many copies
    // stand in the room, and all placed clear of the tables (the room-edge
    // offsets below sit against walls, where the table grid never reaches).
    const R2 = this.venue.geometry.rooms, G2 = this.venue.geometry;
    const put = (name, spots, height, cast) => {
      if (!spots.length) return;
      jobs.push(this.assets.instance(name, spots, { height, castShadow: cast !== false })
        .then(g => { if (g) this.group.add(g); }).catch(() => null));
    };
    const P = (x, z, yaw) => ({ position: new THREE.Vector3(x, 0.1, z), rotationY: yaw || 0 });

    // bar stools along the counter's guest side. C2[0] is unchanged by the
    // bar's enlargement (only the back edge moved, absorbing the old
    // back_bar strip), so this line still sits at the real guest edge.
    const C2 = G2.bar_counter;
    const stools = [];
    for (let mz = C2[1] + 22; mz < C2[3] - 10; mz += 34) {
      stools.push(P(this.X(C2[0]) - 0.62, this.Z(mz), Math.PI / 2));
    }
    put('barStool', stools, 0.78);

    // sideboards and shelving against the long walls: what stops a room
    // reading as an empty box with tables floating in the middle
    const sideboards = [], shelves = [];
    for (const [rn, r] of Object.entries(R2)) {
      if (['wc', 'terrace', 'garden'].includes(rn)) continue;
      const wallZ = this.Z(r[3]) - 0.45;
      for (let mx = r[0] + 70; mx < r[2] - 70; mx += 160) {
        sideboards.push(P(this.X(mx), wallZ, Math.PI));
      }
    }
    // Banquette seating along the lounge's back wall - upholstered wall
    // seating was one of the requested categories and the room previously had
    // none, just the free-standing armchairs.
    const LR = R2.lounge;
    const banquettes = [];
    const lw = this.W(LR[2] - LR[0]) - 0.3;
    const bn = Math.max(1, Math.floor(lw / 1.2));
    for (let i = 0; i < bn; i++) {
      const mx = LR[0] + (LR[2] - LR[0]) * ((i + 0.5) / bn);
      banquettes.push(P(this.X(mx), this.Z(LR[1]) + 0.30, 0));
    }
    put('banquette', banquettes, 0.46);

    // The old back_bar strip is folded into the enlarged marble counter now
    // (see build()); a shelfUnit placed against its far edge would stand
    // inside or hard against the counter, so it is no longer placed here.
    put('sideboard', sideboards, 0.85);
    put('shelfUnit', shelves, 1.8);

    // large floor plants in the room corners, alternating two species so the
    // room does not read as one plant copy-pasted
    const bigPlants1 = [], bigPlants2 = [];
    let pi = 0;
    for (const [rn, r] of Object.entries(R2)) {
      if (rn === 'wc') continue;
      for (const [mx, mz] of [[r[0] + 26, r[1] + 26], [r[2] - 26, r[1] + 26],
                              [r[0] + 26, r[3] - 26], [r[2] - 26, r[3] - 26]]) {
        (pi++ % 2 ? bigPlants1 : bigPlants2).push(P(this.X(mx), this.Z(mz), (mx * 0.7) % 6.28));
      }
    }
    put('plantPotted1', bigPlants1, 1.35, false);
    put('plantPotted2', bigPlants2, 1.15, false);


    // wall sconces at seated-eye height along the perimeter, and pendants over
    // the bar counter - the reference's warmth comes from many small sources
    const sconces = [], pendants = [];
    const [gx1, gy1, gx2, gy2] = G2.building;
    for (let mz = gy1 + 90; mz < gy2 - 60; mz += 130) {
      sconces.push({ position: new THREE.Vector3(this.X(gx1) + 0.22, 2.05, this.Z(mz)), rotationY: Math.PI / 2 });
      sconces.push({ position: new THREE.Vector3(this.X(gx2) - 0.22, 2.05, this.Z(mz)), rotationY: -Math.PI / 2 });
    }
    for (let mz = C2[1] + 26; mz < C2[3] - 16; mz += 52) {
      pendants.push({ position: new THREE.Vector3(this.X((C2[0] + C2[2]) / 2), 2.45, this.Z(mz)), rotationY: 0 });
    }
    put('wallSconce', sconces, 0.30, false);
    put('pendantLamp', pendants, 0.35, false);

    // ---- the authored kitchen run and bathroom suite, dropped into the rooms
    // the floorplan already has. Both are modelled here rather than
    // downloaded (blender/author_assets.py) and are placed once, scaled to
    // their room. The two big dark slabs that used to stand in for the pass
    // are gone, so this area now reads as a working kitchen.
    const K3 = G2.pass, Wc3 = G2.wc;
    const section = (name, rect, yaw) => {
      jobs.push(this.assets.instance(name, [{
        position: new THREE.Vector3(this.X((rect[0] + rect[2]) / 2), 0.1,
                                    this.Z((rect[1] + rect[3]) / 2)),
        rotationY: yaw || 0,
      }], { castShadow: true, face: false })
        .then(g => { if (g) this.group.add(g); }).catch(() => null));
    };
    // No bar counter stands in the pass any more. The ProVis piece went in
    // here and did not survive: 76 k triangles collapsed to 14 k tore it into
    // disconnected flat panels, so its three brown fallback materials read as
    // loose slabs with the bottles floating over them, and its pale
    // stone-iland section read as a separate white curved lump on the floor -
    // the two objects in the screenshots. The floorplan already has a real
    // bar (bar_counter/back_bar) elsewhere; this space is now planted.

    section('bathSuite', Wc3, 0);

    // ---- restroom. The wc block was an empty tiled box with four walls; it
    // is a real room on the floorplan so it gets real fixtures. Basins on a
    // vanity run along the north wall, cubicle partitions and pans along the
    // south, mirrors over the basins - all built here rather than downloaded
    // because they are simple slabs and boxes at correct human dimensions
    // (vanity 0.86, pan 0.40, mirror centred at 1.55).
    const Wc = G2.wc;
    const wcTile = this.mats && this.marble ? this.marble : this.plaster;
    const porcelain = new THREE.MeshStandardMaterial({ color: 0xf4f3f0, roughness: 0.18, metalness: 0.02 });
    const mirrorMat = new THREE.MeshStandardMaterial({ color: 0xdfe6ec, roughness: 0.05, metalness: 0.95 });
    const wcW = this.W(Wc[2] - Wc[0]);
    // vanity counter along the north wall
    this.slab([Wc[0] + 6, Wc[1] + 6, Wc[2] - 6, Wc[1] + 30], this.darkPanel, 0, 0.86);
    this.slab([Wc[0] + 4, Wc[1] + 4, Wc[2] - 4, Wc[1] + 32], wcTile, 0.86, 0.04);
    const basinN = Math.max(2, Math.floor(wcW / 0.9));
    for (let i = 0; i < basinN; i++) {
      const bx = this.X(Wc[0] + 6) + (wcW - 0.5) * ((i + 0.5) / basinN);
      const bz = this.Z(Wc[1] + 18);
      const basin = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.13, 0.11, 20), porcelain);
      basin.position.set(bx, 0.945, bz); basin.castShadow = true;
      const tap = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.18, 8), this.brass);
      tap.position.set(bx, 1.03, bz - 0.16);
      const mirror = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.62, 0.02), mirrorMat);
      mirror.position.set(bx, 1.55, this.Z(Wc[1]) + 0.12);
      this.group.add(basin, tap, mirror);
    }
    // cubicles and pans along the south wall
    const cubN = Math.max(2, Math.floor(wcW / 1.1));
    for (let i = 0; i < cubN; i++) {
      const cx2 = this.X(Wc[0] + 6) + (wcW - 0.5) * ((i + 0.5) / cubN);
      const cz2 = this.Z(Wc[3] - 32);
      const pan = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.40, 0.56), porcelain);
      pan.position.set(cx2, 0.30, cz2); pan.castShadow = true;
      const cistern = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.34, 0.14), porcelain);
      cistern.position.set(cx2, 0.67, cz2 - 0.32);
      this.group.add(pan, cistern);
      if (i < cubN - 1) {
        const part = new THREE.Mesh(new THREE.BoxGeometry(0.03, 1.9, 1.0),
          new THREE.MeshStandardMaterial({ color: 0x2c2a27, roughness: 0.6 }));
        part.position.set(cx2 + (wcW - 0.5) / cubN / 2, 0.95, cz2 - 0.1);
        this.group.add(part);
      }
    }

    // the authored umbrella, replacing the built canopy on the terrace
    if (this.umbrellaSpots && this.umbrellaSpots.length) {
      jobs.push(this.assets.instance('umbrellaReal', this.umbrellaSpots,
                                     { castShadow: true, face: false })
        .then(g => {
          if (!g) return;                       // keep the built canopies
          this.group.add(g);
          for (const m of (this.umbrellas || [])) {
            if (m.parent) m.parent.remove(m);
          }
        }).catch(() => null));
    }

    // swap the stand-in cylinders for the scanned clay planter
    if (this.potSpots && this.potSpots.length) {
      jobs.push(this.assets.instance('planterPot', this.potSpots, { height: 0.62, castShadow: true }).then(g => {
        if (!g) return;                                  // download failed: keep the cylinders
        this.group.add(g);
        for (const m of this.procPots) this.group.remove(m);
        this.procPots.length = 0;
        // the scan's rim sits lower than the cylinder's, so drop the soil to meet it
        for (const sp of this.potSpots) if (sp.soil) sp.soil.position.y = 0.44;
      }));
    }
    await Promise.all(jobs.map(p => p.catch(() => null)));
  }

  /** bollards and a chain along the water, a kerb, and a stone quay wall face */
  quayEdge(water, prom) {
    const x = this.X(water[2]) + 0.12;
    const post = this.iron;
    const n = Math.round(this.W(prom[3] - prom[1]) / 2.6);
    const geo = new THREE.CylinderGeometry(0.07, 0.09, 0.62, 10);
    const cap = new THREE.SphereGeometry(0.085, 10, 8);
    const im = new THREE.InstancedMesh(geo, post, n), ic = new THREE.InstancedMesh(cap, post, n);
    const m = new THREE.Matrix4();
    const pts = [];
    for (let i = 0; i < n; i++) {
      const z = this.Z(prom[1]) + i * 2.6 + 0.8;
      m.makeTranslation(x, 0.31 + 0.06, z); im.setMatrixAt(i, m);
      m.makeTranslation(x, 0.62 + 0.06, z); ic.setMatrixAt(i, m);
      pts.push(new THREE.Vector3(x, 0.58, z));
    }
    im.instanceMatrix.needsUpdate = true; ic.instanceMatrix.needsUpdate = true;
    im.castShadow = true;
    this.group.add(im, ic);
    // chain: one sagging line per span, one geometry, instanced by translation
    const chain = new THREE.MeshStandardMaterial({ color: 0x2a2a2e, metalness: 0.7, roughness: 0.5 });
    const a = pts[0], b = pts[1];
    if (b) {
      const mid = a.clone().lerp(b, 0.5); mid.y -= 0.16;
      const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, 0), mid.clone().sub(a), b.clone().sub(a)]);
      const tube = new THREE.TubeGeometry(curve, 8, 0.012, 5, false);
      const ich = new THREE.InstancedMesh(tube, chain, pts.length - 1);
      for (let i = 0; i < pts.length - 1; i++) { m.makeTranslation(pts[i].x, pts[i].y, pts[i].z); ich.setMatrixAt(i, m); }
      ich.instanceMatrix.needsUpdate = true;
      this.group.add(ich);
    }
    // kerb between promenade and water, and the quay wall face going down to the water
    const len = this.W(prom[3] - prom[1]);
    const kerb = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.14, len), this.kerbMat || new THREE.MeshStandardMaterial({ color: 0x8c8378, roughness: 0.9 }));
    kerb.position.set(x - 0.06, 0.07, this.Z((prom[1] + prom[3]) / 2)); kerb.receiveShadow = true;
    const face = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.9, len), this.concreteMat || new THREE.MeshStandardMaterial({ color: 0x5e5a54, roughness: 0.95 }));
    face.position.set(x - 0.2, -0.45, this.Z((prom[1] + prom[3]) / 2));
    this.group.add(kerb, face);
  }

  /** baseboards, door leaves, wall lamps: the small architectural things that stop walls reading as boxes */
  trim(R, g) {
    const base = new THREE.MeshStandardMaterial({ color: 0x3a2a1e, roughness: 0.6 });
    const boards = [
      [R.window[0], R.window[1], R.window[0], R.window[3]], [R.east[2], R.east[1], R.east[2], R.east[3]],
      [R.window[0], R.window[3], R.east[2], R.east[3]], [R.private[0], R.private[1], R.private[2], R.private[1]],
    ];
    for (const [x1, y1, x2, y2] of boards) {
      const ax = this.X(x1), az = this.Z(y1), bx = this.X(x2), bz = this.Z(y2);
      const len = Math.hypot(bx - ax, bz - az);
      const b = new THREE.Mesh(new THREE.BoxGeometry(len, 0.12, 0.05), base);
      b.position.set((ax + bx) / 2, 0.16, (az + bz) / 2); b.rotation.y = -Math.atan2(bz - az, bx - ax);
      this.group.add(b);
    }
    // doors: private room, restrooms, main entrance
    const door = new THREE.MeshStandardMaterial({ color: 0x4a3324, roughness: 0.55 });
    const doors = [[R.private[2], R.private[3] - 20, 0], [g.wc[0] + 20, g.wc[3], Math.PI / 2], [g.entrance[0], g.entrance[1] - 8, Math.PI / 2]];
    for (const [mx, my, rot] of doors) {
      const d = new THREE.Mesh(new THREE.BoxGeometry(0.06, 2.1, 0.9), door);
      d.position.set(this.X(mx), 1.15, this.Z(my)); d.rotation.y = rot; d.castShadow = true;
      const h = new THREE.Mesh(new THREE.SphereGeometry(0.03, 8, 8), this.brass);
      h.position.set(this.X(mx) + 0.05 * Math.cos(rot), 1.05, this.Z(my) + 0.32 * Math.cos(rot) + 0.05 * Math.sin(rot));
      this.group.add(d, h);
    }
    // wall lamps: warm emissive shades with a halo, no point light (the budget is spent on tables)
    const shade = new THREE.MeshStandardMaterial({ color: 0xfff1d6, emissive: 0xffc98a, emissiveIntensity: 1.6 });
    const arm = this.iron;
    const spots = [];
    for (let y = R.window[1] + 90; y < R.window[3]; y += 140) spots.push([R.window[0] + 4, y, 0]);
    for (let y = R.east[1] + 90; y < R.east[3]; y += 140) spots.push([R.east[2] - 4, y, Math.PI]);
    spots.push([R.private[0] + 40, R.private[1] + 4, Math.PI / 2], [R.private[2] - 40, R.private[1] + 4, Math.PI / 2]);
    for (let x = R.window[0] + 60; x < R.east[2]; x += 120) spots.push([x, R.east[3] - 4, -Math.PI / 2]);
    const armGeo = this.G('wlArm', () => new THREE.BoxGeometry(0.16, 0.03, 0.03));
    const shGeo = this.G('wlShade', () => new THREE.CylinderGeometry(0.09, 0.12, 0.14, 12, 1, true));
    for (const [mx, my, rot] of spots) {
      const a = new THREE.Mesh(armGeo, arm);
      a.position.set(this.X(mx), 2.1, this.Z(my)); a.rotation.y = rot;
      const sh = new THREE.Mesh(shGeo, shade);
      const px = this.X(mx) + 0.12 * Math.cos(rot), pz = this.Z(my) - 0.12 * Math.sin(rot);
      sh.position.set(px, 2.06, pz);
      this.group.add(a, sh);
      if (this.halos) this.halos.add(new THREE.Vector3(px, 2.04, pz), 0xffc98a, 0.55);
    }
  }

  /** back bar shelves with bottles, a glass rack overhead, an LED strip under the counter lip, stools with backs */
  barDetails(g) {
    // The wall-mounted shelving unit (four shelves, coloured bottles, mirror
    // strip, its own supporting carcass) is gone: the carcass was the "large
    // dark structure" - a solid slab nearly as thick as it was tall standing
    // where the back_bar strip used to be. That whole footprint is now part
    // of the enlarged marble counter built above, so the props that used to
    // sit on the wall shelves are placed directly on the counter top instead,
    // in the tasteful groupings a working bar actually has.
    const C = this.barFootprint;
    const cols = [0xb88a3c, 0x7a4a2e, 0x4c7a63, 0x9a5a52, 0xd8cfb4, 0x6a8ab2, 0xc4553f];
    const glass = cols.map(c => new THREE.MeshPhysicalMaterial({ color: c, roughness: 0.12, metalness: 0, transparent: true, opacity: 0.9, envMapIntensity: 1.3, clearcoat: 0.6 }));
    const bottleGeo = new THREE.CylinderGeometry(0.035, 0.04, 0.3, 10);
    const neckGeo = new THREE.CylinderGeometry(0.014, 0.02, 0.1, 8);

    const topY = 1.14;                       // marble top surface (1.11 + 0.06 slab, minus half-thickness rounding)
    const cx1 = this.Z(C[1]) + 0.35, cx2 = this.Z(C[3]) - 0.35;   // usable length, clear of the ends
    const midX = this.X((C[0] + C[2]) / 2);
    const guestX = this.X(C[0]) + 0.35, backX = this.X(C[2]) - 0.35;   // front (guest) and back edge, inset
    const span = cx2 - cx1;

    // ---- cluster A: bottles + wine glasses, one end of the counter
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sv = new THREE.Vector3(), p = new THREE.Vector3();
    const bottleSpots = [];
    for (let i = 0; i < 6; i++) bottleSpots.push({ z: cx1 + 0.55 + i * 0.16, k: i % cols.length });
    const byColour = cols.map(() => []);
    bottleSpots.forEach(b => byColour[b.k].push(b));
    byColour.forEach((list, k) => {
      if (!list.length) return;
      const im = new THREE.InstancedMesh(bottleGeo, glass[k], list.length);
      const iN = new THREE.InstancedMesh(neckGeo, glass[k], list.length);
      list.forEach((b, i) => {
        p.set(backX, topY + 0.15, b.z); m.compose(p, q, sv.set(1, 1, 1)); im.setMatrixAt(i, m);
        p.set(backX, topY + 0.30 + 0.05, b.z); m.compose(p, q, sv.set(1, 1, 1)); iN.setMatrixAt(i, m);
      });
      im.instanceMatrix.needsUpdate = true; iN.instanceMatrix.needsUpdate = true;
      this.group.add(im, iN);
    });
    const wineGlassSpots = [];
    for (let i = 0; i < 5; i++) wineGlassSpots.push({
      position: new THREE.Vector3(guestX, topY, cx1 + 0.5 + i * 0.18), rotationY: 0,
    });
    this.assets.instance('glassWine', wineGlassSpots, { height: 0.15, castShadow: false })
      .then(gr => { if (gr) this.group.add(gr); }).catch(() => null);

    // ---- cluster B: small plates / appetizers, middle of the counter
    const plateSpots = [
      { position: new THREE.Vector3(midX - 0.5, topY, (cx1 + cx2) / 2), rotationY: 0.4 },
      { position: new THREE.Vector3(midX - 0.2, topY, (cx1 + cx2) / 2 + 0.22), rotationY: 1.1 },
    ];
    this.assets.instance('dishOlives', plateSpots, { width: 0.22, castShadow: false })
      .then(gr => { if (gr) this.group.add(gr); }).catch(() => null);
    const waterSpots = [{ position: new THREE.Vector3(midX + 0.1, topY, (cx1 + cx2) / 2 - 0.15), rotationY: 0 }];
    this.assets.instance('glassWater', waterSpots, { height: 0.09, castShadow: false })
      .then(gr => { if (gr) this.group.add(gr); }).catch(() => null);

    // ---- cluster C: dessert / fruit, the other end
    const fruitSpots = [
      { position: new THREE.Vector3(midX + 0.6, topY, cx2 - 0.6), rotationY: 0.6 },
    ];
    this.assets.instance('foodPomegranate', fruitSpots, { height: 0.09, castShadow: false })
      .then(gr => { if (gr) this.group.add(gr); }).catch(() => null);
    this.assets.instance('foodApple',
      [{ position: new THREE.Vector3(midX + 0.72, topY, cx2 - 0.48), rotationY: 1.2 }],
      { height: 0.08, castShadow: false }).then(gr => { if (gr) this.group.add(gr); }).catch(() => null);

    // ---- cluster D: a tray with two water glasses, ready to carry
    const trayMat = new THREE.MeshStandardMaterial({ color: 0x3a352c, roughness: 0.4, metalness: 0.3 });
    const tray = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.012, 20), trayMat);
    tray.position.set(midX - 0.9, topY + 0.006, cx2 - 0.3);
    this.group.add(tray);
    this.assets.instance('glassWater', [
      { position: new THREE.Vector3(midX - 0.95, topY + 0.012, cx2 - 0.34), rotationY: 0 },
      { position: new THREE.Vector3(midX - 0.85, topY + 0.012, cx2 - 0.26), rotationY: 0 },
    ], { height: 0.09, castShadow: false }).then(gr => { if (gr) this.group.add(gr); }).catch(() => null);

    // glass rack over the counter: two rails and hanging wine glasses
    const cz1 = this.Z(C[1]) + 0.3, cz2 = this.Z(C[3]) - 0.3;
    for (const off of [-0.22, 0.22]) {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.04, cz2 - cz1), this.iron);
      rail.position.set(midX + off, 2.25, (cz1 + cz2) / 2);
      this.group.add(rail);
    }
    const glassCount = Math.floor((cz2 - cz1) / 0.16) * 2;
    const gGeo = new THREE.CylinderGeometry(0.008, 0.038, 0.11, 8, 1, true);
    const gIm = new THREE.InstancedMesh(gGeo, this.mats.glass({ color: 0xffffff, opacity: 0.35 }), glassCount);
    let gi = 0;
    for (const off of [-0.22, 0.22]) for (let z = cz1; z < cz2 && gi < glassCount; z += 0.16) { m.makeTranslation(midX + off, 2.17, z); gIm.setMatrixAt(gi++, m); }
    gIm.count = gi; gIm.instanceMatrix.needsUpdate = true;
    this.group.add(gIm);
    // a warm LED under the counter lip, the reference's bar glow
    const lip = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.02, this.W(C[3] - C[1])), new THREE.MeshStandardMaterial({ color: 0xffe0b0, emissive: 0xffb86a, emissiveIntensity: 2.4 }));
    lip.position.set(this.X(C[0]) - 0.1, 1.02, this.Z((C[1] + C[3]) / 2));
    this.group.add(lip);
    const strip = new THREE.PointLight(0xffc98a, 1.4, 6.5, 2);
    strip.position.set(midX, 1.9, (cz1 + cz2) / 2);
    this.group.add(strip);
    this.lampLights.push(strip);
    this.stools(C);
  }

  stools(C) {
    const seat = new THREE.MeshStandardMaterial({ color: 0x8a6440, roughness: 0.7 });
    const leg = this.iron;
    const x = this.X(C[0]) - 0.55;
    const seatGeo = new THREE.CylinderGeometry(0.19, 0.17, 0.08, 16), legGeo = new THREE.CylinderGeometry(0.025, 0.06, 0.78, 8);
    const ringGeo = new THREE.TorusGeometry(0.16, 0.012, 6, 20), backGeo = new THREE.TorusGeometry(0.17, 0.015, 6, 20, Math.PI);
    for (let z = this.Z(C[1]) + 0.5; z < this.Z(C[3]) - 0.3; z += 0.9) {
      const s = new THREE.Mesh(seatGeo, seat); s.position.set(x, 0.82, z); s.castShadow = true;
      const l = new THREE.Mesh(legGeo, leg); l.position.set(x, 0.42, z);
      const ring = new THREE.Mesh(ringGeo, leg); ring.position.set(x, 0.28, z); ring.rotation.x = Math.PI / 2;
      const back = new THREE.Mesh(backGeo, leg); back.position.set(x, 1.0, z); back.rotation.y = -Math.PI / 2; back.rotation.x = 0;
      this.group.add(s, l, ring, back);
    }
  }

  /** the pass: heat lamps on a rail, stacked plates, a ticket rail */
  passDetails(K) {
    const x1 = this.X(K[0]), x2 = this.X(K[2]), z1 = this.Z(K[1]), z2 = this.Z(K[3]);
    const rail = new THREE.Mesh(new THREE.BoxGeometry(x2 - x1, 0.05, 0.05), this.steel);
    rail.position.set((x1 + x2) / 2, 1.85, (z1 + z2) / 2);
    this.group.add(rail);
    const lampMat = new THREE.MeshStandardMaterial({ color: 0xffd6a0, emissive: 0xff9a3c, emissiveIntensity: 2.0 });
    for (let i = 0; i < 3; i++) {
      const x = x1 + (x2 - x1) * (i + 0.5) / 3;
      const shade = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.14, 0.18, 12, 1, true), this.steel);
      shade.position.set(x, 1.7, (z1 + z2) / 2);
      const bulb = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.02, 10), lampMat);
      bulb.position.set(x, 1.62, (z1 + z2) / 2);
      this.group.add(shade, bulb);
      if (this.halos) this.halos.add(new THREE.Vector3(x, 1.6, (z1 + z2) / 2), 0xff9a3c, 0.5);
    }
    const plates = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.12, 20), new THREE.MeshStandardMaterial({ color: 0xf4f1ea, roughness: 0.3 }));
    plates.position.set(x1 + 0.4, 1.08, z1 + 0.35);
    const plates2 = plates.clone(); plates2.position.set(x2 - 0.4, 1.08, z2 - 0.35);
    this.group.add(plates, plates2);
  }

  /** pendant lamps on a black rail above the bar counter, like the reference's lit spine */
  pendants(C) {
    const cx = this.X((C[0] + C[2]) / 2), z1 = this.Z(C[1]), z2 = this.Z(C[3]);
    const rail = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, z2 - z1 + 0.6), this.iron);
    rail.position.set(cx, 3.05, (z1 + z2) / 2);
    this.group.add(rail);
    const n = 5;
    const shade = new THREE.MeshStandardMaterial({ color: 0x1b1b1f, roughness: 0.5, metalness: 0.4, side: THREE.DoubleSide });
    const inner = new THREE.MeshStandardMaterial({ color: 0xffe6c0, emissive: 0xffc98a, emissiveIntensity: 2.0 });
    const cordGeo = this.G('cord', () => new THREE.CylinderGeometry(0.006, 0.006, 0.7, 4));
    const shadeGeo = this.G('pendant', () => new THREE.CylinderGeometry(0.06, 0.2, 0.22, 16, 1, true));
    const bulbGeo = this.G('pbulb', () => new THREE.SphereGeometry(0.035, 8, 6));
    for (let i = 0; i < n; i++) {
      const z = z1 + (z2 - z1) * (i + 0.5) / n;
      const cord = new THREE.Mesh(cordGeo, this.iron); cord.position.set(cx, 2.7, z);
      const sh = new THREE.Mesh(shadeGeo, shade); sh.position.set(cx, 2.3, z); sh.castShadow = true;
      const bulb = new THREE.Mesh(bulbGeo, inner); bulb.position.set(cx, 2.22, z);
      this.group.add(cord, sh, bulb);
      if (this.halos) this.halos.add(new THREE.Vector3(cx, 2.2, z), 0xffc98a, 0.6);
    }
    const light = new THREE.PointLight(0xffc98a, 1.2, 6, 2);
    light.position.set(cx, 2.1, (z1 + z2) / 2);
    this.group.add(light); this.lampLights.push(light);
  }

  /** rugs under the private table and in the lounge, framed art on the solid walls */
  rugsAndArt(R, g) {
    const rugMat = new THREE.MeshStandardMaterial({ color: 0x4d2f33, roughness: 1 });
    const rugMat2 = new THREE.MeshStandardMaterial({ color: 0x2f3a4f, roughness: 1 });
    const P = R.private;
    const rug = new THREE.Mesh(new THREE.BoxGeometry(this.W(P[2] - P[0]) - 1.2, 0.012, this.W(P[3] - P[1]) - 1.0), rugMat);
    rug.position.set(this.X((P[0] + P[2]) / 2), 0.106, this.Z((P[1] + P[3]) / 2)); rug.receiveShadow = true;
    const border = new THREE.Mesh(new THREE.BoxGeometry(this.W(P[2] - P[0]) - 1.0, 0.01, this.W(P[3] - P[1]) - 0.8), new THREE.MeshStandardMaterial({ color: 0xb59a5a, roughness: 1 }));
    border.position.copy(rug.position).setY(0.102);
    this.group.add(border, rug);
    const L = R.lounge;
    const lrug = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.012, 2.4), rugMat2);
    lrug.position.set(this.X((L[0] + L[2]) / 2), 0.115, this.Z(L[1] + 40) - 0.3); lrug.receiveShadow = true;
    this.group.add(lrug);
    // art: dark frames with a muted canvas, spaced along the south wall of the dining room and inside the private room
    const frame = new THREE.MeshStandardMaterial({ color: 0x2a1c12, roughness: 0.5 });
    const canvases = [0x8a6a4a, 0x4f6a72, 0x9a7a5a, 0x6a5a7a, 0xb08a5a, 0x5a6a4a];
    const spots = [];
    for (let x = R.window[0] + 70; x < R.east[2] - 60; x += 110) spots.push([x, R.east[3] - 6, 0]);
    spots.push([P[0] + 6, (P[1] + P[3]) / 2, Math.PI / 2], [P[2] - 6, P[1] + 40, -Math.PI / 2]);
    for (let y = R.window[1] + 160; y < R.window[3] - 100; y += 240) spots.push([g.building[0] + 8, y, Math.PI / 2]);
    const fGeo = this.G('frame', () => new THREE.BoxGeometry(0.9, 0.7, 0.04)), cGeo = this.G('canvas', () => new THREE.BoxGeometry(0.78, 0.58, 0.05));
    spots.forEach(([mx, my, rot], i) => {
      const f = new THREE.Mesh(fGeo, frame); f.position.set(this.X(mx), 1.7, this.Z(my)); f.rotation.y = rot;
      const c = new THREE.Mesh(cGeo, new THREE.MeshStandardMaterial({ color: canvases[i % canvases.length], roughness: 0.9 }));
      c.position.copy(f.position); c.rotation.y = rot;
      this.group.add(f, c);
    });
  }

  /** a bronze fire bowl in the lounge corner: the warmest thing in the court at night */
  fireBowl(L) {
    const x = this.X(L[0] + 40), z = this.Z(L[3] - 40);
    const bowl = new THREE.Mesh(new THREE.LatheGeometry([new THREE.Vector2(0.15, 0), new THREE.Vector2(0.2, 0.05), new THREE.Vector2(0.42, 0.28),
      new THREE.Vector2(0.45, 0.34), new THREE.Vector2(0.38, 0.34), new THREE.Vector2(0.34, 0.26), new THREE.Vector2(0, 0.24)], 24),
      new THREE.MeshStandardMaterial({ color: 0x5b3f2a, metalness: 0.6, roughness: 0.5 }));
    bowl.position.set(x, 0.1, z); bowl.castShadow = true;
    const flameMat = new THREE.MeshStandardMaterial({ color: 0xffb25a, emissive: 0xff7a1c, emissiveIntensity: 2.6, transparent: true, opacity: 0.9 });
    const flame = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.42, 10), flameMat);
    flame.position.set(x, 0.55, z);
    const light = new THREE.PointLight(0xff8a2c, 2.2, 7, 1.8);
    light.position.set(x, 0.9, z);
    this.group.add(bowl, flame, light);
    this.lampLights.push(light);
    const halo = this.halos ? this.halos.add(new THREE.Vector3(x, 0.55, z), 0xff8a2c, 1.4) : -1;
    this.flames.push({ mesh: flame, light, base: 2.2, halo, phase: 1.3 });
  }

  /** two patio heaters at the terrace edge */
  heaters(T) {
    const glow = new THREE.MeshStandardMaterial({ color: 0xffb27a, emissive: 0xff8a3c, emissiveIntensity: 2.2 });
    for (const [mx, my] of [[T[0] + 40, T[1] + 40], [T[2] - 40, T[3] - 60]]) {
      const x = this.X(mx), z = this.Z(my);
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.05, 2.2, 8), this.iron); post.position.set(x, 1.1, z); post.castShadow = true;
      const base = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.3, 0.06, 16), this.iron); base.position.set(x, 0.11, z);
      const hood = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.14, 16, 1, true), this.iron); hood.position.set(x, 2.28, z);
      const el = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.12, 0.22, 12), glow); el.position.set(x, 2.1, z);
      this.group.add(post, base, hood, el);
      if (this.halos) this.halos.add(new THREE.Vector3(x, 2.08, z), 0xff8a3c, 0.9);
    }
  }

  /** a host stand by the door with a small brass lamp */
  hostStand([mx, my]) {
    const x = this.X(mx) - 1.4, z = this.Z(my) + 1.1;
    const stand = new THREE.Mesh(new THREE.BoxGeometry(0.55, 1.1, 0.42), new THREE.MeshStandardMaterial({ color: 0x3a2618, roughness: 0.55 }));
    stand.position.set(x, 0.65, z); stand.castShadow = true;
    const top = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.04, 0.5), this.brass); top.position.set(x, 1.22, z);
    const lamp = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.09, 0.1, 10, 1, true), new THREE.MeshStandardMaterial({ color: 0xfff1d6, emissive: 0xffc98a, emissiveIntensity: 1.8 }));
    lamp.position.set(x - 0.18, 1.5, z - 0.1);
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.3, 6), this.brass); arm.position.set(x - 0.18, 1.35, z - 0.1);
    this.group.add(stand, top, lamp, arm);
    if (this.halos) this.halos.add(new THREE.Vector3(x - 0.18, 1.47, z - 0.1), 0xffc98a, 0.4);
  }

  /** potted plants at every room corner and both sides of every door; the plant GLB lands on these if present */
  cornerPlants(R, g) {
    const pot = new THREE.MeshStandardMaterial({ color: 0x3a3230, roughness: 0.7 });
    const pots = [];
    const push = (mx, my, r) => pots.push([mx, my, r || 8]);
    push(R.window[0] + 14, R.window[1] + 14); push(R.east[2] - 14, R.east[1] + 14);
    push(R.window[0] + 14, R.window[3] - 14); push(R.east[2] - 14, R.east[3] - 14);
    push(R.private[0] + 12, R.private[3] - 12); push(R.private[2] - 12, R.private[1] + 12);
    push(g.entrance[0] - 26, g.entrance[1] + 26, 10); push(g.entrance[0] + 26, g.entrance[1] + 26, 10);
    push(R.lounge[0] + 12, R.lounge[1] + 12, 9); push(R.garden[0] + 12, R.garden[1] + 40, 9);
    push(g.pass[0] - 12, g.pass[3] + 12); push(g.pass[2] + 12, g.pass[3] + 12);
    push(R.terrace[0] + 14, R.terrace[3] - 14, 10); push(R.terrace[2] - 14, R.terrace[1] + 14, 10);
    this.plantSpots = [];
    const geo = this.G('pot', () => new THREE.CylinderGeometry(0.22, 0.17, 0.42, 14));
    for (const [mx, my, r] of pots) {
      const p = new THREE.Mesh(geo, pot); p.position.set(this.X(mx), 0.31, this.Z(my)); p.castShadow = true;
      this.group.add(p);
      this.shrubSpots.push([this.X(mx), this.Z(my), 0.45, 0.05, 0.52]);
      this.plantSpots.push({ position: new THREE.Vector3(this.X(mx), 0.52, this.Z(my)), rotationY: (mx * 0.37) % 6.28 });
    }
  }

  /** stone rings and soil around every promenade tree, like the reference's tree pits */
  treeRings(trees, prom) {
    const rim = new THREE.MeshStandardMaterial({ color: 0x9a8f80, roughness: 0.9 });
    const soil = new THREE.MeshStandardMaterial({ color: 0x3a2a1c, roughness: 1 });
    const rimGeo = new THREE.CylinderGeometry(1.0, 1.05, 0.14, 24, 1, true), soilGeo = new THREE.CircleGeometry(1.0, 24);
    const list = trees.filter(([mx]) => mx < prom[2]);
    const im = new THREE.InstancedMesh(rimGeo, rim, list.length), is = new THREE.InstancedMesh(soilGeo, soil, list.length);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -Math.PI / 2), s = new THREE.Vector3(1, 1, 1);
    list.forEach(([mx, my, r], i) => {
      const k = Math.min(1.15, Math.max(0.6, r / 40));
      m.compose(new THREE.Vector3(this.X(mx), 0.13, this.Z(my)), new THREE.Quaternion(), new THREE.Vector3(k, 1, k)); im.setMatrixAt(i, m);
      m.compose(new THREE.Vector3(this.X(mx), 0.09, this.Z(my)), q, new THREE.Vector3(k, k, 1)); is.setMatrixAt(i, m);
    });
    im.instanceMatrix.needsUpdate = true; is.instanceMatrix.needsUpdate = true;
    this.group.add(im, is);
  }

  /** slatted benches facing the water, every ~10 m of promenade */
  benches() {
    const slat = new THREE.MeshStandardMaterial({ color: 0x6b4a2c, roughness: 0.7 });
    const frame = this.iron;
    const spots = [[150, 214], [150, 420], [150, 640], [150, 860], [150, 1060]];
    const slatGeo = new THREE.BoxGeometry(0.08, 0.03, 1.6), legGeo = new THREE.BoxGeometry(0.05, 0.42, 0.06);
    const slatT = [], legT = [];
    for (const [mx, my] of spots) {
      const x = this.X(mx), z = this.Z(my);
      for (let i = 0; i < 5; i++) slatT.push({ p: new THREE.Vector3(x - 0.2 + i * 0.1, 0.5, z), r: 0 });
      for (let i = 0; i < 3; i++) slatT.push({ p: new THREE.Vector3(x - 0.34 + i * 0.03, 0.72 + i * 0.1, z), r: 0.2 });
      for (const dz of [-0.7, 0.7]) legT.push({ p: new THREE.Vector3(x, 0.27, z + dz), r: 0 });
    }
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), Z = new THREE.Vector3(0, 0, 1);
    const im = new THREE.InstancedMesh(slatGeo, slat, slatT.length);
    slatT.forEach((t, i) => { q.setFromAxisAngle(Z, t.r); m.compose(t.p, q, s); im.setMatrixAt(i, m); });
    const il = new THREE.InstancedMesh(legGeo, frame, legT.length);
    legT.forEach((t, i) => { q.identity(); m.compose(t.p, q, s); il.setMatrixAt(i, m); });
    im.instanceMatrix.needsUpdate = true; il.instanceMatrix.needsUpdate = true; im.castShadow = true;
    this.group.add(im, il);
  }

  /** long planter troughs: along the promenade's inner edge, the terrace edges and the court walls */
  planterTroughs(g, R) {
    const trough = new THREE.MeshStandardMaterial({ color: 0x4a4440, roughness: 0.85 });
    const soil = new THREE.MeshStandardMaterial({ color: 0x33251a, roughness: 1 });
    const lines = [
      // [x1,y1,x2,y2, count, flowerRatio]
      [226, 330, 226, 830, 5, 0.45],
      [R.terrace[0] + 10, R.terrace[3] - 8, R.terrace[2] - 10, R.terrace[3] - 8, 6, 0.5],
      [R.terrace[0] + 8, R.terrace[1] + 60, R.terrace[0] + 8, R.terrace[3] - 60, 3, 0.35],
      [R.terrace[2] - 8, R.terrace[1] + 60, R.terrace[2] - 8, R.terrace[3] - 60, 3, 0.35],
      [R.garden[0] + 10, R.garden[3] - 12, R.garden[0] + 130, R.garden[3] - 12, 2, 0.3],
      [R.garden[2] - 130, R.garden[3] - 12, R.garden[2] - 10, R.garden[3] - 12, 2, 0.3],
    ];
    const tGeo = this.G('trough', () => new THREE.BoxGeometry(1.4, 0.42, 0.42)), sGeo = this.G('troughSoil', () => new THREE.BoxGeometry(1.3, 0.04, 0.34));
    const items = [];
    for (const [x1, y1, x2, y2, n, fl] of lines) {
      const along = Math.abs(x2 - x1) > Math.abs(y2 - y1);
      for (let i = 0; i < n; i++) {
        const t = (i + 0.5) / n;
        const mx = x1 + (x2 - x1) * t, my = y1 + (y2 - y1) * t;
        items.push({ x: this.X(mx), z: this.Z(my), rot: along ? 0 : Math.PI / 2, fl });
      }
    }
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), Y = new THREE.Vector3(0, 1, 0), p = new THREE.Vector3();
    const im = new THREE.InstancedMesh(tGeo, trough, items.length), is = new THREE.InstancedMesh(sGeo, soil, items.length);
    items.forEach((it, i) => {
      q.setFromAxisAngle(Y, it.rot);
      m.compose(p.set(it.x, 0.29, it.z), q, s); im.setMatrixAt(i, m);
      m.compose(p.set(it.x, 0.5, it.z), q, s); is.setMatrixAt(i, m);
      // three shrub clumps per trough
      for (let k = -1; k <= 1; k++) {
        const ox = it.rot === 0 ? k * 0.45 : 0, oz = it.rot === 0 ? 0 : k * 0.45;
        this.shrubSpots.push([it.x + ox, it.z + oz, 0.34, it.fl, 0.5]);
      }
    });
    im.instanceMatrix.needsUpdate = true; is.instanceMatrix.needsUpdate = true; im.castShadow = true;
    this.group.add(im, is);
  }

  planters(g) {
    const pot = new THREE.MeshStandardMaterial({ color: 0x9a8468, roughness: 0.8 });
    const soil = new THREE.MeshStandardMaterial({ color: 0x3a2a1c, roughness: 1 });
    const spots = [[268, 316, 11], [268, 836, 11], [676, 316, 10], [676, 836, 10], [128, 292, 13],
                   [128, 660, 13], [128, 1010, 13], [272, 1024, 12], [668, 1024, 12], [272, 1226, 11],
                   [668, 1226, 11], [470, 1010, 10], [204, 300, 10], [204, 760, 10], [300, 108, 10],
                   [660, 108, 10]];
    // The pots themselves are a real scanned clay planter, instanced in
    // buildModels() once the GLB is down. What is built here is only the soil
    // disc and the fallback body, kept so a failed download still leaves
    // something for the shrubs to grow out of rather than floating foliage.
    this.potSpots = [];
    this.procPots = [];
    for (const [mx, my, r] of spots) {
      const R = this.W(r) * 0.9;
      const p = new THREE.Mesh(new THREE.CylinderGeometry(R, R * 0.8, 0.5, 18), pot);
      p.position.set(this.X(mx), 0.33, this.Z(my)); p.castShadow = true; p.receiveShadow = true;
      const s = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.92, R * 0.92, 0.04, 18), soil);
      s.position.set(this.X(mx), 0.56, this.Z(my));
      this.group.add(p, s);
      this.procPots.push(p);
      // the real pot is squatter than the cylinder, so the soil and the shrubs
      // drop with it; 1.55 x radius because the scan tapers hard at the foot
      this.potSpots.push({ position: new THREE.Vector3(this.X(mx), 0.09, this.Z(my)),
                           scale: R / 0.5,                 // multiplier, nominal pot is 0.5 m across
                           rotationY: (mx * 0.7 + my * 0.3) % 6.283, soil: s });
      this.shrubSpots.push([this.X(mx), this.Z(my), R * 1.15, 0.35, 0.58]);
    }
    // the flower wall along the east, the vine wall over the garden front, vines on the court's inner wall
    const hedge = (x1, y1, x2, y2, flower, r, spacing) => {
      const n = Math.round(Math.hypot(x2 - x1, y2 - y1) / (spacing || 22));
      for (let i = 0; i <= n; i++) {
        const t = i / n;
        this.shrubSpots.push([this.X(x1 + (x2 - x1) * t), this.Z(y1 + (y2 - y1) * t), r || 0.75, flower]);
      }
    };
    // The Flower Wall room's namesake wall (east, x=694): the reference's
    // waterfront brief called for "particularly rich floral borders" here.
    // Was one row at 1.1 m spacing and 50% flower ratio; now two staggered
    // rows at 0.7 m spacing (offset front/back) and every plant flowering,
    // which is what turns a hedge into a wall of flowers.
    hedge(694, 300, 694, 860, 0.85, 0.55, 14);
    hedge(689, 306, 689, 854, 0.85, 0.42, 14);
    hedge(256, 88, 682, 88, 0.3);
    hedge(262, 292, 392, 292, 0.25, 0.5);
    hedge(548, 292, 676, 292, 0.25, 0.5);
    hedge(240, 1000, 240, 1238, 0.2, 0.55);
  }

  /** classic lamp posts with a glass lantern head and a warm halo; the outdoor ones carry a point light */
  streetLamps(lamps) {
    const post = this.iron;
    const bulb = new THREE.MeshStandardMaterial({ color: 0xffe2b0, emissive: 0xffc57a, emissiveIntensity: 2.4 });
    const postGeo = this.G('lpPost', () => new THREE.CylinderGeometry(0.035, 0.07, 1, 8));
    const baseGeo = this.G('lpBase', () => new THREE.CylinderGeometry(0.12, 0.16, 0.3, 10));
    const headGeo = this.G('lpHead', () => new THREE.CylinderGeometry(0.16, 0.12, 0.34, 6, 1, true));
    const capGeo = this.G('lpCap', () => new THREE.ConeGeometry(0.2, 0.16, 6));
    const coreGeo = this.G('lpCore', () => new THREE.CylinderGeometry(0.05, 0.05, 0.16, 8));
    for (const [mx, my, outdoor] of lamps) {
      // Indoor entries (outdoor: false in venue/floor.json) built a 2.6 m
      // street-lamp post standing among the dining tables - the pole running
      // through a table in the reference screenshot. Tables already have
      // their own hurricane lamps from TableManager; a free-standing post
      // was never needed indoors, only on the promenade and terrace. Only
      // outdoor entries are built now.
      if (!outdoor) continue;
      const x = this.X(mx), z = this.Z(my);
      const h = 3.4;
      const p = new THREE.Mesh(postGeo, post); p.scale.y = h; p.position.set(x, h / 2, z); p.castShadow = true;
      const b = new THREE.Mesh(baseGeo, post); b.position.set(x, 0.21, z);
      const head = new THREE.Mesh(headGeo, this.lampGlass); head.position.set(x, h + 0.14, z);
      const cap = new THREE.Mesh(capGeo, post); cap.position.set(x, h + 0.38, z);
      const core = new THREE.Mesh(coreGeo, bulb); core.position.set(x, h + 0.14, z);
      this.group.add(p, b, head, cap, core);
      const halo = this.halos ? this.halos.add(new THREE.Vector3(x, h + 0.14, z), 0xffc57a, outdoor ? 1.5 : 1.0) : -1;
      if (outdoor) {
        const light = new THREE.PointLight(0xffc98a, 3.2, 11, 1.8);
        light.position.set(x, h - 0.05, z);
        light.visible = false;
        this.group.add(light);
        this.lampLights.push(light);
        this.emissives.push({ mat: bulb, light, base: light.intensity, phase: Math.random() * 6.28, halo });
      }
    }
  }

  stringLights(box, y) {
    const [x1, y1, x2, y2] = box;
    const bulbGeo = new THREE.SphereGeometry(0.04, 6, 6);
    const bulbMat = new THREE.MeshStandardMaterial({ color: 0xfff0cc, emissive: 0xffd08a, emissiveIntensity: 3.0 });
    const wire = new THREE.MeshStandardMaterial({ color: 0x141414, roughness: 0.8 });
    const rows = 2;
    const count = 34;
    const total = rows * count;
    const im = new THREE.InstancedMesh(bulbGeo, bulbMat, total);
    const m = new THREE.Matrix4();
    let i = 0;
    for (let r = 0; r < rows; r++) {
      const zz = y1 + (y2 - y1) * (0.3 + 0.4 * r);
      const pts = [];
      for (let k = 0; k < count; k++) {
        const t = k / (count - 1);
        const sag = Math.sin(t * Math.PI) * 0.35;
        const px = this.X(x1 + (x2 - x1) * t), py = y - sag, pz = this.Z(zz);
        m.makeTranslation(px, py, pz);
        im.setMatrixAt(i++, m);
        pts.push(new THREE.Vector3(px, py + 0.04, pz));
        if (this.halos && k % 2 === 0) this.stringHalos.push(this.halos.add(new THREE.Vector3(px, py, pz), 0xffd08a, 0.22));
      }
      // the wire itself
      const curve = new THREE.CatmullRomCurve3(pts);
      this.group.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.006, 4, false), wire));
      // and its two posts
      for (const px of [pts[0].x, pts[pts.length - 1].x]) {
        const post = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.04, y, 8), this.iron);
        post.position.set(px, y / 2, this.Z(zz)); post.castShadow = true;
        this.group.add(post);
      }
    }
    im.instanceMatrix.needsUpdate = true;
    this.group.add(im);
    // one warm area light per row instead of 34 point lights
    for (let r = 0; r < rows; r++) {
      const l = new THREE.PointLight(0xffc98a, 1.6, 14, 1.6);
      l.position.set(this.X((x1 + x2) / 2), y - 0.2, this.Z(y1 + (y2 - y1) * (0.3 + 0.4 * r)));
      l.visible = false;
      this.group.add(l);
      this.lampLights.push(l);
    }
    this.stringLightMats.push(bulbMat);
  }

  /** the entrance: mat, steps, flanking lanterns and the lit SUFRA sign */
  entrance([mx, my]) {
    const mat = new THREE.MeshStandardMaterial({ color: 0x5a3a34, roughness: 0.95 });
    const m = new THREE.Mesh(new THREE.BoxGeometry(2.2, 0.02, 1.4), mat);
    m.position.set(this.X(mx), 0.1, this.Z(my) - 0.2); m.receiveShadow = true;
    const step = new THREE.MeshStandardMaterial({ color: 0xa79c8a, roughness: 0.8 });
    for (let i = 0; i < 4; i++) {
      const s = new THREE.Mesh(new THREE.BoxGeometry(3, 0.12, 0.4), step);
      s.position.set(this.X(mx), 0.06 - i * 0.02, this.Z(my) + 0.8 + i * 0.4); s.receiveShadow = true;
      this.group.add(s);
    }
    // the sign: a dark board with the brand lit in gold
    const tex = this.brandTexture();
    const signMat = new THREE.MeshStandardMaterial({ color: 0x14120f, roughness: 0.5, metalness: 0.4,
      map: tex || null, emissiveMap: tex || null, emissive: tex ? 0xffffff : 0xe2c07c, emissiveIntensity: tex ? 0.9 : 0.5 });
    const sign = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.9, 0.06), signMat);
    sign.position.set(this.X(mx) - 2.3, 1.5, this.Z(my) + 0.4);
    const postGeo = new THREE.BoxGeometry(0.06, 1.1, 0.06);
    const p1 = new THREE.Mesh(postGeo, this.iron); p1.position.set(this.X(mx) - 3.1, 0.55, this.Z(my) + 0.4);
    const p2 = new THREE.Mesh(postGeo, this.iron); p2.position.set(this.X(mx) - 1.5, 0.55, this.Z(my) + 0.4);
    const glow = new THREE.PointLight(0xffd8a0, 1.4, 4, 2);
    glow.position.set(this.X(mx) - 2.3, 1.5, this.Z(my) + 1.0);
    this.group.add(m, sign, p1, p2, glow);
    this.lampLights.push(glow);
    if (this.halos) this.halos.add(new THREE.Vector3(this.X(mx) - 2.3, 1.5, this.Z(my) + 0.5), 0xe2c07c, 1.2);
    // flanking lanterns on the door posts
    const lanternMat = new THREE.MeshStandardMaterial({ color: 0xfff1d6, emissive: 0xffc98a, emissiveIntensity: 1.8 });
    for (const dz of [-0.8, 0.8]) {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.22, 0.14), lanternMat);
      l.position.set(this.X(mx) + 0.1, 2.2, this.Z(my) - 8 * this.u + dz);
      const cap = new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.1, 4), this.iron); cap.position.copy(l.position).setY(2.36);
      this.group.add(l, cap);
      if (this.halos) this.halos.add(l.position.clone(), 0xffc98a, 0.6);
    }
  }

  /** the brand, drawn once into a small canvas texture */
  brandTexture() {
    const c = document.createElement('canvas'); c.width = 512; c.height = 256;
    const ctx = c.getContext && c.getContext('2d');
    if (!ctx) return null;
    ctx.fillStyle = '#100e0b'; ctx.fillRect(0, 0, 512, 256);
    ctx.strokeStyle = '#c9a25c'; ctx.lineWidth = 3; ctx.strokeRect(14, 14, 484, 228);
    ctx.fillStyle = '#e8c88a';
    ctx.font = '500 96px "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('S U F R A', 256, 118);
    ctx.font = '400 26px -apple-system, "Helvetica Neue", Arial, sans-serif';
    ctx.fillStyle = '#b89a66';
    ctx.fillText('W A T E R F R O N T', 256, 196);
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  kiosk(box) {
    if (!box) return;
    const [x1, y1, x2, y2] = box;
    const body = new THREE.Mesh(new THREE.BoxGeometry(this.W(x2 - x1), 2.0, this.W(y2 - y1)),
      new THREE.MeshStandardMaterial({ color: 0x6a5240, roughness: 0.8 }));
    body.position.set(this.X((x1 + x2) / 2), 1.0, this.Z((y1 + y2) / 2)); body.castShadow = true;
    const red = new THREE.MeshStandardMaterial({ color: 0xc8463e, roughness: 0.85 });
    const white = new THREE.MeshStandardMaterial({ color: 0xf0ece2, roughness: 0.85 });
    for (let i = 0; i < 6; i++) {
      const s = new THREE.Mesh(new THREE.BoxGeometry(this.W(x2 - x1) / 6, 0.04, this.W(y2 - y1) + 0.5), i % 2 ? white : red);
      s.position.set(this.X(x1) + this.W(x2 - x1) * (i + 0.5) / 6, 2.05, this.Z((y1 + y2) / 2));
      this.group.add(s);
    }
    // a hatch with a warm light
    const hatch = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.8, this.W(y2 - y1) - 0.5), new THREE.MeshStandardMaterial({ color: 0xffe0b0, emissive: 0xffb86a, emissiveIntensity: 1.2 }));
    hatch.position.set(this.X(x2) + 0.02, 1.3, this.Z((y1 + y2) / 2));
    this.group.add(body, hatch);
    if (this.halos) this.halos.add(hatch.position.clone().add(new THREE.Vector3(0.2, 0, 0)), 0xffb86a, 0.9);
  }

  umbrella(x, z, r) {
    // The authored market umbrella (blender/author_assets.py) replaces the
    // lathe-and-ribs version built below. Spots are collected here and
    // instanced once in buildModels(); the built umbrella still runs as the
    // fallback and is removed the moment the GLB lands.
    (this.umbrellaSpots = this.umbrellaSpots || []).push({
      position: new THREE.Vector3(x, 0.1, z),
      rotationY: (x * 1.3 + z * 0.7) % 6.283,
      // Modelled at 1.5 m radius (3 m across, a real market umbrella). The
      // caller passes the table's own radius, which on a 3 m terrace table
      // gave a 6 m canopy filling the sky, so clamp to a believable spread.
      scale: Math.min(1.15, Math.max(0.85, r / 1.5)),
    });
    (this.procUmbrellas = this.procUmbrellas || []).push(this.group.children.length);

    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.035, 2.6, 10),
      new THREE.MeshStandardMaterial({ color: 0x8a7550, roughness: 0.6 }));
    pole.position.set(x, 1.3, z); pole.castShadow = true;
    // Canopy: a lathe dome, but with the hem flared and dropped so it reads as
    // fabric on ribs rather than the flat white disc it used to be. An earlier
    // attempt built the twelve panels as a custom BufferGeometry and rendered
    // a bare skeleton with no fabric at all - the lathe is correct and cheaper.
    const pts = [];
    for (let i = 0; i <= 12; i++) {
      const t = i / 12;
      // taut near the pole, sagging through the middle, flicking up at the hem
      const y = 0.46 * (1 - t * t) - 0.10 * Math.pow(t, 3) + (t > 0.93 ? 0.035 : 0);
      pts.push(new THREE.Vector2(t * r, y));
    }
    const canopy = new THREE.Mesh(new THREE.LatheGeometry(pts, 24),
      this._canopyMat || (this._canopyMat = new THREE.MeshStandardMaterial({
        color: 0xeee6d4, roughness: 0.92, side: THREE.DoubleSide,
        emissive: 0x4a422f, emissiveIntensity: 0.16 })));
    canopy.position.set(x, 2.55, z); canopy.castShadow = true;
    // twelve ribs in one draw call
    const ribMat = this._ribMat || (this._ribMat = new THREE.MeshStandardMaterial({ color: 0x6b5a40 }));
    const ribs = new THREE.InstancedMesh(new THREE.BoxGeometry(r, 0.015, 0.015), ribMat, 12);
    const rm = new THREE.Matrix4(), rq = new THREE.Quaternion(), re = new THREE.Euler(), rs = new THREE.Vector3(1, 1, 1);
    for (let i = 0; i < 12; i++) {
      re.set(0, -i / 12 * 6.283, 0.28, 'YXZ'); rq.setFromEuler(re);
      rm.compose(new THREE.Vector3(x + Math.cos(i / 12 * 6.283) * r / 2, 2.6, z + Math.sin(i / 12 * 6.283) * r / 2), rq, rs);
      ribs.setMatrixAt(i, rm);
    }
    ribs.instanceMatrix.needsUpdate = true;
    const finial = new THREE.Mesh(new THREE.SphereGeometry(0.05, 8, 8), this.brass || ribMat);
    finial.position.set(x, 2.98, z);
    this.group.add(pole, canopy, ribs, finial);
    this.umbrellas.push(canopy);
  }

  update(dt, t) {
    // lamps flicker almost imperceptibly
    for (const e of this.emissives) {
      const f = 0.94 + 0.06 * Math.sin(t * 6.1 + e.phase) * Math.sin(t * 1.3 + e.phase);
      e.light.intensity = e.base * f;
    }
    const sl = 2.7 + 0.3 * Math.sin(t * 2.2);
    for (const m of this.stringLightMats) m.emissiveIntensity = sl;
    for (const f of this.flames) {
      const k = 1 + 0.25 * Math.sin(t * 9.1 + f.phase) * Math.sin(t * 3.7) + 0.1 * Math.sin(t * 17.3);
      f.mesh.scale.set(1 + 0.12 * Math.sin(t * 7.3), k, 1 + 0.12 * Math.cos(t * 6.1));
      f.light.intensity = f.base * (0.85 + 0.15 * k);
      if (this.halos) this.halos.setSize(f.halo, 1.3 + 0.25 * k);
    }
  }
}
