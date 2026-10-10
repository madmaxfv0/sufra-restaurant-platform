/* ============================================================
   SUFRA ANBAR — warehouse, procurement and food-cost UI.

   One boot function, twelve panels, one fetch per panel. Everything
   renders from what the API actually returned: when a figure is null
   because this role may not see costs, the cell says so rather than
   printing a zero that looks like real data.
   ============================================================ */

(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = s => NOVA.esc(String(s ?? ''));
  const money = n => (n === null || n === undefined) ? '—' : NOVA.money2(n);
  const num = (n, dp = 2) => (n === null || n === undefined)
    ? '—' : Number(n).toLocaleString('en-GB', { maximumFractionDigits: dp });

  const STATUS_LABEL = {
    healthy: 'Healthy', low: 'Low', critical: 'Critical', out: 'Out of stock',
    over: 'Over-stocked', expiring: 'Expiring soon', expired: 'Expired',
    quarantined: 'Quarantined',
  };
  const STATUS_COLOUR = {
    healthy: 'var(--mint)', low: 'var(--amber)', critical: 'var(--coral)',
    out: 'var(--coral)', over: 'var(--violet)', expiring: 'var(--amber)',
    expired: 'var(--coral)',
  };
  const TXN_LABEL = {
    PURCHASE_RECEIPT: 'Delivery received', SALE_CONSUMPTION: 'Sold',
    WASTE: 'Waste', TRANSFER_IN: 'Transfer in', TRANSFER_OUT: 'Transfer out',
    STOCKTAKE_ADJUSTMENT: 'Stocktake', MANUAL_ADJUSTMENT: 'Manual adjustment',
    RETURN_TO_SUPPLIER: 'Returned to supplier', RETURN_TO_STOCK: 'Returned to stock',
    OPENING_BALANCE: 'Opening balance',
  };
  const WASTE_LABEL = {
    spoilage: 'Spoilage', expired: 'Expired', prep: 'Preparation waste',
    overproduction: 'Overproduction', returned: 'Returned dish', damaged: 'Damaged',
    incorrect_prep: 'Incorrect preparation', staff_meal: 'Staff meal',
    quality_reject: 'Quality rejection', other: 'Other',
  };

  const state = { tab: 'overview', reference: null, cache: {} };

  // Two translation engines are loaded: nova-core's NOVAI18N and the larger
  // static dictionary in sufra-final-i18n.js, which exports itself as
  // SUFRA_FINAL_I18N. The second one carries the Anbar vocabulary and its
  // MutationObserver debounces, which can drop a whole panel swapped in as
  // one innerHTML write — so re-apply both explicitly after every render.
  /* The daily brief is composed on the server from live figures, so it
     cannot go through the static dictionary. The server sends a template
     key plus its parameters alongside the English sentence; these render
     the same facts in the reader's own language. Anything without a key
     (an anomaly title, which is already a full sentence) falls back to the
     English the server built. */
  const lang = () => {
    try {
      return localStorage.getItem('nova-lang') ||
             localStorage.getItem('nova-command-lang') || 'en';
    } catch { return 'en'; }
  };

  const BRIEF = {
    headline: {
      all_clear: [null,
        'Anbar qaydasındadır. Hazırda diqqət tələb edən heç nə yoxdur.',
        'Склад в порядке. Сейчас ничего не требует внимания.'],
      healthy: [null, 'Anbar qaydasındadır.', 'Склад в порядке.'],
      needs_attention: [null,
        p => `Anbar ümumilikdə qaydasındadır. ${p.n} mal diqqət tələb edir.`,
        p => `Склад в целом в порядке. ${p.n} позиций требуют внимания.`],
    },
    point: {
      short_vs_demand: [null,
        p => `${p.name} sabahkı tələbatı ödəməyə bilər — anbarda ${p.stock} ${p.unit}, `
           + `gözlənilən tələbat ${p.required} ${p.unit}.`,
        p => `${p.name} может не покрыть завтрашний спрос — на складе ${p.stock} ${p.unit}, `
           + `ожидаемый расход ${p.required} ${p.unit}.`],
      out_of_stock: [null,
        p => `${p.name} bitib (${p.stock} ${p.unit}).`,
        p => `${p.name} закончился (${p.stock} ${p.unit}).`],
      below_minimum: [null,
        p => `${p.name} minimum ehtiyatdan aşağıdır (${p.stock} ${p.unit}).`,
        p => `${p.name} ниже минимального запаса (${p.stock} ${p.unit}).`],
      expiring_soon: [null,
        p => `${p.count} malın vaxtı 72 saat ərzində bitir, bunun ₼${p.value}-i `
           + `gözlənilən istifadədən artıqdır.`,
        p => `У ${p.count} позиций срок истекает в течение 72 часов, из них на ₼${p.value} `
           + `сверх ожидаемого расхода.`],
      price_up: [null,
        p => `${p.name} alış qiyməti ${p.pct}% artaraq ${p.unit} başına ₼${p.price} olub.`,
        p => `Закупочная цена «${p.name}» выросла на ${p.pct}% до ₼${p.price} за ${p.unit}.`],
      tomorrow_book: [null,
        p => `Sabah üçün ${p.reservations} rezervasiya var (${p.booked} nəfər rezerv edilib, `
           + `gəlişlərlə birlikdə ${p.expected} gözlənilir).`,
        p => `На завтра ${p.reservations} броней (${p.booked} гостей забронировано, `
           + `с учётом проходящих ожидается ${p.expected}).`],
      approvals_waiting: [null,
        p => `${p.count} satınalma sifarişi təsdiq gözləyir (₼${p.value}).`,
        p => `${p.count} заказ(ов) на закупку ожидают утверждения (₼${p.value}).`],
    },
  };

  function briefText(entry, fallback, table) {
    const l = lang();
    if (l === 'en' || !entry || !entry.key) return fallback;
    const row = table[entry.key];
    if (!row) return fallback;
    const slot = row[l === 'az' ? 1 : 2];
    if (!slot) return fallback;
    try {
      return typeof slot === 'function' ? slot(entry.params || {}) : slot;
    } catch { return fallback; }
  }

  const briefHeadline = b => briefText(
    { key: b.headline_key, params: { n: b.attention } }, b.headline, BRIEF.headline);
  const briefPoint = p => briefText(p, p.text, BRIEF.point);

  function applyI18n(root) {
    // Restore the English source first. The shared layer translates text
    // nodes in place and only maps English -> target, so translating an
    // already-translated tab is a no-op and the label would be stuck in
    // whichever language was picked first.
    document.querySelectorAll('.anbar-tab[data-en]').forEach(b => {
      b.textContent = b.dataset.en;
    });
    try { if (window.SUFRA_FINAL_I18N) window.SUFRA_FINAL_I18N.apply(root || document.body); } catch { /* never block a render */ }
    try { if (window.NOVAI18N) window.NOVAI18N.apply(root || document.body); } catch { /* ditto */ }
  }

  /* ---------------------------------------------------------- shells */

  function panel(html) { $('#anbar-panel').innerHTML = html; }
  function loading() { panel('<div class="anbar-loading">Loading…</div>'); }

  function emptyState(title, body, actionLabel, onAction) {
    const id = 'empty-' + Math.random().toString(36).slice(2, 8);
    setTimeout(() => {
      const btn = document.getElementById(id);
      if (btn && onAction) btn.onclick = onAction;
    }, 0);
    return `<div class="anbar-empty"><b>${esc(title)}</b><p>${esc(body)}</p>
      ${actionLabel ? `<button class="btn solid" id="${id}">${esc(actionLabel)}</button>` : ''}</div>`;
  }

  function card(key, value, sub, tone) {
    return `<div class="anbar-card ${tone || ''}">
      <span class="k">${esc(key)}</span>
      <span class="v">${value}</span>
      ${sub ? `<span class="s">${esc(sub)}</span>` : ''}</div>`;
  }

  function chip(status, label) {
    return `<span class="chip ${esc(status)}">${esc(label || STATUS_LABEL[status] || status)}</span>`;
  }

  function table(head, rows, opts = {}) {
    if (!rows.length) return `<div class="anbar-empty"><p>${esc(opts.empty || 'Nothing to show yet.')}</p></div>`;
    return `<div class="anbar-table-wrap"><table class="anbar-table ${opts.stack ? 'stack-mobile' : ''}">
      <thead><tr>${head.map(h => `<th class="${h.num ? 'num' : ''}">${esc(h.label)}</th>`).join('')}</tr></thead>
      <tbody>${rows.join('')}</tbody></table></div>`;
  }

  function bars(rows, max) {
    const top = max || Math.max(...rows.map(r => Math.abs(r.value)), 1);
    return `<div class="anbar-bars">${rows.map(r => `
      <div class="anbar-bar-row">
        <div class="anbar-bar-label"><span>${esc(r.name)}</span><span>${r.display}</span></div>
        <div class="anbar-bar-track">
          <div class="anbar-bar-fill ${r.tone || ''}" style="width:${Math.min(100, 100 * Math.abs(r.value) / top)}%"></div>
        </div>
      </div>`).join('')}</div>`;
  }

  function explain(reasons) {
    if (!reasons || !reasons.length) return '';
    return `<details class="anbar-explain"><summary></summary>
      <div class="anbar-why"><ul>${reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul></div>
    </details>`;
  }

  async function send(url, body, method) {
    try {
      const res = await NOVA.api(url, body, method);
      if (res && res.message) NOVA.toast(res.message);
      return res;
    } catch (e) {
      NOVA.toast(e.message || 'That did not work.', 'bad');
      return null;
    }
  }

  function closeDrawer() {
    const d = $('#anbar-drawer');
    if (d) { d.hidden = true; d.querySelector('.anbar-drawer-inner').innerHTML = ''; }
  }

  function openDrawer(html) {
    const d = $('#anbar-drawer');
    d.querySelector('.anbar-drawer-inner').innerHTML = html;
    d.hidden = false;
    const close = d.querySelector('[data-close]');
    if (close) close.onclick = closeDrawer;
    applyI18n(d);
  }

  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

  /* ---------------------------------------------------------- 1. OVERVIEW */

  async function renderOverview() {
    loading();
    const d = await NOVA.api('/api/anbar/overview');
    const c = d.cards;
    const money$ = d.can_see_costs;

    const cards = [
      money$ ? card('Inventory value', money(c.inventory_value), `${c.active_items} active lines`) : null,
      money$ ? card('Food cost', c.food_cost_pct === null ? '—' : c.food_cost_pct + '%',
        'menu average', (c.food_cost_pct || 0) >= 35 ? 'warn' : 'good') : null,
      card('Low stock', c.low_stock, 'at or under reorder point', c.low_stock ? 'warn' : ''),
      card('Critical', c.critical_stock, 'below minimum', c.critical_stock ? 'crit' : ''),
      card('Out of stock', c.out_of_stock, 'nothing on the shelf', c.out_of_stock ? 'crit' : ''),
      card('Expiring soon', c.expiring_soon,
        money$ ? money(c.expiry_value_at_risk) + ' beyond expected use' : 'within 72 hours',
        c.expiring_soon ? 'warn' : ''),
      money$ ? card('Waste today', money(c.waste_today), `${money(c.waste_week)} this week`,
        (c.waste_today || 0) > 0 ? 'warn' : '') : null,
      money$ ? card('Purchases', money(c.purchases_month), 'this month') : null,
      card('Pending orders', c.pending_orders, 'awaiting approval', c.pending_orders ? 'warn' : ''),
      card('Deliveries due', c.expected_deliveries, 'expected in'),
      money$ ? card('Variance', money(c.variance_value), 'physical vs ledger',
        Math.abs(c.variance_value || 0) > 25 ? 'warn' : '') : null,
      card('Open alerts', c.open_alerts, 'need review', c.open_alerts ? 'warn' : ''),
    ].filter(Boolean).join('');

    const brief = d.brief;
    const briefHtml = `<div class="anbar-brief">
      <div class="anbar-brief-head"><i></i>SUFRA AI daily brief</div>
      <h3>${esc(briefHeadline(brief))}</h3>
      ${brief.points.length ? `<ul>${brief.points.map(p =>
        `<li class="${esc(p.severity)}"><i></i><span>${esc(briefPoint(p))}</span></li>`).join('')}</ul>` : ''}
      <div class="conf">Forecast confidence: ${esc(brief.confidence)} · generated ${esc(brief.generated_at.replace('T', ' '))}</div>
    </div>`;

    const totalHealth = d.stock_health.reduce((a, r) => a + r.count, 0) || 1;
    const healthHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Stock health</h3>
        <p>Every active line, by where it sits against its own thresholds.</p></div></div>
      <div class="anbar-health">${d.stock_health.map(r =>
        `<i style="width:${100 * r.count / totalHealth}%;background:${STATUS_COLOUR[r.status] || 'var(--sage)'}"
            title="${esc(STATUS_LABEL[r.status] || r.status)}: ${r.count}"></i>`).join('')}</div>
      <div class="anbar-health-key">${d.stock_health.map(r =>
        `<span><i style="background:${STATUS_COLOUR[r.status] || 'var(--sage)'}"></i>
         ${esc(STATUS_LABEL[r.status] || r.status)} ${r.count}</span>`).join('')}</div>
    </div>`;

    const catHtml = money$ && d.value_by_category.length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Value by category</h3>
        <p>Where the capital on the shelves actually sits.</p></div></div>
      ${bars(d.value_by_category.map(r => ({ name: r.name, value: r.value, display: money(r.value) })))}
    </div>` : '';

    const seriesHtml = money$ && d.series.length > 1 ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Purchases vs consumption</h3>
        <p>Value received against value sold through recipes, last 30 days.</p></div></div>
      <div class="anbar-spark">${(() => {
        const max = Math.max(...d.series.map(r => Math.max(r.received, r.consumed)), 1);
        return d.series.map(r => `<i style="height:${Math.max(3, 100 * r.consumed / max)}%"
          title="${esc(r.day)} — sold ${money(r.consumed)}, received ${money(r.received)}"></i>`).join('');
      })()}</div>
      <p class="anbar-count" style="margin-top:10px">Sold ${money(c.consumed_30d)} ·
        received ${money(c.received_30d)} over 30 days</p>
    </div>` : '';

    const criticalHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Critical items</h3>
        <p>What runs out first if nobody acts.</p></div></div>
      ${table([{ label: 'Item' }, { label: 'Status' }, { label: 'On hand', num: true },
               { label: 'Reorder at', num: true }, { label: 'Supplier' }],
        d.critical.map(r => `<tr class="clickable" data-item="${r.id}">
          <td class="primary">${esc(r.name)}</td>
          <td class="trailing">${chip(r.status)}</td>
          <td class="num" data-label="On hand">${num(r.in_stock, 3)} ${esc(r.unit)}</td>
          <td class="num" data-label="Reorder at">${num(r.reorder_point, 3)}</td>
          <td class="muted" data-label="Supplier">${esc(r.supplier || '—')}</td></tr>`),
        { stack: true, empty: 'Nothing is critical. Every line is above its minimum.' })}
    </div>`;

    const alertsHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Alerts</h3>
        <p>Open findings, newest first.</p></div></div>
      ${d.alerts.length ? d.alerts.map(a => `<div class="anbar-alert ${esc(a.severity)}">
        <div class="anbar-alert-body"><b>${esc(a.title)}</b><p>${esc(a.body)}</p></div>
        <time>${esc(a.at)}</time></div>`).join('')
        : '<div class="anbar-empty"><p>No open alerts.</p></div>'}
    </div>`;

    const deliveriesHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Upcoming deliveries</h3>
        <p>Orders approved or sent and not yet received.</p></div></div>
      ${table([{ label: 'Order' }, { label: 'Supplier' }, { label: 'Expected' },
               { label: 'Status' }, { label: 'Value', num: true }],
        d.upcoming_deliveries.map(r => `<tr>
          <td class="primary">${esc(r.code)}</td>
          <td data-label="Supplier">${esc(r.supplier)}</td>
          <td data-label="Expected" class="muted">${esc(r.expected_on || '—')}</td>
          <td class="trailing">${chip('neutral', r.status)}</td>
          <td class="num" data-label="Value">${money(r.total)}</td></tr>`),
        { stack: true, empty: 'Nothing is on its way in.' })}
    </div>`;

    panel(`<div class="anbar-cards">${cards}</div>
      ${briefHtml}
      <div class="anbar-split">${healthHtml}${catHtml || alertsHtml}</div>
      ${catHtml ? `<div class="anbar-split" style="margin-top:16px">${alertsHtml}${seriesHtml}</div>` : ''}
      <div class="anbar-split" style="margin-top:16px">${criticalHtml}${deliveriesHtml}</div>`);

    $('#anbar-panel').querySelectorAll('[data-item]').forEach(tr => {
      tr.onclick = () => openItem(Number(tr.dataset.item));
    });
  }

  /* ---------------------------------------------------------- 2. INVENTORY */

  const invFilters = { q: '', category: 0, location: 0, status: '', supplier: 0, sort: 'status' };

  async function renderInventory() {
    loading();
    const qs = new URLSearchParams(Object.entries(invFilters)
      .filter(([, v]) => v !== '' && v !== 0)).toString();
    const d = await NOVA.api('/api/anbar/items' + (qs ? '?' + qs : ''));
    state.cache.inventory = d;

    const opts = (list, current, blank) =>
      `<option value="">${esc(blank)}</option>` + list.map(o =>
        `<option value="${o.id}" ${String(o.id) === String(current) ? 'selected' : ''}>${esc(o.name)}</option>`).join('');

    const toolbar = `<div class="anbar-toolbar">
      <input type="search" id="inv-q" placeholder="Search by name or SKU…" value="${esc(invFilters.q)}">
      <select id="inv-cat">${opts(d.categories, invFilters.category, 'All categories')}</select>
      <select id="inv-loc">${opts(d.locations, invFilters.location, 'All locations')}</select>
      <select id="inv-status">
        <option value="">All statuses</option>
        ${Object.entries(STATUS_LABEL).map(([k, v]) =>
          `<option value="${k}" ${invFilters.status === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}
      </select>
      <select id="inv-sup">${opts(d.suppliers, invFilters.supplier, 'All suppliers')}</select>
      <select id="inv-sort">
        ${['status', 'name', 'value', 'stock', 'category'].map(k =>
          `<option value="${k}" ${invFilters.sort === k ? 'selected' : ''}>Sort: ${k}</option>`).join('')}
      </select>
      <span class="spacer"></span>
      <span class="anbar-count">${d.count} items${d.total_value !== null ? ' · ' + money(d.total_value) : ''}</span>
      <button class="btn solid" id="inv-new">Add item</button>
    </div>`;

    const rows = d.rows.map(r => `<tr class="clickable" data-item="${r.id}">
      <td class="primary">${esc(r.name)}<br><span class="muted" style="font-size:11px">${esc(r.sku)}${r.category ? ' · ' + esc(r.category) : ''}</span></td>
      <td class="trailing">${chip(r.status)}</td>
      <td class="num" data-label="On hand"><span class="strong">${num(r.in_stock, 3)}</span> ${esc(r.unit)}</td>
      <td class="num" data-label="Reorder">${num(r.reorder_point, 2)}</td>
      <td class="num" data-label="Cost">${money(r.cost)}</td>
      <td class="num" data-label="Value">${money(r.value)}</td>
      <td data-label="Location" class="muted">${esc(r.location || '—')}</td>
      <td data-label="Supplier" class="muted">${esc(r.supplier || '—')}</td>
    </tr>`);

    panel(toolbar + `<div class="card">${
      d.rows.length
        ? table([{ label: 'Item' }, { label: 'Status' }, { label: 'On hand', num: true },
                 { label: 'Reorder', num: true }, { label: 'Cost', num: true },
                 { label: 'Value', num: true }, { label: 'Location' }, { label: 'Supplier' }],
          rows, { stack: true })
        : emptyState('No inventory items match',
            invFilters.q || invFilters.category || invFilters.status
              ? 'Nothing matches those filters. Clear them to see the full list.'
              : 'Anbar has no stock lines yet. Add the first one to start tracking.',
            'Add first item', () => itemForm())
    }</div>`);

    const rerun = () => renderInventory();
    const q = $('#inv-q');
    let t;
    q.oninput = () => { clearTimeout(t); t = setTimeout(() => { invFilters.q = q.value.trim(); rerun(); }, 260); };
    $('#inv-cat').onchange = e => { invFilters.category = Number(e.target.value) || 0; rerun(); };
    $('#inv-loc').onchange = e => { invFilters.location = Number(e.target.value) || 0; rerun(); };
    $('#inv-status').onchange = e => { invFilters.status = e.target.value; rerun(); };
    $('#inv-sup').onchange = e => { invFilters.supplier = Number(e.target.value) || 0; rerun(); };
    $('#inv-sort').onchange = e => { invFilters.sort = e.target.value; rerun(); };
    $('#inv-new').onclick = () => itemForm();
    $('#anbar-panel').querySelectorAll('[data-item]').forEach(tr => {
      tr.onclick = () => openItem(Number(tr.dataset.item));
    });
  }

  function itemForm() {
    const ref = state.cache.inventory || { categories: [], locations: [], suppliers: [], units: [] };
    NOVA.modal('Add inventory item', `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label class="full"><span>Name</span><input id="f-name" maxlength="80" placeholder="Salmon fillet"></label>
        <label><span>SKU</span><input id="f-sku" maxlength="40" placeholder="auto"></label>
        <label><span>Barcode</span><input id="f-barcode" maxlength="40"></label>
        <label><span>Category</span><select id="f-cat">${ref.categories.map(c =>
          `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></label>
        <label><span>Storage location</span><select id="f-loc">${ref.locations.map(l =>
          `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select></label>
        <label><span>Stock unit (base)</span><select id="f-base">${(ref.units || []).map(u =>
          `<option value="${u}">${esc(u)}</option>`).join('')}</select></label>
        <label><span>Purchase unit</span><select id="f-pu">${(ref.units || []).map(u =>
          `<option value="${u}">${esc(u)}</option>`).join('')}</select></label>
        <label><span>Base units per purchase unit</span><input id="f-pf" type="number" step="any" value="1"></label>
        <label><span>Recipe unit</span><select id="f-ru">${(ref.units || []).map(u =>
          `<option value="${u}">${esc(u)}</option>`).join('')}</select></label>
        <label><span>Base units per recipe unit</span><input id="f-rf" type="number" step="any" value="0.001"></label>
        <label><span>Cost per base unit</span><input id="f-cost" type="number" step="any" value="0"></label>
        <label><span>Opening quantity</span><input id="f-open" type="number" step="any" value="0"></label>
        <label><span>Minimum stock</span><input id="f-min" type="number" step="any" value="0"></label>
        <label><span>Reorder point</span><input id="f-reorder" type="number" step="any" value="0"></label>
        <label><span>Target stock</span><input id="f-target" type="number" step="any" value="0"></label>
        <label><span>Maximum stock</span><input id="f-max" type="number" step="any" value="0"></label>
        <label><span>Supplier</span><select id="f-sup"><option value="">—</option>${
          ref.suppliers.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></label>
        <label><span>Shelf life (days)</span><input id="f-shelf" type="number" step="1" value="0"></label>
        <label class="full"><span>Track batches and expiry dates</span>
          <select id="f-batch"><option value="">No</option><option value="1">Yes</option></select></label>
      </div>
      <p class="anbar-note">The unit trio is what stops a recipe in grams from being
        subtracted from a delivery in cases. Base is how stock is held, purchase is how
        the supplier invoices, recipe is what a chef writes on the card.</p>
      <div id="f-err"></div>
      <button class="btn solid block" id="f-save">Add item</button>
    </div>`, (body, close) => {
      $('#f-save', body).onclick = async () => {
        const payload = {
          name: $('#f-name', body).value.trim(),
          sku: $('#f-sku', body).value.trim(),
          barcode: $('#f-barcode', body).value.trim(),
          category_id: $('#f-cat', body).value || null,
          location_id: $('#f-loc', body).value || null,
          base_unit: $('#f-base', body).value,
          purchase_unit: $('#f-pu', body).value,
          purchase_factor: Number($('#f-pf', body).value) || 1,
          recipe_unit: $('#f-ru', body).value,
          recipe_factor: Number($('#f-rf', body).value) || 1,
          cost: Number($('#f-cost', body).value) || 0,
          opening_qty: Number($('#f-open', body).value) || 0,
          min_stock: Number($('#f-min', body).value) || 0,
          reorder_point: Number($('#f-reorder', body).value) || 0,
          target_stock: Number($('#f-target', body).value) || 0,
          max_stock: Number($('#f-max', body).value) || 0,
          supplier_id: $('#f-sup', body).value || null,
          shelf_life_days: Number($('#f-shelf', body).value) || 0,
          track_batches: !!$('#f-batch', body).value,
        };
        if (!payload.name) {
          $('#f-err', body).innerHTML = '<div class="anbar-error">Give the item a name.</div>';
          return;
        }
        const res = await send('/api/anbar/items', payload);
        if (res && res.ok) { close(); renderInventory(); }
      };
    });
  }

  /* ---------------------------------------------------------- item drawer */

  async function openItem(id) {
    openDrawer('<div class="anbar-loading">Loading…</div>');
    const d = await NOVA.api('/api/anbar/items/' + id);
    const it = d.item;
    const v = d.variance;

    const section = (title, inner) => `<section><h4>${esc(title)}</h4>${inner}</section>`;

    openDrawer(`
      <div class="anbar-drawer-head">
        <div>
          <h2>${esc(it.name)}</h2>
          <p>${esc(it.sku || '')}${it.supplier ? ' · ' + esc(it.supplier) : ''}</p>
          <div style="margin-top:10px">${chip(it.status)}</div>
        </div>
        <button class="btn ghost tiny" data-close>Close</button>
      </div>

      <div class="anbar-cards" style="grid-template-columns:repeat(auto-fit,minmax(120px,1fr))">
        ${card('On hand', `${num(it.in_stock, 3)} <span style="font-size:13px;color:var(--sage)">${esc(it.unit)}</span>`)}
        ${d.can_see_costs ? card('Value', money(it.value), money(it.cost) + '/' + it.unit) : ''}
        ${card('Used 7d', num(d.usage.d7, 2) + ' ' + it.unit, num(d.usage.d30, 2) + ' over 30d')}
      </div>

      ${section('Overview', `<dl class="anbar-kv">
        <dt>Reorder point</dt><dd>${num(it.reorder_point, 3)} ${esc(it.unit)}</dd>
        <dt>Minimum stock</dt><dd>${num(it.min_stock, 3)} ${esc(it.unit)}</dd>
        <dt>Target stock</dt><dd>${num(it.target_stock, 3)} ${esc(it.unit)}</dd>
        <dt>Expected tomorrow</dt><dd>${num(d.usage.expected_tomorrow, 3)} ${esc(it.unit)}</dd>
        <dt>Purchase unit</dt><dd>1 ${esc(it.purchase_unit)} = ${num(it.purchase_factor, 4)} ${esc(it.unit)}</dd>
        <dt>Recipe unit</dt><dd>1 ${esc(it.recipe_unit)} = ${num(it.recipe_factor, 5)} ${esc(it.unit)}</dd>
        ${it.expires_on ? `<dt>Expires</dt><dd>${esc(it.expires_on)}</dd>` : ''}
      </dl>`)}

      ${section('Theoretical vs physical', `<dl class="anbar-kv">
        <dt>Ledger says</dt><dd>${num(v.theoretical, 3)} ${esc(it.unit)}</dd>
        <dt>Shelf says</dt><dd>${num(v.physical, 3)} ${esc(it.unit)}</dd>
        <dt>Variance</dt><dd style="color:${Math.abs(v.qty) > 0.001 ? 'var(--coral)' : 'var(--mint)'}">
          ${v.qty > 0 ? '+' : ''}${num(v.qty, 3)} ${esc(it.unit)}${v.value !== null ? ' · ' + money(v.value) : ''}</dd>
      </dl>`)}

      ${d.dishes.length ? section('Used by', table(
        [{ label: 'Dish' }, { label: 'Per portion', num: true }, { label: 'Cost', num: true }],
        d.dishes.map(x => `<tr><td class="primary">${esc(x.name)}</td>
          <td class="num" data-label="Per portion">${num(x.qty, 3)} ${esc(x.unit)}</td>
          <td class="num" data-label="Cost">${money(x.cost_contribution)}</td></tr>`),
        { stack: true })) : ''}

      ${d.batches.length ? section('Batches', table(
        [{ label: 'Batch' }, { label: 'Qty', num: true }, { label: 'Expires' }],
        d.batches.map(b => `<tr><td class="primary">${esc(b.code || '—')}</td>
          <td class="num" data-label="Qty">${num(b.qty, 3)}</td>
          <td class="trailing">${b.expires_on
            ? (b.days_left <= 3 ? chip('expiring', b.expires_on + ' · ' + b.days_left + 'd')
                                : esc(b.expires_on))
            : '—'}</td></tr>`), { stack: true })) : ''}

      ${d.purchases.length ? section('Purchase history', table(
        [{ label: 'Date' }, { label: 'Supplier' }, { label: 'Qty', num: true }, { label: 'Price', num: true }],
        d.purchases.map(p => `<tr><td class="primary">${esc(p.date)}</td>
          <td data-label="Supplier">${esc(p.supplier)}</td>
          <td class="num" data-label="Qty">${num(p.qty, 3)}</td>
          <td class="num" data-label="Price">${money(p.unit_price)}</td></tr>`), { stack: true })) : ''}

      ${d.offers.length ? section('Suppliers', table(
        [{ label: 'Supplier' }, { label: 'Per ' + it.unit, num: true }, { label: 'Lead' }],
        d.offers.map(o => `<tr><td class="primary">${esc(o.supplier)}${o.preferred ? ' ' + chip('good', 'preferred') : ''}</td>
          <td class="num" data-label="Price">${money(o.price_per_base)}</td>
          <td class="trailing muted">${o.lead_time_days}d</td></tr>`), { stack: true })) : ''}

      ${d.waste.length ? section('Waste', table(
        [{ label: 'Date' }, { label: 'Qty', num: true }, { label: 'Reason' }, { label: 'Cost', num: true }],
        d.waste.map(w => `<tr><td class="primary">${esc(w.date)}</td>
          <td class="num" data-label="Qty">${num(w.qty, 3)}</td>
          <td data-label="Reason">${esc(WASTE_LABEL[w.reason] || w.reason)}</td>
          <td class="num" data-label="Cost">${money(w.cost)}</td></tr>`), { stack: true })) : ''}

      ${section('Movement ledger', table(
        [{ label: 'When' }, { label: 'Movement' }, { label: 'Qty', num: true }, { label: 'Balance', num: true }, { label: 'By' }],
        d.ledger.map(t => `<tr><td class="primary">${esc(t.at)}</td>
          <td data-label="Movement">${esc(TXN_LABEL[t.type] || t.type)}</td>
          <td class="num" data-label="Qty" style="color:${t.qty < 0 ? 'var(--coral)' : 'var(--mint)'}">
            ${t.qty > 0 ? '+' : ''}${num(t.qty, 3)}</td>
          <td class="num" data-label="Balance">${num(t.balance, 3)}</td>
          <td class="muted" data-label="By">${esc(t.by)}</td></tr>`),
        { stack: true, empty: 'No movement recorded yet. Stock changes appear here the moment they happen.' }))}

      <div class="btn-row" style="margin-top:20px;display:flex;gap:9px;flex-wrap:wrap">
        <button class="btn solid" id="d-adjust">Adjust stock</button>
        <button class="btn" id="d-waste">Log waste</button>
        <button class="btn ghost" id="d-edit">Edit item</button>
      </div>`);

    $('#d-adjust').onclick = () => adjustForm(it);
    $('#d-waste').onclick = () => wasteForm(it);
    $('#d-edit').onclick = () => editItemForm(it);
  }

  function adjustForm(it) {
    NOVA.modal('Adjust ' + it.name, `<div class="anbar-form">
      <label><span>Adjustment type</span><select id="a-mode">
        <option value="delta">Add or remove a quantity</option>
        <option value="set">Set the on-hand figure</option>
      </select></label>
      <label><span>Quantity (${esc(it.unit)})</span><input id="a-qty" type="number" step="any" placeholder="-1.5"></label>
      <label><span>Reason</span><select id="a-reason">
        <option value="count correction">Count correction</option>
        <option value="damage">Damage</option>
        <option value="found stock">Found stock</option>
        <option value="data entry error">Data entry error</option>
        <option value="supplier return">Supplier return</option>
        <option value="other">Other</option>
      </select></label>
      <label><span>Comment</span><textarea id="a-note" rows="2" maxlength="200"></textarea></label>
      <p class="anbar-note">Adjustments never overwrite history. This writes a signed
        ledger entry against your name, which is what makes the variance report meaningful.</p>
      <div id="a-err"></div>
      <button class="btn solid block" id="a-save">Apply adjustment</button>
    </div>`, (body, close) => {
      $('#a-save', body).onclick = async () => {
        const qty = Number($('#a-qty', body).value);
        if (!qty && qty !== 0) {
          $('#a-err', body).innerHTML = '<div class="anbar-error">Enter a quantity.</div>';
          return;
        }
        const res = await send(`/api/anbar/items/${it.id}/adjust`, {
          qty, mode: $('#a-mode', body).value, unit: it.unit,
          reason: $('#a-reason', body).value, note: $('#a-note', body).value.trim(),
        });
        if (res && res.ok) { close(); openItem(it.id); }
      };
    });
  }

  function wasteForm(it) {
    NOVA.modal('Log waste — ' + it.name, `<div class="anbar-form">
      <label><span>Quantity (${esc(it.unit)})</span><input id="w-qty" type="number" step="any"></label>
      <label><span>Reason</span><select id="w-reason">${Object.entries(WASTE_LABEL).map(([k, v]) =>
        `<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
      <label><span>Comment</span><textarea id="w-note" rows="2" maxlength="200"></textarea></label>
      <div id="w-err"></div>
      <button class="btn solid block" id="w-save">Record waste</button>
    </div>`, (body, close) => {
      $('#w-save', body).onclick = async () => {
        const qty = Number($('#w-qty', body).value);
        if (!(qty > 0)) {
          $('#w-err', body).innerHTML = '<div class="anbar-error">Enter a quantity above zero.</div>';
          return;
        }
        const res = await send('/api/anbar/waste', {
          ingredient_id: it.id, qty, unit: it.unit,
          reason: $('#w-reason', body).value, note: $('#w-note', body).value.trim(),
        });
        if (res && res.ok) { close(); openItem(it.id); }
      };
    });
  }

  function editItemForm(it) {
    const ref = state.cache.inventory || { categories: [], locations: [], suppliers: [], units: [] };
    const sel = (list, current) => list.map(o =>
      `<option value="${o.id}" ${String(o.id) === String(current) ? 'selected' : ''}>${esc(o.name)}</option>`).join('');
    NOVA.modal('Edit ' + it.name, `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label class="full"><span>Name</span><input id="e-name" value="${esc(it.name)}"></label>
        <label><span>Category</span><select id="e-cat"><option value="">—</option>${sel(ref.categories, it.category_id)}</select></label>
        <label><span>Location</span><select id="e-loc"><option value="">—</option>${sel(ref.locations, it.location_id)}</select></label>
        <label><span>Minimum stock</span><input id="e-min" type="number" step="any" value="${it.min_stock}"></label>
        <label><span>Reorder point</span><input id="e-reorder" type="number" step="any" value="${it.reorder_point}"></label>
        <label><span>Target stock</span><input id="e-target" type="number" step="any" value="${it.target_stock}"></label>
        <label><span>Maximum stock</span><input id="e-max" type="number" step="any" value="${it.max_stock}"></label>
        <label><span>Base units per purchase unit</span><input id="e-pf" type="number" step="any" value="${it.purchase_factor}"></label>
        <label><span>Base units per recipe unit</span><input id="e-rf" type="number" step="any" value="${it.recipe_factor}"></label>
        <label><span>Supplier</span><select id="e-sup"><option value="">—</option>${sel(ref.suppliers, it.supplier_id)}</select></label>
        <label><span>Shelf life (days)</span><input id="e-shelf" type="number" value="${it.shelf_life_days}"></label>
      </div>
      <button class="btn solid block" id="e-save">Save changes</button>
    </div>`, (body, close) => {
      $('#e-save', body).onclick = async () => {
        const res = await send(`/api/anbar/items/${it.id}`, {
          name: $('#e-name', body).value.trim(),
          category_id: $('#e-cat', body).value || null,
          location_id: $('#e-loc', body).value || null,
          min_stock: Number($('#e-min', body).value) || 0,
          reorder_point: Number($('#e-reorder', body).value) || 0,
          target_stock: Number($('#e-target', body).value) || 0,
          max_stock: Number($('#e-max', body).value) || 0,
          purchase_factor: Number($('#e-pf', body).value) || 1,
          recipe_factor: Number($('#e-rf', body).value) || 1,
          supplier_id: $('#e-sup', body).value || null,
          shelf_life_days: Number($('#e-shelf', body).value) || 0,
        });
        if (res && res.ok) { close(); openItem(it.id); }
      };
    });
  }

  /* ---------------------------------------------------------- 3. RECEIVING */

  async function renderReceiving() {
    loading();
    const [d, sup, pos] = await Promise.all([
      NOVA.api('/api/anbar/receipts'),
      NOVA.api('/api/anbar/suppliers'),
      NOVA.api('/api/anbar/purchase-orders'),
    ]);
    state.cache.receiving = { sup, pos };

    panel(`<div class="anbar-toolbar">
        <span class="anbar-count">${d.rows.length} deliveries recorded</span>
        <span class="spacer"></span>
        <button class="btn solid" id="rc-new">Record delivery</button>
      </div>
      <div class="card">${d.rows.length ? d.rows.map(r => `
        <div class="anbar-alert ${r.status === 'confirmed' ? 'info' : 'attention'}">
          <div class="anbar-alert-body">
            <b>${esc(r.code)} · ${esc(r.supplier)} ${chip(r.status === 'confirmed' ? 'good' : 'attention', r.status)}</b>
            <p>${esc(r.delivered_on)}${r.invoice_ref ? ' · invoice ' + esc(r.invoice_ref) : ''}
               · ${r.lines.length} lines · received by ${esc(r.received_by || '—')}
               ${r.total_value !== null ? ' · ' + money(r.total_value) : ''}</p>
            ${r.issues ? `<p style="color:var(--amber);margin-top:4px">Flagged: ${esc(r.issues.replace(/,/g, ', '))}</p>` : ''}
            <div style="margin-top:8px">${table(
              [{ label: 'Item' }, { label: 'Delivered', num: true }, { label: 'Accepted', num: true },
               { label: 'Rejected', num: true }, { label: 'Quality' }],
              r.lines.map(l => `<tr><td class="primary">${esc(l.name)}</td>
                <td class="num" data-label="Delivered">${num(l.delivered, 3)}</td>
                <td class="num" data-label="Accepted">${num(l.accepted, 3)}</td>
                <td class="num" data-label="Rejected">${l.rejected ? num(l.rejected, 3) : '—'}</td>
                <td class="trailing">${l.quality === 'ok' ? '<span class="muted">ok</span>' : chip('attention', l.quality)}</td></tr>`),
              { stack: true })}</div>
            ${r.status === 'draft' ? `<button class="btn solid tiny" style="margin-top:10px"
              data-confirm="${r.id}">Confirm and take into stock</button>` : ''}
          </div>
        </div>`).join('')
        : emptyState('No deliveries recorded',
            'When a supplier delivers, record it here. Stock only moves once the delivery is confirmed, so a mistake at the door never reaches the shelf.',
            'Record first delivery', () => receiptForm())}
      </div>`);

    $('#rc-new').onclick = () => receiptForm();
    $('#anbar-panel').querySelectorAll('[data-confirm]').forEach(b => {
      b.onclick = async () => {
        const res = await send(`/api/anbar/receipts/${b.dataset.confirm}/confirm`, {}, 'POST');
        if (res && res.ok) renderReceiving();
      };
    });
  }

  async function receiptForm() {
    const inv = state.cache.inventory || await NOVA.api('/api/anbar/items');
    state.cache.inventory = inv;
    const { sup, pos } = state.cache.receiving;
    const openPos = pos.rows.filter(p => ['approved', 'sent', 'partial', 'draft'].includes(p.status));

    NOVA.modal('Record delivery', `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label><span>Supplier</span><select id="r-sup">${sup.rows.map(x =>
          `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></label>
        <label><span>Against purchase order</span><select id="r-po">
          <option value="">None — direct delivery</option>
          ${openPos.map(p => `<option value="${p.id}">${esc(p.code)} · ${esc(p.supplier)}</option>`).join('')}
        </select></label>
        <label><span>Invoice reference</span><input id="r-inv" maxlength="40"></label>
        <label><span>Delivered on</span><input id="r-date" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
      </div>
      <h4 style="margin:6px 0 0;font-size:12px;color:var(--sage)">Lines</h4>
      <div class="anbar-line-editor" id="r-lines"></div>
      <button class="btn ghost tiny" id="r-add">Add line</button>
      <p class="anbar-note">Accepted is what actually goes into stock. Anything delivered
        but not accepted is recorded as rejected with its reason, so supplier quality
        scores build from real events rather than memory.</p>
      <div id="r-err"></div>
      <button class="btn solid block" id="r-save">Open delivery</button>
    </div>`, (body, close) => {
      const lines = $('#r-lines', body);
      const addLine = () => {
        const row = document.createElement('div');
        row.className = 'anbar-line';
        row.innerHTML = `
          <label><span>Item</span><select class="l-item">${inv.rows.map(r =>
            `<option value="${r.id}" data-unit="${esc(r.purchase_unit)}">${esc(r.name)}</option>`).join('')}</select></label>
          <label><span>Delivered</span><input class="l-del" type="number" step="any" value="0"></label>
          <label><span>Accepted</span><input class="l-acc" type="number" step="any" value="0"></label>
          <label><span>Price/unit</span><input class="l-price" type="number" step="any" value="0"></label>
          <label><span>Quality</span><select class="l-q">
            <option value="ok">OK</option><option value="damaged">Damaged</option>
            <option value="wrong">Wrong product</option><option value="short">Short</option>
            <option value="poor">Poor quality</option><option value="expiring">Short expiry</option>
            <option value="temperature">Temperature</option>
          </select></label>
          <label><span>Expires</span><input class="l-exp" type="date"></label>
          <button class="btn ghost tiny l-del-btn" type="button">Remove</button>`;
        row.querySelector('.l-del').oninput = e => {
          const acc = row.querySelector('.l-acc');
          if (!acc.dataset.touched) acc.value = e.target.value;
        };
        row.querySelector('.l-acc').oninput = e => { e.target.dataset.touched = '1'; };
        row.querySelector('.l-del-btn').onclick = () => row.remove();
        lines.appendChild(row);
      };
      addLine();
      $('#r-add', body).onclick = addLine;
      $('#r-po', body).onchange = e => {
        const po = openPos.find(p => String(p.id) === e.target.value);
        if (!po) return;
        $('#r-sup', body).value = po.supplier_id;
        lines.innerHTML = '';
        po.lines.forEach(l => {
          addLine();
          const row = lines.lastElementChild;
          row.querySelector('.l-item').value = l.ingredient_id;
          row.querySelector('.l-del').value = l.qty;
          row.querySelector('.l-acc').value = l.qty;
          row.querySelector('.l-price').value = l.unit_price || 0;
        });
      };
      $('#r-save', body).onclick = async () => {
        const payload = {
          supplier_id: $('#r-sup', body).value,
          purchase_order_id: $('#r-po', body).value || null,
          invoice_ref: $('#r-inv', body).value.trim(),
          delivered_on: $('#r-date', body).value,
          lines: [...lines.querySelectorAll('.anbar-line')].map(row => ({
            ingredient_id: row.querySelector('.l-item').value,
            unit: row.querySelector('.l-item').selectedOptions[0].dataset.unit,
            delivered_qty: Number(row.querySelector('.l-del').value) || 0,
            accepted_qty: Number(row.querySelector('.l-acc').value) || 0,
            unit_price: Number(row.querySelector('.l-price').value) || 0,
            quality: row.querySelector('.l-q').value,
            expires_on: row.querySelector('.l-exp').value || '',
          })).filter(l => l.delivered_qty > 0),
        };
        if (!payload.lines.length) {
          $('#r-err', body).innerHTML = '<div class="anbar-error">Add at least one delivered line.</div>';
          return;
        }
        const res = await send('/api/anbar/receipts', payload);
        if (res && res.ok) { close(); renderReceiving(); }
      };
    });
  }

  /* ---------------------------------------------------------- 4. PURCHASES */

  async function renderPurchases() {
    loading();
    const [d, plan, sup] = await Promise.all([
      NOVA.api('/api/anbar/purchase-orders'),
      NOVA.api('/api/anbar/reorder'),
      NOVA.api('/api/anbar/suppliers'),
    ]);
    state.cache.purchases = { sup };

    const planHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Suggested order</h3>
        <p>Demand over supplier lead time, minus what is on hand and already coming.</p></div>
        <span class="chip ${plan.confidence === 'high' ? 'good' : plan.confidence === 'medium' ? 'attention' : 'info'}">
          ${esc(plan.confidence)} confidence</span></div>
      ${plan.rows.length ? `${table(
        [{ label: 'Item' }, { label: 'On hand', num: true }, { label: 'Suggest', num: true },
         { label: 'Value', num: true }, { label: 'Supplier' }],
        plan.rows.slice(0, 25).map(r => `<tr>
          <td class="primary">${esc(r.name)} ${chip(r.status)}
            ${explain(r.why)}</td>
          <td class="num" data-label="On hand">${num(r.in_stock, 2)} ${esc(r.unit)}</td>
          <td class="num strong" data-label="Suggest">${num(r.suggested, 2)} ${esc(r.unit)}</td>
          <td class="num" data-label="Value">${money(r.value)}</td>
          <td data-label="Supplier" class="muted">${esc(r.supplier)}</td></tr>`),
        { stack: true })}
        <p class="anbar-count" style="margin-top:12px">Basis: ${esc(plan.basis)}.
          ${plan.total_value !== null ? 'Total ' + money(plan.total_value) + '.' : ''}
          Nothing is ordered until a manager raises and approves it.</p>`
        : '<div class="anbar-empty"><p>Nothing needs ordering. Every line covers expected demand over its lead time.</p></div>'}
    </div>`;

    const ordersHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Purchase orders</h3>
        <p>Above ${money(d.approval_threshold)} an order needs owner or GM approval.</p></div></div>
      ${d.rows.length ? table(
        [{ label: 'Order' }, { label: 'Supplier' }, { label: 'Status' },
         { label: 'Expected' }, { label: 'Total', num: true }, { label: '' }],
        d.rows.map(p => `<tr>
          <td class="primary">${esc(p.code)}<br><span class="muted" style="font-size:11px">${p.lines.length} lines · ${esc(p.raised_by)}</span></td>
          <td data-label="Supplier">${esc(p.supplier)}</td>
          <td class="trailing">${chip(
            p.status === 'pending' ? 'attention' : p.status === 'delivered' ? 'good' :
            p.status === 'cancelled' ? 'out' : 'neutral', p.status)}</td>
          <td data-label="Expected" class="muted">${esc(p.expected_on || '—')}</td>
          <td class="num" data-label="Total">${money(p.total)}</td>
          <td class="trailing">${po_actions(p)}</td></tr>`), { stack: true })
        : emptyState('No purchase orders yet',
            'Raise one from the suggested order above, or create it manually against a supplier.',
            'Raise an order', () => poForm())}
    </div>`;

    panel(`<div class="anbar-toolbar"><span class="spacer"></span>
      <button class="btn solid" id="po-new">Raise purchase order</button></div>
      ${planHtml}<div style="height:16px"></div>${ordersHtml}`);

    $('#po-new').onclick = () => poForm(plan.rows);
    $('#anbar-panel').querySelectorAll('[data-po-status]').forEach(b => {
      b.onclick = async () => {
        const res = await send(`/api/anbar/purchase-orders/${b.dataset.po}/status`,
          { status: b.dataset.poStatus });
        if (res && res.ok) renderPurchases();
      };
    });
  }

  function po_actions(p) {
    const btn = (label, status, cls) =>
      `<button class="btn ${cls || 'ghost'} tiny" data-po="${p.id}" data-po-status="${status}">${label}</button>`;
    if (p.status === 'draft') return btn('Approve', 'approved', 'solid');
    if (p.status === 'pending') return btn('Approve', 'approved', 'solid');
    if (p.status === 'approved') return btn('Mark sent', 'sent');
    return '';
  }

  async function poForm(suggestions) {
    const inv = state.cache.inventory || await NOVA.api('/api/anbar/items');
    state.cache.inventory = inv;
    const sup = state.cache.purchases.sup;
    NOVA.modal('Raise purchase order', `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label><span>Supplier</span><select id="p-sup">${sup.rows.map(x =>
          `<option value="${x.id}">${esc(x.name)}</option>`).join('')}</select></label>
        <label><span>Expected delivery</span><input id="p-date" type="date"></label>
      </div>
      <div class="anbar-line-editor" id="p-lines"></div>
      <button class="btn ghost tiny" id="p-add">Add line</button>
      ${suggestions && suggestions.length ? `<button class="btn ghost tiny" id="p-fill">Fill from suggestion</button>` : ''}
      <label><span>Note</span><textarea id="p-note" rows="2" maxlength="200"></textarea></label>
      <div id="p-total" class="anbar-note"></div>
      <div id="p-err"></div>
      <button class="btn solid block" id="p-save">Raise order</button>
    </div>`, (body, close) => {
      const lines = $('#p-lines', body);
      const recalc = () => {
        const total = [...lines.querySelectorAll('.anbar-line')].reduce((a, row) =>
          a + (Number(row.querySelector('.l-qty').value) || 0) *
              (Number(row.querySelector('.l-price').value) || 0), 0);
        $('#p-total', body).textContent = 'Order total: ' + NOVA.money2(total);
      };
      const addLine = (ingId, qty, price) => {
        const row = document.createElement('div');
        row.className = 'anbar-line';
        row.innerHTML = `
          <label><span>Item</span><select class="l-item">${inv.rows.map(r =>
            `<option value="${r.id}" data-unit="${esc(r.purchase_unit)}" data-cost="${r.cost || 0}">${esc(r.name)}</option>`).join('')}</select></label>
          <label><span>Quantity</span><input class="l-qty" type="number" step="any" value="${qty || 0}"></label>
          <label><span>Unit price</span><input class="l-price" type="number" step="any" value="${price || 0}"></label>
          <button class="btn ghost tiny l-rm" type="button">Remove</button>`;
        if (ingId) row.querySelector('.l-item').value = ingId;
        row.querySelector('.l-item').onchange = e => {
          row.querySelector('.l-price').value = e.target.selectedOptions[0].dataset.cost || 0;
          recalc();
        };
        row.querySelector('.l-qty').oninput = recalc;
        row.querySelector('.l-price').oninput = recalc;
        row.querySelector('.l-rm').onclick = () => { row.remove(); recalc(); };
        lines.appendChild(row);
        recalc();
      };
      addLine();
      $('#p-add', body).onclick = () => addLine();
      const fill = $('#p-fill', body);
      if (fill) fill.onclick = () => {
        lines.innerHTML = '';
        const supId = $('#p-sup', body).value;
        const mine = suggestions.filter(r => !r.supplier_id || String(r.supplier_id) === supId);
        (mine.length ? mine : suggestions).slice(0, 12).forEach(r =>
          addLine(r.ingredient_id, r.suggested, 0));
      };
      $('#p-save', body).onclick = async () => {
        const payload = {
          supplier_id: $('#p-sup', body).value,
          expected_on: $('#p-date', body).value,
          note: $('#p-note', body).value.trim(),
          lines: [...lines.querySelectorAll('.anbar-line')].map(row => ({
            ingredient_id: row.querySelector('.l-item').value,
            unit: row.querySelector('.l-item').selectedOptions[0].dataset.unit,
            qty: Number(row.querySelector('.l-qty').value) || 0,
            unit_price: Number(row.querySelector('.l-price').value) || 0,
          })).filter(l => l.qty > 0),
        };
        if (!payload.lines.length) {
          $('#p-err', body).innerHTML = '<div class="anbar-error">Add at least one line with a quantity.</div>';
          return;
        }
        const res = await send('/api/anbar/purchase-orders', payload);
        if (res && res.ok) { close(); renderPurchases(); }
      };
    });
  }

  /* ---------------------------------------------------------- 5. SUPPLIERS */

  async function renderSuppliers() {
    loading();
    const d = await NOVA.api('/api/anbar/suppliers');

    const rows = d.rows.map(r => `<tr>
      <td class="primary">${esc(r.name)}${r.preferred ? ' ' + chip('good', 'preferred') : ''}
        <br><span class="muted" style="font-size:11px">${esc(r.category)}${r.contact ? ' · ' + esc(r.contact) : ''}</span></td>
      <td class="num" data-label="Score"><span class="strong">${num(r.score, 1)}</span></td>
      <td class="num" data-label="On time">${r.on_time_pct === null ? '—' : r.on_time_pct + '%'}</td>
      <td class="num" data-label="Rejected">${num(r.reject_pct, 1)}%</td>
      <td class="num" data-label="Deliveries">${r.deliveries}</td>
      <td class="num" data-label="Spend">${money(r.spend)}</td>
      <td data-label="Lead" class="muted">${r.lead_time_days}d</td>
    </tr>`);

    const compare = d.comparison.length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Where suppliers overlap</h3>
        <p>Same ingredient, more than one quote. Price is only part of the answer.</p></div></div>
      ${d.comparison.map(c => `<div class="anbar-alert info">
        <div class="anbar-alert-body">
          <b>${esc(c.name)}</b>
          ${table([{ label: 'Supplier' }, { label: 'Price', num: true }, { label: 'Score', num: true },
                   { label: 'On time', num: true }],
            c.offers.map(o => `<tr><td class="primary">${esc(o.supplier)}</td>
              <td class="num" data-label="Price">${money(o.price_per_base)}</td>
              <td class="num" data-label="Score">${num(o.score, 1)}</td>
              <td class="num" data-label="On time">${o.on_time_pct === null ? '—' : o.on_time_pct + '%'}</td></tr>`),
            { stack: true })}
          <p style="margin-top:8px">${esc(c.recommendation)}</p>
        </div></div>`).join('')}
    </div>` : '';

    const prices = d.price_moves.length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Price movement</h3>
        <p>What each line last cost against the time before.</p></div></div>
      ${table([{ label: 'Item' }, { label: 'Previous', num: true }, { label: 'Current', num: true },
               { label: 'Change', num: true }, { label: '30d', num: true }, { label: 'Supplier' }],
        d.price_moves.map(m => `<tr class="${m.change_pct > 0 ? 'neg' : ''}">
          <td class="primary">${esc(m.name)}</td>
          <td class="num" data-label="Previous">${money(m.previous)}</td>
          <td class="num" data-label="Current">${money(m.current)}</td>
          <td class="num strong" data-label="Change" style="color:${m.change_pct > 0 ? 'var(--coral)' : 'var(--mint)'}">
            ${m.change_pct > 0 ? '+' : ''}${m.change_pct}%</td>
          <td class="num" data-label="30d">${m.trend_30d ? (m.trend_30d > 0 ? '+' : '') + m.trend_30d + '%' : '—'}</td>
          <td data-label="Supplier" class="muted">${esc(m.supplier || '—')}</td></tr>`), { stack: true })}
    </div>` : '';

    panel(`<div class="anbar-toolbar"><span class="anbar-count">${d.rows.length} suppliers</span>
      <span class="spacer"></span><button class="btn solid" id="sup-new">Add supplier</button></div>
      <div class="card">${d.rows.length ? table(
        [{ label: 'Supplier' }, { label: 'Score', num: true }, { label: 'On time', num: true },
         { label: 'Rejected', num: true }, { label: 'Deliveries', num: true },
         { label: 'Spend', num: true }, { label: 'Lead' }], rows, { stack: true })
        : emptyState('No suppliers yet', 'Add the people you buy from, and Anbar starts scoring them on what actually happens at the door.', 'Add supplier', () => supplierForm())}
        <p class="anbar-count" style="margin-top:12px">Score blends delivery punctuality,
          acceptance rate and quality. A supplier with no delivery history is scored on its
          declared figures until real deliveries replace them.</p>
      </div>
      ${compare ? '<div style="height:16px"></div>' + compare : ''}
      ${prices ? '<div style="height:16px"></div>' + prices : ''}`);

    $('#sup-new').onclick = () => supplierForm();
  }

  function supplierForm() {
    NOVA.modal('Add supplier', `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label class="full"><span>Name</span><input id="s-name" maxlength="80"></label>
        <label><span>Legal name</span><input id="s-legal" maxlength="120"></label>
        <label><span>Category</span><input id="s-cat" maxlength="40" value="Produce"></label>
        <label><span>Contact person</span><input id="s-person" maxlength="60"></label>
        <label><span>Phone</span><input id="s-phone" maxlength="40"></label>
        <label><span>Email</span><input id="s-email" type="email" maxlength="80"></label>
        <label><span>Payment terms</span><input id="s-terms" maxlength="40" placeholder="30 days"></label>
        <label class="full"><span>Address</span><input id="s-addr" maxlength="160"></label>
        <label><span>Delivery days</span><input id="s-days" maxlength="60" placeholder="Mon, Wed, Fri"></label>
        <label><span>Lead time (days)</span><input id="s-lead" type="number" value="1"></label>
        <label><span>Minimum order value</span><input id="s-moq" type="number" step="any" value="0"></label>
        <label><span>Preferred</span><select id="s-pref"><option value="">No</option><option value="1">Yes</option></select></label>
      </div>
      <div id="s-err"></div>
      <button class="btn solid block" id="s-save">Add supplier</button>
    </div>`, (body, close) => {
      $('#s-save', body).onclick = async () => {
        const name = $('#s-name', body).value.trim();
        if (!name) {
          $('#s-err', body).innerHTML = '<div class="anbar-error">Give the supplier a name.</div>';
          return;
        }
        const res = await send('/api/anbar/suppliers', {
          name, legal_name: $('#s-legal', body).value.trim(),
          category: $('#s-cat', body).value.trim(),
          contact_person: $('#s-person', body).value.trim(),
          phone: $('#s-phone', body).value.trim(),
          email: $('#s-email', body).value.trim(),
          address: $('#s-addr', body).value.trim(),
          payment_terms: $('#s-terms', body).value.trim(),
          delivery_days: $('#s-days', body).value.trim(),
          lead_time_days: Number($('#s-lead', body).value) || 1,
          min_order_value: Number($('#s-moq', body).value) || 0,
          preferred: !!$('#s-pref', body).value,
        });
        if (res && res.ok) { close(); renderSuppliers(); }
      };
    });
  }

  /* ---------------------------------------------------------- 6. TRANSFERS */

  async function renderTransfers() {
    loading();
    const d = await NOVA.api('/api/anbar/transfers');
    state.cache.transfers = d;

    panel(`<div class="anbar-toolbar">
      <span class="anbar-count">${d.rows.length} transfers</span><span class="spacer"></span>
      <button class="btn solid" id="tr-new">New transfer</button></div>
      <div class="card">${d.rows.length ? d.rows.map(t => `
        <div class="anbar-alert ${t.status === 'received' ? 'info' : 'attention'}">
          <div class="anbar-alert-body">
            <b>${esc(t.code)} · ${esc(t.from)} → ${esc(t.to)}
              ${chip(t.status === 'received' ? 'good' : t.status === 'cancelled' ? 'out' : 'attention', t.status)}</b>
            <p>${esc(t.requested_at)} · requested by ${esc(t.requested_by)}
              ${t.received_by ? ' · received by ' + esc(t.received_by) : ''}</p>
            <div style="margin-top:8px">${table([{ label: 'Item' }, { label: 'Qty', num: true }],
              t.lines.map(l => `<tr><td class="primary">${esc(l.name)}</td>
                <td class="num" data-label="Qty">${num(l.qty, 3)}</td></tr>`), { stack: true })}</div>
            <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
              ${['requested', 'approved'].includes(t.status)
                ? `<button class="btn solid tiny" data-tr="${t.id}" data-tr-status="in_transit">Send</button>` : ''}
              ${t.status === 'in_transit'
                ? `<button class="btn solid tiny" data-tr="${t.id}" data-tr-status="received">Confirm received</button>` : ''}
              ${['requested', 'approved'].includes(t.status)
                ? `<button class="btn ghost tiny" data-tr="${t.id}" data-tr-status="cancelled">Cancel</button>` : ''}
            </div>
          </div></div>`).join('')
        : emptyState('No transfers yet',
            'Move stock between the warehouse, the kitchen and the bar. Stock leaves on send and lands on receipt, so a transfer can never invent inventory.',
            'New transfer', () => transferForm())}
      </div>`);

    $('#tr-new').onclick = () => transferForm();
    $('#anbar-panel').querySelectorAll('[data-tr-status]').forEach(b => {
      b.onclick = async () => {
        const res = await send(`/api/anbar/transfers/${b.dataset.tr}/status`,
          { status: b.dataset.trStatus });
        if (res && res.ok) renderTransfers();
      };
    });
  }

  async function transferForm() {
    const inv = state.cache.inventory || await NOVA.api('/api/anbar/items');
    state.cache.inventory = inv;
    const locs = state.cache.transfers.locations;
    NOVA.modal('New stock transfer', `<div class="anbar-form">
      <div class="anbar-form-grid">
        <label><span>From</span><select id="t-from">${locs.map(l =>
          `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select></label>
        <label><span>To</span><select id="t-to">${locs.map(l =>
          `<option value="${l.id}">${esc(l.name)}</option>`).join('')}</select></label>
      </div>
      <div class="anbar-line-editor" id="t-lines"></div>
      <button class="btn ghost tiny" id="t-add">Add item</button>
      <label><span>Note</span><textarea id="t-note" rows="2" maxlength="200"></textarea></label>
      <div id="t-err"></div>
      <button class="btn solid block" id="t-save">Request transfer</button>
    </div>`, (body, close) => {
      const lines = $('#t-lines', body);
      const addLine = () => {
        const row = document.createElement('div');
        row.className = 'anbar-line';
        row.innerHTML = `<label><span>Item</span><select class="l-item">${inv.rows.map(r =>
            `<option value="${r.id}" data-unit="${esc(r.unit)}">${esc(r.name)} (${num(r.in_stock, 2)} ${esc(r.unit)})</option>`).join('')}</select></label>
          <label><span>Quantity</span><input class="l-qty" type="number" step="any" value="0"></label>
          <button class="btn ghost tiny l-rm" type="button">Remove</button>`;
        row.querySelector('.l-rm').onclick = () => row.remove();
        lines.appendChild(row);
      };
      addLine();
      $('#t-add', body).onclick = addLine;
      if (locs[1]) $('#t-to', body).value = locs[1].id;
      $('#t-save', body).onclick = async () => {
        const from = $('#t-from', body).value, to = $('#t-to', body).value;
        if (from === to) {
          $('#t-err', body).innerHTML = '<div class="anbar-error">Source and destination must differ.</div>';
          return;
        }
        const payload = {
          from_location_id: from, to_location_id: to,
          note: $('#t-note', body).value.trim(),
          lines: [...lines.querySelectorAll('.anbar-line')].map(row => ({
            ingredient_id: row.querySelector('.l-item').value,
            unit: row.querySelector('.l-item').selectedOptions[0].dataset.unit,
            qty: Number(row.querySelector('.l-qty').value) || 0,
          })).filter(l => l.qty > 0),
        };
        if (!payload.lines.length) {
          $('#t-err', body).innerHTML = '<div class="anbar-error">Add at least one item.</div>';
          return;
        }
        const res = await send('/api/anbar/transfers', payload);
        if (res && res.ok) { close(); renderTransfers(); }
      };
    });
  }

  /* ---------------------------------------------------------- 7. STOCKTAKE */

  async function renderStocktake() {
    loading();
    const d = await NOVA.api('/api/anbar/stocktakes');
    panel(`<div class="anbar-toolbar">
      <span class="anbar-count">${d.rows.length} counts</span><span class="spacer"></span>
      <button class="btn solid" id="st-new">Start stocktake</button></div>
      <div class="card">${d.rows.length ? table(
        [{ label: 'Count' }, { label: 'Scope' }, { label: 'Status' }, { label: 'Lines', num: true },
         { label: 'Variance', num: true }, { label: 'Started' }, { label: '' }],
        d.rows.map(t => `<tr>
          <td class="primary">${esc(t.code)}${t.blind ? ' ' + chip('info', 'blind') : ''}</td>
          <td data-label="Scope" class="muted">${esc(t.scope)}</td>
          <td class="trailing">${chip(t.status === 'approved' ? 'good' :
            t.status === 'review' ? 'attention' : 'neutral', t.status)}</td>
          <td class="num" data-label="Lines">${t.line_count}</td>
          <td class="num" data-label="Variance" style="color:${(t.variance_value || 0) < 0 ? 'var(--coral)' : 'inherit'}">
            ${money(t.variance_value)}</td>
          <td data-label="Started" class="muted">${esc(t.started_at)} · ${esc(t.started_by)}</td>
          <td class="trailing"><button class="btn ghost tiny" data-take="${t.id}">Open</button></td></tr>`),
        { stack: true })
        : emptyState('No stocktakes yet',
            'A count compares what is on the shelf with what the ledger expects. The difference is variance, and it is the single most useful number in a warehouse.',
            'Start first stocktake', () => stocktakeForm())}
      </div>`);
    $('#st-new').onclick = () => stocktakeForm();
    $('#anbar-panel').querySelectorAll('[data-take]').forEach(b => {
      b.onclick = () => openStocktake(Number(b.dataset.take));
    });
  }

  async function stocktakeForm() {
    const ref = state.reference || await NOVA.api('/api/anbar/reference');
    state.reference = ref;
    NOVA.modal('Start stocktake', `<div class="anbar-form">
      <label><span>Scope</span><select id="k-scope">
        <option value="full">Full inventory</option>
        <option value="category">One category</option>
        <option value="location">One storage area</option>
      </select></label>
      <label id="k-cat-wrap" hidden><span>Category</span><select id="k-cat">${ref.categories.map(c =>
        `<option value="${c.id}">${esc(c.name)} (${c.items})</option>`).join('')}</select></label>
      <label id="k-loc-wrap" hidden><span>Storage area</span><select id="k-loc">${ref.locations.map(l =>
        `<option value="${l.id}">${esc(l.name)} (${l.items})</option>`).join('')}</select></label>
      <label><span>Blind count</span><select id="k-blind">
        <option value="">No — show the system figure</option>
        <option value="1">Yes — hide it until counted</option>
      </select></label>
      <p class="anbar-note">A blind count hides the expected quantity so the person counting
        writes what they see rather than what the screen suggests. It takes slightly longer
        and is considerably more honest.</p>
      <button class="btn solid block" id="k-save">Start count</button>
    </div>`, (body, close) => {
      $('#k-scope', body).onchange = e => {
        $('#k-cat-wrap', body).hidden = e.target.value !== 'category';
        $('#k-loc-wrap', body).hidden = e.target.value !== 'location';
      };
      $('#k-save', body).onclick = async () => {
        const scope = $('#k-scope', body).value;
        const res = await send('/api/anbar/stocktakes', {
          scope, blind: !!$('#k-blind', body).value,
          category_id: scope === 'category' ? $('#k-cat', body).value : null,
          location_id: scope === 'location' ? $('#k-loc', body).value : null,
        });
        if (res && res.ok) { close(); openStocktake(res.id); }
      };
    });
  }

  async function openStocktake(id) {
    loading();
    const d = await NOVA.api('/api/anbar/stocktakes/' + id);
    const t = d.stocktake;
    const editable = t.status !== 'approved' && t.status !== 'cancelled';

    panel(`<div class="anbar-toolbar">
        <button class="btn ghost tiny" id="st-back">← All counts</button>
        <span class="spacer"></span>
        <span class="anbar-count">${esc(t.code)} · ${esc(t.scope)} · ${esc(t.status)}
          ${t.blind ? '· blind' : ''}</span>
        ${editable ? `<button class="btn" id="st-save">Save counts</button>
          <button class="btn solid" id="st-approve">Approve and adjust</button>` : ''}
      </div>
      ${d.blind_active ? '<div class="anbar-note" style="margin-bottom:12px">Blind count in progress — the system quantity stays hidden until each line is counted.</div>' : ''}
      <div class="card">
        ${table([{ label: 'Item' }, { label: 'System', num: true }, { label: 'Counted', num: true },
                 { label: 'Variance', num: true }, { label: 'Cost impact', num: true }, { label: 'Comment' }],
          d.lines.map(l => `<tr>
            <td class="primary">${esc(l.name)} <span class="muted">${esc(l.unit)}</span></td>
            <td class="num" data-label="System">${l.system_qty === null ? '<span class="muted">hidden</span>' : num(l.system_qty, 3)}</td>
            <td class="num" data-label="Counted">${editable
              ? `<input type="number" step="any" class="st-count" data-line="${l.id}"
                   value="${l.counted_qty === null ? '' : l.counted_qty}"
                   style="width:88px;padding:5px 7px;background:var(--panel-2);border:1px solid var(--edge);border-radius:8px;color:var(--bone);text-align:right">`
              : (l.counted_qty === null ? '—' : num(l.counted_qty, 3))}</td>
            <td class="num" data-label="Variance" style="color:${l.variance_qty < 0 ? 'var(--coral)' : l.variance_qty > 0 ? 'var(--mint)' : 'inherit'}">
              ${l.counted_qty === null ? '—' : (l.variance_qty > 0 ? '+' : '') + num(l.variance_qty, 3)}</td>
            <td class="num" data-label="Cost impact">${l.counted_qty === null ? '—' : money(l.variance_value)}</td>
            <td data-label="Comment">${editable
              ? `<input type="text" class="st-comment" data-line="${l.id}" maxlength="200"
                   value="${esc(l.comment)}" placeholder="optional"
                   style="width:100%;min-width:110px;padding:5px 7px;background:var(--panel-2);border:1px solid var(--edge);border-radius:8px;color:var(--bone)">`
              : esc(l.comment || '—')}</td></tr>`), {})}
        <p class="anbar-count" style="margin-top:12px">
          Total variance so far: <b>${money(t.variance_value)}</b>.
          Nothing is adjusted until this count is approved.</p>
      </div>`);

    $('#st-back').onclick = renderStocktake;
    const collect = () => {
      const comments = {};
      $('#anbar-panel').querySelectorAll('.st-comment').forEach(i => {
        comments[i.dataset.line] = i.value;
      });
      return [...$('#anbar-panel').querySelectorAll('.st-count')]
        .filter(i => i.value !== '')
        .map(i => ({ line_id: Number(i.dataset.line), counted_qty: Number(i.value),
                     comment: comments[i.dataset.line] || '' }));
    };
    if (editable) {
      $('#st-save').onclick = async () => {
        const res = await send(`/api/anbar/stocktakes/${id}/count`, { counts: collect() });
        if (res && res.ok) openStocktake(id);
      };
      $('#st-approve').onclick = async () => {
        const counts = collect();
        if (!counts.length) { NOVA.toast('Count at least one line first.', 'bad'); return; }
        if (!confirm('Approve this count? Physical quantities become the new stock figures '
          + 'and the difference is written to the ledger. This cannot be undone.')) return;
        await send(`/api/anbar/stocktakes/${id}/count`, { counts });
        const res = await send(`/api/anbar/stocktakes/${id}/approve`, {}, 'POST');
        if (res && res.ok) openStocktake(id);
      };
    }
  }

  /* ---------------------------------------------------------- 8. WASTE */

  async function renderWaste() {
    loading();
    const d = await NOVA.api('/api/anbar/waste?days=30');
    const intel = d.intelligence;

    const findings = (intel.findings || []).length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>What the waste is telling you</h3>
        <p>Patterns found in the last 30 days of entries.</p></div></div>
      ${intel.findings.map(f => `<div class="anbar-alert attention">
        <div class="anbar-alert-body"><b>${esc(f.title)}</b><p>${esc(f.body)}</p></div></div>`).join('')}
    </div>` : '';

    const breakdown = d.can_see_costs ? `<div class="anbar-split">
      <div class="card"><div class="anbar-section-title"><div><h3>By reason</h3></div></div>
        ${intel.by_reason.length ? bars(intel.by_reason.map(r => ({
          name: WASTE_LABEL[r.name] || r.name, value: r.value, display: money(r.value), tone: 'warn' })))
          : '<div class="anbar-empty"><p>Nothing logged.</p></div>'}</div>
      <div class="card"><div class="anbar-section-title"><div><h3>Top items</h3></div></div>
        ${intel.by_item.length ? bars(intel.by_item.map(r => ({
          name: r.name, value: r.value, display: money(r.value), tone: 'bad' })))
          : '<div class="anbar-empty"><p>Nothing logged.</p></div>'}</div>
    </div>` : '';

    panel(`<div class="anbar-cards">
        ${card('Waste 30 days', money(intel.total), `${intel.entries} entries`, intel.total ? 'warn' : '')}
        ${d.can_see_costs ? card('Purchases 30 days', money(intel.purchases), 'confirmed deliveries') : ''}
        ${d.can_see_costs ? card('Waste rate', intel.waste_pct_of_purchases === null
          ? '—' : intel.waste_pct_of_purchases + '%', 'of purchases',
          (intel.waste_pct_of_purchases || 0) > 5 ? 'warn' : 'good') : ''}
      </div>
      <div class="anbar-toolbar"><span class="spacer"></span>
        <button class="btn solid" id="wa-new">Log waste</button></div>
      ${findings}${findings ? '<div style="height:16px"></div>' : ''}
      ${breakdown}${breakdown ? '<div style="height:16px"></div>' : ''}
      <div class="card">
        <div class="anbar-section-title"><div><h3>Waste log</h3>
          <p>Every entry, with who recorded it.</p></div></div>
        ${d.rows.length ? table(
          [{ label: 'Date' }, { label: 'Item' }, { label: 'Qty', num: true },
           { label: 'Reason' }, { label: 'Cost', num: true }, { label: 'By' }],
          d.rows.map(r => `<tr>
            <td class="primary">${esc(r.date)}</td>
            <td data-label="Item">${esc(r.name)}</td>
            <td class="num" data-label="Qty">${num(r.qty, 3)} ${esc(r.unit)}</td>
            <td data-label="Reason">${chip('attention', WASTE_LABEL[r.reason] || r.reason)}</td>
            <td class="num" data-label="Cost">${money(r.cost)}</td>
            <td data-label="By" class="muted">${esc(r.by || '—')}</td></tr>`), { stack: true })
          : emptyState('No waste recorded',
              'Recording waste is what makes the pattern findable later. An empty log is not the same as no waste.',
              'Log waste', () => wasteQuickForm())}
      </div>`);
    $('#wa-new').onclick = () => wasteQuickForm();
  }

  async function wasteQuickForm() {
    const inv = state.cache.inventory || await NOVA.api('/api/anbar/items');
    state.cache.inventory = inv;
    NOVA.modal('Log waste', `<div class="anbar-form">
      <label><span>Item</span><select id="q-item">${inv.rows.map(r =>
        `<option value="${r.id}" data-unit="${esc(r.unit)}">${esc(r.name)} (${num(r.in_stock, 2)} ${esc(r.unit)})</option>`).join('')}</select></label>
      <label><span>Quantity</span><input id="q-qty" type="number" step="any"></label>
      <label><span>Reason</span><select id="q-reason">${Object.entries(WASTE_LABEL).map(([k, v]) =>
        `<option value="${k}">${esc(v)}</option>`).join('')}</select></label>
      <label><span>Comment</span><textarea id="q-note" rows="2" maxlength="200"></textarea></label>
      <div id="q-err"></div>
      <button class="btn solid block" id="q-save">Record waste</button>
    </div>`, (body, close) => {
      $('#q-save', body).onclick = async () => {
        const qty = Number($('#q-qty', body).value);
        if (!(qty > 0)) {
          $('#q-err', body).innerHTML = '<div class="anbar-error">Enter a quantity above zero.</div>';
          return;
        }
        const sel = $('#q-item', body);
        const res = await send('/api/anbar/waste', {
          ingredient_id: sel.value, qty, unit: sel.selectedOptions[0].dataset.unit,
          reason: $('#q-reason', body).value, note: $('#q-note', body).value.trim(),
        });
        if (res && res.ok) { close(); renderWaste(); }
      };
    });
  }

  /* ---------------------------------------------------------- 9. RECIPES */

  const usageState = {dish:null, days:30, portions:1};
  async function renderUsage() {
    loading();
    const query = new URLSearchParams({days:usageState.days, portions:usageState.portions});
    if(usageState.dish)query.set('menu_item_id',usageState.dish);
    const d = await NOVA.api('/api/anbar/recipe-usage?'+query);
    usageState.dish=d.dish.id;
    panel(`<section class="card warehouse-usage">
      <div class="anbar-section-title"><div><h2>Расход ингредиентов / Dish ingredient usage</h2>
      <p>Количество по рецепту × количество порций. Расход на основе граммовки рецепта для каждого блюда.</p></div></div>
      <div class="warehouse-usage-controls">
        <label><span>Dish</span><select id="usage-dish">${d.dishes.map(m=>`<option value="${m.id}" ${m.id===d.dish.id?'selected':''}>${esc(m.name)}</option>`).join('')}</select></label>
        <label><span>Usage period</span><select id="usage-days">${[1,7,30,90].map(n=>`<option value="${n}" ${n===d.days?'selected':''}>${n}</option>`).join('')}</select><small>Days</small></label>
        <label><span>Plan portions</span><input id="usage-portions" type="number" min="1" max="10000" step="1" value="${d.portions}"></label>
        <button class="btn solid" id="usage-calculate">Calculate</button>
        <button class="btn" id="usage-recipe">Edit recipe</button>
      </div>
      <div class="anbar-cards">${card('Prepared portions',d.prepared_portions,'Recorded in selected period')}${card('Planned portions',d.portions,'Preview only — stock is unchanged')}</div>
      ${!d.has_recipe?'<p class="anbar-note">Recipe needed. Enter the kitchen’s quantities per portion to calculate ingredient use.</p>':''}
      ${table([{label:'Ингредиент / Ingredient'},{label:'Ед. изм.'},{label:'На порцию',num:true},{label:'Израсходовано',num:true},{label:'Остаток на складе',num:true},{label:'На план',num:true},{label:'После готовки',num:true}],
        d.ingredients.map(r=>`<tr><td class="primary"><b>${esc(r.name_ru||r.name)}</b>${r.name_ru?`<br><small style="color:var(--muted)">${esc(r.name)}</small>`:''} ${!r.in_current_recipe?'<br><small style="color:var(--coral)">Предыдущий рецепт</small>':''}</td>
          <td>${esc(r.unit)}</td><td class="num">${num(r.per_portion,3)} ${esc(r.unit)}</td><td class="num">${num(r.used,3)} ${esc(r.unit)}</td>
          <td class="num strong">${num(r.remaining,3)} ${esc(r.unit)}</td><td class="num">${num(r.planned,3)} ${esc(r.unit)}</td>
          <td class="num strong" style="color:${r.after_plan<0?'var(--coral)':'var(--mint)'}">${num(r.after_plan,3)} ${esc(r.unit)}</td></tr>`),{stack:false})}
      <p class="anbar-note">Remaining stock includes all recorded deliveries, dishes, waste and adjustments. The plan is a preview and does not deduct stock.</p>
    </section>`);
    $('#usage-dish').onchange=()=>{usageState.dish=Number($('#usage-dish').value);renderUsage()};
    $('#usage-days').onchange=()=>{usageState.days=Number($('#usage-days').value);renderUsage()};
    $('#usage-calculate').onclick=()=>{const n=Number($('#usage-portions').value);if(!Number.isInteger(n)||n<1||n>10000){NOVA.toast('Enter a whole number of portions from 1 to 10000.','bad');return}usageState.portions=n;renderUsage()};
    $('#usage-recipe').onclick=()=>recipeForm(d.dish.id);
    applyI18n();
  }

  async function renderRecipes() {
    loading();
    const d = await NOVA.api('/api/anbar/recipes');

    const costed = d.dishes.length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Dish costing</h3>
        <p>Ingredient cost at today's weighted average, against the menu price.</p></div></div>
      ${table([{ label: 'Dish' }, { label: 'Price', num: true }, { label: 'Cost', num: true },
               { label: 'Food cost', num: true }, { label: 'Margin', num: true },
               { label: 'Sold 30d', num: true }, { label: '' }],
        d.dishes.map(r => `<tr>
          <td class="primary">${esc(r.name)}<br><span class="muted" style="font-size:11px">${esc(r.course)} · ${r.lines} ingredients</span></td>
          <td class="num" data-label="Price">${money(r.price)}</td>
          <td class="num" data-label="Cost">${money(r.cost)}</td>
          <td class="num strong" data-label="Food cost"
              style="color:${r.food_cost_pct >= 35 ? 'var(--coral)' : r.food_cost_pct >= 30 ? 'var(--amber)' : 'var(--mint)'}">
            ${r.food_cost_pct}%</td>
          <td class="num" data-label="Margin">${money(r.margin)}</td>
          <td class="num" data-label="Sold 30d">${r.sold_30d}</td>
          <td class="trailing"><button class="btn ghost tiny" data-recipe="${r.menu_item_id}">Edit</button></td></tr>`),
        { stack: true })}
    </div>` : '';

    const uncosted = d.uncosted.length ? `<div class="card">
      <div class="anbar-section-title"><div><h3>Dishes without a recipe</h3>
        <p>These sell without deducting anything from stock, and cannot be costed.
          Highest sellers first — those are the ones distorting the numbers most.</p></div></div>
      ${table([{ label: 'Dish' }, { label: 'Course' }, { label: 'Price', num: true },
               { label: 'Sold 30d', num: true }, { label: '' }],
        d.uncosted.map(r => `<tr>
          <td class="primary">${esc(r.name)}</td>
          <td data-label="Course" class="muted">${esc(r.course)}</td>
          <td class="num" data-label="Price">${money(r.price)}</td>
          <td class="num" data-label="Sold 30d">${r.sold_30d}</td>
          <td class="trailing"><button class="btn solid tiny" data-recipe="${r.menu_item_id}">Add recipe</button></td></tr>`),
        { stack: true })}
    </div>` : '';

    panel(`<div class="anbar-cards">
        ${card('Costed dishes', `${d.costed_count} / ${d.total_dishes}`, 'have a recipe on file',
          d.costed_count < d.total_dishes ? 'warn' : 'good')}
        ${card('Missing recipes', d.uncosted.length, 'consume no stock when sold',
          d.uncosted.length ? 'warn' : 'good')}
      </div>
      ${costed}${costed && uncosted ? '<div style="height:16px"></div>' : ''}${uncosted}
      ${!costed && !uncosted ? emptyState('No dishes on the menu yet',
        'Add dishes in the Menu screen, then give each one a recipe here so stock and food cost stay accurate.') : ''}`);

    $('#anbar-panel').querySelectorAll('[data-recipe]').forEach(b => {
      b.onclick = () => recipeForm(Number(b.dataset.recipe));
    });
  }

  async function recipeForm(menuItemId) {
    const [d, inv] = await Promise.all([
      NOVA.api('/api/anbar/recipes/' + menuItemId),
      state.cache.inventory ? Promise.resolve(state.cache.inventory) : NOVA.api('/api/anbar/items'),
    ]);
    state.cache.inventory = inv;
    const dish = d.dish;

    NOVA.modal(`Recipe — ${dish.name}`, `<div class="anbar-form">
      <div class="anbar-note">Menu price ${money(dish.price)}.
        Quantities are per portion, in each item's recipe unit.</div>
      <div class="anbar-line-editor" id="rp-lines"></div>
      <button class="btn ghost tiny" id="rp-add">Add ingredient</button>
      <div id="rp-total" class="anbar-note"></div>
      <button class="btn solid block" id="rp-save">Save recipe</button>
    </div>`, (body, close) => {
      const lines = $('#rp-lines', body);
      const recalc = () => {
        let cost = 0;
        lines.querySelectorAll('.anbar-line').forEach(row => {
          const opt = row.querySelector('.l-item').selectedOptions[0];
          const qty = Number(row.querySelector('.l-qty').value) || 0;
          cost += qty * Number(opt.dataset.rcost || 0);
        });
        const pct = dish.price ? (100 * cost / dish.price).toFixed(1) : '—';
        $('#rp-total', body).innerHTML =
          `Portion cost <b>${NOVA.money2(cost)}</b> · food cost <b>${pct}%</b> · ` +
          `margin <b>${NOVA.money2(dish.price - cost)}</b>`;
      };
      const addLine = (ingId, qty) => {
        const row = document.createElement('div');
        row.className = 'anbar-line';
        row.innerHTML = `<label><span>Ingredient</span><select class="l-item">${inv.rows.map(r =>
            `<option value="${r.id}" data-unit="${esc(r.recipe_unit)}"
               data-rcost="${(r.cost || 0) * 1}">${esc(r.name)}</option>`).join('')}</select></label>
          <label><span>Qty per portion</span><input class="l-qty" type="number" step="any" value="${qty || 0}"></label>
          <label><span>Unit</span><input class="l-unit" readonly value=""
            style="background:transparent;border-color:transparent;color:var(--sage)"></label>
          <button class="btn ghost tiny l-rm" type="button">Remove</button>`;
        const sel = row.querySelector('.l-item');
        if (ingId) sel.value = ingId;
        const syncUnit = () => {
          const opt = sel.selectedOptions[0];
          row.querySelector('.l-unit').value = opt ? opt.dataset.unit : '';
          // Recipe-unit cost: the API gives cost per base unit, so scale it by
          // the item's recipe factor for an honest per-gram figure.
          const inventoryRow = inv.rows.find(r => String(r.id) === sel.value);
          if (inventoryRow && inventoryRow.cost !== null) {
            const factor = inventoryRow.recipe_factor || 1;
            opt.dataset.rcost = inventoryRow.cost * factor;
          }
          recalc();
        };
        sel.onchange = syncUnit;
        row.querySelector('.l-qty').oninput = recalc;
        row.querySelector('.l-rm').onclick = () => { row.remove(); recalc(); };
        lines.appendChild(row);
        syncUnit();
      };
      if (d.lines.length) d.lines.forEach(l => addLine(l.ingredient_id, l.qty));
      else addLine();
      $('#rp-add', body).onclick = () => addLine();
      $('#rp-save', body).onclick = async () => {
        const payload = {
          lines: [...lines.querySelectorAll('.anbar-line')].map(row => ({
            ingredient_id: row.querySelector('.l-item').value,
            qty: Number(row.querySelector('.l-qty').value) || 0,
          })).filter(l => l.qty > 0),
        };
        const res = await send('/api/anbar/recipes/' + menuItemId, payload);
        if (res && res.ok) { close(); state.tab==='usage'?renderUsage():renderRecipes(); }
      };
      applyI18n(body);
    });
  }

  /* ---------------------------------------------------------- 10. INTELLIGENCE */

  async function renderIntelligence() {
    loading();
    const d = await NOVA.api('/api/anbar/intelligence');
    const brief = d.brief;

    const demandHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Tomorrow's demand</h3>
        <p>${esc(d.demand.reservations)} reservations · ${esc(d.demand.booked_covers)} covers booked ·
          ${esc(d.demand.covers)} expected including walk-ins.</p></div>
        <span class="chip ${d.demand.confidence === 'high' ? 'good' : d.demand.confidence === 'medium' ? 'attention' : 'info'}">
          ${esc(d.demand.confidence)} confidence</span></div>
      ${d.demand.rows.length ? table(
        [{ label: 'Ingredient' }, { label: 'Needed', num: true }, { label: 'On hand', num: true }, { label: 'Gap', num: true }],
        d.demand.rows.slice(0, 15).map(r => `<tr class="${r.gap > 0 ? 'neg' : ''}">
          <td class="primary">${esc(r.name)}</td>
          <td class="num" data-label="Needed">${num(r.required, 2)} ${esc(r.unit)}</td>
          <td class="num" data-label="On hand">${num(r.in_stock, 2)}</td>
          <td class="num strong" data-label="Gap">${r.gap > 0 ? num(r.gap, 2) : '—'}</td></tr>`), { stack: true })
        : '<div class="anbar-empty"><p>No recipes on file, so ingredient demand cannot be projected yet.</p></div>'}
      <p class="anbar-count" style="margin-top:10px">Basis: ${esc(d.demand.basis)}.</p>
    </div>`;

    const anomalyHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Anomalies</h3>
        <p>Observations, not accusations. Each one shows the arithmetic behind it.</p></div></div>
      ${d.anomalies.length ? d.anomalies.map(a => `<div class="anbar-alert ${esc(a.severity)}">
        <div class="anbar-alert-body"><b>${esc(a.title)}</b><p>${esc(a.body)}</p>${explain(a.why)}</div>
        <time>${chip(a.severity, a.severity)}</time></div>`).join('')
        : '<div class="anbar-empty"><p>Nothing unusual. Consumption, prices and adjustments all sit inside their normal range.</p></div>'}
    </div>`;

    const expiryHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Expiry &amp; FEFO</h3>
        <p>Earliest date first, against how much demand will realistically use.</p></div>
        ${d.expiry.value_at_risk !== null ? `<span class="chip attention">${money(d.expiry.value_at_risk)} at risk</span>` : ''}</div>
      ${d.expiry.rows.length ? table(
        [{ label: 'Item' }, { label: 'Expires' }, { label: 'Qty', num: true },
         { label: 'Will use', num: true }, { label: 'At risk', num: true }],
        d.expiry.rows.map(r => `<tr>
          <td class="primary">${esc(r.name)}${r.batch_code ? '<br><span class="muted" style="font-size:11px">' + esc(r.batch_code) + '</span>' : ''}</td>
          <td class="trailing">${chip(r.days <= 1 ? 'expired' : 'expiring',
            r.days <= 0 ? 'today' : r.days + ' days')}</td>
          <td class="num" data-label="Qty">${num(r.qty, 2)} ${esc(r.unit)}</td>
          <td class="num" data-label="Will use">${num(r.expected_use, 2)}</td>
          <td class="num strong" data-label="At risk">${num(r.at_risk_qty, 2)}
            ${r.at_risk_value ? '<br><span class="muted" style="font-size:11px">' + money(r.at_risk_value) + '</span>' : ''}</td></tr>`),
        { stack: true })
        : '<div class="anbar-empty"><p>Nothing expires within seven days.</p></div>'}
    </div>`;

    const reorderHtml = `<div class="card">
      <div class="anbar-section-title"><div><h3>Smart reordering</h3>
        <p>Quantity, not just a threshold trip. Open "Why?" on any line for the arithmetic.</p></div></div>
      ${d.reorder.rows.length ? table(
        [{ label: 'Item' }, { label: 'Suggest', num: true }, { label: 'Value', num: true }, { label: 'Supplier' }],
        d.reorder.rows.slice(0, 12).map(r => `<tr>
          <td class="primary">${esc(r.name)} ${chip(r.status)}${explain(r.why)}</td>
          <td class="num strong" data-label="Suggest">${num(r.suggested, 2)} ${esc(r.unit)}</td>
          <td class="num" data-label="Value">${money(r.value)}</td>
          <td data-label="Supplier" class="muted">${esc(r.supplier)}</td></tr>`), { stack: true })
        : '<div class="anbar-empty"><p>Nothing needs ordering right now.</p></div>'}
      <p class="anbar-count" style="margin-top:10px">SUFRA never places an order by itself.
        Raise these in Purchases, where they still need approval.</p>
    </div>`;

    const costHtml = d.can_see_costs && d.food_cost && d.food_cost.dishes && d.food_cost.dishes.length
      ? `<div class="card">
        <div class="anbar-section-title"><div><h3>Food cost intelligence</h3>
          <p>House average ${d.food_cost.average_food_cost_pct}% across ${d.food_cost.costed_dishes} costed dishes.</p></div></div>
        ${(d.food_cost.findings || []).map(f => `<div class="anbar-alert attention">
          <div class="anbar-alert-body"><b>${esc(f.title)}</b><p>${esc(f.body)}</p></div></div>`).join('')}
        ${(d.food_cost.drift || []).map(f => `<div class="anbar-alert high">
          <div class="anbar-alert-body"><b>${esc(f.title)}</b><p>${esc(f.body)}</p></div></div>`).join('')}
        ${!(d.food_cost.findings || []).length && !(d.food_cost.drift || []).length
          ? '<div class="anbar-empty"><p>Every costed dish sits inside its expected margin.</p></div>' : ''}
      </div>` : '';

    const impactHtml = d.can_see_costs && d.cost_impact && d.cost_impact.length
      ? `<div class="card">
        <div class="anbar-section-title"><div><h3>Price rises reaching the menu</h3>
          <p>Which dishes a supplier increase actually hurts, and by how much a month.</p></div></div>
        ${table([{ label: 'Dish' }, { label: 'Per portion', num: true },
                 { label: 'Monthly', num: true }, { label: 'Food cost', num: true }, { label: 'Driven by' }],
          d.cost_impact.slice(0, 10).map(r => `<tr class="neg">
            <td class="primary">${esc(r.name)}</td>
            <td class="num" data-label="Per portion">+${money(r.delta_per_portion)}</td>
            <td class="num strong" data-label="Monthly">${money(r.monthly_impact)}</td>
            <td class="num" data-label="Food cost">${r.food_cost_pct}%</td>
            <td data-label="Driven by" class="muted">${esc(r.drivers.map(x => x.name + ' +' + x.change_pct + '%').join(', '))}</td></tr>`),
          { stack: true })}
      </div>` : '';

    const wasteHtml = d.can_see_costs && d.waste && (d.waste.findings || []).length
      ? `<div class="card">
        <div class="anbar-section-title"><div><h3>Waste intelligence</h3>
          <p>${money(d.waste.total)} over 30 days${d.waste.waste_pct_of_purchases !== null
            ? ' · ' + d.waste.waste_pct_of_purchases + '% of purchases' : ''}.</p></div></div>
        ${d.waste.findings.map(f => `<div class="anbar-alert attention">
          <div class="anbar-alert-body"><b>${esc(f.title)}</b><p>${esc(f.body)}</p></div></div>`).join('')}
      </div>` : '';

    const supplierHtml = d.can_see_costs && d.suppliers && d.suppliers.length
      ? `<div class="card">
        <div class="anbar-section-title"><div><h3>Supplier recommendations</h3>
          <p>Where the cheapest quote is not automatically the right one.</p></div></div>
        ${d.suppliers.map(c => `<div class="anbar-alert info">
          <div class="anbar-alert-body"><b>${esc(c.name)}</b><p>${esc(c.recommendation)}</p></div></div>`).join('')}
      </div>` : '';

    panel(`<div class="anbar-brief">
        <div class="anbar-brief-head"><i></i>SUFRA AI daily brief</div>
        <h3>${esc(briefHeadline(brief))}</h3>
        ${brief.points.length ? `<ul>${brief.points.map(p =>
          `<li class="${esc(p.severity)}"><i></i><span>${esc(briefPoint(p))}</span></li>`).join('')}</ul>` : ''}
        <div class="conf">Forecast confidence: ${esc(brief.confidence)}. Where history is thin,
          Anbar gives a rules-based recommendation and says so rather than inventing precision.</div>
      </div>
      <div class="anbar-split">${demandHtml}${reorderHtml}</div>
      <div style="height:16px"></div>
      <div class="anbar-split">${anomalyHtml}${expiryHtml}</div>
      ${costHtml || impactHtml ? `<div style="height:16px"></div><div class="anbar-split">${costHtml}${impactHtml}</div>` : ''}
      ${wasteHtml || supplierHtml ? `<div style="height:16px"></div><div class="anbar-split">${wasteHtml}${supplierHtml}</div>` : ''}`);
  }

  /* ---------------------------------------------------------- 11. REPORTS */

  const REPORTS = [
    ['valuation', 'Inventory valuation'], ['movement', 'Inventory movement'],
    ['purchasing', 'Purchasing'], ['supplier-performance', 'Supplier performance'],
    ['waste', 'Waste'], ['variance', 'Stock variance'], ['food-cost', 'Food cost'],
    ['consumption', 'Product consumption'], ['expiry', 'Expiry risk'],
    ['price-change', 'Price changes'],
  ];
  let reportState = { name: 'valuation', days: 30 };

  async function renderReports() {
    loading();
    let d;
    try {
      d = await NOVA.api(`/api/anbar/reports/${reportState.name}?days=${reportState.days}`);
    } catch (e) {
      panel(`<div class="anbar-empty"><b>Reports need cost access</b>
        <p>${esc(e.message || 'Your role cannot open financial reports.')}</p></div>`);
      return;
    }

    const toolbar = `<div class="anbar-toolbar">
      <select id="rp-name">${REPORTS.map(([k, v]) =>
        `<option value="${k}" ${reportState.name === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select>
      <select id="rp-days">${[
        [1, 'Today'], [2, 'Yesterday'], [7, '7 days'], [30, '30 days'], [90, '90 days'], [365, '12 months'],
      ].map(([k, v]) => `<option value="${k}" ${reportState.days === k ? 'selected' : ''}>${esc(v)}</option>`).join('')}</select>
      <span class="spacer"></span>
      <button class="btn ghost" id="rp-csv">Export CSV</button>
    </div>`;

    let bodyHtml = '';
    const rows = d.rows || [];
    if (reportState.name === 'waste') {
      bodyHtml = `<div class="anbar-cards">
          ${card('Total waste', money(d.total), `${d.entries} entries`)}
          ${card('Purchases', money(d.purchases), 'same window')}
          ${card('Waste rate', d.waste_pct_of_purchases === null ? '—' : d.waste_pct_of_purchases + '%', 'of purchases')}
        </div>
        <div class="card">${bars((d.by_item || []).map(r => ({
          name: r.name, value: r.value, display: money(r.value), tone: 'warn' })))}</div>`;
    } else if (reportState.name === 'food-cost') {
      bodyHtml = `<div class="card">${table(
        [{ label: 'Dish' }, { label: 'Price', num: true }, { label: 'Cost', num: true },
         { label: 'Food cost', num: true }, { label: 'Margin', num: true }],
        (d.dishes || []).map(r => `<tr><td class="primary">${esc(r.name)}</td>
          <td class="num" data-label="Price">${money(r.price)}</td>
          <td class="num" data-label="Cost">${money(r.cost)}</td>
          <td class="num strong" data-label="Food cost">${r.food_cost_pct}%</td>
          <td class="num" data-label="Margin">${money(r.margin)}</td></tr>`), { stack: true })}</div>`;
    } else if (reportState.name === 'supplier-performance') {
      bodyHtml = `<div class="card">${table(
        [{ label: 'Supplier' }, { label: 'Score', num: true }, { label: 'On time', num: true },
         { label: 'Rejected', num: true }, { label: 'Spend', num: true }, { label: 'Basis' }],
        rows.map(r => `<tr><td class="primary">${esc(r.name)}</td>
          <td class="num" data-label="Score">${num(r.score, 1)}</td>
          <td class="num" data-label="On time">${r.on_time_pct === null ? '—' : r.on_time_pct + '%'}</td>
          <td class="num" data-label="Rejected">${num(r.reject_pct, 1)}%</td>
          <td class="num" data-label="Spend">${money(r.spend)}</td>
          <td data-label="Basis" class="muted">${esc(r.basis)}</td></tr>`), { stack: true })}</div>`;
    } else if (rows.length) {
      const cols = Object.keys(rows[0]);
      bodyHtml = `<div class="card">${table(
        cols.map(c => ({ label: c.replace(/_/g, ' '), num: typeof rows[0][c] === 'number' })),
        rows.map(r => `<tr>${cols.map((c, i) => {
          const v = r[c];
          const isNum = typeof v === 'number';
          return `<td class="${isNum ? 'num' : ''} ${i === 0 ? 'primary' : ''}" data-label="${esc(c.replace(/_/g, ' '))}">${
            v === null || v === undefined ? '—' : (isNum ? num(v, 3) : esc(v))}</td>`;
        }).join('')}</tr>`), { stack: true })}
        ${d.total !== undefined ? `<p class="anbar-count" style="margin-top:12px">Total: <b>${money(d.total)}</b></p>` : ''}
      </div>`;
    } else {
      bodyHtml = `<div class="card"><div class="anbar-empty">
        <b>Nothing in this period</b><p>No rows fall inside the selected window.</p></div></div>`;
    }

    panel(toolbar + `<div class="anbar-section-title"><div><h3>${esc(d.title)}</h3>
      ${d.days ? `<p>Last ${d.days} days.</p>` : ''}</div></div>` + bodyHtml);

    $('#rp-name').onchange = e => { reportState.name = e.target.value; renderReports(); };
    $('#rp-days').onchange = e => { reportState.days = Number(e.target.value); renderReports(); };
    $('#rp-csv').onclick = () => exportCsv(d);
  }

  function exportCsv(d) {
    const rows = d.rows || d.dishes || [];
    if (!rows.length) { NOVA.toast('Nothing to export.', 'bad'); return; }
    const cols = Object.keys(rows[0]).filter(c => typeof rows[0][c] !== 'object');
    const csv = [cols.join(',')].concat(rows.map(r =>
      cols.map(c => {
        const v = r[c];
        const text = v === null || v === undefined ? '' : String(v);
        return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
      }).join(','))).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `sufra-anbar-${reportState.name}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------------------------------------------------------- 12. ACTIVITY */

  async function renderActivity() {
    loading();
    const d = await NOVA.api('/api/anbar/activity?limit=200');
    panel(`<div class="anbar-split">
      <div class="card">
        <div class="anbar-section-title"><div><h3>Stock movement ledger</h3>
          <p>Every gram in and out, append-only. This is the audit trail.</p></div></div>
        ${table([{ label: 'When' }, { label: 'Item' }, { label: 'Movement' },
                 { label: 'Qty', num: true }, { label: 'Balance', num: true },
                 { label: 'Value', num: true }, { label: 'By' }],
          d.ledger.map(t => `<tr>
            <td class="primary">${esc(t.at)}</td>
            <td data-label="Item">${esc(t.item)}</td>
            <td data-label="Movement">${esc(TXN_LABEL[t.type] || t.type)}</td>
            <td class="num" data-label="Qty" style="color:${t.qty < 0 ? 'var(--coral)' : 'var(--mint)'}">
              ${t.qty > 0 ? '+' : ''}${num(t.qty, 3)}</td>
            <td class="num" data-label="Balance">${num(t.balance, 3)}</td>
            <td class="num" data-label="Value">${money(t.value)}</td>
            <td data-label="By" class="muted">${esc(t.by)}${t.reason ? '<br><span style="font-size:11px">' + esc(t.reason) + '</span>' : ''}</td></tr>`),
          { stack: true, empty: 'No stock has moved yet. Settle a bill, receive a delivery or log waste and it appears here.' })}
      </div>
      <div class="card">
        <div class="anbar-section-title"><div><h3>Warehouse actions</h3>
          <p>Who changed what, and what it was before.</p></div></div>
        ${d.audit.length ? d.audit.map(a => `<div class="anbar-alert info">
          <div class="anbar-alert-body"><b>${esc(a.action)}</b>
            <p>${esc(a.detail)}</p>
            <p class="muted" style="font-size:11px;margin-top:4px">${esc(a.by)} · ${esc(a.at)}</p></div>
        </div>`).join('') : '<div class="anbar-empty"><p>No warehouse actions recorded yet.</p></div>'}
      </div>
    </div>`);
  }

  /* ---------------------------------------------------------- router */

  const TABS = {
    overview: renderOverview, inventory: renderInventory, receiving: renderReceiving,
    purchases: renderPurchases, suppliers: renderSuppliers, transfers: renderTransfers,
    stocktake: renderStocktake, waste: renderWaste, recipes: renderRecipes, usage: renderUsage,
    intelligence: renderIntelligence, reports: renderReports, activity: renderActivity,
  };

  async function go(tab) {
    state.tab = tab;
    closeDrawer();
    document.querySelectorAll('.anbar-tab').forEach(b =>
      b.classList.toggle('on', b.dataset.tab === tab));
    try { history.replaceState(null, '', '#' + tab); } catch { /* file:// */ }
    try {
      await TABS[tab]();
    } catch (e) {
      panel(`<div class="anbar-empty"><b>That section could not load</b>
        <p>${esc(e.message || String(e))}</p>
        <button class="btn solid" onclick="location.reload()">Reload</button></div>`);
      console.error('[anbar]', tab, e);
    }
    applyI18n();
  }

  window.bootAnbar = async function bootAnbar() {
    document.querySelectorAll('.anbar-tab').forEach(b => {
      b.onclick = () => go(b.dataset.tab);
    });
    const wanted = (location.hash || '').replace('#', '');
    await go(TABS[wanted] ? wanted : 'overview');
  };
})();
