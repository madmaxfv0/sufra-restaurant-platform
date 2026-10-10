import * as THREE from '/static/vendor/three/three.module.js';
import { clone as cloneSkinned } from '/static/vendor/three/jsm/utils/SkeletonUtils.js';

/**
 * Guests and waiters.
 *
 * Rigged characters (GLB with a skeleton) plus animation clips, described in
 * static/3d/models/humans/manifest.json. Each occupied table receives as
 * many seated guests as the live feed reports, each with its own clip,
 * speed and start offset so nothing synchronises. Waiters walk the venue's
 * pre-drawn walk paths (the same ones the 2D map used), never through
 * furniture, because the paths were drawn around it.
 *
 * Without a manifest the system is inert. It never throws into the scene.
 */
export class GuestSystem {
  constructor(scene, assets, quality) {
    this.scene = scene; this.assets = assets; this.quality = quality;
    this.pool = [];         // [{root, clips:{name: AnimationClip}}]
    this.guests = {};       // tableId -> [{obj, mixer}]
    this.waiters = [];
    // {x, z, r} circles a walker may not enter: tables, planters, the bar,
    // the pass, the wc block. Filled by setObstacles() once the room is built.
    this.obstacles = [];
    this.enabled = false;
    this.group = new THREE.Group(); this.group.name = 'people';
    scene.add(this.group);
  }

  async load() {
    if (this.quality === 'smooth') return false;      // every other tier gets people
    let manifest;
    try {
      const r = await fetch('/static/3d/models/humans/manifest.json', { cache: 'no-store' });
      if (!r.ok) return false;
      manifest = await r.json();
    } catch (e) { return false; }
    const chars = manifest.characters || [];
    for (const c of chars) {
      try {
        const g = await this.assets.gltf.loadAsync('/static/3d/models/humans/' + c.file);
        const root = g.scene;
        root.traverse(o => { if (o.isMesh) { o.castShadow = true; o.frustumCulled = false; } });
        const clips = {};
        for (const clip of g.animations || []) clips[clip.name] = clip;
        // external clips, retargeted onto this character's skeleton
        for (const [key, file] of Object.entries(c.animations || {})) {
          try {
            const a = await this.assets.gltf.loadAsync('/static/3d/animations/humans/' + file);
            for (const clip of a.animations || []) {
              // a file with one clip is stored under the manifest key; a file with
              // several (a Mixamo pack) keeps each clip's own name, so "Walk" and
              // "Idle" from one download both become available
              const name = a.animations.length === 1 ? key : clip.name;
              const fitted = this.retarget(clip, root);
              if (fitted) clips[name] = fitted;
            }
          } catch (e) { this.assets.log.warn('[people] animation missing: ' + file); }
        }
        const box = new THREE.Box3().setFromObject(root);
        const size = new THREE.Vector3(); box.getSize(size);
        this.pool.push({ root, clips, box, size, height: c.height || 1.7 });
      } catch (e) { this.assets.log.warn('[people] ' + c.file + ' failed: ' + e.message); }
    }
    this.enabled = this.pool.length > 0;
    return this.enabled;
  }

  pick(i) { return this.pool[i % this.pool.length]; }

  /**
   * Make a clip drive THIS skeleton.
   *
   * Every Mixamo-derived rig uses the same bone names, but some exporters keep
   * the "mixamorig" prefix and some strip it. A clip from one will not bind to
   * the other until the track names match, so this tries both spellings.
   * Position tracks are dropped: they carry the source rig's own units and
   * would shove a different character through the floor. Rotation is what a
   * walk or a sit actually is; the site moves the character along its path.
   */
  retarget(clip, root) {
    const bones = new Set();
    root.traverse(o => { if (o.isBone) bones.add(o.name); });
    if (!bones.size) return null;
    const hasPrefix = [...bones].some(n => n.startsWith('mixamorig'));
    const out = clip.clone();
    const tracks = [];
    for (const t of out.tracks) {
      const dot = t.name.indexOf('.');
      let bone = t.name.slice(0, dot), prop = t.name.slice(dot);
      if (prop === '.position') continue;
      // Drop the hips' own rotation. Mixamo bakes the armature's Z-up-to-Y-up
      // correction into the root bone's quaternion, and this character was
      // exported with that correction already applied to its rest pose - so
      // replaying the track applied it twice and laid every walker out flat in
      // mid-air, rotated 90 degrees about X at hip height. Every other bone is
      // relative to its parent and retargets cleanly; losing the hip sway costs
      // a little swagger and nothing else.
      if (prop === '.quaternion' && /hips?$/i.test(bone)) continue;
      if (prop === '.scale') continue;      // Mixamo exports these as constant 1
      if (!bones.has(bone)) {
        const alt = hasPrefix ? 'mixamorig' + bone.replace(/^mixamorig/, '') : bone.replace(/^mixamorig/, '');
        if (!bones.has(alt)) continue;
        bone = alt;
      }
      t.name = bone + prop;
      tracks.push(t);
    }
    if (!tracks.length) { this.assets.log.warn('[people] clip "' + clip.name + '" matched no bones on this character'); return null; }
    out.tracks = tracks;
    out.resetDuration();
    return out;
  }

  /** seat `count` guests around a table; chairs: [{pos:Vector3, yaw:number}] */
  seat(tableId, chairs, count) {
    this.clear(tableId);
    if (!this.enabled || !count) return;
    const list = [];
    chairs.slice(0, count).forEach((ch, i) => {
      const P = this.pick(tableId.charCodeAt(1) + i * 3 + tableId.length);
      const obj = cloneSkinned(P.root);
      // seated guests were never passed through vary(), so a full room was one
      // avatar in one outfit repeated at every chair
      obj.scale.setScalar(P.height / P.size.y);
      this.vary(obj, tableId.charCodeAt(1) * 3 + i);
      const sc = obj.scale.y;
      obj.position.set(ch.pos.x, ch.pos.y - P.box.min.y * sc, ch.pos.z);
      obj.rotation.y = ch.yaw;
      const mixer = new THREE.AnimationMixer(obj);
      const names = Object.keys(P.clips);
      const seated = names.filter(n => /sit/i.test(n));
      if (!seated.length) return;                 // no sitting clip yet: walkers only
      const pickName = seated[(i * 7 + tableId.length) % seated.length];
      if (pickName) {
        const action = mixer.clipAction(P.clips[pickName]);
        action.time = Math.random() * P.clips[pickName].duration;    // desynchronised start
        action.timeScale = 0.85 + Math.random() * 0.3;
        action.play();
      }
      this.group.add(obj);
      list.push({ obj, mixer, P, nextSwap: 8 + Math.random() * 14, elapsed: 0 });
    });
    this.guests[tableId] = list;
  }

  clear(tableId) {
    for (const g of this.guests[tableId] || []) this.group.remove(g.obj);
    delete this.guests[tableId];
  }

  /**
   * People walking the venue's pre-drawn paths. The paths were traced around
   * the furniture, so nobody ever walks through a table.
   *
   * @param paths [[x,z],...][] in metres
   * @param count how many walkers in total, spread across the paths
   * @param opts  { speed, seed, bothWays } - staff move at about 0.55 m/s,
   *              strolling guests nearer 0.9 m/s
   */
  addWalkers(paths, count, opts) {
    if (!this.enabled || !paths.length) return;
    const o = opts || {};
    const speed = o.speed || 0.55;
    const seed = o.seed || 0;
    for (let i = 0; i < count; i++) {
      const path = paths[(i + seed) % paths.length];
      if (!path || path.length < 2) continue;
      const P = this.pick(i + seed + 5);
      const obj = cloneSkinned(P.root);
      // setScalar has to come first: vary() MULTIPLIES the scale, so calling it
      // beforehand meant setScalar overwrote every bit of height variation and
      // the whole promenade walked at exactly 1.74 m.
      obj.scale.setScalar(P.height / P.size.y);
      this.vary(obj, i + seed, o.clothing);
      const sc = obj.scale.y;                 // after variation, so feet still land
      const mixer = new THREE.AnimationMixer(obj);
      const walk = Object.keys(P.clips).find(n => /walk/i.test(n));
      if (walk) {
        const a = mixer.clipAction(P.clips[walk]);
        a.time = Math.random() * P.clips[walk].duration;      // nobody in step with anybody
        a.timeScale = 0.85 + Math.random() * 0.3;
        a.play();
      }
      this.group.add(obj);
      this.waiters.push({
        obj, mixer, path,
        u: Math.random(),
        speed: speed * (0.85 + Math.random() * 0.3),
        yOff: -P.box.min.y * sc,
        dir: o.bothWays && i % 2 ? -1 : 1,
      });
    }
  }

  /**
   * One character file, many people. Clothing meshes get their own tinted
   * material per clone; skin, hair and eyes are left alone. Scale varies a few
   * percent. It is what stops a promenade of one avatar looking like clones.
   */
  vary(obj, seed, mode) {
    const h = (n) => { const x = Math.sin(seed * 127.1 + n * 311.7) * 43758.5453; return x - Math.floor(x); };
    const palette = [0x2f3a55, 0x6b2f2f, 0x2c4a3b, 0x8a7358, 0x3b3b40, 0x5b3d63, 0x334d6e, 0x7a5a3a,
                     0xb8b0a2, 0x1f2833, 0x7d8c6f, 0xa8443a, 0xd8cdb8];
    // Indoor walkers are staff, not diners (see Sufra360.js: the promenade
    // gets the varied palette above, the dining-room walkers get this one) -
    // a consistent white shirt over black trousers/apron, the way a working
    // front-of-house team actually dresses, rather than each waiter in a
    // different bright colour. Small variation is still allowed within it:
    // a near-white vs pure white shirt, an apron or a waistcoat.
    const isStaff = mode === 'staff';
    const staffTop = [0xf7f4ea, 0xffffff, 0xefece0, 0xfbfaf5];
    const staffBottom = [0x121214, 0x18181a, 0x0e0e10];
    // +-5% was not enough to break the read of one avatar repeated: adults run
    // roughly 1.55-1.90 m, so vary the height over that and let the build vary
    // a little independently of it. Only the crowd is affected - seated guests
    // and walkers both come through here.
    const hgt = 0.90 + h(1) * 0.20;
    obj.scale.multiplyScalar(hgt);
    obj.scale.x *= 0.94 + h(6) * 0.13;
    obj.scale.z *= 0.94 + h(7) * 0.13;
    obj.traverse(m => {
      if (!m.isMesh || !m.material) return;
      const name = (m.name + ' ' + (m.material.name || '')).toLowerCase();
      // "body" is the clothed torso mesh on this character, not bare skin -
      // tinting it as a complexion put walkers on the promenade in what looked
      // like their underwear. Leave it to the clothing branches below.
      if (/eye|teeth/.test(name)) return;
      // skin and hair keep their own maps but shift tone, so the crowd is not
      // one complexion; the clothing branches below still do the heavy lifting
      if (/skin|head|face|hair/.test(name) && !/body|shirt|top|cloth/.test(name)) {
        const mat = m.material.clone();
        if (mat.color) {
          const warm = new THREE.Color().setHSL(0.06 + h(8) * 0.03, 0.32 + h(9) * 0.20, 0.28 + h(10) * 0.34);
          mat.color = mat.color.clone().lerp(warm, /hair/.test(name) ? 0.55 : 0.30);
        }
        m.material = mat;
        return;
      }
      const mat = m.material.clone();
      const isShoe = /shoe|foot/.test(name);
      const isBottom = /bottom|pants/.test(name);
      const isTop = /top|shirt|jacket|outfit|cloth|wear/.test(name) || (!isBottom && !isShoe);
      if (isStaff) {
        // A hard set, not a lerp toward: the guest tint above is a subtle
        // colour-wash over whatever the source texture already is, which
        // would leave a bright printed pattern showing through. Staff need
        // to read as uniformly black-and-white regardless of the source
        // character's original outfit colour, so this replaces it outright.
        if (isShoe) mat.color = new THREE.Color(0x0c0c0d);
        else if (isBottom) mat.color = new THREE.Color(staffBottom[Math.floor(h(3) * staffBottom.length)]);
        else if (isTop) mat.color = new THREE.Color(staffTop[Math.floor(h(2) * staffTop.length)]);
      } else if (isTop) {
        mat.color = mat.color ? mat.color.clone().lerp(new THREE.Color(palette[Math.floor(h(2) * palette.length)]), 0.7) : mat.color;
      } else if (isBottom) {
        mat.color = mat.color ? mat.color.clone().lerp(new THREE.Color(palette[Math.floor(h(3) * palette.length)]), 0.6) : mat.color;
      }
      m.material = mat;
    });
  }

  /** register the solid things walkers must go around */
  setObstacles(list) { this.obstacles = list || []; }

  /** kept so older code keeps working */
  addWaiters(paths, count) { this.addWalkers(paths, count, { speed: 0.55 }); }

  update(dt) {
    if (!this.enabled) return;
    for (const id in this.guests) for (const g of this.guests[id]) {
      g.mixer.update(dt);
      g.elapsed += dt;
      if (g.elapsed > g.nextSwap) {                       // occasionally change what they are doing
        g.elapsed = 0; g.nextSwap = 10 + Math.random() * 18;
        const names = Object.keys(g.P.clips).filter(n => /sit/i.test(n));
        if (names.length > 1) {
          const next = names[Math.floor(Math.random() * names.length)];
          const a = g.mixer.clipAction(g.P.clips[next]);
          g.mixer.stopAllAction(); a.reset().fadeIn(0.8).play();
        }
      }
    }
    for (const w of this.waiters) {
      w.mixer.update(dt);
      const p = w.path, n = p.length - 1;
      const total = this.pathLength(p);
      w.u += w.dir * (w.speed * dt) / Math.max(1, total);
      if (w.u >= 1) { w.u = 1; w.dir = -1; } else if (w.u <= 0) { w.u = 0; w.dir = 1; }
      const f = w.u * n, i = Math.min(n - 1, Math.floor(f)), k = f - i;
      const x = p[i][0] + (p[i + 1][0] - p[i][0]) * k, z = p[i][1] + (p[i + 1][1] - p[i][1]) * k;
      const dx = (p[i + 1][0] - p[i][0]) * w.dir, dz = (p[i + 1][1] - p[i][1]) * w.dir;
      // Push out of anything solid before committing the step. The paths are
      // waypoints down the middle of the circulation space, but tables, chairs
      // and planters sit close enough to them that a walker would clip a
      // corner; this slides them around the obstacle rather than through it.
      let px = x, pz = z;
      for (const o of (this.obstacles || [])) {
        const ox = px - o.x, oz = pz - o.z;
        const d = Math.hypot(ox, oz);
        if (d < o.r && d > 1e-4) { const k = o.r / d; px = o.x + ox * k; pz = o.z + oz * k; }
      }
      w.obj.position.set(px, 0.1 + w.yOff, pz);
      w.obj.rotation.y = Math.atan2(dx, dz);
    }
  }

  pathLength(p) {
    if (p._len) return p._len;
    let L = 0; for (let i = 1; i < p.length; i++) L += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
    return (p._len = L);
  }
}
