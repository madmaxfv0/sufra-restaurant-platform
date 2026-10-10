import * as THREE from '/static/vendor/three/three.module.js';
import { OrbitControls } from '/static/vendor/three/jsm/controls/OrbitControls.js';
import { EffectComposer } from '/static/vendor/three/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from '/static/vendor/three/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from '/static/vendor/three/jsm/postprocessing/UnrealBloomPass.js';
import { SMAAPass } from '/static/vendor/three/jsm/postprocessing/SMAAPass.js';
import { OutputPass } from '/static/vendor/three/jsm/postprocessing/OutputPass.js';

/**
 * Owns the renderer, the scene, the camera and the frame loop.
 *
 * Build 9 changes, all for smoothness on a laptop:
 *  - the post-processing chain (bloom) only exists on High / Ultra; Balanced
 *    and Smooth render straight to the canvas with hardware MSAA, which is
 *    nearly free on Apple GPUs, and get their lamp glow from HaloSystem
 *  - adaptive resolution: if the frame rate sags the pixel ratio steps down
 *    (never below 0.8), and creeps back up when there is headroom
 *  - shadow map type follows the tier (soft PCF is the expensive one)
 *  - nothing in the loop touches the DOM
 */
export class SceneManager {
  constructor(canvas, quality, Q) {
    this.quality = quality;
    this.Q = Q;
    this.renderer = new THREE.WebGLRenderer({
      canvas, antialias: !Q.composer, powerPreference: 'high-performance',
      stencil: false, alpha: false, depth: true,
    });
    this.dprCap = Math.min(window.devicePixelRatio || 1, Q.dpr);
    this.dpr = this.dprCap;
    this.renderer.setPixelRatio(this.dpr);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.95;
    this.renderer.shadowMap.enabled = Q.shadow > 0;
    this.renderer.shadowMap.type = Q.softShadow ? THREE.PCFSoftShadowMap : THREE.PCFShadowMap;
    this.renderer.setClearColor(0x070c16, 1);

    this.scene = new THREE.Scene();
    // far reaches past the Baku skyline at ~780 m. near stays at 0.5 rather than
    // going lower, because the near/far ratio is what costs depth precision and
    // z-fighting on the tabletops would be far more visible than a clipped city.
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.5, 2200);

    this.composer = null;
    if (Q.composer) {
      this.composer = new EffectComposer(this.renderer);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      // subtle: lamps and the water sparkle bloom, walls do not
      this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), Q.bloomStrength || 0.22, 0.55, 0.86);
      this.composer.addPass(this.bloom);
      if (Q.smaa) this.composer.addPass(new SMAAPass(1, 1));
      this.composer.addPass(new OutputPass());
    }

    this.clock = new THREE.Clock();
    this.tickers = [];
    this.building = false;                 // the app sets this while it adds objects
    this.adaptive = !!Q.adaptive;
    this._frames = 0; this._acc = 0; this._cool = 0; this._warm = 4;
    this.onAdapt = null;
    this.fps = 60;
    this.resize();
    let raf = 0;
    window.addEventListener('resize', () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => this.resize()); });
  }

  resize() {
    const el = this.renderer.domElement;
    const w = el.clientWidth || window.innerWidth, h = el.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    if (this.composer) this.composer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  setDpr(v) {
    v = Math.max(0.75, Math.min(this.dprCap, v));
    if (Math.abs(v - this.dpr) < 0.01) return;
    this.dpr = v;
    this.renderer.setPixelRatio(v);
    if (this.composer) this.composer.setPixelRatio(v);
    this.resize();
    if (this.onAdapt) this.onAdapt(v);
  }

  onTick(fn) { this.tickers.push(fn); }

  render() {
    if (this.composer) this.composer.render(); else this.renderer.render(this.scene, this.camera);
  }

  start() {
    if (this._running) return;
    this._running = true;
    const loop = () => {
      requestAnimationFrame(loop);
      if (document.hidden) return;
      const dt = Math.min(0.05, this.clock.getDelta());
      const t = this.clock.elapsedTime;
      for (const f of this.tickers) { try { f(dt, t); } catch (e) { this._tickErr(e); } }
      this.render();
      this._adapt(dt);
    };
    loop();
  }

  _tickErr(e) {
    // one report per distinct message, never a flood, never a dead loop
    this._errs = this._errs || new Set();
    const k = (e && e.message) || String(e);
    if (this._errs.has(k)) return;
    this._errs.add(k);
    console.error('[SUFRA 360 tick]', e);
    if (this.onTickError) this.onTickError(e);
  }

  /** adaptive resolution: measured over ~1.5 s windows, with a cooldown so it never oscillates */
  _adapt(dt) {
    this._acc += dt; this._frames += 1;
    if (this._acc < 1.5) return;
    this.fps = this._frames / this._acc;
    this._acc = 0; this._frames = 0;
    if (!this.adaptive || this.building) return;
    if (this._warm > 0) { this._warm -= 1; return; }          // ignore the first seconds (shaders compiling)
    if (this._cool > 0) { this._cool -= 1; return; }
    if (this.fps < 40 && this.dpr > 0.8) { this.setDpr(this.dpr - 0.15); this._cool = 2; }
    else if (this.fps > 57 && this.dpr < this.dprCap) { this.setDpr(this.dpr + 0.1); this._cool = 3; }
  }
}

// ------------------------------------------------------------------ camera
export class CameraController {
  static MOVE_KEYS = new Set(['w', 'a', 's', 'd', 'q', 'e', 'r', 'f', 'Shift',
                              'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']);

  constructor(camera, dom, bounds) {
    this.camera = camera;
    this.bounds = bounds;                 // {minX,maxX,minZ,maxZ}
    const c = this.controls = new OrbitControls(camera, dom);
    c.enableDamping = true; c.dampingFactor = 0.07;
    c.minPolarAngle = 0.20;               // never straight down
    c.maxPolarAngle = 1.14;               // never below ~65 deg from vertical: no flying under
    c.minDistance = 4.5; c.maxDistance = 78;
    c.enablePan = true; c.screenSpacePanning = false;
    c.zoomSpeed = 0.75; c.rotateSpeed = 0.55; c.panSpeed = 0.6;
    c.maxTargetRadius = Infinity;
    this.glide = null;
    this.overview = null;
    this.idle = false;                    // slow cinematic orbit behind the entry screen
    this.idleAz = 0;

    // Walk the room: W/S or up/down move the camera along its own view
    // direction, A/D or left/right strafe across it, Q/E and R/F change
    // height. Orbit-drag alone could only circle a fixed point, so there was
    // no way to simply move down the room. Shift is a run modifier.
    this.keys = new Set();
    this.moveSpeed = 9;                   // metres per second, walking pace
    const track = (e, down) => {
      // never steal typing from the Ask bar or the booking drawer
      const t = e.target;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
                t.tagName === 'SELECT' || t.isContentEditable)) return;
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      if (!CameraController.MOVE_KEYS.has(k)) return;
      e.preventDefault();
      if (down) this.keys.add(k); else this.keys.delete(k);
      if (down) { this.idle = false; this.glide = null; }
    };
    this._onKeyDown = (e) => track(e, true);
    this._onKeyUp = (e) => track(e, false);
    addEventListener('keydown', this._onKeyDown);
    addEventListener('keyup', this._onKeyUp);
    // a lost keyup (tab away mid-press) would otherwise leave the camera drifting
    addEventListener('blur', () => this.keys.clear());
  }

  /** Pan the camera and its orbit target together, so orbiting still works
   *  around wherever you have walked to. */
  walk(dt) {
    if (!this.keys.size) return false;
    const k = this.keys;
    let fwd = (k.has('w') || k.has('ArrowUp') ? 1 : 0) - (k.has('s') || k.has('ArrowDown') ? 1 : 0);
    let side = (k.has('d') || k.has('ArrowRight') ? 1 : 0) - (k.has('a') || k.has('ArrowLeft') ? 1 : 0);
    let vert = (k.has('e') || k.has('r') ? 1 : 0) - (k.has('q') || k.has('f') ? 1 : 0);
    if (!fwd && !side && !vert) return false;

    const speed = this.moveSpeed * (k.has('Shift') ? 2.4 : 1) * (dt || 0.016);
    // forward is the view direction flattened to the floor, so W walks across
    // the room rather than burrowing into it when the camera is looking down
    const dir = new THREE.Vector3();
    this.camera.getWorldDirection(dir);
    dir.y = 0;
    if (dir.lengthSq() < 1e-6) dir.set(0, 0, -1);
    dir.normalize();
    const right = new THREE.Vector3().crossVectors(dir, new THREE.Vector3(0, 1, 0)).normalize();

    const step = new THREE.Vector3()
      .addScaledVector(dir, fwd * speed)
      .addScaledVector(right, side * speed);
    step.y = vert * speed;
    this.camera.position.add(step);
    this.controls.target.add(step);
    return true;
  }

  /** The reference-image opening shot: high, slightly rotated, restaurant filling the frame. */
  setOverview(centerX, centerZ, extent) {
    const dist = extent * 1.02;
    const polar = 0.50;                   // ~29 deg from vertical => ~61 deg down, like the reference
    const az = -0.35;
    const pos = new THREE.Vector3(
      centerX + Math.sin(polar) * Math.sin(az) * dist,
      Math.cos(polar) * dist,
      centerZ + Math.sin(polar) * Math.cos(az) * dist);
    this.overview = { pos, target: new THREE.Vector3(centerX, 0, centerZ), dist, polar, az };
    this.camera.position.copy(pos);
    this.controls.target.copy(this.overview.target);
    this.controls.update();
  }

  /** the establishing shot behind the brand: higher, wider, drifting slowly */
  startIdle() {
    if (!this.overview) return;
    this.idle = true;
    this.idleAz = this.overview.az - 0.25;
    this._placeIdle();
  }

  _placeIdle() {
    const o = this.overview, d = o.dist * 1.22, p = 0.46;
    this.camera.position.set(
      o.target.x + Math.sin(p) * Math.sin(this.idleAz) * d,
      Math.cos(p) * d,
      o.target.z + Math.sin(p) * Math.cos(this.idleAz) * d);
    this.controls.target.copy(o.target);
  }

  stopIdle() { this.idle = false; }

  flyTo(target, distance, polar, azimuth, ms) {
    const t = target.clone();
    const p = polar == null ? 0.78 : polar;
    const a = azimuth == null ? this.currentAzimuth() : azimuth;
    const pos = new THREE.Vector3(
      t.x + Math.sin(p) * Math.sin(a) * distance,
      t.y + Math.cos(p) * distance,
      t.z + Math.sin(p) * Math.cos(a) * distance);
    this.glide = { fromPos: this.camera.position.clone(), fromTgt: this.controls.target.clone(),
                   toPos: pos, toTgt: t, start: performance.now(), ms: ms || 1600 };
  }

  toOverview(ms) {
    if (!this.overview) return;
    this.glide = { fromPos: this.camera.position.clone(), fromTgt: this.controls.target.clone(),
                   toPos: this.overview.pos.clone(), toTgt: this.overview.target.clone(),
                   start: performance.now(), ms: ms || 1800 };
  }

  currentAzimuth() {
    const d = this.camera.position.clone().sub(this.controls.target);
    return Math.atan2(d.x, d.z);
  }

  update(dt) {
    const walked = this.walk(dt);
    if (walked) this.idle = false;
    if (this.idle) {
      this.idleAz += (dt || 0.016) * 0.045;
      this._placeIdle();
      this.controls.update();
      return;
    }
    if (this.glide) {
      const g = this.glide;
      const k = Math.min(1, (performance.now() - g.start) / g.ms);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      this.camera.position.lerpVectors(g.fromPos, g.toPos, e);
      this.controls.target.lerpVectors(g.fromTgt, g.toTgt, e);
      if (k >= 1) this.glide = null;
    }
    // keep the target on the property so the restaurant cannot be "lost"
    const b = this.bounds, t = this.controls.target;
    t.x = Math.min(b.maxX, Math.max(b.minX, t.x));
    t.z = Math.min(b.maxZ, Math.max(b.minZ, t.z));
    t.y = Math.max(0, Math.min(3, t.y));
    this.controls.update();
    if (this.camera.position.y < 1.2) this.camera.position.y = 1.2;   // never under the floor
  }

  /** user input cancels a glide so the camera never fights the hand */
  bindCancel(dom) {
    const cancel = () => { this.glide = null; this.idle = false; };
    dom.addEventListener('pointerdown', cancel);
    dom.addEventListener('wheel', cancel, { passive: true });
  }
}
