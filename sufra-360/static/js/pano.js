// Equirectangular 360 viewer.
//
// Renders with canvas 2D by slicing the panorama into vertical columns and
// reprojecting each one. No WebGL, no shaders, no library - so it works on
// every browser including old Safari, and it cannot fail to initialise.
//
// Drag to look, wheel or pinch to zoom, gyroscope on phones, and a
// side-by-side stereo mode for a cardboard headset.

const DEG = Math.PI / 180;

export class PanoViewer {
  constructor(canvas) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.img = null;
    this.yaw = 0; this.pitch = 0; this.fov = 82;
    this.targetYaw = null;
    this.stereo = false;
    this.gyro = false;
    this.fade = 0;
    this.running = false;
    this.step = 3;                       // column width in CSS pixels
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.ok = !!this.ctx;
    this.error = this.ok ? null : 'This browser has no 2D canvas.';
    this._bind();
    this.resize();
    this._onResize = () => this.resize();
    window.addEventListener('resize', this._onResize);
  }

  load(url, yaw) {
    this.yaw = yaw || 0;
    this.pitch = 0;
    this.fade = 0;
    this.error = null;
    return new Promise((resolve) => {
      const im = new Image();
      im.onload = () => {
        this.img = im;
        this.resize();
        this.start();
        resolve(true);
      };
      im.onerror = () => {
        this.img = null;
        this.error = 'The 360 image did not load: ' + url;
        this.start();
        resolve(false);
      };
      im.src = url;
    });
  }

  resize() {
    const r = this.cv.getBoundingClientRect();
    const w = Math.max(1, Math.round(r.width));
    const h = Math.max(1, Math.round(r.height));
    this.vw = w; this.vh = h;
    this.cv.width = Math.round(w * this.dpr);
    this.cv.height = Math.round(h * this.dpr);
  }

  start() { if (!this.running) { this.running = true; this._loop(); } }
  stop() { this.running = false; }

  lookAt(yaw, ms) {
    this.targetYaw = { from: this.yaw, to: yaw,
                       start: Date.now(), ms: ms || 700 };
  }

  setStereo(on) { this.stereo = on; }

  /** Screen x for a compass bearing, or null when it is behind you. */
  screenXFor(bearing) {
    let d = ((bearing - this.yaw + 540) % 360) - 180;
    if (Math.abs(d) > 88) return null;
    const f = (this.vw / 2) / Math.tan(this.fov * DEG / 2);
    const x = this.vw / 2 + Math.tan(d * DEG) * f;
    if (x < -60 || x > this.vw + 60) return null;
    return x;
  }

  async enableGyro() {
    const DOE = window.DeviceOrientationEvent;
    if (!DOE) return false;
    if (typeof DOE.requestPermission === 'function') {
      try {
        const r = await DOE.requestPermission();
        if (r !== 'granted') return false;
      } catch (e) { return false; }
    }
    this.gyro = true;
    this._base = null;
    this._onGyro = (e) => {
      if (e.alpha == null) return;
      if (this._base === null) this._base = e.alpha - this.yaw;
      this.yaw = (e.alpha - this._base) % 360;
      const b = typeof e.beta === 'number' ? e.beta : 90;
      this.pitch = Math.max(-70, Math.min(70, b - 90));
    };
    window.addEventListener('deviceorientation', this._onGyro);
    return true;
  }

  disableGyro() {
    this.gyro = false;
    if (this._onGyro) window.removeEventListener('deviceorientation', this._onGyro);
  }

  _bind() {
    const cv = this.cv;
    let drag = null, pinch = null;
    cv.style.cursor = 'grab';

    const down = (e) => {
      if (this.gyro) return;
      const p = e.touches ? e.touches[0] : e;
      drag = { x: p.clientX, y: p.clientY, yaw: this.yaw, pitch: this.pitch };
      this.targetYaw = null;
      cv.style.cursor = 'grabbing';
    };
    const move = (e) => {
      if (!drag) return;
      const p = e.touches ? e.touches[0] : e;
      const k = this.fov / Math.max(1, this.vw) * 1.9;
      this.yaw = drag.yaw - (p.clientX - drag.x) * k;
      this.pitch = Math.max(-78, Math.min(78, drag.pitch + (p.clientY - drag.y) * k));
    };
    const up = () => { drag = null; cv.style.cursor = 'grab'; };

    cv.addEventListener('mousedown', down);
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
    cv.addEventListener('touchstart', (e) => {
      if (e.touches.length === 2) { pinch = { d: tdist(e), fov: this.fov }; drag = null; }
      else down(e);
    }, { passive: true });
    cv.addEventListener('touchmove', (e) => {
      if (pinch && e.touches.length === 2) {
        e.preventDefault();
        this.fov = Math.max(38, Math.min(100, pinch.fov * pinch.d / tdist(e)));
      } else { move(e); }
    }, { passive: false });
    cv.addEventListener('touchend', () => { pinch = null; up(); });

    cv.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.fov = Math.max(38, Math.min(100, this.fov + e.deltaY * 0.05));
    }, { passive: false });
  }

  _loop() {
    if (!this.running) return;
    const raf = window.requestAnimationFrame ||
                ((f) => setTimeout(f, 16));
    raf(() => this._loop());

    if (this.targetYaw) {
      const k = Math.min(1, (Date.now() - this.targetYaw.start) / this.targetYaw.ms);
      const e = 1 - Math.pow(1 - k, 3);
      let d = ((this.targetYaw.to - this.targetYaw.from + 540) % 360) - 180;
      this.yaw = this.targetYaw.from + d * e;
      if (k >= 1) this.targetYaw = null;
    }
    this.fade = Math.min(1, this.fade + 0.05);
    this._draw();
  }

  _draw() {
    const ctx = this.ctx;
    if (!ctx) return;
    const W = this.cv.width, H = this.cv.height;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = '#070c16';
    ctx.fillRect(0, 0, W, H);

    if (!this.img) {
      if (this.error) {
        ctx.fillStyle = '#e0817b';
        ctx.font = (14 * this.dpr) + 'px -apple-system, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(this.error, W / 2, H / 2);
      }
      return;
    }

    ctx.save();
    ctx.scale(this.dpr, this.dpr);
    ctx.globalAlpha = this.fade;

    if (this.stereo) {
      this._panel(ctx, 0, 0, this.vw / 2, this.vh, this.yaw - 1.4);
      this._panel(ctx, this.vw / 2, 0, this.vw / 2, this.vh, this.yaw + 1.4);
    } else {
      this._panel(ctx, 0, 0, this.vw, this.vh, this.yaw);
    }

    ctx.globalAlpha = 1;
    ctx.restore();
  }

  _panel(ctx, ox, oy, w, h, yaw) {
    const img = this.img;
    const iw = img.width, ih = img.height;
    const f = (w / 2) / Math.tan(this.fov * DEG / 2);
    const step = this.step;

    ctx.save();
    ctx.beginPath();
    ctx.rect(ox, oy, w, h);
    ctx.clip();

    for (let x = 0; x < w; x += step) {
      const cx = x + step / 2 - w / 2;
      // horizontal angle of this column
      const theta = Math.atan(cx / f);
      let sx = ((yaw + theta / DEG) / 360) * iw;
      sx = ((sx % iw) + iw) % iw;

      // the column is further from the eye as it moves off centre, so it
      // covers a smaller vertical angle - this is what stops the stretch
      const dist = f / Math.cos(theta);
      const vspan = 2 * Math.atan((h / 2) / dist);          // radians
      let sh = (vspan / Math.PI) * ih;
      let sy = ((90 - this.pitch) / 180) * ih - sh / 2;

      // clamp at the poles without distorting what remains
      let dy = oy, dh = h;
      if (sy < 0) { dh = h * (1 + sy / sh); dy = oy + (h - dh); sh += sy; sy = 0; }
      if (sy + sh > ih) { const over = sy + sh - ih; dh = h * (1 - over / sh); sh -= over; }
      if (sh <= 0 || dh <= 0) continue;

      const sw = Math.max(1, (step / w) * (this.fov / 360) * iw);
      if (sx + sw <= iw) {
        ctx.drawImage(img, sx, sy, sw, sh, ox + x, dy, step + 1, dh);
      } else {
        const a = iw - sx;
        ctx.drawImage(img, sx, sy, a, sh, ox + x, dy, (step + 1) * (a / sw), dh);
        ctx.drawImage(img, 0, sy, sw - a, sh,
                      ox + x + (step + 1) * (a / sw), dy,
                      (step + 1) * (1 - a / sw), dh);
      }
    }
    ctx.restore();
  }
}

function tdist(e) {
  const a = e.touches[0], b = e.touches[1];
  return Math.sqrt(Math.pow(a.clientX - b.clientX, 2) +
                   Math.pow(a.clientY - b.clientY, 2));
}
