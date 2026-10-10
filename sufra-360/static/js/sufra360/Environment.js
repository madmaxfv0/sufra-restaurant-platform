import * as THREE from '/static/vendor/three/three.module.js';

// ------------------------------------------------------------- environment
/**
 * Sun, sky dome, fog, exposure, environment map. Driven by the venue's
 * local clock unless the user overrides the time of day.
 *
 * Build 9: only the HDR the current hour needs is loaded before the scene
 * shows; the other two arrive in the background. Stars at night. Tighter
 * shadow frustum (sharper shadows for the same map size).
 */
export class EnvironmentManager {
  constructor(scene, renderer, assets, timezone, shadowSize) {
    this.scene = scene;
    this.renderer = renderer;
    this.assets = assets;
    this.tz = timezone || 'Asia/Baku';
    this.override = 'auto';          // auto | day | sunset | night
    this.cloud = 0.3;
    this.fogAmount = 0;
    this.lightning = 0;

    this.sun = new THREE.DirectionalLight(0xfff1dc, 2.2);
    this.sun.castShadow = shadowSize > 0;
    this.sun.shadow.mapSize.set(shadowSize || 1024, shadowSize || 1024);
    this.sun.shadow.bias = -0.0005;
    this.sun.shadow.normalBias = 0.025;
    const sc = this.sun.shadow.camera;
    sc.near = 1; sc.far = 220; sc.left = -38; sc.right = 38; sc.top = 38; sc.bottom = -38;
    this.sunTarget = new THREE.Object3D();
    scene.add(this.sun, this.sunTarget);
    this.sun.target = this.sunTarget;
    this.shadowSize = shadowSize;

    this.hemi = new THREE.HemisphereLight(0x8fb6e8, 0x3a2f24, 0.55);
    scene.add(this.hemi);

    this.sky = this.makeSky();
    scene.add(this.sky);
    // Thinner than it was: the old density fully swallowed anything past 200 m,
    // which was fine when the scene stopped there. It now has to leave the city
    // and the far water readable while still softening distance.
    scene.fog = new THREE.FogExp2(0x0a1220, 0.0016);
  }

  makeSky() {
    // 2 km, so the city at 780 m and the far water are inside the sky, not beyond it
    const geo = new THREE.SphereGeometry(2000, 32, 16);
    this.skyU = {
      uTop: { value: new THREE.Color(0x0b1730) }, uHorizon: { value: new THREE.Color(0x33456e) },
      uSunDir: { value: new THREE.Vector3(0, 1, 0) }, uSunGlow: { value: new THREE.Color(0xffb070) },
      uCloud: { value: 0.3 }, uFlash: { value: 0 }, uNight: { value: 0.5 },
    };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.skyU, side: THREE.BackSide, depthWrite: false, fog: false,
      vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: `
        uniform vec3 uTop, uHorizon, uSunDir, uSunGlow; uniform float uCloud, uFlash, uNight;
        varying vec3 vDir;
        float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 45.32); return fract(p.x * p.y); }
        void main(){
          vec3 d = normalize(vDir);
          float h = clamp(d.y, 0.0, 1.0);
          vec3 c = mix(uHorizon, uTop, pow(h, 0.55));
          float s = max(0.0, dot(d, normalize(uSunDir)));
          c += uSunGlow * pow(s, 18.0) * (1.0 - uCloud * 0.8) * 0.9;
          c = mix(c, vec3(0.42, 0.45, 0.50) * (0.35 + 0.65 * h), uCloud * 0.55);
          // a scatter of faint stars once the sun is well down; cloud hides them
          vec2 sp = vec2(atan(d.z, d.x), asin(clamp(d.y, -1.0, 1.0))) * 160.0;
          float st = step(0.9975, hash21(floor(sp))) * smoothstep(0.08, 0.35, h);
          c += vec3(0.85, 0.9, 1.0) * st * uNight * (1.0 - uCloud) * 0.55;
          c += vec3(uFlash);
          gl_FragColor = vec4(c, 1.0);
        }`,
    });
    return new THREE.Mesh(geo, mat);
  }

  /** just the HDR this hour needs; the rest are fetched once the scene is showing */
  async loadEnvironment() {
    const h = this.effectiveHour();
    const dayness = THREE.MathUtils.clamp(Math.cos((h - 13.2) / 7.2 * Math.PI * 0.5), 0, 1);
    const sunsetness = Math.exp(-Math.pow((h - 19.3) / 1.1, 2));
    const want = dayness > 0.55 ? 'day' : (dayness > 0.08 || sunsetness > 0.3) ? 'evening' : 'night';
    await this.loadOne(want);
    this.scene.environment = this.envEvening || this.envNight || this.envDay || null;
    this.scene.environmentIntensity = 0.5;
  }

  async loadOne(which) {
    if (which === 'night' && this.envNight === undefined) this.envNight = await this.assets.environment('hdri/potsdamer_platz_1k.hdr');
    if (which === 'evening' && this.envEvening === undefined) {
      this.envEvening = await this.assets.environment('hdri/kiara_1_dawn_1k.hdr') || await this.assets.environment('hdri/venice_sunset_1k.hdr');
    }
    if (which === 'day' && this.envDay === undefined) {
      this.envDay = await this.assets.environment('hdri/lebombo_1k.hdr') || await this.assets.environment('hdr/royal_esplanade_1k.hdr');
    }
  }

  /** the other two, in the background, so a time-of-day switch has them ready */
  async loadRest() {
    for (const w of ['evening', 'night', 'day']) { try { await this.loadOne(w); } catch (e) {} }
  }

  /** local hour as a float, in the venue's timezone */
  localHour() {
    try {
      const f = new Intl.DateTimeFormat('en-GB', { timeZone: this.tz, hour: 'numeric', minute: 'numeric', hour12: false });
      const parts = f.formatToParts(new Date());
      const h = +parts.find(p => p.type === 'hour').value;
      const m = +parts.find(p => p.type === 'minute').value;
      return (h % 24) + m / 60;
    } catch (e) { const d = new Date(); return d.getHours() + d.getMinutes() / 60; }
  }

  effectiveHour() {
    if (this.override === 'day') return 13.5;
    if (this.override === 'sunset') return 19.6;
    if (this.override === 'night') return 22.5;
    return this.localHour();
  }

  /** 0 at night, 1 at midday, with a warm shoulder around sunset */
  apply(weather, dt) {
    const h = this.effectiveHour();
    const dayness = THREE.MathUtils.clamp(Math.cos((h - 13.2) / 7.2 * Math.PI * 0.5), 0, 1); // 0 before 6/after 20.4
    const sunsetness = Math.exp(-Math.pow((h - 19.3) / 1.1, 2));
    const cloud = THREE.MathUtils.lerp(this.cloud, weather.cloud, dt * 0.3);
    this.cloud = cloud;

    // sun position from hour: azimuth sweeps east -> west, elevation peaks early afternoon
    const az = (h - 6) / 14 * Math.PI;
    const el = Math.max(-0.25, Math.sin((h - 5.5) / 14.5 * Math.PI)) * 1.05;
    const dir = new THREE.Vector3(Math.cos(el) * Math.cos(az), Math.sin(el), Math.cos(el) * Math.sin(az));
    this.sun.position.copy(dir).multiplyScalar(90);
    const sunI = dayness * (1 - cloud * 0.72) * 2.6 + sunsetness * 1.2;
    this.sun.intensity = Math.max(0.05, sunI);
    this.sun.color.setHSL(0.09 - 0.03 * dayness, 0.55 + 0.3 * sunsetness, 0.62 + 0.3 * dayness);
    // a shadow toggle recompiles every material; hysteresis so it happens once at dusk, not every frame
    const wantShadow = this.sun.castShadow ? sunI > 0.30 : sunI > 0.40;
    if (this.shadowSize > 0 && wantShadow !== this.sun.castShadow) this.sun.castShadow = wantShadow;

    // ambient: cool blue at night, neutral by day, warmer at sunset
    const amb = 0.18 + dayness * 0.7 * (1 - cloud * 0.3) + sunsetness * 0.2;
    this.hemi.intensity = amb;
    this.hemi.color.setHSL(0.6, 0.5, 0.55 + 0.3 * dayness);

    // sky
    const top = new THREE.Color().setHSL(0.62, 0.55, 0.06 + 0.42 * dayness);
    const hor = new THREE.Color().setHSL(0.6 - 0.05 * sunsetness, 0.45 + 0.3 * sunsetness, 0.18 + 0.45 * dayness + 0.15 * sunsetness);
    this.skyU.uTop.value.lerp(top, dt * 0.5);
    this.skyU.uHorizon.value.lerp(hor, dt * 0.5);
    this.skyU.uSunDir.value.copy(dir);
    this.skyU.uCloud.value = cloud;
    this.skyU.uNight.value = 1 - dayness;
    this.skyU.uSunGlow.value.setHSL(0.07, 0.8, 0.5 + 0.3 * sunsetness);

    // fog: night haze + weather fog, cooler when wet
    // roughly a third of the old values, for the same reason: at 0.0016 the city
    // 340 m out sits under a quarter of a fog veil, and the 780 m ridge is most
    // of the way into haze, which is what distance should look like.
    const target = 0.0013 + 0.0011 * (1 - dayness) + weather.fog * 0.009 + weather.rain * 0.0013;
    this.scene.fog.density = THREE.MathUtils.lerp(this.scene.fog.density, target, dt * 0.4);
    this.scene.fog.color.copy(hor).multiplyScalar(0.55 + 0.35 * dayness).lerp(new THREE.Color(0x8892a0), weather.fog * 0.6);

    // exposure + environment map: day = brighter, HDR swap by time
    const exposure = 0.74 + 0.5 * dayness - 0.15 * cloud * dayness - 0.12 * weather.rain;
    this.renderer.toneMappingExposure = THREE.MathUtils.lerp(this.renderer.toneMappingExposure, exposure, dt * 0.6);
    const env = dayness > 0.55 ? (this.envDay || this.envEvening || this.envNight)
              : dayness > 0.08 || sunsetness > 0.3 ? (this.envEvening || this.envNight || this.envDay)
              : (this.envNight || this.envEvening || this.envDay);
    if (env && this.scene.environment !== env) this.scene.environment = env;
    this.scene.environmentIntensity = 0.28 + 0.55 * dayness * (1 - cloud * 0.5) + 0.35 * weather.wet;

    // thunderstorm: a rare soft flash, never a strobe
    if (weather.storm > 0.5) {
      if (Math.random() < dt / 42) this.lightning = 1;
    }
    this.lightning = Math.max(0, this.lightning - dt * 2.2);
    this.skyU.uFlash.value = this.lightning * 0.45;
    this.hemi.intensity += this.lightning * 1.4;

    return { dayness, sunsetness, sunDir: dir, sunColor: this.sun.color };
  }
}

// ----------------------------------------------------------------- weather
/**
 * Turns a weather reading into a slowly-moving target state, then hands the
 * interpolated values to everything that cares. Nothing pops: the fastest
 * change (a demo switch) still takes ~60 s to fully arrive.
 */
export class WeatherManager {
  constructor() {
    this.state = { cloud: 0.35, rain: 0, snow: 0, fog: 0, wind: 12, windDeg: 350, storm: 0, wet: 0, temp: 18, label: 'partly cloudy', source: '' };
    this.target = Object.assign({}, this.state);
    this.demo = null;                  // null = live, else a preset name
    this.speed = 1 / 60;               // per-second fraction toward target
  }

  static presetFor(condition, reading) {
    const r = reading || {};
    const wind = r.wind_kmh == null ? 12 : r.wind_kmh;
    const base = { cloud: 0.3, rain: 0, snow: 0, fog: 0, wind, windDeg: r.wind_deg || 350, storm: 0 };
    const table = {
      clear:          { cloud: 0.05 },
      mostly_clear:   { cloud: 0.18 },
      partly_cloudy:  { cloud: 0.45 },
      overcast:       { cloud: 0.9 },
      cloudy:         { cloud: 0.9 },
      drizzle:        { cloud: 0.85, rain: 0.28 },
      rain:           { cloud: 0.92, rain: 0.62 },
      heavy_rain:     { cloud: 0.97, rain: 1.0 },
      thunderstorm:   { cloud: 1.0, rain: 0.9, storm: 1, wind: Math.max(wind, 34) },
      fog:            { cloud: 0.75, fog: 1 },
      snow:           { cloud: 0.9, snow: 0.8 },
      wind_test:      { cloud: 0.25, wind: 36, windDeg: 340 },
      wind:           { cloud: 0.35, wind: Math.max(wind, 40) },
      strong_wind:    { cloud: 0.4, wind: Math.max(wind, 62) },
    };
    return Object.assign(base, table[condition] || table.partly_cloudy);
  }

  /** from the server reading */
  setLive(reading) {
    this.live = reading;
    if (this.demo) return;
    const p = WeatherManager.presetFor(reading.condition, reading);
    Object.assign(this.target, p, { temp: reading.temp_c == null ? 18 : reading.temp_c,
                                    label: reading.condition.replace('_', ' '), source: reading.source });
  }

  setDemo(name) {
    this.demo = name === 'auto' ? null : name;
    if (!this.demo) { if (this.live) this.setLive(this.live); return; }
    const p = WeatherManager.presetFor(name, this.live);
    Object.assign(this.target, p, { label: name.replace('_', ' ') + ' (demo)', source: 'demo' });
  }

  update(dt) {
    const s = this.state, t = this.target;
    const k = Math.min(1, dt * this.speed * 3.2);
    for (const key of ['cloud', 'rain', 'snow', 'fog', 'wind', 'storm', 'temp']) {
      s[key] += (t[key] - s[key]) * k;
    }
    let d = ((t.windDeg - s.windDeg + 540) % 360) - 180;
    s.windDeg = (s.windDeg + d * k + 360) % 360;
    // surfaces take longer to soak than to start raining, and longer still to dry
    const wetTarget = Math.min(1, s.rain * 1.1 + s.snow * 0.5);
    const wetK = wetTarget > s.wet ? dt / 45 : dt / 140;
    s.wet += (wetTarget - s.wet) * Math.min(1, wetK * 3);
    s.label = t.label; s.source = t.source;
    return s;
  }
}
