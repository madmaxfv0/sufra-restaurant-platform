import * as THREE from '/static/vendor/three/three.module.js';
import { GLTFLoader } from '/static/vendor/three/jsm/loaders/GLTFLoader.js';

function cloneRig(source) {
  const clone = source.clone(true);
  const sourceToClone = new Map();
  const cloneToSource = new Map();

  const pair = (a, b) => {
    sourceToClone.set(a, b);
    cloneToSource.set(b, a);
    const n = Math.min(a.children.length, b.children.length);
    for (let i = 0; i < n; i++) pair(a.children[i], b.children[i]);
  };

  pair(source, clone);

  clone.traverse((node) => {
    if (!node.isSkinnedMesh) return;
    const original = cloneToSource.get(node);
    if (!original?.skeleton) return;

    const skeleton = original.skeleton.clone();
    skeleton.bones = original.skeleton.bones.map(
      (bone) => sourceToClone.get(bone)
    );

    node.bindMatrix.copy(original.bindMatrix);
    node.bind(skeleton, node.bindMatrix);
  });

  return clone;
}

export class ClothedPeopleSystem {
  constructor(scene, venue, quality = 'high') {
    this.scene = scene;
    this.venue = venue;
    this.quality = quality;

    this.group = new THREE.Group();
    this.group.name = 'sufra-clothed-rigged-people-v6';
    this.scene.add(this.group);

    const map = venue.map;
    this.u = Number(map.units_to_m || 0.05);
    this.mapW = Number(map.width || 720);
    this.mapH = Number(map.height || 1280);

    this.loader = new GLTFLoader();
    this.templates = [];
    this.people = [];
    this._seed = 0x510e527f;
  }

  X(mx) { return (Number(mx) - this.mapW / 2) * this.u; }
  Z(my) { return (Number(my) - this.mapH / 2) * this.u; }

  rand() {
    this._seed = (1664525 * this._seed + 1013904223) >>> 0;
    return this._seed / 4294967296;
  }

  async loadManifest() {
    const r = await fetch(
      '/static/models/clothed_people/manifest.json?v=6',
      { cache: 'no-store' }
    );
    if (!r.ok) {
      throw new Error(
        `Clothed people manifest could not load: HTTP ${r.status}`
      );
    }
    this.manifest = await r.json();
  }

  findClip(clips, preferred, fallbacks) {
    const lower = new Map(
      (clips || []).map((c) => [c.name.toLowerCase(), c])
    );

    if (preferred) {
      const exact = lower.get(String(preferred).toLowerCase());
      if (exact) return exact;
    }

    for (const word of fallbacks) {
      const w = word.toLowerCase();
      const exact = lower.get(w);
      if (exact) return exact;

      for (const clip of clips || []) {
        if (clip.name.toLowerCase().includes(w)) return clip;
      }
    }

    return null;
  }

  async loadAssets() {
    await this.loadManifest();

    const chars = this.manifest.characters || [];
    if (!chars.length) {
      throw new Error('No clothed character models in V6 manifest.');
    }

    for (let i = 0; i < chars.length; i++) {
      const cfg = chars[i];
      const gltf = await this.loader.loadAsync(cfg.url);

      gltf.scene.traverse((node) => {
        if (node.isLight || node.isCamera) node.visible = false;

        if (node.isMesh) {
          node.castShadow = true;
          node.receiveShadow = true;
          node.frustumCulled = true;

          // Keep authored textures/materials but improve scene response.
          const mats = Array.isArray(node.material)
            ? node.material
            : [node.material];

          for (const m of mats) {
            if (!m) continue;
            if ('roughness' in m && m.roughness == null) m.roughness = 0.8;
          }
        }
      });

      const clips = gltf.animations || [];
      const walk = this.findClip(
        clips,
        cfg.walk,
        ['walk_loop', 'walking', 'walk']
      );
      const idle = this.findClip(
        clips,
        cfg.idle,
        ['idle_loop', 'idle']
      );

      if (!walk) {
        console.warn(
          `[SUFRA V6] Skip ${cfg.name}: walk animation missing`
        );
        continue;
      }

      this.templates.push({
        cfg,
        scene: gltf.scene,
        walk,
        idle: idle || walk,
      });
    }

    if (!this.templates.length) {
      throw new Error(
        'V6 models loaded but none has a usable walk animation.'
      );
    }

    console.info(
      `[SUFRA V6] ${this.templates.length} clothed character templates ready`
    );
  }

  buildRoutes(promenade) {
    const [mx1, my1, mx2, my2] = promenade;

    this.zMin = this.Z(my1) + 1.9;
    this.zMax = this.Z(my2) - 1.9;

    const xSea = this.X(mx1 + 16);
    const xSeaMid = this.X(mx1 + 29);
    const xInnerMid = this.X(mx2 - 29);
    const xInner = this.X(mx2 - 15);

    const z20 = THREE.MathUtils.lerp(this.zMin, this.zMax, 0.20);
    const z36 = THREE.MathUtils.lerp(this.zMin, this.zMax, 0.36);
    const z62 = THREE.MathUtils.lerp(this.zMin, this.zMax, 0.62);
    const z82 = THREE.MathUtils.lerp(this.zMin, this.zMax, 0.82);

    this.routes = [
      [
        new THREE.Vector3(xSea, 0, this.zMin),
        new THREE.Vector3(xSea, 0, this.zMax),
      ],
      [
        new THREE.Vector3(xInner, 0, this.zMax),
        new THREE.Vector3(xInner, 0, this.zMin),
      ],
      [
        new THREE.Vector3(xSeaMid, 0, this.zMin),
        new THREE.Vector3(xInnerMid, 0, z36),
        new THREE.Vector3(xSeaMid, 0, z62),
        new THREE.Vector3(xInnerMid, 0, this.zMax),
      ],
      [
        new THREE.Vector3(xInnerMid, 0, this.zMax),
        new THREE.Vector3(xSeaMid, 0, z82),
        new THREE.Vector3(xInnerMid, 0, z36),
        new THREE.Vector3(xSeaMid, 0, this.zMin),
      ],
      [
        new THREE.Vector3(xSea, 0, z20),
        new THREE.Vector3(xInner, 0, z36),
        new THREE.Vector3(xInnerMid, 0, z62),
        new THREE.Vector3(xSeaMid, 0, z82),
        new THREE.Vector3(xSea, 0, z20),
      ],
    ];
  }

  getRoutePoint(p, index) {
    const max = p.route.length - 1;
    let i = THREE.MathUtils.clamp(index, 0, max);
    if (p.reverse) i = max - i;
    return p.route[i];
  }

  fitModel(model, targetHeight, forwardOffset = 0) {
    model.rotation.y = Number(forwardOffset || 0);
    model.updateMatrixWorld(true);

    let box = new THREE.Box3().setFromObject(model);
    const height = Math.max(0.01, box.max.y - box.min.y);

    model.scale.setScalar(targetHeight / height);
    model.updateMatrixWorld(true);

    box = new THREE.Box3().setFromObject(model);
    model.position.y -= box.min.y;
    model.updateMatrixWorld(true);
  }

  makePerson(template, targetHeight, index) {
    const root = new THREE.Group();
    root.name = `clothed_person_${index}`;

    const model = cloneRig(template.scene);
    model.name = `clothed_model_${index}`;

    this.fitModel(
      model,
      targetHeight,
      template.cfg.forward_offset || 0
    );
    root.add(model);

    const mixer = new THREE.AnimationMixer(model);

    const walkAction = mixer.clipAction(template.walk);
    const idleAction = mixer.clipAction(template.idle);

    walkAction.setLoop(THREE.LoopRepeat, Infinity);
    idleAction.setLoop(THREE.LoopRepeat, Infinity);

    walkAction.play();
    idleAction.play();

    walkAction.setEffectiveWeight(1);
    idleAction.setEffectiveWeight(0);

    walkAction.setEffectiveTimeScale(
      0.88 + this.rand() * 0.20
    );
    idleAction.setEffectiveTimeScale(
      0.88 + this.rand() * 0.18
    );

    if (template.walk.duration > 0) {
      walkAction.time = this.rand() * template.walk.duration;
    }

    return {
      root,
      model,
      mixer,
      walkAction,
      idleAction,
      state: 'walk',
      template,
    };
  }

  setState(p, state) {
    if (p.state === state) return;

    const fade = 0.22;

    if (state === 'idle') {
      p.walkAction.fadeOut(fade);
      p.idleAction
        .reset()
        .setEffectiveWeight(1)
        .fadeIn(fade)
        .play();
    } else {
      p.idleAction.fadeOut(fade);
      p.walkAction
        .reset()
        .setEffectiveWeight(1)
        .fadeIn(fade)
        .play();
    }

    p.state = state;
  }

  async build(promenade) {
    await this.loadAssets();
    this.buildRoutes(promenade);

    const count =
      this.quality === 'ultra' ? 14 :
      this.quality === 'high' ? 11 : 8;

    for (let i = 0; i < count; i++) {
      const template =
        this.templates[i % this.templates.length];

      const isFemale =
        String(template.cfg.gender).toLowerCase() === 'female';

      const targetHeight = isFemale
        ? 1.56 + this.rand() * 0.20
        : 1.64 + this.rand() * 0.22;

      const p = this.makePerson(
        template,
        targetHeight,
        i
      );

      p.route = this.routes[i % this.routes.length];
      p.reverse = (i % 2) === 1;
      p.segment = 0;
      p.progress = this.rand() * 0.88;
      p.speed = 0.68 + this.rand() * 0.38;
      p.pause = 0;
      p.pauseChance = 0.20 + this.rand() * 0.24;
      p.lateral = (this.rand() - 0.5) * 0.23;

      const a = this.getRoutePoint(p, 0);
      const b = this.getRoutePoint(p, 1);

      p.root.position.copy(a).lerp(b, p.progress);
      p.root.position.y = 0.06;
      p.root.rotation.y =
        Math.atan2(b.x - a.x, b.z - a.z);

      this.people.push(p);
      this.group.add(p.root);
    }

    console.info(
      `[SUFRA V6] ${this.people.length} clothed walkers active`
    );

    return this;
  }

  nextSegment(p) {
    const last = p.route.length - 2;
    p.segment += 1;
    p.progress = 0;

    if (p.segment > last) {
      p.reverse = !p.reverse;
      p.segment = 0;

      if (this.rand() < p.pauseChance) {
        p.pause = 0.4 + this.rand() * 1.5;
      }
    }
  }

  crowdSlowdown(p) {
    let factor = 1;

    for (const other of this.people) {
      if (other === p) continue;

      const dx = other.root.position.x - p.root.position.x;
      const dz = other.root.position.z - p.root.position.z;
      const d2 = dx * dx + dz * dz;

      if (d2 < 0.38) {
        factor = Math.min(factor, 0.25);
      } else if (d2 < 0.75) {
        factor = Math.min(factor, 0.60);
      } else if (d2 < 1.12) {
        factor = Math.min(factor, 0.84);
      }
    }

    return factor;
  }

  updateOne(p, dt, rain) {
    if (p.pause > 0) {
      p.pause -= dt;
      this.setState(p, 'idle');
      p.mixer.update(dt);
      return;
    }

    this.setState(p, 'walk');

    const a = this.getRoutePoint(p, p.segment);
    const b = this.getRoutePoint(p, p.segment + 1);

    const length = Math.max(
      0.15,
      a.distanceTo(b)
    );

    p.progress +=
      (
        p.speed *
        this.crowdSlowdown(p) *
        (1 + rain * 0.16) *
        dt
      ) /
      length;

    if (p.progress >= 1) {
      this.nextSegment(p);
    }

    const aa = this.getRoutePoint(p, p.segment);
    const bb = this.getRoutePoint(p, p.segment + 1);

    const pos = aa.clone().lerp(
      bb,
      THREE.MathUtils.clamp(p.progress, 0, 1)
    );

    const dx = bb.x - aa.x;
    const dz = bb.z - aa.z;
    const len = Math.max(0.001, Math.hypot(dx, dz));

    const px = -dz / len;
    const pz = dx / len;

    p.root.position.x = pos.x + px * p.lateral;
    p.root.position.z = pos.z + pz * p.lateral;

    const desired = Math.atan2(dx, dz);
    let d = desired - p.root.rotation.y;
    d = Math.atan2(Math.sin(d), Math.cos(d));

    p.root.rotation.y +=
      d * Math.min(1, dt * 5.8);

    p.mixer.update(dt);
  }

  update(dt, t, weather = null) {
    const rain = Math.max(
      0,
      Number(weather?.rain || 0)
    );

    for (const p of this.people) {
      this.updateOne(p, dt, rain);
    }
  }
}
