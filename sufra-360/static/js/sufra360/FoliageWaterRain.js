import * as THREE from '/static/vendor/three/three.module.js';

// ------------------------------------------------------------------ foliage
/**
 * Trees and shrubs. Trunks are lathe-turned tapered profiles with a bark
 * normal map and branches along curves; the canopy is thousands of alpha-
 * tested leaf cards in ONE InstancedMesh, moved by a wind vertex shader.
 * Each card carries its own phase and height factor, so every tree, every
 * branch height and every leaf moves differently. Upper leaves move more.
 */
export class FoliageSystem {
  constructor(scene, assets, share, opts) {
    this.scene = scene;
    this.assets = assets;
    this.share = share == null ? 1 : share;
    this.opts = opts || {};
    this.wind = { strength: 0.35, dirX: 1, dirZ: 0.2 };
    this.uniforms = { uTime: { value: 0 }, uWind: { value: new THREE.Vector3(1, 0, 0.2) },
                      uStrength: { value: 0.35 } };
    this.wet = 0;
  }

  async build(trees, shrubs, y) {
    // Real tree models take priority. Drop GLBs into static/3d/models/trees/ and list
    // them in manifest.json; every material that looks like foliage gets the wind
    // shader, trunks and bark stay still. Without a manifest, the leaf-card canopy below.
    const real = await this.buildRealTrees(trees, y);
    if (real) trees = [];                     // no card canopies where real trees stand
    const leafTex = await this.assets.texture('textures/leaf_card.png', true);
    const flowerTex = await this.assets.texture('textures/flower_card.png', true);
    const barkMat = await this.barkMaterial();

    const trunkGroup = new THREE.Group();
    const cards = [];         // {pos, rot, scale, phase, hf, tint}
    const flowers = [];

    for (let i = 0; i < trees.length; i++) {
      const [x, z, r] = trees[i];
      const height = r * 1.9;
      trunkGroup.add(this.trunk(x, y, z, r * 0.16, height, barkMat, i));
      const n = Math.round((80 + r * 32) * this.share);
      for (let k = 0; k < n; k++) {
        // ellipsoid canopy, denser toward the outside so the silhouette reads
        const u = Math.random(), v = Math.random(), w = Math.pow(Math.random(), 0.45);
        const th = u * Math.PI * 2, ph = Math.acos(2 * v - 1);
        const cx = Math.sin(ph) * Math.cos(th) * r * 0.95 * w;
        const cy = Math.cos(ph) * r * 0.7 * w;
        const cz = Math.sin(ph) * Math.sin(th) * r * 0.95 * w;
        const hf = 0.35 + 0.65 * ((cy + r * 0.7) / (r * 1.4));    // top moves most
        cards.push({
          pos: new THREE.Vector3(x + cx, y + height * 0.78 + cy, z + cz),
          rot: new THREE.Euler(Math.random() * 0.9 - 0.45, Math.random() * Math.PI * 2, Math.random() * 0.9 - 0.45),
          scale: r * (0.34 + Math.random() * 0.22),
          phase: i * 1.7 + Math.random() * 6.28, hf,
          tint: new THREE.Color().setHSL(0.26 + Math.random() * 0.06, 0.45 + Math.random() * 0.25, 0.28 + Math.random() * 0.16),
        });
      }
    }

    for (const [x, z, r, flowerRatio, base] of shrubs) {
      const n = Math.round((14 + r * 22) * this.share);
      const y0 = base == null ? y + 0.15 : base;              // planters and troughs lift their shrubs
      for (let k = 0; k < n; k++) {
        const a = Math.random() * Math.PI * 2, d = Math.random() * r * 0.8;
        const h = Math.random() * r * 0.6;
        cards.push({
          pos: new THREE.Vector3(x + Math.cos(a) * d, y0 + h, z + Math.sin(a) * d),
          rot: new THREE.Euler(Math.random() * 0.6 - 0.3, Math.random() * 6.28, Math.random() * 0.6 - 0.3),
          scale: r * (0.28 + Math.random() * 0.16), phase: Math.random() * 6.28, hf: 0.4 + h / (r * 0.6) * 0.4,
          // brighter and more varied than before: the old range topped out at
          // 45% lightness, which under overcast light read as dark blobs
          tint: new THREE.Color().setHSL(0.24 + Math.random() * 0.09, 0.5 + Math.random() * 0.2, 0.38 + Math.random() * 0.2),
        });
        if (Math.random() < (flowerRatio || 0)) {
          flowers.push({ pos: new THREE.Vector3(x + Math.cos(a) * d, y0 + 0.1 + h, z + Math.sin(a) * d),
                         rot: new THREE.Euler(-0.3, Math.random() * 6.28, 0), scale: r * 0.22,
                         phase: Math.random() * 6.28, hf: 0.9 });
        }
      }
    }

    this.leaves = this.cardMesh(cards, leafTex, 0.86, true);
    // thousands of alpha-tested cards in the shadow pass is the single heaviest thing a tree can do
    this.leaves.castShadow = this.opts.leafShadows !== false;
    this.scene.add(trunkGroup, this.leaves);
    if (flowers.length) {
      this.flowers = this.cardMesh(flowers, flowerTex, 0.7, false);
      this.scene.add(this.flowers);
    }
    this.leafMat = this.leaves.material;
    this.dryLeaf = this.leafMat.color.clone();
    return this;
  }

  async buildRealTrees(trees, y) {
    let manifest;
    try {
      const r = await fetch('/static/3d/models/trees/manifest.json', { cache: 'no-store' });
      if (!r.ok) return false;
      manifest = await r.json();
    } catch (e) { return false; }
    const species = (manifest.trees || []).filter(t => t.file);
    if (!species.length) return false;
    const group = new THREE.Group(); group.name = 'real-trees';
    const loader = this.assets.gltf;
    const loaded = [];
    for (const sp of species) {
      try {
        const g = await loader.loadAsync('/static/3d/models/trees/' + sp.file);
        const root = g.scene; root.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(root); const size = new THREE.Vector3(); box.getSize(size);
        const meshes = [];
        root.traverse(o => {
          if (!o.isMesh) return;
          o.castShadow = true; o.receiveShadow = true;
          const m = o.material;
          const name = ((m && m.name) || o.name || '').toLowerCase();
          const leafy = /leaf|leaves|foliage|needle|canopy|frond|branch_small/.test(name) || (m && (m.alphaTest > 0 || m.transparent));
          if (leafy && m) {
            m.side = THREE.DoubleSide; if (m.alphaTest === 0) m.alphaTest = 0.4;
            this.injectWindHierarchical(m, size.y);
          }
          meshes.push(o);
        });
        loaded.push({ sp, root, meshes, box, size });
      } catch (e) { this.assets.log.warn('[trees] ' + sp.file + ' failed: ' + e.message); }
    }
    if (!loaded.length) return false;
    // one InstancedMesh per sub-mesh per species; trees cycle through species with size variation
    trees.forEach((t, i) => t._species = loaded[i % loaded.length]);
    for (const L of loaded) {
      const mine = trees.filter(t => t._species === L);
      if (!mine.length) continue;
      const targetH = L.sp.height || 7;
      for (const mesh of L.meshes) {
        const im = new THREE.InstancedMesh(mesh.geometry, mesh.material, mine.length);
        im.castShadow = true; im.receiveShadow = true;
        const q = new THREE.Quaternion(), sv = new THREE.Vector3(), m4 = new THREE.Matrix4(), tmp = new THREE.Matrix4();
        mine.forEach((t, k) => {
          const [x, z, r] = t;
          const sc = (targetH / L.size.y) * (0.85 + (r / 2.2) * 0.3);
          q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), (x * 13.7 + z * 3.1) % 6.28);
          sv.setScalar(sc);
          m4.compose(new THREE.Vector3(x, y - L.box.min.y * sc, z), q, sv);
          tmp.copy(m4).multiply(mesh.matrixWorld);
          im.setMatrixAt(k, tmp);
        });
        im.instanceMatrix.needsUpdate = true;
        group.add(im);
      }
    }
    this.scene.add(group);
    this.realTrees = group;
    return true;
  }

  /**
   * Parkland between the plot and the city.
   *
   * The land plane runs 320 m inland and 640 m along the shore, and until now
   * every metre of it past the promenade was one flat tinted quad - the large
   * sand-coloured mass in the overview captures. This scatters the low-detail
   * tree models across it so the ground reads as parkland with clearings
   * rather than as a slab.
   *
   * The models are the *_lod variants: welded and collapsed to 2-3 k triangles
   * from 52-60 k. Nothing here is closer than 55 m and the sun's shadow camera
   * only spans 38 m, so these trees neither cast nor receive shadows; the
   * budget goes entirely into silhouette count.
   *
   * Placement is a jittered grid gated by a clump field, so the park has
   * copses and open ground instead of an even lattice, and it is seeded from
   * the grid index rather than Math.random so the same park comes back on
   * every reload - otherwise no two captures would be comparable.
   */
  async buildParkland(quayX, centreZ, y, groundY) {
    let manifest;
    try {
      const r = await fetch('/static/3d/models/trees/manifest.json', { cache: 'no-store' });
      if (!r.ok) return false;
      manifest = await r.json();
    } catch (e) { return false; }
    const species = (manifest.trees || []).filter(t => t.lod);
    if (!species.length) return false;

    const R_IN = 58;     // clear of the plot, the terrace and the promenade trees
    const R_OUT = 244;   // BakuContext keeps the city out to 260; stop short of it
    // 21 m pitch put 59 trees on 88,000 m2 - a scattering, not a park. 13 m
    // with the acceptance below gives copses at a believable 13-26 m spacing.
    const STEP = 13;     // grid pitch before jitter
    const spots = [];
    const rnd = (i, k) => {              // deterministic, cell-indexed
      const n = Math.sin(i * 127.1 + k * 311.7) * 43758.5453;
      return n - Math.floor(n);
    };
    const n = Math.ceil(R_OUT / STEP);
    let cell = 0;
    for (let gi = -n; gi <= n; gi++) {
      for (let gj = -n; gj <= n; gj++) {
        cell++;
        const jx = (rnd(cell, 1) - 0.5) * STEP * 0.85;
        const jz = (rnd(cell, 2) - 0.5) * STEP * 0.85;
        const x = quayX + gi * STEP + jx, z = centreZ + gj * STEP + jz;
        const dx = x - quayX, dz = z - centreZ;
        const r = Math.hypot(dx, dz);
        if (r < R_IN || r > R_OUT) continue;
        if (dx < 0) continue;                                    // that side is water
        // the promenade paving carries 140 m up and down the shore; no trees on it
        if (dx < 12 && Math.abs(dz) < 150) continue;
        // copses: a low-frequency field opens clearings and thickens groves
        const clump = Math.sin(x * 0.021 + 1.3) * Math.sin(z * 0.017 - 0.7)
                    + 0.6 * Math.sin((x + z) * 0.041);
        // and thin out toward the city so the park fades rather than ending
        const fade = 1 - Math.max(0, (r - 170) / (R_OUT - 170)) * 0.55;
        if (rnd(cell, 3) > (0.52 + 0.40 * clump) * fade) continue;
        spots.push([x, z, r, cell]);
      }
    }
    if (!spots.length) return false;

    const group = new THREE.Group(); group.name = 'parkland';
    const loader = this.assets.gltf;
    let placed = 0;
    for (let si = 0; si < species.length; si++) {
      const sp = species[si];
      const mine = spots.filter((_, k) => k % species.length === si);
      if (!mine.length) continue;
      let g;
      try { g = await loader.loadAsync('/static/3d/models/trees/' + sp.lod); }
      catch (e) { this.assets.log.warn('[parkland] ' + sp.lod + ' failed: ' + e.message); continue; }
      const root = g.scene; root.updateMatrixWorld(true);
      const size = new THREE.Vector3(), box = new THREE.Box3().setFromObject(root);
      box.getSize(size);
      const meshes = [];
      root.traverse(o => {
        if (!o.isMesh) return;
        o.castShadow = false; o.receiveShadow = false;
        const m = o.material;
        const name = ((m && m.name) || o.name || '').toLowerCase();
        if (m && (/leaf|leaves|foliage|needle|canopy|frond/.test(name) || m.alphaTest > 0 || m.transparent)) {
          m.side = THREE.DoubleSide;
          if (m.alphaTest === 0) m.alphaTest = 0.4;
          this.injectWindHierarchical(m, size.y);
        }
        meshes.push(o);
      });
      const targetH = sp.height || 7;
      for (const mesh of meshes) {
        const im = new THREE.InstancedMesh(mesh.geometry, mesh.material, mine.length);
        im.castShadow = false; im.receiveShadow = false;
        // the trunk, branch and leaf meshes of one species all carry the same
        // per-tree transforms; tools/probe_park.py needs this to avoid
        // reporting each tree once per sub-mesh
        im.userData.species = sp.lod;
        const q = new THREE.Quaternion(), sv = new THREE.Vector3();
        const m4 = new THREE.Matrix4(), tmp = new THREE.Matrix4();
        const up = new THREE.Vector3(0, 1, 0);
        mine.forEach(([x, z, r, cell], k) => {
          // 0.72x to 1.30x: a park of identical trees reads as wallpaper
          const sc = (targetH / size.y) * (0.72 + rnd(cell, 4) * 0.58);
          q.setFromAxisAngle(up, rnd(cell, 5) * 6.2831);
          sv.setScalar(sc);
          // sit on the land's relief, not on a nominal plane: the ground the
          // scatter covers is no longer flat (RestaurantBuilder.groundY)
          const gy = groundY ? groundY(x, z) : 0;
          m4.compose(new THREE.Vector3(x, y + gy - box.min.y * sc, z), q, sv);
          im.setMatrixAt(k, tmp.copy(m4).multiply(mesh.matrixWorld));
        });
        im.instanceMatrix.needsUpdate = true;
        group.add(im);
      }
      placed += mine.length;
    }
    this.scene.add(group);
    this.parkland = group;
    this.assets.log.info(`[parkland] ${placed} trees, ${group.children.length} draw calls`);
    return true;
  }

  /**
   * A ground layer of grass blades and wildflowers around the plot, moving in
   * the same wind that drives the trees.
   *
   * The lawn was a flat textured plane: correct colour, completely dead. This
   * scatters alpha-tested blade cards over the ring the camera actually sees
   * (the far parkland stays a plain plane - blades are invisible past ~50 m
   * and would cost a quarter of a million quads for nothing).
   *
   * Movement is hierarchical like the trees, but tuned per layer: blades bend
   * most at the tip and barely at the root, flowers nod on their stem, and
   * every instance carries its own phase so the field ripples rather than
   * pulsing in unison.
   */
  async buildGroundCover(quayX, centreZ, groundY, keepOut) {
    const tex = await this.assets.texture('textures/leaf_card.png', true);
    const flowerTex = await this.assets.texture('textures/flower_card.png', true);
    const R_IN = 22, R_OUT = 62;          // clear of the plot, out to where blades stop reading
    const N = this.share > 0.6 ? 14000 : 6000;
    const blades = [], flowers = [];
    let seed = 20260907;
    const rnd = () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; };
    for (let i = 0; i < N; i++) {
      const a = rnd() * Math.PI * 2, r = R_IN + Math.sqrt(rnd()) * (R_OUT - R_IN);
      const x = quayX + Math.cos(a) * r, z = centreZ + Math.sin(a) * r;
      if (x < quayX + 2) continue;                       // that side is water and quay
      // and nothing paved. Without the plot rectangle the blades came up
      // through the terrace decking and the garden court flagstones.
      if (keepOut && x > keepOut.x1 && x < keepOut.x2 && z > keepOut.z1 && z < keepOut.z2) continue;
      if (Math.abs(x - quayX) < 16 && Math.abs(z) < 150) continue;   // promenade paving
      const gy = groundY ? groundY(x, z) : 0;
      const isFlower = rnd() < 0.06;
      (isFlower ? flowers : blades).push({
        pos: new THREE.Vector3(x, gy + (isFlower ? 0.16 : 0.10), z),
        rot: new THREE.Euler(0, rnd() * 6.2831, (rnd() - 0.5) * 0.25),
        scale: isFlower ? 0.20 + rnd() * 0.10 : 0.26 + rnd() * 0.20,
        phase: rnd() * 6.2831,
        hf: isFlower ? 0.95 : 0.85,
        tint: new THREE.Color().setHSL(
          isFlower ? 0.86 + rnd() * 0.10 : 0.24 + rnd() * 0.07,
          isFlower ? 0.45 + rnd() * 0.25 : 0.42 + rnd() * 0.22,
          isFlower ? 0.55 + rnd() * 0.18 : 0.30 + rnd() * 0.16),
      });
    }
    const group = new THREE.Group(); group.name = 'ground-cover';
    if (blades.length) {
      this.grass = this.cardMesh(blades, tex, 0.92, true);
      this.grass.castShadow = false; this.grass.receiveShadow = false;
      group.add(this.grass);
    }
    if (flowers.length) {
      this.meadowFlowers = this.cardMesh(flowers, flowerTex, 0.8, true);
      this.meadowFlowers.castShadow = false; this.meadowFlowers.receiveShadow = false;
      group.add(this.meadowFlowers);
    }
    this.scene.add(group);
    this.groundCover = group;
    this.assets.log.info(`[groundcover] ${blades.length} grass, ${flowers.length} flowers`);
    return true;
  }

  /** hierarchical wind for a real tree: trunk still, big branches subtle, tips and leaves clear */
  injectWindHierarchical(mat, treeHeight) {
    const U = this.uniforms;
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.uTime = U.uTime; shader.uniforms.uWind = U.uWind; shader.uniforms.uStrength = U.uStrength;
      shader.uniforms.uTreeH = { value: treeHeight };
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>
          uniform float uTime; uniform vec3 uWind; uniform float uStrength; uniform float uTreeH;
          float hashw(vec3 p){ return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453); }`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          {
            #ifdef USE_INSTANCING
              vec4 wp = instanceMatrix * vec4(position, 1.0);
              float ph = hashw(vec3(instanceMatrix[3].xyz)) * 6.2831;
            #else
              vec4 wp = vec4(position, 1.0);
              float ph = 0.0;
            #endif
            float h = clamp(wp.y / max(uTreeH, 0.1), 0.0, 1.0);        // 0 at the roots, 1 at the crown
            float radial = length(wp.xz) / max(uTreeH * 0.35, 0.1);     // 0 at the trunk, 1 at the tips
            float hier = pow(h, 1.6) * (0.35 + 0.65 * clamp(radial, 0.0, 1.0));
            float gust = 0.55 + 0.45 * sin(uTime * 0.31 + ph);
            float n1 = sin(uTime * 1.7 + ph + wp.x * 0.9) * 0.5 + sin(uTime * 2.9 + ph * 1.7 + wp.z * 1.3) * 0.3
                     + sin(uTime * 4.3 + wp.y * 2.1 + ph) * 0.2;
            float amp = uStrength * hier * gust * 0.55;
            transformed.x += uWind.x * n1 * amp;
            transformed.z += uWind.z * n1 * amp;
            transformed.y += sin(uTime * 3.7 + ph + wp.x * 2.0) * amp * 0.25 * h;
          }`);
    };
    mat.customProgramCacheKey = () => 'wind-tree';
  }

  cardMesh(cards, tex, roughness, useTint) {
    const geo = new THREE.PlaneGeometry(1, 1);
    const mat = new THREE.MeshStandardMaterial({
      map: tex || null, alphaTest: 0.42, side: THREE.DoubleSide, roughness,
      color: tex ? 0xffffff : 0x3f7a3a, envMapIntensity: 0.35,
    });
    this.injectWind(mat);
    const im = new THREE.InstancedMesh(geo, mat, cards.length);
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3();
    const aWind = new Float32Array(cards.length * 2);
    cards.forEach((c, i) => {
      q.setFromEuler(c.rot); s.setScalar(c.scale);
      m.compose(c.pos, q, s); im.setMatrixAt(i, m);
      aWind[i * 2] = c.phase; aWind[i * 2 + 1] = c.hf;
      if (useTint && c.tint) im.setColorAt(i, c.tint);
    });
    geo.setAttribute('aWind', new THREE.InstancedBufferAttribute(aWind, 2));
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
    im.receiveShadow = true;
    return im;
  }

  injectWind(mat) {
    const U = this.uniforms;
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.uTime = U.uTime;
      shader.uniforms.uWind = U.uWind;
      shader.uniforms.uStrength = U.uStrength;
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>
          attribute vec2 aWind;
          uniform float uTime; uniform vec3 uWind; uniform float uStrength;`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          {
            float ph = aWind.x, hf = aWind.y;
            float g = 0.6 + 0.4 * sin(uTime * 0.37 + ph * 0.5);        // slow gusts
            float f1 = sin(uTime * 1.9 + ph) * 0.5 + sin(uTime * 3.1 + ph * 1.3) * 0.25;
            float f2 = sin(uTime * 2.3 + ph * 0.7) * 0.35;
            float amp = uStrength * hf * g * (0.6 + 0.4 * uv.y);         // tip of the card moves more
            transformed.x += uWind.x * f1 * amp;
            transformed.z += uWind.z * f1 * amp;
            transformed.y += f2 * amp * 0.35;
          }`);
    };
    mat.customProgramCacheKey = () => 'wind';
  }

  trunk(x, y, z, radius, height, mat, seed) {
    const pts = [];
    const segs = 9;
    for (let i = 0; i <= segs; i++) {
      const t = i / segs;
      const r = radius * (1.15 - t * 0.75) * (1 + 0.08 * Math.sin(seed + t * 9));
      pts.push(new THREE.Vector2(Math.max(0.02, r), t * height));
    }
    const g = new THREE.LatheGeometry(pts, 12);
    const trunk = new THREE.Mesh(g, mat);
    trunk.position.set(x, y, z);
    trunk.rotation.y = seed;
    trunk.castShadow = true; trunk.receiveShadow = true;
    // three main branches leaning outward into the canopy
    for (let b = 0; b < 3; b++) {
      const a = seed + b * 2.1;
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(0, height * 0.55, 0),
        new THREE.Vector3(Math.cos(a) * radius * 2.2, height * 0.75, Math.sin(a) * radius * 2.2),
        new THREE.Vector3(Math.cos(a) * radius * 4.0, height * 0.92, Math.sin(a) * radius * 4.0),
      ]);
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 8, radius * 0.32, 6, false), mat);
      tube.castShadow = true;
      trunk.add(tube);
    }
    return trunk;
  }

  async barkMaterial() {
    const [map, normal, rough] = await Promise.all([
      this.assets.texture('textures/bark_albedo.jpg', true, [1, 3]),
      this.assets.texture('textures/bark_normal.jpg', false, [1, 3]),
      this.assets.texture('textures/bark_rough.jpg', false, [1, 3]),
    ]);
    return new THREE.MeshStandardMaterial({ map, normalMap: normal, roughnessMap: rough,
      color: map ? 0xffffff : 0x5a4432, roughness: 0.9, normalScale: new THREE.Vector2(1.4, 1.4) });
  }

  setWind(kmh, deg) {
    // 0 km/h -> whisper, 60 km/h -> Baku
    const s = 0.08 + Math.min(1, kmh / 60) * 0.9;
    const rad = (deg || 0) * Math.PI / 180;
    this.uniforms.uStrength.value = s;
    this.uniforms.uWind.value.set(Math.sin(rad), 0, Math.cos(rad));
  }

  setWetness(w) {
    if (!this.leafMat) return;
    this.leafMat.color.copy(this.dryLeaf).multiplyScalar(1 - 0.28 * w);
    this.leafMat.roughness = 0.86 - 0.5 * w;
  }

  update(dt, t) { this.uniforms.uTime.value = t; }
}

// -------------------------------------------------------------------- water
/**
 * Harbour water, build 9. One MeshPhysicalMaterial (so it inherits the HDR
 * reflections, sun highlight, fog and tone mapping for free) with a shader
 * patch that adds:
 *   - two scrolling normal layers at different scales (believable texture)
 *   - a colour gradient from a bright shallow blue at the quay to a deep
 *     harbour blue further out (depth without a second render)
 *   - a soft, animated foam line where the water meets the quay wall
 *   - a sparkle term that catches the lamps and the sun
 * No planar reflection pass: that was the most expensive thing in build 8
 * and it made the surface grey, because it mirrored a dark sky.
 */
export class WaterSystem {
  constructor(scene, assets) { this.scene = scene; this.assets = assets; }

  async build(x, z, w, h, y, sun, quality, quayX) {
    const normals = await this.assets.texture('water/waternormals.jpg', false, 1);
    this.quality = quality || 'high';
    // tile at a fixed 9 m regardless of how big the plane is, so a 900 m harbour
    // does not smear the ripples into stripes
    if (normals) { normals.wrapS = normals.wrapT = THREE.RepeatWrapping; normals.repeat.set(w / 9, h / 9); }
    this.u = {
      uTime: { value: 0 }, uQuayX: { value: quayX == null ? x + w / 2 : quayX },
      uShallow: { value: new THREE.Color(0x2f77b8) },     // the reference's bright harbour blue at the edge
      uDeep: { value: new THREE.Color(0x123f7a) },        // and its deeper tone further out
      uFoam: { value: 1.0 }, uWave: { value: 1.0 }, uSparkle: { value: 0.35 },
      // where the water starts dissolving into haze, and what colour it becomes.
      // Without this the plane simply stops and you can see its edge.
      uHorizon: { value: 260.0 }, uHaze: { value: new THREE.Color(0x9fb6cc) },
    };
    const mat = new THREE.MeshPhysicalMaterial({
      color: 0x1f5c9e, roughness: 0.16, metalness: 0.0,
      normalMap: normals || null, normalScale: new THREE.Vector2(0.65, 0.65),
      envMapIntensity: 1.35, clearcoat: 0.5, clearcoatRoughness: 0.12,
      specularIntensity: 1.0,
    });
    const U = this.u;
    mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, U);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vWaterW;')
        .replace('#include <worldpos_vertex>', '#include <worldpos_vertex>\nvWaterW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
          uniform float uTime, uQuayX, uFoam, uWave, uSparkle, uHorizon; uniform vec3 uShallow, uDeep, uHaze;
          varying vec3 vWaterW;
          float wnoise(vec2 p){ return sin(p.x * 1.7 + uTime * 0.9) * sin(p.y * 2.3 - uTime * 0.7) * 0.5 + 0.5; }`)
        .replace('#include <normal_fragment_maps>', `
          #ifdef USE_NORMALMAP_TANGENTSPACE
            vec2 uvA = vNormalMapUv + vec2(uTime * 0.012, uTime * 0.019);
            vec2 uvB = vNormalMapUv * 2.6 + vec2(-uTime * 0.021, uTime * 0.014);
            vec3 nA = texture2D(normalMap, uvA).xyz * 2.0 - 1.0;
            vec3 nB = texture2D(normalMap, uvB).xyz * 2.0 - 1.0;
            vec3 mapN = normalize(vec3(nA.xy * 0.7 + nB.xy * 0.5, 1.0));
            mapN.xy *= normalScale * uWave;
            normal = normalize(tbn * mapN);
          #else
            // no normal texture on disk: a procedural ripple so the surface still moves
            vec3 wn = normalize(vec3(sin(vWaterW.x * 2.1 + uTime * 1.1) * 0.06 + sin(vWaterW.z * 3.3 - uTime * 0.8) * 0.05, 1.0,
                                     cos(vWaterW.z * 1.7 + uTime * 0.9) * 0.06));
            normal = normalize((viewMatrix * vec4(wn, 0.0)).xyz);
          #endif`)
        .replace('#include <color_fragment>', `#include <color_fragment>
          float toQuay = uQuayX - vWaterW.x;                       // metres from the quay wall, growing westward
          float deep = smoothstep(0.4, 9.0, toQuay);
          diffuseColor.rgb = mix(uShallow, uDeep, deep);
          float lap = wnoise(vWaterW.xz * 0.9) * 0.6 + wnoise(vWaterW.zx * 2.1 + 3.0) * 0.4;
          float foam = (1.0 - smoothstep(0.0, 1.1 + 0.5 * lap, toQuay)) * uFoam;
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.86, 0.92, 0.96), foam * (0.55 + 0.45 * lap));
          float sp = pow(wnoise(vWaterW.xz * 7.0 + uTime * 0.3) * wnoise(vWaterW.zx * 11.0 - uTime * 0.2), 6.0);
          // sparkle only near the viewer: at 300 m it would alias into noise
          float dCam = length(vWaterW.xz - cameraPosition.xz);
          float near = 1.0 - smoothstep(0.0, uHorizon * 0.5, dCam);
          diffuseColor.rgb += vec3(0.9, 0.95, 1.0) * sp * uSparkle * near;
          // and the far water dissolves into haze, so the plane has no visible edge
          float far = smoothstep(uHorizon * 0.55, uHorizon * 1.9, dCam);
          diffuseColor.rgb = mix(diffuseColor.rgb, uHaze, far * 0.92);`)
        .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
          roughnessFactor = mix(roughnessFactor, 0.6, foam);
          roughnessFactor = mix(roughnessFactor, 0.42, far);`);
      // a long, low swell across the whole harbour, so the far water is not a
      // mirror-flat sheet. Two crossed waves is enough at this distance.
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>
          uniform float uTime, uWave;`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          vec3 swellW = (modelMatrix * vec4(transformed, 1.0)).xyz;
          transformed.z += (sin(swellW.x * 0.055 + uTime * 0.55) * 0.16
                          + sin(swellW.z * 0.041 - uTime * 0.42) * 0.13) * uWave;`);
    };
    mat.customProgramCacheKey = () => 'sufra-water-11';
    // a couple of hundred segments over 900 m is roughly one vertex every 5 m:
    // enough for the swell to read, cheap enough to be irrelevant to the budget
    const seg = quality === 'smooth' ? 48 : quality === 'balanced' ? 96 : 160;
    const geo = new THREE.PlaneGeometry(w, h, seg, seg);
    this.water = new THREE.Mesh(geo, mat);
    this.water.rotation.x = -Math.PI / 2;
    this.water.position.set(x, y, z);
    this.water.receiveShadow = true;
    this.scene.add(this.water);
    this.mat = mat;
    return this;
  }

  /** keep the far water the same colour as the sky it fades into */
  setHaze(color, horizon) {
    if (color) this.u.uHaze.value.copy(color);
    if (horizon) this.u.uHorizon.value = horizon;
  }

  setConditions(windKmh, rain) {
    if (!this.mat) return;
    const wind = Math.min(1, windKmh / 50);
    this.u.uWave.value = 0.7 + wind * 0.9 + rain * 0.4;
    this.u.uFoam.value = 0.8 + wind * 0.5;
    this.mat.roughness = 0.14 + rain * 0.2 + wind * 0.05;
    this.u.uSparkle.value = 0.35 * (1 - rain * 0.7);
  }

  setSun(dir, color) { /* the physical material reads the scene's sun light directly */ }

  update(dt) { if (this.mat) this.u.uTime.value += dt; }
}

// ------------------------------------------------------------ rain and snow
/**
 * GPU rain: every drop is two vertices of one LineSegments; the vertex
 * shader moves it, leans it into the wind and fades it with distance so
 * the sheet has depth. Snow reuses the same buffer as slow bright points.
 */
export class RainSystem {
  constructor(scene, bounds, maxDrops) {
    this.scene = scene;
    this.bounds = bounds;
    this.max = maxDrops;
    const n = maxDrops;
    const pos = new Float32Array(n * 2 * 3);
    const seed = new Float32Array(n * 2 * 4);   // x0, z0, speed, len
    const end = new Float32Array(n * 2);        // 0 top, 1 bottom
    const idx = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      const x = bounds.minX + Math.random() * (bounds.maxX - bounds.minX);
      const z = bounds.minZ + Math.random() * (bounds.maxZ - bounds.minZ);
      const sp = 9 + Math.random() * 7, len = 0.25 + Math.random() * 0.45;
      const y0 = Math.random() * 30;
      for (let k = 0; k < 2; k++) {
        const j = i * 2 + k;
        pos[j * 3] = x; pos[j * 3 + 1] = y0; pos[j * 3 + 2] = z;
        seed[j * 4] = x; seed[j * 4 + 1] = z; seed[j * 4 + 2] = sp; seed[j * 4 + 3] = len;
        end[j] = k;
        idx[j] = i;
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('aSeed', new THREE.BufferAttribute(seed, 4));
    geo.setAttribute('aEnd', new THREE.BufferAttribute(end, 1));
    geo.setAttribute('aIdx', new THREE.BufferAttribute(idx, 1));
    this.uniforms = {
      uTime: { value: 0 }, uWind: { value: new THREE.Vector3(0.3, 0, 0.1) },
      uCount: { value: 0 }, uOpacity: { value: 0 }, uSnow: { value: 0 },
      uColor: { value: new THREE.Color(0xbcd0e8) },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute vec4 aSeed; attribute float aEnd; attribute float aIdx;
        uniform float uTime; uniform vec3 uWind; uniform float uCount; uniform float uSnow;
        varying float vFade;
        void main() {
          float idx = aIdx;
          float alive = step(idx, uCount);
          float speed = mix(aSeed.z, 1.1 + aSeed.z * 0.08, uSnow);
          float y = mod(position.y - uTime * speed, 30.0);
          float lean = (30.0 - y) * 0.06;
          float wob = uSnow * sin(uTime * 1.3 + idx) * 0.6;
          vec3 p = vec3(aSeed.x + uWind.x * lean + wob, y - aEnd * aSeed.w * (1.0 - uSnow * 0.9),
                        aSeed.y + uWind.z * lean);
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float d = -mv.z;
          vFade = alive * smoothstep(90.0, 12.0, d) * (0.55 + 0.45 * aEnd);
          gl_Position = projectionMatrix * mv;
          gl_PointSize = 2.5 * (60.0 / max(d, 1.0));
        }`,
      fragmentShader: `
        uniform float uOpacity; uniform vec3 uColor; uniform float uSnow;
        varying float vFade;
        void main() {
          // Rain stays a hard line (LineSegments, unaffected by gl_PointCoord).
          // Snow is drawn as THREE.Points, which are square by default - this
          // is what made every flake read as a tiny tile rather than a dot.
          // A radial falloff from the point's own center turns it into a soft
          // circular flake with no new geometry or texture.
          vec2 c = gl_PointCoord - 0.5;
          float disc = 1.0 - smoothstep(0.28, 0.5, length(c));
          float snowAlpha = mix(1.0, disc, uSnow);
          if (uSnow > 0.5 && disc <= 0.0) discard;
          gl_FragColor = vec4(uColor, vFade * uOpacity * mix(0.55, 0.9, uSnow) * snowAlpha);
        }`,
    });
    this.lines = new THREE.LineSegments(geo, mat);
    this.lines.frustumCulled = false;
    this.points = new THREE.Points(geo, mat.clone());
    this.points.material.uniforms = this.uniforms;
    this.points.frustumCulled = false;
    this.points.visible = false;
    scene.add(this.lines, this.points);
  }

  /** intensity 0..1, snow bool */
  set(intensity, snow, windKmh, windDeg) {
    const rad = (windDeg || 0) * Math.PI / 180;
    this.uniforms.uWind.value.set(Math.sin(rad) * (0.15 + windKmh / 60), 0, Math.cos(rad) * (0.15 + windKmh / 60));
    this.uniforms.uCount.value = this.max * intensity;
    this.uniforms.uOpacity.value = intensity > 0.01 ? 0.5 + 0.5 * intensity : 0;
    this.uniforms.uSnow.value = snow ? 1 : 0;
    this.uniforms.uColor.value.set(snow ? 0xf4f7ff : 0xbcd0e8);
    this.lines.visible = !snow && intensity > 0.01;
    this.points.visible = snow && intensity > 0.01;
  }

  update(dt, t) { this.uniforms.uTime.value = t; }
}
