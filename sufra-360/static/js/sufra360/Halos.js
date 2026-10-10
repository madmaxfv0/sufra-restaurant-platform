import * as THREE from '/static/vendor/three/three.module.js';

/**
 * Soft light halos. Every lamp, lantern and string-light row gets a camera-
 * facing quad with a radial falloff, drawn additively in ONE instanced draw
 * call. This is what gives the warm "glow" look of the reference without a
 * full-screen bloom pass, so Balanced and Smooth keep the atmosphere.
 * Colours are per instance and can change (table lanterns follow status).
 */
export class HaloSystem {
  constructor(scene, max) {
    this.scene = scene;
    this.max = max || 256;
    this.count = 0;
    this.items = [];
    const geo = new THREE.PlaneGeometry(1, 1);
    const aSize = new Float32Array(this.max);
    geo.setAttribute('aSize', new THREE.InstancedBufferAttribute(aSize, 1));
    this.aSize = geo.getAttribute('aSize');
    this.uniforms = { uGlobal: { value: 1.0 } };
    const mat = new THREE.ShaderMaterial({
      uniforms: this.uniforms, transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.AdditiveBlending, side: THREE.DoubleSide, fog: false,
      vertexShader: `
        attribute float aSize;
        varying vec2 vUv; varying vec3 vCol;
        void main() {
          vUv = uv;
          #ifdef USE_INSTANCING_COLOR
            vCol = instanceColor;
          #else
            vCol = vec3(1.0);
          #endif
          vec3 centre = (modelMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
          vec4 mv = viewMatrix * vec4(centre, 1.0);
          mv.xy += (position.xy) * aSize;                 // billboard in view space
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform float uGlobal;
        varying vec2 vUv; varying vec3 vCol;
        void main() {
          float d = length(vUv - 0.5) * 2.0;
          float a = pow(max(0.0, 1.0 - d), 2.6);
          gl_FragColor = vec4(vCol * a * uGlobal, a * 0.9);
        }`,
    });
    this.mesh = new THREE.InstancedMesh(geo, mat, this.max);
    this.mesh.count = 0;
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 50;
    // instanceColor must exist before first render for USE_INSTANCING_COLOR to be defined
    this.mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(this.max * 3), 3);
    this._m = new THREE.Matrix4();
    scene.add(this.mesh);
  }

  /** returns an index you can recolour later */
  add(position, color, size) {
    if (this.count >= this.max) return -1;
    const i = this.count++;
    this._m.makeTranslation(position.x, position.y, position.z);
    this.mesh.setMatrixAt(i, this._m);
    this.mesh.setColorAt(i, new THREE.Color(color));
    this.aSize.setX(i, size || 0.8);
    this.mesh.count = this.count;
    this.mesh.instanceMatrix.needsUpdate = true;
    this.mesh.instanceColor.needsUpdate = true;
    this.aSize.needsUpdate = true;
    this.items.push({ position: position.clone(), size: size || 0.8 });
    return i;
  }

  /** follow an object (a lantern flame, a lamp head) */
  track(i, position) {
    if (i < 0) return;
    this._m.makeTranslation(position.x, position.y, position.z);
    this.mesh.setMatrixAt(i, this._m);
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  setColor(i, color) {
    if (i < 0) return;
    this.mesh.setColorAt(i, color);
    this.mesh.instanceColor.needsUpdate = true;
  }

  setSize(i, size) {
    if (i < 0) return;
    this.aSize.setX(i, size);
    this.aSize.needsUpdate = true;
  }

  /** dim by day, full at night */
  setGlobal(v) { this.uniforms.uGlobal.value = v; }
}
