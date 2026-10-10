import * as THREE from '/static/vendor/three/three.module.js';
import { GLTFLoader } from '/static/vendor/three/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from '/static/vendor/three/jsm/loaders/DRACOLoader.js';
import { RGBELoader } from '/static/vendor/three/jsm/loaders/RGBELoader.js';

const ROOT = '/static/3d/';

// Every real model in the project, with its licence. A missing file never
// throws past this module: instance() returns null and the builder uses
// its built-in fallback for that object type.
export const CATALOG = {
  chairSheen:   { file: 'chairs/sheen_chair.glb',       licence: 'CC0-1.0',   author: 'Khronos glTF-Sample-Assets', chair: true },
  // Kenney CC0 tableware, via the pmndrs market mirror
  glassWine:    { file: 'models/tableware/glass-wine.gltf',    licence: 'CC0-1.0', author: 'Kenney' },
  glassWater:   { file: 'models/tableware/glass.gltf',         licence: 'CC0-1.0', author: 'Kenney' },
  plateDinner:  { file: 'models/tableware/plate-dinner.gltf',  licence: 'CC0-1.0', author: 'Kenney' },
  fork:         { file: 'models/tableware/utensil-fork.gltf',  licence: 'CC0-1.0', author: 'Kenney' },
  knife:        { file: 'models/tableware/utensil-knife.gltf', licence: 'CC0-1.0', author: 'Kenney' },
  wineRed:      { file: 'models/tableware/wine-red.gltf',      licence: 'CC0-1.0', author: 'Kenney' },
  cupSaucer:    { file: 'models/tableware/cup-saucer.gltf',    licence: 'CC0-1.0', author: 'Kenney' },
  // Sara Vieira CC0 furniture and plants, via the pmndrs market
  diningTable:  { file: 'models/props/table.gltf',  licence: 'CC0-1.0', author: 'Sara Vieira (ambientCG Wood027 PBR)' },
  bench:        { file: 'models/props/bench.gltf',  licence: 'CC0-1.0', author: 'Sara Vieira' },
  plant:        { file: 'models/props/plant.gltf',  licence: 'CC0-1.0', author: 'Sara Vieira' },
  chairDamask:  { file: 'chairs/damask_chair.glb',      licence: 'CC-BY-4.0', author: 'Khronos glTF-Sample-Assets', chair: true },
  lantern:      { file: 'lamps/lantern.glb',            licence: 'CC0-1.0',   author: 'Khronos glTF-Sample-Assets' },
  waterBottle:  { file: 'tableware/water_bottle.glb',   licence: 'CC0-1.0',   author: 'Khronos glTF-Sample-Assets' },
  dishOlives:   { file: 'tableware/dish_olives.glb',    licence: 'CC-BY-4.0', author: 'Khronos glTF-Sample-Assets' },
  vaseFlowers:  { file: 'decor/vase_flowers.glb',       licence: 'CC0-1.0',   author: 'Khronos glTF-Sample-Assets' },
  // Poly Haven CC0, prepared by blender/prep_assets.py. These replace the
  // tapered cylinder + soil disc that used to stand in for a planter.
  planterPot:   { file: 'models/props/planter_pot_clay.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  // ---- authored in-project by blender/author_assets.py. Modelled from
  // scratch at catering/joinery dimensions, so the venue owns them outright
  // and no third-party licence applies.
  umbrellaReal: { file: 'models/authored/umbrella.glb',        licence: 'CC0 (this project)', author: 'SUFRA' },
  kitchenRun:   { file: 'models/authored/kitchen_run.glb',     licence: 'CC0 (this project)', author: 'SUFRA' },
  bathSuite:    { file: 'models/authored/bathroom_suite.glb',  licence: 'CC0 (this project)', author: 'SUFRA' },
  diningTableA: { file: 'models/authored/dining_table.glb',    licence: 'CC0 (this project)', author: 'SUFRA' },
  banquette:    { file: 'models/authored/banquette.glb',       licence: 'CC0 (this project)', author: 'SUFRA' },
  // ProVis3D 034 Restaurant (user-supplied archviz scene). The FBX/OBJ export
  // lost every texture link - the .mtl has no map_Kd at all - so the geometry
  // is the asset here and blender/dress_provis.py gives it materials from the
  // surviving descriptive material names (Go = wood, May tre = rattan, Kim
  // loai vang = brass, stone-iland, leaf, palm_bark).
  // These six files are a licensed third-party product and are not in the
  // repository (see static/3d/ASSET_CREDITS.md). Where a `fallback` is named,
  // that CC0 model is used when the file is absent.
  provisChair:  { file: 'models/provis/chair.glb',       licence: 'user upload', author: 'ProVis3D 034', chair: true, fallback: 'chairDining' },
  provisTable:  { file: 'models/provis/table.glb',       licence: 'user upload', author: 'ProVis3D 034', fallback: 'tableDining' },
  provisBar:    { file: 'models/provis/bar_counter.glb', licence: 'user upload', author: 'ProVis3D 034' },
  provisBarBack:{ file: 'models/provis/bar_back.glb',    licence: 'user upload', author: 'ProVis3D 034' },
  provisPalm:   { file: 'models/provis/palm.glb',        licence: 'user upload', author: 'ProVis3D 034' },
  provisPlant:  { file: 'models/provis/plant.glb',       licence: 'user upload', author: 'ProVis3D 034' },
  dishMeat:     { file: 'models/authored/dish_meat.glb',       licence: 'CC0 (this project)', author: 'SUFRA' },
  dishGrain:    { file: 'models/authored/dish_grain.glb',      licence: 'CC0 (this project)', author: 'SUFRA' },
  dishVeg:      { file: 'models/authored/dish_veg.glb',        licence: 'CC0 (this project)', author: 'SUFRA' },
  // Interior fit-out, Poly Haven CC0, prepped by blender/prep_assets.py. The
  // chair entries carry chair:true so model() runs measureFacing on them and
  // every chair ends up facing its table whatever axis the artist modelled to.
  chairDining:  { file: 'models/furniture/dining_chair_02.glb', licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  chairGreen:   { file: 'models/furniture/GreenChair_01.glb',   licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  chairWooden:  { file: 'models/furniture/WoodenChair_01.glb',  licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  armChair:     { file: 'models/furniture/ArmChair_01.glb',     licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  sofaBanquette:{ file: 'models/furniture/Sofa_01.glb',         licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  tableDining:  { file: 'models/furniture/dining_table.glb',    licence: 'CC0-1.0', author: 'Poly Haven' },
  tableSquare:  { file: 'models/furniture/WoodenTable_02.glb',  licence: 'CC0-1.0', author: 'Poly Haven' },
  tableRound:   { file: 'models/furniture/coffee_table_round_01.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  barStool:     { file: 'models/furniture/bar_chair_round_01.glb', licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  metalStool:   { file: 'models/furniture/metal_stool_02.glb',  licence: 'CC0-1.0', author: 'Poly Haven', chair: true },
  shelfUnit:    { file: 'models/furniture/Shelf_01.glb',        licence: 'CC0-1.0', author: 'Poly Haven' },
  sideboard:    { file: 'models/furniture/modern_wooden_cabinet.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  vaseCeramic:  { file: 'models/tableware/ceramic_vase_02.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  vaseBrass:    { file: 'models/tableware/brass_vase_01.glb',   licence: 'CC0-1.0', author: 'Poly Haven' },
  potCeramic:   { file: 'models/plants/ceramic_pot.glb',        licence: 'CC0-1.0', author: 'Poly Haven' },
  foodPomegranate: { file: 'models/tableware/food_pomegranate_01.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  foodApple:    { file: 'models/tableware/food_apple_01.glb',   licence: 'CC0-1.0', author: 'Poly Haven' },
  tableLamp:    { file: 'models/lamps/desk_lamp_arm_01.glb',    licence: 'CC0-1.0', author: 'Poly Haven' },
  wallSconce:   { file: 'models/lamps/industrial_wall_lamp.glb',licence: 'CC0-1.0', author: 'Poly Haven' },
  pendantLamp:  { file: 'models/lamps/modern_ceiling_lamp_01.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
  plantPotted1: { file: 'models/plants/potted_plant_01.glb',    licence: 'CC0-1.0', author: 'Poly Haven' },
  plantPotted2: { file: 'models/plants/potted_plant_02.glb',    licence: 'CC0-1.0', author: 'Poly Haven' },
  planterBox:   { file: 'models/props/planter_box_01.glb',   licence: 'CC0-1.0', author: 'Poly Haven' },
  streetLamp:   { file: 'models/props/street_lamp_01.glb',   licence: 'CC0-1.0', author: 'Poly Haven' },
  benchStreet:  { file: 'models/props/modular_street_seating.glb', licence: 'CC0-1.0', author: 'Poly Haven' },
};

/** a promise that gives up: a stalled download must never stall the whole scene */
export function withTimeout(promise, ms, label) {
  let t;
  const timer = new Promise((_, rej) => { t = setTimeout(() => rej(new Error((label || 'load') + ' timed out after ' + (ms / 1000) + 's')), ms); });
  return Promise.race([promise, timer]).finally(() => clearTimeout(t));
}

export class AssetManager {
  constructor(log, quality) {
    this.log = log || console;
    this.quality = quality || 'high';
    this.gltf = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath('/static/vendor/three/jsm/libs/draco/');
    this.gltf.setDRACOLoader(draco);
    this.tex = new THREE.TextureLoader();
    this.hdr = new RGBELoader();
    this.models = {};
    this.pending = {};
    this.textures = {};
    this.failed = new Set();
    this.aniso = this.quality === 'ultra' ? 8 : this.quality === 'high' ? 8 : 4;
    this.bytes = 0;
  }

  /** fire every download at once; nothing awaits here */
  preload(names) {
    for (const n of names) this.model(n).catch(() => null);
  }

  async model(name) {
    if (this.models[name]) return this.models[name];
    if (this.failed.has(name)) return null;
    if (this.pending[name]) return this.pending[name];
    const entry = CATALOG[name];
    if (!entry) return null;
    const p = (async () => {
      try {
        // 30 s was a queue timeout, not a stall timeout: the deferred layer asks
        // for the trees, the characters, two HDRs and every prop at once, and a
        // 90 KB planter that serves in 8 ms was timing out behind them. The
        // guard is here to stop a genuinely dead download blocking the scene,
        // and 90 s still does that.
        const g = await withTimeout(this.gltf.loadAsync(ROOT + entry.file), 90000, name);
        const root = g.scene;
        root.updateMatrixWorld(true);
        // normalise: measure so builders can scale to real-world size
        const box = new THREE.Box3().setFromObject(root);
        const size = new THREE.Vector3(); box.getSize(size);
        const meshes = [];
        root.traverse(o => {
          if (o.isMesh) {
            o.castShadow = true; o.receiveShadow = true;
            const m = o.material;
            if (m) {
              if (m.map) m.map.anisotropy = this.aniso;
              // a full-scene transmission pass per frame is the single most expensive thing a
              // material can ask for; glass in small props reads just as well as tinted gloss
              if ('transmission' in m && m.transmission > 0) { m.transmission = 0; m.transparent = true; m.opacity = Math.max(m.opacity, 0.72); m.roughness = Math.min(m.roughness, 0.15); }
            }
            meshes.push(o);
          }
        });
        const rec = { root, meshes, box, size, faceFix: entry.chair ? this.measureFacing(root, box, size) : 0 };
        this.models[name] = rec;
        return rec;
      } catch (e) {
        this.failed.add(name);
        this.log.warn('[assets] ' + name + ' unavailable, using fallback: ' + e.message);
        if (entry.fallback && CATALOG[entry.fallback]) {
          const rec = await this.model(entry.fallback);
          if (rec) this.models[name] = rec;
          return rec;
        }
        return null;
      } finally { delete this.pending[name]; }
    })();
    this.pending[name] = p;
    return p;
  }

  /**
   * Which way does a chair model face? Its backrest is the tallest part, so the
   * centroid of the upper vertices sits BEHIND the seat. The chair faces the
   * opposite way. Returns the Y rotation that makes it face +Z, whatever the
   * artist's convention was - so every chair in the room faces its table.
   */
  measureFacing(root, box, size) {
    const cx = (box.min.x + box.max.x) / 2, cz = (box.min.z + box.max.z) / 2;
    const v = new THREE.Vector3();
    let n = 0, sx = 0, sz = 0;
    root.traverse(o => {
      if (!o.isMesh || !o.geometry || !o.geometry.attributes.position) return;
      const pos = o.geometry.attributes.position;
      const step = Math.max(1, Math.floor(pos.count / 4000));
      for (let i = 0; i < pos.count; i += step) {
        v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
        if ((v.y - box.min.y) / size.y > 0.7) { n++; sx += v.x - cx; sz += v.z - cz; }
      }
    });
    if (!n) return 0;
    const fx = -sx / n, fz = -sz / n;            // facing = away from the backrest
    if (Math.hypot(fx, fz) < 1e-4) return 0;
    return -Math.atan2(fx, fz);
  }

  /**
   * Place one loaded model many times with ONE draw call per sub-mesh.
   * transforms: [{ position: Vector3, rotationY: number, scale: number }]
   * Returns a Group of InstancedMeshes (or null if the model failed).
   */
  async instance(name, transforms, opts) {
    const m = await this.model(name);
    if (!m || !transforms.length) return null;
    opts = opts || {};
    const group = new THREE.Group();
    group.name = 'inst:' + name;
    const target = opts.height ? opts.height / m.size.y
                 : opts.width ? opts.width / Math.max(m.size.x, m.size.z)
                 : (opts.scale || 1);
    const yOff = -m.box.min.y * target;               // stand on the floor
    const cx = (m.box.min.x + m.box.max.x) / 2, cz = (m.box.min.z + m.box.max.z) / 2;
    const fix = opts.face === false ? 0 : (m.faceFix || 0);
    const base = new THREE.Matrix4();
    const tmp = new THREE.Matrix4();
    const q = new THREE.Quaternion();
    const s = new THREE.Vector3();
    const Y = new THREE.Vector3(0, 1, 0);
    for (const mesh of m.meshes) {
      let material = mesh.material;
      if (opts.tint != null || opts.roughness != null) {
        material = material.clone();
        if (opts.tint != null) material.color.multiply(new THREE.Color(opts.tint));
        if (opts.roughness != null && 'roughness' in material) material.roughness = opts.roughness;
        if ('sheen' in material) material.sheen = 0.35;
      }
      const im = new THREE.InstancedMesh(mesh.geometry, material, transforms.length);
      im.castShadow = opts.castShadow !== false;
      im.receiveShadow = true;
      transforms.forEach((t, i) => {
        q.setFromAxisAngle(Y, (t.rotationY || 0) + fix);
        const sx = t.sx || t.scale || 1, sz = t.sz || t.scale || 1, sy = t.sy || t.scale || 1;
        s.set(target * sx, target * sy, target * sz);
        // recentre the model on its footprint so off-origin sources still land where asked
        const off = new THREE.Vector3(-cx * target * sx, 0, -cz * target * sz).applyQuaternion(q);
        base.compose(new THREE.Vector3(t.position.x + off.x, t.position.y + yOff * sy, t.position.z + off.z), q, s);
        tmp.copy(base).multiply(mesh.matrixWorld);
        im.setMatrixAt(i, tmp);
      });
      im.instanceMatrix.needsUpdate = true;
      im.frustumCulled = true;
      group.add(im);
    }
    return group;
  }

  async texture(path, srgb, repeat) {
    const key = path + '|' + (repeat || 1);
    if (this.textures[key] !== undefined) return this.textures[key];
    try {
      const t = await withTimeout(this.tex.loadAsync(ROOT + path), 20000, path);
      t.wrapS = t.wrapT = THREE.RepeatWrapping;
      if (repeat) t.repeat.set(repeat[0] || repeat, repeat[1] || repeat);
      if (srgb) t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = this.aniso;
      this.textures[key] = t;
      return t;
    } catch (e) {
      this.log.warn('[assets] texture missing: ' + path);
      this.textures[key] = null;
      return null;
    }
  }

  async environment(file) {
    try {
      const t = await withTimeout(this.hdr.loadAsync(ROOT + file), 25000, file);
      t.mapping = THREE.EquirectangularReflectionMapping;
      return t;
    } catch (e) {
      this.log.warn('[assets] HDR missing: ' + file);
      return null;
    }
  }
}

// ---------------------------------------------------------------- materials
/**
 * PBR material sets that know how to get wet. Each material remembers its
 * dry values; Materials.setWetness(0..1) darkens albedo and lowers
 * roughness on outdoor surfaces so restaurant lights reflect off them.
 */
export class Materials {
  constructor(assets) {
    this.assets = assets;
    this.outdoor = [];       // [{mat, dryColor, dryRough, wetRough}]
    this.cache = {};
  }

  async pbr(setName, opts) {
    opts = opts || {};
    const key = setName + JSON.stringify(opts);
    if (this.cache[key]) return this.cache[key];
    const rep = opts.repeat || 1;
    const [map, normal, rough] = await Promise.all([
      this.assets.texture('textures/' + setName + '_albedo.jpg', true, rep),
      this.assets.texture('textures/' + setName + '_normal.jpg', false, rep),
      this.assets.texture('textures/' + setName + '_rough.jpg', false, rep),
    ]);
    const mat = new THREE.MeshStandardMaterial({
      map: map || null, normalMap: normal || null, roughnessMap: rough || null,
      color: opts.tint ? new THREE.Color(opts.tint) : new THREE.Color(0xffffff),
      roughness: opts.roughness == null ? 0.85 : opts.roughness,
      metalness: opts.metalness || 0,
      normalScale: new THREE.Vector2(opts.normalScale || 1, opts.normalScale || 1),
      envMapIntensity: opts.env == null ? 0.6 : opts.env,
    });
    if (!map) mat.color.set(opts.fallback || 0x8a7a66);
    if (opts.outdoor) {
      this.outdoor.push({ mat, dryColor: mat.color.clone(),
                          dryRough: mat.roughness, wetRough: opts.wetRough == null ? 0.22 : opts.wetRough,
                          dryEnv: mat.envMapIntensity });
    }
    this.cache[key] = mat;
    return mat;
  }

  /** ambientCG scanned sets: Color / Normal / Roughness / AmbientOcclusion (CC0) */
  async scanned(folder, prefix, opts) {
    opts = opts || {};
    const rep = opts.repeat || 1;
    const [map, normal, rough, ao] = await Promise.all([
      this.assets.texture('textures/' + folder + '/' + prefix + '_Color.jpg', true, rep),
      this.assets.texture('textures/' + folder + '/' + prefix + '_Normal.jpg', false, rep),
      this.assets.texture('textures/' + folder + '/' + prefix + '_Roughness.jpg', false, rep),
      // only the wood set ships an AO map; asking for the others just logged 404s
      folder === 'wood' ? this.assets.texture('textures/' + folder + '/' + prefix + '_AmbientOcclusion.jpg', false, rep) : Promise.resolve(null),
    ]);
    const mat = new THREE.MeshStandardMaterial({
      map: map || null, normalMap: normal || null, roughnessMap: rough || null, aoMap: ao || null,
      aoMapIntensity: 0.9, roughness: opts.roughness == null ? 1 : opts.roughness,
      metalness: 0, envMapIntensity: opts.env == null ? 0.7 : opts.env,
      normalScale: new THREE.Vector2(opts.normalScale || 1, opts.normalScale || 1),
      color: opts.tint ? new THREE.Color(opts.tint) : new THREE.Color(0xffffff),
    });
    if (!map) mat.color.set(opts.fallback || 0x8a7a66);
    if (opts.outdoor) this.outdoor.push({ mat, dryColor: mat.color.clone(), dryRough: mat.roughness,
                                          wetRough: opts.wetRough == null ? 0.22 : opts.wetRough, dryEnv: mat.envMapIntensity });
    return mat;
  }

  /** three.js wood / brick sets shipped with the examples (MIT) */
  async threeSet(prefix, opts) {
    opts = opts || {};
    const rep = opts.repeat || 1;
    const [map, bump, rough] = await Promise.all([
      this.assets.texture('textures/' + prefix + '_diffuse.jpg', true, rep),
      this.assets.texture('textures/' + prefix + '_bump.jpg', false, rep),
      this.assets.texture('textures/' + prefix + '_roughness.jpg', false, rep),
    ]);
    const mat = new THREE.MeshStandardMaterial({
      map: map || null, bumpMap: bump || null, bumpScale: 0.02, roughnessMap: rough || null,
      roughness: 0.7, envMapIntensity: 0.5, color: opts.tint ? new THREE.Color(opts.tint) : new THREE.Color(0xffffff),
    });
    if (!map) mat.color.set(opts.fallback || 0x7a5a3a);
    if (opts.outdoor) this.outdoor.push({ mat, dryColor: mat.color.clone(), dryRough: mat.roughness,
                                          wetRough: 0.25, dryEnv: mat.envMapIntensity });
    return mat;
  }

  /** window glass that costs one draw call, not a second render of the whole room */
  glass(opts) {
    opts = opts || {};
    return new THREE.MeshPhysicalMaterial({
      color: opts.color || 0xcfe0ee, metalness: 0, roughness: 0.06,
      transparent: true, opacity: opts.opacity == null ? 0.16 : opts.opacity,
      envMapIntensity: 1.6, reflectivity: 0.9, clearcoat: 0.4, clearcoatRoughness: 0.08,
      depthWrite: false, side: THREE.DoubleSide,
    });
  }

  setWetness(w) {
    w = Math.max(0, Math.min(1, w));
    if (Math.abs(w - (this._lastWet || 0)) < 0.002) return;   // no material churn while dry
    this._lastWet = w;
    for (const o of this.outdoor) {
      o.mat.color.copy(o.dryColor).multiplyScalar(1 - 0.42 * w);
      o.mat.roughness = o.dryRough + (o.wetRough - o.dryRough) * w;
      o.mat.envMapIntensity = o.dryEnv + (1.6 - o.dryEnv) * w;
    }
  }
}
