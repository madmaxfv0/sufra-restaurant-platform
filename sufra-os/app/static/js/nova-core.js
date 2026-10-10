/* ============================================================
   NOVA core — shared by all three apps.

   One socket, one fetch helper, one set of primitives. Everything
   above this file is screen logic; nothing below it knows which
   app it is running in.
   ============================================================ */

const NOVA = (() => {
  const listeners = [];
  let socket = null, retry = 0;

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    socket = new WebSocket(`${proto}://${location.host}/ws`);
    socket.onopen = () => { retry = 0; mark(true); };
    socket.onclose = () => {
      mark(false);
      retry = Math.min(retry + 1, 6);
      setTimeout(connect, 400 * retry);          // back off, don't hammer
    };
    socket.onmessage = e => {
      const msg = JSON.parse(e.data);
      listeners.forEach(fn => fn(msg));
    };
  }
  function mark(live) {
    document.querySelectorAll('[data-live]').forEach(el => el.style.opacity = live ? '1' : '.35');
  }

  /* Every failure surfaces as a readable message rather than a dead screen.
     A 401 is tagged so callers can show the sign-in screen again instead
     of just toasting an error into the void. */
  async function api(url, body, method) {
    const token = (() => {
      try {
        const scope = location.pathname.startsWith('/waiter') ? 'waiter'
          : location.pathname.startsWith('/admin') ? 'admin' : 'staff';
        return sessionStorage.getItem(`nova-${scope}-token`);
      } catch { return null; }
    })();
    const headers = {};
    if (body || method) headers['Content-Type'] = 'application/json';
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const opts = (body || method || token)
      ? { method: method || (body ? 'POST' : 'GET'), headers,
          body: body ? JSON.stringify(body) : undefined }
      : {};
    let res;
    try {
      res = await fetch(url, opts);
    } catch {
      throw new Error('Lost the connection to the restaurant.');
    }
    let data = null;
    try { data = await res.json(); } catch { data = null; }
    if (!res.ok) {
      const err = new Error((data && data.error) || (data && data.detail) || `Request failed (${res.status})`);
      err.status = res.status;
      err.body = data;
      const credentialCheck = ['/api/auth/login','/api/auth/verify','/api/auth/qr/identify','/api/enterprise/security/pin/change'].includes(url.split('?')[0]);
      if(res.status===401 && token && !credentialCheck && NOVA.auth?.getToken()===token) NOVA.auth.expireSession();
      throw err;
    }
    return data;
  }

  // The venue's currency, injected by the page from restaurant settings.
  const CUR = () => (window.SUFRA_CURRENCY || '\u20bc');
  const money = n => CUR() + Number(n || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 });
  const money2 = n => CUR() + Number(n || 0).toFixed(2);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  function setNumber(el, value, fmt = v => Math.round(v)) {
    if (!el) return;
    const to = Number(value) || 0;
    if (el.dataset.seen || reduced()) { el.textContent = fmt(to); el.dataset.seen = '1'; return; }
    el.dataset.seen = '1';
    const start = performance.now(), dur = 850;
    const step = t => {
      const p = Math.min(1, (t - start) / dur);
      el.textContent = fmt(to * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function toast(text, tone) {
    let el = document.querySelector('.toast');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
    el.className = 'toast ' + (tone || '');
    el.textContent = text;
    requestAnimationFrame(() => el.classList.add('up'));
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('up'), 3000);
  }
  const fail = e => toast(e.message || String(e), 'bad');

  /* ---- modal + bottom sheet ------------------------------------- */

  function modal(title, html, onMount) {
    const back = document.querySelector('#modal');
    if (!back) return;
    back.innerHTML = `<div class="modal">
        <button class="close" aria-label="Close">×</button>
        <h2>${esc(title)}</h2>
        <div class="modal-body">${html}</div>
      </div>`;
    back.classList.add('open');
    const close = () => back.classList.remove('open');
    back.querySelector('.close').onclick = close;
    back.onclick = e => { if (e.target === back) close(); };
    document.addEventListener('keydown', function esc2(e) {
      if (e.key === 'Escape') { close(); document.removeEventListener('keydown', esc2); }
    });
    if (onMount) onMount(back.querySelector('.modal-body'), close);
    const first = back.querySelector('input,select,textarea,button.solid');
    if (first) first.focus();
    return close;
  }

  function sheet(title, html, onMount) {
    const el = document.querySelector('#sheet');
    if (!el) return;
    el.innerHTML = `<div class="sheet-grip"></div>
      <button class="close" aria-label="Close">×</button>
      <h2>${esc(title)}</h2><div class="sheet-body">${html}</div>`;
    el.classList.add('open');
    const close = () => el.classList.remove('open');
    el.querySelector('.close').onclick = close;
    if (onMount) onMount(el.querySelector('.sheet-body'), close);
    return close;
  }

  const skeleton = (rows = 3) =>
    `<div class="skeleton">${'<i></i>'.repeat(rows)}</div>`;

  const empty = (title, body) =>
    `<div class="empty"><b>${esc(title)}</b>${esc(body || '')}</div>`;

  /* Wraps a render function so loading and failure states are automatic. */
  async function load(el, fn) {
    if (!el) return;
    if (!el.dataset.loaded) el.innerHTML = skeleton();
    try {
      await fn();
      el.dataset.loaded = '1';
    } catch (e) {
      el.innerHTML = `<div class="empty error"><b>That didn't load.</b>${esc(e.message)}
        <button class="btn tiny" style="margin-top:10px">Try again</button></div>`;
      const b = el.querySelector('button');
      if (b) b.onclick = () => load(el, fn);
    }
  }

  /* ---- charts: hand-rolled SVG, no library ---------------------- */

  function areaChart(el, points, { label = v => v, id = 'mintFade' } = {}) {
    if (!el || !points.length) return;
    const W = 600, H = 190, pad = { l: 40, r: 8, t: 14, b: 24 };
    const max = Math.max(...points.map(p => p.v), 1) * 1.15;
    const x = i => pad.l + i * (W - pad.l - pad.r) / Math.max(1, points.length - 1);
    const y = v => pad.t + (1 - v / max) * (H - pad.t - pad.b);
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
    const area = `${line} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
    const rules = [0, .5, 1].map(f =>
      `<line class="grid-line" x1="${pad.l}" x2="${W - pad.r}" y1="${y(max * f)}" y2="${y(max * f)}"/>
       <text x="0" y="${y(max * f) + 3}">${label(max * f)}</text>`).join('');
    const every = Math.ceil(points.length / 8);
    const ticks = points.map((p, i) => i % every ? '' :
      `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${esc(p.k)}</text>`).join('');
    el.innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">
      <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="#7FE7BB" stop-opacity=".30"/>
        <stop offset="100%" stop-color="#7FE7BB" stop-opacity="0"/></linearGradient></defs>
      ${rules}<path class="area" style="fill:url(#${id})" d="${area}"/>
      <path class="stroke" d="${line}" pathLength="1"
        style="stroke-dasharray:1;stroke-dashoffset:${reduced() ? 0 : 1};animation:trace 1.1s cubic-bezier(.22,1,.36,1) forwards"/>
      ${ticks}</svg>`;
  }

  function barChart(el, points, nowKey) {
    if (!el || !points.length) return;
    const W = 600, H = 150, pad = { l: 6, r: 6, t: 10, b: 22 };
    const max = Math.max(...points.map(p => p.v), 1);
    const bw = (W - pad.l - pad.r) / points.length;
    el.innerHTML = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img">
      ${points.map((p, i) => {
        const h = (p.v / max) * (H - pad.t - pad.b);
        return `<rect class="bar ${String(p.k) === String(nowKey) ? 'now' : ''}" rx="3"
          x="${pad.l + i * bw + bw * .18}" width="${bw * .64}"
          y="${H - pad.b - h}" height="${Math.max(2, h)}"/>
          <text x="${pad.l + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${esc(p.k)}</text>`;
      }).join('')}</svg>`;
  }

  /* Horizontal ranked bars. Used anywhere a top-N list needs weight. */
  function ranked(el, rows, fmt = money2) {
    if (!el) return;
    if (!rows.length) { el.innerHTML = empty('Nothing to show yet.'); return; }
    const max = Math.max(...rows.map(r => Math.abs(r.value)), 1);
    el.innerHTML = rows.map(r => `
      <div class="rank">
        <div class="rank-label"><span>${esc(r.label)}</span><b>${fmt(r.value)}</b></div>
        <div class="rank-bar"><i class="${r.tone || ''}"
          style="width:${Math.abs(r.value) / max * 100}%"></i></div>
      </div>`).join('');
  }

  /* ---- appearance ------------------------------------------------ */

  function theme(next) {
    const allowed = ['dark','light'];
    let value = next;
    if (!allowed.includes(value)) {
      try { value = localStorage.getItem('sufra-theme') || 'dark'; } catch { value='dark'; }
    }
    if (!allowed.includes(value)) value='dark';
    document.documentElement.dataset.theme=value;
    try { localStorage.setItem('sufra-theme', value); } catch {}
    document.querySelectorAll('[data-theme-toggle]').forEach(b=>{
      b.setAttribute('aria-label', value==='dark'?'Switch to light mode':'Switch to dark mode');
      b.innerHTML = value==='dark' ? '<span>☀</span><em>Light</em>' : '<span>◐</span><em>Dark</em>';
    });
    return value;
  }
  theme();

  if (!document.getElementById('trace-kf')) {
    const st = document.createElement('style');
    st.id = 'trace-kf';
    st.textContent = '@keyframes trace{to{stroke-dashoffset:0}}';
    document.head.appendChild(st);
  }

  connect();
  return { api, money, money2, esc, plural, setNumber, toast, fail, modal, sheet,
           skeleton, empty, load, areaChart, barChart, ranked, theme,
           on: fn => listeners.push(fn) };
})();

/* ============================================================
   Auth: token storage, the shared staff-login screen, idle lock.
   Used by both the waiter app and the admin app so the login
   experience — and the security behind it — is written once.
   ============================================================ */

NOVA.auth = (() => {
  const scope = location.pathname.startsWith('/waiter') ? 'waiter'
    : location.pathname.startsWith('/admin') ? 'admin' : 'staff';
  const KEY = `nova-${scope}-token`;
  const STAFF_KEY = `nova-${scope}-staff`;
  const PERMS_KEY = `nova-${scope}-perms`;

  // A launcher click may explicitly request a clean session. Strip the query
  // immediately so the post-login reload does not clear the new session again.
  try {
    const u = new URL(location.href);
    if (u.searchParams.get('fresh') === '1' || u.hash.startsWith('#staff_qr=')) {
      sessionStorage.removeItem(KEY);
      sessionStorage.removeItem(STAFF_KEY);
      sessionStorage.removeItem(PERMS_KEY);
      localStorage.removeItem(KEY);
      localStorage.removeItem(STAFF_KEY);
      localStorage.removeItem(PERMS_KEY);
      u.searchParams.delete('fresh');
      history.replaceState({}, '', u.pathname + (u.search ? u.search : '') + u.hash);
    }
  } catch {}

  window.addEventListener('hashchange', () => {
    if(location.hash.startsWith('#staff_qr=')) location.reload();
  });

  const readStore = (key) => {
    try { return sessionStorage.getItem(key); }
    catch { return null; }
  };
  const getToken = () => readStore(KEY);
  const getStaff = () => { try { return JSON.parse(readStore(STAFF_KEY) || 'null'); } catch { return null; } };
  const getPerms = () => { try { return JSON.parse(readStore(PERMS_KEY) || '[]'); } catch { return []; } };
  const can = perm => getPerms().includes(perm);

  function setSession(token, staff, permissions) {
    try {
      const staffJson = JSON.stringify(staff);
      const permsJson = JSON.stringify(permissions || []);
      sessionStorage.setItem(KEY, token);
      sessionStorage.setItem(STAFF_KEY, staffJson);
      sessionStorage.setItem(PERMS_KEY, permsJson);
      localStorage.removeItem(KEY);
      localStorage.removeItem(STAFF_KEY);
      localStorage.removeItem(PERMS_KEY);
    } catch {}
  }
  function clearSession() {
    try {
      sessionStorage.removeItem(KEY);
      sessionStorage.removeItem(STAFF_KEY);
      sessionStorage.removeItem(PERMS_KEY);
      localStorage.removeItem(KEY);
      localStorage.removeItem(STAFF_KEY);
      localStorage.removeItem(PERMS_KEY);
    } catch {}
  }
  let expiring=false;
  function expireSession() {
    if(expiring)return;
    expiring=true;
    clearSession();
    const url=new URL(location.href);
    url.searchParams.set('fresh','1');
    url.searchParams.set('session_expired','1');
    location.replace(url.pathname+url.search+url.hash);
  }
  async function logout() {
    try { await NOVA.api('/api/auth/logout', {}); } catch {}
    clearSession();
  }

  function allowedRoster(roster) {
    if (scope === 'waiter') {
      const roles = new Set(['waiter', 'bartender']);
      return roster.filter(p => roles.has(p.role));
    }
    if (scope === 'admin') {
      const roles = new Set(['owner','general_manager','restaurant_manager','host','inventory_manager','cashier','kitchen']);
      return roster.filter(p => roles.has(p.role));
    }
    return roster;
  }

  function roleIcon(){ return ''; }

  async function staffLogin(mount, onSuccess) {
    if (!mount) throw new Error('The staff sign-in mount is missing from this page.');
    mount.hidden = false;
    mount.innerHTML = `<div class="signin-box"><div class="auth-head">
      <div class="wordmark big">SU<span>FRA</span></div>
      <h1>Opening staff access…</h1><p>Loading the restaurant team.</p>
    </div></div>`;

    let roster = [];
    let globalKeyHandler = null;
    const stopKeyboard = () => {
      if (globalKeyHandler) document.removeEventListener('keydown', globalKeyHandler);
      globalKeyHandler = null;
    };

    try {
      const embedded = Array.isArray(window.NOVA_STAFF_ROSTER) ? window.NOVA_STAFF_ROSTER : [];
      if (embedded.length) {
        roster = allowedRoster(embedded);
      } else {
        const response = await Promise.race([
          NOVA.api('/api/auth/roster'),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Staff roster timed out.')), 5000)),
        ]);
        roster = allowedRoster(Array.isArray(response && response.staff) ? response.staff : []);
      }
      if (!roster.length) throw new Error('No employee profiles are available for this application.');
    } catch (e) {
      mount.innerHTML = `<div class="signin-box"><div class="auth-error"><b>Staff access could not open.</b>
        <p>${NOVA.esc(e.message || String(e))}</p><button class="btn solid" id="auth-retry">Try again</button></div></div>`;
      const retry = mount.querySelector('#auth-retry');
      if (retry) retry.onclick = () => staffLogin(mount, onSuccess);
      return;
    }

    function showQR() { stopKeyboard(); NOVA.staffQR(mount, showPinPad, showRoster); }

    function showRoster() {
      stopKeyboard();
      mount.innerHTML = `<div class="signin-box">
        <div class="auth-head"><div class="wordmark big">SU<span>FRA</span></div>
          <h1>Who's using SUFRA?</h1><p>Choose your employee profile, then enter your four-digit PIN.</p>
          <button type="button" class="back-link" id="auth-use-qr">Use QR instead</button></div>

        <div class="who-grid">${roster.map(p => `<button type="button" class="who" data-id="${p.id}">
          <span class="who-face">${roleIcon(p.role)}<i>${NOVA.esc(p.avatar || (p.name || '?').slice(0,1))}</i></span>
          <b>${NOVA.esc(p.name)}</b><span class="who-role">${NOVA.esc(ROLE_LABEL[p.role] || p.role)}</span>
          ${p.section ? `<span class="who-section">${NOVA.esc(p.section)}</span>` : ''}
          <span class="who-shift ${p.on_shift ? 'on' : ''}">${p.on_shift ? 'On shift' : 'Off shift'}</span>
        </button>`).join('')}</div></div>`;

      mount.querySelector('#auth-use-qr').onclick = showQR;
      mount.querySelectorAll('.who').forEach(b => b.onclick = () => {
        const person = roster.find(p => String(p.id) === String(b.dataset.id));
        if (person) showPinPad(person);
      });
    }

    function showPinPad(person, qrToken) {
      stopKeyboard();
      let entered = '', busy = false, timer = null;
      mount.innerHTML = `<div class="signin-box pin-screen">
        <div class="auth-head"><button type="button" class="back-link" id="pin-back">← Choose another employee</button>
          <span class="who-face big">${roleIcon(person.role)}<i>${NOVA.esc(person.avatar || (person.name || '?').slice(0,1))}</i></span>
          <h1>${NOVA.esc(person.name)}</h1><p>${NOVA.esc(ROLE_LABEL[person.role] || person.role)}${person.section ? ' · '+NOVA.esc(person.section) : ''}</p></div>
        <label class="pin-input-wrap"><span>PIN</span><input id="pin-input" type="password" inputmode="numeric" autocomplete="one-time-code" maxlength="4" pattern="[0-9]*" aria-label="4 digit PIN" placeholder="••••"></label>
        <div class="pin-dots"><i></i><i></i><i></i><i></i></div><p class="pin-error" id="pin-error"></p>
        <div class="keypad">${[1,2,3,4,5,6,7,8,9].map(n=>`<button type="button" data-k="${n}">${n}</button>`).join('')}
          <button type="button" data-k="clear" class="ghost-key">Clear</button><button type="button" data-k="0">0</button><button type="button" data-k="back" class="ghost-key">⌫</button></div>
        <button type="button" class="btn solid block pin-submit" id="pin-go" disabled>Sign in</button></div>`;
      const input=mount.querySelector('#pin-input'), go=mount.querySelector('#pin-go'), error=mount.querySelector('#pin-error');
      const dots=[...mount.querySelectorAll('.pin-dots i')];
      function paint(message='') {
        dots.forEach((d,i)=>d.classList.toggle('on',i<entered.length));
        if (input.value !== entered) input.value=entered;
        error.textContent=message; go.disabled=busy||entered.length!==4; go.textContent=busy?'Signing in…':'Sign in';
      }
      async function submit() {
        if (busy || entered.length!==4) return;
        if(!mount.contains(input))return;
        clearTimeout(timer); busy=true; paint();
        try {
          const r=await NOVA.api('/api/auth/login',{staff_id:person.id,pin:entered,qr_token:qrToken});
          if(!mount.contains(input))return;
          setSession(r.token,r.staff,r.permissions); stopKeyboard();
          if (typeof onSuccess==='function') await onSuccess(r.staff,r.permissions);
        } catch(e) { busy=false; entered=''; paint(e.message||'Incorrect PIN or sign-in failed.'); input.focus(); }
      }
      function setEntered(v) {
        entered=String(v||'').replace(/\D/g,'').slice(0,4); paint(); clearTimeout(timer);
        if (entered.length===4) timer=setTimeout(submit,120);
      }
      mount.querySelector('#pin-back').onclick=showRoster;
      mount.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{
        const k=b.dataset.k;
        if(k==='clear') setEntered(''); else if(k==='back') setEntered(entered.slice(0,-1)); else setEntered(entered+k);
        input.focus();
      });
      go.onclick=submit;
      // Physical keyboard PIN entry — works even when the visible input loses focus.
      input.addEventListener('input',()=>setEntered(input.value));
      input.addEventListener('keydown',e=>{ if(e.key==='Enter'){e.preventDefault();submit()} else if(e.key==='Escape'){e.preventDefault();showRoster()} });
      globalKeyHandler=e=>{
        if(e.target===input)return;
        if(/^[0-9]$/.test(e.key)){e.preventDefault();setEntered(entered+e.key)}
        else if(e.key==='Backspace'){e.preventDefault();setEntered(entered.slice(0,-1))}
        else if(e.key==='Enter'){e.preventDefault();submit()}
        else if(e.key==='Escape'){e.preventDefault();showRoster()}
      };
      document.addEventListener('keydown',globalKeyHandler); paint(); setTimeout(()=>input.focus(),0);
    }
    if(location.hash.startsWith("#staff_qr=")) showQR(); else showRoster();
  }

  function idleLock(minutes, onLock) {
    let last=Date.now(), sent=0, ended=false;
    const expire=()=>{if(ended)return;ended=true;clearInterval(timer);logout();expireSession()};
    const activity=()=>{
      if(ended)return;
      if(Date.now()-last>=minutes*60000){expire();return}
      last=Date.now();
      if(last-sent>15000){sent=last;NOVA.api('/api/auth/activity',{}).catch(e=>{if(e.status===401)expire()})}
    };
    const timer=setInterval(()=>{if(Date.now()-last>=minutes*60000)expire()},1000);
    ['pointerdown','pointermove','wheel','keydown','touchstart'].forEach(ev=>document.addEventListener(ev,activity,{passive:true}));
    document.addEventListener('visibilitychange',()=>{if(Date.now()-last>=minutes*60000)expire()});
    activity();return {unlock:activity};
  }
  return {getToken,getStaff,getPerms,can,setSession,clearSession,logout,staffLogin,idleLock,expireSession};
})();
const ROLE_LABEL = {
  owner: 'Owner', general_manager: 'General Manager', restaurant_manager: 'Manager',
  host: 'Host', waiter: 'Waiter', bartender: 'Bartender', kitchen: 'Kitchen',
  cashier: 'Cashier', inventory_manager: 'Inventory Manager',
};

/* Small shared helpers used by more than one app. */

const STATUS_LABEL = {
  available: 'Free', reserved: 'Held', seated: 'Just sat', ordering: 'Ordering',
  cooking: 'In the kitchen', ready: 'Food at the pass', dining: 'Eating',
  needs_waiter: 'Wants a waiter', bill: 'Bill asked for', cleaning: 'Needs clearing'
};

const TASK_LABEL = {
  call: 'Wants a waiter', water: 'Water', cutlery: 'Cutlery', bill: 'Bill',
  runner: 'Food at the pass', clear: 'Clear the table', checkin: 'Check in'
};

const TAG_LABEL = {
  vegan: 'vegan', vegetarian: 'vegetarian', gf: 'gluten free', halal: 'halal',
  nuts: 'contains nuts', shellfish: 'shellfish', dairy: 'dairy', fish: 'fish',
  gluten: 'contains gluten', sesame: 'sesame', egg: 'egg', wine: 'wine',
  red: 'red', white: 'white', cocktail: 'cocktail', zero: 'no alcohol',
  digestif: 'digestif'
};

/* A dish plate, drawn from its hue. No stock photography anywhere in NOVA. */
function plate(hue, size = 64, signature = false) {
  return `<div class="plate${signature ? ' sig' : ''}" style="
    --h:${hue};width:${size}px;height:${size}px"><i></i></div>`;
}

/* NOVA GLOBAL I18N V4 */
window.NOVAI18N=(()=>{
 const KEY='nova-lang';let lang=(()=>{try{return localStorage.getItem(KEY)||localStorage.getItem('nova-command-lang')||'en'}catch{return'en'}})();if(!['en','az','ru'].includes(lang))lang='en';
 const R=[
 ['owner','sahibkar','владелец'],['general manager','baş menecer','генеральный менеджер'],['restaurant manager','restoran meneceri','менеджер ресторана'],['host','host','хостес'],['waiter','ofisiant','официант'],['bartender','barmen','бармен'],['kitchen','mətbəx','кухня'],['cashier','kassir','кассир'],['inventory manager','anbar meneceri','менеджер склада'],
 ['Booking intelligence','Rezervasiya analitikası','Аналитика броней'],['Enterprise','Korporativ','Корпоративное'],['Owner intelligence','Sahibkar analitikası','Аналитика владельца'],['HR & People','İnsan resursları','Кадры и персонал'],['Accounting','Mühasibatlıq','Бухгалтерия'],['Open customer booking site','Müştəri rezervasiya saytını aç','Открыть сайт бронирования'],['AI table assignments','AI masa təyinatları','AI-назначение столов'],['Manage table assignment','Masa təyinatını idarə et','Управление назначением стола'],['Walk-in tables','Sərbəst gələnlər üçün masalar','Столы для гостей без брони'],['safe for the next 90 min','növbəti 90 dəqiqə üçün təhlükəsiz','свободны ближайшие 90 минут'],['Reserved tables','Rezerv edilmiş masalar','Забронированные столы'],['protected for bookings','rezervasiyalar üçün qorunur','защищены под брони'],['Reserved','Rezerv edilib','Забронирован'],['Free for walk-ins','Sərbəst gələnlər üçün boş','Свободен для гостей без брони'],['Press any reservation for full details','Tam məlumat üçün istənilən rezervasiyaya toxunun','Нажмите на любую бронь для подробностей'],['Open capacity','Boş tutum','Свободная вместимость'],['Available for walk-ins','Sərbəst gələnlər üçün əlçatandır','Доступно для гостей без брони'],['Best available','Ən uyğun boş masa','Лучший свободный'],['Guest reservation','Qonaq rezervasiyası','Бронь гостя'],['Take a booking','Rezervasiya qəbul et','Принять бронь'],['Add to waitlist','Gözləmə siyahısına əlavə et','Добавить в лист ожидания'],['Awaiting table','Masa gözləyir','Ожидает стол'],
 ['Live operations','Canlı əməliyyatlar','Операции в реальном времени'],['Everything that has actually happened, from every application, as it happens.','Hər tətbiqdə real olaraq baş verən hər şey — baş verdiyi anda.','Всё, что действительно произошло, из каждого приложения, в момент события.'],['Notifications','Bildirişlər','Уведомления'],['Confirmations, the 15-minute reminder and the late note. Status is what the provider really said.','Təsdiqlər, 15 dəqiqəlik xatırlatma və gecikmə mesajı. Status provayderin real cavabıdır.','Подтверждения, напоминание за 15 минут и сообщение об опоздании. Статус — это реальный ответ провайдера.'],['Nothing has happened yet.','Hələ heç nə baş verməyib.','Пока ничего не произошло.'],['Bookings, seating, table changes and menu edits appear here the moment they occur.','Rezervasiyalar, oturma, masa dəyişiklikləri və menyu redaktələri baş verdiyi anda burada görünür.','Брони, посадка, изменения столов и правки меню появляются здесь в момент события.'],['Activity stream','Fəaliyyət axını','Лента активности'],['Real events only — reservations, seating, tables, waitlist and menu, from SUFRA OS and SUFRA 360 alike.','Yalnız real hadisələr — rezervasiyalar, oturma, masalar, gözləmə siyahısı və menyu; həm SUFRA OS, həm SUFRA 360-dan.','Только реальные события — брони, посадка, столы, лист ожидания и меню, из SUFRA OS и SUFRA 360.'],['Email','E-poçt','Эл. почта'],['SMS','SMS','SMS'],['connected','qoşulub','подключено'],['not configured','tənzimlənməyib','не настроено'],['Assigned table','Təyin olunmuş masa','Назначенный стол'],['Not assigned','Təyin olunmayıb','Не назначен'],['Seated','Oturdu','Посажен'],['Late','Gecikir','Опаздывает'],['Completed','Tamamlandı','Завершено'],['No-show','Gəlmədi','Не пришёл'],['Cancel','Ləğv et','Отменить'],['Table assignment','Masa təyinatı','Назначение стола'],['Move to','Bura köçür','Перенести на'],['Keep this table','Bu masanı saxla','Оставить этот стол'],['Change table','Masanı dəyiş','Сменить стол'],['Edit the booking','Rezervasiyanı redaktə et','Редактировать бронирование'],['Save changes','Dəyişiklikləri yadda saxla','Сохранить изменения'],['Send updated confirmation','Yenilənmiş təsdiqi göndər','Отправить обновлённое подтверждение'],['A move is refused if the destination already has a booking overlapping this one.','Hədəf masada bu vaxtla üst-üstə düşən rezervasiya varsa, köçürmə qəbul edilmir.','Перенос отклоняется, если у целевого стола уже есть пересекающаяся бронь.'],['Editing never emails the guest on its own — use “Send updated confirmation” when you want them told.','Redaktə özü-özünə qonağa məktub göndərmir — bildirmək istəyəndə “Yenilənmiş təsdiqi göndər” düyməsindən istifadə edin.','Редактирование само по себе не отправляет письмо гостю — используйте «Отправить обновлённое подтверждение».'],['Party size','Qonaq sayı','Количество гостей'],['Duration (min)','Müddət (dəq)','Длительность (мин)'],['First name','Ad','Имя'],['Last name','Soyad','Фамилия'],['Phone','Telefon','Телефон'],['Occasion','Münasibət','Повод'],['Seating preference','Oturma üstünlüyü','Пожелание по посадке'],['Allergies','Allergiyalar','Аллергии'],['Dietary','Pəhriz','Питание'],['Accessibility','Əlçatanlıq','Доступность'],['High chairs','Uşaq stulu','Детские стулья'],['Special request','Xüsusi istək','Особое пожелание'],['Floor note','Zal üçün qeyd','Заметка для зала'],['Confirmation language','Təsdiq dili','Язык подтверждения'],['No-show risk','Gəlməmə riski','Риск неявки'],['Guest confirmed','Qonaq təsdiqlədi','Гость подтвердил'],['Awaiting guest confirmation','Qonağın təsdiqi gözlənilir','Ожидается подтверждение гостя'],['reminder sent','xatırlatma göndərildi','напоминание отправлено'],['Make a booking','Rezervasiya yarat','Оформить бронь'],['Seat','Otuzdur','Посадить'],['Left','Getdi','Ушли'],['Open','Aç','Открыть'],['Free the table','Masanı boşalt','Освободить стол'],['from SUFRA 360','SUFRA 360-dan','из SUFRA 360'],
 ['Overview','Ümumi baxış','Обзор'],['Command centre','İdarəetmə mərkəzi','Центр управления'],['Live operations','Canlı əməliyyatlar','Операции в реальном времени'],['Service','Xidmət','Сервис'],['Floor','Zal','Зал'],['Reservations','Rezervasiyalar','Бронирования'],['Orders','Sifarişlər','Заказы'],['Kitchen','Mətbəx','Кухня'],['Product','Məhsul','Продукт'],['Menu','Menyu','Меню'],['Inventory','Ehtiyatlar','Запасы'],['Suppliers','Təchizatçılar','Поставщики'],['People','İnsanlar','Люди'],['Guests','Qonaqlar','Гости'],['Staff','Heyət','Персонал'],['Events','Tədbirlər','События'],['Business','Biznes','Бизнес'],['Analytics','Analitika','Аналитика'],['Finance','Maliyyə','Финансы'],['AI Copilot','AI Köməkçi','AI-помощник'],['Settings','Ayarlar','Настройки'],['Live','Canlı','Онлайн'],['Switch user','İstifadəçini dəyiş','Сменить пользователя'],['Waiter app','Ofisiant tətbiqi','Приложение официанта'],['Guest app','Qonaq tətbiqi','Приложение гостя'],
 ['Administration','İdarəetmə','Администрация'],['Desktop','Kompüter','Компьютер'],['Waiter','Ofisiant','Официант'],['Tablet','Planşet','Планшет'],['Guest','Qonaq','Гость'],['Phone','Telefon','Телефон'],['Try this first.','Əvvəl bunu sınayın.','Попробуйте сначала это.'],['Table 13 QR link','Masa 13 QR keçidi','QR-ссылка стола 13'],['Ask the copilot','AI köməkçidən soruşun','Спросить AI-помощника'],
 ['Opening staff access…','Heyət girişi açılır…','Открываем доступ персонала…'],['Opening waiter access…','Ofisiant girişi açılır…','Открываем доступ официанта…'],['Checking your session.','Sessiyanız yoxlanılır.','Проверяем вашу сессию.'],['Loading your team.','Heyətiniz yüklənir.','Загружаем вашу команду.'],["Who's using SUFRA?",'SUFRA-dan kim istifadə edir?','Кто использует SUFRA?'],['Choose your employee profile, then enter your personal PIN.','İşçi profilinizi seçin, sonra şəxsi PIN kodunuzu daxil edin.','Выберите профиль сотрудника, затем введите личный PIN-код.'],['On shift','Növbədədir','На смене'],['Off shift','Növbədə deyil','Не на смене'],['Choose another employee','Başqa işçi seçin','Выбрать другого сотрудника'],['Sign in','Daxil ol','Войти'],['Signing in…','Giriş edilir…','Вход…'],['Clear','Təmizlə','Очистить'],['Try again','Yenidən cəhd edin','Попробовать снова'],['Reload','Yenilə','Перезагрузить'],['Session locked','Sessiya kilidlənib','Сессия заблокирована'],['Tablet locked','Planşet kilidlənib','Планшет заблокирован'],['Switch employee','İşçini dəyiş','Сменить сотрудника'],
 ['Owner','Sahib','Владелец'],['General Manager','Baş menecer','Генеральный менеджер'],['Manager','Menecer','Менеджер'],['Host','Hostes','Хостес'],['Bartender','Barmen','Бармен'],['Cashier','Kassir','Кассир'],['Inventory Manager','Ehtiyat meneceri','Менеджер запасов'],
 ['Good morning','Sabahınız xeyir','Доброе утро'],['Good afternoon','Günortanız xeyir','Добрый день'],['Good evening','Axşamınız xeyir','Добрый вечер'],['Home','Ana səhifə','Главная'],['Tables','Masalar','Столы'],['Order','Sifariş','Заказ'],['Tasks','Tapşırıqlar','Задачи'],['Profile','Profil','Профиль'],['My section','Mənim bölməm','Моя секция'],['Open floor','Zalı aç','Открыть зал'],['Open requests','Açıq sorğular','Открытые запросы'],['Ready at pass','Passda hazır','Готово на выдаче'],['Active tables','Aktiv masalar','Активные столы'],['Do these next','Bunları növbəti edin','Сделать дальше'],['Where you are needed','Harada sizə ehtiyac var','Где вы нужны'],['Full floor →','Tam zal →','Весь зал →'],['Service status','Xidmət statusu','Статус обслуживания'],['Bill requested','Hesab istənilib','Запрошен счёт'],['Food ready','Yemək hazırdır','Блюдо готово'],['Guest called you','Qonaq sizi çağırdı','Гость вызвал вас'],['Done','Hazırdır','Готово'],['Seats','Oturacaqlar','Места'],['Notes','Qeydlər','Заметки'],['Search dishes','Yemək axtarın','Поиск блюд'],['Shared','Ümumi','Общее'],['Kitchen note','Mətbəx qeydi','Заметка для кухни'],['Cancel','Ləğv et','Отмена'],['Add to course','Kursa əlavə et','Добавить в курс'],['Send course','Kursu göndər','Отправить курс'],['Sending…','Göndərilir…','Отправка…'],['Save note','Qeydi saxla','Сохранить заметку'],['Take full payment','Tam ödənişi qəbul et','Принять полную оплату'],
 ["Tonight's menu.",'Bu axşamın menyusu.','Меню на сегодня.'],['Browse, filter and save what catches your eye. Your waiter will take the order.','Menyuya baxın, filtr edin və bəyəndiklərinizi yadda saxlayın. Sifarişi ofisiantınız götürəcək.','Просматривайте меню, фильтруйте и сохраняйте понравившиеся блюда. Заказ примет ваш официант.'],['Still water','Qazsız su','Вода без газа'],['Cutlery','Çəngəl-bıçaq','Приборы'],['A waiter','Ofisiant','Официант'],['The bill','Hesab','Счёт'],['Filters','Filtrlər','Фильтры'],['Search dishes or ingredients','Yemək və ya inqrediyent axtarın','Поиск блюд или ингредиентов'],['Not sure what to choose?','Nə seçəcəyinizə əmin deyilsiniz?','Не знаете, что выбрать?'],['Saved dishes','Yadda saxlanılan yeməklər','Сохранённые блюда'],['Good to know','Bilmək faydalıdır','Полезно знать'],['Allergies','Allergiyalar','Аллергии'],['Need something?','Nəsə lazımdır?','Что-то нужно?'],['Ordering','Sifariş','Заказ'],['Saved','Yadda saxlanılan','Сохранённое'],['Info','Məlumat','Информация'],['Nothing saved yet.','Hələ heç nə yadda saxlanılmayıb.','Пока ничего не сохранено.'],['waiter notified','ofisianta bildirildi','официант уведомлён'],
 ['Every moving part of the service on one screen.','Xidmətin bütün hərəkətli hissələri bir ekranda.','Все процессы сервиса на одном экране.'],['Alerts as they happen','Hadisə baş verən kimi xəbərdarlıqlar','Оповещения по мере появления'],['At the pass','Passda','На выдаче'],['Open requests','Açıq sorğular','Открытые запросы'],['The room','Zal','Зал'],['Reading the room','Zalın vəziyyəti','Состояние зала'],["Tonight's book",'Bu axşamın rezervasiyaları','Бронирования на вечер'],['Seating suggestion','Oturma təklifi','Рекомендация по рассадке'],['Take a booking','Rezervasiya qəbul et','Принять бронь'],['Add to waitlist','Gözləmə siyahısına əlavə et','Добавить в лист ожидания'],['Previous day','Əvvəlki gün','Предыдущий день'],['Today','Bu gün','Сегодня'],['Next day','Növbəti gün','Следующий день'],['Service timeline','Xidmət zaman xətti','Лента сервиса'],['Waitlist','Gözləmə siyahısı','Лист ожидания'],['Open bills','Açıq hesablar','Открытые счета'],['Everything today','Bu günün hamısı','Всё за сегодня'],['The pass','Pass','Выдача'],['Waiting','Gözləyir','Ожидает'],['Cooking','Hazırlanır','Готовится'],['Ready to serve','Servisə hazırdır','Готово к подаче'],['Tap to start cooking','Hazırlamağa başlamaq üçün toxunun','Нажмите, чтобы начать готовить'],['Tap when ready','Hazır olduqda toxunun','Нажмите, когда готово'],['Tap when served','Servis edildikdə toxunun','Нажмите после подачи'],['Kitchen ticket status','Mətbəx sifariş statusu','Статус кухонных заказов'],['How the timers work','Taymerlər necə işləyir','Как работают таймеры'],['Menu engineering','Menyu analitikası','Инженерия меню'],['All dishes','Bütün yeməklər','Все блюда'],["Tomorrow's order",'Sabahın sifarişi','Заказ на завтра'],['Raise purchase orders','Satınalma sifarişləri yarat','Создать заказы поставщикам'],['Log waste','Tullantını qeyd et','Записать списание'],['Full stock list','Tam ehtiyat siyahısı','Полный список запасов'],['Regulars only','Yalnız daimi qonaqlar','Только постоянные гости'],['Guest book','Qonaq kitabı','Книга гостей'],['Last week','Keçən həftə','Прошлая неделя'],['This week','Bu həftə','Эта неделя'],['Next week','Gələn həftə','Следующая неделя'],['Rota','Növbə cədvəli','График смен'],['Revenue over thirty days','Otuz günlük gəlir','Выручка за тридцать дней'],['Average by weekday','Həftə günləri üzrə orta','Среднее по дням недели'],['Guest satisfaction','Qonaq məmnunluğu','Удовлетворённость гостей'],['Retention','Qayıdış','Возвращаемость'],['Menu performance','Menyu performansı','Эффективность меню'],['Where the waste is','Tullantı haradadır','Где возникают списания'],['Where the money went','Pul hara getdi','Куда ушли деньги'],['How guests paid','Qonaqlar necə ödəyib','Как платили гости'],["Today's payments",'Bugünkü ödənişlər','Платежи сегодня'],['Price movement over six weeks','Altı həftəlik qiymət dəyişməsi','Изменение цен за шесть недель'],['Purchase orders','Satınalma sifarişləri','Заказы поставщикам'],['Supplier scorecard','Təchizatçı qiymətləndirməsi','Оценка поставщиков'],['Hold an event','Tədbir rezerv et','Забронировать мероприятие'],['Branches','Filiallar','Филиалы'],['Group performance','Qrup performansı','Результаты группы'],['Roles and access','Rollar və giriş','Роли и доступ'],['Demo controls','Demo idarəetməsi','Управление демо'],['Reset demo data','Demo məlumatlarını sıfırla','Сбросить демо-данные']
 ];
 window.SUFRA_CORE_TRANSLATIONS=Object.fromEntries(R.map(([en,az,ru])=>[en,[az,ru]]));
 const M={az:new Map(),ru:new Map()};R.forEach(([e,a,r])=>{M.az.set(e,a);M.ru.set(e,r)});
 function tr(s){if(lang==='en'||!s)return s;const x=M[lang].get(s);if(x!==undefined)return x;let m,az=lang==='az';if((m=s.match(/^Table (\d+)$/)))return az?`Masa ${m[1]}`:`Стол ${m[1]}`;if((m=s.match(/^Seat (\d+)$/)))return az?`Oturacaq ${m[1]}`:`Место ${m[1]}`;if((m=s.match(/^(\d+) min$/)))return az?`${m[1]} dəq`:`${m[1]} мин`;if((m=s.match(/^(\d+) min ago$/)))return az?`${m[1]} dəq əvvəl`:`${m[1]} мин назад`;if((m=s.match(/^(\d+)% risk$/)))return az?`${m[1]}% risk`:`риск ${m[1]}%`;if((m=s.match(/^(\d+) people$/)))return az?`${m[1]} nəfər`:`${m[1]} чел.`;if((m=s.match(/^(\d+) guests?$/)))return az?`${m[1]} qonaq`:`${m[1]} гостей`;if((m=s.match(/^(.+?) · (Owner|General Manager|Manager|Host|Waiter|Bartender|Kitchen|Cashier|Inventory Manager)(.*)$/)))return `${m[1]} · ${tr(m[2])}${m[3]}`;return s}
 function node(n){if(!n||n.nodeType!==3||!n.parentElement||n.parentElement.closest('script,style,code,pre,textarea,[data-i18n-skip],[translate=no],.nova-lang-global,#command-lang'))return;const raw=n.nodeValue||'',x=raw.trim();if(!x)return;const y=tr(x);if(y!==x)n.nodeValue=raw.replace(x,y)}
 function walk(root=document.body){if(!root)return;root.querySelectorAll?.('option:not([value])').forEach(o=>o.value=o.textContent);const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode()))node(n);root.querySelectorAll?.('[placeholder],[title],[aria-label]').forEach(e=>['placeholder','title','aria-label'].forEach(a=>{const v=e.getAttribute(a),y=tr(v);if(v&&y!==v)e.setAttribute(a,y)}))}
 function staff(){return window.NOVA_ACTIVE_STAFF||window.NOVA?.auth?.getStaff?.()||null}function greet(){const h=new Date().getHours(),e=h<12?'Good morning':h<18?'Good afternoon':'Good evening';return lang==='en'?e:tr(e)}
 function identity(){const me=staff();if(!me)return;const first=(me.name||'').split(' ')[0];['#command-greeting','#w-greeting'].forEach(q=>{const e=document.querySelector(q);if(e){const v=`${greet()}${first?', '+first:''}`;if(e.textContent!==v)e.textContent=v}})}
 function mount(){let e=document.querySelector('#command-lang')||document.querySelector('.nova-lang-global');if(!e){e=document.createElement('div');e.className='nova-lang-global';e.innerHTML='<button type="button" data-lang="en">EN</button><button type="button" data-lang="az">AZ</button><button type="button" data-lang="ru">RU</button>';document.body.appendChild(e)}e.querySelectorAll('[data-lang]').forEach(b=>{b.classList.toggle('on',b.dataset.lang===lang);if(!b.dataset.globalWired){b.dataset.globalWired='1';b.addEventListener('click',()=>{try{localStorage.setItem(KEY,b.dataset.lang);localStorage.removeItem('nova-command-lang')}catch{}location.reload()})}})}
 function apply(){document.documentElement.lang=lang;mount();if(lang!=='en')walk();identity()}
 let t;const o=new MutationObserver(()=>{clearTimeout(t);t=setTimeout(apply,20)});function start(){apply();o.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']})}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();/* translate(): the phrase from the static dictionary, or '' when there is
   none. The machine-translation fallback below asks this first so it never
   re-translates something the dictionary already covers. It was being called
   before it existed, which threw on every text node and silently disabled the
   whole fallback pass — the reason odd strings stayed English. */
return{apply,get:()=>lang,translate:(s)=>{if(lang==='en'||!s)return '';const x=M[lang]&&M[lang].get(String(s).trim());return x===undefined?'':x}};
})();


/* NOVA COMPLETE LOCALIZATION V5 */
(()=>{
 const D={"A queue sorted by what breaks first. Take and change orders, mark dishes served, move a party, split a bill, take payment, page a manager. Built for a tablet held in one hand.":["Ən təcili işlərə görə sıralanmış növbə. Sifariş götürün və dəyişin, yeməkləri servis edilmiş kimi qeyd edin, qonaqları başqa masaya keçirin, hesabı bölün, ödəniş alın və meneceri çağırın. Bir əllə istifadə olunan planşet üçün hazırlanıb.","Очередь отсортирована по срочности. Принимайте и меняйте заказы, отмечайте подачу блюд, пересаживайте гостей, делите счёт, принимайте оплату и вызывайте менеджера. Интерфейс рассчитан на планшет в одной руке."],"Answers are computed from the restaurant's own data. Every reply says where the number came from.":["Cavablar restoranın öz məlumatları əsasında hesablanır. Hər cavab rəqəmin mənbəyini göstərir.","Ответы рассчитываются по данным самого ресторана. В каждом ответе указано, откуда взялась цифра."],"Anyone at a table":["Masada oturan hər kəs","Любой гость за столом"],"Are guests happy?":["Qonaqlar razıdır?","Гости довольны?"],"Ask":["Soruş","Спросить"],"Ask SUFRA":["SUFRA-dan soruşun","Спросить SUFRA"],"Ask about ingredients, dietary needs or pairings. Nothing is ordered from this screen.":["İnqrediyentlər, pəhriz tələbləri və uyğunlaşdırmalar barədə soruşun. Bu ekrandan sifariş verilmir.","Спросите об ингредиентах, диетических требованиях или сочетаниях. С этого экрана ничего не заказывается."],"Ask about the restaurant. Every answer says where the number came from.":["Restoran haqqında soruşun. Hər cavab rəqəmin mənbəyini göstərir.","Спросите о ресторане. В каждом ответе указано, откуда взялась цифра."],"Ask me about tonight, the kitchen, stock, the menu or the team.":["Bu axşam, mətbəx, ehtiyatlar, menyu və ya heyət barədə soruşun.","Спросите о сегодняшнем вечере, кухне, запасах, меню или команде."],"Ask me about tonight, yesterday, the kitchen, stock, the menu, the team or the money.":["Bu axşam, dünən, mətbəx, ehtiyatlar, menyu, heyət və ya maliyyə barədə soruşun.","Спросите о сегодняшнем вечере, вчерашнем дне, кухне, запасах, меню, команде или деньгах."],"Biggest movers first. A sharp rise is a reason to reprice a dish, not absorb it.":["Ən böyük dəyişikliklər əvvəl göstərilir. Kəskin qiymət artımı xərci udmaq yox, yeməyin qiymətini yenidən hesablamaq üçün siqnaldır.","Сначала показаны самые сильные изменения. Резкий рост — повод пересмотреть цену блюда, а не поглощать расход."],"Book a table, work the waitlist, and see the shape of the day.":["Masa rezerv edin, gözləmə siyahısını idarə edin və günün yükünü aydın görün.","Бронируйте столы, управляйте листом ожидания и сразу видьте загрузку дня."],"Branches, roles and how the product behaves.":["Filiallar, rollar və sistemin işləmə qaydaları.","Филиалы, роли и поведение системы."],"By reason, then by ingredient. Reason tells you the process to fix.":["Əvvəl səbəbə, sonra inqrediyentə görə. Səbəb hansı prosesi düzəltməli olduğunuzu göstərir.","Сначала по причине, затем по ингредиенту. Причина показывает, какой процесс нужно исправить."],"Click a cell to add, change or clear a shift.":["Növbə əlavə etmək, dəyişmək və ya silmək üçün xanaya klikləyin.","Нажмите на ячейку, чтобы добавить, изменить или удалить смену."],"Click a row to edit price, description, timing or allergens. Toggle availability to pull a dish from every screen at once.":["Qiyməti, təsviri, hazırlanma vaxtını və ya allergenləri dəyişmək üçün sətrə klikləyin. Mövcudluğu söndürsəniz, yemək bütün ekranlardan dərhal çıxarılacaq.","Нажмите на строку, чтобы изменить цену, описание, время приготовления или аллергены. Отключите доступность — и блюдо исчезнет со всех экранов."],"Daily takings, with the weekday pattern underneath it.":["Gündəlik gəlir və aşağıda həftə günləri üzrə tendensiya.","Дневная выручка и ниже — закономерность по дням недели."],"Dashed outline is free. Amber means food is dying at the pass. A halo means the table has been in one state longer than it should be.":["Kəsik kontur boş masa deməkdir. Kəhrəba rəng yeməyin passda çox gözlədiyini göstərir. Halqalı masa həmin statusda normadan artıq qalıb.","Пунктирный контур означает свободный стол. Янтарный цвет — блюдо слишком долго ждёт на выдаче. Ореол означает, что стол слишком долго находится в одном статусе."],"Demand against cover":["Tələb və ehtiyat örtüyü","Спрос и запас"],"Drag a table to redraw the floor. Tap one to open it.":["Zalı yenidən qurmaq üçün masanı sürüşdürün. Açmaq üçün masaya toxunun.","Перетащите стол, чтобы изменить план зала. Нажмите на стол, чтобы открыть его."],"Each block is a booking, placed on the hour it arrives. Height is party size.":["Hər kart rezervasiyadır: vaxt, qonağın adı və qrup ölçüsü birbaşa göstərilir.","Каждая карточка — бронь: время, имя гостя и размер компании видны сразу."],"Each ticket fills from the bottom as it burns through the time the model promised the guest. Past three quarters it turns amber; past the promise it turns red and climbs to the top of its rail. The promise is not the menu time — it accounts for how many tickets that station already had when the order fired.":["Hər çek modelin qonağa verdiyi vaxt istifadə olunduqca aşağıdan dolur. Vaxtın dörddə üçü keçəndə kəhrəba, vəd olunan vaxt aşanda qırmızı olur və relsin yuxarısına qalxır. Bu vaxt menyudakı vaxt deyil — sifariş mətbəxə göndəriləndə stansiyadakı mövcud çek yükü də nəzərə alınır.","Каждый чек заполняется снизу по мере расходования времени, обещанного гостю моделью. После трёх четвертей времени он становится янтарным, после превышения обещания — красным и поднимается наверх. Это не просто время из меню: учитывается очередь станции в момент отправки заказа."],"Every bill open in the building, and everything closed today.":["Restorandakı bütün açıq hesablar və bu gün bağlanan bütün hesablar.","Все открытые счета в ресторане и все счета, закрытые сегодня."],"Every hour of trading so far.":["Bu gün indiyədək hər iş saatı.","Каждый час работы за сегодня."],"Every transaction, including partial and split settlements.":["Qismən və bölünmüş ödənişlər daxil olmaqla bütün əməliyyatlar.","Все транзакции, включая частичные и разделённые оплаты."],"Everything a guest has asked for and not yet received.":["Qonağın istədiyi və hələ almadığı bütün xidmətlər.","Всё, что гость запросил и ещё не получил."],"Fill gaps from the forecast":["Proqnoza əsasən boş növbələri doldurun","Закрыть пробелы по прогнозу"],"Food plated and waiting for a runner.":["Hazır yeməklər runner tərəfindən aparılmağı gözləyir.","Готовые блюда ждут, когда их заберут на выдаче."],"For severe allergies, always speak directly with your waiter. Saved dishes are a shortlist only and are never sent to the kitchen.":["Ağır allergiyalar barədə həmişə birbaşa ofisiantınızla danışın. Yadda saxlanılan yeməklər yalnız seçim siyahısıdır və heç vaxt mətbəxə avtomatik göndərilmir.","При серьёзной аллергии обязательно поговорите с официантом. Сохранённые блюда — только список выбора и никогда автоматически не отправляются на кухню."],"Forecast covers exploded through every recipe. Ingredient demand, not a reorder point tripping over.":["Proqnozlaşdırılan qonaq sayı bütün reseptlər üzrə hesablanıb. Burada sadəcə minimum hədd yox, real inqrediyent tələbi göstərilir.","Прогноз гостей разложен по всем рецептам. Здесь показан реальный спрос на ингредиенты, а не простое срабатывание точки заказа."],"Four legs, scored separately. The weakest one is the one to work on.":["Dörd göstərici ayrıca qiymətləndirilir. Ən zəif göstərici üzərində işləmək lazımdır.","Четыре показателя оцениваются отдельно. Работать нужно прежде всего над самым слабым."],"Gluten free dessert":["Qlütensiz desert","Безглютеновый десерт"],"Held with consent. Click anyone to edit their notes, allergies and seating.":["Razılıqla saxlanılır. Qeydləri, allergiyaları və oturma üstünlüklərini dəyişmək üçün qonağa klikləyin.","Данные хранятся с согласия. Нажмите на гостя, чтобы изменить заметки, аллергии и предпочтения по рассадке."],"How many waiters do I need Friday?":["Cümə günü neçə ofisiant lazımdır?","Сколько официантов нужно в пятницу?"],"How many waiters should I schedule Friday?":["Cümə günü neçə ofisiant növbəyə salınmalıdır?","Сколько официантов поставить в смену в пятницу?"],"How much of the room has been here before.":["Zaldakı qonaqların nə qədəri əvvəllər burada olub.","Какая доля гостей в зале уже была здесь раньше."],"How this answers":["Bu cavab necə hesablanır","Как рассчитывается ответ"],"If the day changes":["Gün dəyişərsə","Если день изменится"],"Kitchen, service, stock, equipment and money, ranked by cost of ignoring.":["Mətbəx, xidmət, ehtiyat, avadanlıq və maliyyə — diqqətsiz qalmasının xərcinə görə sıralanıb.","Кухня, сервис, запасы, оборудование и деньги — по стоимости бездействия."],"SUFRA does not send guest orders from the phone. Your waiter takes and confirms the order.":["SUFRA qonağın sifarişini telefondan mətbəxə göndərmir. Sifarişi ofisiant götürür və təsdiqləyir.","SUFRA не отправляет заказ гостя с телефона на кухню. Заказ принимает и подтверждает официант."],"NOVA holds larger tables back when a matching booking is close.":["Uyğun rezervasiya yaxınlaşanda NOVA böyük masaları həmin rezervasiya üçün saxlayır.","Когда приближается подходящая бронь, NOVA придерживает большие столы для неё."],"Next few hours, with no-show risk scored per booking.":["Növbəti bir neçə saat və hər rezervasiya üçün gəlməmə riski.","Ближайшие часы с оценкой риска неявки по каждой брони."],"Nothing with nuts":["Qoz-fındıqsız seçimlər","Без орехов"],"Open the guest app and the waiter app side by side. Ask for water on the phone and watch it arrive in the waiter's queue.":["Qonaq və ofisiant tətbiqlərini yanaşı açın. Telefonda su istəyin və sorğunun ofisiantın növbəsində göründüyünə baxın.","Откройте приложение гостя и официанта рядом. Запросите воду с телефона и увидьте запрос в очереди официанта."],"Owner, general manager, host, inventory manager":["Sahib, baş menecer, hostes, ehtiyat meneceri","Владелец, генеральный менеджер, хостес, менеджер запасов"],"Owners switch between them. The group view compares all four.":["Sahiblər filiallar arasında keçid edə bilər. Qrup görünüşü dörd filialı müqayisə edir.","Владельцы могут переключаться между филиалами. Групповой вид сравнивает все четыре."],"Par level is the line you never want to drop below. Days cover is how many services the current stock survives.":["Par səviyyəsi ehtiyatın düşməməli olduğu minimum həddir. Gün örtüyü mövcud ehtiyatın neçə servisə çatacağını göstərir.","Par-уровень — минимальный запас, ниже которого лучше не опускаться. Days cover показывает, на сколько сервисов хватит текущего запаса."],"Prices, availability, allergens and what each dish is worth.":["Qiymətlər, mövcudluq, allergenlər və hər yeməyin biznes dəyəri.","Цены, доступность, аллергены и ценность каждого блюда для бизнеса."],"Private dining, functions and anything that takes over a room.":["Özəl yeməklər, tədbirlər və ayrıca zal tələb edən bütün rezervasiyalar.","Частные ужины, мероприятия и всё, что занимает отдельный зал."],"Questions are routed to a model, not to a language model. Forecasts come from a ridge regression over 180 trading days, shortfalls from exploding recipes over forecast covers, and revenue changes from a variance decomposition splitting the move into a covers effect and an average spend effect. The copilot phrases the result; it never invents the number.":["Suallar dil modelinə deyil, hesablayan modellərə yönləndirilir. Proqnoz 180 iş günü üzrə ridge reqressiyasından, çatışmazlıq proqnoz qonaq sayının reseptlərə bölünməsindən, gəlir dəyişməsi isə qonaq sayı və orta xərc təsirlərini ayıran variasiya analizindən gəlir. AI köməkçi yalnız nəticəni ifadə edir, rəqəmi uydurmur.","Вопросы направляются вычислительным моделям, а не языковой модели. Прогноз строится ridge-регрессией по 180 рабочим дням, дефицит — через раскладку прогноза гостей по рецептам, а изменение выручки — через декомпозицию на эффект количества гостей и среднего чека. AI-помощник только формулирует результат и не придумывает цифры."],"Quoted times come from how many suitable tables are actually free.":["Gözləmə vaxtı uyğun ölçülü masaların real mövcudluğuna əsasən hesablanır.","Ожидаемое время рассчитывается по фактически свободным столам подходящего размера."],"Raised by NOVA from forecast shortfalls, or by hand.":["NOVA tərəfindən proqnoz çatışmazlığına görə və ya əl ilə yaradılıb.","Создано NOVA из прогнозируемого дефицита или вручную."],"Ranked by what it costs if nobody acts.":["Heç kim tədbir görməsə yaradacağı xərcə görə sıralanıb.","Отсортировано по стоимости бездействия."],"Reading the room…":["Zal təhlil olunur…","Анализируем зал…"],"Recording it is what makes the pattern findable later.":["Qeyd etmək bu tendensiyanı sonradan aşkar etməyə imkan verir.","Фиксация позволяет позже обнаружить закономерность."],"Resetting rebuilds the demo restaurant.":["Sıfırlama demo restoranını yenidən qurur.","Сброс заново создаёт демо-ресторан."],"Revenue down to net, in the order the costs land.":["Xərclərin yaranma ardıcıllığı ilə gəlirdən xalis nəticəyədək.","От выручки до чистого результата в порядке возникновения расходов."],"Ridge regression over 180 trading days.":["180 iş günü üzrə ridge reqressiyası.","Ridge-регрессия по 180 рабочим дням."],"Saving a dish does not place an order. Your waiter confirms every item, modifier and allergy with you.":["Yeməyi yadda saxlamaq sifariş vermək deyil. Ofisiant hər yeməyi, əlavəni və allergiyanı sizinlə təsdiqləyir.","Сохранение блюда не оформляет заказ. Официант подтвердит с вами каждое блюдо, модификатор и аллергию."],"Scan, browse the menu with photos, filter allergies, save dishes and call for water, cutlery, a waiter or the bill. Orders are confirmed by staff. Nothing to install.":["QR kodu skan edin, şəkilli menyuya baxın, allergenlərə görə filtr edin, yeməkləri yadda saxlayın və su, çəngəl-bıçaq, ofisiant və ya hesab istəyin. Sifarişləri heyət təsdiqləyir. Heç nə quraşdırmaq lazım deyil.","Сканируйте QR-код, просматривайте меню с фотографиями, фильтруйте аллергены, сохраняйте блюда и вызывайте воду, приборы, официанта или счёт. Заказы подтверждает персонал. Устанавливать ничего не нужно."],"Score weighs reliability and quality against how long they take to deliver.":["Bal etibarlılıq və keyfiyyəti çatdırılma müddəti ilə birlikdə qiymətləndirir.","Оценка сопоставляет надёжность и качество со сроком поставки."],"Seat, cancel or mark a no-show. Risk is scored per booking.":["Qonağı əyləşdirin, rezervasiyanı ləğv edin və ya gəlməmə kimi qeyd edin. Risk hər rezervasiya üçün ayrıca hesablanır.","Посадите гостя, отмените бронь или отметьте неявку. Риск рассчитывается отдельно для каждой брони."],"Service is simulated so every screen has something to react to.":["Demo rejimində hər ekranın işləməsini göstərmək üçün xidmət simulyasiya edilir.","В демо-режиме сервис симулируется, чтобы на каждом экране были события."],"Sixteen screens: command centre, live operations, floor, reservations, orders, kitchen, menu, inventory, suppliers, guests, staff, events, analytics, finance, AI copilot and settings.":["On altı ekran: idarəetmə mərkəzi, canlı əməliyyatlar, zal, rezervasiyalar, sifarişlər, mətbəx, menyu, ehtiyatlar, təchizatçılar, qonaqlar, heyət, tədbirlər, analitika, maliyyə, AI köməkçi və ayarlar.","Шестнадцать экранов: центр управления, операции в реальном времени, зал, бронирования, заказы, кухня, меню, запасы, поставщики, гости, персонал, события, аналитика, финансы, AI-помощник и настройки."],"Split by method. Useful when a terminal goes down.":["Ödəniş üsuluna görə bölünüb. Terminal işləmədikdə xüsusilə faydalıdır.","Разбивка по способу оплаты. Полезно, если один из терминалов не работает."],"Split on median margin and median sales. Four groups, four different decisions.":["Median marja və median satışa görə dörd qrupa bölünür — hər qrup üçün fərqli qərar.","Разделение по медианной марже и продажам: четыре группы, четыре разных решения."],"Table duration":["Masa müddəti","Время за столом"],"Tap a ticket to move it on: waiting → on → ready.":["Çeki növbəti mərhələyə keçirmək üçün toxunun: gözləyir → hazırlanır → hazırdır.","Нажмите на чек, чтобы перевести его дальше: ожидание → готовится → готово."],"The book":["Rezervasiya kitabı","Книга броней"],"The rota, the wage bill, and whether it matches forecast demand.":["Növbə cədvəli, əməkhaqqı xərci və proqnoz tələbinə uyğunluğu.","График смен, фонд оплаты труда и соответствие прогнозируемому спросу."],"The same regression re-run against different conditions.":["Eyni reqressiya müxtəlif şərtlərlə yenidən hesablanır.","Та же регрессия пересчитывается для разных условий."],"Thirty days of trading, and what it says to do next.":["Otuz günlük fəaliyyət və bundan çıxan növbəti addımlar.","Тридцать дней работы и рекомендации, что делать дальше."],"Tonight across every branch.":["Bu axşam bütün filiallar üzrə.","Сегодня вечером по всем филиалам."],"Top dishes by thirty-day revenue.":["30 günlük gəlirə görə ən güclü yeməklər.","Лучшие блюда по выручке за 30 дней."],"Use menu filters for browsing, then tell your waiter about any allergy before ordering.":["Menyu filtrlərindən istifadə edin və sifarişdən əvvəl bütün allergiyalar barədə ofisianta məlumat verin.","Используйте фильтры меню и обязательно сообщите официанту об аллергиях до заказа."],"Useful information without replacing human service.":["İnsan xidmətini əvəz etmədən faydalı məlumat.","Полезная информация, не заменяющая живое обслуживание."],"Waiters, bartenders, runners":["Ofisiantlar, barmenlər, runnerlər","Официанты, бармены, раннеры"],"Water, cutlery, your waiter and the bill can be requested from the Menu screen.":["Su, çəngəl-bıçaq, ofisiant və hesab Menyu ekranından istənilə bilər.","Воду, приборы, официанта и счёт можно запросить с экрана меню."],"What came in, what it cost, and what is left.":["Nə daxil olub, neçəyə başa gəlib və nə qədər qalıb.","Что поступило, сколько стоило и сколько осталось."],"What is in the building, and what tomorrow needs.":["Hazırda ehtiyatda nə var və sabah nə lazım olacaq.","Что есть в запасе сейчас и что понадобится завтра."],"What the forecast says each day needs, against who is actually on the rota.":["Hər gün üçün proqnoz tələbi ilə real növbə heyətinin müqayisəsi.","Сравнение прогнозируемой потребности на каждый день с фактическим графиком персонала."],"What wine goes with the sea bass?":["Dəniz levreyi ilə hansı şərab uyğundur?","Какое вино подходит к сибасу?"],"What's vegan?":["Hansı yeməklər vegandır?","Что здесь веганское?"],"Which tables have service problems?":["Hansı masalarda xidmət problemi var?","У каких столов проблемы с обслуживанием?"],"Who comes back, what they eat, and what would hurt them.":["Kim geri qayıdır, nə yeyir və hansı allergenlər onlar üçün təhlükəlidir.","Кто возвращается, что ест и какие аллергены для них опасны."],"Who delivers, how reliably, and what they have been charging.":["Kim çatdırır, nə qədər etibarlıdır və hansı qiymətləri tətbiq edir.","Кто поставляет, насколько надёжен и какие цены выставляет."],"Who sees what. The waiter and guest apps enforce these as separate products.":["Kimin nə görə bildiyi. Ofisiant və qonaq tətbiqləri ayrıca məhsullar kimi bu giriş qaydalarını tətbiq edir.","Кто что видит. Приложения официанта и гостя используют отдельные права доступа как самостоятельные продукты."],"Why did food waste increase?":["Qida tullantısı niyə artdı?","Почему выросли списания продуктов?"],"Your shortlist to show your waiter.":["Ofisianta göstərmək üçün seçdiyiniz yeməklər.","Ваш список блюд, который можно показать официанту."],"ask the team":["heyətdən istəyin","попросить персонал"],"ask your waiter":["ofisiantdan istəyin","попросить официанта"],"average bill":["orta hesab","средний чек"],"extra sets":["əlavə dəst","дополнительный комплект"],"last seven days":["son yeddi gün","последние семь дней"],"mains served":["əsas yemək servis edilib","основных блюд подано"],"service in progress":["xidmət davam edir","обслуживание идёт"],"someone will come":["ofisiant gələcək","официант подойдёт"],"tickets open · oldest":["açıq çek · ən köhnə","открыто чеков · старейший"],"Bookings":["Rezervasiyalar","Брони"],"on the book":["rezervasiya kitabında","в книге"],"of capacity":["tutumdan","от вместимости"],"Regulars":["Daimi qonaqlar","Постоянные гости"],"expected":["gözlənilir","ожидаются"],"At risk":["Riskli","С риском"],"above 30% no-show":["30%-dən yüksək gəlməmə riski","риск неявки выше 30%"],"waiting now":["hazırda gözləyir","ждут сейчас"],"Reservation schedule":["Rezervasiya cədvəli","Расписание броней"],"Clear view of time, guest name, party size and remaining capacity.":["Vaxt, qonağın adı, qrup ölçüsü və qalan tutum bir baxışda görünür.","Время, имя гостя, размер компании и оставшаяся вместимость видны сразу."],"Approx. seats open":["Təxmini boş yer","Примерно свободно мест"],"booked guests":["rezerv edilmiş qonaq","забронировано гостей"],"No bookings in this hour":["Bu saat üçün rezervasiya yoxdur","В этот час броней нет"],"Time":["Vaxt","Время"],"Guest":["Qonaq","Гость"],"Party":["Qrup","Гостей"],"Risk":["Risk","Риск"],"Seat":["Əyləşdir","Посадить"],"No-show":["Gəlmədi","Неявка"],"Nothing booked for this day.":["Bu gün üçün rezervasiya yoxdur.","На этот день броней нет."],"Take a booking to start the book.":["Rezervasiya kitabını başlatmaq üçün ilk rezervasiyanı qəbul edin.","Примите первую бронь, чтобы начать книгу."],"Nobody waiting.":["Heç kim gözləmir.","Никто не ждёт."],"Walk-ins go straight to a table.":["Rezervasiyasız gələn qonaqlar birbaşa masaya əyləşdirilə bilər.","Гостей без брони можно сразу посадить за стол."],"Left":["Getdi","Ушёл"],"Guest name":["Qonağın adı","Имя гостя"],"Party size":["Qonaq sayı","Количество гостей"],"Date and time":["Tarix və vaxt","Дата и время"],"Where the booking came from":["Rezervasiyanın mənbəyi","Источник бронирования"],"Occasion":["Səbəb","Повод"],"None":["Yoxdur","Нет"],"Birthday":["Ad günü","День рождения"],"Anniversary":["İldönümü","Годовщина"],"Date":["Görüş","Свидание"],"Allergies":["Allergiyalar","Аллергии"],"Deposit taken":["Alınmış depozit","Полученный депозит"],"Note for the floor":["Zal üçün qeyd","Заметка для зала"],"Hold the table":["Masanı saxla","Забронировать стол"],"Name":["Ad","Имя"],"Phone":["Telefon","Телефон"],"Add and quote a time":["Əlavə et və gözləmə vaxtı hesabla","Добавить и рассчитать ожидание"],"website":["veb-sayt","сайт"],"phone":["telefon","телефон"],"walk-in":["rezervasiyasız","без брони"],"instagram":["Instagram","Instagram"],"concierge":["konsyerj","консьерж"],"regular":["daimi qonaq","постоянный гость"],"allergy":["allergiya","аллергия"],"ACTION CENTRE":["FƏALİYYƏT MƏRKƏZİ","ЦЕНТР ДЕЙСТВИЙ"],"LIVE SECTION":["CANLI BÖLMƏ","СЕКЦИЯ В РЕАЛЬНОМ ВРЕМЕНИ"],"YOUR TABLES":["SİZİN MASALARINIZ","ВАШИ СТОЛЫ"],"KITCHEN PASS":["MƏTBƏX PASSI","ВЫДАЧА КУХНИ"],"Where you're needed":["Harada sizə ehtiyac var","Где вы нужны"],"Service status":["Xidmət statusu","Статус обслуживания"],"Ready to serve":["Servisə hazırdır","Готово к подаче"],"You're clear. No open service requests.":["Hər şey qaydasındadır. Açıq xidmət sorğusu yoxdur.","Всё спокойно. Открытых запросов на обслуживание нет."],"No active tables assigned to you yet.":["Hələ sizə aktiv masa təyin edilməyib.","У вас пока нет активных назначенных столов."],"live with kitchen & management":["mətbəx və rəhbərliklə canlı sinxronizasiya","в реальном времени с кухней и управлением"],"Covers":["Qonaqlar","Гости"],"Open":["Aç","Открыть"],"All":["Hamısı","Все"],"Snack":["Qəlyanaltı","Закуски"],"Starter":["Başlanğıc","Стартеры"],"Main":["Əsas yemək","Основные блюда"],"Side":["Qarnir","Гарниры"],"Dessert":["Desert","Десерты"],"Drink":["İçki","Напитки"],"vegetarian":["vegetarian","вегетарианское"],"vegan":["vegan","веганское"],"gluten free":["qlütensiz","без глютена"],"halal":["halal","халяль"],"contains nuts":["qoz-fındıq var","содержит орехи"],"shellfish":["qabıqlı dəniz məhsulları","моллюски"],"dairy":["süd məhsulları","молочные продукты"],"fish":["balıq","рыба"],"contains gluten":["qlüten var","содержит глютен"],"sesame":["küncüt","кунжут"],"egg":["yumurta","яйцо"],"no alcohol":["alkoqolsuz","без алкоголя"],"digestif":["didjestiv","дижестив"],"red":["qırmızı","красное"],"white":["ağ","белое"],"cocktail":["kokteyl","коктейль"],"available":["boşdur","свободен"],"seated":["əyləşdirilib","посажены"],"ordered":["sifariş verilib","заказ принят"],"cooking":["hazırlanır","готовится"],"served":["servis edilib","подано"],"bill":["hesab","счёт"],"dirty":["təmizlənməlidir","нужна уборка"],"waiting":["gözləyir","ожидание"],"ready":["hazırdır","готово"],"cancelled":["ləğv edilib","отменено"],"no show":["gəlmədi","неявка"],"Wants a waiter":["Ofisiant istəyir","Нужен официант"],"Water":["Su","Вода"],"Bill":["Hesab","Счёт"],"Food at the pass":["Yemək passdadır","Блюдо на выдаче"],"Clear the table":["Masanı təmizlə","Убрать стол"],"Check in":["Masaya yaxınlaş","Проверить стол"],"Oyster & Champagne Mignonette":["İstridyə və şampan minyoneti","Устрицы с шампанским миньонетом"],"Gordal Olives":["Gordal zeytunları","Оливки Gordal"],"Sourdough & Cultured Butter":["Turş mayalı çörək və kulturalı kərə yağı","Заквасочный хлеб и культивированное масло"],"Burrata, Datterini, Basil Oil":["Burrata, datterini pomidoru, reyhan yağı","Буррата, томаты даттерини, базиликовое масло"],"Tuna Crudo, Yuzu, Sesame":["Tuna krudo, yuzu, küncüt","Крудо из тунца, юдзу, кунжут"],"Hand-Dived Scallop":["Əllə yığılmış dəniz darağı","Гребешок ручного сбора"],"Beef Tartare, Smoked Yolk":["Mal əti tartarı, hisə verilmiş yumurta sarısı","Тартар из говядины, копчёный желток"],"Wild Mushroom Croquette":["Meşə göbələyi kroketi","Крокет из лесных грибов"],"Vine Tomato & Watermelon":["Budaq pomidoru və qarpız","Томаты на ветке и арбуз"],"Porcini Risotto":["Porçini rizottosu","Ризотто с белыми грибами"],"Grilled Sea Bass, Asparagus":["Qrildə dəniz levreyi, qulançar","Сибас на гриле, спаржа"],"Dover Sole Meunière":["Dover kambalası meunière","Дуврская морская камбала меньер"],"Dry-Aged Ribeye 400g":["Quru yetişdirilmiş ribay 400 q","Рибай сухой выдержки 400 г"],"Rack of Lamb, Harissa":["Quzu qabırğası, harissa","Каре ягнёнка, харисса"],"Truffle Tagliatelle":["Trüfellə tagliatelle","Тальятелле с трюфелем"],"Lobster Ravioli":["Lobster raviolisi","Равиоли с лобстером"],"Confit Duck Leg, Cherry":["Konfi ördək budu, albalı","Утиная ножка конфи, вишня"],"Aubergine Katsu":["Badımcan katsusu","Кацу из баклажана"],"Cauliflower Steak, Tahini":["Gül kələmi steyki, tahini","Стейк из цветной капусты, тахини"],"Roast Chicken for Two":["İki nəfərlik sobada toyuq","Запечённая курица на двоих"],"Triple-Cooked Chips":["Üç dəfə bişirilmiş kartof","Картофель тройного приготовления"],"Charred Hispi Cabbage":["Qızardılmış hispi kələmi","Обожжённая капуста hispi"],"Green Beans, Almond":["Yaşıl lobya, badam","Зелёная фасоль, миндаль"],"Truffle Mash":["Trüfellə kartof püresi","Картофельное пюре с трюфелем"],"Chocolate Nemesis":["Şokolad Nemesis","Шоколадный Nemesis"],"Lemon Tart, Basil":["Limon tartı, reyhan","Лимонный тарт, базилик"],"Vanilla Ice Cream, Olive Oil":["Vanilli dondurma, zeytun yağı","Ванильное мороженое, оливковое масло"],"Cheese, Four Ways":["Dörd növ pendir","Четыре вида сыра"],"Martini, Very Cold":["Martini, çox soyuq","Мартини, очень холодный"],"Garden Spritz (0%)":["Garden Spritz (0%)","Garden Spritz (0%)"],"Sparkling Water":["Qazlı su","Газированная вода"],"Still Water":["Qazsız su","Вода без газа"],"Bread & Butter":["Çörək və kərə yağı","Хлеб и масло"],"Extra Sauce":["Əlavə sous","Дополнительный соус"],"Cappuccino":["Kapuçino","Капучино"],"Whole Turbot to Share":["Paylaşmaq üçün bütöv turbot","Целый тюрбо на компанию"],"Caviar Service 30g":["Kürü servisi 30 q","Подача икры 30 г"],"Six from Carlingford, three ways.":["Carlingford-dan altı istridyə, üç fərqli təqdimatda.","Шесть устриц из Carlingford в трёх подачах."],"Warmed with orange peel.":["Portağal qabığı ilə isidilib.","Подогреты с апельсиновой цедрой."],"Two-day ferment, house butter.":["İki günlük fermentasiya, restoranın öz kərə yağı.","Двухдневная ферментация, домашнее масло."],"Puglian burrata, still warm.":["Puglia burratası, hələ ilıq.","Буррата из Апулии, ещё тёплая."],"Line-caught, cured four hours.":["Xəttlə tutulub, dörd saat marinad edilib.","Выловлен на леску, выдержан четыре часа."],"Grilled in the shell, brown butter.":["Qabığında qrildə, qəhvəyi kərə yağı ilə.","На гриле в раковине, с коричневым маслом."],"Hand-cut sirloin, aged eight weeks.":["Əllə doğranmış sirloin, səkkiz həftə yetişdirilib.","Ручная нарезка сирлоина, выдержка восемь недель."],"Girolles, aged comté.":["Girolle göbələyi və yetişdirilmiş comté.","Лисички и выдержанный comté."],"Ten varieties, verjus.":["On növ pomidor, verjus.","Десять сортов, вержус."],"Carnaroli, 24-month parmesan.":["Carnaroli düyüsü, 24 aylıq parmesan.","Carnaroli, пармезан выдержки 24 месяца."],"Whole fillet, Cornish day boat.":["Bütöv file, Cornwall günlük ovundan.","Целое филе, дневной улов из Корнуолла."],"On the bone, filleted at table.":["Sümüklü servis edilir, masada filelənir.","Подаётся на кости, филируется у стола."],"60-day aged, bone marrow butter.":["60 günlük yetişdirmə, sümük iliyi yağı.","Выдержка 60 дней, масло с костным мозгом."],"Herdwick, north-facing pasture.":["Herdwick quzusu, şimal yamac otlağı.","Herdwick, пастбища северного склона."],"Fresh pasta, winter black truffle.":["Təzə pasta, qış qara trüfeli.","Свежая паста, зимний чёрный трюфель."],"Native lobster, bisque.":["Yerli lobster, bisk sousu.","Местный лобстер, биск."],"Slow-cooked nine hours.":["Doqquz saat yavaş bişirilib.","Томилось девять часов."],"Panko crust, curry from scratch.":["Panko qabığı, sıfırdan hazırlanmış karri.","Корочка панко, карри собственного приготовления."],"Charred whole, pomegranate.":["Bütöv qızardılıb, narla.","Обжарена целиком, с гранатом."],"Landes chicken, forty minutes.":["Landes toyuğu, qırx dəqiqə.","Курица Landes, сорок минут."],"Three days in the making.":["Üç günlük hazırlıq.","Готовится в течение трёх дней."],"Anchovy butter, or without.":["Ançouslu kərə yağı ilə və ya onsuz.","С анчоусным маслом или без него."],"Blanched to order.":["Sifarişə uyğun blanşlanır.","Бланшируется под заказ."],"Ratte potato, a lot of butter.":["Ratte kartofu, bol kərə yağı.","Картофель Ratte, много сливочного масла."],"Flourless, seventy percent.":["Unsuz, 70% şokolad.","Без муки, шоколад 70%."],"Amalfi lemons, torched.":["Amalfi limonu, alovla karamelizə edilib.","Лимоны Амальфи, обожжённая поверхность."],"Served in the bowl it set in.":["Hazırlandığı qabda servis edilir.","Подаётся в той же чаше, в которой застыл."],"Filled to order, Bronte pistachio.":["Sifarişlə doldurulur, Bronte püstəsi.","Наполняется под заказ, фисташка Bronte."],"Madagascan vanilla, Sicilian oil.":["Madaqaskar vanili, Siciliya zeytun yağı.","Мадагаскарская ваниль, сицилийское масло."],"From La Fromagerie, with quince.":["La Fromagerie-dən, heyva ilə.","Из La Fromagerie, с айвой."],"Prosecco instead of gin.":["Cin əvəzinə Prosecco.","Prosecco вместо джина."],"Stirred fifty turns, lemon or olive.":["Əlli dəfə qarışdırılır, limon və ya zeytunla.","Пятьдесят оборотов при смешивании, лимон или оливка."],"Seedlip, cucumber, elderflower.":["Seedlip, xiyar, mürver çiçəyi.","Seedlip, огурец, бузина."],"Decanted thirty minutes.":["Otuz dəqiqə dekantasiya edilir.","Декантируется тридцать минут."],"Montmains, mineral and taut.":["Montmains, mineral və canlı.","Montmains, минеральное и собранное."],"Filtered in-house, refilled free.":["Restoranda filtr edilir, pulsuz yenilənir.","Фильтруется в ресторане, доливается бесплатно."],"Single origin, changed monthly.":["Tək mənşəli, hər ay dəyişir.","Моносорт, меняется каждый месяц."],"For after, not before.":["Yeməkdən sonra üçün.","Для после еды, не до."],"Two to three people, market price.":["İki-üç nəfərlik, bazar qiyməti.","На двух-трёх человек, рыночная цена."],"Oscietra, blini, crème fraîche.":["Oscietra, blini, crème fraîche.","Oscietra, блины, crème fraîche."],"Filtered in-house, complimentary.":["Restoranda filtr edilir, ödənişsizdir.","Фильтруется в ресторане, бесплатно."],"Double shot, oat milk on request.":["İkiqat shot, istəyə görə yulaf südü.","Двойной шот, овсяное молоко по запросу."],"Sourdough, cultured butter.":["Turş mayalı çörək, kulturalı kərə yağı.","Заквасочный хлеб, культивированное масло."],"A little more on the side.":["Yanında bir az əlavə sous.","Немного дополнительного соуса отдельно."],"Notifications":["Bildirişlər","Уведомления"],"Anything the building wanted you to know.":["Restoranda bilməli olduğunuz bütün yeniliklər.","Всё важное, о чём ресторан хочет вас уведомить."],"Nothing waiting.":["Gözləyən tapşırıq yoxdur.","Ничего не ожидает."],"Alerts land here as they happen.":["Xəbərdarlıqlar baş verdiyi anda burada görünür.","Оповещения появляются здесь сразу после события."],"Service is running clean.":["Xidmət problemsiz gedir.","Сервис работает без проблем."],"Nothing is off pace, over capacity or short.":["Gecikmə, həddən artıq yük və ya çatışmazlıq yoxdur.","Нет задержек, перегрузки или дефицита."],"In service":["Xidmətdə","В обслуживании"],"Open tickets":["Açıq çeklər","Открытые чеки"],"Revenue":["Gəlir","Выручка"],"All quiet.":["Hər şey sakitdir.","Всё спокойно."],"No alert is currently open.":["Hazırda aktiv xəbərdarlıq yoxdur.","Сейчас нет активных предупреждений."],"Every plate has been carried.":["Bütün hazır yeməklər aparılıb.","Все готовые блюда уже вынесены."],"Nothing open.":["Açıq sorğu yoxdur.","Ничего не открыто."],"Every request has been closed.":["Bütün sorğular bağlanıb.","Все запросы закрыты."],"State":["Status","Статус"],"In this state":["Bu statusda","В этом статусе"],"Seated for":["Əyləşdiyi müddət","За столом"],"On the bill":["Hesabda","В счёте"],"Visits":["Ziyarətlər","Посещения"],"Allergy":["Allergiya","Аллергия"],"Usually orders":["Adətən sifariş edir","Обычно заказывает"],"Prefers":["Üstünlük verir","Предпочитает"],"Move this table to":["Masanın statusunu dəyiş","Перевести стол в статус"],"Nothing on the book.":["Rezervasiya yoxdur.","Броней нет."],"For the next few hours.":["Növbəti bir neçə saat üçün.","На ближайшие несколько часов."],"No large bookings close enough to plan around.":["Yaxın vaxtda xüsusi plan tələb edən böyük rezervasiya yoxdur.","В ближайшее время нет крупных броней, требующих отдельного плана."],"Fill":["Doluluq","Заполнение"],"not yet settled":["hələ ödənməyib","ещё не оплачено"],"Value on the floor":["Zaldakı hesab dəyəri","Сумма открытых столов"],"today":["bu gün","сегодня"],"Outstanding":["Ödənilməmiş","К оплате"],"still to collect":["hələ alınmalıdır","ещё нужно получить"],"No orders in this view.":["Bu görünüşdə sifariş yoxdur.","В этом представлении заказов нет."],"Open bills appear here the moment one is started.":["Açıq hesab yaradılan kimi burada görünür.","Открытый счёт появляется здесь сразу после создания."],"Price":["Qiymət","Цена"],"Food cost":["Məhsul maya dəyəri","Себестоимость продуктов"],"Prep minutes":["Hazırlanma dəqiqəsi","Время приготовления"],"Calories":["Kalori","Калории"],"Description":["Təsvir","Описание"],"Allergens and diets, comma separated":["Allergenlər və pəhrizlər, vergüllə ayırın","Аллергены и диеты через запятую"],"Available tonight. Unticking pulls it from the guest menu and the order pad immediately.":["Bu axşam mövcuddur. İşarəni götürsəniz, yemək qonaq menyusundan və sifariş panelindən dərhal çıxacaq.","Доступно сегодня. Снимите отметку — блюдо сразу исчезнет из меню гостя и панели заказа."],"Save changes":["Dəyişiklikləri saxla","Сохранить изменения"],"Dishes":["Yeməklər","Блюда"],"Average margin":["Orta marja","Средняя маржа"],"Stars":["Ulduzlar","Звёзды"],"popular and profitable":["populyar və gəlirli","популярные и прибыльные"],"Weak performers":["Zəif nəticələr","Слабые позиции"],"candidates to cut":["çıxarmaq üçün namizədlər","кандидаты на удаление"],"Lines tracked":["İzlənən məhsullar","Отслеживаемые позиции"],"ingredients":["inqrediyent","ингредиентов"],"Running short":["Azalır","Заканчиваются"],"against tomorrow":["sabaha qarşı","к завтрашнему дню"],"Tight":["Kritik həddə yaxın","Малый запас"],"under 1.6 services":["1.6 servisdən az","меньше 1,6 сервиса"],"Order value":["Sifariş dəyəri","Стоимость заказа"],"if raised now":["indi yaradılarsa","если оформить сейчас"],"Stock value":["Ehtiyat dəyəri","Стоимость запасов"],"on hand":["hazırda stokda","в наличии"],"Nothing to order.":["Sifariş ediləcək heç nə yoxdur.","Заказывать ничего не нужно."],"Every ingredient covers tomorrow at current stock.":["Mövcud ehtiyatla bütün inqrediyentlər sabaha çatır.","Текущих запасов всех ингредиентов хватает на завтра."],"Ingredient":["İnqrediyent","Ингредиент"],"Quantity":["Miqdar","Количество"],"Reason":["Səbəb","Причина"],"Log it":["Qeyd et","Записать"],"Tomorrow as forecast":["Sabah — proqnoza görə","Завтра по прогнозу"],"If it rains hard":["Güclü yağış olarsa","Если будет сильный дождь"],"With a local event":["Yerli tədbirlə","При локальном мероприятии"],"Public holiday":["Rəsmi bayram","Праздничный день"],"Average spend":["Orta xərc","Средний чек"],"Lifetime value":["Ümumi müştəri dəyəri","Пожизненная ценность"],"Next booking":["Növbəti rezervasiya","Следующая бронь"],"Seating preference":["Oturma üstünlüyü","Предпочтение по рассадке"],"Flag as a regular. The floor sees this before they sit down.":["Daimi qonaq kimi işarələyin. Zal heyəti qonaq əyləşməmişdən əvvəl bunu görəcək.","Отметьте как постоянного гостя. Зал увидит это до посадки гостя."],"Save":["Saxla","Сохранить"],"On the book":["Qonaq bazasında","В гостевой базе"],"guest records":["qonaq qeydi","записей гостей"],"flagged":["işarələnib","отмечено"],"With allergies":["Allergiyası olan","С аллергиями"],"need briefing":["heyət məlumatlandırılmalıdır","нужно предупредить персонал"],"combined":["ümumi","всего"],"No guests match that.":["Uyğun qonaq tapılmadı.","Подходящих гостей не найдено."],"Try a different name, or clear the search.":["Başqa ad sınayın və ya axtarışı təmizləyin.","Попробуйте другое имя или очистите поиск."],"Start":["Başlanğıc","Начало"],"End":["Son","Окончание"],"Status":["Status","Статус"],"Update shift":["Növbəni yenilə","Обновить смену"],"Add shift":["Növbə əlavə et","Добавить смену"],"Team":["Heyət","Команда"],"on shift now":["hazırda növbədədir","сейчас на смене"],"Rostered hours":["Planlaşdırılmış saatlar","Часы по графику"],"this week":["bu həftə","на этой неделе"],"Wage bill":["Əməkhaqqı fondu","Фонд оплаты труда"],"Average rating":["Orta reytinq","Средний рейтинг"],"Revenue, 30 days":["Gəlir, 30 gün","Выручка, 30 дней"],"total":["cəmi","всего"],"guests served":["xidmət olunan qonaq","обслужено гостей"],"Waste":["Tullantı","Списания"],"at cost":["maya dəyəri ilə","по себестоимости"],"Repeat guests":["Təkrar qonaqlar","Повторные гости"],"Guests on record":["Bazadakı qonaqlar","Гостей в базе"],"Been before":["Əvvəl gəlib","Были раньше"],"Repeat rate":["Təkrar gəliş faizi","Доля повторных визитов"],"Average visits":["Orta ziyarət sayı","Среднее число визитов"],"Gross profit":["Ümumi mənfəət","Валовая прибыль"],"Wages":["Əməkhaqqı","Зарплаты"],"Net":["Xalis nəticə","Чистый результат"],"before fixed costs":["sabit xərclərdən əvvəl","до постоянных расходов"],"Tips":["Çaypulu","Чаевые"],"to the team":["heyətə","команде"],"No payments yet today.":["Bu gün hələ ödəniş yoxdur.","Сегодня платежей пока нет."],"They appear here the moment a bill is settled.":["Hesab ödənilən kimi burada görünür.","Платёж появится здесь сразу после закрытия счёта."],"active accounts":["aktiv hesab","активных аккаунтов"],"Rising prices":["Artan qiymətlər","Растущие цены"],"up over 5% in six weeks":["6 həftədə 5%-dən çox artıb","рост более 5% за шесть недель"],"Open orders":["Açıq sifarişlər","Открытые заказы"],"not yet delivered":["hələ çatdırılmayıb","ещё не доставлены"],"Committed":["Öhdəlik götürülmüş","Обязательства"],"No purchase orders yet.":["Hələ satınalma sifarişi yoxdur.","Заказов поставщикам пока нет."],"Raise them from the inventory screen.":["Onları ehtiyat ekranından yaradın.","Создайте их на экране запасов."],"Event name":["Tədbirin adı","Название мероприятия"],"Room":["Zal","Помещение"],"Private dining":["Özəl zal","Приватный зал"],"Cellar room":["Zirzəmi zalı","Зал в погребе"],"Terrace":["Terras","Терраса"],"Whole restaurant":["Bütün restoran","Весь ресторан"],"Per head":["Nəfər başına","На человека"],"Contact":["Əlaqə","Контакт"],"Kitchen and floor notes":["Mətbəx və zal üçün qeydlər","Заметки для кухни и зала"],"Hold the room":["Zalı rezerv et","Забронировать помещение"],"Upcoming":["Gələcək","Предстоящие"],"events booked":["rezerv edilmiş tədbir","забронировано мероприятий"],"guests committed":["təsdiqlənmiş qonaq","подтверждено гостей"],"Value":["Dəyər","Стоимость"],"at agreed per-head":["razılaşdırılmış nəfər başı qiymətlə","по согласованной цене на человека"],"Deposits held":["Alınmış depozitlər","Полученные депозиты"],"30% of value":["dəyərin 30%-i","30% стоимости"],"Deposit":["Depozit","Депозит"],"When":["Vaxt","Когда"],"delivered":["tamamlanıb","завершено"],"No events booked.":["Rezerv edilmiş tədbir yoxdur.","Мероприятий нет."],"Hold a room to start the diary.":["Tədbir təqvimini başlatmaq üçün zal rezerv edin.","Забронируйте помещение, чтобы начать календарь событий."],"Reset the demo?":["Demo sıfırlansın?","Сбросить демо?"],"Yes, rebuild it":["Bəli, yenidən qur","Да, пересоздать"],"Keep what I have":["Mövcud məlumatları saxla","Оставить текущие данные"],"Starters":["Başlanğıclar","Закуски"],"Raw / Cold":["Çiy / Soyuq","Сырое / Холодное"],"Mains":["Əsas yeməklər","Основные блюда"],"Grill":["Qril","Гриль"],"Sides":["Qarnirlər","Гарниры"],"Desserts":["Desertlər","Десерты"],"Drinks":["İçkilər","Напитки"],"Wine":["Şərab","Вино"],"Cocktails":["Kokteyllər","Коктейли"],"Cooking temperature":["Bişmə dərəcəsi","Степень прожарки"],"Rare":["Az bişmiş","Rare"],"Medium Rare":["Orta-az bişmiş","Medium Rare"],"Medium":["Orta bişmiş","Medium"],"Medium Well":["Orta-yaxşı bişmiş","Medium Well"],"Well Done":["Tam bişmiş","Well Done"],"Sauce":["Sous","Соус"],"Peppercorn":["İstiot sousu","Перечный соус"],"Béarnaise":["Bearnez","Беарнез"],"No Sauce":["Sous olmasın","Без соуса"],"Fries":["Fri kartof","Картофель фри"],"Mashed Potato":["Kartof püresi","Картофельное пюре"],"Vegetables":["Tərəvəzlər","Овощи"],"Special request":["Xüsusi istək","Особая просьба"],"No dairy":["Süd məhsulsuz","Без молочного"],"No salt":["Duzsuz","Без соли"],"Sauce on side":["Sous ayrıca","Соус отдельно"],"No garlic":["Sarımsaqsız","Без чеснока"],"No onion":["Soğansız","Без лука"],"Ready to carry":["Aparmağa hazırdır","Готово к выносу"],"Nothing waiting at the pass.":["Passda gözləyən yemək yoxdur.","На выдаче ничего не ждёт."],"Serve":["Servis et","Подать"],"LIVE FLOOR":["CANLI ZAL","ЗАЛ В РЕАЛЬНОМ ВРЕМЕНИ"],"Blue tables are yours. Colored rings show requests and ready food.":["Mavi masalar sizindir. Rəngli halqalar sorğuları və hazır yeməkləri göstərir.","Синие столы — ваши. Цветные кольца показывают запросы и готовые блюда."],"Your table":["Sizin masanız","Ваш стол"],"Guest request":["Qonaq sorğusu","Запрос гостя"],"ASSIGNED TO YOU":["SİZƏ TƏYİN EDİLİB","НАЗНАЧЕНО ВАМ"],"SERVICE QUEUE":["XİDMƏT NÖVBƏSİ","ОЧЕРЕДЬ СЕРВИСА"],"Tasks & requests":["Tapşırıqlar və sorğular","Задачи и запросы"],"Open a table for context, or mark the task done when the guest has been served.":["Ətraflı məlumat üçün masanı açın və ya xidmət tamamlandıqda tapşırığı bitmiş kimi qeyd edin.","Откройте стол для контекста или отметьте задачу выполненной после обслуживания гостя."],"Course is empty":["Kurs boşdur","Курс пуст"],"Choose a seat, then tap dishes.":["Oturacağı seçin, sonra yeməklərə toxunun.","Выберите место, затем добавьте блюда."],"Course total":["Kursun cəmi","Итого по курсу"],"Keep draft":["Qaralamanı saxla","Сохранить черновик"],"Draft kept on this tablet.":["Qaralama bu planşetdə saxlanıldı.","Черновик сохранён на этом планшете."],"Shared / table":["Ümumi / masa","Общее / стол"],"Nothing ordered yet":["Hələ sifariş yoxdur","Пока ничего не заказано"],"Guest preference":["Qonaq üstünlüyü","Предпочтение гостя"],"Internal":["Daxili","Внутреннее"],"Acknowledge allergy":["Allergiyanı təsdiqlə","Подтвердить аллергию"],"No notes yet.":["Hələ qeyd yoxdur.","Заметок пока нет."],"Write a clear note":["Aydın qeyd yazın","Напишите понятную заметку"],"Couldn't load seats.":["Oturacaqları yükləmək mümkün olmadı.","Не удалось загрузить места."],"Couldn't load notes.":["Qeydləri yükləmək mümkün olmadı.","Не удалось загрузить заметки."],"Couldn't load the bill.":["Hesabı yükləmək mümkün olmadı.","Не удалось загрузить счёт."],"Nothing ordered yet.":["Hələ heç nə sifariş edilməyib.","Пока ничего не заказано."],"Card":["Kart","Карта"],"Cash":["Nağd","Наличные"],"For split-by-item or custom amounts, use the manager/cashier workflow.":["Məhsul üzrə bölünmüş və ya fərdi məbləğli ödəniş üçün menecer/kassir axınından istifadə edin.","Для оплаты по позициям или произвольной суммы используйте интерфейс менеджера/кассира."],"enter PIN":["PIN daxil edin","введите PIN"],"Show me only":["Yalnız bunları göstər","Показывать только"],"Leave out":["Bunları çıxar","Исключить"],"Clear all":["Hamısını təmizlə","Очистить всё"],"Nothing matches that.":["Uyğun nəticə yoxdur.","Ничего не найдено."],"Try another search or clear a filter.":["Başqa axtarış edin və ya filtri təmizləyin.","Попробуйте другой поиск или очистите фильтр."],"signature":["imza yeməyi","фирменное"],"Remove from saved":["Yadda saxlanılanlardan sil","Удалить из сохранённых"],"Save to my selections":["Seçimlərimə əlavə et","Сохранить в мой список"],"Remove":["Sil","Удалить"],"Tap the heart beside dishes you may want.":["Bəyəndiyiniz yeməklərin yanındakı ürək işarəsinə toxunun.","Нажмите на сердечко рядом с блюдами, которые хотите сохранить."],"MAIN ROOM":["ƏSAS ZAL","ОСНОВНОЙ ЗАЛ"],"PRIVATE":["ÖZƏL","ПРИВАТНЫЙ"],"TERRACE":["TERRAS","ТЕРРАСА"],"BAR":["BAR","БАР"],"SUFRA · Waiter":["SUFRA · Ofisiant","SUFRA · Официант"]};
 Object.assign(window.SUFRA_CORE_TRANSLATIONS,D);
 const lang=(()=>{try{const x=localStorage.getItem('nova-lang')||'en';return ['en','az','ru'].includes(x)?x:'en'}catch{return'en'}})();
 if(lang==='en') return;
 const ix=lang==='az'?0:1;
 const exact=s=>D[s]?.[ix];
 function tr(s){
   if(!s) return s;
   const raw=String(s), x=raw.trim(); if(!x) return s;
   let y=exact(x); if(y!==undefined) return raw.replace(x,y);
   let m; const az=lang==='az';
   if((m=x.match(/^Section ([A-Z])$/))) y=az?`Bölmə ${m[1]}`:`Секция ${m[1]}`;
   else if((m=x.match(/^(.+)'s service board$/))) y=az?`${m[1]} üçün xidmət paneli`:`Панель сервиса — ${m[1]}`;
   else if((m=x.match(/^(\d+) active tables · (\d+) covers · live with kitchen & management$/))) y=az?`${m[1]} aktiv masa · ${m[2]} qonaq · mətbəx və rəhbərliklə canlı sinxronizasiya`:`Активных столов: ${m[1]} · гостей: ${m[2]} · синхронизация с кухней и управлением`;
   else if((m=x.match(/^(\d+) active tables$/))) y=az?`${m[1]} aktiv masa`:`Активных столов: ${m[1]}`;
   else if((m=x.match(/^(\d+) covers$/))) y=az?`${m[1]} qonaq`:`Гостей: ${m[1]}`;
   else if((m=x.match(/^(\d+) open$/))) y=az?`${m[1]} açıq`:`Открыто: ${m[1]}`;
   else if((m=x.match(/^Table (\d+)$/))) y=az?`Masa ${m[1]}`:`Стол ${m[1]}`;
   else if((m=x.match(/^Table (\d+) · (\d+) seats$/))) y=az?`Masa ${m[1]} · ${m[2]} yer`:`Стол ${m[1]} · ${m[2]} мест`;
   else if((m=x.match(/^Seat (\d+)$/))) y=az?`Oturacaq ${m[1]}`:`Место ${m[1]}`;
   else if((m=x.match(/^(\d+) guests?$/))) y=az?`${m[1]} qonaq`:`${m[1]} гостей`;
   else if((m=x.match(/^(\d+) people$/))) y=az?`${m[1]} nəfər`:`${m[1]} гостей`;
   else if((m=x.match(/^(\d+)p$/))) y=az?`${m[1]} nəfər`:`${m[1]} чел.`;
   else if((m=x.match(/^(\d+) min$/))) y=az?`${m[1]} dəq`:`${m[1]} мин`;
   else if((m=x.match(/^(\d+)[–-](\d+) min$/))) y=az?`${m[1]}–${m[2]} dəq`:`${m[1]}–${m[2]} мин`;
   else if((m=x.match(/^waiting (\d+)m, quoted (\d+)m$/))) y=az?`${m[1]} dəq gözləyir · təxmini ${m[2]} dəq`:`Ждёт ${m[1]} мин · обещано ${m[2]} мин`;
   else if((m=x.match(/^of (\d+) seats$/))) y=az?`${m[1]} yerdən`:`из ${m[1]} мест`;
   else if((m=x.match(/^(\d+)% of capacity$/))) y=az?`tutumun ${m[1]}%-i`:`${m[1]}% вместимости`;
   else if((m=x.match(/^allergy: (.+)$/i))) y=az?`allergiya: ${m[1]}`:`аллергия: ${m[1]}`;
   else if((m=x.match(/^Added\. Quoted (\d+) minutes\.$/))) y=az?`Əlavə edildi. Təxmini gözləmə: ${m[1]} dəq.`:`Добавлено. Ожидание: около ${m[1]} мин.`;
   else if((m=x.match(/^Marked (.+)$/))) y=az?`${tr(m[1])} kimi qeyd edildi`:`Отмечено: ${tr(m[1])}`;
   else if((m=x.match(/^(.+?) · Waiter · Section ([A-Z])$/))) y=az?`${m[1]} · Ofisiant · Bölmə ${m[2]}`:`${m[1]} · Официант · Секция ${m[2]}`;
   else if((m=x.match(/^Waiter · Section ([A-Z])$/))) y=az?`Ofisiant · Bölmə ${m[1]}`:`Официант · Секция ${m[1]}`;
   else if((m=x.match(/^(\d+) tickets open, oldest (\d+)m$/))) y=az?`${m[1]} açıq çek · ən köhnəsi ${m[2]} dəq`:`Открыто чеков: ${m[1]} · старейшему ${m[2]} мин`;
   else if((m=x.match(/^(\d+) of (\d+) tables$/))) y=az?`${m[1]} / ${m[2]} masa`:`${m[1]} из ${m[2]} столов`;
   else if((m=x.match(/^(\d+) covers · (\d+) booked$/))) y=az?`${m[1]} qonaq · ${m[2]} rezerv edilib`:`${m[1]} гостей · ${m[2]} забронировано`;
   else if((m=x.match(/^(\d+) things? worth acting on before (\d{2}:\d{2})\.$/))) y=az?`${m[1]} məsələ ${m[2]}-dək tədbir tələb edir.`:`${m[1]} задач требуют действий до ${m[2]}.`;
   else if((m=x.match(/^(.+?) — NOVA$/))) {const z=exact(m[1])||m[1]; y=`${z} — SUFRA`;}
   if(y!==undefined) return raw.replace(x,y);
   return s;
 }
 function textNode(n){if(!n||n.nodeType!==3||!n.parentElement||n.parentElement.closest('script,style,code,pre,textarea,[data-i18n-skip],[translate=no],.nova-lang-global,#command-lang'))return;const v=n.nodeValue||'',x=v.trim();if(!x)return;const y=tr(v);if(y!==v)n.nodeValue=y;}
 function walk(root=document.body){if(!root)return;root.querySelectorAll?.('option:not([value])').forEach(o=>o.value=o.textContent);const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode()))textNode(n);root.querySelectorAll?.('[placeholder],[title],[aria-label]').forEach(e=>['placeholder','title','aria-label'].forEach(a=>{const v=e.getAttribute(a),y=tr(v);if(v&&y!==v)e.setAttribute(a,y)}));if(document.title)document.title=tr(document.title);}
 function localDate(){document.querySelectorAll('[data-nova-date]').forEach(e=>{const v=e.dataset.novaDate;if(!v)return;try{const label=new Date(v+'T12:00:00').toLocaleDateString(lang==='az'?'az-AZ':'ru-RU',{weekday:'short',day:'numeric',month:'short',year:'numeric'});if(e.textContent!==label)e.textContent=label}catch{}})}
 let timer=0;function apply(){walk();localDate();}
 const mo=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(apply,25)});
 function start(){apply();mo.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']})}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
 window.NOVA_I18N_COMPLETE={tr,apply,lang};
})();

/* NOVA OPERATIONS V10 I18N */
(()=>{
 const lang=(()=>{try{return localStorage.getItem('nova-lang')||'en'}catch{return'en'}})();if(lang==='en')return;const az=lang==='az';
 const D={
 'AI Order Inspector':['AI Sifariş Yoxlayıcısı','AI Проверка заказа'],'AI CHECK':['AI YOXLAMA','AI ПРОВЕРКА'],'No order risks detected.':['Sifariş riski aşkarlanmadı.','Рисков в заказе не обнаружено.'],'Recommended firing sequence':['Tövsiyə olunan hazırlanma ardıcıllığı','Рекомендуемая последовательность запуска'],'Back to order':['Sifarişə qayıt','Вернуться к заказу'],'Confirm & send':['Təsdiqlə və göndər','Подтвердить и отправить'],'Critical conflicts must be fixed before this order can be sent.':['Sifariş göndərilməzdən əvvəl kritik uyğunsuzluqlar düzəldilməlidir.','Критические конфликты нужно исправить до отправки заказа.'],'Change':['Dəyiş','Изменить'],'Remove':['Sil','Удалить'],'Remove sent item':['Göndərilmiş məhsulu sil','Удалить отправленную позицию'],'Change sent item':['Göndərilmiş məhsulu dəyiş','Изменить отправленную позицию'],'Reason':['Səbəb','Причина'],'Remove & notify kitchen':['Sil və mətbəxə bildir','Удалить и уведомить кухню'],'Update kitchen':['Mətbəxi yenilə','Обновить кухню'],'Guest requested a change':['Qonaq dəyişiklik istədi','Гость попросил изменение'],'Manager':['Menecer','Менеджер'],'Complaint':['Şikayət','Жалоба'],'File a complaint':['Şikayət yaz','Оформить жалобу'],'Category':['Kateqoriya','Категория'],'What happened':['Nə baş verdi','Что произошло'],'Send to management':['Rəhbərliyə göndər','Отправить руководству'],'Service':['Xidmət','Сервис'],'Food':['Yemək','Еда'],'Billing':['Hesablaşma','Оплата'],'Other':['Digər','Другое'],'Split equally':['Bərabər böl','Разделить поровну'],'By item':['Məhsullar üzrə','По позициям'],'Custom':['Fərdi məbləğ','Своя сумма'],'Number of shares':['Pay sayı','Количество долей'],'Amount':['Məbləğ','Сумма'],'Tip':['Çaypulu','Чаевые'],'No tip':['Çaypulu yoxdur','Без чаевых'],'Take payment':['Ödənişi qəbul et','Принять оплату'],'Pay now':['İndi ödə','Оплатить сейчас'],'Tables & waiter assignments':['Masalar və ofisiant təyinatları','Столы и назначения официантов'],'Assignments update the waiter tablet immediately.':['Təyinatlar ofisiant planşetində dərhal yenilənir.','Назначения сразу обновляются на планшете официанта.'],'Add table':['Masa əlavə et','Добавить стол'],'Unassigned':['Təyin edilməyib','Не назначен'],'Remove table':['Masanı sil','Убрать стол'],'Removed tables':['Silinmiş masalar','Убранные столы'],'Bring back':['Geri qaytar','Вернуть'],'Table number':['Masa nömrəsi','Номер стола'],'Zone':['Zona','Зона'],'Shape':['Forma','Форма'],'Assign waiter':['Ofisiant təyin et','Назначить официанта'],'Add to floor':['Zala əlavə et','Добавить в зал'],'Order changes':['Sifariş dəyişiklikləri','Изменения заказов'],'Changes made after sending stay here until the kitchen acknowledges them.':['Göndərildikdən sonra edilən dəyişikliklər mətbəx təsdiqləyənədək burada qalır.','Изменения после отправки остаются здесь, пока кухня их не подтвердит.'],'Acknowledge':['Təsdiqlə','Подтвердить'],'Unavailable':['86 / mövcud deyil paneli','86 / нет в наличии'],'Mark a dish or ingredient unavailable. Waiter and guest menus update immediately.':['Yeməyi və ya inqrediyenti mövcud deyil kimi qeyd edin. Ofisiant və qonaq menyuları dərhal yenilənir.','Отметьте блюдо или ингредиент как отсутствующий. Меню официанта и гостя обновятся сразу.'],'Mark unavailable':['Mövcud deyil kimi qeyd et','Отметить недоступным'],'Back on':['Yenidən mövcuddur','Вернуть в наличие'],'Everything available.':['Hər şey mövcuddur.','Всё в наличии.'],'No dishes or ingredients are currently blocked.':['Hazırda heç bir yemək və ya inqrediyent bloklanmayıb.','Сейчас нет заблокированных блюд или ингредиентов.'],'Type':['Növ','Тип'],'Dish / ingredient':['Yemək / inqrediyent','Блюдо / ингредиент'],'Dish':['Yemək','Блюдо'],'Ingredient':['İnqrediyent','Ингредиент'],'Mark unavailable now':['İndi mövcud deyil et','Сделать недоступным'],'Menu structure':['Menyu strukturu','Структура меню'],'Add sections such as Business Lunch or Set Menu, add dishes, or restore removed dishes.':['Business Lunch və ya Set Menu kimi bölmələr, yeməklər əlavə edin və silinənləri bərpa edin.','Добавляйте разделы вроде Business Lunch или Set Menu, блюда и восстанавливайте удалённые блюда.'],'Section':['Bölmə','Раздел'],'Add menu section':['Menyu bölməsi əlavə et','Добавить раздел меню'],'Section name':['Bölmə adı','Название раздела'],'Add section':['Bölmə əlavə et','Добавить раздел'],'Add dish':['Yemək əlavə et','Добавить блюдо'],'Dish name':['Yeməyin adı','Название блюда'],'Station':['Stansiya','Станция'],'Price':['Qiymət','Цена'],'Food cost':['Maya dəyəri','Себестоимость'],'Prep minutes':['Hazırlanma dəqiqələri','Время приготовления'],'Description':['Təsvir','Описание'],'Tags / allergens':['Teqlər / allergenlər','Теги / аллергены'],'Removed dishes':['Silinmiş yeməklər','Удалённые блюда'],'Restore':['Bərpa et','Восстановить'],'Edit section':['Bölməni dəyiş','Изменить раздел'],'Rename':['Adını dəyiş','Переименовать'],'Delete empty section':['Boş bölməni sil','Удалить пустой раздел'],'Manager & complaint desk':['Menecer və şikayət paneli','Панель менеджера и жалоб'],'Guest and waiter complaints arrive here in real time.':['Qonaq və ofisiant şikayətləri burada real vaxtda görünür.','Жалобы гостей и официантов появляются здесь в реальном времени.'],'Resolve':['Həll et','Закрыть'],'No open complaints.':['Açıq şikayət yoxdur.','Нет открытых жалоб.'],'Guest and waiter complaints will appear here immediately.':['Qonaq və ofisiant şikayətləri dərhal burada görünəcək.','Жалобы гостей и официантов появятся здесь сразу.'],'Reservation schedule':['Rezervasiya təqvimi','Календарь бронирований'],'Clear view of time, guest name, party size and remaining capacity.':['Vaxt, qonağın adı, qrup ölçüsü və qalan tutum aydın göstərilir.','Наглядно показаны время, имя гостя, размер компании и оставшаяся вместимость.'],'bookings':['rezervasiya','бронирований'],'guests':['qonaq','гостей'],'total seats':['ümumi yer','мест всего'],'Table not assigned':['Masa təyin edilməyib','Стол не назначен'],'Not assigned':['Təyin edilməyib','Не назначен'],'No-show risk':['Gəlməmə riski','Риск неявки'],'Occasion':['Səbəb','Повод'],'Floor note':['Zal qeydi','Заметка для зала'],'Manager requested':['Menecer çağırılıb','Менеджер вызван'],'tell management':['rəhbərliyə bildirin','сообщить руководству'],'ask for a manager':['menecer çağırın','позвать менеджера'],'Unavailable':['Mövcud deyil','Недоступно'],'Kitchen unavailable':['Mətbəxdə mövcud deyil','Нет на кухне'],'This updates the kitchen immediately and removes it from the bill.':['Bu dəyişiklik mətbəxə dərhal göndərilir və məhsul hesabdan çıxarılır.','Изменение сразу отправляется на кухню, а позиция удаляется из счёта.'],'Guest changed mind':['Qonaq fikrini dəyişdi','Гость передумал'],'Incorrect item entered':['Yanlış məhsul daxil edilib','Ошибочно введённая позиция'],'Allergy correction':['Allergiya düzəlişi','Исправление из-за аллергии'],'Manager request':['Menecer göstərişi','Запрос менеджера'],'Kitchen issue':['Mətbəx problemi','Проблема кухни'],'Quantity':['Miqdar','Количество'],'Kitchen note':['Mətbəx qeydi','Комментарий кухне'],'The kitchen receives a change ticket immediately.':['Mətbəx dəyişiklik bildirişini dərhal alır.','Кухня сразу получает уведомление об изменении.'],'Cancel':['Ləğv et','Отмена'],'Full':['Tam','Полностью'],'Outstanding':['Qalıq məbləğ','Остаток'],'You can repeat partial payments until the outstanding balance reaches zero.':['Qalıq məbləğ sıfır olana qədər qismən ödənişləri təkrarlaya bilərsiniz.','Частичные платежи можно повторять, пока остаток не станет равен нулю.'],'No order changes.':['Sifariş dəyişikliyi yoxdur.','Изменений заказов нет.'],'The kitchen is synchronized with the floor.':['Mətbəx zalla sinxronlaşdırılıb.','Кухня синхронизирована с залом.'],'REMOVE':['SİL','УДАЛИТЬ'],'CHANGE':['DƏYİŞ','ИЗМЕНИТЬ'],'menu item':['yemək','блюдо'],'e.g. sold out, delivery issue':['məs. tükənib, təchizat problemi','например: закончилось, проблема с поставкой'],'hot':['isti mətbəx','горячий цех'],'cold':['soyuq mətbəx','холодный цех'],'grill':['qril','гриль'],'pastry':['şirniyyat','кондитерский цех'],'bar':['bar','бар'],'Main':['Əsas zal','Основной зал'],'Terrace':['Terras','Терраса'],'Private':['Özəl','Приватный зал'],'round':['dairəvi','круглый'],'square':['kvadrat','квадратный'],'banquette':['banket','банкетка'],'Tell us what happened':['Nə baş verdiyini yazın','Расскажите, что произошло'],'Send to manager':['Menecerə göndər','Отправить менеджеру'],'Waiter requested a manager for the guest':['Ofisiant qonaq üçün menecer çağırdı','Официант вызвал менеджера для гостя'],'Guest requested a manager':['Qonaq menecer çağırdı','Гость попросил менеджера'],'Kitchen has been updated with the change.':['Dəyişiklik mətbəxə göndərildi.','Изменение отправлено на кухню.'],'A manager has been notified.':['Menecerə məlumat verildi.','Менеджер уведомлён.'],'A manager has been paged.':['Menecer çağırıldı.','Менеджер вызван.'],'Your complaint has been sent to the manager on duty.':['Şikayət növbətçi menecerə göndərildi.','Жалоба отправлена дежурному менеджеру.'],'Complaint filed for management.':['Şikayət rəhbərlik üçün qeydə alındı.','Жалоба зарегистрирована для руководства.'],'Main-course preparation times vary significantly.':['Əsas yeməklərin hazırlanma vaxtları xeyli fərqlənir.','Время приготовления основных блюд заметно различается.'],'SUFRA generated a firing sequence so the course can land together.':['SUFRA yeməklərin eyni vaxtda hazır olması üçün hazırlanma ardıcıllığı yaratdı.','SUFRA рассчитала порядок запуска, чтобы блюда были готовы одновременно.'],'No-dairy request conflicts with mashed potato.':['Süd məhsulsuz istək kartof püresi ilə uyğun gəlmir.','Запрос без молочного конфликтует с картофельным пюре.'],'Mashed potato may contain butter or cream. Choose another side or confirm a dairy-free preparation.':['Kartof püresində kərə yağı və ya qaymaq ola bilər. Başqa qarnir seçin və ya süd məhsulsuz hazırlanmanı təsdiqləyin.','Картофельное пюре может содержать масло или сливки. Выберите другой гарнир или подтвердите приготовление без молочных продуктов.'],'Choose a cooking temperature before the grill fires it.':['Qrilə göndərməzdən əvvəl bişmə dərəcəsini seçin.','Перед отправкой на гриль выберите степень прожарки.'],'Confirm whether someone is sharing, skipping a main, or still deciding.':['Kiminsə yeməyi paylaşdığını, əsas yemək götürmədiyini və ya hələ seçim etdiyini təsdiqləyin.','Уточните, кто-то делит блюдо, пропускает основное или ещё выбирает.'],'Check for accidental duplicate mains.':['Təsadüfi təkrarlanan əsas yeməkləri yoxlayın.','Проверьте, нет ли случайно продублированных основных блюд.'],'It has been taken off sale by the kitchen.':['Mətbəx onu satışdan çıxarıb.','Кухня сняла позицию с продажи.'],'Manage active dishes':['Aktiv yeməkləri idarə et','Управление активными блюдами'],'Remove this dish from active menus?':['Bu yemək aktiv menyulardan çıxarılsın?','Убрать это блюдо из активного меню?']};
 /* SUFRA I18N EXPANSION 20260901 */
 Object.assign(D,{
  'Sixteen screens: command centre, live operations, floor, reservations, orders, kitchen, menu, inventory, suppliers, guests, staff, events, analytics, finance, AI copilot and settings.':['On altı ekran: idarəetmə mərkəzi, canlı əməliyyatlar, zal, rezervasiyalar, sifarişlər, mətbəx, menyu, ehtiyatlar, təchizatçılar, qonaqlar, heyət, tədbirlər, analitika, maliyyə, AI köməkçi və ayarlar.','Шестнадцать экранов: центр управления, текущие операции, зал, бронирования, заказы, кухня, меню, запасы, поставщики, гости, персонал, события, аналитика, финансы, AI-помощник и настройки.'],
  'Waiters, bartenders, runners':['Ofisiantlar, barmenlər, çatdıranlar','Официанты, бармены, раннеры'],
  'A queue sorted by what breaks first. Take and change orders, mark dishes served, move a party, split a bill, take payment, page a manager. Built for a tablet held in one hand.':['Ən təcili işlərə görə sıralanmış növbə. Sifarişləri qəbul edin və dəyişin, yeməkləri servis edilmiş kimi qeyd edin, qonaqları köçürün, hesabı bölün, ödəniş alın və meneceri çağırın. Bir əllə tutulan planşet üçün hazırlanıb.','Очередь отсортирована по срочности. Принимайте и меняйте заказы, отмечайте подачу блюд, пересаживайте гостей, делите счёт, принимайте оплату и вызывайте менеджера. Интерфейс рассчитан на планшет в одной руке.'],
  'Scan, browse the menu with photos, filter allergies, save dishes and call for water, cutlery, a waiter or the bill. Orders are confirmed by staff. Nothing to install.':['Skan edin, menyuya fotolarla baxın, allergenlər üzrə filtrləyin, yeməkləri yadda saxlayın və su, çəngəl-bıçaq, ofisiant və ya hesab istəyin. Sifarişlər heyət tərəfindən təsdiqlənir. Heç nə quraşdırmaq lazım deyil.','Сканируйте, просматривайте меню с фотографиями, фильтруйте по аллергенам, сохраняйте блюда и вызывайте воду, приборы, официанта или счёт. Заказы подтверждает персонал. Ничего устанавливать не нужно.'],
  "Open the guest app and the waiter app side by side. Ask for water on the phone and watch it arrive in the waiter's queue.":["Qonaq və ofisiant tətbiqlərini yan-yana açın. Telefonda su istəyin və sorğunun ofisiant növbəsinə çatmasını izləyin.","Откройте приложения гостя и официанта рядом. Попросите воду с телефона и увидите, как запрос появится в очереди официанта."],
  'Service is simulated so every screen has something to react to.':['Hər ekranın reaksiya verə bilməsi üçün xidmət simulyasiya olunur.','Сервис моделируется, чтобы каждый экран мог реагировать на события.'],
  'Revenue today':['Bugünkü gəlir','Выручка сегодня'],'Guests':['Qonaqlar','Гости'],'Per guest':['Qonaq başına','На одного гостя'],'Occupancy':['Doluluq','Заполняемость'],'Time to bill':['Hesaba qədər vaxt','Время до счёта'],'Satisfaction':['Məmnunluq','Удовлетворённость'],
  'What needs a decision':['Nə qərar tələb edir','Что требует решения'],'Tonight forecast':['Bu axşamın proqnozu','Прогноз на вечер'],'Revenue through the day':['Gün ərzində gəlir','Выручка в течение дня'],'Kitchen load':['Mətbəx yükü','Загрузка кухни'],'Model explains 89% of past variation':['Model keçmiş dəyişkənliyin 89%-ni izah edir','Модель объясняет 89% прошлых изменений'],
  'bookings on the book':['rezervasiya siyahısında','в списке бронирований'],'last seven days':['son yeddi gün','последние семь дней'],'Open checks':['Açıq hesablar','Открытые счета'],'oldest open':['ən köhnə açıq hesab','самый старый открытый счёт'],
  'No data yet.':['Hələ məlumat yoxdur.','Пока нет данных.'],'Nothing to show yet.':['Hələ göstəriləcək heç nə yoxdur.','Пока нечего показывать.'],'That didn’t load.':['Bu yüklənmədi.','Не удалось загрузить.'],'That didn’t load.':['Bu yüklənmədi.','Не удалось загрузить.'],
  'Table QR ordering':['Masa QR sifarişi','Заказ по QR-коду стола'],'Every physical table gets a unique QR link. Guests scan, browse and send their order to the same live kitchen workflow.':['Hər fiziki masa unikal QR keçidi alır. Qonaqlar skan edir, menyuya baxır və sifarişi eyni canlı mətbəx prosesinə göndərirlər.','Каждый физический стол получает уникальную QR-ссылку. Гости сканируют её, просматривают меню и отправляют заказ в тот же рабочий процесс кухни.'],
  'Security & sign-in':['Təhlükəsizlik və giriş','Безопасность и вход'],'Change PINs and manage Touch ID / Face ID / passkey enrollment.':['PIN-ləri dəyişin və Touch ID / Face ID / passkey qeydiyyatını idarə edin.','Меняйте PIN-коды и управляйте регистрацией Touch ID / Face ID / passkey.'],
  'The room':['Zal','Зал'],'Drag a table to redraw the floor. Tap one to open it.':['Zalı yenidən qurmaq üçün masanı sürüşdürün. Açmaq üçün masaya toxunun.','Перетащите стол, чтобы изменить план зала. Нажмите на стол, чтобы открыть его.'],
  'Prices, availability, allergens and what each dish is worth.':['Qiymətlər, mövcudluq, allergenlər və hər yeməyin dəyəri.','Цены, доступность, аллергены и ценность каждого блюда.'],
  'Thirty days of trading, and what it says to do next.':['Otuz günlük əməliyyatlar və bundan sonra nə etmək lazım olduğu.','Тридцать дней работы и выводы о следующих шагах.'],
  'Top dishes by thirty-day revenue.':['Otuz günlük gəlirə görə ən yaxşı yeməklər.','Лучшие блюда по выручке за тридцать дней.'],
  'By reason, then by ingredient. Reason tells you the process to fix.':['Əvvəl səbəbə, sonra inqrediyentə görə. Səbəb düzəldilməli prosesi göstərir.','Сначала по причине, затем по ингредиенту. Причина показывает, какой процесс нужно исправить.'],
  'The rota, the wage bill, and whether it matches forecast demand.':['Növbə cədvəli, əməkhaqqı xərci və proqnoz tələbatla uyğunluğu.','График смен, фонд оплаты труда и соответствие прогнозируемому спросу.'],
  'Every bill open in the building, and everything closed today.':['Məkandakı bütün açıq hesablar və bu gün bağlananlar.','Все открытые счета в ресторане и всё закрытое сегодня.'],
  'Book a table, work the waitlist, and see the shape of the day.':['Rezervasiya yaradın, gözləmə siyahısını idarə edin və günün planını görün.','Создавайте бронирования, управляйте листом ожидания и смотрите план дня.'],
  'Reservation schedule':['Rezervasiya cədvəli','Расписание бронирований'],
  'Clear view of time, guest name, party size and remaining capacity.':['Vaxt, qonaq adı, qrup ölçüsü və qalan tutum aydın göstərilir.','Наглядно показаны время, имя гостя, размер компании и свободная вместимость.'],
  'The book':['Rezervasiya siyahısı','Книга бронирований'],
  'Seat, cancel or mark a no-show. Risk is scored per booking.':['Qonağı yerləşdirin, ləğv edin və ya gəlmədiyini qeyd edin. Risk hər rezervasiya üçün hesablanır.','Посадите гостя, отмените бронь или отметьте неявку. Риск рассчитывается для каждой брони.'],
  'Quoted times come from how many suitable tables are actually free.':['Gözləmə vaxtı uyğun boş masaların real sayına əsaslanır.','Ожидание рассчитывается по фактическому числу подходящих свободных столов.'],
  'Bookings':['Rezervasiyalar','Бронирования'], 'Covers':['Qonaq sayı','Гости'], 'Fill':['Doluluq','Заполняемость'], 'Regulars':['Daimi qonaqlar','Постоянные гости'], 'At risk':['Riskli','Под риском'],
  'on the book':['rezervasiya var','в книге'], 'of capacity':['tutumdan','от вместимости'], 'expected':['gözlənilir','ожидается'], 'above 30% no-show':['gəlməmə riski 30%-dən yuxarı','риск неявки выше 30%'], 'waiting now':['hazırda gözləyir','ожидают сейчас'],
  'Guest name':['Qonağın adı','Имя гостя'], 'Party size':['Qrup ölçüsü','Количество гостей'], 'Date and time':['Tarix və vaxt','Дата и время'], 'Where the booking came from':['Rezervasiya mənbəyi','Источник бронирования'], 'Deposit taken':['Depozit','Депозит'], 'Note for the floor':['Zal üçün qeyd','Заметка для зала'], 'Hold the table':['Masanı saxla','Забронировать стол'],
  'Add to the waitlist':['Gözləmə siyahısına əlavə et','Добавить в лист ожидания'], 'Phone':['Telefon','Телефон'], 'Add and quote a time':['Əlavə et və vaxt bildir','Добавить и рассчитать время'],
  'Time':['Vaxt','Время'], 'Bookings':['Rezervasiyalar','Бронирования'], 'Party':['Qrup','Компания'], 'Risk':['Risk','Риск'], 'Seat':['Yerləşdir','Посадить'], 'No-show':['Gəlmədi','Неявка'], 'Nothing booked for this day.':['Bu gün üçün rezervasiya yoxdur.','На этот день бронирований нет.'], 'Take a booking to start the book.':['İlk rezervasiyanı yaradın.','Создайте первое бронирование.'], 'Nobody waiting.':['Gözləyən yoxdur.','Никто не ждёт.'], 'Walk-ins go straight to a table.':['Rezervasiyasız qonaqları birbaşa boş masaya yerləşdirin.','Гостей без брони можно сразу посадить за свободный стол.'],
  'Service command board':['Mətbəx idarəetmə paneli','Панель управления кухней'], 'Order changes and unavailable products in one place.':['Sifariş dəyişiklikləri və mövcud olmayan məhsullar bir ekranda.','Изменения заказов и недоступные продукты на одном экране.'], 'Order changes':['Sifariş dəyişiklikləri','Изменения заказов'], 'Every waiter change remains visible until a chef acknowledges it.':['Ofisiantın hər dəyişikliyi aşpaz təsdiq edənədək görünür.','Каждое изменение официанта видно, пока повар его не подтвердит.'], 'Acknowledge':['Təsdiqlə','Подтвердить'], 'Unavailable':['Mövcud deyil / 86 paneli','Стоп-лист / 86'], 'Block a dish or ingredient once; waiter and guest menus follow automatically.':['Yemək və ya inqrediyenti bir dəfə bloklayın; ofisiant və qonaq menyuları avtomatik yenilənir.','Заблокируйте блюдо или ингредиент один раз — меню официанта и гостя обновятся автоматически.'], 'Mark unavailable':['Mövcud deyil kimi işarələ','Добавить в стоп-лист'], 'Back on':['Geri qaytar','Вернуть'], 'Everything available.':['Hər şey mövcuddur.','Всё доступно.'], 'No dishes or ingredients are currently blocked.':['Hazırda heç bir yemək və ya inqrediyent bloklanmayıb.','Сейчас ни одно блюдо или ингредиент не заблокированы.'], 'Take something off sale':['Satışdan müvəqqəti çıxar','Временно снять с продажи'], 'Guests and waiters update immediately.':['Qonaq və ofisiant ekranları dərhal yenilənir.','Экраны гостей и официантов обновятся сразу.'], 'Dish / ingredient':['Yemək / inqrediyent','Блюдо / ингредиент'], 'Mark unavailable now':['İndi mövcud deyil et','Снять с продажи сейчас'],
  'Photo':['Foto','Фото'], 'Photo from internet':['İnternetdən foto','Фото из интернета'], 'Paste an image URL, or leave blank for an automatic food photo':['Şəkil linkini daxil edin və ya avtomatik yemək fotosu üçün boş saxlayın','Вставьте ссылку на изображение или оставьте пустым для автоматического фото блюда'], 'Upload your own photo':['Öz şəklinizi yükləyin','Загрузить своё фото'], 'Dish name · English':['Yeməyin adı · İngiliscə','Название блюда · Английский'], 'Name · Azerbaijani':['Ad · Azərbaycanca','Название · Азербайджанский'], 'Name · Russian':['Ad · Rusca','Название · Русский'], 'Description · English':['Təsvir · İngiliscə','Описание · Английский'], 'Description · Azerbaijani':['Təsvir · Azərbaycanca','Описание · Азербайджанский'], 'Description · Russian':['Təsvir · Rusca','Описание · Русский'], 'Translate EN → AZ + RU':['EN → AZ + RU tərcümə et','Перевести EN → AZ + RU'], 'Translations filled. Review them before saving.':['Tərcümələr əlavə edildi. Saxlamazdan əvvəl yoxlayın.','Переводы заполнены. Проверьте их перед сохранением.'],
  'Back to menu':['Menyuya qayıt','Вернуться в меню'], 'For allergies or modifications, please confirm directly with your waiter.':['Allergiya və dəyişiklikləri birbaşa ofisiantla təsdiqləyin.','Аллергии и изменения обязательно подтвердите непосредственно с официантом.'], 'Remove from saved':['Yadda saxlanılandan sil','Удалить из сохранённых'], 'Save to my selections':['Seçimlərimə əlavə et','Сохранить в мои варианты'],
  'Tips already added':['Əvvəl əlavə edilmiş çaypulu','Уже добавленные чаевые'], 'Tip on this payment':['Bu ödəniş üçün çaypulu','Чаевые к этому платежу'], 'Full':['Tam','Полностью'], 'Split equally':['Bərabər böl','Разделить поровну'], 'By item':['Məhsullara görə','По позициям'], 'Custom':['Fərdi məbləğ','Своя сумма'], 'Number of shares':['Hissələrin sayı','Количество долей'], 'Amount':['Məbləğ','Сумма'], 'Tip':['Çaypulu','Чаевые'], 'No tip':['Çaypulu yoxdur','Без чаевых'], 'Card':['Kart','Карта'], 'Cash':['Nağd','Наличные'], 'Food / service':['Yemək / xidmət','Еда / обслуживание'], 'Pay now including tip':['Çaypulu ilə birlikdə ödə','Оплатить с чаевыми'], 'Take payment':['Ödənişi qəbul et','Принять оплату'],
  'Change sent item':['Göndərilmiş məhsulu dəyiş','Изменить отправленную позицию'], 'Remove sent item':['Göndərilmiş məhsulu sil','Удалить отправленную позицию'], 'Update kitchen':['Mətbəxi yenilə','Обновить кухню'], 'Remove & notify kitchen':['Sil və mətbəxə bildir','Удалить и уведомить кухню'],
  'Kitchen controls unavailable':['Mətbəx idarəetməsi əlçatan deyil','Управление кухней недоступно'], 'Nothing available to select':['Seçmək üçün heç nə yoxdur','Нет доступных вариантов'],
  'SUFRA does not send guest orders from the phone. Your waiter takes and confirms the order.':['SUFRA qonaq sifarişlərini telefondan mətbəxə göndərmir. Sifarişi ofisiant götürür və təsdiqləyir.','SUFRA не отправляет гостевые заказы с телефона. Заказ принимает и подтверждает официант.']
 });
 Object.assign(window.SUFRA_CORE_TRANSLATIONS,D);
 const ix=az?0:1;
 function tr(s){
   const x=String(s||'').trim(); if(!x)return undefined;
   if(D[x])return D[x][ix];
   const compact=x.replace(/\s+/g,' ');
   if(compact!==x&&D[compact])return D[compact][ix];
   let m;
   if((m=x.match(/^Table (\d+)$/)))return az?`Masa ${m[1]}`:`Стол ${m[1]}`;
   if((m=x.match(/^(\d+) seats$/)))return az?`${m[1]} yer`:`${m[1]} мест`;
   if((m=x.match(/^(\d+) open$/)))return az?`${m[1]} açıq`:`Открыто: ${m[1]}`;
   if((m=x.match(/^(\d+) bookings$/)))return az?`${m[1]} rezervasiya`:`Бронирований: ${m[1]}`;
   if((m=x.match(/^(\d+) guests$/)))return az?`${m[1]} qonaq`:`Гостей: ${m[1]}`;
   if((m=x.match(/^(\d+) total seats$/)))return az?`${m[1]} ümumi yer`:`Всего мест: ${m[1]}`;
   if((m=x.match(/^(\d+) min$/)))return az?`${m[1]} dəq`:`${m[1]} мин`;
   if((m=x.match(/^Fire \+(\d+) min$/)))return az?`${m[1]} dəq sonra göndər`:`Запустить через ${m[1]} мин`;
   if(x==='Fire now')return az?'İndi göndər':'Запустить сейчас';
   if((m=x.match(/^Table (\d+) has a (.+) restriction\.$/)))return az?`Masa ${m[1]} üçün ${m[2]} məhdudiyyəti var.`:`У стола ${m[1]} ограничение: ${m[2]}.`;
   if((m=x.match(/^(.+): temperature missing\.$/)))return az?`${m[1]}: bişmə dərəcəsi seçilməyib.`:`${m[1]}: не указана степень прожарки.`;
   if((m=x.match(/^(\d+) guests but only (\d+) mains ordered\.$/)))return az?`${m[1]} qonaqdır, amma yalnız ${m[2]} əsas yemək sifariş edilib.`:`${m[1]} гостей, но заказано только ${m[2]} основных блюд.`;
   if((m=x.match(/^(\d+) mains for (\d+) guests\.$/)))return az?`${m[2]} qonaq üçün ${m[1]} əsas yemək sifariş edilib.`:`${m[1]} основных блюд на ${m[2]} гостей.`;
   if((m=x.match(/^(.+) may contain (.+)\. Ingredients\/tags: (.+)$/)))return az?`${m[1]} ${m[2]} ehtiva edə bilər. İnqrediyentlər/teqlər: ${m[3]}`:`${m[1]} может содержать ${m[2]}. Ингредиенты/теги: ${m[3]}`;
   if((m=x.match(/^(.+) is unavailable\.$/)))return az?`${m[1]} mövcud deyil.`:`${m[1]} недоступно.`;
   if((m=x.match(/^(.+) is available again\.$/)))return az?`${m[1]} yenidən mövcuddur.`:`${m[1]} снова доступно.`;
   if((m=x.match(/^Table (\d+) assignment updated\.$/)))return az?`Masa ${m[1]} üçün ofisiant təyinatı yeniləndi.`:`Назначение для стола ${m[1]} обновлено.`;
   if((m=x.match(/^Table (\d+) added\.$/)))return az?`Masa ${m[1]} əlavə edildi.`:`Стол ${m[1]} добавлен.`;
   if((m=x.match(/^Table (\d+) removed from the floor\.$/)))return az?`Masa ${m[1]} zaldan çıxarıldı.`:`Стол ${m[1]} убран из зала.`;
   if((m=x.match(/^Table (\d+) restored\.$/)))return az?`Masa ${m[1]} geri qaytarıldı.`:`Стол ${m[1]} восстановлен.`;
   if((m=x.match(/^(.+) section added\.$/)))return az?`${m[1]} bölməsi əlavə edildi.`:`Раздел «${m[1]}» добавлен.`;
   if((m=x.match(/^(.+) added to (.+)\.$/)))return az?`${m[1]} ${m[2]} bölməsinə əlavə edildi.`:`${m[1]} добавлено в раздел ${m[2]}.`;
   if((m=x.match(/^(.+) added to the menu\.$/)))return az?`${m[1]} menyuya əlavə edildi.`:`${m[1]} добавлено в меню.`;
   if((m=x.match(/^(.+) removed from active menus\.$/)))return az?`${m[1]} aktiv menyulardan çıxarıldı.`:`${m[1]} удалено из активного меню.`;
   if((m=x.match(/^(.+) restored\.$/)))return az?`${m[1]} bərpa edildi.`:`${m[1]} восстановлено.`;
   if((m=x.match(/^(.+) removed from the menu\.$/)))return az?`${m[1]} menyudan çıxarıldı.`:`${m[1]} удалено из меню.`;
   if((m=x.match(/^(.+) restored to the menu\.$/)))return az?`${m[1]} menyuya geri qaytarıldı.`:`${m[1]} восстановлено в меню.`;
   if((m=x.match(/^ORDER CHANGE · Table (\d+)$/)))return az?`SİFARİŞ DƏYİŞİKLİYİ · Masa ${m[1]}`:`ИЗМЕНЕНИЕ ЗАКАЗА · Стол ${m[1]}`;
   if((m=x.match(/^Manager requested · Table (\d+)$/)))return az?`Menecer çağırışı · Masa ${m[1]}`:`Вызов менеджера · Стол ${m[1]}`;
   if((m=x.match(/^Guest complaint · Table (\d+)$/)))return az?`Qonaq şikayəti · Masa ${m[1]}`:`Жалоба гостя · Стол ${m[1]}`;
   return undefined;
 }
 function apply(root=document.body){if(!root)return;root.querySelectorAll?.('option:not([value])').forEach(o=>o.value=o.textContent);const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while((n=w.nextNode())){if(!n.parentElement||n.parentElement.closest('script,style,code,pre,textarea,[data-i18n-skip],[translate=no],.nova-lang-global'))continue;const raw=n.nodeValue,x=raw.trim(),y=tr(x);if(y)n.nodeValue=raw.replace(x,y)}root.querySelectorAll?.('[placeholder],[title],[aria-label]').forEach(e=>['placeholder','title','aria-label'].forEach(a=>{const v=e.getAttribute(a),y=tr(v);if(y)e.setAttribute(a,y)}))}
 let timer=0;const mo=new MutationObserver(()=>{clearTimeout(timer);timer=setTimeout(()=>apply(),25)});const start=()=>{apply();mo.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']})};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
 window.addEventListener('nova-language-changed',()=>apply());
 return {apply,get:()=>lang,translate:tr};
})();



window.SUFRAAutoI18N={
  scan(){
    /* Runtime web translation intentionally disabled.
       Static reviewed dictionaries are used instead. */
  }
};
