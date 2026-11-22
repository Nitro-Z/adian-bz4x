/* bz4x-car.js — 路上的 bZ4X（只用在 website_v2）
 *
 * 3D 小車畫在地圖「上面」的一層透明畫布（Three.js），所以永遠看得到，不會被大樓或高架橋擋住，
 * 就像導航 App 裡的車子。sim3d.js 在地圖每畫完一格時，把車子在螢幕上的位置、車頭方向與鏡頭角度傳進來：
 *
 *   const car = await BZ4XCar.create(hostElement);
 *   car.render({ x, y, yaw, pitch, lengthPx, night, moving, alpha });  // yaw = 車頭方向 − 鏡頭方向（度，順時針），pitch = 鏡頭俯角（度，負的）
 *                                                            // moving：行駛中才開大燈；alpha：停靠時淡出
 *   car.hide();
 *
 * 外型是示意的 bZ4X（長 4.69 m、寬 1.86 m、軸距 2.85 m）：白色車身、黑色輪拱與下護板、貫穿式尾燈、
 * 粗黑描邊（網站的新粗獷風格）。Three.js 載不到時，改用 2D 的俯視小車。
 */
(function () {
  'use strict';
  const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.min.js';
  const INK = 0x141B2D, GREEN = 0x27F550, BODY = 0xF3F5F7, GLASS = 0x1B2436, RED = 0xFF2A2A,
    LAMP = 0xF2FCFF, TYRE = 0x16181D, RIM = 0xA9B1BB, BEAM = 0xFFE7A0;
  const LEN = 4.69, HALF_W = 0.93, AXLE = 1.425, WHEEL_R = 0.36;
  const CANVAS = 480;   // 畫布邊長（CSS px），車子大小靠鏡頭範圍調整，不必每格改畫布

  // ---------- 2D 備用（Three.js 載不到時） ----------
  function fallback2D(host) {
    const c = document.createElement('canvas'), s = 2, w = 46, h = 96;
    c.width = w * s; c.height = h * s;
    const g = c.getContext('2d'); g.scale(s, s);
    const rr = (x, y, ww, hh, r) => { g.beginPath(); g.roundRect(x, y, ww, hh, r); };
    g.fillStyle = '#141B2D'; rr(1, 1, w - 2, h - 2, 14); g.fill();
    g.fillStyle = '#F3F5F7'; rr(4, 4, w - 8, h - 8, 12); g.fill();
    g.fillStyle = '#1B2436'; rr(8, 26, w - 16, 16, 5); g.fill(); rr(9, 70, w - 18, 10, 4); g.fill();
    g.fillStyle = '#FF2A2A'; g.fillRect(8, h - 7, w - 16, 3);
    Object.assign(c.style, { position: 'absolute', left: '0', top: '0', width: w + 'px', height: h + 'px', pointerEvents: 'none', display: 'none', zIndex: 2 });
    host.appendChild(c);
    return {
      render({ x, y, yaw, lengthPx = 96, alpha = 1 }) {
        const k = lengthPx / h;
        c.style.display = 'block'; c.style.opacity = alpha;
        c.style.transform = `translate(${x - w / 2}px, ${y - h / 2}px) rotate(${yaw}deg) scale(${k})`;
      },
      hide() { c.style.display = 'none'; },
      three: false,
    };
  }

  async function create(host) {
    let T;
    try { T = await import(THREE_URL); } catch (e) { console.warn('Three.js 載入失敗，改用 2D 小車', e); return fallback2D(host); }

    const canvas = document.createElement('canvas');
    Object.assign(canvas.style, { position: 'absolute', left: '0', top: '0', width: CANVAS + 'px', height: CANVAS + 'px', pointerEvents: 'none', display: 'none', zIndex: 2 });
    host.appendChild(canvas);
    let R;
    try {
      R = new T.WebGLRenderer({ canvas, alpha: true, antialias: true });
    } catch (e) { canvas.remove(); console.warn('WebGL 不足，改用 2D 小車', e); return fallback2D(host); }
    R.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    R.setSize(CANVAS, CANVAS, false);
    R.setClearColor(0x000000, 0);

    const scene = new T.Scene();
    const cam = new T.OrthographicCamera(-5, 5, 5, -5, 0.1, 300);
    const hemi = new T.HemisphereLight(0xffffff, 0x7d8696, 2.4); scene.add(hemi);
    const sun = new T.DirectionalLight(0xffffff, 1.9); sun.position.set(-5, 12, 7); scene.add(sun);

    // ---------- 材質 ----------
    const phong = (color, extra) => new T.MeshPhongMaterial(Object.assign({ color, shininess: 40, specular: 0x333333 }, extra));
    const M = {
      body: phong(BODY, { shininess: 60, specular: 0x555555 }),
      glass: phong(GLASS, { shininess: 90, specular: 0x8899aa }),
      ink: phong(INK, { shininess: 10 }),
      tyre: phong(TYRE, { shininess: 5 }),
      rim: phong(RIM, { shininess: 70 }),
      tail: new T.MeshBasicMaterial({ color: RED }),
      lamp: new T.MeshBasicMaterial({ color: LAMP }),
    };
    const outlineUniforms = { thick: { value: 0.1 } };
    const outlineMat = new T.ShaderMaterial({
      uniforms: Object.assign(outlineUniforms, { color: { value: new T.Color(INK) } }),
      vertexShader: 'attribute vec3 onormal; uniform float thick; void main(){ vec3 p = position + onormal * thick; gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }',
      fragmentShader: 'uniform vec3 color; void main(){ gl_FragColor = vec4(color, 1.0); }',
      side: T.BackSide,
    });

    // 描邊用的「平滑法線」：同一個位置的頂點法線取平均，外擴時才不會在稜角裂開
    function addOutline(mesh) {
      const g = mesh.geometry, pos = g.attributes.position, nor = g.attributes.normal, n = pos.count;
      const key = i => `${Math.round(pos.getX(i) * 500)},${Math.round(pos.getY(i) * 500)},${Math.round(pos.getZ(i) * 500)}`;
      const acc = new Map();
      for (let i = 0; i < n; i++) {
        const k = key(i), v = acc.get(k) || [0, 0, 0];
        v[0] += nor.getX(i); v[1] += nor.getY(i); v[2] += nor.getZ(i); acc.set(k, v);
      }
      const out = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        const v = acc.get(key(i)), l = Math.hypot(v[0], v[1], v[2]) || 1;
        out[i * 3] = v[0] / l; out[i * 3 + 1] = v[1] / l; out[i * 3 + 2] = v[2] / l;
      }
      g.setAttribute('onormal', new T.BufferAttribute(out, 3));
      const o = new T.Mesh(g, outlineMat);
      o.position.copy(mesh.position); o.rotation.copy(mesh.rotation); o.scale.copy(mesh.scale);
      return o;
    }

    const car = new T.Group();      // 整台車（繞 y 軸轉 = 車頭方向）
    const solids = [];
    function part(geo, mat, x = 0, y = 0, z = 0, outline = true) {
      const m = new T.Mesh(geo, mat); m.position.set(x, y, z);
      car.add(m); if (outline) solids.push(m);
      return m;
    }
    // 側面輪廓（u = 往車頭的距離，v = 高度）擠出成車寬；u → −z（車頭朝 −z），擠出方向 → x
    function profile(pts, width, bevel = 0.05) {
      const shape = new T.Shape(pts.map(([u, v]) => new T.Vector2(u, v)));
      const depth = Math.max(0.01, width - 2 * bevel);
      const g = new T.ExtrudeGeometry(shape, { depth, bevelEnabled: bevel > 0, bevelThickness: bevel, bevelSize: bevel, bevelSegments: 2, curveSegments: 6 });
      g.translate(0, 0, -depth / 2);
      g.rotateY(Math.PI / 2);
      return g;
    }
    const arc = (cu, cv, r, a0, a1, n = 10) => Array.from({ length: n + 1 }, (_, i) => {
      const a = a0 + (a1 - a0) * i / n; return [cu + r * Math.cos(a), cv + r * Math.sin(a)];
    });
    const ARCH = 0.47;

    // 車身（白）：車頭 → 引擎蓋 → 腰線 → 車尾，下緣挖出兩個輪拱
    const bodyPts = [
      [2.28, 0.38], [2.37, 0.55], [2.34, 0.78], [2.14, 0.88], [1.40, 1.00], [1.28, 1.04],
      [-1.75, 1.13], [-2.16, 1.15], [-2.33, 1.04], [-2.37, 0.82], [-2.34, 0.52], [-2.26, 0.38],
      ...arc(-AXLE, WHEEL_R, ARCH, Math.PI, 0), ...arc(AXLE, WHEEL_R, ARCH, Math.PI, 0),
    ];
    part(profile(bodyPts, HALF_W * 2), M.body);
    // 車窗（深色）與白色車頂：擋風玻璃長、車頂往後微微下斜，尾端有擾流板
    part(profile([[1.32, 1.01], [0.28, 1.59], [-0.45, 1.64], [-1.45, 1.585], [-1.95, 1.47], [-2.20, 1.13], [-1.75, 1.10]], 1.52, 0.06), M.glass);
    part(profile([[0.24, 1.585], [-0.45, 1.640], [-1.45, 1.585], [-1.93, 1.475], [-2.05, 1.53], [-1.45, 1.645], [-0.45, 1.700], [0.20, 1.640]], 1.38, 0.04), M.body);
    // 下護板（黑）：前後保桿下緣、兩側裙邊
    const box = (sx, sy, sz) => new T.BoxGeometry(sx, sy, sz);
    part(box(HALF_W * 2 + 0.05, 0.24, 0.52), M.ink, 0, 0.36, -2.18);   // 前保桿下緣（車身有 5 cm 圓角，所以往外放）
    part(box(HALF_W * 2 + 0.05, 0.26, 0.52), M.ink, 0, 0.37, 2.18);    // 後保桿下緣
    part(box(HALF_W * 2 + 0.06, 0.28, 2 * (AXLE - ARCH) - 0.02), M.ink, 0, 0.36, 0);
    // 輪拱（黑，向外凸一點，從上面看得到）
    const archGeo = () => {
      const s = new T.Shape([...arc(0, 0, ARCH + 0.14, 0, Math.PI, 14), ...arc(0, 0, ARCH, Math.PI, 0, 14)].map(([u, v]) => new T.Vector2(u, v)));
      const g = new T.ExtrudeGeometry(s, { depth: 0.12, bevelEnabled: false, curveSegments: 6 });
      g.translate(0, 0, -0.06); g.rotateY(Math.PI / 2); return g;
    };
    for (const zs of [-1, 1]) for (const xs of [-1, 1]) part(archGeo(), M.ink, xs * (HALF_W + 0.01), WHEEL_R, zs * AXLE);
    // 輪胎與輪圈
    for (const zs of [-1, 1]) for (const xs of [-1, 1]) {
      const t = part(new T.CylinderGeometry(WHEEL_R, WHEEL_R, 0.25, 22), M.tyre, xs * (HALF_W - 0.14), WHEEL_R, zs * AXLE);
      t.rotation.z = Math.PI / 2;
      const r = part(new T.CircleGeometry(0.25, 22), M.rim, xs * (HALF_W - 0.14 + 0.126), WHEEL_R, zs * AXLE, false);
      r.rotation.y = xs * Math.PI / 2;
    }
    // 後照鏡
    for (const xs of [-1, 1]) part(box(0.22, 0.10, 0.12), M.body, xs * (HALF_W + 0.09), 1.07, -0.78);
    // 車頭：黑色「鎚頭」飾條與細長頭燈；車尾：貫穿式尾燈
    part(box(1.40, 0.11, 0.08), M.ink, 0, 0.66, -2.42, false);
    for (const xs of [-1, 1]) part(box(0.44, 0.06, 0.16), M.lamp, xs * 0.58, 0.88, -2.20, false);
    const tail = part(box(1.70, 0.06, 0.06), M.tail, 0, 1.02, 2.40, false);

    // 地面：影子、綠色光圈、夜間頭燈光束
    const ground = new T.Group();
    const flat = (geo, mat, y) => { const m = new T.Mesh(geo, mat); m.rotation.x = -Math.PI / 2; m.position.y = y; m.renderOrder = -1; ground.add(m); return m; };
    const shadow = flat(new T.CircleGeometry(1, 40), new T.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.30, depthWrite: false }), 0.01);
    shadow.scale.set(1.30, 2.75, 1);
    flat(new T.RingGeometry(2.95, 3.25, 64), new T.MeshBasicMaterial({ color: INK, transparent: true, opacity: 0.85, depthWrite: false }), 0.012);
    flat(new T.RingGeometry(3.01, 3.19, 64), new T.MeshBasicMaterial({ color: GREEN, transparent: true, opacity: 0.95, depthWrite: false }), 0.014);
    const beamMat = new T.MeshBasicMaterial({ color: BEAM, transparent: true, opacity: 0, depthWrite: false, blending: T.AdditiveBlending, side: T.DoubleSide });
    for (const xs of [-1, 1]) {   // 形狀的 y 往前（轉平之後 y → −z = 車頭方向）
      const s = new T.Shape([new T.Vector2(xs * 0.55, 2.3), new T.Vector2(xs * 2.6, 9.5), new T.Vector2(xs * -0.4, 9.5), new T.Vector2(xs * 0.25, 2.3)]);
      flat(new T.ShapeGeometry(s), beamMat, 0.02);
    }
    car.add(ground);
    solids.forEach(m => car.add(addOutline(m)));
    const spin = new T.Group(); spin.add(car); scene.add(spin);

    let shown = false, lastAlpha = 1;
    return {
      three: true,
      // x, y：車子在螢幕上的位置（CSS px）；yaw：車頭相對鏡頭的方向；pitch：鏡頭俯角；lengthPx：車長幾個像素
      render({ x, y, yaw = 0, pitch = -40, lengthPx = 100, night = 0, moving = true, alpha = 1 }) {
        const ppm = lengthPx / LEN, half = CANVAS / 2 / ppm;
        cam.left = -half; cam.right = half; cam.top = half; cam.bottom = -half; cam.updateProjectionMatrix();
        const e = Math.max(12, Math.min(88, -pitch)) * Math.PI / 180, D = 80;
        cam.position.set(0, D * Math.sin(e), D * Math.cos(e)); cam.lookAt(0, 0, 0);
        spin.rotation.y = -yaw * Math.PI / 180;
        outlineUniforms.thick.value = 2.1 / ppm;
        hemi.intensity = 2.4 * (1 - 0.42 * night); sun.intensity = 1.9 * (1 - 0.6 * night);
        beamMat.opacity = moving ? 0.55 * night : 0;   // 停著（充電、停車）時不開大燈
        tail.scale.y = 1 + 0.8 * night;
        R.render(scene, cam);
        canvas.style.transform = `translate(${(x - CANVAS / 2).toFixed(2)}px, ${(y - CANVAS / 2).toFixed(2)}px)`;   // 不取整數：地圖是次像素移動，取整數會讓車子每格跳半個像素（看起來在抖）
        if (alpha !== lastAlpha) { canvas.style.opacity = alpha; lastAlpha = alpha; }
        if (!shown) { canvas.style.display = 'block'; shown = true; }
      },
      hide() { if (shown) { canvas.style.display = 'none'; shown = false; } },
    };
  }

  window.BZ4XCar = { create };
})();
