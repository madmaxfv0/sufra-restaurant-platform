// Living top-down map. Canvas 2D: still plate + animated light, greenery
// sway, water shimmer, and table hotspots tinted by live availability.

export class LivingMap {
  constructor(canvas, opts = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false });
    this.onPick = opts.onPick || (() => {});
    this.onHover = opts.onHover || (() => {});

    this.ground = null;
    this.venue = null;
    this.tables = [];
    this.states = {};
    this.highlight = new Set();
    this.selected = null;
    this.hovered = null;

    this.cam = { x: 360, y: 640, zoom: 1, t: 0 };
    this.target = null;
    this.t0 = performance.now();
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.walkers = [];
    this.paused = false;
    this.onDeepZoom = opts.onDeepZoom || (() => {});
    this._deepFired = null;
    // live conditions, replaced by the venue's real weather once fetched
    this.wx = { wind: 8, rain: 0, cloud: 0.4, isDay: 0, temp: 14, code: 0, label: '' };
    this.drops = [];
    this.clouds = [];
    for (let i = 0; i < 7; i++) this.clouds.push({
      x: Math.random() * 900 - 100, y: Math.random() * 1400 - 100,
      r: 180 + Math.random() * 260, s: 0.4 + Math.random() * 0.9 });

    this._bind();
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  async load(venue) {
    this.venue = venue.venue;
    this.geo = this.venue.geometry;
    this.mapW = this.venue.map.width;
    this.mapH = this.venue.map.height;
    this.ground = await loadImage(this.venue.map.image);
    this.fit();
    (this.geo.walk_paths || []).forEach((p, i) => {
      this.walkers.push({ path: p, u: Math.random(), speed: 0.00006 + i * 0.00002,
                          waiter: i < 2 });
    });
    this.loop();
  }

  setTables(tables) { this.tables = tables; }
  setStates(states) { this.states = states; }
  setHighlight(ids) { this.highlight = new Set(ids || []); }
  setSelected(id) { this.selected = id; }

  setWeather(w) {
    this.wx = Object.assign(this.wx, w);
    const n = Math.round(this.wx.rain > 0 ? 260 + this.wx.rain * 90 : 0);
    this.drops = [];
    for (let i = 0; i < Math.min(700, n); i++) this.drops.push({
      x: Math.random() * this.mapW, y: Math.random() * this.mapH,
      l: 6 + Math.random() * 12, v: 260 + Math.random() * 260 });
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    this.cv.width = Math.max(1, Math.round(r.width * this.dpr));
    this.cv.height = Math.max(1, Math.round(r.height * this.dpr));
    this.vw = r.width; this.vh = r.height;
    if (this.mapW) this.clampCam();
  }

  // --- camera -------------------------------------------------------
  baseScale() { return Math.max(this.vw / this.mapW, this.vh / this.mapH); }
  scale() { return this.baseScale() * this.cam.zoom; }

  fit(animated = false) {
    const z = Math.min(this.vw / this.mapW, this.vh / this.mapH) / this.baseScale();
    this.moveTo(this.mapW / 2, this.mapH / 2, Math.max(z, 0.62), animated ? 900 : 0);
  }

  moveTo(x, y, zoom, ms = 900) {
    if (!ms) { this.cam.x = x; this.cam.y = y; this.cam.zoom = zoom; this.clampCam(); return; }
    this.target = { from: { ...this.cam }, to: { x, y, zoom },
                    start: performance.now(), ms };
  }

  focusTable(id, zoom = 3.0) {
    const t = this.tables.find(t => t.id === id);
    if (t) this.moveTo(t.x, t.y, zoom, 1000);
  }

  clampCam() {
    const s = this.scale();
    const halfW = this.vw / (2 * s), halfH = this.vh / (2 * s);
    if (this.mapW * s <= this.vw) this.cam.x = this.mapW / 2;
    else this.cam.x = Math.min(this.mapW - halfW, Math.max(halfW, this.cam.x));
    if (this.mapH * s <= this.vh) this.cam.y = this.mapH / 2;
    else this.cam.y = Math.min(this.mapH - halfH, Math.max(halfH, this.cam.y));
  }

  toScreen(mx, my) {
    const s = this.scale();
    return [(mx - this.cam.x) * s + this.vw / 2, (my - this.cam.y) * s + this.vh / 2];
  }

  toMap(sx, sy) {
    const s = this.scale();
    return [(sx - this.vw / 2) / s + this.cam.x, (sy - this.vh / 2) / s + this.cam.y];
  }

  // --- input --------------------------------------------------------
  _bind() {
    const cv = this.cv;
    let drag = null, pinch = null, moved = 0;

    const pos = e => {
      const r = cv.getBoundingClientRect();
      const p = e.touches ? e.touches[0] : e;
      return [p.clientX - r.left, p.clientY - r.top];
    };

    cv.addEventListener('pointerdown', e => {
      cv.setPointerCapture(e.pointerId);
      drag = { p: pos(e), cam: { ...this.cam } }; moved = 0; this.target = null;
    });

    cv.addEventListener('pointermove', e => {
      const p = pos(e);
      if (drag) {
        const s = this.scale();
        moved += Math.abs(p[0] - drag.p[0]) + Math.abs(p[1] - drag.p[1]);
        this.cam.x = drag.cam.x - (p[0] - drag.p[0]) / s;
        this.cam.y = drag.cam.y - (p[1] - drag.p[1]) / s;
        this.clampCam();
      } else {
        const hit = this.hitTest(p[0], p[1]);
        const id = hit ? hit.id : null;
        if (id !== this.hovered) {
          this.hovered = id;
          cv.style.cursor = id ? 'pointer' : 'grab';
          this.onHover(hit, p);
        }
      }
    });

    const up = e => {
      if (drag && moved < 6) {
        const p = pos(e);
        const hit = this.hitTest(p[0], p[1]);
        if (hit) this.onPick(hit);
      }
      drag = null;
    };
    cv.addEventListener('pointerup', up);
    cv.addEventListener('pointercancel', () => { drag = null; });

    cv.addEventListener('wheel', e => {
      e.preventDefault();
      this.target = null;
      const [mx, my] = this.toMap(...pos(e));
      const k = Math.exp(-e.deltaY * 0.0016);
      const z = Math.min(6, Math.max(0.55, this.cam.zoom * k));
      const ratio = 1 - this.cam.zoom / z;
      this.cam.x += (mx - this.cam.x) * ratio;
      this.cam.y += (my - this.cam.y) * ratio;
      this.cam.zoom = z;
      this.clampCam();
    }, { passive: false });

    cv.addEventListener('touchstart', e => {
      if (e.touches.length === 2) {
        pinch = { d: touchDist(e), zoom: this.cam.zoom };
      }
    }, { passive: true });
    cv.addEventListener('touchmove', e => {
      if (pinch && e.touches.length === 2) {
        e.preventDefault();
        this.cam.zoom = Math.min(6, Math.max(0.55, pinch.zoom * touchDist(e) / pinch.d));
        this.clampCam();
      }
    }, { passive: false });
    cv.addEventListener('touchend', () => { pinch = null; });
  }

  hitTest(sx, sy) {
    const [mx, my] = this.toMap(sx, sy);
    let best = null, bestD = 1e9;
    for (const t of this.tables) {
      const rx = Math.max(t.w, 44) / 2 + 16, ry = Math.max(t.h, 44) / 2 + 16;
      const dx = (mx - t.x) / rx, dy = (my - t.y) / ry;
      const d = dx * dx + dy * dy;
      if (d < 1 && d < bestD) { best = t; bestD = d; }
    }
    return best;
  }

  // --- render -------------------------------------------------------
  loop() {
    const step = () => {
      this.draw();
      requestAnimationFrame(step);
    };
    step();
  }

  draw() {
    const now = performance.now();
    const time = (now - this.t0) / 1000;
    const ctx = this.ctx;

    if (this.target) {
      const k = Math.min(1, (now - this.target.start) / this.target.ms);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      const f = this.target.from, t = this.target.to;
      this.cam.x = f.x + (t.x - f.x) * e;
      this.cam.y = f.y + (t.y - f.y) * e;
      this.cam.zoom = f.zoom + (t.zoom - f.zoom) * e;
      this.clampCam();
      if (k >= 1) this.target = null;
    }

    ctx.save();
    ctx.scale(this.dpr, this.dpr);
    ctx.fillStyle = '#05090f';
    ctx.fillRect(0, 0, this.vw, this.vh);

    if (!this.ground) { ctx.restore(); return; }
    const s = this.scale();
    const ox = this.vw / 2 - this.cam.x * s, oy = this.vh / 2 - this.cam.y * s;

    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(this.ground, ox, oy, this.mapW * s, this.mapH * s);

    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(s, s);

    this.drawDaylight(ctx);
    this.drawWater(ctx, time);
    this.drawGreenery(ctx, time);
    this.drawLamps(ctx, time);
    this.drawWalkers(ctx, time);
    this.drawTables(ctx, time);
    this.drawClouds(ctx, time);
    this.drawRain(ctx, time);

    ctx.restore();
    ctx.restore();

    // deep zoom on a table hands off to the 360 view
    if (this.cam.zoom > 4.0) {
      const near = this.nearestTable(this.cam.x, this.cam.y);
      if (near && this._deepFired !== near.id) {
        this._deepFired = near.id;
        this.onDeepZoom(near);
      }
    } else if (this.cam.zoom < 3.2) this._deepFired = null;
  }

  nearestTable(x, y) {
    let best = null, bd = 1e9;
    for (const t of this.tables) {
      const d = Math.hypot(t.x - x, t.y - y);
      if (d < bd) { best = t; bd = d; }
    }
    return bd < 90 ? best : null;
  }

  drawDaylight(ctx) {
    // shifts the whole plate between daylight and night by real conditions
    const day = this.wx.isDay ? 1 : 0;
    const overcast = this.wx.cloud;
    if (day) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = `rgba(${130 - overcast * 50},${150 - overcast * 46},${168 - overcast * 40},${0.30 - overcast * 0.10})`;
      ctx.fillRect(0, 0, this.mapW, this.mapH);
      ctx.restore();
      ctx.save();
      ctx.globalCompositeOperation = 'saturation';
      ctx.restore();
    } else if (overcast > 0.5) {
      ctx.save();
      ctx.fillStyle = `rgba(10,16,30,${(overcast - 0.5) * 0.30})`;
      ctx.fillRect(0, 0, this.mapW, this.mapH);
      ctx.restore();
    }
  }

  drawClouds(ctx, t) {
    if (this.wx.cloud < 0.18) return;
    const drift = (this.wx.wind || 6) * 0.5;
    ctx.save();
    ctx.globalAlpha = Math.min(0.30, this.wx.cloud * 0.30);
    for (const c of this.clouds) {
      const x = ((c.x + t * drift * c.s) % (this.mapW + 500)) - 250;
      const y = ((c.y + t * drift * c.s * 0.35) % (this.mapH + 500)) - 250;
      const g = ctx.createRadialGradient(x, y, 1, x, y, c.r);
      g.addColorStop(0, 'rgba(6,10,20,0.85)');
      g.addColorStop(1, 'rgba(6,10,20,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, c.r, 0, 6.2832); ctx.fill();
    }
    ctx.restore();
  }

  drawRain(ctx, t) {
    if (!this.drops.length) return;
    const lean = (this.wx.wind || 8) * 0.05;
    ctx.save();
    ctx.strokeStyle = 'rgba(178,206,232,0.34)';
    ctx.lineWidth = 0.7;
    ctx.beginPath();
    for (const d of this.drops) {
      const y = (d.y + t * d.v) % this.mapH;
      const x = (d.x + y * lean) % this.mapW;
      ctx.moveTo(x, y); ctx.lineTo(x - d.l * lean * 0.5, y + d.l);
    }
    ctx.stroke();
    // splash sparkle on the deck and lobby
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 26; i++) {
      const x = 150 + Math.random() * 100, y = 250 + Math.random() * 790;
      ctx.fillStyle = 'rgba(190,215,240,0.16)';
      ctx.beginPath(); ctx.arc(x, y, 1 + Math.random() * 2.5, 0, 6.2832); ctx.fill();
    }
    ctx.restore();
  }

  drawWater(ctx, t) {
    const [x1, y1, x2, y2] = this.geo.sea || this.geo.water || [0, 0, 0, 0];
    if (x2 <= x1) return;
    ctx.save();
    ctx.beginPath(); ctx.rect(x1, y1, x2 - x1, y2 - y1); ctx.clip();
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < 70; i++) {
      const yy = y1 + ((i * 97 + t * (10 + this.wx.wind * 1.2)) % (y2 - y1));
      const xx = x1 + 6 + ((i * 37) % (x2 - x1 - 14));
      const a = 0.10 + 0.08 * Math.sin(t * (1.2 + this.wx.wind * 0.05) + i)
                + Math.min(0.10, this.wx.wind * 0.004);
      ctx.fillStyle = `rgba(150,200,240,${a})`;
      ctx.fillRect(xx, yy, 16 + 10 * Math.sin(t + i), 1.6);
    }
    // swell rolling toward the deck
    for (let i = 0; i < 14; i++) {
      const yy = y1 + ((i * 91 + t * (18 + this.wx.wind * 1.6)) % (y2 - y1));
      ctx.fillStyle = `rgba(150,196,232,${0.05 + 0.04 * Math.sin(t + i)})`;
      ctx.fillRect(x1 + 4, yy, x2 - x1 - 10, 2.4);
    }
    ctx.restore();
  }

  drawGreenery(ctx, t) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    (this.geo.trees || []).forEach((tr, i) => {
      const [cx, cy, r] = tr;
      const gust = 1 + 0.35 * Math.sin(t * 0.33 + i);
      const sway = Math.sin(t * (0.45 + this.wx.wind * 0.035) + i * 1.3)
                 * (0.9 + this.wx.wind * 0.16) * gust;
      const puff = 0.5 + 0.5 * Math.sin(t * 0.5 + i);
      const g = ctx.createRadialGradient(cx + sway, cy - 1, 1, cx + sway, cy, r);
      g.addColorStop(0, `rgba(150,200,120,${0.10 + 0.05 * puff})`);
      g.addColorStop(1, 'rgba(60,110,60,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(cx + sway, cy, r, 0, 6.2832); ctx.fill();
    });
    ctx.restore();
  }

  drawLamps(ctx, t) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    (this.geo.lamps || []).forEach(([cx, cy], i) => {
      const f = 0.82 + 0.18 * Math.sin(t * 2.1 + i * 2.3) +
                0.05 * Math.sin(t * 7.3 + i);
      const g = ctx.createRadialGradient(cx, cy, 1, cx, cy, 34);
      g.addColorStop(0, `rgba(255,206,140,${0.30 * f})`);
      g.addColorStop(1, 'rgba(255,180,90,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(cx, cy, 34, 0, 6.2832); ctx.fill();
    });
    ctx.restore();
  }

  drawWalkers(ctx, t) {
    ctx.save();
    this.walkers.forEach(w => {
      w.u = (w.u + w.speed * 16 * (this.wx.rain > 0.4 ? 1.55 : 1)) % 1;
      const p = w.path, n = p.length - 1;
      const f = w.u * n, i = Math.min(n - 1, Math.floor(f)), k = f - i;
      const x = p[i][0] + (p[i + 1][0] - p[i][0]) * k;
      const y = p[i][1] + (p[i + 1][1] - p[i][1]) * k;
      ctx.fillStyle = w.waiter ? 'rgba(232,224,206,0.72)' : 'rgba(196,176,150,0.55)';
      ctx.beginPath(); ctx.arc(x, y, 5.2, 0, 6.2832); ctx.fill();
      ctx.fillStyle = 'rgba(0,0,0,0.35)';
      ctx.beginPath(); ctx.arc(x + 1.4, y + 2, 4.4, 0, 6.2832); ctx.fill();
    });
    ctx.restore();
  }

  drawTables(ctx, t) {
    const s = this.scale();
    const showLabels = this.cam.zoom > 1.05;

    for (const tb of this.tables) {
      const st = (this.states[tb.id] || {}).state || 'UNKNOWN';
      const sel = this.selected === tb.id;
      const hot = this.highlight.has(tb.id);
      const hov = this.hovered === tb.id;
      const r = Math.max(tb.w, tb.h) / 2 + 12;

      // candle flicker on every table, warmer when it's yours
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      const f = 0.75 + 0.25 * Math.sin(t * 3.1 + tb.x * 0.05) +
                0.08 * Math.sin(t * 11 + tb.y);
      const g = ctx.createRadialGradient(tb.x, tb.y, 1, tb.x, tb.y, r * 1.5);
      g.addColorStop(0, `rgba(255,190,110,${0.22 * f})`);
      g.addColorStop(1, 'rgba(255,150,60,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(tb.x, tb.y, r * 1.5, 0, 6.2832); ctx.fill();
      ctx.restore();

      const style = {
        AVAILABLE:    ['rgba(126,214,196,0.95)', 'rgba(126,214,196,0.14)'],
        HELD_BY_YOU:  ['rgba(232,182,92,1)',     'rgba(232,182,92,0.24)'],
        HELD:         ['rgba(214,152,72,0.75)',  'rgba(214,152,72,0.10)'],
        RESERVED:     ['rgba(150,150,160,0.28)', 'rgba(0,0,0,0.16)'],
        INCOMPATIBLE: ['rgba(150,150,160,0.20)', 'rgba(0,0,0,0.12)'],
        UNKNOWN:      ['rgba(200,200,210,0.22)', 'rgba(0,0,0,0)'],
      }[st];

      ctx.save();
      if (hot || sel) {
        const pulse = 0.55 + 0.45 * Math.sin(t * 2.4);
        ctx.strokeStyle = sel ? 'rgba(240,214,150,1)' : `rgba(216,178,108,${0.5 + 0.4 * pulse})`;
        ctx.lineWidth = (sel ? 3.4 : 2.4) / this.cam.zoom * 1.4;
        ctx.beginPath(); ctx.arc(tb.x, tb.y, r + 5 + (sel ? 2 * pulse : 0), 0, 6.2832);
        ctx.stroke();
      }
      ctx.fillStyle = style[1];
      ctx.beginPath(); ctx.arc(tb.x, tb.y, r, 0, 6.2832); ctx.fill();
      ctx.strokeStyle = style[0];
      ctx.lineWidth = (hov ? 2.6 : 1.6) / this.cam.zoom * 1.4;
      ctx.beginPath(); ctx.arc(tb.x, tb.y, r, 0, 6.2832); ctx.stroke();

      if (st === 'RESERVED' || st === 'INCOMPATIBLE') {
        ctx.strokeStyle = 'rgba(230,230,240,0.28)';
        ctx.lineWidth = 1.4 / this.cam.zoom * 1.4;
        ctx.beginPath();
        ctx.moveTo(tb.x - r * 0.6, tb.y - r * 0.6);
        ctx.lineTo(tb.x + r * 0.6, tb.y + r * 0.6);
        ctx.stroke();
      }

      if (showLabels || hov || sel || hot) {
        const fs = Math.max(9, 13 / this.cam.zoom);
        ctx.font = `600 ${fs}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const w = ctx.measureText(tb.label).width + fs * 1.1;
        ctx.fillStyle = 'rgba(8,14,24,0.78)';
        roundRect(ctx, tb.x - w / 2, tb.y - r - fs * 1.9, w, fs * 1.5, fs * 0.5);
        ctx.fill();
        ctx.fillStyle = st === 'AVAILABLE' ? '#cfeee5'
          : st === 'HELD_BY_YOU' ? '#f0d296' : 'rgba(220,220,230,0.6)';
        ctx.fillText(tb.label, tb.x, tb.y - r - fs * 1.15);
      }
      ctx.restore();
    }
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function touchDist(e) {
  const a = e.touches[0], b = e.touches[1];
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}

export function loadImage(src) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = () => rej(new Error('image failed: ' + src));
    im.src = src;
  });
}
