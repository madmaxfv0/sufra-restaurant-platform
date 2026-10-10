import * as THREE from '/static/vendor/three/three.module.js';

/**
 * Loads the venue you built in Blender and wires it to the live restaurant.
 *
 * The website keeps every function it had. Clicking, zooming, hover cards, the
 * assistant, the reservation flow and the live table lamps are all driven by
 * your venue database, not by geometry. This module only swaps out what the
 * room LOOKS like. It finds your objects by name:
 *
 *     table_t01 .. table_t25   clicked, highlighted, focused by the camera
 *     lamp_t01  .. lamp_t25    tinted green / red / amber as tables free up
 *     seat_t01-A ...           where guests sit
 *     water                    handed to the water animation
 *
 * If static/models/venue.glb is missing or fails to load, nothing breaks: the
 * site builds the procedural room exactly as before.
 */
export class GLBVenue {
  constructor(assets, log) {
    this.assets = assets;
    this.log = log || console;
    this.tables = {};        // table id -> Object3D
    this.lamps = {};         // table id -> { nodes: Mesh[], base: Color[] }
    this.seats = {};         // seat id  -> Object3D
    this.clips = [];
    this.loaded = false;
  }

  /** true if the file is there. Cheap HEAD request, so a missing model costs nothing. */
  static async available(url) {
    try {
      const r = await fetch(url, { method: 'HEAD' });
      return r.ok && (r.headers.get('content-length') === null ||
                      parseInt(r.headers.get('content-length'), 10) > 1000);
    } catch (e) { return false; }
  }

  /**
   * @param onProgress called with 0..1 while downloading, so the entry screen
   *        shows real progress instead of a guess
   */
  async load(url, scene, onProgress) {
    const gltf = await new Promise((res, rej) => {
      this.assets.gltf.load(url, res, (e) => {
        if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total);
      }, (err) => {
        const msg = String((err && err.message) || err);
        // the one failure worth naming, because the cause is not obvious
        if (/draco|DRACOLoader|decoder/i.test(msg)) {
          rej(new Error('This venue.glb is Draco-compressed but the decoder is missing. ' +
            'Either export again without --draco, or copy the draco folder from three.js ' +
            'into static/vendor/three/jsm/libs/draco/.'));
        } else {
          rej(new Error('venue.glb could not be read: ' + msg.slice(0, 160)));
        }
      });
    });

    this.root = gltf.scene;
    this.root.name = 'venue_glb';
    this.clips = gltf.animations || [];

    this.index();
    this.condition();
    scene.add(this.root);
    this.loaded = true;

    if (this.clips.length) {
      this.mixer = new THREE.AnimationMixer(this.root);
      for (const clip of this.clips) this.mixer.clipAction(clip).play();
    }

    const counts = {
      tables: Object.keys(this.tables).length,
      lamps: Object.keys(this.lamps).length,
      seats: Object.keys(this.seats).length,
      clips: this.clips.length,
      background: !!this.hasBackground,
      meshes: this.meshCount,
      triangles: this.triangles,
    };
    console.info('[SUFRA 360] Blender venue loaded:', JSON.stringify(counts));
    return counts;
  }

  /** find the objects the site needs to talk to */
  index() {
    this.meshCount = 0;
    this.triangles = 0;
    this.root.traverse((o) => {
      if (o.isMesh) {
        this.meshCount++;
        const g = o.geometry;
        if (g && g.index) this.triangles += g.index.count / 3;
        else if (g && g.attributes.position) this.triangles += g.attributes.position.count / 3;
      }
      const n = o.name || '';
      // Blender appends .001 to duplicate names; ignore that suffix
      const clean = n.replace(/\.\d{3}$/, '');
      if (clean.startsWith('table_')) {
        const id = (o.userData && o.userData.table_id) || clean.slice(6);
        if (!this.tables[id]) this.tables[id] = o;
      } else if (clean.startsWith('lamp_') && !clean.startsWith('lamp_post') && !clean.startsWith('lamp_head')) {
        const id = clean.slice(5);
        const meshes = [];
        o.traverse((c) => { if (c.isMesh) meshes.push(c); });
        // an Empty on its own still works: we place a light and a halo at it
        this.lamps[id] = { node: o, meshes };
      } else if (clean.startsWith('seat_')) {
        this.seats[clean.slice(5)] = o;
      } else if (clean === 'water') {
        this.water = o;
      } else if (clean.startsWith('baku_') || clean.startsWith('background_')) {
        // the model brings its own horizon, so the site should not add one
        this.hasBackground = true;
      }
    });
  }

  /**
   * Make the Blender materials behave on the web.
   *
   * Blender exports glass as `transmission`, which forces three.js to render the
   * whole scene a second time every frame. On a Mac in Safari that alone can
   * halve the frame rate, so it becomes ordinary transparency, which looks
   * near-identical at these distances.
   */
  condition() {
    const seen = new Set();
    this.root.traverse((o) => {
      if (!o.isMesh) return;
      o.castShadow = true;
      o.receiveShadow = true;
      // huge ground and water planes should receive but not cast
      if (/^(floor_ground|water)/.test(o.name)) o.castShadow = false;

      const mats = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of mats) {
        if (!m || seen.has(m.uuid)) continue;
        seen.add(m.uuid);
        if (m.transmission !== undefined && m.transmission > 0) {
          m.transmission = 0;
          m.transparent = true;
          m.opacity = Math.min(0.55, m.opacity !== undefined ? m.opacity : 0.35);
          m.depthWrite = false;
        }
        if (m.envMapIntensity !== undefined) m.envMapIntensity = 1.0;
        // Blender writes emissive strength as a separate factor the exporter folds in;
        // clamp it so a bright lamp does not blow out the tone mapping
        if (m.emissiveIntensity !== undefined && m.emissiveIntensity > 4) m.emissiveIntensity = 4;
        for (const key of ['map', 'emissiveMap']) {
          if (m[key]) m[key].anisotropy = 4;
        }
      }
    });
  }

  /**
   * Hand the table manager the real objects, so it stops building its own
   * furniture and drives yours instead. Everything downstream - clicks,
   * the panel, the assistant, the reservation - is unchanged.
   */
  attach(tableManager) {
    tableManager.useNodes(this.tables, this.lamps, this.seats);
  }

  update(dt) {
    if (this.mixer) this.mixer.update(dt);
  }

  dispose() {
    if (!this.root) return;
    this.root.traverse((o) => {
      if (o.isMesh) {
        o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        for (const m of mats) if (m) m.dispose();
      }
    });
    this.root.parent && this.root.parent.remove(this.root);
  }
}
