/* sim3d.js — 阿電 的 3D 行車模擬：地圖與畫面元件（只用在 website_v2）
 *
 * 地圖有兩種：
 *   - 預設：Google Photorealistic 3D Tiles（3D 街景）。金鑰由 gateway 的 api/maps-config 提供（要先登入），
 *     只能用在 Map Tiles API 和我們的網域，GCP 每天最多 200 個 3D 工作階段。
 *   - map: '2d'：一般街道圖（OpenStreetMap 圖磚），不用 Google 金鑰、不花 3D 工作階段。點陣圖的字會跟著地圖轉，
 *     所以 2D 用「北方朝上」的鏡頭（timeline 的 northUp）。OSM 的使用規定不准大量預先下載，所以 2D 不做預先載入。
 * 時間軸（播放、拖曳、倍速）在 sim3d-timeline.js；這個檔案只負責「把某一刻畫出來」。
 *
 *   const sim = await Sim3D.create(el, { configUrl, creditContainer, map: '3d' | '2d' });   // 失敗會 throw → 改用 Leaflet
 *   const path = Sim3D.makePath(Sim3D.simplify(coords, 3));   // 路線：去掉 3 公尺內的鋸齒；也存「路面高度」
 *   sim.setLegs([{ path, kind: 'go' }, { path, kind: 'back' }]); sim.setActiveLeg(0);   // 去程綠、回程黃
 *   sim.refreshLegs();                                  // 量好路面高度之後重畫路線
 *   sim.addPlace({ lat, lon, icon: '🏫', label: '板橋國小', tone, key });   // 地點圖釘（像 Google 地圖）
 *   sim.addPin({ lat, lon, fast, label });              // 附近其他充電站（小圖釘）
 *   sim.view({ lat, lon, h, heading, pitch, range });   // 鏡頭（角度用度）
 *   sim.setCar([lat, lon], 車頭方向, 路面高度, 行駛中?, 透明度); sim.showCar(true); sim.setNight(0..1);
 *   sim.setStop({ p, h, icon, title, line, tone, k });  // 停靠時跳出的資訊卡（k = 0–1 彈出程度）
 *   sim.setWalker({ from, to, h, f, emoji });           // 從地點走到車子的小人（f = 0–1）
 *
 * 路線和車子用「同一份路面高度」（預先載入時沿路量，去掉屋頂、天橋等離群值再平滑），所以車子一定在線上。
 * 路線不「貼地」：貼地會把路邊的牆、屋頂也塗上顏色，看起來坑坑疤疤；被大樓擋住的部分用半透明顯示。
 * 路上的車是 bZ4X 3D 小車（bz4x-car.js），畫在地圖上面一層，不會被大樓、高架橋擋住。
 * 地圖的標誌與資料來源（attribution）放在 creditContainer，畫面上一定要看得到（Map Tiles API 政策）。
 */
(function () {
  'use strict';
  const CESIUM_VER = '1.146.0';
  const BASE = `https://cdn.jsdelivr.net/npm/cesium@${CESIUM_VER}/Build/Cesium/`;
  const GREEN = '#27F550', INK = '#141B2D', YELLOW = '#FFD84D', WHITE = '#FFFFFF';
  // 3D 建築判斷門檻：格點與四周平均的高低差（第 90 百分位，公尺）。11/09 實測：台北、板橋、台中 22–98；彰化、員林、墾丁、花蓮 < 1
  const ROUGH_3D_M = 3;
  const LIFT = 2.5, LIFT_ACTIVE = 4;   // 路線畫在路面上方幾公尺（目前這一段高一點，重疊時畫在上面）
  // 一般地圖：OpenStreetMap 標準圖磚（小地圖也是用這個；CARTO 現在要 API 金鑰，不用）
  const STREET = { url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', credit: '地圖 © OpenStreetMap 貢獻者', maximumLevel: 19 };

  let cesiumLoading = null;
  function loadCesium() {
    if (window.Cesium) return Promise.resolve(window.Cesium);
    if (cesiumLoading) return cesiumLoading;
    window.CESIUM_BASE_URL = BASE;
    cesiumLoading = new Promise((resolve, reject) => {
      const css = document.createElement('link');
      css.rel = 'stylesheet'; css.href = BASE + 'Widgets/widgets.css';
      document.head.appendChild(css);
      const s = document.createElement('script');
      s.src = BASE + 'Cesium.js';
      s.onload = () => (window.Cesium ? resolve(window.Cesium) : reject(new Error('Cesium missing')));
      s.onerror = () => reject(new Error('Cesium load failed'));
      document.head.appendChild(s);
    });
    return cesiumLoading;
  }

  // ---------- 路線幾何（純數學） ----------
  const R = 6371008.8, rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;
  function meters(a, b) {
    const dLat = rad(b[0] - a[0]), dLon = rad(b[1] - a[1]);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function bearing(a, b) {   // 弧度，北 = 0，順時針
    const y = Math.sin(rad(b[1] - a[1])) * Math.cos(rad(b[0]));
    const x = Math.cos(rad(a[0])) * Math.sin(rad(b[0])) - Math.sin(rad(a[0])) * Math.cos(rad(b[0])) * Math.cos(rad(b[1] - a[1]));
    return Math.atan2(y, x);
  }
  // Douglas–Peucker：拿掉偏離直線不到 tol 公尺的點。路線變平順（不鋸齒），真正的轉彎都保留
  function simplify(coords, tol = 3) {
    const n = coords.length;
    if (n < 3) return coords.slice();
    const ky = 110540, kx = 111320 * Math.cos(rad(coords[0][0]));
    const xy = coords.map(([la, lo]) => [lo * kx, la * ky]);
    const keep = new Uint8Array(n); keep[0] = keep[n - 1] = 1;
    const stack = [[0, n - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      const [x1, y1] = xy[a], dx = xy[b][0] - x1, dy = xy[b][1] - y1, L2 = dx * dx + dy * dy;
      let best = -1, bi = -1;
      for (let i = a + 1; i < b; i++) {
        const px = xy[i][0] - x1, py = xy[i][1] - y1;
        const t = L2 ? Math.max(0, Math.min(1, (px * dx + py * dy) / L2)) : 0;
        const d = Math.hypot(px - t * dx, py - t * dy);
        if (d > best) { best = d; bi = i; }
      }
      if (best > tol) { keep[bi] = 1; stack.push([a, bi], [bi, b]); }
    }
    return coords.filter((_, i) => keep[i]);
  }

  // 路線：沿路線距離 → 位置；另外存一份「路面高度」（每 ds 公尺一格）。
  // 預先載入時，鏡頭越近量到的高度越準（圖塊越細）；最後去掉屋頂、天橋等離群值再平滑（finalize）。
  function makePath(coords) {
    const cum = [0];
    for (let i = 1; i < coords.length; i++) cum.push(cum[i - 1] + meters(coords[i - 1], coords[i]));
    const total = cum[cum.length - 1];
    function at(d) {   // 沿路線距離 d 公尺的位置（二分搜尋，可任意跳著查）
      d = Math.max(0, Math.min(total, d));
      let lo = 0, hi = cum.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (cum[m] <= d) lo = m; else hi = m; }
      const seg = cum[hi] - cum[lo] || 1, t = (d - cum[lo]) / seg, a = coords[lo], b = coords[hi];
      return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    }
    const ds = Math.max(15, total / 3000), n = Math.max(1, Math.ceil(total / ds));
    const raw = new Float32Array(n + 1).fill(NaN), q = new Float32Array(n + 1).fill(Infinity);
    let fin = null, fallback = () => 40;
    const idx = d => Math.max(0, Math.min(n, Math.round(d / ds)));
    const path = {
      coords, cum, total, at, ds, n,
      get final() { return !!fin; },
      setFallback(f) { fallback = f; },
      // 這一點還需要量嗎？（還沒有「差不多準」的樣本）
      wants(d, quality) { return !(q[idx(d)] <= quality * 1.25); },
      // 量到的高度；quality = 量的時候鏡頭距離（越小越準）。差不多準的時候取低的（避開屋頂）
      addSample(d, h, quality) {
        if (!Number.isFinite(h)) return;
        const i = idx(d);
        if (!Number.isFinite(raw[i]) || quality < q[i] * 0.8) { raw[i] = h; q[i] = quality; }
        else if (quality <= q[i] * 1.25) { raw[i] = Math.min(raw[i], h); q[i] = Math.min(q[i], quality); }
      },
      hAt(d) {
        const x = Math.max(0, Math.min(n, d / ds));
        if (fin) { const i = Math.floor(x), f = x - i; return i >= n ? fin[n] : fin[i] + (fin[i + 1] - fin[i]) * f; }
        const i = Math.round(x);
        for (let k = 0; k <= 8; k++) {
          if (Number.isFinite(raw[i - k])) return raw[i - k];
          if (Number.isFinite(raw[i + k])) return raw[i + k];
        }
        const p = at(d); return fallback(p[0], p[1]);
      },
      // 補洞（線性內插）→ 每點取前後 ±45 公尺的第 25 百分位（去掉屋頂、招牌）→ 前後 ±30 公尺平均（平順）
      finalize() {
        const h = Float64Array.from(raw);
        let first = -1;
        for (let i = 0; i <= n; i++) if (Number.isFinite(h[i])) { first = i; break; }
        if (first < 0) {
          for (let i = 0; i <= n; i++) { const p = at(i * ds); h[i] = fallback(p[0], p[1]); }
        } else {
          for (let i = 0; i < first; i++) h[i] = h[first];
          let prev = first;
          for (let i = first + 1; i <= n; i++) {
            if (!Number.isFinite(h[i])) continue;
            for (let j = prev + 1; j < i; j++) h[j] = h[prev] + (h[i] - h[prev]) * (j - prev) / (i - prev);
            prev = i;
          }
          for (let i = prev + 1; i <= n; i++) h[i] = h[prev];
        }
        const w1 = Math.max(1, Math.round(45 / ds)), w2 = Math.max(1, Math.round(30 / ds)), lo = new Float64Array(n + 1), buf = [];
        for (let i = 0; i <= n; i++) {
          buf.length = 0;
          for (let j = Math.max(0, i - w1); j <= Math.min(n, i + w1); j++) buf.push(h[j]);
          buf.sort((a, b) => a - b);
          lo[i] = buf[Math.floor((buf.length - 1) * 0.25)];
        }
        const ps = new Float64Array(n + 2);
        for (let i = 0; i <= n; i++) ps[i + 1] = ps[i] + lo[i];
        fin = new Float32Array(n + 1);
        for (let i = 0; i <= n; i++) { const a = Math.max(0, i - w2), b = Math.min(n, i + w2); fin[i] = (ps[b + 1] - ps[a]) / (b - a + 1); }
      },
      // 路線的一段（例如休息站前、後）：共用同一份路面高度
      sub(d0, d1) {
        const L = Math.max(0, d1 - d0), cl = d => d0 + Math.max(0, Math.min(L, d));
        return { root: path, off: d0, total: L, at: d => at(cl(d)), hAt: d => path.hAt(cl(d)) };
      },
    };
    return path;
  }
  const angleLerpDeg = (a, b, t) => a + deg(Math.atan2(Math.sin(rad(b - a)), Math.cos(rad(b - a)))) * t;
  const smooth = t => t * t * (3 - 2 * t);

  // 車子、地點圖釘、走路的人、停靠資訊卡畫在地圖上面的一層：sim-overlay.js（3D、2D 共用）

  async function create(container, opts = {}) {
    const flat = opts.map === '2d';
    let key = null;
    if (!flat) {
      const res = await fetch(opts.configUrl || 'api/maps-config', { credentials: 'same-origin' });
      if (!res.ok) throw new Error('maps-config ' + res.status);
      key = (await res.json()).key;
      if (!key) throw new Error('no maps key');
    }
    const C = await loadCesium();

    const viewer = new C.Viewer(container, Object.assign({
      baseLayer: flat ? new C.ImageryLayer(new C.UrlTemplateImageryProvider({ url: STREET.url,
        credit: new C.Credit(STREET.credit, true), maximumLevel: STREET.maximumLevel })) : false,
      baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
      navigationHelpButton: false, fullscreenButton: false, animation: false, timeline: false,
      infoBox: false, selectionIndicator: false, requestRenderMode: false,
      useBrowserRecommendedResolution: !opts.crisp,
    }, opts.creditContainer ? { creditContainer: opts.creditContainer } : {}));
    const scene = viewer.scene;
    scene.postProcessStages.fxaa.enabled = true;
    viewer.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
    // 細節（screen-space error）。11/10 實測「你的一天」整段（1920×1080）：12 要 4.2–4.6 GB 顯示卡記憶體；16 約 4 GB，播放時還要
    // 重新載入 4,000 個圖塊（緩衝約 9 秒）；20 只要 2.1–2.5 GB，播放時 881 個、緩衝約 1 秒，近看跟 16 幾乎一樣
    const SSE = opts.sse || 20;
    let tileset = null, nightShader = null, layer = null;
    const stats = { loads: 0 };
    if (flat) {
      layer = viewer.imageryLayers.get(0);
      Object.assign(scene.globe, { show: true, showGroundAtmosphere: false, enableLighting: false, maximumScreenSpaceError: 1.5 });
      scene.globe.baseColor = C.Color.fromCssColorString('#EEEAE2');
      scene.fog.enabled = false;
      scene.skyAtmosphere.show = true;
    } else {
      scene.globe.show = false;                    // 只顯示 Google 3D（Google 的使用方式）
      scene.skyAtmosphere.show = true;
      // showCreditsOnScreen：Google 要求把各圖塊的資料來源一行列在畫面上（不能只放在「Data attribution」連結裡）
      // 開車時鏡頭一直在動：移動中也要下載（cullRequestsWhileMoving），畫面邊緣也要一樣清楚（foveated）。
      // Cesium 預設這兩項都會先略過、等鏡頭停下來才補，看起來就是「開到哪、生成到哪」。
      tileset = await C.createGooglePhotorealistic3DTileset({ key, onlyUsingWithGoogleGeocoder: true },
        { maximumScreenSpaceError: SSE, showCreditsOnScreen: true, cullRequestsWhileMoving: false, foveatedScreenSpaceError: false });
      // 預先載入的圖塊要全部留在顯示卡記憶體，開過去時才不用再下載（一天的路線約 2.1–2.5 GB）。
      // 記憶體 8 GB 以上的電腦用 3 GB 快取；比較小的電腦 1.5 GB（被擠掉的圖塊會從瀏覽器的磁碟快取再讀，比網路快）
      const mem = navigator.deviceMemory || 8;
      tileset.cacheBytes = (opts.cacheMB || (mem >= 8 ? 3072 : 1536)) * 1048576;
      tileset.maximumCacheOverflowBytes = 1024 * 1048576;
      tileset.tileLoad.addEventListener(() => { stats.loads++; });
      scene.primitives.add(tileset);
      // 夜晚：只把 3D 建築調暗、偏藍（「日拍夜景」）；路線、車子、看板不受影響，仍然很亮
      try {
        nightShader = new C.CustomShader({
          uniforms: { u_night: { type: C.UniformType.FLOAT, value: 0.0 } },
          lightingModel: C.LightingModel.UNLIT,
          fragmentShaderText: `
            void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
              vec3 c = material.diffuse;
              float l = dot(c, vec3(0.299, 0.587, 0.114));
              // 顏色是線性空間，顯示時會再變亮，所以數值要壓得很低
              vec3 n = vec3(0.004, 0.006, 0.016) + l * l * vec3(0.06, 0.08, 0.17);   // 暗的深藍
              n += smoothstep(0.85, 1.0, l) * vec3(0.22, 0.17, 0.07);                // 照片裡最亮的地方（燈、白色屋頂）像城市燈光
              material.diffuse = mix(c, n, u_night);
            }`,
        });
        tileset.customShader = nightShader;
      } catch (e) { console.warn('night shader unavailable', e); }
    }
    // 鏡頭越高，細節要求越鬆（高空時建築本來就很小）：要載的圖塊少很多，預先載入快、記憶體也夠
    const SSE_K = opts.sseK != null ? opts.sseK : 0.4;
    const sseFor = range => Math.min(28, SSE * (1 + SSE_K * smooth(Math.max(0, Math.min(1, (range - 900) / 4100)))));
    let frames = 0;
    scene.postRender.addEventListener(() => { frames++; });

    // ---------- 地圖上面一層（sim-overlay.js）：bZ4X 小車、地點圖釘、走路的人、停靠資訊卡 ----------
    const enu = new C.Matrix4(), inv = new C.Matrix4(), v3 = new C.Cartesian3();
    const ovl = SimOverlay.create(container, {
      project: (lat, lon, h) => scene.cartesianToCanvasCoordinates(C.Cartesian3.fromDegrees(lon, lat, h || 0), new C.Cartesian2()),
      // 從這一點看鏡頭：換到當地的東–北–上座標，算出鏡頭的方向與俯角
      camera(lat, lon, h) {
        const pos = C.Cartesian3.fromDegrees(lon, lat, h || 0);
        C.Transforms.eastNorthUpToFixedFrame(pos, undefined, enu);
        C.Matrix4.inverseTransformation(enu, inv);
        C.Matrix4.multiplyByPoint(inv, viewer.camera.positionWC, v3);
        return { heading: deg(Math.atan2(-v3.x, -v3.y)), pitch: -deg(Math.atan2(v3.z, Math.hypot(v3.x, v3.y))), dist: C.Cartesian3.magnitude(v3) };
      },
      avoid: opts.avoid,
    }, { spriteBase: opts.spriteBase });
    scene.postRender.addEventListener(() => ovl.draw());

    let legs = [], active = -1;
    const ink = C.Color.fromCssColorString(INK);

    function sampleHeight(lat, lon) {
      if (flat) return 0;
      try {
        // 不要量到我們自己畫的東西（圖釘、路線）
        const h = scene.sampleHeight(C.Cartographic.fromDegrees(lon, lat), legs.map(l => l.e));
        return Number.isFinite(h) ? h : null;
      } catch (e) { return null; }
    }
    const tilesDone = () => tileset ? tileset.tilesLoaded : scene.globe.tilesLoaded;
    async function waitTiles(maxMs = 1500) {
      const t0 = performance.now(), f0 = frames;
      // 至少等地圖用新的鏡頭畫完兩格，tilesLoaded 才是這個畫面的（不然會拿到上一個畫面的「已載完」）
      while (frames - f0 < 2 && performance.now() - t0 < maxMs) await new Promise(r => setTimeout(r, 16));
      while (!tilesDone() && performance.now() - t0 < maxMs) await new Promise(r => setTimeout(r, 50));
      return tilesDone();
    }

    // 路線的點：每 step 公尺補一點，高度用路面高度（之後 refreshLegs 重算）
    function legPositions(path, lift) {
      if (flat) return C.Cartesian3.fromDegreesArray(path.coords.flatMap(([la, lo]) => [lo, la]));
      const pts = [], N = path.coords.length, step = path.total > 60000 ? 200 : path.total > 15000 ? 60 : 20;
      for (let i = 0; i < N; i++) {
        const d0 = path.cum[i];
        pts.push(path.coords[i][1], path.coords[i][0], path.hAt(d0) + lift);
        if (i + 1 < N) for (let d = d0 + step; d < path.cum[i + 1] - step * 0.5; d += step) { const p = path.at(d); pts.push(p[1], p[0], path.hAt(d) + lift); }
      }
      return C.Cartesian3.fromDegreesArrayHeights(pts);
    }
    function legLook(l, on) {
      const mat = new C.PolylineOutlineMaterialProperty({ color: l.color.withAlpha(on ? 1 : 0.85), outlineColor: ink.withAlpha(on ? 1 : 0.6), outlineWidth: on ? 6 : 3 });
      if (flat) return { width: on ? 14 : 7, material: mat, zIndex: on ? 10 : 0 };
      // 被大樓擋住的部分：半透明（看得出路線在大樓後面，但不會蓋掉大樓）
      const fail = new C.PolylineOutlineMaterialProperty({ color: l.color.withAlpha(on ? 0.32 : 0.18), outlineColor: ink.withAlpha(on ? 0.22 : 0.12), outlineWidth: on ? 6 : 3 });
      return { width: on ? 16 : 7, material: mat, depthFailMaterial: fail };
    }

    const api = {
      Cesium: C, viewer, tileset, flat, stats, waitTiles, sampleHeight, carReady: ovl.carReady,
      // 這個地點有沒有 3D 建築：11×11 格點（間距 25 公尺）上 3D 模型表面的高低差
      async probe(lat, lon, ms = 20000) {
        if (flat) return { ok: false, rough: 0, ground: 0, samples: 0 };
        api.freeCamera();
        let g = 40;
        try {
          const [p] = await Promise.race([scene.sampleHeightMostDetailed([C.Cartographic.fromDegrees(lon, lat)]),
            new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 8000))]);
          if (p && Number.isFinite(p.height)) g = p.height;
        } catch (e) { /* 用預設高度 */ }
        viewer.camera.setView({ destination: C.Cartesian3.fromDegrees(lon, lat - 0.004, g + 650),
          orientation: { heading: 0, pitch: rad(-45), roll: 0 } });
        await waitTiles(ms);
        // 用已經載入的圖塊量高度（很快）；以前用 sampleHeightMostDetailed，網路慢的時候會逾時，誤判成沒有 3D
        const n = 11, step = 25, dLat = step / 111320, dLon = step / (111320 * Math.cos(rad(lat)));
        const H = [];
        for (let i = 0; i < n; i++) for (let j = 0; j < n; j++)
          H.push(sampleHeight(lat + (i - (n - 1) / 2) * dLat, lon + (j - (n - 1) / 2) * dLon));
        const devs = [];
        for (let i = 1; i < n - 1; i++) for (let j = 1; j < n - 1; j++) {
          const h = H[i * n + j], nb = [H[(i - 1) * n + j], H[(i + 1) * n + j], H[i * n + j - 1], H[i * n + j + 1]];
          if ([h, ...nb].every(Number.isFinite)) devs.push(Math.abs(h - nb.reduce((a, b) => a + b, 0) / 4));
        }
        devs.sort((a, b) => a - b);
        const rough = devs.length ? devs[Math.floor(devs.length * 0.9)] : 0;
        // 量不到足夠的點 → ok = null（不知道）；呼叫的地方當作「有 3D」，用低空鏡頭
        return { ok: devs.length < 30 ? null : rough >= ROUGH_3D_M, rough, ground: g, samples: devs.length };
      },
      // 鏡頭：繞著 (lat, lon, h) 看，heading/pitch 用度，range 公尺
      view({ lat, lon, h = 40, heading = 0, pitch = -40, range = 500 }) {
        scene.screenSpaceCameraController.enableInputs = false;
        if (tileset) tileset.maximumScreenSpaceError = sseFor(range);
        viewer.camera.lookAt(C.Cartesian3.fromDegrees(lon, lat, h), new C.HeadingPitchRange(rad(heading), rad(pitch), range));
      },
      freeCamera() { viewer.camera.lookAtTransform(C.Matrix4.IDENTITY); scene.screenSpaceCameraController.enableInputs = true; },
      // 車子：位置 [lat, lon]、車頭方向（度，北 = 0 順時針）、路面高度（公尺，橢球高）、行駛中（開大燈）、透明度（停靠時淡出）
      setCar: ovl.setCar, showCar: ovl.showCar, setStop: ovl.setStop, setHeightFn: ovl.setHeightFn,
      setWalker(w) { ovl.setWalkers(Array.isArray(w) ? w : w ? [w] : []); },
      setNight(f) {
        ovl.setNight(f);
        if (nightShader) nightShader.setUniform('u_night', f);
        if (layer) { layer.brightness = 1 - 0.62 * f; layer.saturation = 1 - 0.45 * f; layer.contrast = 1 + 0.15 * f; }
        scene.skyAtmosphere.brightnessShift = -0.8 * f;
        scene.skyAtmosphere.saturationShift = -0.35 * f;
      },
      // 每一段路線：去程綠色、回程黃色（黑邊）；目前這一段是粗線，而且畫在最上面
      setLegs(list) {
        legs.forEach(l => viewer.entities.remove(l.e));
        legs = list.map(item => {
          const l = { path: item.path, kind: item.kind || 'go' };
          l.color = C.Color.fromCssColorString(l.kind === 'back' ? YELLOW : GREEN);
          const look = legLook(l, false);
          l.e = viewer.entities.add({ polyline: Object.assign({ positions: legPositions(l.path, LIFT) },
            flat ? { clampToGround: true } : { arcType: C.ArcType.NONE }, look) });
          return l;
        });
        active = -1;
      },
      refreshLegs() { legs.forEach((l, k) => { l.e.polyline.positions = legPositions(l.path, k === active ? LIFT_ACTIVE : LIFT); }); },
      setActiveLeg(i) {
        if (i === active) return;
        const was = active;
        active = i;
        // 大地圖只畫正在開的這一段（去程綠、回程黃）；兩個方向都畫在小地圖上
        legs.forEach((l, k) => {
          l.e.show = k === i;
          if (k !== i && k !== was) return;
          const on = k === i;
          Object.assign(l.e.polyline, legLook(l, on));
          if (!flat) l.e.polyline.positions = legPositions(l.path, on ? LIFT_ACTIVE : LIFT);
        });
      },
      // 地點圖釘（像 Google 地圖，DOM 文字：清楚、畫在車子上面）；停靠時被資訊卡取代（hidePin）
      async addPlace(o) { return ovl.addPin(o); },
      hidePin: ovl.hidePin,
      async addPin({ lat, lon, fast, label, sub }) { return ovl.addPin({ lat, lon, ev: true, fast, label, sub }); },
      clearMarkers: ovl.clearPins,
      // 還在下載、處理的圖塊數；播放時用來「緩衝」，畫面才不會糊
      pendingTiles() {
        if (!tileset) return scene.globe.tilesLoaded ? 0 : 6;
        const st = tileset.statistics;   // Cesium 的內部統計；拿不到就看 tilesLoaded
        return st ? (st.numberOfPendingRequests || 0) + (st.numberOfTilesProcessing || 0) : (tileset.tilesLoaded ? 0 : 30);
      },
      memoryMB() { return tileset ? Math.round(tileset.totalMemoryUsageInBytes / 1048576) : 0; },
      destroy() { try { viewer.destroy(); } catch (e) { /* 已經關掉 */ } },
    };
    return api;
  }

  window.Sim3D = { create, makePath, simplify, meters, bearing, angleLerpDeg, smooth, loadCesium, version: CESIUM_VER, rad, deg };
})();
