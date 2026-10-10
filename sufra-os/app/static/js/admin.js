/* The venue's currency symbol, injected by the page from restaurant
   settings (see main._currency). One symbol for the whole product. */
const CUR = (window.SUFRA_CURRENCY || '\u20bc');
/* ============================================================
   NOVA admin app — one module per screen.
   ============================================================ */

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

/* ---- shell: auth gate, notifications, branch switcher ---- */

function showAdminLock(idle) {
  const me = NOVA.auth.getStaff();
  const el = $('#lock-overlay');
  el.hidden = false;
  el.innerHTML = `
    <div class="auth-head">
      <span class="who-face big">${NOVA.esc(me.avatar)}</span>
      <h1>Session locked</h1>
      <p>${NOVA.esc(me.name)}, enter your PIN to continue.</p>
    </div>
    <div id="admin-lock-pin"></div>
    <button class="btn ghost block" id="admin-lock-switch" style="margin-top:18px">Switch user</button>`;
  let entered = '';
  const renderPad = (error) => {
    $('#admin-lock-pin').innerHTML = `
      <div class="pin-dots">${Array.from({ length: 4 }).map((_, i) =>
        `<i class="${i < entered.length ? 'on' : ''}"></i>`).join('')}</div>
      <p class="pin-error">${error ? NOVA.esc(error) : ''}</p>
      <div class="keypad">
        ${[1,2,3,4,5,6,7,8,9].map(n => `<button data-k="${n}">${n}</button>`).join('')}
        <button data-k="clear" class="ghost-key">Clear</button>
        <button data-k="0">0</button>
        <button data-k="back" class="ghost-key">⌫</button>
      </div>`;
    $$('#admin-lock-pin [data-k]').forEach(b => b.onclick = () => {
      const k = b.dataset.k;
      if (k === 'clear') entered = '';
      else if (k === 'back') entered = entered.slice(0, -1);
      else if (entered.length < 4) entered += k;
      renderPad();
      if (entered.length >= 4 && k !== 'back' && k !== 'clear') tryUnlock();
    });
  };
  async function tryUnlock() {
    try { await NOVA.api('/api/auth/verify', { pin: entered }); el.hidden = true; idle.unlock(); }
    catch (e) { entered = ''; renderPad(e.message); }
  }
  renderPad();
  $('#admin-lock-switch').onclick = async () => { await NOVA.auth.logout(); location.reload(); };
}

async function bootAdminShell() {
  const shell=document.querySelector('.shell'),authMount=$('#auth-mount');
  if(!shell||!authMount)throw new Error('Admin shell markup is incomplete.');
  const path=location.pathname.replace(/^\/admin\/?/,'');
  const current=path.split('/')[0]||'';
  const access={
    owner:['','executive','operations','floor','reservations','orders','kitchen','menu','inventory','anbar','guests','staff','hr','analytics','finance','accounting','suppliers','qr','copilot','settings'],
    general_manager:['','executive','operations','floor','reservations','orders','kitchen','menu','inventory','anbar','guests','staff','hr','analytics','finance','accounting','suppliers','qr','copilot'],
    restaurant_manager:['executive','operations','floor','reservations','orders','kitchen','menu','inventory','anbar','guests','staff','hr','analytics','qr'],
    host:['reservations','floor','guests'],inventory_manager:['anbar','inventory','suppliers','menu'],kitchen:['kitchen','menu'],cashier:['orders']
  };
  const roleHome={owner:'/admin',general_manager:'/admin/operations',restaurant_manager:'/admin/operations',host:'/admin/reservations',inventory_manager:'/admin/inventory',kitchen:'/admin/kitchen',cashier:'/admin/orders',waiter:'/waiter?fresh=1',bartender:'/waiter?fresh=1'};
  let verifiedStaff=null,verifiedPerms=[];
  async function signed(){
    const staff=NOVA.auth.getStaff(),token=NOVA.auth.getToken();
    if(staff&&token){
      try{
        const r=await Promise.race([
          NOVA.api('/api/auth/me'),
          new Promise((_,reject)=>setTimeout(()=>reject(new Error('Session check timed out.')),4500))
        ]);
        verifiedStaff=r.staff;verifiedPerms=r.permissions||[];
        NOVA.auth.setSession(token,verifiedStaff,verifiedPerms);
        return true
      }catch(e){
        console.warn('SUFRA session check failed; returning to PIN screen.',e);
        NOVA.auth.clearSession()
      }
    }
    return false
  }
  if(!(await signed())){shell.hidden=true;authMount.hidden=false;await NOVA.auth.staffLogin(authMount,()=>location.reload());return}
  const me=verifiedStaff||NOVA.auth.getStaff();
  window.NOVA_ACTIVE_STAFF=me;
  if(['waiter','bartender'].includes(me.role)){location.replace('/waiter?fresh=1');return}
  const allowed=access[me.role]||[];
  if(!allowed.includes(current)){location.replace(roleHome[me.role]||'/admin');return}
  document.querySelectorAll('.rail nav a[href^="/admin"]').forEach(a=>{const part=a.getAttribute('href').replace('/admin','').replace(/^\//,'');a.hidden=!allowed.includes(part)});
  document.querySelectorAll('.rail .nav-group').forEach(g=>{let n=g.nextElementSibling,any=false;while(n&&!n.classList.contains('nav-group')){if(n.tagName==='A'&&!n.hidden)any=true;n=n.nextElementSibling}g.hidden=!any});
  authMount.hidden=true;shell.hidden=false;$('#signed-in-as').textContent=`${me.name} · ${ROLE_LABEL[me.role]||me.role}`;if(window.NOVAI18N)NOVAI18N.apply();
  $('#switch-user').onclick=async()=>{await NOVA.auth.logout();location.href='/admin?fresh=1'};
  const idle=NOVA.auth.idleLock(8,()=>showAdminLock(idle)),bell=$('#bell'),panel=$('#notifications');
  async function poll(){try{const d=await NOVA.api('/api/admin/notifications'),c=$('#bell-count');c.textContent=d.unread||'';c.classList.toggle('has',d.unread>0);bell.dataset.rows=JSON.stringify(d.notifications)}catch{}}
  bell.onclick=()=>{const rows=JSON.parse(bell.dataset.rows||'[]');panel.innerHTML=`<button class="close">×</button><h2>Notifications</h2><p class="sub">Anything the building wanted you to know.</p>${rows.length?rows.map(n=>`<div class="insight ${n.level} ${n.read?'read':''}" data-id="${n.id}"><i></i><div><b>${NOVA.esc(n.title)}</b><p>${NOVA.esc(n.body)}</p><div class="do">${n.ago} min ago · ${NOVA.esc(n.audience)}</div></div></div>`).join(''):NOVA.empty('Nothing waiting.','Alerts land here as they happen.')}`;panel.classList.add('open');panel.querySelector('.close').onclick=()=>panel.classList.remove('open');panel.querySelectorAll('.insight').forEach(el=>el.onclick=async()=>{el.classList.add('read');await NOVA.api(`/api/admin/notifications/${el.dataset.id}/read`,{});poll()})};
  const ls=$('#loc-switch');if(ls)ls.onclick=async()=>{const d=await NOVA.api('/api/admin/settings');NOVA.modal('Branches',d.locations.map(l=>`<button class="pick ${l.home?'on':''}" data-name="${NOVA.esc(l.name)}"><b>${NOVA.esc(l.name)}</b><span>${NOVA.esc(l.city)} · ${l.seats} seats ${l.home?'· live data':'· forecast only'}</span></button>`).join(''),(body,close)=>body.querySelectorAll('.pick').forEach(b=>b.onclick=()=>{ls.textContent=b.dataset.name+' ▾';NOVA.toast(`Switched to ${b.dataset.name}`);close()}))};
  if(!window.__novaAdminPageBooted){window.__novaAdminPageBooted=true;const pageBoot={'':async()=>{await bootCommand();await bootOpsFeed()},operations:async()=>{await bootOperations();await bootComplaints();await bootOpsFeed()},floor:async()=>{await bootFloor();await bootFloorControl()},reservations:bootReservations,orders:bootOrders,kitchen:async()=>{await bootKitchen();await bootKitchenOps()},menu:async()=>{await bootMenuAdmin();await bootMenuOps()},inventory:bootInventory,anbar:()=>window.bootAnbar(),guests:bootGuests,staff:bootStaff,analytics:bootAnalytics,finance:bootFinance,suppliers:bootSuppliers,copilot:bootCopilot,settings:bootSettings,executive:window.bootEnterpriseExecutive,hr:window.bootEnterpriseHR,accounting:window.bootEnterpriseAccounting,qr:window.bootEnterpriseQR}[current];if(pageBoot)await pageBoot()}
  poll();NOVA.on(poll);setInterval(poll,45000);
}

/* ============================================================
   Command centre
   ============================================================ */

function bootCommand() {
  NOVACommandLang.init();
  /* The foresight track. Pins are packed into lanes so two events that
     happen at similar times sit above each other instead of on top of
     each other — the collision that made the first build unreadable. */
  function foresight(insights, kpis) {
    const track=$('#track'),SPAN=120;
    const pins=insights.filter(i=>i.horizon<=SPAN).sort((a,b)=>a.horizon-b.horizon).slice(0,6);
    const ticks=[0,30,60,90,120].map(m=>{const t=new Date(Date.now()+m*60000);return `<div class="tick" style="left:${m/SPAN*100}%"><i></i><span>${m?t.toTimeString().slice(0,5):'now'}</span></div>`}).join('');
    track.innerHTML=`<div class="foresight-cards">${pins.map((p,i)=>`<article class="pin ${p.severity}" style="animation-delay:${.12+i*.07}s"><small class="pin-time">${p.horizon<=0?'now':Math.max(1,Math.round(p.horizon))+' min'}</small><b>${NOVA.esc(p.title)}</b><span>${NOVA.esc(p.action||p.detail)}</span></article>`).join('')||'<div class="foresight-empty">No urgent actions in the next two hours.</div>'}</div><div class="track-axis"><div class="track-line"></div>${ticks}</div>`;
    $('#foresight-sub').textContent=pins.length?`${NOVA.plural(pins.length,'thing')} worth acting on before ${new Date(Date.now()+SPAN*60000).toTimeString().slice(0,5)}.`:`Nothing needs a decision in the next two hours. ${kpis.tables_busy} of ${kpis.tables_total} tables are in service.`;
    if(window.NOVAI18N)NOVAI18N.apply();
  }

  function strip(k) {
    NOVA.setNumber($('#m-revenue'), k.revenue, NOVA.money);
    NOVA.setNumber($('#m-covers'), k.covers);
    NOVA.setNumber($('#m-spend'), k.spend_per_cover, v => NOVA.money(v));
    NOVA.setNumber($('#m-occ'), k.occupancy, v => Math.round(v) + '%');
    NOVA.setNumber($('#m-dur'), k.avg_duration, v => Math.round(v) + 'm');
    NOVA.setNumber($('#m-sat'), k.satisfaction, v => v.toFixed(0) + '%');
    $('#m-revenue-sub').textContent = `${k.gross_margin}% gross margin`;
    $('#m-occ-sub').textContent = `${k.tables_busy} of ${k.tables_total} tables`;
    $('#m-dur-sub').textContent = k.open_tickets
      ? `${k.open_tickets} tickets open, oldest ${k.oldest_ticket}m` : 'kitchen is clear';
    $('#clock').textContent = k.clock;
    $('#day').textContent = k.day;
  }

  function insightList(items) {
    $('#insights').innerHTML = items.length ? items.map(i => `
      <div class="insight ${i.severity}"><i></i><div>
        <b>${NOVA.esc(i.title)}</b><p>${NOVA.esc(i.detail)}</p>
        ${i.action ? `<div class="do">${NOVA.esc(i.action)}</div>` : ''}
      </div></div>`).join('')
      : NOVA.empty('Service is running clean.', 'Nothing is off pace, over capacity or short.');
  }

  function forecastCard(f) {
    $('#fc-revenue').textContent = NOVA.money(f.revenue);
    $('#fc-band').textContent = `${NOVA.money(f.low)} – ${NOVA.money(f.high)}`;
    $('#fc-covers').textContent = `${f.covers} covers · ${f.booked} booked`;
    $('#fc-drivers').innerHTML = f.drivers.map(d =>
      `<div class="kv"><span>${NOVA.esc(d.name)}</span>
        <b class="${d.effect >= 0 ? 'up' : 'down'}">${d.effect >= 0 ? '+' : ''}${
          NOVA.money(d.effect)}</b></div>`).join('');
    $('#fc-conf').textContent = `Model explains ${Math.round(f.confidence * 100)}% of past variation`;
  }

  function stations(rows) {
    $('#stations').innerHTML = rows.map(r => {
      const pct = Math.min(100, r.load_projected * 100);
      const cls = pct >= 100 ? 'over' : pct >= 80 ? 'hot' : '';
      return `<div style="margin-bottom:14px">
        <div class="station-head" style="padding-bottom:6px">
          <b>${r.station[0].toUpperCase() + r.station.slice(1)}</b>
          <span>${r.now}/${r.capacity} now · ${Math.round(pct)}% in 20m</span></div>
        <div class="load-bar"><i class="${cls}" style="width:${pct}%"></i></div></div>`;
    }).join('');
  }

  async function refresh() {
    const d = await NOVA.api('/api/snapshot');
    const commandInsights = NOVACommandLang.cleanInsights(d.insights);
    strip(d.kpis); foresight(commandInsights, d.kpis); insightList(commandInsights);
    forecastCard(d.forecast); stations(d.stations);
    NOVA.areaChart($('#revchart'), d.revenue_curve.map(p => ({ k: p.hour, v: p.revenue })),
      { label: v => (window.SUFRA_CURRENCY || '\u20bc') + Math.round(v / 100) / 10 + 'k' });
    NOVA.barChart($('#coverschart'),
      d.revenue_curve.map(p => ({ k: p.hour, v: p.covers })), new Date().getHours());
    NOVACommandLang.apply(); if(window.NOVAI18N)NOVAI18N.apply();
  }

  wireCopilot();
  NOVA.load($('#insights'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* Copilot is on two screens, so it lives in one function. */
function wireCopilot() {
  const thread = $('#thread'), form = $('#ask');
  if (!thread || !form) return;
  const say = (who, html) => {
    const el = document.createElement('div');
    el.className = `msg ${who}`; el.innerHTML = html;
    thread.appendChild(el); thread.scrollTop = thread.scrollHeight;
    return el;
  };
  async function ask(q) {
    if (!q.trim()) return;
    say('me', NOVA.esc(q));
    const wait = say('nova', '<span class="typing"><i></i><i></i><i></i></span>');
    try {
      const r = await NOVA.api('/api/copilot', { question: q });
      wait.innerHTML = `${NOVA.esc(r.answer)}
        ${r.why ? `<div class="why">${NOVA.esc(r.why)}</div>` : ''}
        ${r.source ? `<div class="src">computed from ${NOVA.esc(r.source)}</div>` : ''}`;
    } catch (e) {
      wait.innerHTML = NOVA.esc(e.message);
      wait.classList.add('bad');
    }
    thread.scrollTop = thread.scrollHeight;
  }
  form.onsubmit = e => {
    e.preventDefault();
    const i = e.target.querySelector('input');
    ask(i.value); i.value = '';
  };
  $$('.seeds button').forEach(b => b.onclick = () => ask(b.textContent));
}

function bootCopilot() { wireCopilot(); }


/* ============================================================
   Live operations stream — the one real activity feed
   ============================================================
   Every row here was written by something that actually happened: a booking
   taken in SUFRA 360, a waiter seating a party, a manager moving a table, the
   scheduler marking a no-show. Nothing is generated to make the screen look
   busy — a quiet restaurant shows an empty state and says so. */

const OPS_ICON = {
  reservation_created: '✦', reservation_updated: '✎', reservation_cancelled: '✕',
  reservation_moved: '⇄', reservation_completed: '✓', guest_seated: '◍',
  guest_late: '◷', guest_no_show: '⊘', guest_confirmed: '✓',
  table_status: '▦', table_held: '⏱', hold_released: '⏱',
  waitlist_added: '⋯', waitlist_updated: '⋯', waitlist_converted: '✦',
  menu_updated: '☰', menu_availability: '⊘',
  reminder_sent: '✉', confirmation_sent: '✉',
};

function opsTitle(e) {
  const lang = (window.NOVAI18N && NOVAI18N.get && NOVAI18N.get()) || 'en';
  if (lang === 'az' && e.title_az) return e.title_az;
  if (lang === 'ru' && e.title_ru) return e.title_ru;
  return e.title;
}

async function bootOpsFeed() {
  const mount = document.querySelector('#ops-feed');
  if (!mount) return;
  let lastId = 0;
  async function refresh() {
    let d;
    try { d = await NOVA.api('/api/admin/activity?limit=40'); }
    catch (e) { mount.innerHTML = `<p class="sub">${NOVA.esc(e.message)}</p>`; return; }
    const rows = (d.events || []).slice().reverse();
    lastId = rows.length ? rows[0].id : lastId;
    mount.innerHTML = rows.length ? `<div class="ops-stream">${rows.map(e => `
      <div class="ops-event ${NOVA.esc(e.severity)}">
        <span class="ops-icon">${OPS_ICON[e.kind] || '•'}</span>
        <div><b>${NOVA.esc(opsTitle(e))}</b>
          ${e.detail ? `<span>${NOVA.esc(e.detail)}</span>` : ''}</div>
        <time>${NOVA.esc(e.time)}<em>${NOVA.esc(e.actor || '')}</em></time>
      </div>`).join('')}</div>`
      : NOVA.empty('Nothing has happened yet.',
                   'Bookings, seating, table changes and menu edits appear here the moment they occur.');
    if (window.NOVAI18N) NOVAI18N.apply();
  }
  await refresh();
  NOVA.on(() => refresh().catch(() => {}));
  setInterval(() => refresh().catch(() => {}), 20000);
}

/* ============================================================
   Live operations
   ============================================================ */

function bootOperations() {
  async function refresh() {
    const [snap, pass] = await Promise.all([
      NOVA.api('/api/snapshot'), NOVA.api('/api/pass')]);
    const k = snap.kpis;
    $('#ops-strip').innerHTML = [
      ['In service', `${k.tables_busy}/${k.tables_total}`, `${k.occupancy}% full`],
      ['Open tickets', k.open_tickets, `oldest ${k.oldest_ticket}m`],
      ['Open requests', pass.tasks.length, 'guest-initiated'],
      ['Revenue', NOVA.money(k.revenue), `${k.gross_margin}% margin`],
      ['Covers', k.covers, 'mains served'],
      ['Satisfaction', k.satisfaction + '%', 'last seven days'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#ops-alerts').innerHTML = snap.insights.length ? snap.insights.map(i => `
      <div class="insight ${i.severity}"><i></i><div>
        <b>${NOVA.esc(i.title)}</b><p>${NOVA.esc(i.detail)}</p>
        ${i.action ? `<div class="do">${NOVA.esc(i.action)}</div>` : ''}
      </div></div>`).join('')
      : NOVA.empty('All quiet.', 'No alert is currently open.');

    const atPass = pass.tables.filter(t => t.status === 'ready');
    $('#ops-pass').innerHTML = atPass.length ? atPass.map(t =>
      `<div class="kv"><span>Table ${t.number} · ${NOVA.esc(t.waiter)}</span>
        <b class="down">${t.minutes}m under the lamp</b></div>`).join('')
      : NOVA.empty('Nothing waiting.', 'Every plate has been carried.');

    $('#ops-tasks').innerHTML = pass.tasks.length ? pass.tasks.slice(0, 10).map(t =>
      `<div class="kv ops-task"><span>Table ${t.table} · ${NOVA.esc(TASK_LABEL[t.kind] || t.kind)}</span>
        <span class="task-actions"><b class="${t.minutes > 5 ? 'down' : ''}">${t.minutes}m</b>
        <button class="btn tiny solid" data-ops-done="${t.id}">✓ Done</button></span></div>`).join('')
      : NOVA.empty('Nothing open.', 'Every request has been closed.');
    $$('#ops-tasks [data-ops-done]').forEach(b => b.onclick = async () => {
      b.disabled = true;
      try { await NOVA.api(`/api/tasks/${b.dataset.opsDone}/done`, {}); await refresh(); }
      catch (e) { b.disabled = false; NOVA.fail(e); }
    });
  }
  NOVA.load($('#ops-alerts'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* ============================================================
   Floor
   ============================================================ */

function bootFloor() {
  const room = $('#room'), inspector = $('#inspector');
  let tables = [], selected = null, dragging = null;

  function draw(rows) {
    const before = Object.fromEntries(tables.map(t => [t.id, t.status]));
    tables = rows;
    rows.forEach(t => {
      let el = room.querySelector(`.tbl[data-id="${t.id}"]`);
      if (!el) {
        el = document.createElement('div');
        el.className = `tbl ${t.shape}`; el.dataset.id = t.id; el.tabIndex = 0;
        el.addEventListener('pointerdown', startDrag);
        room.appendChild(el);
      }
      el.style.left = t.x * 100 + '%'; el.style.top = t.y * 100 + '%';
      el.dataset.status = t.status;
      el.classList.toggle('alarm', t.alert);
      el.classList.toggle('has-request', (t.tasks || []).length > 0);
      el.classList.toggle('new-request', (t.tasks || []).some(k => k.minutes <= 1));
      if (before[t.id] && before[t.id] !== t.status) {
        el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
      }
      const r=t.reservation;
      el.classList.toggle('reserved-soon', !!(r && !r.active));
      el.innerHTML = `${t.guest && t.guest.vip ? '<div class="vip">V</div>' : ''}
        <b>${t.number}</b><span>${t.party ? t.party + '/' + t.seats : t.seats}</span>
        ${r?`<div class="reservation-label"><strong>${NOVA.esc(r.guest)}</strong><small>${r.time} · ${r.party}p${r.active?' · seated':' · reserved'}</small></div>`:''}
        <div class="timer">${t.status === 'available' ? '' :
          t.minutes + 'm · ' + STATUS_LABEL[t.status]}</div>`;
      if (selected === t.id) openInspector(t);
    });
    const busy = rows.filter(r => r.status !== 'available').length;
    $('#floor-count').textContent = `${busy}/${rows.length} in service`;
    const late = rows.filter(r => r.alert).length;
    $('#floor-alert').textContent = late
      ? `${late} past their service window` : 'every table inside its window';
  }

  function startDrag(e) {
    dragging = { el: e.currentTarget, id: +e.currentTarget.dataset.id,
                 moved: false, rect: room.getBoundingClientRect() };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  room.addEventListener('pointermove', e => {
    if (!dragging) return;
    dragging.moved = true;
    const x = (e.clientX - dragging.rect.left) / dragging.rect.width;
    const y = (e.clientY - dragging.rect.top) / dragging.rect.height;
    dragging.el.style.left = Math.max(3, Math.min(97, x * 100)) + '%';
    dragging.el.style.top = Math.max(4, Math.min(96, y * 100)) + '%';
  });
  room.addEventListener('pointerup', async () => {
    if (!dragging) return;
    const { el, id, moved } = dragging; dragging = null;
    if (moved) {
      try {
        await NOVA.api(`/api/tables/${id}/move`,
          { x: parseFloat(el.style.left) / 100, y: parseFloat(el.style.top) / 100 });
        NOVA.toast('Floor plan saved');
      } catch (e) { NOVA.fail(e); }
    } else {
      selected = id;
      openInspector(tables.find(t => t.id === id));
    }
  });

  /* Allergies, on the table, for whoever is standing at it.
     A guest often mentions one at the door rather than at booking, and until
     now only the waiter's tablet could write that down. The same note the
     waiter would make is written here, and the order inspector reads it the
     moment the kitchen is asked for anything. */
  async function paintAllergies(t) {
    const box = document.querySelector('#insp-allergy');
    if (!box) return;
    let d;
    try { d = await NOVA.api(`/api/waiter/table/${t.id}/allergens`); }
    catch (e) { box.innerHTML = `<p class="sub">${NOVA.esc(e.message)}</p>`; return; }
    if (!document.querySelector('#insp-allergy')) return;
    const src = { 'table note': 'noted on the table', 'booking': 'on the booking',
                  'booking note': 'in the booking notes', 'guest profile': 'on the guest profile' };
    /* One line per allergen, not one per place we found it. The same "sesame"
       arriving from the booking, the guest's profile and the note a waiter
       copied onto the table is one fact about one guest, and listing it three
       times buries the second allergen underneath it. */
    const byAllergen = {};
    d.entries.forEach(e => e.allergens.forEach(a => {
      const row = byAllergen[a] || (byAllergen[a] = { sources: [], who: '', unread: false, said: e.term });
      row.sources.push(src[e.source] || e.source);
      // "From the booking" is the author of the copied note, not a person;
      // name the guest whenever one of the sources knows them.
      if (!row.who || row.who === 'From the booking') row.who = e.who;
      if (!e.acknowledged) row.unread = true;
      if (e.term.length < row.said.length) row.said = e.term;
    }));
    const rows = Object.entries(byAllergen).map(([a, r]) => `
      <div class="kv"><span><b class="down">${NOVA.esc(a)}</b>
        <div class="micro">${NOVA.esc(r.who)} · ${NOVA.esc([...new Set(r.sources)].join(' · '))}${
          r.unread ? ' · <b class="down">not yet read by the floor</b>' : ''}</div></span></div>`);
    box.innerHTML = (rows.length || d.unrecognised.length) ? rows.join('') +
      (d.unrecognised.length ? `<div class="kv"><span><b class="warn">${
        NOVA.esc(d.unrecognised.join(', '))}</b>
        <div class="micro">SUFRA cannot screen the menu for this — confirm it by hand.</div></span></div>` : '')
      : '<p class="sub">Nothing declared for this table.</p>';
    const add = document.querySelector('#insp-add-allergy');
    if (add) add.onclick = () => NOVA.modal(`Record an allergy · Table ${t.number}`, `
      <p class="sub">Written onto the table exactly as a waiter would write it. The order
         inspector screens every dish against it, and the floor must read it before the
         next ticket can be sent.</p>
      <label class="lbl">What did the guest tell you?<input class="field" id="al-msg"
        placeholder="for example: nuts, or severe shellfish allergy on seat 2"></label>
      <button class="btn solid block" id="al-save">Record it</button>
      <p class="form-error" id="al-error"></p>`, (body, close) => {
        body.querySelector('#al-save').onclick = async () => {
          const msg = body.querySelector('#al-msg').value.trim();
          if (!msg) { body.querySelector('#al-error').textContent = 'Write what the guest said.'; return; }
          try {
            await NOVA.api(`/api/waiter/table/${t.id}/notes`, { kind: 'allergy', message: msg });
            close(); NOVA.toast('Allergy recorded on table ' + t.number); paintAllergies(t);
          } catch (e) { body.querySelector('#al-error').textContent = e.message; }
        };
      });
  }

  function openInspector(t) {
    if (!t) return;
    const g = t.guest;
    inspector.innerHTML = `<button class="close">×</button>
      <h2>Table ${t.number}</h2>
      <p class="sub">${NOVA.esc(t.zone)} · seats ${t.seats} · ${NOVA.esc(t.waiter)} is on it</p>
      <div class="kv"><span>State</span><b>${STATUS_LABEL[t.status]}</b></div>
      <div class="kv"><span>In this state</span><b>${t.minutes} min</b></div>
      ${t.seated_minutes ? `<div class="kv"><span>Seated for</span><b>${t.seated_minutes} min</b></div>` : ''}
      ${t.spend ? `<div class="kv"><span>On the bill</span><b>${NOVA.money2(t.spend)}</b></div>` : ''}
      ${g ? `<h3>${NOVA.esc(g.name)}${g.vip ? ' · regular' : ''}</h3>
        <div class="kv"><span>Visits</span><b>${g.visits}</b></div>
        ${g.allergies ? `<div class="kv"><span>Allergy</span><b class="down">${NOVA.esc(g.allergies)}</b></div>` : ''}
        ${g.likes ? `<div class="kv"><span>Usually orders</span><b>${NOVA.esc(g.likes)}</b></div>` : ''}
        ${g.pref ? `<div class="kv"><span>Prefers</span><b>${NOVA.esc(g.pref)}</b></div>` : ''}
        ${g.note ? `<p class="sub" style="margin-top:12px">${NOVA.esc(g.note)}</p>` : ''}`
      : '<p class="sub" style="margin-top:20px">Walk-in, no profile attached.</p>'}
      ${t.tasks.length ? `<h3>Open requests</h3>${t.tasks.map(k => `
        <div class="task p${k.priority}" style="margin-bottom:8px">
          <div class="what"><b>${NOVA.esc(k.message)}</b><span>${k.minutes} min ago</span></div>
          <button class="btn" data-done="${k.id}">Done</button></div>`).join('')}` : ''}
      <h3>Allergies</h3>
      <div id="insp-allergy"><p class="sub">Checking…</p></div>
      <div class="btn-row"><button class="btn" id="insp-add-allergy">Record an allergy</button></div>
      <h3>Move this table to</h3>
      <div class="btn-row">${['seated', 'ordering', 'dining', 'bill', 'cleaning', 'available']
        .map(s => `<button class="btn ${s === t.status ? 'solid' : ''}" data-set="${s}">${
          STATUS_LABEL[s]}</button>`).join('')}</div>`;
    paintAllergies(t);
    inspector.classList.add('open');
    inspector.querySelector('.close').onclick = () => {
      inspector.classList.remove('open'); selected = null;
    };
    inspector.querySelectorAll('[data-set]').forEach(b => b.onclick = async () => {
      try {
        await NOVA.api(`/api/tables/${t.id}/status`, { status: b.dataset.set });
        NOVA.toast(`Table ${t.number} → ${STATUS_LABEL[b.dataset.set].toLowerCase()}`);
      } catch (e) { NOVA.fail(e); }
    });
    inspector.querySelectorAll('[data-done]').forEach(b => b.onclick = async () => {
      try { await NOVA.api(`/api/tasks/${b.dataset.done}/done`, {}); NOVA.toast('Marked done'); }
      catch (e) { NOVA.fail(e); }
    });
  }

  const refresh = async () => draw((await NOVA.api('/api/floor')).tables);
  refresh().catch(NOVA.fail);
  NOVA.on(() => refresh().catch(() => {}));
  setInterval(() => refresh().catch(() => {}), 20000);

  NOVA.api('/api/reservations').then(d => {
    const rows = d.reservations.slice(0, 7);
    $('#book').innerHTML = rows.length ? rows.map(r => `
      <div class="kv"><span>${r.time} · ${NOVA.esc(r.guest)}${r.vip ? ' · regular' : ''}</span>
        <b class="${r.risk > .3 ? 'warn' : ''}">${r.party}p · ${Math.round(r.risk * 100)}% risk</b>
      </div>`).join('') : NOVA.empty('Nothing on the book.', 'For the next few hours.');
    const soon = rows.filter(r => r.party >= 4)[0];
    $('#seating').innerHTML = soon
      ? `<p class="sub">Hold a four-top: <b>${NOVA.esc(soon.guest)}</b> arrives at
         <b>${soon.time}</b> for ${soon.party}. Seat the next pair on the bar instead.</p>`
      : NOVA.empty('No large bookings close enough to plan around.');
  }).catch(() => {});
}

/* ============================================================
   Kitchen
   ============================================================ */

function bootKitchen() {
  const ORDER = ['grill', 'hot', 'cold', 'pastry', 'bar'];
  let data = { rail: {}, stations: [] };

  function card(t) {
    const allergens = (t.allergens || '').split(',').filter(a =>
      ['nuts', 'shellfish', 'gluten', 'dairy', 'sesame', 'fish', 'egg'].includes(a));
    const pressureCls = t.state === 'ready' ? ''
      : t.pressure >= 1 ? 'critical' : t.pressure >= .75 ? 'late' : '';
    const cls = `status-${t.state} ${pressureCls}`.trim();
    return `<div class="ticket ${cls}" data-id="${t.id}" data-fired="${t.elapsed}"
        data-promised="${t.promised}" style="--fill:${Math.min(100, t.pressure * 100)}%">
      <div class="row"><span class="tno">T${t.table}</span>
        <span class="clock num" data-clock>${t.elapsed.toFixed(0)}′ / ${t.promised}′</span></div>
      <p class="dish">${t.qty > 1 ? t.qty + ' × ' : ''}${NOVA.esc(t.dish)}</p>
      ${allergens.length ? `<div class="warn">contains ${allergens.join(', ')}</div>` : ''}
      ${t.note ? `<div class="warn">${NOVA.esc(t.note)}</div>` : ''}
      <div class="state-row">
        <span class="state-badge">${t.state === 'queued' ? 'Waiting'
          : t.state === 'cooking' ? 'Cooking' : 'Ready to serve'}</span>
        <span class="state-next">${t.state === 'queued' ? 'Tap to start cooking'
          : t.state === 'cooking' ? 'Tap when ready' : 'Tap when served'}</span>
      </div></div>`;
  }

  function render() {
    const load = Object.fromEntries(data.stations.map(s => [s.station, s]));
    $('#rails').innerHTML = ORDER.map(st => {
      const tickets = data.rail[st] || [];
      const l = load[st] || { capacity: 1, load_projected: 0 };
      const pct = Math.min(100, l.load_projected * 100);
      return `<div class="station-col">
        <div class="station-head"><b>${st[0].toUpperCase() + st.slice(1)}</b>
          <span>${tickets.length} on</span></div>
        <div class="load-bar"><i class="${pct >= 100 ? 'over' : pct >= 80 ? 'hot' : ''}"
          style="width:${pct}%"></i></div>
        <div class="col-body">${tickets.length ? tickets.map(card).join('')
          : '<div class="empty small">Clear.</div>'}</div></div>`;
    }).join('');

    $$('.ticket').forEach(el => {
      el.onclick = async () => {
        if (el.dataset.busy === '1') return;
        el.dataset.busy = '1';
        el.classList.add('advancing');

        try {
          await NOVA.api(`/api/items/${el.dataset.id}/advance`, {});
          await refresh();
        } catch (e) {
          el.dataset.busy = '';
          el.classList.remove('advancing');
          NOVA.fail(e);
        }
      };
      const promised = +el.dataset.promised || 1;
      let mins = parseFloat(el.dataset.fired) || 0;
      const clock = el.querySelector('[data-clock]');
      clearInterval(el._t);
      el._t = setInterval(() => {
        mins += 1 / 60;
        const p = mins / promised;
        el.style.setProperty('--fill', Math.min(100, p * 100) + '%');
        if (clock) clock.textContent = `${mins.toFixed(0)}′ / ${promised}′`;
        el.classList.toggle('late', p >= .75 && p < 1 && !el.classList.contains('ready'));
        el.classList.toggle('critical', p >= 1 && !el.classList.contains('ready'));
      }, 1000);
    });
  }

  async function refresh() {
    data = await NOVA.api('/api/kitchen');
    $('#k-open').textContent = data.kpis.open_tickets;
    $('#k-oldest').textContent = data.kpis.oldest_ticket + 'm';
    render();
  }
  NOVA.load($('#rails'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* ============================================================
   Reservations
   ============================================================ */

function bootReservations() {
  let day = new Date().toISOString().slice(0, 10);

  function bookingForm(prefill = {}) {
    const now = new Date(); now.setMinutes(0, 0, 0); now.setHours(19);
    return `
      <label class="lbl">Guest name<input class="field" id="b-name" value="${NOVA.esc(prefill.name || '')}"></label>
      <div class="row2">
        <label class="lbl">Party size<input class="field" id="b-party" type="number" min="1" max="20" value="${prefill.party || 2}"></label>
        <label class="lbl">Date and time<input class="field" id="b-at" type="datetime-local"
          value="${(prefill.at || now.toISOString().slice(0, 16))}"></label>
      </div>
      <div class="row2">
        <label class="lbl">Where the booking came from<select class="field" id="b-source">
          ${['website', 'phone', 'walk-in', 'instagram', 'concierge'].map(x =>
            `<option>${x}</option>`).join('')}</select></label>
        <label class="lbl">Occasion<select class="field" id="b-occasion">
          <option value="">None</option>${['Birthday', 'Anniversary', 'Business', 'Date'].map(x =>
            `<option>${x}</option>`).join('')}</select></label>
      </div>
      <div class="row2">
        <label class="lbl">Allergies<input class="field" id="b-allergies" placeholder="nuts, shellfish"></label>
        <label class="lbl">Deposit taken<input class="field" id="b-deposit" type="number" min="0" step="5" value="0"></label>
      </div>
      <div class="row2">
        <label class="lbl">Seating preference<select class="field" id="b-pref">
          <option value="">Best available</option><option>Quiet place</option><option>Near a window</option><option>Terrace</option><option>Bar area</option><option>Private dining</option>
        </select></label>
        <label class="lbl">Expected dining time<select class="field" id="b-duration">
          <option value="90">1 h 30</option><option value="105" selected>1 h 45</option><option value="120">2 hours</option><option value="135">2 h 15</option>
        </select></label>
      </div>
      <div class="smart-seat-note">SUFRA chooses the smallest safe table that matches the guest preference and protects the next booking.</div>
      <label class="lbl">Note for the floor<textarea class="field" id="b-note" rows="2"
        placeholder="Quiet table. Cake at 21:30."></textarea></label>
      <button class="btn solid block" id="b-save">Hold the table</button>
      <p class="form-error" id="b-error"></p>`;
  }

  function openBooking() {
    NOVA.modal('Take a booking', bookingForm(), (body, close) => {
      body.querySelector('#b-save').onclick = async () => {
        const err = body.querySelector('#b-error');
        err.textContent = '';
        try {
          const r = await NOVA.api('/api/admin/reservations', {
            name: body.querySelector('#b-name').value,
            party: body.querySelector('#b-party').value,
            at: body.querySelector('#b-at').value,
            source: body.querySelector('#b-source').value,
            occasion: body.querySelector('#b-occasion').value,
            allergies: body.querySelector('#b-allergies').value,
            deposit: body.querySelector('#b-deposit').value,
            pref: body.querySelector('#b-pref')?.value || '',
            duration: body.querySelector('#b-duration')?.value || 105,
            note: body.querySelector('#b-note').value,
          });
          close();
          NOVA.toast(r.message + (r.table ? ` · table ${r.table}` : ''));
          refresh();
        } catch (e) { err.textContent = e.message; }
      };
    });
  }

  function openWaitlist() {
    NOVA.modal('Add to the waitlist', `
      <label class="lbl">Name<input class="field" id="w-name"></label>
      <div class="row2">
        <label class="lbl">Party size<input class="field" id="w-party" type="number" min="1" value="2"></label>
        <label class="lbl">Phone<input class="field" id="w-phone" placeholder="+44 7…"></label>
      </div>
      <button class="btn solid block" id="w-save">Add and quote a time</button>
      <p class="form-error" id="w-error"></p>`, (body, close) => {
      body.querySelector('#w-save').onclick = async () => {
        try {
          const r = await NOVA.api('/api/admin/waitlist', {
            name: body.querySelector('#w-name').value || 'Walk-in',
            party: body.querySelector('#w-party').value,
            phone: body.querySelector('#w-phone').value,
          });
          close();
          NOVA.toast(`Added. Quoted ${r.quoted} minutes.`);
          refresh();
        } catch (e) { body.querySelector('#w-error').textContent = e.message; }
      };
    });
  }

  /* The manager's booking. Everything the guest gave us, everything the floor
     needs, and every action that moves the booking through its life — all
     against the same reservation row SUFRA 360 wrote. */
  async function openReservationDetail(r) {
    let options = null;
    try { options = await NOVA.api(`/api/admin/reservations/${r.id}/options`); } catch (e) {}
    const fresh = (options && options.reservation) || r;
    const risk = Math.round(Number(r.risk || 0) * 100);
    const status = String(fresh.status || 'confirmed').replaceAll('_', ' ');
    const choices = (options && options.choices) || [];
    const lateFlag = fresh.minutes_late > 0 && ['confirmed', 'late'].includes(fresh.status)
      ? `<span class="res-late-flag">${fresh.minutes_late} min late</span>` : '';
    const val = (x) => NOVA.esc(x == null ? '' : x);

    NOVA.modal(`${NOVA.esc(fresh.guest_name || r.guest)} · ${NOVA.esc(fresh.code || '')}`, `
      <div class="res-detail-hero">
        <div><small>${val(fresh.time)}${r.ends ? ` → ${NOVA.esc(r.ends)}` : ''} · ${val(fresh.date)}</small>
          <h2>${val(fresh.guest_name || r.guest)}${lateFlag}</h2>
          <p>${fresh.party_size} guests · ${NOVA.esc(status)} · from ${NOVA.esc(fresh.source || 'phone')}</p></div>
        <div class="res-detail-table"><span>Assigned table</span>
          <b>${fresh.table_number ? 'Table ' + fresh.table_number : 'Not assigned'}</b>
          <small>${val(fresh.zone_name)}</small></div>
      </div>

      <div class="res-contact">
        ${fresh.phone ? `<a href="tel:${val(fresh.phone)}">Call ${val(fresh.phone)}</a>` : ''}
        ${fresh.email ? `<a href="mailto:${val(fresh.email)}">${val(fresh.email)}</a>` : ''}
        <span class="tag">${fresh.guest_confirmation_status === 'confirmed'
          ? 'Guest confirmed' : 'Awaiting guest confirmation'}</span>
        ${fresh.reminder_sent_at ? '<span class="tag">reminder sent</span>' : ''}
        <span class="tag">booked ${val((fresh.created_at || '').replace('T', ' ').slice(0, 16))}</span>
      </div>

      <div class="btn-row" style="margin-bottom:14px">
        <button class="btn tiny solid" data-life="seated">Seated</button>
        <button class="btn tiny" data-life="late">Late</button>
        <button class="btn tiny" data-life="completed">Completed</button>
        <button class="btn tiny ghost" data-life="no_show">No-show</button>
        <button class="btn tiny ghost" data-life="cancelled">Cancel</button>
      </div>

      <h3 style="margin:6px 0 8px">Table assignment</h3>
      <div class="row2">
        <label class="lbl">Move to<select class="field" id="rd-table">
          ${fresh.table_number ? `<option value="${fresh.table_number}">Keep Table ${fresh.table_number}</option>` : ''}
          ${choices.filter(c => c.number !== fresh.table_number).map(c =>
            `<option value="${c.number}">Table ${c.number} · ${NOVA.esc(c.zone)} · ${c.seats} seats</option>`).join('')}
        </select></label>
        <div class="btn-row" style="align-items:flex-end">
          <button class="btn solid" id="rd-keep">Keep this table</button>
          <button class="btn" id="rd-move">Change table</button>
        </div>
      </div>
      <p class="sub">A move is refused if the destination already has a booking overlapping this one.</p>

      <h3 style="margin:16px 0 8px">Edit the booking</h3>
      <div class="res-edit-grid">
        <label class="lbl">Date<input class="field" id="rd-date" type="date" value="${val(fresh.date)}"></label>
        <label class="lbl">Time<input class="field" id="rd-time" type="time" value="${val(fresh.time)}"></label>
        <label class="lbl">Party size<input class="field" id="rd-party" type="number" min="1" max="30" value="${fresh.party_size}"></label>
        <label class="lbl">Duration (min)<input class="field" id="rd-duration" type="number" min="45" max="300" step="15" value="${fresh.duration}"></label>
        <label class="lbl">First name<input class="field" id="rd-first" value="${val(fresh.guest && fresh.guest.first_name)}"></label>
        <label class="lbl">Last name<input class="field" id="rd-last" value="${val(fresh.guest && fresh.guest.last_name)}"></label>
        <label class="lbl">Phone<input class="field" id="rd-phone" value="${val(fresh.phone)}"></label>
        <label class="lbl">Email<input class="field" id="rd-email" value="${val(fresh.email)}"></label>
        <label class="lbl">Occasion<input class="field" id="rd-occasion" value="${val(fresh.occasion)}"></label>
        <label class="lbl">Seating preference<input class="field" id="rd-pref" value="${val(fresh.preference)}"></label>
        <label class="lbl">Allergies<input class="field" id="rd-allergies" value="${val(fresh.allergies)}"></label>
        <label class="lbl">Dietary<input class="field" id="rd-dietary" value="${val(fresh.dietary)}"></label>
        <label class="lbl">Accessibility<input class="field" id="rd-access" value="${val(fresh.accessibility)}"></label>
        <label class="lbl">High chairs<input class="field" id="rd-chairs" type="number" min="0" max="8" value="${fresh.high_chairs || 0}"></label>
        <label class="lbl full">Special request<textarea class="field" id="rd-request" rows="2">${val(fresh.special_request)}</textarea></label>
        <label class="lbl full">Floor note<textarea class="field" id="rd-note" rows="2">${val(fresh.note)}</textarea></label>
        <label class="lbl">Confirmation language<select class="field" id="rd-lang">
          ${['en', 'az', 'ru'].map(l => `<option value="${l}"${l === (fresh.language || 'en') ? ' selected' : ''}>${
            { en: 'English', az: 'Azərbaycanca', ru: 'Русский' }[l]}</option>`).join('')}
        </select></label>
        <div class="lbl"><span>No-show risk</span><b>${risk}%</b></div>
      </div>

      <div class="btn-row">
        <button class="btn solid" id="rd-save">Save changes</button>
      </div>
      <p class="form-error" id="rd-error"></p>`,
      (body, close) => {
        const err = body.querySelector('#rd-error');
        const run = async (fn) => {
          err.textContent = '';
          try { await fn(); } catch (e) { err.textContent = e.message; }
        };
        body.querySelectorAll('[data-life]').forEach(b => b.onclick = () => run(async () => {
          const to = b.dataset.life;
          if (['cancelled', 'no_show'].includes(to) &&
              !confirm(`Mark ${fresh.code} as ${to.replace('_', ' ')}? This releases the table.`)) return;
          await NOVA.api(`/api/admin/reservations/${r.id}/status`, { status: to });
          NOVA.toast(`Marked ${to.replace('_', ' ')}`);
          close(); refresh();
        }));
        body.querySelector('#rd-keep').onclick = () => run(async () => {
          const res = await NOVA.api(`/api/admin/reservations/${r.id}/keep-table`, {});
          NOVA.toast(res.message);
        });
        body.querySelector('#rd-move').onclick = () => run(async () => {
          const to = parseInt(body.querySelector('#rd-table').value, 10);
          if (to === fresh.table_number) return NOVA.toast('That is already the assigned table.');
          const res = await NOVA.api(`/api/admin/reservations/${r.id}/table`, { table_number: to });
          NOVA.toast(`Moved to table ${res.table}`);
          close(); refresh();
        });
        body.querySelector('#rd-save').onclick = () => run(async () => {
          await NOVA.api(`/api/admin/reservations/${r.id}`, {
            date: body.querySelector('#rd-date').value,
            time: body.querySelector('#rd-time').value,
            party_size: body.querySelector('#rd-party').value,
            duration: body.querySelector('#rd-duration').value,
            first_name: body.querySelector('#rd-first').value,
            last_name: body.querySelector('#rd-last').value,
            phone: body.querySelector('#rd-phone').value,
            email: body.querySelector('#rd-email').value,
            occasion: body.querySelector('#rd-occasion').value,
            preference: body.querySelector('#rd-pref').value,
            allergies: body.querySelector('#rd-allergies').value,
            dietary: body.querySelector('#rd-dietary').value,
            accessibility: body.querySelector('#rd-access').value,
            high_chairs: body.querySelector('#rd-chairs').value,
            special_request: body.querySelector('#rd-request').value,
            note: body.querySelector('#rd-note').value,
            language: body.querySelector('#rd-lang').value,
          });
          NOVA.toast('Booking updated');
          close(); refresh();
        });
      });
  }

  function timeline(d) {
    const rows = d.reservations || [];
    const HOURS = [12,13,14,15,16,17,18,19,20,21,22,23];
    const live = rows.filter(r => !['cancelled','no_show','completed','left'].includes(r.status));
    const byHour = Object.fromEntries(HOURS.map(h => [h, live.filter(r => Math.floor(Number(r.hour ?? String(r.time || '0').split(':')[0])) === h)]));
    $('#res-timeline').innerHTML = `<div class="sufra-calendar sufra-calendar-v3">
      <div class="calendar-legend"><span class="reserved">Reserved</span><span class="walkin">Free for walk-ins</span><span class="seated">Seated</span><em>Press any reservation for full details</em></div>
      ${HOURS.map(h => {
        const list = byHour[h] || [];
        return `<div class="cal-row ${list.length ? 'has-bookings' : ''}"><time>${String(h).padStart(2,'0')}:00</time><div class="cal-events">${
          list.length ? list.map(r => `<button type="button" class="cal-book res-clickable ${r.status === 'seated' ? 'seated' : ''} ${r.risk > .3 ? 'risk' : ''}" data-res-detail="${r.id}">
            <div class="res-card-main"><small>${NOVA.esc(r.time)}${r.ends ? `–${NOVA.esc(r.ends)}` : ''}</small><b>${NOVA.esc(r.guest)}</b><span>${r.party} guests · ${r.table ? `Table ${r.table}` : 'Awaiting table'}</span></div>
            <div class="res-card-side"><strong>${NOVA.esc(r.pref || 'Best available')}</strong><em>${Math.round(Number(r.risk || 0)*100)}% risk</em></div>
          </button>`).join('') : '<div class="cal-free"><b>Open capacity</b><span>Available for walk-ins</span></div>'
        }</div></div>`;
      }).join('')}
    </div>`;
    $$('#res-timeline [data-res-detail]').forEach(el => {
      el.onclick = () => {
        const r = rows.find(x => String(x.id) === String(el.dataset.resDetail));
        if (r) openReservationDetail(r);
      };
    });
  }

  async function refresh() {
    const d = await NOVA.api(`/api/admin/reservations?day=${day}`);
    const s = d.summary;
    $('#res-date').dataset.novaDate = d.day;
    $('#res-date').textContent = new Date(d.day+'T12:00:00').toDateString();
    $('#res-strip').innerHTML = [
      ['Bookings', s.bookings, 'on the book'],
      ['Covers', s.covers, `of ${s.capacity} seats`],
      ['Fill', Math.round(100 * s.covers / Math.max(1, s.capacity)) + '%', 'of capacity'],
      ['Regulars', s.vips, 'expected'],
      ['At risk', s.at_risk, 'above 30% no-show'],
      ['Needs a look', s.awaiting_decision ?? 0, 'booked by guests'],
      ['Seated', s.seated ?? 0, 'on the floor now'],
      ['Waitlist', d.waitlist.length, 'waiting now'],
      ['Walk-in tables', s.walkin_free ?? '—', 'safe for the next 90 min'],
      ['Reserved tables', s.reserved_tables ?? '—', 'protected for bookings'],
    ].map(([l, v, sub]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${sub}</small></div>`).join('');

    timeline(d);

    /* The book is what the floor still has to do. Seated and finished
       bookings drop out of it into a disclosure below, so the list is only
       the parties still to arrive. */
    const closed = d.closed || [];
    $('#res-list').innerHTML = (d.reservations.length ? `<div class="res-book-list">
      ${d.reservations.map(r => `<article class="res-book-row${r.needs_decision ? ' awaiting' : ''}" data-id="${r.id}">
        <div class="res-book-time"><small>Time</small><b>${r.time}</b></div>
        <div class="res-book-guest"><small>Guest</small><b>${NOVA.esc(r.guest)}</b>
          <div class="res-tags">${r.vip ? '<span class="tag star">regular</span>' : ''}
          ${r.occasion ? `<span class="tag">${NOVA.esc(r.occasion)}</span>` : ''}
          ${['SUFRA 360', 'the website'].includes(r.source_label)
            ? `<span class="tag ${r.needs_decision ? 'tight' : ''}">via ${NOVA.esc(r.source_label)}${
                r.needs_decision ? ' · needs a look' : ''}</span>` : ''}</div>
          ${r.allergies ? `<div class="micro down">allergy: ${NOVA.esc(r.allergies)}</div>` : ''}
          ${r.note ? `<div class="micro">${NOVA.esc(r.note)}</div>` : ''}</div>
        <div class="res-book-party"><small>Party</small><b>${r.party} people</b><span>${r.table ? `Table ${r.table}` : '—'}</span></div>
        <div class="res-book-risk"><small>Risk</small><span class="tag ${r.risk>.3?'tight':''}">${Math.round(r.risk*100)}%</span></div>
        <div class="res-book-actions btn-row">
          ${r.needs_decision ? `<button class="btn tiny solid" data-accept="${r.id}">Accept</button>
            <button class="btn tiny danger" data-decline="${r.id}">Decline</button>` : ''}
          <button class="btn tiny" data-act="seated">Seat</button>
          ${r.status==='seated'?'<button class="btn tiny solid" data-act="completed">Left</button>':'<button class="btn tiny ghost" data-act="late">Late</button>'}
          <button class="btn tiny ghost" data-act="no_show">No-show</button>
          <button class="btn tiny ghost" data-act="cancelled">Cancel</button>
          <button class="btn tiny solid" data-open="${r.id}">Open</button>
        </div>
      </article>`).join('')}</div>`
      : NOVA.empty('Nothing still to arrive.', 'Every booking for this day has been seated, finished or cancelled.'))
      + (closed.length ? `<details class="res-closed"><summary>Seated and finished (${closed.length})</summary>
        ${closed.map(r => `<div class="kv"><span>${NOVA.esc(r.time)} · <b>${NOVA.esc(r.guest)}</b>
          <div class="micro">${r.party} guests${r.table ? ` · Table ${r.table}` : ''}${
            r.source_label ? ` · via ${NOVA.esc(r.source_label)}` : ''}</div></span>
          <b class="${['cancelled', 'no_show'].includes(r.status) ? 'down' : 'up'}">${
            NOVA.esc(String(r.status).replaceAll('_', ' '))}</b></div>`).join('')}</details>` : '');

    $$('#res-list [data-accept]').forEach(b => b.onclick = async () => {
      try {
        const res = await NOVA.api(`/api/admin/reservations/${b.dataset.accept}/decision`, { decision: 'accept' });
        NOVA.toast(res.message); refresh();
      } catch (e) { NOVA.fail(e); }
    });
    $$('#res-list [data-decline]').forEach(b => b.onclick = () => {
      const row = d.reservations.find(x => String(x.id) === String(b.dataset.decline)) || {};
      NOVA.modal(`Decline ${NOVA.esc(row.code || '')}`, `
        <p class="sub">${NOVA.esc(row.guest_name || 'The guest')} believes this table is theirs.
           Declining releases it and sends them a message explaining — so say something
           they can act on.</p>
        <label class="lbl">Why can you not hold it?<textarea class="field" id="dec-why" rows="3"
          placeholder="for example: the terrace is closed for a private event that evening"></textarea></label>
        <button class="btn solid block danger" id="dec-go">Decline and tell the guest</button>
        <p class="form-error" id="dec-error"></p>`, (body, close) => {
        body.querySelector('#dec-go').onclick = async () => {
          try {
            const res = await NOVA.api(`/api/admin/reservations/${b.dataset.decline}/decision`,
              { decision: 'decline', reason: body.querySelector('#dec-why').value.trim() });
            close(); NOVA.toast(res.message, res.delivery && res.delivery.delivered ? '' : 'bad'); refresh();
          } catch (e) { body.querySelector('#dec-error').textContent = e.message; }
        };
      });
    });

    $$('#res-list [data-open]').forEach(b => b.onclick = () => {
      const row = d.reservations.find(x => String(x.id) === String(b.dataset.open));
      if (row) openReservationDetail(row);
    });
    $$('#res-list [data-id]').forEach(tr =>
      tr.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
        try {
          await NOVA.api(`/api/admin/reservations/${tr.dataset.id}/status`,
            { status: b.dataset.act });
          NOVA.toast(`Marked ${b.dataset.act.replace('_', ' ')}`);
          refresh();
        } catch (e) { NOVA.fail(e); }
      }));

    $('#res-waitlist').innerHTML = d.waitlist.length ? d.waitlist.map(w => `
      <div class="task res-wait-row p${w.waiting > w.quoted ? 1 : 2}" data-id="${w.id}">
        <div class="who">${w.party}</div>
        <div class="what"><b>${NOVA.esc(w.name)}</b>
          <span>${w.party} people · waiting ${w.waiting}m, quoted ${w.quoted}m${
            w.source === 'sufra_360' ? ' · from SUFRA 360' : ''}</span>
          ${w.desired ? `<div class="micro">wants ${NOVA.esc(w.desired)}${w.area ? ' · ' + NOVA.esc(w.area) : ''}</div>` : ''}
          ${w.phone || w.email ? `<div class="micro">${NOVA.esc([w.phone, w.email].filter(Boolean).join(' · '))}</div>` : ''}
          ${w.note ? `<div class="micro">${NOVA.esc(w.note)}</div>` : ''}</div>
        <div class="btn-row">
          <button class="btn tiny solid" data-convert="${w.id}">Make a booking</button>
          <button class="btn tiny" data-act="seated">Seat</button>
          <button class="btn tiny ghost" data-act="left">Left</button></div></div>`).join('')
      : NOVA.empty('Nobody waiting.', 'Walk-ins go straight to a table.');

    $$('#res-waitlist [data-convert]').forEach(b => b.onclick = async () => {
      try {
        const res = await NOVA.api(`/api/admin/waitlist/${b.dataset.convert}/convert`, {});
        NOVA.toast(`Booked · ${res.reservation.code} · Table ${res.reservation.table_number}`);
        refresh();
      } catch (e) { NOVA.fail(e); }
    });

    $$('#res-waitlist [data-id]').forEach(el =>
      el.querySelectorAll('[data-act]').forEach(b => b.onclick = async () => {
        try {
          await NOVA.api(`/api/admin/waitlist/${el.dataset.id}/status`, { status: b.dataset.act });
          refresh();
        } catch (e) { NOVA.fail(e); }
      }));
  }

  const shift = n => {
    const d = new Date(day); d.setDate(d.getDate() + n);
    day = d.toISOString().slice(0, 10); refresh();
  };
  $('#new-booking').onclick = openBooking;
  $('#new-waitlist').onclick = openWaitlist;
  $('#res-prev').onclick = () => shift(-1);
  $('#res-next').onclick = () => shift(1);
  $('#res-today').onclick = () => { day = new Date().toISOString().slice(0, 10); refresh(); };

  NOVA.load($('#res-list'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* ============================================================
   Orders
   ============================================================ */

function bootOrders() {
  let scope = 'open';

  async function refresh() {
    const d = await NOVA.api(`/api/admin/orders?scope=${scope}`);
    $('#ord-strip').innerHTML = [
      ['Open bills', d.totals.open, 'not yet settled'],
      ['Value on the floor', NOVA.money(d.totals.value), 'today'],
      ['Outstanding', NOVA.money(d.totals.outstanding), 'still to collect'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#ord-list').innerHTML = d.orders.length ? d.orders.map(o => `
      <div class="card order-card">
        <div class="order-head">
          <div><b class="tno">Table ${o.table}</b>
            <span class="sub">${NOVA.esc(o.waiter)} · opened ${o.opened} · ${o.minutes}m</span></div>
          <div class="right">
            <b>${NOVA.money2(o.total)}</b>
            ${o.paid ? '<span class="tag star">settled</span>'
              : o.settled ? `<span class="tag tight">${NOVA.money2(o.outstanding)} left</span>`
              : '<span class="tag">unpaid</span>'}</div>
        </div>
        <table class="data compact"><tbody>${o.items.map(i => `<tr>
          <td>${i.qty} × ${NOVA.esc(i.name)}${i.note ? `<div class="micro">${NOVA.esc(i.note)}</div>` : ''}</td>
          <td><span class="tag">${NOVA.esc(i.station)}</span></td>
          <td><span class="tag ${i.state === 'served' ? 'star' : ''}">${NOVA.esc(i.state)}</span></td>
          <td class="num right">${NOVA.money2(i.price * i.qty)}</td></tr>`).join('')}</tbody></table>
      </div>`).join('')
      : NOVA.empty('No orders in this view.', 'Open bills appear here the moment one is started.');
  }

  $$('[data-scope]').forEach(b => b.onclick = () => {
    scope = b.dataset.scope;
    $$('[data-scope]').forEach(x => x.classList.toggle('solid', x === b));
    refresh();
  });
  NOVA.load($('#ord-list'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* ============================================================
   Menu admin
   ============================================================ */

function bootMenuAdmin() {
  let items = [], course = 'All';

  function edit(item) {
    NOVA.modal(item.name, `
      <div class="row2">
        <label class="lbl">Price<input class="field" id="e-price" type="number" step="0.5" value="${item.price}"></label>
        <label class="lbl">Food cost<input class="field" id="e-cost" type="number" step="0.1" value="${item.cost}"></label>
      </div>
      <div class="row2">
        <label class="lbl">Prep minutes<input class="field" id="e-min" type="number" value="${item.minutes}"></label>
        <label class="lbl">Calories<input class="field" id="e-kcal" type="number" value="${item.kcal}"></label>
      </div>
      <label class="lbl">Description<textarea class="field" id="e-blurb" rows="2">${NOVA.esc(item.blurb)}</textarea></label>
      <label class="lbl">Allergens and diets, comma separated<input class="field" id="e-tags" value="${NOVA.esc(item.tags.join(','))}"></label>
      <label class="check"><input type="checkbox" id="e-avail" ${item.available ? 'checked' : ''}>
        <span>Available tonight. Unticking pulls it from the guest menu and the order pad immediately.</span></label>
      ${item.advice ? `<div class="callout"><b>${NOVA.esc(item.class)}</b>${NOVA.esc(item.advice)}</div>` : ''}
      <div class="btn-row"><button class="btn solid" id="e-save">Save changes</button><button class="btn danger" id="e-remove">Remove from menu</button></div>
      <p class="form-error" id="e-error"></p>`, (body, close) => {
      body.querySelector('#e-save').onclick = async () => {
        try {
          await NOVA.api(`/api/admin/menu/${item.id}`, {
            price: body.querySelector('#e-price').value,
            food_cost: body.querySelector('#e-cost').value,
            base_minutes: body.querySelector('#e-min').value,
            kcal: body.querySelector('#e-kcal').value,
            blurb: body.querySelector('#e-blurb').value,
            tags: body.querySelector('#e-tags').value,
            available: body.querySelector('#e-avail').checked,
          });
          close(); NOVA.toast(`${item.name} updated`); refresh();
        } catch (e) { body.querySelector('#e-error').textContent = e.message; }
      };
      body.querySelector('#e-remove').onclick = async () => {
        if(!confirm('Remove this dish from active menus?'))return;
        try{
          const r=await NOVA.api(`/api/ops/menu/items/${item.id}`,null,'DELETE');
          close();
          NOVA.toast(r.message||'Dish removed.','good');
          refresh().catch(()=>{});
        }catch(e){
          body.querySelector('#e-error').textContent=e.message;
        }
      };
    });
  }

  function render() {
    const list = items.filter(i => course === 'All' || i.course === course);
    $('#menu-table').innerHTML = `<table class="data">
      <thead><tr><th></th><th>Dish</th><th>Price</th><th>Margin</th><th>Sold</th>
      <th>Class</th><th>On</th></tr></thead><tbody>
      ${list.map(i => `<tr data-id="${i.id}" class="clickable">
        <td>${i.image_url?`<img class="menu-thumb" src="${NOVA.esc(i.image_url)}" alt="${NOVA.esc(i.name)}">`:plate(i.hue,34,i.signature)}</td>
        <td><b>${NOVA.esc(i.name)}</b>
          <div class="micro">${i.tags.map(t => TAG_LABEL[t] || t).join(' · ') || '—'}</div></td>
        <td class="num">${CUR}${i.price}</td>
        <td class="num">${NOVA.money2(i.margin)} <span class="micro">${i.margin_pct}%</span></td>
        <td class="num">${i.sold}</td>
        <td><span class="tag ${i.class === 'star' ? 'star' : i.class === 'weak' ? 'weak'
          : i.class === 'hidden gem' ? 'gem' : ''}">${NOVA.esc(i.class)}</span></td>
        <td>${i.available ? '<span class="tag star">yes</span>' : '<span class="tag weak">off</span>'}</td>
      </tr>`).join('')}</tbody></table>`;
    $$('#menu-table tr[data-id]').forEach(tr =>
      tr.onclick = () => edit(items.find(i => i.id === +tr.dataset.id)));
  }

  async function refresh() {
    const d = await NOVA.api('/api/admin/menu');
    items = d.items;
    const off = items.filter(i => !i.available).length;
    $('#menu-strip').innerHTML = [
      ['Dishes', items.length, `${off} unavailable`],
      ['Average margin', Math.round(items.reduce((s, i) => s + i.margin_pct, 0) / items.length) + '%',
        'across the menu'],
      ['Stars', items.filter(i => i.class === 'star').length, 'popular and profitable'],
      ['Weak performers', items.filter(i => i.class === 'weak').length, 'candidates to cut'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#menu-filters').innerHTML = ['All', ...d.courses].map(c =>
      `<button class="btn ${c === course ? 'solid' : ''}" data-c="${c}">${c}</button>`).join('');
    $$('#menu-filters button').forEach(b => b.onclick = () => {
      course = b.dataset.c;
      $$('#menu-filters button').forEach(x => x.classList.toggle('solid', x === b));
      render();
    });

    const groups = ['star', 'workhorse', 'hidden gem', 'weak'];
    const copy = { star: 'Popular and profitable. Protect these.',
      workhorse: 'Popular, thin. Lift the price or trim the cost.',
      'hidden gem': 'Profitable, overlooked. Move it up the page.',
      weak: 'Neither. Cut it or rework it.' };
    const cls = { star: 'star', workhorse: '', 'hidden gem': 'gem', weak: 'weak' };
    $('#menu-matrix').innerHTML = `<div class="matrix">${groups.map(g => {
      const rows = items.filter(i => i.class === g);
      return `<div><h4><span class="tag ${cls[g]}">${g}</span></h4>
        <p class="sub">${copy[g]}</p>
        ${rows.slice(0, 7).map(i => `<div class="kv"><span>${NOVA.esc(i.name)}</span>
          <b>${i.sold} · ${i.margin_pct}%</b></div>`).join('')}</div>`;
    }).join('')}</div>`;

    render();
  }
  NOVA.load($('#menu-table'), refresh);
}

/* ============================================================
   Inventory
   ============================================================ */

function bootInventory() {
  async function refresh() {
    const d = await NOVA.api('/api/inventory');
    const short = d.rows.filter(r => r.status === 'short').length;
    const tight = d.rows.filter(r => r.status === 'tight').length;
    $('#inv-strip').innerHTML = [
      ['Lines tracked', d.rows.length, 'ingredients'],
      ['Running short', short, 'against tomorrow'],
      ['Tight', tight, 'under 1.6 services'],
      ['Order value', NOVA.money(d.basket_value), 'if raised now'],
      ['Stock value', NOVA.money(d.rows.reduce((s, r) => s + r.in_stock * r.cost, 0)), 'on hand'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#basket-value').textContent = NOVA.money2(d.basket_value);
    $('#basket-table').innerHTML = d.basket.length ? `<table class="data">
      <thead><tr><th>Ingredient</th><th>Stock</th><th>Needed</th><th>Order</th><th>Supplier</th></tr></thead>
      <tbody>${d.basket.map(r => `<tr>
        <td>${NOVA.esc(r.name)}</td><td class="num">${r.in_stock}${r.unit}</td>
        <td class="num">${r.required}${r.unit}</td>
        <td class="num"><span class="tag ${r.status}">${r.order_qty}${r.unit}</span></td>
        <td class="sub">${NOVA.esc(r.supplier)}</td></tr>`).join('')}</tbody></table>`
      : NOVA.empty('Nothing to order.', 'Every ingredient covers tomorrow at current stock.');

    $('#inv-table').innerHTML = `<table class="data">
      <thead><tr><th>Ingredient</th><th>Stock</th><th>Par</th><th>Days cover</th>
      <th>Store</th><th>Supplier</th><th></th></tr></thead><tbody>
      ${d.rows.map(r => `<tr>
        <td>${NOVA.esc(r.name)}</td>
        <td class="num">${r.in_stock}${r.unit}</td>
        <td class="num sub">${r.par}${r.unit}</td>
        <td class="num">${r.days_cover > 90 ? '—' : r.days_cover}</td>
        <td class="sub">${NOVA.esc(r.store)}</td>
        <td class="sub">${NOVA.esc(r.supplier)}</td>
        <td><span class="tag ${r.status}">${r.status}</span></td></tr>`).join('')}</tbody></table>`;

    $('#waste-form').innerHTML = `
      <label class="lbl">Ingredient<select class="field" id="w-ing">
        ${d.rows.map(r => `<option value="${r.id}">${NOVA.esc(r.name)}</option>`).join('')}
      </select></label>
      <div class="row2">
        <label class="lbl">Quantity<input class="field" id="w-qty" type="number" step="0.1" value="1"></label>
        <label class="lbl">Reason<select class="field" id="w-reason">
          ${['overproduction', 'expired', 'prep mistake', 'returned', 'damaged']
            .map(x => `<option>${x}</option>`).join('')}</select></label>
      </div>
      <button class="btn block" id="w-log">Log it</button>`;
    $('#w-log').onclick = async () => {
      try {
        await NOVA.api('/api/admin/waste', {
          ingredient_id: $('#w-ing').value, qty: $('#w-qty').value,
          reason: $('#w-reason').value,
        });
        NOVA.toast('Waste recorded'); refresh();
      } catch (e) { NOVA.fail(e); }
    };
  }

  $('#approve').onclick = async () => {
    try {
      const r = await NOVA.api('/api/admin/purchase-orders', { by: 'Elena Rossi' });
      NOVA.toast(r.message); refresh();
    } catch (e) { NOVA.fail(e); }
  };

  const cases = [
    ['Tomorrow as forecast', 'days=1'], ['If it rains hard', 'days=1&rain=14'],
    ['With a local event', 'days=1&event=true'], ['Public holiday', 'days=1&holiday=true'],
  ];
  Promise.all(cases.map(c => NOVA.api('/api/forecast?' + c[1]))).then(rs => {
    $('#scenarios').innerHTML = rs.map((f, i) =>
      `<div class="kv"><span>${cases[i][0]}</span>
        <b>${NOVA.money(f.revenue)} · ${f.covers} covers</b></div>`).join('');
  }).catch(() => {});

  NOVA.load($('#inv-table'), refresh);
}

/* ============================================================
   Guests
   ============================================================ */

function bootGuests() {
  let q = '', vipOnly = false;

  function editGuest(g) {
    NOVA.modal(g.name, `
      <div class="kv"><span>Visits</span><b>${g.visits}</b></div>
      <div class="kv"><span>Average spend</span><b>${NOVA.money2(g.avg_spend)}</b></div>
      <div class="kv"><span>Lifetime value</span><b>${NOVA.money(g.lifetime)}</b></div>
      ${g.next ? `<div class="kv"><span>Next booking</span><b>${NOVA.esc(g.next)}</b></div>` : ''}
      <label class="lbl">Allergies<input class="field" id="g-all" value="${NOVA.esc(g.allergies)}"></label>
      <label class="lbl">Usually orders<input class="field" id="g-likes" value="${NOVA.esc(g.likes)}"></label>
      <label class="lbl">Seating preference<input class="field" id="g-pref" value="${NOVA.esc(g.pref)}"></label>
      <label class="lbl">Note for the floor<textarea class="field" id="g-note" rows="2">${NOVA.esc(g.note)}</textarea></label>
      <label class="check"><input type="checkbox" id="g-vip" ${g.vip ? 'checked' : ''}>
        <span>Flag as a regular. The floor sees this before they sit down.</span></label>
      <button class="btn solid block" id="g-save">Save</button>
      <p class="sub" style="margin-top:12px">Held with consent. Anything here is visible
        to the floor team on this guest's table.</p>`, (body, close) => {
      body.querySelector('#g-save').onclick = async () => {
        try {
          await NOVA.api(`/api/admin/guests/${g.id}`, {
            allergies: body.querySelector('#g-all').value,
            likes: body.querySelector('#g-likes').value,
            seating_pref: body.querySelector('#g-pref').value,
            note: body.querySelector('#g-note').value,
            vip: body.querySelector('#g-vip').checked,
          });
          close(); NOVA.toast('Guest updated'); refresh();
        } catch (e) { NOVA.fail(e); }
      };
    });
  }

  async function refresh() {
    const d = await NOVA.api(`/api/admin/guests?q=${encodeURIComponent(q)}&vip_only=${vipOnly}`);
    $('#guest-strip').innerHTML = [
      ['On the book', d.totals.count, 'guest records'],
      ['Regulars', d.totals.vips, 'flagged'],
      ['With allergies', d.totals.with_allergies, 'need briefing'],
      ['Lifetime value', NOVA.money(d.totals.lifetime), 'combined'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#guest-table').innerHTML = d.guests.length ? `<table class="data">
      <thead><tr><th>Guest</th><th>Visits</th><th>Average</th><th>Lifetime</th>
      <th>Notes</th><th>Next</th></tr></thead><tbody>
      ${d.guests.slice(0, 60).map(g => `<tr data-id="${g.id}" class="clickable">
        <td><b>${NOVA.esc(g.name)}</b>${g.vip ? ' <span class="tag star">regular</span>' : ''}</td>
        <td class="num">${g.visits}</td>
        <td class="num">${NOVA.money2(g.avg_spend)}</td>
        <td class="num">${NOVA.money(g.lifetime)}</td>
        <td class="sub">${g.allergies ? `<span class="tag weak">${NOVA.esc(g.allergies)}</span> ` : ''}
          ${NOVA.esc(g.pref || '')}</td>
        <td class="sub">${NOVA.esc(g.next || '—')}</td></tr>`).join('')}</tbody></table>`
      : NOVA.empty('No guests match that.', 'Try a different name, or clear the search.');

    $$('#guest-table tr[data-id]').forEach(tr =>
      tr.onclick = () => editGuest(d.guests.find(g => g.id === +tr.dataset.id)));
  }

  let timer;
  $('#guest-search').oninput = e => {
    q = e.target.value;
    clearTimeout(timer);
    timer = setTimeout(refresh, 250);
  };
  $('#guest-vip').onclick = e => {
    vipOnly = !vipOnly;
    e.target.classList.toggle('solid', vipOnly);
    refresh();
  };
  NOVA.load($('#guest-table'), refresh);
}

/* ============================================================
   Staff and rota
   ============================================================ */

function bootStaff() {
  let week = 0;
  const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  function editShift(person, dayIso, existing) {
    NOVA.modal(`${person.name} · ${new Date(dayIso).toDateString()}`, `
      <div class="row2">
        <label class="lbl">Start<input class="field" id="s-start" type="number" step="0.5"
          value="${existing ? existing.start : 16.5}"></label>
        <label class="lbl">End<input class="field" id="s-end" type="number" step="0.5"
          value="${existing ? existing.end : 23.5}"></label>
      </div>
      <label class="lbl">Status<select class="field" id="s-status">
        ${['scheduled', 'confirmed', 'sick', 'holiday'].map(x =>
          `<option ${existing && existing.status === x ? 'selected' : ''}>${x}</option>`).join('')}
      </select></label>
      <button class="btn solid block" id="s-save">${existing ? 'Update shift' : 'Add shift'}</button>`,
      (body, close) => {
        body.querySelector('#s-save').onclick = async () => {
          try {
            await NOVA.api('/api/admin/shifts', {
              id: existing ? existing.id : null, staff_id: person.id, day: dayIso,
              start_hour: body.querySelector('#s-start').value,
              end_hour: body.querySelector('#s-end').value,
              status: body.querySelector('#s-status').value,
            });
            close(); NOVA.toast('Rota updated'); refresh();
          } catch (e) { NOVA.fail(e); }
        };
      });
  }

  async function refresh() {
    const d = await NOVA.api(`/api/admin/staff?week_offset=${week}`);
    const onShift = d.staff.filter(p => p.on_shift).length;
    $('#staff-strip').innerHTML = [
      ['Team', d.staff.length, `${onShift} on shift now`],
      ['Rostered hours', d.staff.reduce((s, p) => s + p.hours, 0).toFixed(0), 'this week'],
      ['Wage bill', NOVA.money(d.wage_bill), 'this week'],
      ['Average rating', (d.staff.reduce((s, p) => s + p.rating, 0) / d.staff.length).toFixed(1),
        'from guest feedback'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#staff-demand').innerHTML = `<table class="data">
      <thead><tr><th>Day</th><th>Forecast</th><th>Waiters</th><th>Kitchen</th><th>Bar</th></tr></thead>
      <tbody>${d.demand.map(x => {
        const cell = (need, have) => `<td class="num">
          <span class="tag ${have < need ? 'short' : 'star'}">${have}/${need}</span></td>`;
        return `<tr><td>${x.dow}</td><td class="num">${x.covers} covers</td>
          ${cell(x.waiters_needed, x.waiters_rostered)}
          ${cell(x.chefs_needed, x.chefs_rostered)}
          ${cell(x.bar_needed, x.bar_rostered)}</tr>`;
      }).join('')}</tbody></table>`;

    $('#staff-rota').innerHTML = `<table class="data rota">
      <thead><tr><th>Person</th>${d.week.map((iso, i) =>
        `<th>${DOW[i]}<br><span class="micro">${new Date(iso).getDate()}</span></th>`).join('')}
        <th>Hours</th><th>Cost</th></tr></thead>
      <tbody>${d.staff.map(p => `<tr>
        <td><b>${NOVA.esc(p.name)}</b><div class="micro">${NOVA.esc(p.role)} · ★${p.rating}</div></td>
        ${d.week.map(iso => {
          const sh = p.shifts.find(x => x.day === iso);
          return `<td class="rota-cell" data-staff="${p.id}" data-day="${iso}"
            data-shift="${sh ? sh.id : ''}">${sh
              ? `<span class="shift ${sh.status}">${sh.label}</span>` : '<span class="add">+</span>'}</td>`;
        }).join('')}
        <td class="num">${p.hours}</td><td class="num">${NOVA.money(p.cost)}</td></tr>`).join('')}
      </tbody></table>`;

    $$('.rota-cell').forEach(td => td.onclick = () => {
      const person = d.staff.find(p => p.id === +td.dataset.staff);
      const sh = person.shifts.find(x => x.day === td.dataset.day);
      editShift(person, td.dataset.day, sh);
    });
  }

  $('#wk-prev').onclick = () => { week--; refresh(); };
  $('#wk-next').onclick = () => { week++; refresh(); };
  $('#wk-this').onclick = () => { week = 0; refresh(); };
  $('#auto-roster').onclick = async () => {
    const day = new Date(); day.setDate(day.getDate() + 1);
    try {
      const r = await NOVA.api('/api/admin/shifts/auto', { day: day.toISOString().slice(0, 10) });
      NOVA.toast(r.message); refresh();
    } catch (e) { NOVA.fail(e); }
  };
  NOVA.load($('#staff-rota'), refresh);
}

/* ============================================================
   Analytics
   ============================================================ */

function bootAnalytics() {
  async function refresh() {
    const d = await NOVA.api('/api/admin/analytics');
    const rev = d.trend.reduce((s, t) => s + t.revenue, 0);
    const cov = d.trend.reduce((s, t) => s + t.covers, 0);
    $('#an-strip').innerHTML = [
      ['Revenue, 30 days', NOVA.money(rev), 'total'],
      ['Covers', cov.toLocaleString(), 'guests served'],
      ['Per cover', NOVA.money2(rev / Math.max(1, cov)), 'average bill'],
      ['Waste', NOVA.money(d.waste.total), 'at cost'],
      ['Repeat guests', d.retention.rate + '%', `${d.retention.repeat} of ${d.retention.guests}`],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    NOVA.areaChart($('#an-trend'), d.trend.map(t => ({ k: t.label, v: t.revenue })),
      { label: v => (window.SUFRA_CURRENCY || '\u20bc') + Math.round(v / 1000) + 'k', id: 'anFade' });
    NOVA.barChart($('#an-weekday'), d.weekday.map(w => ({ k: w.dow, v: w.revenue })),
      ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][new Date().getDay() === 0 ? 6 : new Date().getDay() - 1]);

    $('#an-sat').innerHTML = Object.entries(d.satisfaction).map(([k, v]) => `
      <div class="rank"><div class="rank-label">
        <span>${k[0].toUpperCase() + k.slice(1)}</span><b>${v}%</b></div>
        <div class="rank-bar"><i class="${v < 80 ? 'warn' : ''}" style="width:${v}%"></i></div></div>`).join('');

    $('#an-retention').innerHTML = `
      <div class="kv"><span>Guests on record</span><b>${d.retention.guests}</b></div>
      <div class="kv"><span>Been before</span><b>${d.retention.repeat}</b></div>
      <div class="kv"><span>Repeat rate</span><b>${d.retention.rate}%</b></div>
      <div class="kv"><span>Average visits</span><b>${d.retention.avg_visits}</b></div>`;

    NOVA.ranked($('#an-menu'), d.menu.slice(0, 8).map(m =>
      ({ label: m.name, value: m.revenue_30d })), NOVA.money);

    $('#an-waste').innerHTML = '<div id="wr"></div><h4 style="margin:18px 0 8px">By ingredient</h4><div id="wi"></div>';
    NOVA.ranked($('#wr'), d.waste.by_reason.map(w =>
      ({ label: w.reason, value: w.value, tone: 'warn' })));
    NOVA.ranked($('#wi'), d.waste.by_item.map(w =>
      ({ label: w.name, value: w.value, tone: 'warn' })));
  }
  NOVA.load($('#an-trend'), refresh);
}

/* ============================================================
   Finance
   ============================================================ */

function bootFinance() {
  async function refresh() {
    const d = await NOVA.api('/api/admin/finance');
    $('#fin-strip').innerHTML = [
      ['Revenue', NOVA.money(d.revenue), 'today'],
      ['Food cost', NOVA.money(d.food_cost), `${100 - d.gross_margin}% of sales`],
      ['Gross profit', NOVA.money(d.gross_profit), `${d.gross_margin}% margin`],
      ['Wages', NOVA.money(d.wages), `${d.wage_pct}% of sales`],
      ['Net', NOVA.money(d.net), 'before fixed costs'],
      ['Tips', NOVA.money(d.tips), 'to the team'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    NOVA.ranked($('#fin-waterfall'), [
      { label: 'Revenue', value: d.revenue },
      { label: 'Food cost', value: d.food_cost, tone: 'warn' },
      { label: 'Wages', value: d.wages, tone: 'warn' },
      { label: 'Net', value: d.net },
    ], NOVA.money);

    NOVA.ranked($('#fin-methods'), d.by_method.map(m =>
      ({ label: m.method, value: m.value })), NOVA.money2);

    $('#fin-payments').innerHTML = d.payments.length ? `<table class="data">
      <thead><tr><th>Time</th><th>Amount</th><th>Tip</th><th>Method</th>
      <th>Split</th><th>Reference</th></tr></thead><tbody>
      ${d.payments.map(p => `<tr><td class="num">${p.at}</td>
        <td class="num">${NOVA.money2(p.amount)}</td>
        <td class="num sub">${p.tip ? NOVA.money2(p.tip) : '—'}</td>
        <td><span class="tag">${NOVA.esc(p.method)}</span></td>
        <td class="sub">${NOVA.esc(p.kind)}${p.payer ? ` · ${NOVA.esc(p.payer)}` : ''}</td>
        <td class="sub num">${NOVA.esc(p.ref)}</td></tr>`).join('')}</tbody></table>`
      : NOVA.empty('No payments yet today.', 'They appear here the moment a bill is settled.');
  }
  NOVA.load($('#fin-payments'), refresh);
  NOVA.on(() => refresh().catch(() => {}));
}

/* ============================================================
   Suppliers
   ============================================================ */

function bootSuppliers() {
  async function refresh() {
    const d = await NOVA.api('/api/admin/suppliers');
    const rising = d.price_moves.filter(m => m.change > 5).length;
    $('#sup-strip').innerHTML = [
      ['Suppliers', d.suppliers.length, 'active accounts'],
      ['Rising prices', rising, 'up over 5% in six weeks'],
      ['Open orders', d.purchase_orders.filter(p => p.status !== 'delivered').length, 'not yet delivered'],
      ['Committed', NOVA.money(d.purchase_orders.filter(p => p.status === 'sent')
        .reduce((s, p) => s + p.total, 0)), 'sent, awaiting delivery'],
    ].map(([l, v, s]) => `<div class="metric"><label>${l}</label>
      <b class="num">${v}</b><small>${s}</small></div>`).join('');

    $('#sup-moves').innerHTML = d.price_moves.map(m => `
      <div class="kv"><span>${NOVA.esc(m.ingredient)}
        <div class="micro">${NOVA.esc(m.supplier)} · ${CUR}${m.from} → ${CUR}${m.to} per ${m.unit}</div></span>
        <b class="${m.change > 0 ? 'down' : 'up'}">${m.change > 0 ? '+' : ''}${m.change}%</b></div>`).join('');

    $('#sup-pos').innerHTML = d.purchase_orders.length ? `<table class="data compact">
      <thead><tr><th>Supplier</th><th>Raised</th><th>Deliver</th><th>Value</th><th></th></tr></thead>
      <tbody>${d.purchase_orders.map(p => `<tr>
        <td>${NOVA.esc(p.supplier)}<div class="micro">by ${NOVA.esc(p.raised_by)}</div></td>
        <td class="sub">${p.created}</td><td class="sub">${p.deliver}</td>
        <td class="num">${NOVA.money2(p.total)}</td>
        <td><span class="tag ${p.status === 'delivered' ? 'star' : p.status === 'sent' ? 'tight' : ''}">
          ${NOVA.esc(p.status)}</span></td></tr>`).join('')}</tbody></table>`
      : NOVA.empty('No purchase orders yet.', 'Raise them from the inventory screen.');

    $('#sup-table').innerHTML = `<table class="data">
      <thead><tr><th>Supplier</th><th>Category</th><th>Lead time</th><th>Reliability</th>
      <th>Quality</th><th>Lines</th><th>Score</th></tr></thead><tbody>
      ${d.suppliers.map(s => `<tr>
        <td><b>${NOVA.esc(s.name)}</b><div class="micro">${NOVA.esc(s.contact || '—')}</div></td>
        <td class="sub">${NOVA.esc(s.category)}</td>
        <td class="num">${s.lead} day${s.lead === 1 ? '' : 's'}</td>
        <td class="num">${s.reliability}%</td><td class="num">${s.quality}%</td>
        <td class="num">${s.lines}</td>
        <td><span class="tag ${s.score >= 88 ? 'star' : s.score < 78 ? 'weak' : ''}">${s.score}</span></td>
      </tr>`).join('')}</tbody></table>`;
  }
  NOVA.load($('#sup-table'), refresh);
}

/* ============================================================
   Settings
   ============================================================ */

function bootSettings() {
  async function refresh() {
    const d = await NOVA.api('/api/admin/settings');
    $('#set-locations').innerHTML = d.locations.map(l => `
      <div class="kv"><span>${NOVA.esc(l.name)}
        <div class="micro">${NOVA.esc(l.city)} · ${l.seats} seats · ${NOVA.esc(l.currency)}</div></span>
        <b>${l.home ? '<span class="tag star">live</span>' : '<span class="tag">forecast</span>'}</b>
      </div>`).join('');

    $('#set-group').innerHTML = d.group.map(g => `
      <div class="kv"><span>${NOVA.esc(g.name)}
        <div class="micro">${g.covers} covers · ${NOVA.money2(g.spend)} per cover</div></span>
        <b>${NOVA.money(g.revenue)}</b></div>`).join('')
      + `<p class="sub" style="margin-top:14px">${NOVA.esc(d.note)}</p>`;

    $('#set-roles').innerHTML = `<table class="data compact"><tbody>
      ${d.roles.map(r => `<tr><td><b>${NOVA.esc(r.role)}</b></td>
        <td class="sub">${NOVA.esc(r.access)}</td></tr>`).join('')}</tbody></table>`;
  }

  $('#set-reset').onclick = async () => {
    NOVA.modal('Reset the demo?', `
      <p class="sub">This rebuilds the whole restaurant: floor, menu, stock, guests,
        bookings and 180 days of trading history. Anything you have changed is lost.</p>
      <div class="btn-row" style="margin-top:18px">
        <button class="btn solid" id="r-yes">Yes, rebuild it</button>
        <button class="btn ghost" id="r-no">Keep what I have</button></div>`,
      (body, close) => {
        body.querySelector('#r-no').onclick = close;
        body.querySelector('#r-yes').onclick = async () => {
          close();
          NOVA.toast('Rebuilding…');
          try { await NOVA.api('/api/reset', {}); NOVA.toast('Demo reset'); }
          catch (e) { NOVA.fail(e); }
        };
      });
  };
  NOVA.load($('#set-group'), refresh);
}


/* NOVA COMMAND LANGUAGE PATCH 20260901 */
const NOVACommandLang=(()=>{
  let lang='en',wired=false;

  const T={
    en:{
      morning:'Good morning',
      afternoon:'Good afternoon',
      evening:'Good evening',
      progress:'service in progress',
      next:'The next two hours',
      reading:'Reading the room…',
      decisions:'What needs a decision',
      ranked:'Ranked by what it costs if nobody acts.',
      forecast:"Tonight's forecast",
      ridge:'Ridge regression over 180 trading days.',
      revenueDay:'Revenue through the day',
      everyHour:'Every hour of trading so far.',
      coversHour:'Covers by hour',
      kitchen:'Kitchen pressure',
      kitchenSub:'Open tickets now, and the projection twenty minutes out.',
      ask:'Ask SUFRA',
      askSub:"Answers are computed from the restaurant's own data. Every reply says where the number came from.",
      askPh:'Ask about anything in the restaurant',
      askBtn:'Ask',
      revenue:'Revenue today',
      covers:'Covers',
      mains:'mains served',
      per:'Per cover',
      avg:'average bill',
      occ:'Occupancy',
      duration:'Table duration',
      sat:'Satisfaction',
      seven:'last seven days',
      overview:'Overview',
      service:'Service',
      product:'Product',
      people:'People',
      business:'Business',
      command:'Command centre',
      operations:'Live operations',
      floor:'Floor',
      reservations:'Reservations',
      orders:'Orders',
      kitchenNav:'Kitchen',
      menu:'Menu',
      inventory:'Inventory',
      suppliers:'Suppliers',
      guests:'Guests',
      staff:'Staff',
      events:'Events',
      analytics:'Analytics',
      finance:'Finance',
      copilot:'AI Copilot',
      settings:'Settings',
      live:'Live',
      switch:'Switch user',
      waiter:'Waiter app',
      guest:'Guest app',
      seed1:'Why was revenue lower yesterday?',
      seed2:'Which ingredients run out tomorrow?',
      seed3:'How many waiters do I need Friday?',
      seed4:'Which dishes should we remove?',
      seed5:'Where is the kitchen congested?'
    },

    az:{
      morning:'Sabahınız xeyir',
      afternoon:'Günortanız xeyir',
      evening:'Axşamınız xeyir',
      progress:'xidmət davam edir',
      next:'Növbəti iki saat',
      reading:'Zal təhlil olunur…',
      decisions:'Qərar tələb edən məsələlər',
      ranked:'Heç kim tədbir görməsə yaradacağı təsirə görə sıralanıb.',
      forecast:'Bu axşamın proqnozu',
      ridge:'180 iş günü üzrə ridge reqressiyası.',
      revenueDay:'Gün ərzində gəlir',
      everyHour:'Bu gün indiyədək hər iş saatı.',
      coversHour:'Saat üzrə qonaq sayı',
      kitchen:'Mətbəx yükü',
      kitchenSub:'Hazırda açıq çeklər və iyirmi dəqiqəlik proqnoz.',
      ask:'SUFRA-dan soruşun',
      askSub:'Cavablar restoranın öz məlumatlarından hesablanır. Hər cavab rəqəmin mənbəyini göstərir.',
      askPh:'Restoran haqqında istənilən sualı verin',
      askBtn:'Soruş',
      revenue:'Bugünkü gəlir',
      covers:'Qonaqlar',
      mains:'əsas yemək servis edilib',
      per:'Qonaq başına',
      avg:'orta hesab',
      occ:'Doluluq',
      duration:'Masa müddəti',
      sat:'Məmnunluq',
      seven:'son yeddi gün',
      overview:'Ümumi baxış',
      service:'Xidmət',
      product:'Məhsul',
      people:'İnsanlar',
      business:'Biznes',
      command:'İdarəetmə mərkəzi',
      operations:'Canlı əməliyyatlar',
      floor:'Zal',
      reservations:'Rezervasiyalar',
      orders:'Sifarişlər',
      kitchenNav:'Mətbəx',
      menu:'Menyu',
      inventory:'Ehtiyatlar',
      suppliers:'Təchizatçılar',
      guests:'Qonaqlar',
      staff:'Heyət',
      events:'Tədbirlər',
      analytics:'Analitika',
      finance:'Maliyyə',
      copilot:'AI Köməkçi',
      settings:'Ayarlar',
      live:'Canlı',
      switch:'İstifadəçini dəyiş',
      waiter:'Ofisiant tətbiqi',
      guest:'Qonaq tətbiqi',
      seed1:'Dünən gəlir niyə aşağı idi?',
      seed2:'Sabah hansı məhsullar tükənəcək?',
      seed3:'Cümə günü neçə ofisiant lazımdır?',
      seed4:'Hansı yeməkləri menyudan çıxarmalıyıq?',
      seed5:'Mətbəxdə sıxlıq haradadır?'
    },

    ru:{
      morning:'Доброе утро',
      afternoon:'Добрый день',
      evening:'Добрый вечер',
      progress:'обслуживание идёт',
      next:'Следующие два часа',
      reading:'Анализируем зал…',
      decisions:'Что требует решения',
      ranked:'По потенциальному эффекту, если ничего не делать.',
      forecast:'Прогноз на вечер',
      ridge:'Ridge-регрессия по 180 рабочим дням.',
      revenueDay:'Выручка в течение дня',
      everyHour:'Каждый час работы за сегодня.',
      coversHour:'Гости по часам',
      kitchen:'Нагрузка кухни',
      kitchenSub:'Открытые чеки сейчас и прогноз на двадцать минут.',
      ask:'Спросить NOVA',
      askSub:'Ответы рассчитываются по данным ресторана. В каждом ответе указано, откуда взялась цифра.',
      askPh:'Спросите что угодно о ресторане',
      askBtn:'Спросить',
      revenue:'Выручка сегодня',
      covers:'Гости',
      mains:'основных блюд подано',
      per:'На гостя',
      avg:'средний чек',
      occ:'Заполняемость',
      duration:'Время за столом',
      sat:'Удовлетворённость',
      seven:'последние семь дней',
      overview:'Обзор',
      service:'Сервис',
      product:'Продукт',
      people:'Люди',
      business:'Бизнес',
      command:'Центр управления',
      operations:'Операции в реальном времени',
      floor:'Зал',
      reservations:'Бронирования',
      orders:'Заказы',
      kitchenNav:'Кухня',
      menu:'Меню',
      inventory:'Запасы',
      suppliers:'Поставщики',
      guests:'Гости',
      staff:'Персонал',
      events:'События',
      analytics:'Аналитика',
      finance:'Финансы',
      copilot:'AI-помощник',
      settings:'Настройки',
      live:'Онлайн',
      switch:'Сменить пользователя',
      waiter:'Приложение официанта',
      guest:'Приложение гостя',
      seed1:'Почему вчера выручка была ниже?',
      seed2:'Какие продукты закончатся завтра?',
      seed3:'Сколько официантов нужно в пятницу?',
      seed4:'Какие блюда стоит убрать?',
      seed5:'Где перегружена кухня?'
    }
  };

  const tr=k=>(T[lang]&&T[lang][k])||T.en[k]||k;

  function set(sel,text){
    const e=document.querySelector(sel);
    if(e)e.textContent=text;
  }

  function nav(a,text){
    if(!a)return;
    const d=a.querySelector('.dot');
    a.textContent='';
    if(d)a.appendChild(d);
    a.appendChild(document.createTextNode(text));
  }

  function translateDynamic(s){
    if(lang==='en'||!s)return s;
    let m;

    if((m=s.match(/^(\d+) things? worth acting on before (\d\d:\d\d)\.$/)))
      return lang==='az'
        ? `${m[1]} məsələ ${m[2]}-dək tədbir tələb edir.`
        : `${m[1]} задач требуют действий до ${m[2]}.`;

    if((m=s.match(/^(\d+(?:\.\d+)?)% gross margin$/)))
      return lang==='az'
        ? `${m[1]}% ümumi marja`
        : `Валовая маржа ${m[1]}%`;

    if((m=s.match(/^(\d+) of (\d+) tables$/)))
      return lang==='az'
        ? `${m[1]} / ${m[2]} masa xidmətdədir`
        : `${m[1]} из ${m[2]} столов заняты`;

    if((m=s.match(/^(\d+) tickets open, oldest (\d+)m$/)))
      return lang==='az'
        ? `${m[1]} açıq çek · ən köhnəsi ${m[2]} dəq`
        : `Открыто чеков: ${m[1]} · старейшему ${m[2]} мин`;

    if(s==='kitchen is clear')
      return lang==='az'
        ? 'mətbəxdə növbə yoxdur'
        : 'на кухне нет очереди';

    if((m=s.match(/^(\d+) covers · (\d+) booked$/)))
      return lang==='az'
        ? `${m[1]} qonaq · ${m[2]} rezerv edilib`
        : `${m[1]} гостей · ${m[2]} забронировано`;

    if((m=s.match(/^Model explains (\d+)% of past variation$/)))
      return lang==='az'
        ? `Model keçmiş dəyişkənliyin ${m[1]}%-ni izah edir`
        : `Модель объясняет ${m[1]}% прошлой вариации`;

    if((m=s.match(/^(\d+)\/(\d+) now · (\d+)% in 20m$/)))
      return lang==='az'
        ? `${m[1]}/${m[2]} indi · 20 dəq sonra ${m[3]}%`
        : `${m[1]}/${m[2]} сейчас · через 20 мин ${m[3]}%`;

    if((m=s.match(/^(.+?) arrives in (\d+) minutes$/)))
      return lang==='az'
        ? `${m[1]} ${m[2]} dəqiqəyə gəlir`
        : `${m[1]} прибудет через ${m[2]} мин`;

    if(s==='Brief the section before they sit, not after.')
      return lang==='az'
        ? 'Qonaqlar əyləşməmişdən əvvəl bölməni məlumatlandırın.'
        : 'Проинформируйте секцию до того, как гости сядут.';

    if((m=s.match(/^Table (\d+) waiting (\d+) minutes$/)))
      return lang==='az'
        ? `Masa ${m[1]} ${m[2]} dəqiqədir gözləyir`
        : `Стол ${m[1]} ждёт ${m[2]} мин`;

    if(s==='Assign the nearest waiter and open with an apology, not a menu.')
      return lang==='az'
        ? 'Ən yaxın ofisiantı yönləndirin və üzrxahlıqla yaxınlaşın.'
        : 'Направьте ближайшего официанта и начните с извинения.';

    if((m=s.match(/^Forecast ([^\s]+[\d,.]+) against a usual ([^\s]+[\d,.]+)\. (\d+) covers already booked\.$/)))
      return lang==='az'
        ? `Proqnoz ${m[1]}, adi göstərici ${m[2]}. Artıq ${m[3]} qonaq rezerv edilib.`
        : `Прогноз ${m[1]}, обычный уровень ${m[2]}. Уже забронировано ${m[3]} гостей.`;

    if((m=s.match(/^State is '(.+)', which should clear in (\d+)\.$/)))
      return lang==='az'
        ? `Cari status: «${m[1]}». Bu mərhələ təxminən ${m[2]} dəqiqəyə tamamlanmalıdır.`
        : `Текущий статус: «${m[1]}». Этап должен завершиться примерно за ${m[2]} мин.`;

    if(s==='Overproduction is the biggest source of waste this fortnight')
      return lang==='az'
        ? 'Son iki həftədə tullantının əsas səbəbi artıq istehsaldır'
        : 'Перепроизводство — главный источник списаний за две недели';

    if(s==='Cut prep pars by 15% on the three lowest-selling mains.')
      return lang==='az'
        ? 'Ən az satılan üç əsas yemək üçün hazırlıq normasını 15% azaldın.'
        : 'Снизьте заготовку трёх самых слабых основных блюд на 15%.';

    if((m=s.match(/^Tonight tracks (\d+)% (above|below) a typical (.+)$/))){
      const dir=lang==='az'
        ? (m[2]==='above'?'yuxarı':'aşağı')
        : (m[2]==='above'?'выше':'ниже');

      return lang==='az'
        ? `Bu axşam tipik ${m[3]} göstəricisindən ${m[1]}% ${dir} gedir`
        : `Сегодня прогноз на ${m[1]}% ${dir} обычного уровня (${m[3]})`;
    }

    if(s==='Push the early tasting menu on the door and to the waitlist.')
      return lang==='az'
        ? 'Erkən dequstasiya menyusunu girişdə və gözləmə siyahısında təklif edin.'
        : 'Предлагайте раннее дегустационное меню на входе и гостям из листа ожидания.';

    if((m=s.match(/^Party of (\d+)(.*)$/)))
      return lang==='az'
        ? `${m[1]} nəfərlik qonaq qrupu${m[2]}`
        : `Группа из ${m[1]} гостей${m[2]}`;

    if((m=s.match(/^([\d.]+) units binned before service even started\.$/)))
      return lang==='az'
        ? `Xidmət başlamazdan əvvəl ${m[1]} vahid silinib.`
        : `До начала сервиса списано ${m[1]} ед.`;

    return s;
  }

  function translateDay(s){
    if(lang==='en'||!s)return s;

    const days={
      Monday:['Bazar ertəsi','Понедельник'],
      Tuesday:['Çərşənbə axşamı','Вторник'],
      Wednesday:['Çərşənbə','Среда'],
      Thursday:['Cümə axşamı','Четверг'],
      Friday:['Cümə','Пятница'],
      Saturday:['Şənbə','Суббота'],
      Sunday:['Bazar','Воскресенье']
    };

    const months={
      January:['yanvar','января'],
      February:['fevral','февраля'],
      March:['mart','марта'],
      April:['aprel','апреля'],
      May:['may','мая'],
      June:['iyun','июня'],
      July:['iyul','июля'],
      August:['avqust','августа'],
      September:['sentyabr','сентября'],
      October:['oktyabr','октября'],
      November:['noyabr','ноября'],
      December:['dekabr','декабря']
    };

    let x=s;

    Object.entries(days).forEach(([k,v])=>{
      x=x.replace(k,v[lang==='az'?0:1]);
    });

    Object.entries(months).forEach(([k,v])=>{
      x=x.replace(k,v[lang==='az'?0:1]);
    });

    return x;
  }

  function apply(){
    if(!document.querySelector('#command-lang'))return;

    document.documentElement.lang=lang;

    const me=NOVA.auth.getStaff?.();
    const first=me?.name?.split(' ')[0]||'';
    const h=new Date().getHours();

    set(
      '#command-greeting',
      `${tr(h<12?'morning':h<18?'afternoon':'evening')}${first?', '+first:''}`
    );

    set('#service-progress',tr('progress'));
    set('.foresight h2',tr('next'));

    const fs=$('#foresight-sub');
    if(fs&&fs.textContent.trim()==='Reading the room…'){
      fs.textContent=tr('reading');
    }

    const metrics=$$('.strip .metric');
    const mcopy=[
      ['revenue',null],
      ['covers','mains'],
      ['per','avg'],
      ['occ',null],
      ['duration',null],
      ['sat','seven']
    ];

    metrics.forEach((m,i)=>{
      const c=mcopy[i];
      if(!c)return;

      const l=m.querySelector('label');
      if(l)l.textContent=tr(c[0]);

      if(c[1]){
        const sm=m.querySelector('small');
        if(sm)sm.textContent=tr(c[1]);
      }
    });

    /* Cards are addressed by what they contain, not by their position in the
       grid. Indexing them meant that adding one card to this screen silently
       retitled two others; anything not named here is simply left alone for
       the global translator. */
    const cardOf=(sel)=>{const el=$(sel);return el?el.closest('.card'):null;};

    const decisions=cardOf('#insights');
    if(decisions){
      decisions.querySelector('h3').textContent=tr('decisions');
      decisions.querySelector('p').textContent=tr('ranked');
    }

    const forecast=cardOf('#fc-revenue');
    if(forecast){
      forecast.querySelector('h3').textContent=tr('forecast');
      forecast.querySelector('p').textContent=tr('ridge');
    }

    const revenue=cardOf('#revchart');
    if(revenue){
      const hs=revenue.querySelectorAll('h3');
      const ps=revenue.querySelectorAll('p');
      if(hs[0])hs[0].textContent=tr('revenueDay');
      if(ps[0])ps[0].textContent=tr('everyHour');
      if(hs[1])hs[1].textContent=tr('coversHour');
    }

    const kitchen=cardOf('#stations');
    if(kitchen){
      kitchen.querySelector('h3').textContent=tr('kitchen');
      kitchen.querySelector('p').textContent=tr('kitchenSub');
    }

    const ac=$('#ask')?.closest('.card');

    if(ac){
      ac.querySelector('h3').textContent=tr('ask');
      ac.querySelector(':scope > p').textContent=tr('askSub');
    }

    const ai=$('#ask input');
    if(ai)ai.placeholder=tr('askPh');

    const ab=$('#ask button');
    if(ab)ab.textContent=tr('askBtn');

    const seeds=$$('.seeds button');
    ['seed1','seed2','seed3','seed4','seed5'].forEach((k,i)=>{
      if(seeds[i])seeds[i].textContent=tr(k);
    });

    const groups=$$('.rail .nav-group');

    ['overview','service','product','people','business'].forEach((k,i)=>{
      if(groups[i])groups[i].textContent=tr(k);
    });

    const nm={
      '/admin':'command',
      '/admin/operations':'operations',
      '/admin/floor':'floor',
      '/admin/reservations':'reservations',
      '/admin/orders':'orders',
      '/admin/kitchen':'kitchenNav',
      '/admin/menu':'menu',
      '/admin/inventory':'inventory',
      '/admin/anbar':'anbar',
      '/admin/suppliers':'suppliers',
      '/admin/guests':'guests',
      '/admin/staff':'staff',
      '/admin/analytics':'analytics',
      '/admin/finance':'finance',
      '/admin/copilot':'copilot',
      '/admin/settings':'settings'
    };

    Object.entries(nm).forEach(([href,k])=>{
      nav(document.querySelector(`.rail nav a[href="${href}"]`),tr(k));
    });

    const live=$('.pulse-live');

    if(live){
      live.textContent=tr('live');
      live.insertAdjacentHTML('afterbegin','<i></i>');
    }

    set('#switch-user',tr('switch'));

    const wa=document.querySelector('.rail-foot a[href^="/waiter"]');
    if(wa)wa.textContent=tr('waiter');

    const ga=document.querySelector('.rail-foot a[href^="/guest"]');
    if(ga)ga.textContent=tr('guest');

    $$('#command-lang [data-lang]').forEach(b=>{
      b.classList.toggle('on',b.dataset.lang===lang);
    });

    const day=$('#day');
    if(day)day.textContent=translateDay(day.textContent);

    [
      '#foresight-sub',
      '#m-revenue-sub',
      '#m-occ-sub',
      '#m-dur-sub',
      '#fc-covers',
      '#fc-conf'
    ].forEach(sel=>{
      const e=$(sel);
      if(e)e.textContent=translateDynamic(e.textContent);
    });

    $$(
      '#track .pin b,' +
      '#track .pin span,' +
      '#insights .insight b,' +
      '#insights .insight p,' +
      '#insights .insight .do,' +
      '#stations .station-head span'
    ).forEach(e=>{
      e.textContent=translateDynamic(e.textContent);
    });
  }

  function init(){
    lang=localStorage.getItem('nova-lang')||'en';

    if(!T[lang])lang='en';

    if(!wired){
      wired=true;

      const r=$('#command-lang');

      if(r){
        r.querySelectorAll('[data-lang]').forEach(b=>{
          b.onclick=()=>{
            lang=b.dataset.lang;
            localStorage.setItem('nova-lang',lang);
            location.reload();
          };
        });
      }
    }

    apply();
  }

  function cleanInsights(items){
    return (items||[]).filter(i=>{
      const m=String(i.title||'').match(
        /^Table \d+ waiting (\d+) minutes$/
      );

      return !(m && Number(m[1])>240);
    });
  }

  return {init,apply,cleanInsights};
})();


/* NOVA OPERATIONS V10 ADMIN */
async function bootFloorControl(){const mount=document.querySelector('#floor-control');if(!mount)return;async function refresh(){let d;try{d=await NOVA.api('/api/ops/floor-control')}catch(e){mount.innerHTML=`<p class="sub">${NOVA.esc(e.message)}</p>`;return}mount.innerHTML=`<div class="ops-card-head"><div><h3>Tables & waiter assignments</h3><p>Assignments update the waiter tablet immediately.</p></div><button class="btn solid" id="fc-add">+ Add table</button></div><div class="table-control-grid">${d.tables.map(t=>`<article class="table-control"><div><b>Table ${t.number}</b><span>${t.seats} seats · ${NOVA.esc(t.zone)} · ${NOVA.esc(t.status)}</span></div><select class="field compact-field" data-assign="${t.id}"><option value="">Unassigned</option>${d.waiters.map(w=>`<option value="${w.id}" ${w.id===t.waiter_id?'selected':''}>${NOVA.esc(w.name)}${w.section?' · '+NOVA.esc(w.section):''}</option>`).join('')}</select><button class="btn tiny danger" data-archive="${t.id}">Remove table</button></article>`).join('')}</div>${d.archived.length?`<details class="archived-tables"><summary>Removed tables (${d.archived.length})</summary>${d.archived.map(t=>`<div class="kv"><span>Table ${t.number} · ${t.seats} seats · ${NOVA.esc(t.zone)}</span><button class="btn tiny" data-restore="${t.id}">Bring back</button></div>`).join('')}</details>`:''}`;mount.querySelectorAll('[data-assign]').forEach(x=>x.onchange=async()=>{try{const r=await NOVA.api(`/api/ops/tables/${x.dataset.assign}/assign`,{waiter_id:x.value||null});NOVA.toast(r.message)}catch(e){NOVA.fail(e);refresh()}});mount.querySelectorAll('[data-archive]').forEach(b=>b.onclick=async()=>{if(!confirm('Remove this table from the active floor?'))return;try{const r=await NOVA.api(`/api/ops/tables/${b.dataset.archive}/archive`,{});NOVA.toast(r.message);refresh()}catch(e){NOVA.fail(e)}});mount.querySelectorAll('[data-restore]').forEach(b=>b.onclick=async()=>{try{const r=await NOVA.api(`/api/ops/tables/${b.dataset.restore}/restore`,{});NOVA.toast(r.message);refresh()}catch(e){NOVA.fail(e)}});const add=mount.querySelector('#fc-add');if(add)add.onclick=()=>NOVA.modal('Add table',`<div class="row2"><label class="lbl">Table number<input class="field" id="ft-number" type="number" min="1"></label><label class="lbl">Seats<input class="field" id="ft-seats" type="number" min="1" value="2"></label></div><div class="row2"><label class="lbl">Zone<select class="field" id="ft-zone">${['Main','Terrace','Bar','Private'].map(x=>`<option>${x}</option>`).join('')}</select></label><label class="lbl">Shape<select class="field" id="ft-shape"><option>round</option><option>square</option><option>banquette</option></select></label></div><label class="lbl">Assign waiter<select class="field" id="ft-waiter"><option value="">Unassigned</option>${d.waiters.map(w=>`<option value="${w.id}">${NOVA.esc(w.name)}</option>`).join('')}</select></label><button class="btn solid block" id="ft-save">Add to floor</button><p class="form-error" id="ft-error"></p>`,(body,close)=>{body.querySelector('#ft-save').onclick=async()=>{try{const r=await NOVA.api('/api/ops/tables',{number:+body.querySelector('#ft-number').value,seats:+body.querySelector('#ft-seats').value,zone:body.querySelector('#ft-zone').value,shape:body.querySelector('#ft-shape').value,waiter_id:body.querySelector('#ft-waiter').value||null});close();NOVA.toast(r.message);refresh()}catch(e){body.querySelector('#ft-error').textContent=e.message}}})}await refresh();NOVA.on(()=>refresh().catch(()=>{}))}

async function bootKitchenOps(){
  const mount=document.querySelector('#kitchen-ops');if(!mount)return;
  const ico=(name)=>({change:'↻',ban:'⊘',check:'✓',dish:'◉',ingredient:'◇',clock:'◷'}[name]||'•');
  async function refresh(){
    let d;try{d=await NOVA.api('/api/ops/kitchen-control')}catch(e){mount.innerHTML=`<div class="callout down"><b>Kitchen controls unavailable</b>${NOVA.esc(e.message)}</div>`;return}
    mount.innerHTML=`<section class="k-control-hero"><div><span class="eyebrow">KITCHEN CONTROL</span><h2>Service command board</h2><p>Order changes and unavailable products in one place.</p></div><div class="k-hero-stats"><span><b>${d.changes.length}</b> changes</span><span><b>${d.flags.length}</b> unavailable</span></div></section>
    <div class="kitchen-control-grid">
      <section class="card k-ops-card"><div class="ops-card-head"><div><h3>Order changes</h3><p>Every waiter change remains visible until a chef acknowledges it.</p></div><span class="tag ${d.changes.length?'tight':'star'}">${d.changes.length} open</span></div><div class="k-change-list">${d.changes.length?d.changes.map(c=>`<article class="k-change ${c.kind}"><div class="k-change-icon">${c.kind==='void'?'−':'↻'}</div><div class="k-change-copy"><b>${c.kind==='void'?'REMOVE':'CHANGE'} · Table ${c.table}</b><strong>${NOVA.esc(c.item)}</strong><span>${NOVA.esc(c.reason)} · ${NOVA.esc(c.by)} · ${c.at}</span></div><button class="btn tiny solid" data-ack-change="${c.id}">${ico('check')} Acknowledge</button></article>`).join(''):NOVA.empty('No order changes.','The kitchen is synchronized with the floor.')}</div></section>
      <section class="card k-ops-card"><div class="ops-card-head"><div><h3>Unavailable</h3><p>Block a dish or ingredient once; waiter and guest menus follow automatically.</p></div><button class="btn solid" id="k-flag">${ico('ban')} Mark unavailable</button></div><div class="availability-list">${d.flags.length?d.flags.map(f=>`<article class="availability-row"><div class="availability-icon">${f.kind==='ingredient'?ico('ingredient'):ico('dish')}</div><div><b>${NOVA.esc(f.label)}</b><span>${NOVA.esc(f.kind.replace('_',' '))}${f.note?' · '+NOVA.esc(f.note):''}</span></div><button class="btn tiny" data-restore-flag="${f.id}" data-kind="${f.kind}" data-ref="${f.ref_id}">Back on</button></article>`).join(''):NOVA.empty('Everything available.','No dishes or ingredients are currently blocked.')}</div></section>
    </div>`;
    mount.querySelectorAll('[data-ack-change]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await NOVA.api(`/api/ops/order-changes/${b.dataset.ackChange}/ack`,{});await refresh()}catch(e){NOVA.fail(e);b.disabled=false}});
    mount.querySelectorAll('[data-restore-flag]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await NOVA.api('/api/ops/kitchen/availability',{kind:b.dataset.kind,ref_id:+b.dataset.ref,available:true});NOVA.toast(r.message);await refresh()}catch(e){NOVA.fail(e);b.disabled=false}});
    const flag=mount.querySelector('#k-flag');if(flag)flag.onclick=()=>NOVA.modal('Mark unavailable',`<div class="k-modal-intro"><span>⊘</span><div><b>Take something off sale</b><p>Guests and waiters update immediately.</p></div></div><label class="lbl">Type<select class="field" id="kf-kind"><option value="menu_item">Dish</option><option value="ingredient">Ingredient</option></select></label><label class="lbl">Dish / ingredient<select class="field" id="kf-ref"></select></label><label class="lbl">Reason<input class="field" id="kf-note" placeholder="e.g. sold out, delivery issue"></label><button class="btn solid block" id="kf-save">Mark unavailable now</button><p class="form-error" id="kf-error"></p>`,(body,close)=>{const kind=body.querySelector('#kf-kind'),ref=body.querySelector('#kf-ref'),save=body.querySelector('#kf-save');const draw=()=>{const rows=kind.value==='menu_item'?d.menu_items:d.ingredients;ref.innerHTML=rows.length?rows.map(x=>`<option value="${x.id}">${NOVA.esc(x.name)}</option>`).join(''):'<option value="">Nothing available to select</option>';save.disabled=!rows.length};kind.onchange=draw;draw();save.onclick=async()=>{save.disabled=true;const err=body.querySelector('#kf-error');err.textContent='';try{const r=await NOVA.api('/api/ops/kitchen/availability',{kind:kind.value,ref_id:+ref.value,available:false,note:body.querySelector('#kf-note').value});close();NOVA.toast(r.message);await refresh()}catch(e){err.textContent=e.message;save.disabled=false}}});
    if(window.NOVAI18N)NOVAI18N.apply(mount);
  }
  await refresh();NOVA.on(()=>refresh().catch(()=>{}));
}

async function bootMenuOps(){
  const mount=document.querySelector('#menu-ops');
  if(!mount)return;

  async function refresh(){
    let d;
    try{ d=await NOVA.api('/api/ops/menu-management'); }
    catch(e){ mount.innerHTML=`<p class="sub">${NOVA.esc(e.message)}</p>`; return; }

    mount.innerHTML=`
      <div class="ops-card-head">
        <div><h3>Menu structure</h3><p>Add sections such as Business Lunch or Set Menu, add dishes, or restore removed dishes.</p></div>
        <div class="btn-row"><button class="btn" id="mo-section">+ Section</button><button class="btn solid" id="mo-dish">+ Dish</button></div>
      </div>
      <div class="menu-section-chips">${d.sections.map(x=>`<button class="chip" data-section-edit="${x.id}" data-name="${NOVA.esc(x.name)}" data-name-az="${NOVA.esc(x.name_az||'')}" data-name-ru="${NOVA.esc(x.name_ru||'')}">${NOVA.esc(x.name)}</button>`).join('')}</div>
      <details class="menu-active-manage"><summary>Manage active dishes (${d.items.length})</summary>${d.items.map(x=>`<div class="kv"><span><b>${NOVA.esc(x.name)}</b><div class="micro">${NOVA.esc(x.course)} · ${CUR}${Number(x.price).toFixed(2)}</div></span><button class="btn tiny danger" data-menu-remove="${x.id}">Remove</button></div>`).join('')}</details>
      ${d.archived.length?`<details><summary>Removed dishes (${d.archived.length})</summary>${d.archived.map(x=>`<div class="kv"><span>${NOVA.esc(x.name)} · ${NOVA.esc(x.course)}</span><button class="btn tiny" data-menu-restore="${x.id}">Restore</button></div>`).join('')}</details>`:''}`;

    mount.querySelector('#mo-section').onclick=()=>NOVA.modal(
      'Add menu section',
      `<label class="lbl">Section name · English<input class="field" id="ms-name" placeholder="Business Lunch"></label>
       <div class="row2"><label class="lbl">Name · Azerbaijani<input class="field" id="ms-name-az"></label><label class="lbl">Name · Russian<input class="field" id="ms-name-ru"></label></div>
       <button class="btn ghost block" id="ms-translate">Translate EN → AZ + RU</button>
       <p class="micro">Until translated, guests see the English name on this section. Every dish inside it still shows on the guest menu and in SUFRA 360 either way.</p>
       <button class="btn solid block" id="ms-save">Add section</button><p class="form-error" id="ms-error"></p>`,
      (body,close)=>{
        body.querySelector('#ms-translate').onclick=async()=>{
          const btn=body.querySelector('#ms-translate');btn.disabled=true;btn.textContent='Translating…';
          const text=body.querySelector('#ms-name').value.trim();
          if(!text){btn.disabled=false;btn.textContent='Translate EN → AZ + RU';return;}
          let ok=0,failed=0;
          for(const [dst,target] of [['#ms-name-az','az'],['#ms-name-ru','ru']]){
            try{const r=await NOVA.api('/api/i18n/translate',{text,target});if(r.translated){body.querySelector(dst).value=r.text;ok++}else{failed++}}
            catch{failed++}
          }
          btn.disabled=false;btn.textContent='Translate EN → AZ + RU';
          NOVA.toast(failed?`${ok} of 2 translated — fill the rest by hand.`:'Translated. Review before saving.',failed&&!ok?'bad':'');
        };
        body.querySelector('#ms-save').onclick=async()=>{
          try{
            const r=await NOVA.api('/api/ops/menu/sections',{name:body.querySelector('#ms-name').value,
              name_az:body.querySelector('#ms-name-az').value,name_ru:body.querySelector('#ms-name-ru').value});
            close(); NOVA.toast(r.message); refresh();
          }catch(e){ body.querySelector('#ms-error').textContent=e.message; }
        };
      }
    );

    mount.querySelector('#mo-dish').onclick=()=>NOVA.modal(
      'Add dish',
      `<div class="menu-add-photo"><div class="menu-photo-preview" id="mi-preview"><img src="/static/img/dish-placeholder.svg" alt="Default food image"></div><div><input id="mi-image-url" type="hidden" value=""><label class="btn file-btn">Add food photo<input id="mi-image-file" type="file" accept="image/png,image/jpeg,image/webp" hidden></label><p class="micro" id="mi-photo-source">Optional. If you do not upload a photo, SUFRA uses the default food image.</p></div></div>
       <label class="lbl">Dish name · English<input class="field" id="mi-name"></label>
       <div class="row2"><label class="lbl">Name · Azerbaijani<input class="field" id="mi-name-az"></label><label class="lbl">Name · Russian<input class="field" id="mi-name-ru"></label></div>
       <div class="row2"><label class="lbl">Section<select class="field" id="mi-course">${d.sections.map(x=>`<option>${NOVA.esc(x.name)}</option>`).join('')}</select></label><label class="lbl">Station<select class="field" id="mi-station">${['hot','cold','grill','pastry','bar'].map(x=>`<option>${x}</option>`).join('')}</select></label></div>
       <div class="row2"><label class="lbl">Price<input class="field" id="mi-price" type="number" step="0.5"></label><label class="lbl">Food cost<input class="field" id="mi-cost" type="number" step="0.1"></label></div>
       <label class="lbl">Prep minutes<input class="field" id="mi-min" type="number" value="10"></label>
       <label class="lbl">Description · English<textarea class="field" id="mi-blurb" rows="3"></textarea></label>
       <div class="row2"><label class="lbl">Description · Azerbaijani<textarea class="field" id="mi-blurb-az" rows="3"></textarea></label><label class="lbl">Description · Russian<textarea class="field" id="mi-blurb-ru" rows="3"></textarea></label></div>
       <button class="btn ghost block" id="mi-translate">Translate EN → AZ + RU</button>
       <label class="lbl">Tags / allergens<input class="field" id="mi-tags" placeholder="vegan,gf,dairy"></label>
       <button class="btn solid block" id="mi-save">Add dish</button><p class="form-error" id="mi-error"></p>`,
      (body,close)=>{
        let fileData='';const file=body.querySelector('#mi-image-file'),url=body.querySelector('#mi-image-url'),preview=body.querySelector('#mi-preview');
        const previewUrl=u=>{preview.innerHTML=u?`<img src="${NOVA.esc(u)}" alt="Preview">`:'<span>Photo</span>'};url.oninput=()=>previewUrl(url.value);
        file.onchange=()=>{const f=file.files&&file.files[0];if(!f)return;const rd=new FileReader();rd.onload=()=>{fileData=rd.result;previewUrl(fileData)};rd.readAsDataURL(f)};
        const translateDishFields=async({silent=false,onlyMissing=false}={})=>{
          const translateBtn=body.querySelector('#mi-translate');
          const pairs=[
            ['#mi-name','#mi-name-az','az','Azerbaijani dish name'],
            ['#mi-name','#mi-name-ru','ru','Russian dish name'],
            ['#mi-blurb','#mi-blurb-az','az','Azerbaijani description'],
            ['#mi-blurb','#mi-blurb-ru','ru','Russian description']
          ];

          let ok=0;
          const failed=[];

          if(translateBtn){
            translateBtn.disabled=true;
            translateBtn.textContent='Translating…';
          }

          for(const [src,dst,target,label] of pairs){
            const sourceEl=body.querySelector(src);
            const destEl=body.querySelector(dst);

            const text=(sourceEl?.value||'').trim();

            if(!text)continue;

            if(onlyMissing && (destEl?.value||'').trim()){
              continue;
            }

            let translated=false;

            /* Retry because free public services occasionally rate-limit
               the first request while the second succeeds. */
            for(let attempt=0;attempt<3&&!translated;attempt++){
              try{
                const r=await NOVA.api('/api/i18n/translate',{
                  text,
                  target,
                  source:'en'
                });

                if(
                  r &&
                  r.translated &&
                  typeof r.text==='string' &&
                  r.text.trim() &&
                  r.text.trim().toLowerCase()!==text.toLowerCase()
                ){
                  destEl.value=r.text.trim();
                  translated=true;
                  ok++;
                }
              }catch(e){}

              if(!translated && attempt<2){
                await new Promise(resolve=>
                  setTimeout(resolve,500*(attempt+1))
                );
              }
            }

            if(!translated){
              failed.push(label);
            }
          }

          if(translateBtn){
            translateBtn.disabled=false;
            translateBtn.textContent='Translate EN → AZ + RU';
          }

          if(!silent){
            if(!failed.length){
              NOVA.toast(
                'Azerbaijani and Russian translations are ready. Review before saving.',
                'good'
              );
            }else{
              NOVA.toast(
                `Could not translate: ${failed.join(', ')}. Please retry before saving.`,
                'bad'
              );
            }
          }

          return {
            ok,
            failed,
            complete:failed.length===0
          };
        };

        body.querySelector('#mi-translate').onclick=async()=>{
          await translateDishFields({
            silent:false,
            onlyMissing:false
          });
        };
        body.querySelector('#mi-save').onclick=async()=>{
          const save=body.querySelector('#mi-save');
          const err=body.querySelector('#mi-error');

          err.textContent='';

          const name=body.querySelector('#mi-name').value.trim();
          const blurb=body.querySelector('#mi-blurb').value.trim();

          if(!name){
            err.textContent='Enter the English dish name first.';
            return;
          }

          save.disabled=true;
          save.textContent='Preparing translations…';

          try{
            /*
             * A new dish must carry AZ + RU localized copy.
             * Fill any missing translations automatically before save.
             */
            const result=await translateDishFields({
              silent:true,
              onlyMissing:true
            });

            const nameAz=body.querySelector('#mi-name-az').value.trim();
            const nameRu=body.querySelector('#mi-name-ru').value.trim();
            const blurbAz=body.querySelector('#mi-blurb-az').value.trim();
            const blurbRu=body.querySelector('#mi-blurb-ru').value.trim();

            const missing=[];

            if(!nameAz)missing.push('Azerbaijani name');
            if(!nameRu)missing.push('Russian name');

            if(blurb){
              if(!blurbAz)missing.push('Azerbaijani description');
              if(!blurbRu)missing.push('Russian description');
            }

            /*
             * Never silently save English as an AZ/RU translation.
             * This is the important safety change.
             */
            if(missing.length){
              err.textContent=
                'Translation could not finish for: '+
                missing.join(', ')+
                '. Press Translate again or enter those fields manually.';

              NOVA.toast(
                'Dish was not saved because its translations are incomplete.',
                'bad'
              );

              save.disabled=false;
              save.textContent='Add dish';
              return;
            }

            save.textContent='Adding dish…';

            const r=await NOVA.api('/api/ops/menu/items',{
              name,
              name_az:nameAz,
              name_ru:nameRu,
              course:body.querySelector('#mi-course').value,
              station:body.querySelector('#mi-station').value,
              price:+body.querySelector('#mi-price').value,
              food_cost:+body.querySelector('#mi-cost').value,
              base_minutes:+body.querySelector('#mi-min').value,
              blurb,
              blurb_az:blurbAz,
              blurb_ru:blurbRu,
              tags:body.querySelector('#mi-tags').value,
              image_url:url.value
            });

            close();

            NOVA.toast(
              r.message||'Dish added with Azerbaijani and Russian translations.',
              'good'
            );

            if(fileData){
              try{
                await NOVA.api(
                  `/api/ops/menu/items/${r.id}/image`,
                  {data_url:fileData}
                );
              }catch(photoErr){
                NOVA.toast(
                  'Dish was added, but the uploaded photo could not be saved.',
                  'bad'
                );
              }
            }

            refresh().catch(()=>{});

          }catch(e){
            err.textContent=e.message||'Dish could not be saved.';
            save.disabled=false;
            save.textContent='Add dish';
          }
        };
      }
    );

    mount.querySelectorAll('[data-menu-remove]').forEach(b=>{
      b.onclick=async()=>{
        if(!confirm('Remove this dish from active menus?'))return;
        try{ const r=await NOVA.api(`/api/ops/menu/items/${b.dataset.menuRemove}`,null,'DELETE'); NOVA.toast(r.message); location.reload(); }
        catch(e){ NOVA.fail(e); }
      };
    });

    mount.querySelectorAll('[data-menu-restore]').forEach(b=>{
      b.onclick=async()=>{
        try{ const r=await NOVA.api(`/api/ops/menu/items/${b.dataset.menuRestore}/restore`,{}); NOVA.toast(r.message); location.reload(); }
        catch(e){ NOVA.fail(e); }
      };
    });

    mount.querySelectorAll('[data-section-edit]').forEach(b=>{
      b.onclick=()=>NOVA.modal(
        'Edit section',
        `<label class="lbl">Section name · English<input class="field" id="mse-name" value="${NOVA.esc(b.dataset.name)}"></label>
         <div class="row2"><label class="lbl">Name · Azerbaijani<input class="field" id="mse-name-az" value="${NOVA.esc(b.dataset.nameAz||'')}"></label><label class="lbl">Name · Russian<input class="field" id="mse-name-ru" value="${NOVA.esc(b.dataset.nameRu||'')}"></label></div>
         <button class="btn ghost block" id="mse-translate">Translate EN → AZ + RU</button>
         <div class="btn-row"><button class="btn solid" id="mse-save">Save</button><button class="btn danger" id="mse-delete">Delete empty section</button></div><p class="form-error" id="mse-error"></p>`,
        (body,close)=>{
          body.querySelector('#mse-translate').onclick=async()=>{
            const btn=body.querySelector('#mse-translate');btn.disabled=true;btn.textContent='Translating…';
            const text=body.querySelector('#mse-name').value.trim();
            let ok=0,failed=0;
            for(const [dst,target] of [['#mse-name-az','az'],['#mse-name-ru','ru']]){
              try{const r=await NOVA.api('/api/i18n/translate',{text,target});if(r.translated){body.querySelector(dst).value=r.text;ok++}else{failed++}}
              catch{failed++}
            }
            btn.disabled=false;btn.textContent='Translate EN → AZ + RU';
            NOVA.toast(failed?`${ok} of 2 translated — fill the rest by hand.`:'Translated. Review before saving.',failed&&!ok?'bad':'');
          };
          body.querySelector('#mse-save').onclick=async()=>{
            try{ await NOVA.api(`/api/ops/menu/sections/${b.dataset.sectionEdit}`,{name:body.querySelector('#mse-name').value,
              name_az:body.querySelector('#mse-name-az').value,name_ru:body.querySelector('#mse-name-ru').value}); close(); location.reload(); }
            catch(e){ body.querySelector('#mse-error').textContent=e.message; }
          };
          body.querySelector('#mse-delete').onclick=async()=>{
            try{ await NOVA.api(`/api/ops/menu/sections/${b.dataset.sectionEdit}/delete`,{}); close(); location.reload(); }
            catch(e){ body.querySelector('#mse-error').textContent=e.message; }
          };
        }
      );
    });
  }

  await refresh();
  NOVA.on(()=>refresh().catch(()=>{}));
}

async function bootComplaints(){const mount=document.querySelector('#ops-complaints');if(!mount)return;async function refresh(){let d;try{d=await NOVA.api('/api/ops/complaints')}catch(e){mount.innerHTML='';return}mount.innerHTML=d.complaints.filter(x=>x.status==='open').length?d.complaints.filter(x=>x.status==='open').map(c=>`<article class="complaint-row ${c.severity}"><div><b>Table ${c.table} · ${NOVA.esc(c.category)}</b><strong>${NOVA.esc(c.message)}</strong><span>${NOVA.esc(c.source)} · ${NOVA.esc(c.by)} · ${c.at}</span></div><button class="btn tiny solid" data-resolve-complaint="${c.id}">Resolve</button></article>`).join(''):NOVA.empty('No open complaints.','Guest and waiter complaints will appear here immediately.');mount.querySelectorAll('[data-resolve-complaint]').forEach(b=>b.onclick=async()=>{try{await NOVA.api(`/api/ops/complaints/${b.dataset.resolveComplaint}/resolve`,{});refresh()}catch(e){NOVA.fail(e)}})}await refresh();NOVA.on(()=>refresh().catch(()=>{}))}
