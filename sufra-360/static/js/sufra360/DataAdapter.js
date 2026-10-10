// DataAdapter - the single place SUFRA 360 touches the backend.
// Every other module asks this one; none of them know a URL.

// Every fetch gets a deadline. Without one the first table-feed poll - which
// fires during the build, while dozens of GLB, HDR and texture requests are
// already saturating the six-connection-per-host limit - could queue behind
// them and simply never settle. Nothing timed it out and nothing retried it,
// so the status strip sat on its placeholder dashes for the whole session
// while the scene itself looked fine. A stalled request now fails fast and
// the next poll picks it up.
// Deliberately generous. During the build the main thread is saturated
// building the scene, and a response can sit fully received but unparsed
// because no microtask gets to run - the request is not stuck, the CPU is.
// A short deadline aborts work that would have succeeded; this only catches
// a genuinely dead request, with the retry below covering the rest.
const TIMEOUT_MS = 30000;
const J = async (u, opts) => {
  const r = await fetch(u, Object.assign(
    { credentials: 'same-origin', signal: AbortSignal.timeout(TIMEOUT_MS) }, opts || {}));
  if (!r.ok) throw new Error(u + ' -> ' + r.status);
  return r.json();
};
const POST = (u, body) => J(u, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

// Booking is the one place where a rejection is more useful than an exception:
// the server answers 400 or 409 with a real reason ("Table 7 seats 2-4",
// "We seat between 12:00 and 22:30", "that slot was just taken"). This keeps
// the body so the drawer can show the guest what actually went wrong.
const REASONS = {
  capacity: 'That party size does not fit this table.',
  closed: 'We are not seating at that time.',
  conflict: 'That slot was taken a moment ago. Please pick another time.',
  bad_email: 'That email address does not look right.',
  bad_date: 'Please choose a valid date.',
  missing_fields: 'Some details are still missing.',
  unknown_table: 'That table is no longer available.',
  hold_expired: 'Your hold ran out. Please choose a time again.',
};
const POST_SOFT = async (u, body) => {
  const r = await fetch(u, {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  let d = null;
  try { d = await r.json(); } catch (e) {}
  if (!d) return { ok: false, message: 'The restaurant did not answer (' + r.status + ').' };
  if (d.ok) return d;
  return Object.assign({ ok: false }, d, {
    message: d.message || REASONS[d.error] || 'That booking was refused.',
  });
};

export const DataAdapter = {
  /** venue geometry, zones, service hours (existing) */
  venue: () => J('/api/public/venue'),
  /** tables with x/y/w/h/zone/shape/scores/attributes (existing + build 9 attributes) */
  tables: () => J('/api/public/tables'),
  /** every seat in one round trip (build 9); falls back to one request per table on an older server */
  async seats(tables) {
    try { return await J('/api/public/seats'); }
    catch (e) { return (await Promise.all(tables.map(t => J('/api/public/tables/' + t.id + '/seats').catch(() => [])))).flat(); }
  },
  /** CAN THIS BE BOOKED for a chosen date and time - not who is sitting there now */
  availability: (date, time, party) =>
    J('/api/public/availability?date=' + date + '&time=' + time + '&party_size=' + party),
  /** a short hold while the guest fills in the form; the server still re-checks */
  hold: (tableId, date, time, party) =>
    POST_SOFT('/api/public/holds', { table_id: tableId, date, time, party_size: party }),
  /** create the booking - one row, in SUFRA OS, the same one the manager sees */
  reserve: (payload) => POST_SOFT('/api/public/reservations', payload),
  /** join the restaurant's ONE waitlist */
  waitlist: (payload) => POST_SOFT('/api/public/waitlist', payload),
  /** the guide */
  guide: (question, date, time, party) =>
    POST('/api/public/guide', { question, date, time, party_size: party }),
  /** WHAT IS HAPPENING NOW: physical state of every table */
  live: () => J('/api/public/live'),
  /** the one menu, from the kitchen's own dish records */
  menu: () => J('/api/public/menu'),
  /** cached venue weather */
  weather: () => J('/api/weather'),
  /** a guest's own reservation, by its reference */
  reservation: (code) => J('/api/public/reservations/' + encodeURIComponent(code)),
  /** a guest cancelling their own booking */
  cancel: (code) => POST_SOFT('/api/public/reservations/' + encodeURIComponent(code) + '/cancel'),

  /** the live push. TABLE_HELD / HOLD_RELEASED / RESERVATION_CREATED /
   *  RESERVATION_CANCELLED / WAITLIST_ADDED are raised by this application;
   *  STATE is relayed from SUFRA OS and means the restaurant itself changed -
   *  a table seated or freed, a booking moved, a dish taken off the menu. */
  subscribe(onEvent, onState) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    let ws, tries = 0, opened = false;
    const open = () => {
      try { ws = new WebSocket(proto + '://' + location.host + '/ws'); }
      catch (e) { onState && onState('unavailable'); return; }
      ws.onopen = () => { opened = true; tries = 0; onState && onState('live'); };
      ws.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (err) {} };
      ws.onclose = () => {
        onState && onState('polling');
        tries += 1;
        if (!opened && tries >= 3) return;
        if (tries > 8) return;
        setTimeout(open, Math.min(30000, 600 * Math.pow(2, tries)));
      };
      ws.onerror = () => { try { ws.close(); } catch (e) {} };
    };
    open();
    return () => { try { ws && ws.close(); } catch (e) {} };
  },

  /** map-unit → metre conversion shared by everything that places geometry */
  toWorld(mx, my, mapW, mapH, unitsToM) {
    return [(mx - mapW / 2) * unitsToM, (my - mapH / 2) * unitsToM];
  },
};
