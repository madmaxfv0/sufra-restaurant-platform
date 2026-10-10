import { LivingMap, loadImage } from './map.js?v=6';
import { PanoViewer } from './pano.js?v=6';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const show = (s, on = true) => {
  const el = typeof s === 'string' ? $(s) : s;
  if (el) el.classList.toggle('hidden', !on);
  return el;
};

// ───────────────────────────────── state ──────────────────────────────
const KEY = 'sufra.booking.v1';
const S = Object.assign({
  date: null, time: '19:30', party: 2, pref: 'best', notes: '', event: 'dinner',
  tableId: null, seatId: null, holdId: null, holdExpires: 0,
  form: {}, view: 'overview',
}, load());

function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }
function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }

// ───────────────────────────────── api ────────────────────────────────
const api = {
  async get(u) { const r = await fetch(u, { credentials: 'same-origin' }); return r.json(); },
  async send(m, u, b, hdr) {
    const r = await fetch(u, {
      method: m, credentials: 'same-origin',
      headers: Object.assign({ 'Content-Type': 'application/json' }, hdr || {}),
      body: b ? JSON.stringify(b) : undefined,
    });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, body: j };
  },
};

let VENUE = null, TABLES = [], TMAP = {}, ZONES = {}, STATES = {},
    GOOGLE = { enabled: false }, REAL = { enabled: false };
let map = null, pano = null, seats = [], curSeats = [];

// ───────────────────────────────── boot ───────────────────────────────
(async function boot() {
  try {
    const v = await api.get('/api/public/venue');
    VENUE = v;
    ZONES = Object.fromEntries(v.zones.map(z => [z.id, z]));
    TABLES = await api.get('/api/public/tables');
    TMAP = Object.fromEntries(TABLES.map(t => [t.id, t]));
    GOOGLE = await api.get('/api/public/google').catch(() => ({ enabled: false }));
    if (GOOGLE.enabled) $('#ov-arrival').classList.remove('hidden');
    REAL = await api.get('/api/public/real-venue').catch(() => ({ enabled: false }));
    show('#ov-real', !!REAL.enabled);
    if (!S.date || S.date < v.today) S.date = v.today;
    // build 9: the 360 view's Reserve button arrives with the guest's date, time and party already chosen
    safely('deep link criteria', () => {
      const q = new URLSearchParams(location.search);
      if (q.get('date') && q.get('date') >= v.today) S.date = q.get('date');
      if (q.get('time') && v.slots.indexOf(q.get('time')) >= 0) S.time = q.get('time');
      const p = parseInt(q.get('party'), 10); if (p >= 1 && p <= 8) S.party = p;
      if (q.get('date') || q.get('time') || q.get('party')) save();
    });

    buildCriteria(v);
    map = new LivingMap($('#map'), {
      onPick: pickTable, onHover: () => {},
      onDeepZoom: t => {                      // zoom right in and you sit down
        if (!$('#seatview').classList.contains('hidden')) return;
        S.tableId = t.id; save();
        openSeatView(t.id);
        toast('Table ' + t.label + ' — look around');
      },
    });
    map.setTables(TABLES);
    await map.load(v);
    map.fit();

    // Anything below here is an enhancement. If one of them fails on this
    // browser the booking flow must still work, so each is isolated.
    safely('panorama viewer', () => { pano = new PanoViewer($('#pano')); });
    safely('interface', wire);
    safely('realtime', connectSocket);

    await refresh();

    safely('weather', () => {
      loadWeather();
      setInterval(loadWeather, 10 * 60 * 1000);
    });
    await safelyAsync('saved hold', restoreHold);
    safely('routing', () => route(location.pathname));
    safely('deep link', () => {
      const want = new URLSearchParams(location.search).get('table');
      if (want && TMAP[want]) { route('/reserve'); map.focusTable(want, 2.8); setTimeout(() => pickTable(TMAP[want]), 500); }
    });

    $('#loader').classList.add('gone');
    setTimeout(() => { const l = $('#loader'); if (l) l.remove(); }, 700);

    if (BOOT_WARNINGS.length) {
      toast('Loaded, but ' + BOOT_WARNINGS.join(' and ') + ' did not start.', true);
    }
  } catch (e) {
    bootFailure(e);
  }
})();

const BOOT_WARNINGS = [];

function safely(what, fn) {
  try { return fn(); } catch (e) {
    console.error('[' + what + ']', e);
    BOOT_WARNINGS.push(what);
  }
}

async function safelyAsync(what, fn) {
  try { return await fn(); } catch (e) {
    console.error('[' + what + ']', e);
    BOOT_WARNINGS.push(what);
  }
}

function bootFailure(e) {
  const msg = (e && e.message) || String(e);
  const stack = ((e && e.stack) || '').split('\n').slice(0, 4).join('\n');
  const l = $('#loader');
  if (!l) return;
  l.classList.remove('gone');
  l.innerHTML =
    '<div style="max-width:min(90vw,42rem);text-align:left;font-family:var(--sans)">' +
    '<p style="color:#e0817b;letter-spacing:.16em;text-transform:uppercase;font-size:.7rem">' +
    'The venue did not load</p>' +
    '<p style="color:#eaeef6;font-size:1rem;margin:.6rem 0">' + escapeHtml(msg) + '</p>' +
    '<pre style="color:#9aa7bd;font-size:.72rem;line-height:1.5;white-space:pre-wrap;' +
    'background:rgba(255,255,255,.04);padding:.8rem;border-radius:10px;overflow:auto">' +
    escapeHtml(stack) + '</pre>' +
    '<p style="color:#9aa7bd;font-size:.78rem;margin-top:1rem">' +
    'The server is probably fine. Send me this message and I will fix it. ' +
    'You can also try <b>Cmd+Shift+R</b> to clear the cached files.</p></div>';
}

function buildCriteria(v) {
  const d = $('#f-date');
  d.value = S.date; d.min = v.today;
  const t = $('#f-time');
  t.innerHTML = v.slots.map(s => `<option${s === S.time ? ' selected' : ''}>${s}</option>`).join('');
  const p = $('#f-party');
  p.innerHTML = [1, 2, 3, 4, 5, 6, 7, 8].map(n =>
    `<option value="${n}"${n === S.party ? ' selected' : ''}>${n}</option>`).join('');
  $('#f-pref').value = S.pref;
}

// ─────────────────────────────── refresh ──────────────────────────────
let refreshing = null;
async function refresh() {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const q = `date=${S.date}&time=${S.time}&party_size=${S.party}`;
    const a = await api.get('/api/public/availability?' + q);
    STATES = Object.fromEntries(a.tables.map(r => [r.table_id, r]));
    map.setStates(STATES);
    if (S.tableId && $('#card').classList.contains('hidden') === false) renderCard(S.tableId);
    map.setStates(STATES);
    refreshing = null;
  })();
  return refreshing;
}

async function recommend(limit = 6) {
  const r = await api.send('POST', '/api/public/recommend-tables', {
    date: S.date, time: S.time, party_size: S.party,
    preference: S.pref, notes: S.notes, limit, event: S.event,
  });
  return r.body;
}

// ─────────────────────────────── routing ──────────────────────────────
function route(path, push = false) {
  const known = ['/', '/explore', '/reserve', '/menu', '/about'];
  if (push && location.pathname !== path) history.pushState({}, '', path);
  ['#overview', '#seatview', '#confirm', '#menuscreen', '#about', '#arrival',
   '#realview'].forEach(s => show(s, false));
  show('#card', false); show('#form', false);
  const chrome = path !== '/' && path !== '/menu' && path !== '/about';
  show('#topbar', chrome); show('#legend', chrome); show('#guide', chrome);
  show('#wx', chrome); show('#eventbar', chrome && S.event !== 'dinner');
  document.body.classList.toggle('dim', !chrome && path !== '/');
  pano.stop();

  if (path === '/' || path === '/map') {
    $('#overview').classList.remove('gone'); show('#overview', true);
    map.fit(true);
  } else if (path === '/menu') { show('#menuscreen', true); renderMenu(); }
  else if (path === '/about') { show('#about', true); }
  else { $('#overview').classList.add('gone'); }
  S.view = path; save();
}
window.addEventListener('popstate', () => route(location.pathname));

// ───────────────────────────── interactions ───────────────────────────
function wire() {
  $$('[data-go]').forEach(b => b.addEventListener('click', async () => {
    const g = b.dataset.go;
    if (g === 'menu') return route('/menu', true);
    if (g === 'arrival') return openArrival();
    if (g === 'tour') { route('/explore', true); return openTour(); }
    if (g === 'real') return openReal();
    if (g === 'about') return route('/about', true);
    route(g === 'reserve' ? '/reserve' : '/explore', true);
    if (g === 'reserve') {
      const rec = await recommend(1);
      if (rec.recommended.length) {
        map.focusTable(rec.recommended[0].table.id, 2.6);
        setTimeout(() => pickTable(rec.recommended[0].table), 600);
      }
    } else map.moveTo(468, 560, 1.7, 1400);
  }));

  const on = (sel, handler, evt) => {
    const el = $(sel);
    if (el) el.addEventListener(evt || 'click', handler);
  };

  $('#home').onclick = () => route('/map', true);
  $('#btn-menu').onclick = () => route('/menu', true);
  $('#btn-fit').onclick = () => map.fit(true);
  $('#mn-back').onclick = () => route(S.tableId ? '/reserve' : '/', true);
  $('#ab-back').onclick = () => route('/map', true);

  on('#f-event', async () => {
    S.event = $('#f-event').value; save();
    const rec = await recommend(8);
    const cfg = rec.event_config || {};
    map.setHighlight(rec.recommended.map(r => r.table.id));
    const bar = $('#eventbar');
    if (S.event === 'dinner') show('#eventbar', false);
    else {
      bar.innerHTML = `<b>${escapeHtml(cfg.name || '')}</b> — ${escapeHtml(cfg.blurb || '')}` +
        (cfg.capacity ? ` · up to ${cfg.capacity} · min spend ${(VENUE && VENUE.venue && VENUE.venue.pricing && VENUE.venue.pricing.symbol) || ''}${cfg.min_spend}` : '');
      show('#eventbar', true);
    }
    toast(`${cfg.name || 'Dinner'}: ${rec.eligible_count} tables in play`);
  }, 'change');

  ['f-date', 'f-time', 'f-party', 'f-pref'].forEach(id => {
    on('#' + id, async e => {
      const val = (sel, dflt) => { const el = $(sel); return el ? el.value : dflt; };
      S.date = val('#f-date', S.date); S.time = val('#f-time', S.time);
      S.party = +val('#f-party', S.party); S.pref = val('#f-pref', S.pref);
      save();
      await releaseHold(true);
      await refresh();
      if (S.tableId) renderCard(S.tableId);
      const rec = await recommend(6);
      map.setHighlight(rec.recommended.map(r => r.table.id));
    }, 'change');
  });

  $$('[data-close]').forEach(b => b.onclick = () => {
    show('#' + b.dataset.close, false);
    if (b.dataset.close === 'card') { S.tableId = null; map.setSelected(null); save(); }
  });

  $('#c-seat').onclick = () => openSeatView(S.tableId);
  $('#c-hold').onclick = () => beginHold(S.tableId);
  $('#c-alts').onclick = () => showAlternatives(S.tableId);
  $('#holdrelease').onclick = () => releaseHold();

  $('#sv-back').onclick = () => {
    show('#seatview', false); pano.stop(); setRealView(false);
    stopMarks(); openCard(S.tableId);
  };
  $('#sv-real').onclick = e => setRealView(!realOn, e.target);
  $('#ar-back').onclick = () => { show('#arrival', false); $('#ar-frame').src = 'about:blank'; };
  $('#ar-street').onclick = () => arrivalMode('street');
  $('#ar-air').onclick = () => arrivalMode('air');
  $('#sv-reserve').onclick = () => { show('#seatview', false); pano.stop(); beginHold(S.tableId); };
  $('#sv-vr').onclick = e => {
    pano.setStereo(!pano.stereo); e.target.classList.toggle('on', pano.stereo);
    toast(pano.stereo ? 'Split screen on — put the phone in a headset' : 'Split screen off');
  };
  $('#sv-gyro').onclick = async e => {
    if (pano.gyro) { pano.disableGyro(); e.target.classList.remove('on'); return; }
    const ok = await pano.enableGyro();
    e.target.classList.toggle('on', ok);
    toast(ok ? 'Move your phone to look around' : 'No motion sensor available');
  };
  $('#sv-full').onclick = () => {
    const el = $('#seatview');
    if (!document.fullscreenElement) (el.requestFullscreen ? el.requestFullscreen().catch(() => {}) : null);
    else (document.exitFullscreen ? document.exitFullscreen() : null);
  };

  $('#fm-submit').onclick = submitReservation;
  $('#guide-go').onclick = askGuide;
  $('#guide-q').addEventListener('keydown', e => { if (e.key === 'Enter') askGuide(); });

  $('#cf-done').onclick = () => { show('#confirm', false); route('/', true); };
  $('#cf-view').onclick = () => {
    show('#confirm', false); route('/explore', true);
    if (lastRes) { map.focusTable(lastRes.table_id, 3.2); pickTable(TMAP[lastRes.table_id]); }
  };
  $('#cf-ics').onclick = () => lastRes && downloadICS(lastRes);
  $('#cf-cancel').onclick = cancelBooking;
  $('#ab-find').onclick = findBooking;
  $('#btn-tour').onclick = openTour;
  $('#sv-walk').onclick = () => openReal();
  $('#rv-back').onclick = closeReal;
  $('#rv-tables').onclick = e => {
    const on = $('#rv-list').classList.toggle('hidden');
    e.target.classList.toggle('on', !on);
  };
  $('#rv-full').onclick = () => {
    const el = $('#realview');
    if (!document.fullscreenElement) (el.requestFullscreen ? el.requestFullscreen().catch(() => {}) : null);
    else (document.exitFullscreen ? document.exitFullscreen() : null);
  };
  $('#rv-vp').addEventListener('change', () => loadViewpoint($('#rv-vp').value));
}

// ───────────────────────────── table card ─────────────────────────────
function pickTable(t) {
  S.tableId = t.id; S.seatId = null; save();
  map.setSelected(t.id);
  if (map.cam.zoom < 2.2) map.focusTable(t.id, 2.8);
  openCard(t.id);
}

function openCard(id) {
  if (!id) return;
  route(location.pathname === '/' ? '/explore' : location.pathname);
  renderCard(id);
  show('#card', true);
}

async function renderCard(id) {
  const t = TMAP[id], st = STATES[id] || { state: 'UNKNOWN' };
  const z = ZONES[t.zone] || {};
  $('#c-label').textContent = t.label;
  $('#c-zone').textContent = z.name || t.zone;

  const stateText = { AVAILABLE: 'Available', RESERVED: 'Reserved', HELD: 'Being booked',
                      HELD_BY_YOU: 'Held for you', INCOMPATIBLE: 'Wrong size', UNKNOWN: '—' };
  const el = $('#c-state');
  el.textContent = stateText[st.state];
  el.className = 'pill' + (st.state === 'HELD_BY_YOU' ? ' held'
    : ['RESERVED', 'HELD', 'INCOMPATIBLE'].includes(st.state) ? ' gone' : '');

  const sc = t.scores;
  const traits = [];
  if (sc.quiet > 0.7) traits.push('Quiet');
  if (sc.lively > 0.55) traits.push('Lively');
  if (sc.window_proximity > 0.6) traits.push('By a window');
  if (sc.romantic > 0.72) traits.push('Romantic');
  if (sc.privacy > 0.7) traits.push('Private');
  if (t.premium_view) traits.push('Premium view');
  if (t.accessible) traits.push('Step-free');
  if (z.outdoor) traits.push('Outdoors');
  $('#c-traits').innerHTML = traits.map(x => `<li>${x}</li>`).join('');

  const facts = [
    ['Seats', `${t.min_party}–${t.max_party} guests`],
    ['Room', z.name || t.zone],
    ['Shape', t.shape === 'round' ? 'Round' : 'Rectangular'],
    ['Noise', bar(sc.noise)],
    ['View', bar(sc.view)],
    ['Privacy', bar(sc.privacy)],
  ];
  if (st.state === 'RESERVED' || st.state === 'HELD') {
    facts.push(['Next free', st.next_available || 'not today']);
  }
  facts.push(['Data', t.verification]);
  $('#c-facts').innerHTML = facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');

  const rec = await recommend(8);
  const mine = rec.recommended.find(r => r.table.id === id);
  const why = $('#c-why');
  if (mine && mine.why.length) {
    why.textContent = 'Matches your preference: ' + mine.why.join(', ') + '.';
    why.classList.remove('hidden');
  } else why.classList.add('hidden');

  const bookable = st.state === 'AVAILABLE' || st.state === 'HELD_BY_YOU';
  $('#c-hold').disabled = !bookable;
  $('#c-hold').textContent = st.state === 'HELD_BY_YOU' ? 'Continue booking'
    : bookable ? 'Reserve this table' : (st.reason || 'Unavailable');
  $('#c-altlist').innerHTML = '';
}

function bar(v) {
  const n = Math.round(v * 5);
  return '<span style="letter-spacing:2px;color:var(--gold)">' +
    '●'.repeat(n) + '<span style="opacity:.25">' + '●'.repeat(5 - n) + '</span></span>';
}

async function showAlternatives(id) {
  const rec = await recommend(8);
  const t = TMAP[id];
  const near = rec.recommended.filter(r => r.table.id !== id)
    .map(r => ({ ...r, d: Math.hypot(r.table.x - t.x, r.table.y - t.y) }))
    .sort((a, b) => a.d - b.d).slice(0, 3);
  if (!near.length) return toast('No other tables free at that time.', true);
  $('#c-altlist').innerHTML = near.map(r =>
    `<div class="alt" data-t="${r.table.id}"><span><b>Table ${r.table.label}</b>
     <small>${(ZONES[r.table.zone] || {}).name || r.table.zone} · ${r.why.join(', ') || 'available'}</small>
     </span><span style="color:var(--gold)">→</span></div>`).join('');
  $$('#c-altlist .alt').forEach(el =>
    el.onclick = () => pickTable(TMAP[el.dataset.t]));
}

// ───────────────────────────── seat view ──────────────────────────────
async function openSeatView(id) {
  const t = TMAP[id];
  curSeats = await api.get(`/api/public/tables/${id}/seats`);
  $('#sv-label').textContent = t.label;
  show('#seatview', true);
  renderSeatPicker(0);
  pano.resize();
  const ok = await pano.load(curSeats[0].panorama, curSeats[0].yaw);
  if (!ok) toast('That 360 image is missing — run python3 run.py --rebuild', true);
  S.seatId = curSeats[0].id; save();
  renderCompass(t);
  await refresh();
  startMarks(t);
  $('#sv-real').classList.toggle('hidden', !realAvailable());
  $('#sv-walk').classList.toggle('hidden', !REAL.enabled);
  setRealView(false);
}

function renderSeatPicker(active) {
  $('#sv-seats').innerHTML = curSeats.map((s, i) =>
    `<button data-i="${i}" class="${i === active ? 'on' : ''}">${s.label}</button>`).join('');
  $('#sv-seat').textContent = curSeats[active].label;
  $$('#sv-seats button').forEach(b => b.onclick = async () => {
    const i = +b.dataset.i;
    renderSeatPicker(i);
    S.seatId = curSeats[i].id; save();
    if (realOn) setRealView(true); else pano.lookAt(curSeats[i].yaw, 800);
  });
}

function renderCompass(t) {
  const b = t.bearings;
  const items = [['Window', b.window], ['Bar', b.bar], ['Entrance', b.entrance],
                 ['Kitchen', b.kitchen], ['Water', b.water]];
  const c = $('#compass');
  c.innerHTML = items.map(([n, deg]) =>
    `<div class="bearing" data-deg="${deg}">${n}</div>`).join('');
  clearInterval(renderCompass._t);
  renderCompass._t = setInterval(() => {
    if ($('#seatview').classList.contains('hidden')) return;
    const w = window.innerWidth;
    $$('#compass .bearing').forEach(el => {
      let d = ((+el.dataset.deg - pano.yaw + 540) % 360) - 180;
      const visible = Math.abs(d) < pano.fov * 0.62;
      el.style.opacity = visible ? '1' : '0';
      el.style.left = (w / 2 + (d / (pano.fov * 0.5)) * (w / 2)) + 'px';
      el.style.top = '-16vh';
    });
  }, 60);
}

// ──────────────────────── google street view ──────────────────────────
// Google imagery is shown through the Maps Embed API in an iframe. It is
// never downloaded, cached or altered - that is what the licence allows.
let realOn = false;

function gKeyless(kind, opt) {
  // Google Maps' public share-and-embed endpoints. No key, no billing.
  const L = GOOGLE.location || {};
  const at = `${L.lat},${L.lng}`;
  const named = encodeURIComponent(GOOGLE.place_query || '');
  if (kind === 'streetview') {
    if (!hasCoords()) return `https://maps.google.com/maps?q=${named}&z=18&output=embed`;
    const h = Math.round(opt.heading || 0);
    return `https://maps.google.com/maps?q=&layer=c&cbll=${at}` +
           `&cbp=11,${h},0,0,0&output=svembed`;
  }
  if (kind === 'air') {
    return hasCoords()
      ? `https://maps.google.com/maps?q=${at}&t=k&z=19&output=embed`
      : `https://maps.google.com/maps?q=${named}&t=k&z=19&output=embed`;
  }
  return `https://maps.google.com/maps?q=${encodeURIComponent(
    GOOGLE.place_query || '')}&z=18&output=embed`;
}

function gApi(mode, params) {
  const q = new URLSearchParams(Object.assign({ key: GOOGLE.api_key }, params));
  return `https://www.google.com/maps/embed/v1/${mode}?${q}`;
}

function gStreetView(heading) {
  if (GOOGLE.mode === 'api' && hasCoords()) {
    const m = (GOOGLE.table_panos || {})[S.tableId];
    const L = GOOGLE.location || {};
    if (m && m.pano_id) return gApi('streetview', {
      pano: m.pano_id, heading: Math.round((m.heading || 0) + heading) % 360,
      pitch: m.pitch || 0, fov: 90 });
    if (GOOGLE.interior_pano_id) return gApi('streetview', {
      pano: GOOGLE.interior_pano_id, heading: Math.round(heading), fov: 90 });
    if (L.lat != null) return gApi('streetview', {
      location: `${L.lat},${L.lng}`, heading: Math.round(heading), fov: 90 });
  }
  return gKeyless('streetview', { heading });
}

function hasCoords() {
  const L = GOOGLE.location || {};
  return L.lat != null && L.lng != null;
}

function realAvailable() {
  return !!(GOOGLE.enabled && GOOGLE.use_real &&
            (hasCoords() || GOOGLE.place_query));
}

function setRealView(on, btn) {
  realOn = !!(on && realAvailable());
  const f = $('#gsv');
  if (realOn) {
    const seat = curSeats.find(s => s.id === S.seatId) || curSeats[0] || { yaw: 0 };
    f.src = gStreetView(seat.yaw);
    show('#gsv', true); pano.stop();
  } else {
    show('#gsv', false); f.src = 'about:blank'; pano.start();
  }
  const b = btn || $('#sv-real');
  if (b) b.classList.toggle('on', realOn);
  $('.sv-note').textContent = realOn
    ? `Live Street View of ${GOOGLE.display_name} — imagery © Google, embedded, not modified`
    : 'Placeholder capture — replaced by the real 360 scan of this table.';
}

function openArrival() {
  if (!realAvailable()) return toast('No real venue configured.', true);
  $('#ar-name').textContent =
    `${GOOGLE.display_name} · ${GOOGLE.display_city}`;
  show('#arrival', true);
  arrivalMode('street');
}

function arrivalMode(mode) {
  $('#ar-street').classList.toggle('on', mode === 'street');
  $('#ar-air').classList.toggle('on', mode === 'air');
  const L = GOOGLE.location || {};
  let src;
  if (mode === 'street') {
    src = (GOOGLE.mode === 'api' && hasCoords())
      ? (GOOGLE.exterior_pano_id
          ? gApi('streetview', { pano: GOOGLE.exterior_pano_id, fov: 90 })
          : gApi('streetview', { location: `${L.lat},${L.lng}`, fov: 90 }))
      : gKeyless('streetview', { heading: 0 });
  } else {
    src = (GOOGLE.mode === 'api' && hasCoords())
      ? gApi('view', { center: `${L.lat},${L.lng}`, zoom: 19, maptype: 'satellite' })
      : gKeyless('air');
  }
  $('#ar-frame').src = src;
}

// ─────────────────────────────── holds ────────────────────────────────
let holdTimer = null;

async function beginHold(id) {
  const r = await api.send('POST', '/api/public/holds', {
    table_id: id, date: S.date, time: S.time, party_size: S.party,
  });
  if (!r.ok) {
    toast(r.body.message || 'That table just went.', true);
    await refresh();
    return showAlternatives(id);
  }
  S.holdId = r.body.hold.id;
  S.holdExpires = Date.now() + r.body.hold.seconds_remaining * 1000;
  S.tableId = id; save();
  startHoldClock();
  await refresh();
  openForm();
}

function startHoldClock() {
  clearInterval(holdTimer);
  show('#holdchip', true);
  const t = TMAP[S.tableId];
  $('#holdtext').textContent = `Holding table ${t ? t.label : ''}`;
  const tick = () => {
    const left = Math.max(0, Math.round((S.holdExpires - Date.now()) / 1000));
    $('#holdclock').textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    if (left <= 0) {
      clearInterval(holdTimer); show('#holdchip', false);
      S.holdId = null; save(); refresh();
      toast('Your hold expired. The table is open again.', true);
      show('#form', false);
    }
  };
  tick(); holdTimer = setInterval(tick, 1000);
}

async function releaseHold(silent) {
  if (!S.holdId) return;
  await api.send('DELETE', '/api/public/holds/' + S.holdId);
  S.holdId = null; S.holdExpires = 0; save();
  clearInterval(holdTimer); show('#holdchip', false);
  if (!silent) { toast('Hold released.'); show('#form', false); await refresh(); }
}

async function restoreHold() {
  if (!S.holdId) return;
  const h = await api.get('/api/public/holds/' + S.holdId).catch(() => null);
  if (h && h.live) {
    S.holdExpires = Date.now() + h.seconds_remaining * 1000;
    startHoldClock();
  } else { S.holdId = null; save(); }
}

// ──────────────────────────── booking form ────────────────────────────
function openForm() {
  const t = TMAP[S.tableId], z = ZONES[t.zone] || {};
  $('#fm-summary').textContent =
    `Table ${t.label} · ${z.name || t.zone} · ${fmtDate(S.date)} at ${S.time} · ` +
    `${S.party} ${S.party === 1 ? 'guest' : 'guests'}`;
  const f = S.form || {};
  ['first', 'last', 'email', 'phone', 'allergies', 'dietary', 'access', 'notes']
    .forEach(k => { if (f[k]) $('#fm-' + k).value = f[k]; });
  show('#card', false);
  show('#form', true);
  $('#fm-error').classList.add('hidden');
}

function collectForm() {
  const g = id => $('#fm-' + id).value.trim();
  S.form = { first: g('first'), last: g('last'), email: g('email'), phone: g('phone'),
             allergies: g('allergies'), dietary: g('dietary'), access: g('access'),
             notes: g('notes') };
  save();
  return {
    first_name: S.form.first, last_name: S.form.last, email: S.form.email,
    phone: S.form.phone, party_size: S.party, date: S.date, time: S.time,
    table_id: S.tableId, seat_id: S.seatId,
    occasion: $('#fm-occasion').value || null,
    allergies: S.form.allergies || null, dietary: S.form.dietary || null,
    accessibility: S.form.access || null,
    high_chairs: +$('#fm-chairs').value || 0,
    special_request: S.form.notes || null,
    preference: S.pref, marketing_opt_in: $('#fm-marketing').checked,
  };
}

let lastRes = null, idemKey = null;

async function submitReservation() {
  const btn = $('#fm-submit'), err = $('#fm-error');
  const body = collectForm();
  const missing = ['first_name', 'last_name', 'email', 'phone']
    .filter(k => !body[k]);
  if (missing.length) {
    err.textContent = 'Please fill in: ' + missing.map(m => m.replace('_', ' ')).join(', ');
    err.classList.remove('hidden'); return;
  }
  err.classList.add('hidden');
  btn.disabled = true; btn.textContent = 'Confirming…';
  idemKey = idemKey || (Date.now().toString(36) + Math.random().toString(36).slice(2, 10));

  const r = await api.send('POST', '/api/public/reservations', body,
                           { 'Idempotency-Key': idemKey });
  btn.disabled = false; btn.textContent = 'Confirm reservation';

  if (!r.ok) {
    err.textContent = r.body.message ||
      (r.body.fields ? 'Missing: ' + r.body.fields.join(', ') : 'Could not confirm.');
    err.classList.remove('hidden');
    idemKey = null;
    await refresh();
    if (r.status === 409) showAlternatives(S.tableId);
    return;
  }

  lastRes = r.body.reservation;
  idemKey = null;
  clearInterval(holdTimer); show('#holdchip', false);
  S.holdId = null; save();
  await refresh();
  showConfirmation(lastRes);
}

// ─────────────────────────── confirmation ─────────────────────────────
async function showConfirmation(res) {
  show('#form', false); show('#card', false);
  // The booking reference is deliberately not the headline any more: it
  // lives in the restaurant's own book, which is where it is actually
  // needed. No confirmation email or SMS is sent.
  $('#cf-code').textContent = 'Thank you';
  const eyebrow = document.querySelector('.cf-eyebrow');
  if (eyebrow) eyebrow.textContent = 'Your reservation is confirmed';
  $('#cf-name').textContent = `${res.guest.first_name} ${res.guest.last_name}`;
  $('#cf-date').textContent = fmtDate(res.date);
  $('#cf-time').textContent = `${res.time} – ${res.end_time}`;
  $('#cf-party').textContent = `${res.party_size} ${res.party_size === 1 ? 'guest' : 'guests'}`;
  $('#cf-table').textContent = 'Table ' + res.table_label;
  $('#cf-zone').textContent = res.zone_name || res.zone;
  show('#confirm', true);
  drawMiniMap(res.table_id);
}

async function drawMiniMap(tableId) {
  const cv = $('#cf-map'), ctx = cv.getContext('2d');
  const img = map.ground || await loadImage(VENUE.venue.map.image);
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  ctx.drawImage(img, 0, 0, W, H);
  ctx.fillStyle = 'rgba(5,9,17,.55)'; ctx.fillRect(0, 0, W, H);
  const t = TMAP[tableId];
  const sx = t.x / VENUE.venue.map.width * W, sy = t.y / VENUE.venue.map.height * H;
  const g = ctx.createRadialGradient(sx, sy, 1, sx, sy, 46);
  g.addColorStop(0, 'rgba(240,217,168,.85)'); g.addColorStop(1, 'rgba(216,178,108,0)');
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(sx, sy, 46, 0, 6.2832); ctx.fill();
  ctx.strokeStyle = '#f0d9a8'; ctx.lineWidth = 2;
  ctx.beginPath(); ctx.arc(sx, sy, 13, 0, 6.2832); ctx.stroke();
  ctx.fillStyle = '#f0d9a8'; ctx.font = '600 13px ui-sans-serif,sans-serif';
  ctx.textAlign = 'center'; ctx.fillText(t.label, sx, sy - 22);
}

function downloadICS(res) {
  const dt = (d, t) => d.replace(/-/g, '') + 'T' + t.replace(':', '') + '00';
  const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//SUFRA//EN', 'BEGIN:VEVENT',
    'UID:' + res.code + '@sufra', 'DTSTART:' + dt(res.date, res.time),
    'DTEND:' + dt(res.date, res.end_time),
    'SUMMARY:Dinner at Sufra Waterfront (Table ' + res.table_label + ')',
    'DESCRIPTION:Confirmation ' + res.code + ' for ' + res.party_size + ' guests.',
    'LOCATION:' + VENUE.venue.address, 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar' }));
  a.download = 'sufra-' + res.code + '.ics'; a.click();
}

async function cancelBooking() {
  if (!lastRes) return;
  if (!confirm('Cancel booking ' + lastRes.code + '?')) return;
  const r = await api.send('POST', `/api/public/reservations/${lastRes.code}/cancel`);
  if (r.ok) { toast('Booking cancelled.'); show('#confirm', false); await refresh(); route('/', true); }
  else toast('Could not cancel.', true);
}

async function findBooking() {
  const code = $('#ab-code').value.trim().toUpperCase();
  if (!code) return;
  const r = await fetch('/api/public/reservations/' + code);
  if (!r.ok) return ($('#ab-result').textContent = 'No booking with that code.');
  const res = await r.json();
  lastRes = res;
  show('#about', false);
  showConfirmation(res);
}

// ───────────────────────────── venue guide ────────────────────────────
async function askGuide() {
  const q = $('#guide-q').value.trim();
  if (!q) return;
  S.notes = q; save();
  const box = $('#guide-answer');
  box.textContent = 'Looking…'; show('#guide-answer', true);
  const r = await api.send('POST', '/api/public/guide', {
    question: q, date: S.date, time: S.time, party_size: S.party,
    event: S.event });
  const a = r.body;
  map.setHighlight(a.highlight || []);
  if (a.focus) map.focusTable(a.focus, 2.4);
  box.innerHTML = `<div>${escapeHtml(a.message)}</div>` +
    (a.tables && a.tables.length
      ? `<div class="g-tables">${a.tables.map(t =>
          `<button data-t="${t.id}">Table ${t.label}${t.why.length ? ' · ' + t.why[0] : ''}</button>`
        ).join('')}</div>` : '');
  $$('#guide-answer .g-tables button').forEach(b =>
    b.onclick = () => pickTable(TMAP[b.dataset.t]));
  setTimeout(() => show('#guide-answer', false), 14000);
}

// ─────────────────────────────── menu ─────────────────────────────────
let menuCache = null;
async function renderMenu() {
  if (!menuCache) menuCache = await api.get('/api/public/menu');
  const cur = menuCache.currency || '';
  if ($('#mn-body').dataset.done) return;
  $('#mn-body').dataset.done = '1';
  $('#mn-body').innerHTML = menuCache.sections.map(sec => `
    <section class="mn-sec"><h2>${sec.name}</h2><div class="dishes">
    ${sec.dishes.map(d => `
      <article class="dish">
        <img src="${d.image || ('/assets/menu/' + d.id + '.jpg')}" alt="${escapeHtml(d.name)}" loading="lazy"
             onerror="this.style.visibility='hidden'">
        <div class="d-body">
          <span class="d-price">${cur}${d.price.toFixed(2)}</span>
          <h3>${escapeHtml(d.name)}</h3>
          <p>${escapeHtml(d.blurb || '')}</p>
          <div class="tagrow">
            ${(d.diet || []).map(x => `<span class="tag diet">${x.replace('_', ' ')}</span>`).join('')}
            ${(d.allergens || []).map(x => `<span class="tag alg">${x}</span>`).join('')}
          </div>
        </div>
      </article>`).join('')}
    </div></section>`).join('');
}

// ───────────────────────────── realtime ───────────────────────────────
function connectSocket() {
  const pollMs = (VENUE.poll_seconds || 20) * 1000;
  const poll = () => setInterval(() => { if (!document.hidden) refresh(); }, pollMs);

  if (VENUE.realtime === false) {
    // uvicorn has no websocket library installed. Polling covers it, and
    // retrying an endpoint that structurally cannot work just fills the log.
    poll();
    console.info('[realtime] websockets unavailable on the server, polling every '
                 + (pollMs / 1000) + 's');
    return;
  }

  let ws, retry = 0, everOpened = false;
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => { retry = 0; everOpened = true; };
    ws.onmessage = async e => {
      const m = JSON.parse(e.data);
      if (['TABLE_HELD', 'HOLD_RELEASED', 'RESERVATION_CREATED',
           'RESERVATION_CANCELLED', 'TABLE_REASSIGNED'].includes(m.type)) {
        await refresh();
        const d = m.data || {};
        if (d.table_id && d.table_id === S.tableId && d.date === S.date &&
            m.type === 'RESERVATION_CREATED' && !S.holdId) {
          toast('Table ' + TMAP[d.table_id].label + ' was just booked by someone else.', true);
          showAlternatives(S.tableId);
        }
      }
    };
    ws.onclose = () => {
      retry += 1;
      if (!everOpened && retry >= 3) {
        console.info('[realtime] giving up on the socket, polling instead');
        return;                       // stop knocking on a door that is not there
      }
      if (retry > 8) return;
      setTimeout(open, Math.min(30000, 500 * Math.pow(2, retry)));
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  };
  open();
  poll();
}

// ────────────────────────── feature tour ──────────────────────────────
const TOUR = [
  ['Living map', 'Illustrated night plan. Trees sway, lamps flicker, candles pulse, water moves, waiters walk their routes.',
   () => { route('/explore', true); map.fit(true); }],
  ['Fly to a room', 'Cinematic camera move into the main dining room.',
   () => { route('/explore', true); map.moveTo(468, 560, 2.1, 1500); }],
  ['Live availability', 'Every table tinted by its real state right now: free, being booked, reserved, wrong size.',
   async () => { route('/explore', true); await refresh();
     const free = Object.values(STATES).filter(s => s.state === 'AVAILABLE').length;
     toast(`${free} of ${TABLES.length} tables free at ${S.time}`); }],
  ['Smart recommendation', 'Ranks tables against your seating preference and party size.',
   async () => { const r = await recommend(5); map.setHighlight(r.recommended.map(x => x.table.id));
     if (r.recommended[0]) map.focusTable(r.recommended[0].table.id, 2.2);
     toast('Top pick: Table ' + (r.recommended[0] || {table:{label:'—'}}).table.label); }],
  ['Plain-English search', 'Parses a sentence into weighted preferences and highlights the matches.',
   async () => { $('#guide-q').value = 'somewhere quiet and romantic near a window, not near the entrance';
     await askGuide(); }],
  ['Table card', 'Capacity, room, noise, view and privacy ratings, plus why it matched.',
   async () => { const r = await recommend(1); if (r.recommended[0]) pickTable(r.recommended[0].table); }],
  ['Sit at the table', 'Real 360 view from seated eye height, with a compass showing where the window, bar and entrance are from that seat.',
   async () => { const r = await recommend(1); const t = (r.recommended[0]||{}).table || TABLES[0];
     S.tableId = t.id; save(); await openSeatView(t.id); }],
  ['Switch seats', 'Seat A/B/C/D — the view swings to that chair\'s real orientation.',
   () => { if ($('#seatview').classList.contains('hidden')) return toast('Open a seat view first.', true);
     const i = Math.min(1, curSeats.length - 1); $$('#sv-seats button')[i].click(); }],
  ['VR split screen', 'Side-by-side stereo for a phone headset. Also gyro look and full screen.',
   () => { if ($('#seatview').classList.contains('hidden')) return toast('Open a seat view first.', true);
     $('#sv-vr').click(); }],
  ['Real venue Street View', 'Live Google Street View of a real restaurant, embedded beside the generated view.',
   () => { if (!realAvailable()) return toast('No real venue configured.', true);
     if ($('#seatview').classList.contains('hidden')) return openArrival();
     $('#sv-real').click(); }],
  ['Arrival', 'Street-level and aerial views of the real address.',
   () => openArrival()],
  ['Hold a table', 'A genuine 5-minute server-side hold with a live countdown. Survives a page refresh.',
   async () => { const r = await recommend(1); const t = (r.recommended[0]||{}).table;
     if (!t) return toast('Nothing free at that time.', true); await beginHold(t.id); }],
  ['Two guests, one table', 'Opens a second window. Try to book the same table in both — one wins, one is offered alternatives.',
   () => { window.open(location.origin + '/explore', '_blank', 'width=520,height=800');
     toast('Second guest opened. Race me for a table.'); }],
  ['Booking form', 'Allergies, dietary, accessibility, high chairs, occasion. Marketing consent kept separate.',
   () => { if (!S.tableId) return toast('Pick a table first.', true); openForm(); }],
  ['Confirmation', 'Code, mini floor plan with your table lit, add-to-calendar, cancel.',
   async () => { const r = await fetch('/api/manager/day?date=' + S.date).then(x => x.json());
     if (!r.reservations.length) return toast('No bookings today yet.', true);
     lastRes = r.reservations[0]; showConfirmation(lastRes); }],
  ['Manager override', 'Moves a booking to another table. Every open browser updates instantly over WebSocket.',
   async () => { const day = await fetch('/api/manager/day?date=' + S.date).then(x => x.json());
     if (!day.reservations.length) return toast('No bookings to move.', true);
     const res = day.reservations[0];
     const free = Object.values(STATES).find(s => s.state === 'AVAILABLE' && s.table_id !== res.table_id);
     if (!free) return toast('Nothing free to move it to.', true);
     const r = await api.send('POST', '/api/manager/reassign', { code: res.code, table_id: free.table_id });
     await refresh();
     toast(r.ok ? `${res.code} moved from Table ${res.table_label} to Table ${TMAP[free.table_id].label}`
                : 'Move refused — it would clash.', !r.ok);
     map.focusTable(free.table_id, 2.6); }],
  ['Live weather', 'Real conditions at the venue drive the scene: wind moves the water and the trees, cloud casts shadow, rain falls, daylight lifts the whole plate.',
   async () => { route('/explore', true); await loadWeather();
     toast($('#wx-text').textContent); }],
  ['Zoom until you sit down', 'Keep zooming into a table and the map hands off to the 360 view automatically.',
   async () => { route('/explore', true); const r = await recommend(1);
     const t = (r.recommended[0] || {}).table || TABLES[0];
     map.focusTable(t.id, 4.6); }],
  ['Walk a real venue in 3D', 'Giri — a real cafe, restaurant and bar in Berlin — with a real 3D capture, embedded live. Walk it with the arrow keys, with your live table availability beside it.',
   () => openReal()],
  ['Busy tables inside the 360', 'Look around from your seat and every other table is marked live: free, held, or taken.',
   async () => { if ($('#seatview').classList.contains('hidden')) {
       const t = TABLES[0]; S.tableId = t.id; save(); await openSeatView(t.id); }
     toast('Drag to look around — the markers follow the room'); }],
  ['Event configurations', 'Seated dinner, standing reception, live music night, private dinner. Each changes which tables are in play, the capacity and the minimum spend.',
   async () => { route('/explore', true);
     const order = ['reception', 'live_music', 'private_dinner', 'dinner'];
     const next = order[(order.indexOf(S.event) + 1) % order.length];
     $('#f-event').value = next; $('#f-event').dispatchEvent(new Event('change')); }],
  ['Ask about capacity and price', 'The guide answers logistics from the venue record, not invented.',
   async () => { $('#guide-q').value = 'how many people can you fit and what is the minimum spend for a reception';
     await askGuide(); }],
  ['Menu', 'Twelve dishes, generated plates, prices, dietary tags, allergens. Browse only.',
   () => route('/menu', true)],
  ['Find a booking', 'Look any reservation up by its confirmation code.',
   () => route('/about', true)],
];

function openTour() {
  $('#tour-list').innerHTML = TOUR.map(([t, d], i) =>
    `<li data-i="${i}"><span><b>${t}</b><small>${escapeHtml(d)}</small></span>
     <span class="go">▸</span></li>`).join('');
  $$('#tour-list li').forEach(li => li.onclick = async () => {
    li.classList.add('done');
    try { await TOUR[+li.dataset.i][2](); } catch (e) { console.error(e); toast('That step needs a table selected.', true); }
  });
  show('#tour', true);
}


// ──────────── live table markers inside the 360 seat view ─────────────
// Every other table in the room, placed at its true compass bearing from
// the chair you are sitting in, coloured by what it is doing right now.
let marksTimer = null;

function stopMarks() {
  clearInterval(marksTimer); marksTimer = null;
  const box = $('#svmarks'); if (box) box.innerHTML = '';
}

function startMarks(here) {
  stopMarks();
  const box = $('#svmarks');
  if (!box || !here) return;

  const others = TABLES.filter(t => t.id !== here.id).map(t => {
    const dx = t.x - here.x, dy = t.y - here.y;
    return { t: t, dist: Math.sqrt(dx * dx + dy * dy),
             bearing: (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360 };
  }).filter(o => o.dist < 430).sort((a, b) => a.dist - b.dist).slice(0, 14);

  box.innerHTML = others.map(o =>
    '<div class="tm" data-t="' + o.t.id + '" data-b="' + o.bearing.toFixed(1) +
    '" data-d="' + o.dist.toFixed(0) + '"><span class="dot"></span>' +
    '<span class="lbl"></span></div>').join('');

  $$('#svmarks .tm').forEach(el => { el.onclick = () => {
    const t = TMAP[el.dataset.t];
    show('#seatview', false); pano.stop(); stopMarks(); pickTable(t);
  }; });

  const tick = () => {
    if ($('#seatview').classList.contains('hidden')) return;
    $$('#svmarks .tm').forEach(el => {
      const x = pano.screenXFor(+el.dataset.b);
      if (x === null) { el.style.opacity = '0'; el.style.pointerEvents = 'none'; return; }
      const st = (STATES[el.dataset.t] || {}).state || 'UNKNOWN';
      const d = +el.dataset.d;
      el.className = 'tm ' + (st === 'AVAILABLE' ? 'free' : st === 'HELD_BY_YOU' ? 'mine'
                              : st === 'HELD' ? 'held' : 'busy');
      el.style.opacity = String(Math.max(0.35, 1 - d / 540));
      el.style.pointerEvents = 'auto';
      el.style.left = x + 'px';
      el.style.top = (window.innerHeight * (0.50 + Math.min(0.16, d / 2600))
                      - pano.pitch * (window.innerHeight / pano.fov)) + 'px';
      const word = { AVAILABLE: 'free', HELD: 'being booked', HELD_BY_YOU: 'yours',
                     RESERVED: 'taken', INCOMPATIBLE: 'wrong size', UNKNOWN: '' }[st];
      el.querySelector('.lbl').textContent =
        'Table ' + TMAP[el.dataset.t].label + (word ? ' · ' + word : '');
    });
  };
  tick();
  marksTimer = setInterval(tick, 60);
}

// ───────────────────── a real, existing venue in 3D ───────────────────
// Giri, Hermannstrasse 14, Berlin - a real cafe, restaurant and bar with a
// real 3D capture. Embedded live through Kukan's own embed URL. We never
// download, cache or alter their capture.
let rvTimer = null;

function vpUrl(vp) {
  const p = new URLSearchParams({ embed: 'true' });
  if (vp && vp.pos) p.set('pos', vp.pos);
  if (vp && vp.rot) p.set('rot', vp.rot);
  return REAL.embed_base + '?' + p.toString();
}

function openReal() {
  if (!REAL || !REAL.enabled) return toast('No real venue configured.', true);
  show('#seatview', false);
  if (pano) pano.stop();
  stopMarks();
  show('#realview', true);
  $('#rv-name').textContent = REAL.name;
  $('#rv-kind').textContent = REAL.kind + ' · ' + REAL.address;
  $('#rv-credit').textContent = REAL.credit;

  const vps = REAL.viewpoints || [];
  $('#rv-vp').innerHTML = vps.map(v =>
    '<option value="' + v.id + '">' + escapeHtml(v.label) +
    (v.verified ? '' : ' (approx)') + '</option>').join('') ||
    '<option>Tour start</option>';

  let start = vps[0];
  const mapped = (REAL.table_viewpoints || {})[S.tableId];
  if (mapped) {
    const m = vps.filter(v => v.id === mapped)[0];
    if (m) { start = m; $('#rv-vp').value = m.id; }
  }
  loadViewpoint(start ? start.id : null);
  startRvList();
}

function loadViewpoint(id) {
  const vps = REAL.viewpoints || [];
  const vp = vps.filter(v => v.id === id)[0] || vps[0];
  $('#rv-frame').src = vpUrl(vp);
}

function closeReal() {
  show('#realview', false);
  const f = $('#rv-frame'); if (f) f.src = 'about:blank';
  clearInterval(rvTimer); rvTimer = null;
}

function startRvList() {
  const order = { AVAILABLE: 0, HELD_BY_YOU: 1, HELD: 2, RESERVED: 3, INCOMPATIBLE: 4 };
  const paint = () => {
    if ($('#realview').classList.contains('hidden')) return;
    $('#rv-when').textContent = fmtDate(S.date) + ' at ' + S.time + ' · ' +
      S.party + (S.party === 1 ? ' guest' : ' guests');
    const rows = TABLES.slice().sort((a, b) => {
      const sa = (STATES[a.id] || {}).state || 'UNKNOWN';
      const sb = (STATES[b.id] || {}).state || 'UNKNOWN';
      const oa = order[sa] === undefined ? 9 : order[sa];
      const ob = order[sb] === undefined ? 9 : order[sb];
      return oa - ob || (+a.label - +b.label);
    }).slice(0, 16);
    $('#rv-rows').innerHTML = rows.map(t => {
      const st = (STATES[t.id] || {}).state || 'UNKNOWN';
      const cls = st === 'AVAILABLE' ? 'free'
        : (st === 'HELD' || st === 'HELD_BY_YOU') ? 'held' : 'busy';
      const word = { AVAILABLE: 'free', HELD: 'being booked', HELD_BY_YOU: 'yours',
                     RESERVED: 'taken', INCOMPATIBLE: 'wrong size', UNKNOWN: '' }[st];
      return '<div class="rvrow ' + cls + '" data-t="' + t.id + '"><i class="d"></i>' +
             '<span>Table ' + t.label + '</span><small>' + word + '</small></div>';
    }).join('');
    $$('#rv-rows .rvrow').forEach(el => { el.onclick = () => {
      closeReal(); pickTable(TMAP[el.dataset.t]);
    }; });
  };
  paint();
  clearInterval(rvTimer);
  rvTimer = setInterval(() => { refresh().then(paint); }, 8000);
}


// ────────────────────────────── weather ───────────────────────────────
// Open-Meteo: free, keyless, CORS-enabled. Real conditions drive the wind on
// the water, the sway of the trees, the cloud shadow and the rain.
const WX_CODE = {
  0: ['\u2600', 'clear'], 1: ['\ud83c\udf24', 'mostly clear'],
  2: ['\u26c5', 'partly cloudy'], 3: ['\u2601', 'overcast'],
  45: ['\ud83c\udf2b', 'fog'], 48: ['\ud83c\udf2b', 'freezing fog'],
  51: ['\ud83c\udf26', 'light drizzle'], 53: ['\ud83c\udf26', 'drizzle'],
  55: ['\ud83c\udf27', 'heavy drizzle'], 61: ['\ud83c\udf26', 'light rain'],
  63: ['\ud83c\udf27', 'rain'], 65: ['\ud83c\udf27', 'heavy rain'],
  71: ['\ud83c\udf28', 'light snow'], 73: ['\ud83c\udf28', 'snow'],
  75: ['\u2744', 'heavy snow'], 80: ['\ud83c\udf26', 'showers'],
  81: ['\ud83c\udf27', 'showers'], 82: ['\u26c8', 'violent showers'],
  95: ['\u26c8', 'thunderstorm'], 96: ['\u26c8', 'thunderstorm'],
  99: ['\u26c8', 'thunderstorm'],
};

async function loadWeather() {
  if (!VENUE || !map) return;
  const w = (VENUE.venue && VENUE.venue.weather) || { lat: 51.5074, lng: -0.1278 };
  const ic = $('#wx-icon'), tx = $('#wx-text');
  try {
    const u = 'https://api.open-meteo.com/v1/forecast?latitude=' + w.lat +
      '&longitude=' + w.lng + '&current=temperature_2m,precipitation,cloud_cover,' +
      'wind_speed_10m,is_day,weather_code&timezone=auto';
    const r = await fetch(u);
    const j = await r.json();
    const c = j.current || {};
    const pair = WX_CODE[c.weather_code] || ['\u2601', 'cloudy'];
    const num = (v, d) => (typeof v === 'number' ? v : d);
    map.setWeather({
      wind: num(c.wind_speed_10m, 8), rain: num(c.precipitation, 0),
      cloud: num(c.cloud_cover, 40) / 100, isDay: num(c.is_day, 0),
      temp: num(c.temperature_2m, 14), code: num(c.weather_code, 3),
      label: pair[1],
    });
    if (ic) ic.textContent = pair[0];
    if (tx) tx.textContent = (VENUE.venue.weather_city || 'Baku') + ' · ' +
      Math.round(num(c.temperature_2m, 14)) + '\u00b0C · ' + pair[1] +
      ' · wind ' + Math.round(num(c.wind_speed_10m, 8)) + ' km/h';
  } catch (e) {
    if (ic) ic.textContent = '\u2601';
    if (tx) tx.textContent = 'Weather unavailable \u2014 showing evening conditions';
  }
}

// ─────────────────────────────── utils ────────────────────────────────
let toastT = null;
function toast(msg, bad) {
  const el = $('#toast');
  el.textContent = msg; el.classList.toggle('bad', !!bad); show('#toast', true);
  clearTimeout(toastT); toastT = setTimeout(() => show('#toast', false), 4200);
}
function fmtDate(d) {
  return new Date(d + 'T12:00:00').toLocaleDateString(undefined,
    { weekday: 'short', day: 'numeric', month: 'long' });
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
window.addEventListener('beforeunload', save);
