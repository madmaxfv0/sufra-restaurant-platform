import * as THREE from '/static/vendor/three/three.module.js';
import { DataAdapter as D } from './DataAdapter.js';
import { AssetManager, Materials } from './AssetManager.js';
import { SceneManager, CameraController } from './SceneManager.js';
import { RestaurantBuilder } from './RestaurantBuilder.js';
import { TableManager } from './TableManager.js';
import { FoliageSystem, WaterSystem, RainSystem } from './FoliageWaterRain.js';
import { ClothedPeopleSystem } from './ClothedPeopleSystem.js';
import { EnvironmentManager, WeatherManager } from './Environment.js';
import { GuestSystem } from './GuestSystem.js';
import { HaloSystem } from './Halos.js';
import { GLBVenue } from './GLBVenue.js';
import { BakuContext } from './BakuContext.js';
import { attributesOf, chipsOf, bestFor } from './TableInsight.js';
import { T, W, E, getLang, setLang, onLangChange, applyStatic, niceDate, LANGS } from './i18n.js';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Yield to the browser between build steps. requestAnimationFrame never fires
// in a hidden document, so a guest who opens the link in a background tab, or
// switches away while the room is loading, would otherwise sit on a loading
// screen for ever. Race it against a timer that always fires.
const nextFrame = () => new Promise((r) => {
  let done = false;
  const settle = () => { if (!done) { done = true; r(); } };
  requestAnimationFrame(settle);
  setTimeout(settle, 60);
});
const BUILD = '13';

/**
 * Quality tiers. Balanced is tuned for a MacBook in Safari: no post-processing
 * chain, hardware MSAA, PCF shadows at 1536, leaf cards without shadow casting,
 * 8 table lights + 6 lamp lights live at a time, adaptive resolution.
 */
const QUALITY = {
  ultra:    { dpr: 2,    shadow: 2048, softShadow: true,  leaves: 1.0,  leafShadows: true,  tableLights: 25, lampLights: 14, composer: true,  bloomStrength: 0.24, smaa: true,  rain: 5000, adaptive: false, people: true,  walkers: 16 },
  high:     { dpr: 1.5,  shadow: 2048, softShadow: true,  leaves: 0.85, leafShadows: true,  tableLights: 14, lampLights: 10, composer: true,  bloomStrength: 0.2,  smaa: false, rain: 3000, adaptive: true,  people: true,  walkers: 10 },
  balanced: { dpr: 1.25, shadow: 1536, softShadow: false, leaves: 0.65, leafShadows: false, tableLights: 8,  lampLights: 6,  composer: false, bloomStrength: 0,    smaa: false, rain: 1600, adaptive: true,  people: true,  walkers: 6 },
  smooth:   { dpr: 1,    shadow: 1024, softShadow: false, leaves: 0.45, leafShadows: false, tableLights: 4,  lampLights: 4,  composer: false, bloomStrength: 0,    smaa: false, rain: 800,  adaptive: true,  people: false, walkers: 0 },
};

function pickQuality() {
  const q = new URLSearchParams(location.search).get('q');
  if (q && QUALITY[q]) return q;
  try { const saved = localStorage.getItem('sufra360.quality'); if (saved && QUALITY[saved]) return saved; } catch (e) {}
  const cores = navigator.hardwareConcurrency || 4;
  const safari = /Safari/.test(navigator.userAgent) && !/Chrome|Chromium|Edg/.test(navigator.userAgent);
  // Safari's WebGL is markedly slower than Chrome's on the same Mac; start it one notch down
  if (safari) return cores >= 8 ? 'balanced' : 'smooth';
  if (cores >= 8) return 'high';
  if (cores >= 4) return 'balanced';
  return 'smooth';
}

class Sufra360 {
  constructor() {
    this.quality = pickQuality();
    this.Q = QUALITY[this.quality];
    this.notes = [];
    this.log = { warn: (...a) => { console.warn(...a); this.note(a.join(' ')); }, info: console.info };
    this.stages = [];
    this.progress = 0;
    this.lastProgress = performance.now();
    this._wx = '';
  }

  note(msg) { this.notes.push(msg); }

  // ------------------------------------------------------------------ boot
  async boot() {
    // Errors on later frames never replace a working scene with a red page: they
    // become a quiet toast plus the console. Before the renderer exists they are fatal.
    window.addEventListener('error', (e) => this.fatal(e.error || e.message));
    window.addEventListener('unhandledrejection', (e) => this.fatal(e.reason));
    // A progress-aware watchdog: it only speaks if NOTHING has progressed for 25 s,
    // and even then it only changes the hint under the brand. (Build 8 fired a red
    // error at a fixed 9 s, which a 20 MB first load always overran.)
    this.watchdog = setInterval(() => {
      if (this._settled) { clearInterval(this.watchdog); return; }
      const idle = (performance.now() - this.lastProgress) / 1000;
      if (idle > 25) this.hint('Still working\u2026 a slow connection or a very large model. The console (Cmd+Option+C) shows details.');
    }, 5000);

    const canvas = $('#gl');
    const hasWebGL2 = () => {
      try { return !!(window.WebGL2RenderingContext && canvas.getContext('webgl2')); }
      catch (e) { return false; }
    };
    if (!hasWebGL2()) {
      // A first attempt can fail right after navigation before the GPU
      // context is actually ready - this was showing a permanent "cannot
      // run" error and pointing at a floor map that no longer exists (/explore
      // just redirects back here), so pressing it looked like the error
      // "opened 3D" while really just reloading the same failing page. Retry
      // twice on a short delay before concluding the browser genuinely has
      // no WebGL2, and drop the dead link.
      let ok = false;
      for (let i = 0; i < 2 && !ok; i++) {
        await new Promise(r => setTimeout(r, 400));
        ok = hasWebGL2();
      }
      if (!ok) return this.fallback("This browser or device can't run the 3D view. Try reloading, or open SUFRA 360 in an up-to-date Chrome or Safari.");
    }

    this.step('Reading the venue', 0.04);
    const [venue, tables] = await Promise.all([D.venue(), D.tables()]);
    this.venue = venue; this.tables = tables; this.zones = venue.zones;
    this.seats = await D.seats(tables);
    const v = venue.venue;
    const m = v.map; const u = m.units_to_m;
    const W = m.width * u, H = m.height * u;
    this.bounds = { minX: -W / 2 - 4, maxX: W / 2 + 4, minZ: -H / 2 - 4, maxZ: H / 2 + 4 };

    // ---- renderer, camera, environment: the scene is alive from here on
    this.step('Lighting the sky', 0.1);
    this.sm = new SceneManager(canvas, this.quality, this.Q);
    this.sm.building = true;
    this.sm.onTickError = (e) => this.toast('A scene effect reported an error (see console). Everything else keeps running.');
    this.assets = new AssetManager(this.log, this.quality);
    this.mats = new Materials(this.assets);
    this.halos = new HaloSystem(this.sm.scene, 512);
    this.cam = new CameraController(this.sm.camera, canvas, this.bounds);
    this.cam.bindCancel(canvas);
    this.cam.setOverview(0, 0, Math.max(W, H) * 0.98);
    this.env = new EnvironmentManager(this.sm.scene, this.sm.renderer, this.assets, v.timezone, this.Q.shadow);
    await this.stage('environment', () => this.env.loadEnvironment());
    this.weather = new WeatherManager();
    this.assets.preload(['plateDinner', 'fork', 'knife', 'glassWine', 'glassWater', 'wineRed', 'dishOlives', 'cupSaucer', 'plant', 'chairSheen']);

    const g = v.geometry;
    // RestaurantBuilder is always constructed: even with a Blender venue, the app
    // uses its coordinate helpers. Only its geometry is skipped.
    this.rest = new RestaurantBuilder(this.sm.scene, this.assets, this.mats, v, this.Q, this.halos);
    const [wx1, wy1, wx2, wy2] = g.water;

    // ---- if you have exported a venue from Blender, that becomes the room
    const GLB_URL = '/static/models/venue.glb';
    this.useGLB = await GLBVenue.available(GLB_URL);

    if (this.useGLB) {
      this.step('Loading the venue', 0.18);
      const ok = await this.stage('venue model', async () => {
        this.glb = new GLBVenue(this.assets, this.log);
        this.glbInfo = await this.glb.load(GLB_URL, this.sm.scene, (p) => {
          this.step('Loading the venue \u00b7 ' + Math.round(p * 100) + '%', 0.18 + p * 0.44);
        });
      });
      if (!ok) { this.useGLB = false; this.glb = null; this.toast('The Blender venue could not be loaded, so the built-in room is being used.'); }
    }
    // A model may supply the whole restaurant, or only the shell. If it contains
    // no table_* objects, the furniture is still built here from the database, so
    // it keeps following your data inside your architecture.
    this.glbFurniture = !!(this.useGLB && this.glb && Object.keys(this.glb.tables).length);
    if (this.useGLB && !this.glbFurniture) {
      console.info('[SUFRA 360] the Blender venue has no table_* objects, so tables, ' +
                   'chairs and lamps are being built from the database inside it.');
    }

    // ---- water: your model's own plane if it has one, otherwise the animated harbour
    if (!this.useGLB || !this.glb.water) {
      this.step('Filling the harbour', this.useGLB ? 0.64 : 0.18);
      await this.stage('water', async () => {
        // A harbour, not a strip. The plane runs 900 m out and 900 m along, so
        // rotating the camera finds water at the horizon rather than an edge.
        // It stays one draw call; only the shader knows how far out you are.
        const quayX = this.rest.X(wx2);
        const EXTENT = 900;
        this.water = await new WaterSystem(this.sm.scene, this.assets).build(
          quayX - EXTENT / 2, this.rest.Z((wy1 + wy2) / 2), EXTENT, EXTENT + (wy2 - wy1) * u, 0.0,
          new THREE.Vector3(0.3, 0.6, 0.4), this.quality, quayX);
      });
    }

    if (!this.useGLB) {
      this.step('Laying the floors', 0.28);
      await this.stage('building', () => this.rest.buildBase());
    }

    // Baku on the horizon. Six draw calls, 320-780 m out, so rotating the camera
    // finds a city and a bay rather than the edge of the scene.
    await this.stage('surroundings', () => {
      // If the Blender venue ships its own Background_Baku collection, use that
      // and do not draw a second skyline on top of it.
      const ownCity = this.useGLB && this.glb && this.glb.hasBackground;
      if (ownCity) return;
      this.baku = new BakuContext(this.sm.scene, this.quality)
        .build(this.rest.X(wx2), this.rest.Z((wy1 + wy2) / 2));
    });

    // the loop starts NOW: the brand screen is a veil over a live scene, not a spinner
    this.sm.onTick((dt, t) => this.tick(dt, t));
    this.sm.start();
    this.cam.startIdle();
    this.showScene();
    await nextFrame();

    this.step('Laying the tables', this.useGLB ? 0.72 : 0.45);
    await this.stage('tables', async () => {
      const tm = new TableManager(this.sm.scene, this.assets, this.mats, v, this.tables, this.seats, this.quality, this.Q, this.halos);
      if (this.glbFurniture) this.glb.attach(tm);   // drive your objects instead of building furniture
      this.tm = await tm.build();
      if (!this.glbFurniture) {
        for (const t of this.tables) if (t.tags && t.tags.indexOf('umbrella') >= 0) this.rest.umbrella(this.rest.X(t.x), this.rest.Z(t.y), t.w * u * 0.95);
      }
    });
    await nextFrame();

    if (!this.useGLB) {
      this.step('Lighting the lamps', 0.62);
      await this.stage('decor', () => this.rest.buildDecor());
      await nextFrame();

      this.step('Planting the trees', 0.78);
      await this.stage('trees', async () => {
        // 1.5x the map radius: the reference's promenade trees are mature, with
        // canopies eight to ten metres across, and the old ones read as bushes
        const trees = g.trees.map(([mx, my, r]) => [this.rest.X(mx), this.rest.Z(my), r * u * 1.5])
          .concat(this.rest.extraTrees || []);
        this.foliage = await new FoliageSystem(this.sm.scene, this.assets, this.Q.leaves, { leafShadows: this.Q.leafShadows }).build(trees, this.rest.shrubSpots, 0.08);
      });
    }
    this.rain = new RainSystem(this.sm.scene, this.bounds, this.Q.rain);
    await nextFrame();

    this.step('Opening the doors', 0.92);
    this.cullLights();
    this.wireUI();
    this.startData();
    this.deepLink();
    this._settled = true;
    clearInterval(this.watchdog);
    this.sm.building = false;
    this.armEntry();
    console.info('[SUFRA 360] build %s up: %d tables, %d leaf cards, quality %s, stages failed: %s, fallbacks: %s',
      BUILD, this.tm ? Object.keys(this.tm.byId).length : 0, this.foliage && this.foliage.leaves ? this.foliage.leaves.count : 0,
      this.quality, this.stages.filter(s => !s.ok).map(s => s.name).join(',') || 'none',
      this.notes.length ? this.notes.join(' | ') : 'none');

    // ---- the slow, optional layer: real tableware, sofas and plants, the other two HDRs, guests
    this.background();
  }

  /**
   * An old link like /reserve?table=t12&date=...&time=...&party=4 is redirected
   * here by the server. Honour it: focus that table and open its drawer, so a
   * bookmark or a confirmation email still works without the old 2D page.
   */
  deepLink() {
    const q = new URLSearchParams(location.search);
    const wanted = q.get('table');
    if (!wanted) return;
    const byLabel = this.tables.find(t => t.id === wanted || String(t.label) === String(wanted));
    if (!byLabel) return;
    const party = parseInt(q.get('party'), 10);
    if (party) { const el = $('#ask-party'); if (el) el.value = String(party); }
    const time = q.get('time');
    if (time) { const el = $('#ask-time'); if (el && Array.from(el.options).some(o => o.value === time)) el.value = time; }
    this._deepLink = { table: byLabel, date: q.get('date'), reserve: /reserve/.test(document.referrer) || q.has('date') || q.has('party') };
  }

  async background() {
    const jobs = [];
    if (this.tm && !this.glbFurniture) jobs.push(this.tm.buildTableware().then(n => { if (n) this.step('Tables laid'); }));
    if (!this.useGLB) jobs.push(this.rest.buildModels());
    jobs.push(this.env.loadRest());
    // Clothed rigged pedestrians (character packs with their own Walk/Idle
    // clips). Taken wholesale from the other SUFRA build - this is the
    // moving-people system, nothing else came with it.
    jobs.push((async () => {
      try {
        this.clothedPeople = await new ClothedPeopleSystem(
          this.sm.scene, this.venue.venue, this.quality).build(this.venue.venue.geometry.promenade);
      } catch (e) { this.log.warn('[clothed-people] ' + (e && e.message)); }
    })());

    // Moving grass and wildflowers on the lawn around the plot. Deferred with
    // the rest: it is 14 k instanced cards on one draw call, but it is scenery.
    if (this.foliage && this.rest) {
      const pl = this.venue.venue.geometry.plot;
      jobs.push(this.foliage.buildGroundCover(this.rest.quayX, 0,
        (x, z) => this.rest.groundY(x, z),
        { x1: this.rest.X(pl[0]) - 3, x2: this.rest.X(pl[2]) + 3,
          z1: this.rest.Z(pl[1]) - 3, z2: this.rest.Z(pl[3]) + 3 }).catch(() => null));
    }

    // The parkland fills the land between the plot and the city, which was a
    // flat tinted quad. It is deferred because it is another 0.7 MB of models
    // and nothing in it is nearer than 58 m, so it can arrive after the room.
    if (this.foliage && this.rest) {
      jobs.push(this.foliage.buildParkland(this.rest.quayX, 0, 0.06,
                                          (x, z) => this.rest.groundY(x, z)));
    }
    if (this.Q.people) {
      jobs.push((async () => {
        this.people = new GuestSystem(this.sm.scene, this.assets, this.quality);
        if (await this.people.load()) {
          const paths = (this.venue.venue.geometry.walk_paths || []).map(p => p.map(([mx, my]) => [this.rest.X(mx), this.rest.Z(my)]));
          // staff moving between the pass and the rooms, plus people strolling the
          // promenade. The promenade paths are the ones that run along the water.
          const promenade = paths.filter(p => p.every(([x]) => x < this.rest.X(232)));
          const inside = paths.filter(p => promenade.indexOf(p) < 0);
          const total = this.Q.walkers || 0;
          // Indoors these are STAFF, not strolling visitors: service pace, and
          // seeded apart from the promenade crowd so the two groups do not
          // share clothing. Their routes are the venue's own service paths -
          // bar to tables to pass to entrance - so they stay in circulation
          // space and out of the tables, walls and the wc block.
          // Tables, the bar, the pass and the wc are solid to walkers. Radii
          // are the table's own half-width plus the ring of chairs around it,
          // so staff walk round a laid table instead of through it.
          const solid = this.tables.map(t => ({
            x: this.rest.X(t.x), z: this.rest.Z(t.y),
            r: this.rest.W(Math.max(t.w, t.h)) / 2 + 0.75,
          }));
          const geo = this.venue.venue.geometry;
          // bar_counter and back_bar are now one continuous marble counter
          // (see RestaurantBuilder.build()) rather than two separate strips,
          // so they are one obstacle here too instead of two overlapping ones.
          const barBox = [Math.min(geo.bar_counter[0], geo.back_bar[0]), geo.bar_counter[1],
                          Math.max(geo.bar_counter[2], geo.back_bar[2]), geo.bar_counter[3]];
          for (const box of [barBox, geo.pass, geo.wc]) {
            if (!box) continue;
            solid.push({ x: this.rest.X((box[0] + box[2]) / 2),
                         z: this.rest.Z((box[1] + box[3]) / 2),
                         r: Math.max(this.rest.W(box[2] - box[0]),
                                     this.rest.W(box[3] - box[1])) / 2 + 0.5 });
          }
          this.people.setObstacles(solid);
          // Indoor walkers are staff: consistent white shirt, black
          // trousers/apron, no bright colours. Promenade walkers below stay
          // on the varied guest palette - they are outside visitors, not
          // part of the service team.
          this.people.addWalkers(inside, Math.ceil(total * 0.4), { speed: 0.55, seed: 11, clothing: 'staff' });
          this.people.addWalkers(promenade.length ? promenade : paths, Math.floor(total * 0.6),
                                 { speed: 0.95, bothWays: true, seed: 3 });
        }
      })());
    }
    for (const j of jobs) { try { await j; } catch (e) { this.log.warn('[background] ' + (e && e.message)); } }
    this.hint('');
  }

  /** run one build stage; a failure is noted and shown, never fatal */
  async stage(name, fn) {
    try { await fn(); this.stages.push({ name, ok: true }); return true; }
    catch (e) {
      console.error('[SUFRA 360 stage ' + name + ']', e);
      this.stages.push({ name, ok: false, error: e });
      this.note(name + ' failed: ' + (e && e.message ? e.message : e));
      if (this._sceneShown) this.toast('The ' + name + ' layer failed to build (see console). The rest of the room is up.');
      return false;
    }
  }

  step(s, p) {
    this.lastProgress = performance.now();
    if (p != null) this.progress = p;
    const bar = $('#entry-bar i'); if (bar) bar.style.width = Math.round(this.progress * 100) + '%';
    this.hint(s + '\u2026');
    const lp = $('#loader p'); if (lp) lp.textContent = s + '\u2026';
  }

  hint(s) { const h = $('#entry-hint'); if (h) h.textContent = s; }

  showScene() {
    this._sceneShown = true;
    const l = $('#loader'); if (l) l.classList.add('gone');
    document.body.classList.add('scene-live');
  }

  /** the scene is up behind the brand; Enter lifts the veil and glides from an establishing height down to the overview */
  armEntry() {
    const btn = $('#entry-go'), hint = $('#entry-hint');
    if (!btn) return;
    btn.disabled = false;
    btn.setAttribute('data-i18n', 'entry.enter');
    btn.textContent = T('entry.enter');
    const bar = $('#entry-bar'); if (bar) bar.classList.add('done');
    if (hint) { hint.removeAttribute('data-i18n'); hint.textContent = ''; }
    const go = () => {
      if (this._entered) return;
      this._entered = true;
      $('#entry').classList.add('gone');
      document.body.classList.add('entered');
      this.cam.stopIdle();
      this.cam.toOverview(2400);
      if (this._deepLink) {
        const dl = this._deepLink; this._deepLink = null;
        setTimeout(() => {
          this.focus(dl.table.id);
          if (dl.reserve) setTimeout(() => { if (dl.date) this.book = { table: dl.table, step: 'when', date: dl.date }; this.reserveStrip(dl.table); }, 900);
        }, 2500);
      }
      window.removeEventListener('keydown', onKey);
      setTimeout(() => { const e = $('#entry'); if (e) e.style.display = 'none'; }, 1200);
    };
    const onKey = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
    btn.onclick = go;
    $('#entry').addEventListener('click', (e) => { if (e.target.id === 'entry' || e.target.classList.contains('entry-inner')) go(); });
    window.addEventListener('keydown', onKey);
  }

  fatal(err) {
    const msg = (err && err.stack) || (err && err.message) || String(err);
    console.error('[SUFRA 360]', err);
    if (this._sceneShown) {                   // scene already up: never hide a working page
      if (!this._toldOnce) { this._toldOnce = true; this.toast('A script error was logged to the console. The scene keeps running.'); }
      return;
    }
    if (this._shownFatal) return;
    this._shownFatal = true;
    this.fallback('The 3D view did not start: ' + msg.slice(0, 260));
  }

  fallback(msg) {
    const l = $('#loader');
    if (!l) return;
    l.classList.remove('gone');
    // There is no separate floor map to fall back to - SUFRA 360 is the only
    // guest experience, and the old link here just redirected back into this
    // same page, which read as "the error button opens 3D" and led nowhere
    // on a device that genuinely cannot render it. Offer a real reload instead.
    l.innerHTML = '<p class="fail">' + esc(msg) + '</p>' +
      '<button type="button" class="ghost" id="fallback-reload" style="margin-top:1rem">Reload</button>';
    const btn = $('#fallback-reload');
    if (btn) btn.onclick = () => location.reload();
    const e = $('#entry'); if (e) e.classList.add('gone');
  }

  // ---------------------------------------------------------------- data
  /**
   * The data loop, answering two separate questions.
   *
   *   LIVE MODE      what the room is physically doing right now. Green =
   *                  nobody sitting there; red = a party is at that table.
   *   SLOT MODE      what can be BOOKED for a chosen date and time. Green =
   *                  this table can take your booking then; red = it cannot.
   *
   * They are different questions and they are fetched from different
   * endpoints. A table full at two o'clock is still green for nine o'clock,
   * and a table empty right now is still red for a slot somebody else has
   * already booked. Nothing here invents a state: every row comes from
   * SUFRA OS, which is the same data the manager's floor plan reads.
   */
  startData() {
    const paint = (live) => {
      const rows = live.tables;
      if (!this.tm) return this.strip(live);          // the room is still building
      this.tm.applyLive(rows);
      if (this.people && this.people.enabled) {
        for (const r of rows) {
          const e = this.tm.byId[r.table_id];
          if (!e) continue;
          const want = r.state === 'OCCUPIED' ? Math.min(r.guests || 0, e.chairs.length) : 0;
          const have = (this.people.guests[r.table_id] || []).length;
          if (want !== have) this.people.seat(r.table_id, e.chairs, want);
        }
      }
      this.strip(live);
      if (this.panelId) this.panel(this.panelId, true);
    };

    const pull = async () => {
      if (this.slot) return this.pullAvailability();
      let live;
      try {
        live = await D.live();
      } catch (e) {
        this.setLink(T('hud.feedgone'));
        this.log.warn('[feed] ' + (e && e.message ? e.message : e));
        if (!this.live) {
          this._feedTry = Math.min((this._feedTry || 0) + 1, 5);
          clearTimeout(this._feedRetry);
          this._feedRetry = setTimeout(pull, 1500 * this._feedTry);
        }
        return;
      }
      this.live = live;
      paint(live);
      this.setLink(T('hud.livelink'));
      this._feedTry = 0;
    };

    this._paint = paint;
    this._pull = pull;
    pull();
    this._pullTimer = setInterval(() => { if (!document.hidden) pull(); }, 15000);
    // Coming back to a backgrounded tab should not wait out the rest of the
    // interval on stale numbers.
    document.addEventListener('visibilitychange', () => { if (!document.hidden) pull(); });
    // The server pushes when the restaurant genuinely changes - a waiter
    // seating a party, a manager moving a booking, a dish going off sale -
    // so the room updates without a reload and without polling harder.
    D.subscribe((ev) => {
      pull();
      if (ev && ev.type === 'STATE') this.refreshMenuSoon();
    }, (state) => this.setLink(state === 'live' ? T('hud.livelink') : T('hud.polling')));

    const wx = async () => {
      let w = null;
      try { w = await D.weather(); } catch (e) {}
      // the server could not reach Open-Meteo (usually missing root certificates on a
      // python.org Mac build): the browser can, so ask from here, same provider, same shape
      if (!w || w.fallback) {
        try {
          const v = this.venue.venue, loc = v.weather || { lat: 40.4093, lng: 49.8671 };
          const r = await fetch('https://api.open-meteo.com/v1/forecast?latitude=' + loc.lat + '&longitude=' + loc.lng +
            '&current=temperature_2m,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m,is_day,weather_code&timezone=auto');
          const j = await r.json(); const c = j.current || {};
          const CODES = { 0: 'clear', 1: 'mostly_clear', 2: 'partly_cloudy', 3: 'overcast', 45: 'fog', 48: 'fog',
            51: 'drizzle', 53: 'drizzle', 55: 'drizzle', 61: 'rain', 63: 'rain', 65: 'heavy_rain', 71: 'snow', 73: 'snow',
            75: 'snow', 80: 'rain', 81: 'rain', 82: 'heavy_rain', 85: 'snow', 86: 'snow', 95: 'thunderstorm', 96: 'thunderstorm', 99: 'thunderstorm' };
          w = { condition: CODES[c.weather_code] || 'partly_cloudy', temp_c: c.temperature_2m, precip_mm: c.precipitation,
                cloud: (c.cloud_cover || 0) / 100, wind_kmh: c.wind_speed_10m, wind_deg: c.wind_direction_10m,
                is_day: c.is_day, city: v.weather_city || '', source: 'open-meteo (browser)' };
        } catch (e) {}
      }
      if (!w) { $('#wx-text').textContent = '\u2014'; return; }
      this.weather.setLive(w);
      this.wxChip(w);
    };
    wx();
    setInterval(wx, 10 * 60 * 1000);
  }

  /** SLOT MODE: colour every table by whether it can take THIS booking. */
  async pullAvailability() {
    if (!this.slot) return;
    const { date, time, party } = this.slot;
    const seq = this._slotSeq = (this._slotSeq || 0) + 1;
    let grid;
    try {
      grid = await D.availability(date, time, party);
    } catch (e) {
      this.setLink(T('hud.feedgone'));
      return;
    }
    // Changing a select twice quickly puts two answers in flight; the slower
    // one must not repaint the room over the newer one.
    if (seq !== this._slotSeq) return;
    if (!this.slot) return;                     // switched back while in flight
    this.grid = grid;
    if (!this.tm) { this.slotStrip(grid); return; }   // the room is still building
    const rows = grid.tables.map(r => ({
      table_id: r.table_id, label: r.label, zone: r.zone, state: r.state,
      bookable: r.bookable, reason: r.reason, until: r.until,
      next_available: r.next_available, guests: 0,
    }));
    this.tm.applyLive(rows);
    if (this.people && this.people.enabled) {
      // Nobody is "sitting" at a table in a future slot: clear the room so the
      // picture cannot be mistaken for live occupancy.
      for (const r of rows) {
        const e = this.tm.byId[r.table_id];
        if (e && (this.people.guests[r.table_id] || []).length) this.people.seat(r.table_id, e.chairs, 0);
      }
    }
    this.slotStrip(grid);
    this.setLink(T('hud.livelink'));
    if (this.panelId) this.panel(this.panelId, true);
  }

  /** the bottom strip while a future slot is selected */
  slotStrip(grid) {
    const rows = grid.tables;
    const free = rows.filter(r => r.bookable).length;
    $('#s-tables').textContent = rows.length;
    $('#s-free').textContent = free;
    $('#s-occ').textContent = rows.filter(r => r.state === 'RESERVED').length;
    $('#s-res').textContent = rows.filter(r => r.state === 'HELD' || r.state === 'HELD_BY_YOU').length;
    $('#s-guests').textContent = grid.party_size;
    $('#s-load').textContent = Math.round(100 - (free / Math.max(1, rows.length)) * 100) + '%';
    $('#service').textContent = T('av.count', { n: free });
    const note = $('#sb-note');
    if (note) {
      note.textContent = grid.is_past ? T('av.past')
        : grid.is_closed ? T('av.closed')
        : free ? T('av.showing', { date: niceDate(grid.date), time: grid.time, party: grid.party_size })
        : T('av.none');
    }
  }

  setLink(s) { const el = $('#link'); if (el) { el.textContent = s; el.className = 'link ' + s.replace(/\s.*/, ''); } }

  wxChip(w) {
    const icon = { clear: '\u2600', mostly_clear: '\u{1F324}', partly_cloudy: '\u26C5', overcast: '\u2601', fog: '\u{1F32B}', drizzle: '\u{1F326}',
                   rain: '\u{1F327}', heavy_rain: '\u{1F327}', thunderstorm: '\u26C8', snow: '\u{1F328}' }[w.condition] || '\u2601';
    $('#wx-icon').textContent = icon;
    $('#wx-text').textContent = (w.city || '') + ' \u00b7 ' + Math.round(w.temp_c == null ? 18 : w.temp_c) + '\u00b0C \u00b7 ' +
      w.condition.replace('_', ' ') + ' \u00b7 wind ' + Math.round(w.wind_kmh || 0) + ' km/h' +
      (w.fallback ? ' \u00b7 offline' : w.stale ? ' \u00b7 cached' : '');
  }

  strip(live) {
    // Derive the counts from the rows this frame is actually rendering rather
    // than trusting live.counts. That object comes from SUFRA's own backend
    // and knows nothing about either overlay applied downstream of it - the
    // NOVA status overlay (which rewrites row.state for every table the OS
    // knows) or demo mode (which rewrites all of them). The strip therefore
    // reported "30 tables / 30 available / 0 occupied" while a third of the
    // lamps on screen were already red. Deriving keeps the two in agreement
    // by construction instead of by coincidence.
    const rows = live.tables || [];
    const c = live.counts || {};
    if (!rows.length) return;
    const count = (st) => rows.filter(r => r.state === st).length;
    const tables = rows.length;
    const occupied = count('OCCUPIED');
    const available = count('AVAILABLE');
    const reserved = count('RESERVED_SOON') + count('HELD');
    const guests = rows.reduce((a, r) => a + (r.state === 'OCCUPIED' ? (r.guests || 0) : 0), 0);
    $('#s-tables').textContent = tables;
    $('#s-occ').textContent = occupied;
    $('#s-free').textContent = available;
    $('#s-res').textContent = reserved;
    $('#s-guests').textContent = guests;
    $('#s-load').textContent = Math.round((occupied / Math.max(1, tables)) * 100) + '%';
    $('#service').textContent = T('service.' + (live.service || 'dinner')) +
      ' \u00b7 ' + T('service.livesuffix');
  }

  // ---------------------------------------------------------- interaction
  wireUI() {
    // The Menu, as an overlay: SUFRA 360 keeps rendering behind it and the
    // camera keeps its state, so this is not a page navigation.
    this.wireLanguage();
    this.wireSlotBar();

    const menuBtn = $('#nav-menu'), menuScreen = $('#menuscreen');
    if (menuBtn && menuScreen) {
      menuBtn.onclick = async () => {
        menuScreen.classList.remove('hidden');
        await this.renderMenu();
      };
      const close = () => menuScreen.classList.add('hidden');
      const back = $('#mn-back');
      if (back) back.onclick = close;
      menuScreen.addEventListener('click', e => { if (e.target === menuScreen) close(); });
      document.addEventListener('keydown', e => {
        if (e.key === 'Escape' && !menuScreen.classList.contains('hidden')) close();
      });
    }
    const canvas = $('#gl');
    const ray = new THREE.Raycaster();
    const ptr = new THREE.Vector2();
    let hovered = null, downAt = null;

    const pick = (ev) => {
      const r = canvas.getBoundingClientRect();
      ptr.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, this.sm.camera);
      const hit = ray.intersectObjects(this.tm.hitboxes, false)[0];
      return hit ? hit.object.userData.tableId : null;
    };

    canvas.addEventListener('pointermove', (ev) => {
      if (!this._entered) return;
      const id = pick(ev);
      if (id !== hovered) {
        hovered = id;
        this.tm.hover(id);
        canvas.style.cursor = id ? 'pointer' : 'grab';
        this.tooltip(id, ev);
      } else if (id) this.tooltip(id, ev);
    });
    canvas.addEventListener('pointerdown', (ev) => { downAt = [ev.clientX, ev.clientY]; });
    canvas.addEventListener('pointerup', (ev) => {
      if (!downAt) return;
      const moved = Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]);
      downAt = null;
      if (moved > 5) return;
      const id = pick(ev);
      if (id) this.focus(id);
    });
    canvas.addEventListener('dblclick', (ev) => { const id = pick(ev); if (id) this.focus(id, 2.6); });

    $('#btn-overview').onclick = () => { this.cam.toOverview(); this.closePanel(); };
    const toggleDiag = () => $('#diag').classList.toggle('hidden');
    $('#btn-diag').onclick = toggleDiag;
    window.addEventListener('keydown', (e) => {
      if (e.target && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
      if (e.key === 'd' || e.key === 'D') toggleDiag();
      if (e.key === 'Escape') { this.closePanel(); this.hideAnswer(); }
      if (e.key === 'o' || e.key === 'O') this.cam.toOverview();
      if (e.key === '/') { e.preventDefault(); $('#ask-q').focus(); }
    });
    $('#p-close').onclick = () => { this.closePanel(); };

    // Ask AI, from the main menu
    const askBtn = $('#nav-ask');
    if (askBtn) askBtn.onclick = () => {
      $('#ask').classList.add('open');
      $('#ask-q').focus();
      if ($('#ask-answer').classList.contains('hidden')) this.askHint();
    };

    // About, as an overlay on the room rather than a page navigation: the
    // scene keeps rendering and the camera keeps its place.
    const aboutBtn = $('#nav-about'), aboutPanel = $('#aboutpanel');
    if (aboutBtn && aboutPanel) {
      aboutBtn.onclick = () => { this.renderAbout(); aboutPanel.classList.remove('hidden'); };
      const shut = () => aboutPanel.classList.add('hidden');
      $('#ab-close').onclick = shut;
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !aboutPanel.classList.contains('hidden')) shut();
      });
    }

    // Reserve, from the main menu: pick the best free table and open its drawer
    const bookBtn = $('#nav-book');
    if (bookBtn) bookBtn.onclick = () => this.reserveBest();

    // zones
    const zb = $('#zones');
    zb.innerHTML = '<button data-z="all" class="on">All</button>' +
      this.zones.map(z => '<button data-z="' + z.id + '">' + esc(z.name) + '</button>').join('');
    $$('#zones button').forEach(b => b.onclick = () => {
      $$('#zones button').forEach(x => x.classList.remove('on')); b.classList.add('on');
      this.zone(b.dataset.z);
    });

    // time and weather demo
    $$('[data-time]').forEach(b => b.onclick = () => {
      $$('[data-time]').forEach(x => x.classList.remove('on')); b.classList.add('on');
      this.env.override = b.dataset.time;
    });
    $('#wx-demo').addEventListener('change', (e) => this.weather.setDemo(e.target.value));

    // quality selector: persists, reloads (a renderer cannot be re-created in place cleanly)
    const qs = $('#q-sel'); if (qs) { qs.value = this.quality; qs.addEventListener('change', () => {
      try { localStorage.setItem('sufra360.quality', qs.value); } catch (e) {}
      location.reload();
    }); }

    // the assistant: party size and time travel with every question
    const slots = this.venue.slots || [];
    const ts = $('#ask-time');
    if (ts) {
      const now = new Date(); const cur = String(now.getHours()).padStart(2, '0') + ':' + String(Math.floor(now.getMinutes() / 15) * 15).padStart(2, '0');
      let def = slots.find(s => s >= cur) || slots[slots.length - 1] || '19:30';
      ts.innerHTML = slots.map(s => '<option' + (s === def ? ' selected' : '') + '>' + s + '</option>').join('') || '<option>19:30</option>';
    }
    $('#ask-go').onclick = () => this.ask($('#ask-q').value);
    $('#ask-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') this.ask($('#ask-q').value); });
    $$('.ask-chips button').forEach(b => b.onclick = () => { $('#ask-q').value = b.dataset.q; this.ask(b.dataset.q); });
    $('#ask-close').onclick = () => this.hideAnswer();
  }

  tooltip(id, ev) {
    const tip = $('#tip');
    if (!id) { tip.classList.add('hidden'); return; }
    const e = this.tm.byId[id], L = e.live || {};
    const z = this.zones.find(z => z.id === e.table.zone) || {};
    const a = attributesOf(e.table, z);
    const word = this.stateWord(L);
    let extra = a.zone_name + ' \u00b7 ' + T('panel.seatsval', { v: a.seats }) + ' \u00b7 ' + W(a.noise);
    if (L.state === 'OCCUPIED') extra = T('panel.seatsval', { v: L.guests }) +
      (L.elapsed_min == null ? '' : ' \u00b7 ' + L.elapsed_min + ' min') + ' \u00b7 ' + a.zone_name;
    if (L.state === 'AVAILABLE' && L.until_next) extra = a.zone_name + ' \u00b7 ' + this.untilNext(L);
    if (this.slot && !L.bookable) extra = a.zone_name + ' \u00b7 ' +
      (L.next_available ? T('panel.nextfree', { time: L.next_available }) : T('state.' + L.state));
    tip.innerHTML = '<b>Table ' + esc(e.table.label) + '</b><span class="' + esc((L.state || '').toLowerCase()) + '">' + esc(word) + '</span><small>' + esc(extra) + '</small>';
    const w = tip.offsetWidth || 180;
    tip.style.left = Math.min(window.innerWidth - w - 12, ev.clientX + 14) + 'px'; tip.style.top = (ev.clientY + 12) + 'px';
    tip.classList.remove('hidden');
  }

  focus(id, distance) {
    const e = this.tm.byId[id];
    if (!e) return;
    this.cam.flyTo(e.pos.clone().setY(0.6), distance || 4.6, 0.95, undefined, 1500);
    this.panel(id);
  }

  zone(zid) {
    this.closePanel();
    if (zid === 'all') { this.cam.toOverview(); return; }
    const z = this.zones.find(z => z.id === zid);
    if (!z) return;
    const [x1, y1, x2, y2] = z.bounds;
    const cx = this.rest.X((x1 + x2) / 2), cz = this.rest.Z((y1 + y2) / 2);
    const ext = Math.max((x2 - x1), (y2 - y1)) * this.venue.venue.map.units_to_m;
    this.cam.flyTo(new THREE.Vector3(cx, 0, cz), ext * 1.3 + 6, 0.68, undefined, 1600);
  }

  // ------------------------------------------------------------ assistant
  askContext() {
    // When the guest has chosen a date and time in the slot picker, that IS
    // the context — the assistant must answer about the same moment the room
    // is currently coloured for, not about right now.
    if (this.slot) return { party: this.slot.party, time: this.slot.time, date: this.slot.date };
    const party = parseInt(($('#ask-party') || {}).value, 10) || 2;
    const time = ($('#ask-time') || {}).value || '19:30';
    const date = (this.venue && this.venue.today) ||
      (this.live && this.live.date) || new Date().toISOString().slice(0, 10);
    return { party, time, date };
  }

  /** the one place a table state becomes a word, in the guest's language */
  stateWord(L) {
    if (!L || !L.state) return T('state.UNKNOWN');
    if (this.slot) {
      if (L.state === 'AVAILABLE' || L.state === 'HELD_BY_YOU') return T('state.' + L.state);
      return T('state.' + L.state);
    }
    return T('state.' + L.state);
  }

  untilNext(L) {
    if (!L.until_next) return '';
    const m = /(\d{2}:\d{2})/.exec(L.until_next);
    return m ? T('panel.freeuntil', { time: m[1] }) : T('panel.freeallevening');
  }

  async ask(q) {
    q = (q || '').trim(); if (!q) return;
    const box = $('#ask-answer');
    box.innerHTML = '<div class="a-thinking" title="' + esc(T('ask.thinking')) + '"><i></i><i></i><i></i></div>';
    box.classList.remove('hidden');
    $('#ask').classList.add('open');
    const { party, time, date } = this.askContext();
    let a;
    try { a = await D.guide(q, date, time, party); }
    catch (e) { box.innerHTML = '<div class="a-msg">' + esc(T('ask.failed')) + '</div>'; return; }
    this._lastAnswer = a;
    this.highlight(a.highlight || []);
    if (a.focus && this.tm.byId[a.focus]) this.cam.flyTo(this.tm.byId[a.focus].pos.clone().setY(0.6), 9, 0.7, undefined, 1500);
    const ctx = (a.party_size ? 'for ' + a.party_size : '') + (a.time ? ' at ' + a.time : '');
    const cards = (a.tables || []).map(t => {
      const e = this.tm.byId[t.id];
      const st = (t.state || (e && e.state) || '').toLowerCase();
      return '<button data-t="' + esc(t.id) + '" class="a-card"><span class="dot ' + esc(st) + '"></span>' +
        '<b>' + esc(T('panel.table', { n: t.label })) + '</b><small>' + esc((t.why || []).slice(0, 3).join(' \u00b7 ') || t.zone) + '</small></button>';
    }).join('');
    box.innerHTML = '<div class="a-head"><span class="a-icon">\u2726</span><span class="a-ctx">' + esc(ctx) + '</span></div>' +
      '<div class="a-msg">' + esc(a.message) + '</div>' + (cards ? '<div class="a-tables">' + cards + '</div>' : '');
    $$('#ask-answer .a-card').forEach(b => b.onclick = () => this.focus(b.dataset.t));
    clearTimeout(this._askT); this._askT = setTimeout(() => this.hideAnswer(), 45000);
  }

  hideAnswer() { $('#ask-answer').classList.add('hidden'); $('#ask').classList.remove('open'); this.highlight([]); }

  /** what Ask AI can do, shown the first time it is opened from the menu */
  askHint() {
    const box = $('#ask-answer');
    box.classList.remove('hidden');
    box.innerHTML = '<div class="a-head"><span class="a-icon">\u2726</span>' +
      '<span class="a-ctx">' + esc(T('hud.ask')) + '</span></div>' +
      '<div class="a-msg">' + esc(T('ask.ph')) + '</div>';
  }

  /**
   * Reserve from the main menu. Rather than asking the guest to hunt for a
   * table, this takes the party size and time already set, asks the same guide
   * the assistant uses for the best free match, focuses it and opens the drawer.
   */
  async reserveBest() {
    const { party, time } = this.askContext();
    const q = 'best available table for ' + party + ' at ' + time;
    $('#ask-q').value = q;
    await this.ask(q);
    const a = this._lastAnswer;
    const pick = (a && a.tables || []).find(t => {
      const e = this.tm.byId[t.id];
      return e && e.state === 'AVAILABLE';
    }) || (a && a.tables || [])[0];
    if (!pick) return this.toast(T('av.none'));
    this.focus(pick.id);
    const e = this.tm.byId[pick.id];
    if (e) setTimeout(() => this.reserveStrip(e.table), 600);
  }

  /** pulse a set of tables' rings, subtly, for a few seconds */
  highlight(ids) {
    const set = new Set(ids);
    for (const k in this.tm.byId) this.tm.byId[k].ring.material.opacity = set.has(k) ? 0.5 : (this.panelId === k ? 0.5 : 0);
    clearTimeout(this._hlT);
    if (ids.length) this._hlT = setTimeout(() => { for (const k in this.tm.byId) if (this.panelId !== k) this.tm.byId[k].ring.material.opacity = 0; }, 12000);
  }

  // ---------------------------------------------------------------- panel
  async panel(id, silent) {
    const e = this.tm.byId[id];
    if (!e) return;
    const fresh = this.panelId !== id;
    this.panelId = id;
    this.tm.pinned = id;
    const L = e.live || {};
    const tbl = e.table, sc = tbl.scores || {};
    const z = this.zones.find(x => x.id === tbl.zone) || {};
    const a = attributesOf(tbl, z);
    const chips = chipsOf(a);

    $('#p-title').textContent = T('panel.table', { n: tbl.label });
    $('#p-zone').textContent = a.zone_name + ' \u00b7 ' + W(a.setting) + (z.blurb ? ' \u00b7 ' + z.blurb : '');
    const word = this.stateWord(L);
    let tail = '';
    if (!this.slot && L.state === 'AVAILABLE' && L.until_next) tail = ' \u00b7 ' + this.untilNext(L);
    if (!this.slot && L.state === 'RESERVED_SOON' && L.upcoming) tail = ' \u00b7 ' + L.upcoming;
    if (this.slot && !L.bookable && L.next_available) tail = ' \u00b7 ' + T('panel.nextfree', { time: L.next_available });
    $('#p-state').innerHTML = '<i></i>' + esc(word) + esc(tail);
    $('#p-state').className = 'pill ' + String(L.state || 'unknown').toLowerCase() +
      (this.slot ? (L.bookable ? ' bookable' : ' unbookable') : '');

    const chip = (x, cls) => '<span class="' + (cls || '') + '">' + esc(W(x)) + '</span>';
    $('#p-traits').innerHTML =
      '<div class="trow"><em>' + esc(T('panel.setting')) + '</em>' + chips.setting.map(x => chip(x, 'cool')).join('') + '</div>' +
      '<div class="trow"><em>' + esc(T('panel.atmosphere')) + '</em>' + chips.atmosphere.map(x => chip(x)).join('') + '</div>' +
      (chips.suits.length ? '<div class="trow"><em>' + esc(T('panel.suits')) + '</em>' + chips.suits.map(x => chip(x, 'warm')).join('') + '</div>' : '');

    const meters = [[T('panel.quiet'), sc.quiet], [T('panel.view'), sc.view],
                    [T('panel.privacy'), sc.privacy], [T('panel.romantic'), sc.romantic]];
    $('#p-meters').innerHTML = meters.map(([k, v]) =>
      '<span class="k">' + esc(k) + '</span><span class="bar"><i style="width:' + Math.round((v || 0) * 100) + '%"></i></span>' +
      '<span class="v">' + Math.round((v || 0) * 10) + '/10</span>').join('');

    // Two different questions, two different sets of facts. In live mode the
    // panel talks about the party sitting there; in slot mode it talks about
    // whether this table can take the guest's booking.
    const rows = [[T('panel.seats'), T('panel.seatsval', { v: a.seats })],
                  [T('panel.frombar'), a.bar_m + ' m'],
                  [T('panel.fromkitchen'), a.kitchen_m + ' m']];
    if (a.near_water) rows.push([T('panel.towater'), a.water_m + ' m']);
    if (!this.slot && L.state === 'OCCUPIED') {
      rows.push([T('panel.guestsnow'), L.guests]);
      if (L.since) rows.push([T('panel.seatedat'), L.since + (L.until ? ' \u2192 ' + L.until : '')]);
      if (L.elapsed_min != null) rows.push([T('panel.elapsed'), L.elapsed_min + ' min']);
    }
    if (!this.slot && L.state === 'RESERVED_SOON' && L.upcoming) {
      rows.push([T('panel.arriving'), T('panel.arrivingval', { time: L.upcoming, n: L.guests })]);
    }
    if (this.slot && !L.bookable) {
      rows.push([T('panel.unavailablefor', { date: niceDate(this.slot.date), time: this.slot.time }),
                 L.next_available ? T('panel.nextfree', { time: L.next_available }) : word]);
    }
    $('#p-rows').innerHTML = rows.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('');
    $('#p-best').textContent = a.best_for && a.best_for.length
      ? T('panel.bestfor', { list: a.best_for.slice(0, 3).map(W).join(', ') })
      : T('panel.allround');

    // Only what a guest can actually do. Seating, freeing, moving and
    // cancelling other people's bookings are operational actions and live in
    // SUFRA OS behind a signed-in role — never in a public 3D room.
    const acts = [];
    // A table this guest is already holding is theirs to book; only somebody
    // ELSE's hold makes it unavailable.
    const bookable = this.slot ? !!L.bookable
      : (L.state === 'AVAILABLE' || L.state === 'HELD_BY_YOU');
    if (bookable) acts.push([T('panel.reserve'), 'primary', () => this.reserveStrip(tbl)]);
    else acts.push([T('panel.waitlist'), 'primary', () => this.waitlistStrip(tbl)]);
    acts.push([T('panel.askabout'), 'ghost', () => {
      const q = 'tell me about table ' + tbl.label;
      $('#ask-q').value = q; this.ask(q);
    }]);
    const box = $('#p-actions'); box.innerHTML = '';
    for (const [label, cls, fn] of acts) {
      const b = document.createElement('button'); b.className = cls; b.textContent = label; b.onclick = fn;
      box.appendChild(b);
    }
    if (fresh || !silent) $('#p-reserve').classList.add('hidden');
    if (!silent) $('#panel').classList.remove('hidden');
    e.ring.material.opacity = 0.5;
  }

  /**
   * Booking, entirely inside the 3D scene.
   *
   * Three steps in one drawer: when, who, and the confirmation. The scene keeps
   * rendering behind it, the table stays focused, and nothing navigates away.
   * It drives the same endpoints the old page did - POST /api/public/holds then
   * POST /api/public/reservations - so every rule the restaurant already has
   * (capacity, opening hours, double-booking, idempotency) still applies.
   */
  reserveStrip(t) {
    const ctx = this.askContext();
    this.book = { table: t, step: 'when', date: this.slot ? this.slot.date : ctx.date,
                  time: this.slot ? this.slot.time : ctx.time,
                  party: this.slot ? this.slot.party : ctx.party };
    this.renderBooking();
    $('#p-reserve').classList.remove('hidden');
    $('#p-reserve').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  renderBooking() {
    const box = $('#p-reserve');
    const B = this.book;
    if (!B) return;
    const t = B.table;
    if (B.step === 'when') return this.bookingWhen(box, t);
    if (B.step === 'who') return this.bookingWho(box, t);
    if (B.step === 'done') return this.bookingDone(box, t);
    if (B.step === 'waitlist') return this.bookingWaitlist(box, t);
    if (B.step === 'waitlisted') return this.bookingWaitlisted(box, t);
  }

  /** the party sizes this table can physically take */
  sizesFor(t) {
    const sizes = [];
    for (let n = Math.max(1, t.min_party); n <= t.max_party; n++) sizes.push(n);
    return sizes;
  }

  slotOptions(selected) {
    const slots = (this.venue && this.venue.slots) || [];
    return slots.map(sl => '<option' + (sl === selected ? ' selected' : '') + '>' + sl + '</option>').join('');
  }

  /** step 1: when, how many, and what kind of table */
  bookingWhen(box, t) {
    const B = this.book;
    const sizes = this.sizesFor(t);
    const chosen = Math.min(Math.max(B.party || 2, sizes[0]), sizes[sizes.length - 1]);
    const today = (this.venue && this.venue.today) || new Date().toISOString().slice(0, 10);
    const occasions = [['', 'bk.occasion.none'], ['Birthday', 'bk.occasion.birthday'],
      ['Anniversary', 'bk.occasion.anniversary'], ['Business', 'bk.occasion.business'],
      ['Celebration', 'bk.occasion.celebration'], ['Date night', 'bk.occasion.date'],
      ['Family meal', 'bk.occasion.family']];
    box.innerHTML =
      '<div class="bk-head"><b>' + esc(T('bk.head', { n: t.label })) + '</b>' +
        '<span class="bk-step">' + esc(T('bk.step1')) + '</span></div>' +
      '<label><span>' + esc(T('bk.date')) + '</span><input type="date" id="r-date" value="' +
        esc(B.date || today) + '" min="' + esc(today) + '"></label>' +
      '<label><span>' + esc(T('bk.time')) + '</span><select id="r-time">' +
        this.slotOptions(B.time) + '</select></label>' +
      '<label><span>' + esc(T('bk.guests')) + '</span><div class="bk-sizes" id="r-party">' +
        sizes.map(n => '<button data-n="' + n + '"' + (n === chosen ? ' class="on"' : '') + '>' + n + '</button>').join('') + '</div></label>' +
      '<label><span>' + esc(T('bk.occasion')) + '</span><select id="r-occasion">' +
        occasions.map(([v, k]) => '<option value="' + esc(v) + '"' + (v === B.occasion ? ' selected' : '') + '>' + esc(T(k)) + '</option>').join('') +
        '</select></label>' +
      '<label><span>' + esc(T('bk.pref')) + '</span><input id="r-pref" maxlength="120" placeholder="' +
        esc(T('bk.pref.ph')) + '" value="' + esc(B.preference || '') + '"></label>' +
      '<button class="primary" id="r-next">' + esc(T('bk.next')) + '</button>' +
      '<small id="r-note">' + esc(T('bk.holdnote', { min: Math.round(((this.venue && this.venue.hold_seconds) || 300) / 60) })) + '</small>';

    $$('#r-party button').forEach(b => b.onclick = () => {
      $$('#r-party button').forEach(x => x.classList.remove('on'));
      b.classList.add('on');
    });

    $('#r-next').onclick = async () => {
      const B2 = this.book;
      B2.date = $('#r-date').value;
      B2.time = $('#r-time').value;
      B2.party = parseInt(($('#r-party .on') || {}).dataset.n, 10) || chosen;
      B2.occasion = $('#r-occasion').value;
      B2.preference = $('#r-pref').value.trim();
      // The server is the authority on this, and rejects a past time whatever
      // the browser sends. Checking here as well simply saves a round trip.
      if (this.isPast(B2.date, B2.time)) {
        $('#r-note').textContent = T('av.past');
        return;
      }
      $('#r-next').disabled = true;
      $('#r-note').textContent = T('bk.holding', { n: t.label });
      const r = await D.hold(t.id, B2.date, B2.time, B2.party);
      if (r && r.ok) {
        B2.hold = r.hold || r;
        B2.holdUntil = this.expiryMs(B2.hold.expires_at) ||
          Date.now() + (((this.venue && this.venue.hold_seconds) || 300) * 1000);
        B2.step = 'who';
        this.renderBooking();
        return;
      }
      $('#r-next').disabled = false;
      $('#r-note').innerHTML = esc(E(r)) +
        ' <button class="bk-link" id="r-wl">' + esc(T('panel.waitlist')) + '</button>';
      const wl = $('#r-wl');
      if (wl) wl.onclick = () => { this.book.step = 'waitlist'; this.renderBooking(); };
    };
  }

  /** is this date+time already behind the restaurant's own clock? */
  isPast(date, time) {
    const today = (this.venue && this.venue.today) || new Date().toISOString().slice(0, 10);
    if (date < today) return true;
    if (date > today) return false;
    return time < ((this.venue && this.venue.min_time_today) || '00:00');
  }

  /** step 2: who is coming, with the hold counting down */
  bookingWho(box, t) {
    const B = this.book;
    box.innerHTML =
      '<div class="bk-head"><b>' + esc(T('bk.almost')) + '</b><span class="bk-step">' + esc(T('bk.step2')) + '</span></div>' +
      '<div class="bk-summary">' + esc(T('bk.summary', {
        n: t.label, date: niceDate(B.date), time: B.time, party: B.party })) +
        '<i id="r-timer" class="bk-timer"></i></div>' +
      '<div class="bk-two">' +
        '<label><span>' + esc(T('bk.first')) + '</span><input id="r-first" autocomplete="given-name" maxlength="60"></label>' +
        '<label><span>' + esc(T('bk.last')) + '</span><input id="r-last" autocomplete="family-name" maxlength="60"></label>' +
      '</div>' +
      '<label><span>' + esc(T('bk.email')) + '</span><input id="r-email" type="email" autocomplete="email" maxlength="120" placeholder="you@example.com"></label>' +
      '<label><span>' + esc(T('bk.phone')) + '</span><input id="r-phone" type="tel" autocomplete="tel" maxlength="40" placeholder="+994 ..."></label>' +
      '<label><span>' + esc(T('bk.allergies')) + '</span><input id="r-allergies" maxlength="200" placeholder="' + esc(T('bk.allergies.ph')) + '"></label>' +
      '<label><span>' + esc(T('bk.dietary')) + '</span><input id="r-dietary" maxlength="200" placeholder="' + esc(T('bk.dietary.ph')) + '"></label>' +
      '<label><span>' + esc(T('bk.access')) + '</span><input id="r-access" maxlength="200" placeholder="' + esc(T('bk.access.ph')) + '"></label>' +
      '<label><span>' + esc(T('bk.chairs')) + '</span><select id="r-chairs">' +
        [0, 1, 2, 3].map(n => '<option>' + n + '</option>').join('') + '</select></label>' +
      '<label><span>' + esc(T('bk.requests')) + '</span><textarea id="r-requests" rows="2" maxlength="400" placeholder="' + esc(T('bk.requests.ph')) + '"></textarea></label>' +
      '<button class="primary" id="r-confirm">' + esc(T('bk.confirm')) + '</button>' +
      '<button class="bk-back" id="r-back">' + esc(T('bk.back')) + '</button>' +
      '<small id="r-note"></small>';

    this.startHoldTimer();
    $('#r-back').onclick = () => { this.stopHoldTimer(); this.book.step = 'when'; this.renderBooking(); };

    $('#r-confirm').onclick = async () => {
      const payload = {
        table_id: t.id, date: B.date, time: B.time, party_size: B.party,
        first_name: $('#r-first').value.trim(), last_name: $('#r-last').value.trim(),
        email: $('#r-email').value.trim(), phone: $('#r-phone').value.trim(),
        occasion: B.occasion || '', preference: B.preference || '',
        allergies: $('#r-allergies').value.trim(),
        dietary: $('#r-dietary').value.trim(),
        accessibility: $('#r-access').value.trim(),
        high_chairs: parseInt($('#r-chairs').value, 10) || 0,
        special_request: $('#r-requests').value.trim(),
        language: getLang(),
        hold_id: B.hold && B.hold.id,
        idempotency_key: B.key || (B.key = 's360-' + t.id + '-' + Date.now()),
      };
      const LABEL = { first_name: 'bk.first', last_name: 'bk.last', email: 'bk.email', phone: 'bk.phone' };
      const missing = Object.keys(LABEL).filter(k => !payload[k]);
      if (missing.length) {
        $('#r-note').textContent = T('bk.missing', { fields: missing.map(k => T(LABEL[k])).join(', ') });
        return;
      }
      $('#r-confirm').disabled = true;
      $('#r-note').textContent = T('bk.confirming');
      const r = await D.reserve(payload);
      if (!r || !r.ok) {
        $('#r-confirm').disabled = false;
        $('#r-note').textContent = E(r);
        if (r && (r.error === 'conflict' || r.error === 'no_capacity')) {
          this.book.step = 'waitlist';
          this.renderBooking();
        }
        return;
      }
      this.stopHoldTimer();
      B.reservation = r.reservation;
      B.calendar = r.calendar;
      B.step = 'done';
      this.renderBooking();
      this.toast(T('toast.booked', { n: t.label }));
      if (this._pull) this._pull();
    };
  }

  /**
   * The confirmation.
   *
   * No booking code shouted at the guest: the reference still exists, in
   * the database and in SUFRA OS, where the restaurant actually needs it.
   * No email or SMS goes out — what a guest wants here is to know it
   * worked and to put it in their calendar.
   */
  bookingDone(box, t) {
    const B = this.book;
    const r = B.reservation || {};
    const cal = B.calendar || {};
    box.innerHTML =
      '<div class="bk-done">' +
        '<span class="bk-tick">&#10003;</span>' +
        '<b>' + esc(T('ok.title')) + '</b>' +
        '<p>' + esc(T('ok.body')) + '</p>' +
        '<div class="bk-cal">' +
          (cal.ics ? '<a href="' + esc(cal.ics) + '" download>' + esc(T('ok.calendar')) + '</a>' : '') +
          (cal.google ? '<a href="' + esc(cal.google) + '" target="_blank" rel="noopener">' + esc(T('ok.google')) + '</a>' : '') +
        '</div>' +
      '</div>' +
      '<button class="bk-back" id="r-close">' + esc(T('ok.done')) + '</button>';
    $('#r-close').onclick = () => {
      $('#p-reserve').classList.add('hidden');
      this.book = null;
      this.cam.toOverview();
      this.closePanel();
    };
  }

  /** Join the restaurant's own waitlist — the same list the host works from. */
  waitlistStrip(t) {
    const ctx = this.askContext();
    this.book = { table: t, step: 'waitlist', date: this.slot ? this.slot.date : ctx.date,
                  time: this.slot ? this.slot.time : ctx.time,
                  party: this.slot ? this.slot.party : ctx.party };
    this.renderBooking();
    $('#p-reserve').classList.remove('hidden');
    $('#p-reserve').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  bookingWaitlist(box, t) {
    const B = this.book;
    const sizes = [];
    for (let n = 1; n <= 12; n++) sizes.push(n);
    const today = (this.venue && this.venue.today) || new Date().toISOString().slice(0, 10);
    box.innerHTML =
      '<div class="bk-head"><b class="wl-head">' + esc(T('wl.title')) + '</b></div>' +
      '<p class="wl-blurb">' + esc(T('wl.blurb')) + '</p>' +
      '<label><span>' + esc(T('bk.date')) + '</span><input type="date" id="w-date" value="' +
        esc(B.date || today) + '" min="' + esc(today) + '"></label>' +
      '<label><span>' + esc(T('bk.time')) + '</span><select id="w-time">' + this.slotOptions(B.time) + '</select></label>' +
      '<label><span>' + esc(T('bk.guests')) + '</span><select id="w-party">' +
        sizes.map(n => '<option' + (n === B.party ? ' selected' : '') + '>' + n + '</option>').join('') + '</select></label>' +
      '<label><span>' + esc(T('wl.name')) + '</span><input id="w-name" maxlength="120" autocomplete="name"></label>' +
      '<label><span>' + esc(T('bk.phone')) + '</span><input id="w-phone" type="tel" maxlength="40" autocomplete="tel" placeholder="+994 ..."></label>' +
      '<label><span>' + esc(T('bk.email')) + '</span><input id="w-email" type="email" maxlength="120" autocomplete="email" placeholder="you@example.com"></label>' +
      '<label><span>' + esc(T('wl.area')) + '</span><input id="w-area" maxlength="120" placeholder="' + esc(T('wl.area.ph')) + '" value="' + esc(t ? t.zone_name || '' : '') + '"></label>' +
      '<label><span>' + esc(T('bk.requests')) + '</span><textarea id="w-note" rows="2" maxlength="300"></textarea></label>' +
      '<button class="primary" id="w-join">' + esc(T('wl.join')) + '</button>' +
      '<button class="bk-back" id="w-back">' + esc(T('bk.back')) + '</button>' +
      '<small id="w-note-line"></small>';

    $('#w-back').onclick = () => { this.book.step = 'when'; this.renderBooking(); };
    $('#w-join').onclick = async () => {
      const payload = {
        name: $('#w-name').value.trim(), phone: $('#w-phone').value.trim(),
        email: $('#w-email').value.trim(), party_size: parseInt($('#w-party').value, 10) || 2,
        date: $('#w-date').value, time: $('#w-time').value,
        area: $('#w-area').value.trim(), note: $('#w-note').value.trim(),
        language: getLang(),
      };
      if (!payload.name || (!payload.phone && !payload.email)) {
        $('#w-note-line').textContent = T('bk.missing', {
          fields: [T('wl.name'), T('bk.phone')].join(', ') });
        return;
      }
      $('#w-join').disabled = true;
      $('#w-note-line').textContent = T('wl.joining');
      const r = await D.waitlist(payload);
      if (!r || !r.ok) {
        $('#w-join').disabled = false;
        $('#w-note-line').textContent = E(r);
        return;
      }
      this.book.waitlist = Object.assign({}, r, payload);
      this.book.step = 'waitlisted';
      this.renderBooking();
    };
  }

  bookingWaitlisted(box) {
    const w = (this.book && this.book.waitlist) || {};
    const msg = w.date && w.time
      ? T('wl.done', { date: niceDate(w.date), time: w.time })
      : T('wl.donenow', { min: w.quoted_minutes || 25 });
    box.innerHTML =
      '<div class="bk-done"><span class="bk-tick">&#10003;</span>' +
      '<b>' + esc(T('ok.title')) + '</b><p>' + esc(msg) + '</p></div>' +
      '<button class="bk-back" id="r-close">' + esc(T('ok.done')) + '</button>';
    $('#r-close').onclick = () => {
      $('#p-reserve').classList.add('hidden');
      this.book = null;
      this.closePanel();
    };
  }

  /**
   * The menu — SUFRA OS's own dish records, read live.
   *
   * There is no menu file in this application. A price the manager changes,
   * a dish the kitchen marks sold out, a new starter, a translated name: all
   * of it is one edit in SUFRA OS and it is here on the next read. The
   * screen also re-renders on a language change and whenever the restaurant
   * pushes a change, so it cannot sit on a stale copy.
   */
  async renderMenu(force) {
    const body = $('#mn-body');
    if (!body) return;
    if (!force && this._menu && body.dataset.lang === getLang()) return;
    if (!this._menu || force) {
      try { this._menu = await D.menu(); }
      catch (e) {
        body.innerHTML = '<p class="muted">' + esc(T('menu.unavailable')) + '</p>';
        return;
      }
    }
    const lang = getLang();
    body.dataset.lang = lang;
    const cur = this._menu.currency || '';
    const pick = (d, field) => {
      const localised = d[field + '_' + lang];
      return (lang !== 'en' && localised) ? localised : d[field];
    };
    body.innerHTML = (this._menu.sections || []).map(sec =>
      '<section class="mn-sec"><h2>' + esc(lang === 'en' ? sec.name : (sec['name_' + lang] || sec.name)) + '</h2><div class="dishes">' +
      (sec.dishes || []).map(d =>
        '<article class="dish' + (d.available ? '' : ' soldout') + '">' +
          '<img src="' + esc(d.image || ('/assets/menu/' + d.id + '.jpg')) + '" alt="' + esc(pick(d, 'name')) + '" loading="lazy"' +
            ' onerror="this.style.visibility=\'hidden\'">' +
          '<div class="d-body">' +
            '<div class="d-top"><h3>' + esc(pick(d, 'name')) + '</h3>' +
              '<span class="d-price">' + esc(cur) + Number(d.price).toFixed(2) + '</span></div>' +
            '<p>' + esc(pick(d, 'blurb') || '') + '</p>' +
            '<div class="tagrow">' +
              (d.available ? '' : '<span class="tag alg">' + esc(T('menu.soldout')) + '</span>') +
              (d.diet || []).map(x => '<span class="tag diet">' + esc(String(x).replace('_', ' ')) + '</span>').join('') +
              (d.allergens || []).map(x => '<span class="tag alg">' + esc(x) + '</span>').join('') +
            '</div>' +
          '</div>' +
        '</article>').join('') +
      '</div></section>').join('');
  }

  /** the restaurant's own record — name, hours, contact, policy — translated */
  renderAbout() {
    const body = $('#ab-body');
    if (!body) return;
    const r = (this.venue && this.venue.restaurant) || {};
    const svc = (this.venue && this.venue.service) || {};
    const rows = [
      [T('about.hours'), T('about.seating', { open: svc.open, last: svc.last_seating, close: svc.close })],
      [T('panel.seats'), T('about.tables', { n: this.tables.length, z: this.zones.length })],
      [T('about.contact'), [r.phone, r.email].filter(Boolean).join(' · ')],
      ['', r.address || ''],
    ].filter(([, v]) => v);
    body.innerHTML =
      '<h2>' + esc(r.name || 'SUFRA') + '</h2>' +
      '<p class="ab-sub">' + esc(r.tagline || '') + '</p>' +
      '<dl>' + rows.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>' +
      '<p class="ab-policy">' + esc(T('about.policy', {
        grace: (this.venue && this.venue.grace_minutes) || 30 })) + '</p>';
  }

  /** a menu change pushed by the restaurant: refetch, but only once per burst */
  refreshMenuSoon() {
    clearTimeout(this._menuT);
    this._menuT = setTimeout(() => {
      const open = $('#menuscreen') && !$('#menuscreen').classList.contains('hidden');
      this._menu = null;
      if (open) this.renderMenu(true);
    }, 400);
  }

  // ------------------------------------------------------------ language
  wireLanguage() {
    const paint = () => {
      $$('#lang-pick button, #entry-lang button').forEach(b =>
        b.classList.toggle('on', b.dataset.lang === getLang()));
    };
    $$('#lang-pick button, #entry-lang button').forEach(b => {
      b.onclick = () => setLang(b.dataset.lang);
    });
    applyStatic();
    paint();
    onLangChange(() => {
      paint();
      applyStatic();
      // Everything drawn from JavaScript has to be redrawn, or half the
      // interface stays in the previous language — which is exactly the
      // failure this whole layer exists to prevent.
      if (this.slot) this.slotStrip(this.grid || { tables: [], party_size: this.slot.party,
                                                   date: this.slot.date, time: this.slot.time });
      else if (this.live) this.strip(this.live);
      if (this.panelId) this.panel(this.panelId, true);
      if (this.book) this.renderBooking();
      this.zoneButtons();
      this.renderMenu(true);
      if ($('#aboutpanel') && !$('#aboutpanel').classList.contains('hidden')) this.renderAbout();
      const hint = $('#sb-note');
      if (hint && !this.slot) hint.textContent = T('av.livenow');
    });
  }

  zoneButtons() {
    const zb = $('#zones');
    if (!zb) return;
    const current = (zb.querySelector('button.on') || {}).dataset;
    zb.innerHTML = '<button data-z="all"' + (!current || current.z === 'all' ? ' class="on"' : '') + '>' +
      esc(T('zones.all')) + '</button>' +
      this.zones.map(z => '<button data-z="' + esc(z.id) + '"' +
        (current && current.z === z.id ? ' class="on"' : '') + '>' + esc(z.name) + '</button>').join('');
    $$('#zones button').forEach(b => b.onclick = () => {
      $$('#zones button').forEach(x => x.classList.remove('on')); b.classList.add('on');
      this.zone(b.dataset.z);
    });
  }

  // ------------------------------------------------- date / time / guests
  /**
   * The slot picker. Choosing a date, a time and a party size switches the
   * whole room from "what is happening now" to "what can I book then" — and
   * says so in words under the controls, so the colours are never ambiguous.
   */
  wireSlotBar() {
    const dateEl = $('#sb-date'), timeEl = $('#sb-time'), partyEl = $('#sb-party');
    if (!dateEl || !timeEl || !partyEl) return;
    const today = (this.venue && this.venue.today) || new Date().toISOString().slice(0, 10);
    const minToday = (this.venue && this.venue.min_time_today) || '00:00';
    const slots = (this.venue && this.venue.slots) || [];
    // If the kitchen has stopped seating for today, open on tomorrow rather
    // than on an empty list of times the guest cannot choose from.
    const laterToday = slots.some(s => s >= minToday);
    const nextDay = new Date(today + 'T12:00:00');
    nextDay.setDate(nextDay.getDate() + 1);
    dateEl.min = today;
    dateEl.value = laterToday ? today : nextDay.toISOString().slice(0, 10);
    const maxParty = ((this.venue && this.venue.service) || {}).max_party || 20;
    partyEl.innerHTML = Array.from({ length: Math.min(maxParty, 12) }, (_, i) => i + 1)
      .map(n => '<option' + (n === 2 ? ' selected' : '') + '>' + n + '</option>').join('');

    const fillTimes = () => {
      // Never offer a time the restaurant's own clock has already passed.
      const usable = dateEl.value === today ? slots.filter(s => s >= minToday) : slots;
      const keep = timeEl.value;
      timeEl.innerHTML = usable.map(s => '<option>' + s + '</option>').join('') ||
        '<option value="">—</option>';
      if (usable.indexOf(keep) >= 0) timeEl.value = keep;
      $('#sb-go').disabled = !usable.length;
    };
    fillTimes();

    /* Choosing a time IS the request. The room used to keep showing live
       occupancy until you also found and pressed "Show tables", so a guest
       who picked 20:00 sat looking at a room full of green lamps that were
       answering a different question entirely. Any change to the date, the
       time or the party size now recolours the room straight away; the
       button stays because it says out loud what the picker does. */
    const apply = () => {
      if (!timeEl.value) return;
      this.slot = { date: dateEl.value, time: timeEl.value,
                    party: parseInt(partyEl.value, 10) || 2 };
      $('#slotbar').classList.add('slot-mode');
      this.pullAvailability();
    };
    const applySoon = () => { clearTimeout(this._slotT); this._slotT = setTimeout(apply, 120); };

    dateEl.onchange = () => { fillTimes(); applySoon(); };
    timeEl.onchange = applySoon;
    partyEl.onchange = applySoon;
    $('#sb-go').onclick = apply;

    $('#sb-live').onclick = () => {
      clearTimeout(this._slotT);
      this.slot = null;
      this.grid = null;
      this._slotSeq = (this._slotSeq || 0) + 1;   // abandon any answer in flight
      $('#slotbar').classList.remove('slot-mode');
      const note = $('#sb-note');
      if (note) note.textContent = T('av.livenow');
      if (this._pull) this._pull();
    };
  }

  startHoldTimer() {
    this.stopHoldTimer();
    const tick = () => {
      const el = $('#r-timer');
      if (!el || !this.book || !this.book.holdUntil) return this.stopHoldTimer();
      const left = Math.max(0, Math.round((this.book.holdUntil - Date.now()) / 1000));
      el.textContent = Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
      el.className = 'bk-timer' + (left < 60 ? ' low' : '');
      if (left <= 0) {
        this.stopHoldTimer();
        const note = $('#r-note');
        if (note) note.textContent = 'The hold expired. Go back and pick a time again.';
        const c = $('#r-confirm'); if (c) c.disabled = true;
      }
    };
    tick();
    this._holdTimer = setInterval(tick, 1000);
  }

  stopHoldTimer() { clearInterval(this._holdTimer); this._holdTimer = null; }

  /** unix seconds, unix milliseconds or an ISO string -> milliseconds, or 0 */
  expiryMs(v) {
    if (v == null) return 0;
    const n = typeof v === 'number' ? v : parseFloat(v);
    if (isFinite(n) && String(v).indexOf('-') < 0) {
      const ms = n > 1e11 ? n : n * 1000;         // already ms, or seconds
      return ms > Date.now() ? ms : 0;
    }
    const p = Date.parse(v);
    return isFinite(p) && p > Date.now() ? p : 0;
  }

  closePanel() {
    if (this.panelId && this.tm.byId[this.panelId]) this.tm.byId[this.panelId].ring.material.opacity = 0;
    this.panelId = null; this.tm.pinned = null; $('#panel').classList.add('hidden');
  }

  toast(msg) {
    const t = $('#toast'); if (!t) return;
    t.textContent = msg; t.classList.remove('hidden');
    clearTimeout(this._tt); this._tt = setTimeout(() => t.classList.add('hidden'), 4200);
  }

  /** only the point lights nearest the camera's focus are live; the rest stay emissive + halo */
  cullLights() {
    if (!this.tm) return;
    const focus = this.cam.controls.target;
    if (!this._tableLights) {
      this._tableLights = Object.values(this.tm.byId).map(e => e.light).filter(Boolean);
      this._lampLights = this.rest.lampLights.slice();
    }
    const wp = new THREE.Vector3();
    const byDist = (list, keep) => {
      const scored = list.map(l => { l.getWorldPosition(wp); return { l, d: wp.distanceToSquared(focus) }; });
      scored.sort((a, b) => a.d - b.d);
      scored.forEach((s, i) => { s.l.visible = i < keep; });
    };
    byDist(this._tableLights, this.Q.tableLights);
    byDist(this._lampLights, this.Q.lampLights);
  }

  // ----------------------------------------------------------------- tick
  tick(dt, t) {
    this._cullN = (this._cullN || 0) + 1;
    if (this._cullN % 20 === 1) this.cullLights();              // three times a second is plenty
    const w = this.weather.update(dt);
    const sun = this.env.apply(w, dt);
    if (this.foliage) { this.foliage.setWind(w.wind, w.windDeg); this.foliage.setWetness(w.wet); this.foliage.update(dt, t); }
    if (this.water) { this.water.setConditions(w.wind, w.rain); this.water.update(dt); }
    if (this.rain) { this.rain.set(Math.max(w.rain, w.snow), w.snow > w.rain, w.wind, w.windDeg); this.rain.update(dt, t); }
    this.mats.setWetness(w.wet);
    this.rest.update(dt, t);
    if (this.glb) this.glb.update(dt);            // walk cycles, fans, curtains from Blender
    if (this.baku) {
      this.baku.update(dt, t);
      // the city, and the far water, take the colour of the sky they sit in
      const haze = this.sm.scene.fog ? this.sm.scene.fog.color : null;
      this.baku.setTime(sun.dayness, haze);
      if (this.water && this.water.setHaze) this.water.setHaze(haze);
    }
    if (this.tm) this.tm.update(dt, t);
    if (this.people) this.people.update(dt);
    if (this.clothedPeople) this.clothedPeople.update(dt, t, this.weather && this.weather.state);
    this.halos.setGlobal(0.35 + 0.65 * (1 - sun.dayness));
    // umbrellas lean a touch in strong wind
    if (this.rest.umbrellas.length) {
      const lean = Math.min(0.08, w.wind / 600) * Math.sin(t * 0.6);
      for (const u of this.rest.umbrellas) u.rotation.z = lean;
    }
    this.cam.update(dt);
    // the DOM is touched only when the text actually changes
    const label = w.label + (w.source === 'demo' ? '' : ' \u00b7 ' + (w.source || ''));
    if (label !== this._wx) { this._wx = label; const wl = $('#wx-live'); if (wl) wl.textContent = label; }
    this.diag(dt, w);
  }

  diag(dt, w) {
    const el = $('#diag');
    if (!el || el.classList.contains('hidden')) return;
    this._fpsAcc = (this._fpsAcc || 0) + dt; this._fpsN = (this._fpsN || 0) + 1;
    if (this._fpsAcc < 0.5) return;
    const fps = Math.round(this._fpsN / this._fpsAcc); this._fpsAcc = 0; this._fpsN = 0;
    const info = this.sm.renderer.info;
    const leaves = this.foliage && this.foliage.leaves ? this.foliage.leaves.count : 0;
    el.textContent =
      'SUFRA 360 build ' + BUILD + ' \u00b7 ' + (this.useGLB
        ? 'Blender venue (' + (this.glbInfo ? this.glbInfo.triangles / 1000 | 0 : '?') + 'k tris, ' +
          (this.glbFurniture ? 'its own furniture' : 'furniture from the database') + ')'
        : 'procedural room') +
      ' \u00b7 quality ' + this.quality + ' \u00b7 pixel ratio ' + this.sm.dpr.toFixed(2) + (this.sm.adaptive ? ' (adaptive)' : '') + '\n' +
      'fps ' + fps + ' \u00b7 draw calls ' + info.render.calls + ' \u00b7 triangles ' + (info.render.triangles / 1000).toFixed(0) + 'k\n' +
      'leaf cards ' + leaves + ' \u00b7 wind ' + w.wind.toFixed(0) + ' km/h @ ' + w.windDeg.toFixed(0) + '\u00b0\n' +
      'weather ' + w.label + ' \u00b7 cloud ' + w.cloud.toFixed(2) + ' \u00b7 rain ' + w.rain.toFixed(2) + ' \u00b7 wet ' + w.wet.toFixed(2) + ' \u00b7 fog ' + w.fog.toFixed(2) + '\n' +
      'sun ' + this.env.sun.intensity.toFixed(2) + ' \u00b7 exposure ' + this.sm.renderer.toneMappingExposure.toFixed(2) + '\n' +
      'people ' + (this.people && this.people.enabled
        ? (this.people.waiters.length + Object.values(this.people.guests).reduce((n, g) => n + g.length, 0)) + ' walking/seated'
        : 'none loaded') + '\n' +
      'tables ' + (this.tm ? Object.keys(this.tm.byId).length : 0) + ' \u00b7 halos ' + this.halos.count +
        ' \u00b7 stages failed ' + this.stages.filter(s => !s.ok).length + ' \u00b7 asset fallbacks ' + this.notes.length;
  }
}

window.addEventListener('DOMContentLoaded', () => {
  const app = new Sufra360();
  window.sufra360 = app;
  app.boot().catch(e => {
    console.error(e);
    if (app._sceneShown) app.toast('Part of the room failed to build (see console).');
    else app.fallback('The 3D view did not start: ' + (e && e.message ? e.message : e));
  });
});
