/* sim2d.js — 阿電 行車模擬的 2D 向量地圖（預設；只用在 website_v2）
 *
 * MapLibre GL（BSD-3）＋ OpenFreeMap 向量圖磚（免費、不用金鑰、可商用；資料 © OpenStreetMap 貢獻者，ODbL；
 * 圖磚格式 © OpenMapTiles）。向量地圖馬上畫好、字永遠是正的、可以跟著車轉，也可以先把整條路線載好。
 * 和 sim3d.js（Google 3D 街景）同一套介面，所以時間軸（sim3d-timeline.js）、情境（sim3d-scenes.js）不用改：
 *   const sim = await Sim2D.create(el, { creditContainer, avoid, spriteBase });
 *   sim.view({ lat, lon, heading, pitch, range }) / setLegs / setActiveLeg / addPlace / addPin / setCar / setStop / setWalker / setNight …
 * 鏡頭換算：Cesium 的 range（鏡頭到目標的距離，公尺）→ MapLibre 的 zoom；pitch（往下看幾度，負的）→ MapLibre pitch = 90 + pitch。
 */
(function () {
  'use strict';
  const VER = '4.7.1';
  const JS = `https://cdn.jsdelivr.net/npm/maplibre-gl@${VER}/dist/maplibre-gl.js`;
  const CSS_URL = `https://cdn.jsdelivr.net/npm/maplibre-gl@${VER}/dist/maplibre-gl.css`;
  const STYLE = 'https://tiles.openfreemap.org/styles/liberty';
  const ATTRIB = '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> 資料 © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap 貢獻者</a>';
  const GREEN = '#27F550', INK = '#141B2D', YELLOW = '#FFD84D';
  const FOV = 0.6435011087932844;   // MapLibre 預設垂直視角（36.87°）
  const EARTH = 40075016.686;

  let loading = null;
  function loadMapLibre() {
    if (window.maplibregl) return Promise.resolve(window.maplibregl);
    if (loading) return loading;
    loading = new Promise((resolve, reject) => {
      const css = document.createElement('link'); css.rel = 'stylesheet'; css.href = CSS_URL; document.head.appendChild(css);
      const s = document.createElement('script'); s.src = JS;
      s.onload = () => (window.maplibregl ? resolve(window.maplibregl) : reject(new Error('maplibre missing')));
      s.onerror = () => reject(new Error('maplibre load failed'));
      document.head.appendChild(s);
    });
    return loading;
  }
  const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;

  async function create(container, opts = {}) {
    const ML = await loadMapLibre();
    const mapEl = document.createElement('div'); mapEl.style.cssText = 'position:absolute;inset:0;';
    container.appendChild(mapEl);
    const map = new ML.Map({
      container: mapEl, style: STYLE, interactive: false, attributionControl: false, maxPitch: 85, fadeDuration: 0,
      center: [121.5, 25.03], zoom: 12, pixelRatio: Math.min(2, window.devicePixelRatio || 1),
      localIdeographFontFamily: '"Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif',   // 中文字用本機字型畫（清楚，也不用下載字型檔）
      canvasContextAttributes: { preserveDrawingBuffer: true }, preserveDrawingBuffer: true,
    });
    await new Promise((ok, bad) => { map.once('load', ok); map.once('error', e => bad(e.error || new Error('style'))); });
    if (opts.creditContainer) opts.creditContainer.innerHTML = `<span class="ml-credit">地圖 ${ATTRIB}</span>`;
    // 地名用中文（台灣的 OSM 名稱本來就是中文；有 name:zh-Hant 就用它）；商店、餐廳等 POI 圖示收起來，畫面比較乾淨
    map.getStyle().layers.forEach(l => {
      if (l.type !== 'symbol') return;
      if (/poi/i.test(l.id)) { map.setLayoutProperty(l.id, 'visibility', 'none'); return; }
      const tf = map.getLayoutProperty(l.id, 'text-field');
      if (tf && JSON.stringify(tf).includes('name')) map.setLayoutProperty(l.id, 'text-field', ['coalesce', ['get', 'name:zh-Hant'], ['get', 'name:zh'], ['get', 'name']]);
    });
    // 夜晚：地圖上蓋一層深藍（車子、圖釘、資訊卡在更上面，仍然很亮）
    const tint = document.createElement('div');
    tint.style.cssText = 'position:absolute;inset:0;pointer-events:none;background:#0b1640;mix-blend-mode:multiply;opacity:0;';
    container.appendChild(tint);

    let cam = { lat: 25.03, lon: 121.5, heading: 0, pitch: -50, range: 800 };
    const ovl = SimOverlay.create(container, {
      project(lat, lon) {
        const p = map.project([lon, lat]);
        // 在鏡頭後面、或遠過地平線的點不畫
        return Number.isFinite(p.x) && Number.isFinite(p.y) && p.y > -2000 ? { x: p.x, y: p.y } : null;
      },
      camera(lat, lon) { return { heading: map.getBearing(), pitch: map.getPitch() - 90, dist: cam.range }; },
      avoid: opts.avoid,
    }, { spriteBase: opts.spriteBase });
    let frames = 0;
    map.on('render', () => { frames++; ovl.draw(); });

    // 路線：每一段一個 GeoJSON 圖層（黑邊＋顏色）；大地圖只顯示正在開的這一段
    let legs = [], active = -1;
    const lineData = path => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: path.coords.map(([la, lo]) => [lo, la]) } });
    function legLook(l, on) {
      const v = on ? 'visible' : 'none';
      map.setLayoutProperty(l.id + '-c', 'visibility', v); map.setLayoutProperty(l.id + '-l', 'visibility', v);
    }
    const tilesDone = () => map.loaded() && map.areTilesLoaded();

    const api = {
      flat: true, vector: true, map, stats: { loads: 0 }, carReady: ovl.carReady,
      async waitTiles(maxMs = 1500) {
        const t0 = performance.now(), f0 = frames;
        map.triggerRepaint();
        while (frames - f0 < 2 && performance.now() - t0 < maxMs) await new Promise(r => setTimeout(r, 16));
        while (!tilesDone() && performance.now() - t0 < maxMs) await new Promise(r => setTimeout(r, 40));
        return tilesDone();
      },
      sampleHeight: () => 0,
      async probe() { return { ok: false, rough: 0, ground: 0, samples: 0 }; },
      view({ lat, lon, heading = 0, pitch = -50, range = 800 }) {
        cam = { lat, lon, heading, pitch, range };
        const H = mapEl.clientHeight || 800;
        const camPx = 0.5 * H / Math.tan(FOV / 2);   // 鏡頭到畫面中心的距離（像素）
        const zoom = Math.log2(camPx * EARTH * Math.cos(rad(lat)) / (512 * Math.max(30, range)));
        map.jumpTo({ center: [lon, lat], zoom: Math.max(1, Math.min(20.5, zoom)), bearing: heading, pitch: Math.max(0, Math.min(85, 90 + pitch)) });
      },
      freeCamera() {},
      setCar: ovl.setCar, showCar: ovl.showCar, setStop: ovl.setStop, setHeightFn: ovl.setHeightFn,
      setWalker(w) { ovl.setWalkers(Array.isArray(w) ? w : w ? [w] : []); },
      setNight(f) { ovl.setNight(f); tint.style.opacity = (0.55 * f).toFixed(3); },
      setLegs(list) {
        legs.forEach(l => { [l.id + '-l', l.id + '-c'].forEach(id => map.getLayer(id) && map.removeLayer(id)); map.getSource(l.id) && map.removeSource(l.id); });
        legs = list.map((item, k) => {
          const l = { id: 'leg' + k, path: item.path, kind: item.kind || 'go' };
          map.addSource(l.id, { type: 'geojson', data: lineData(l.path) });
          map.addLayer({ id: l.id + '-c', type: 'line', source: l.id, layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
            paint: { 'line-color': INK, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 7, 16, 15] } });
          map.addLayer({ id: l.id + '-l', type: 'line', source: l.id, layout: { 'line-join': 'round', 'line-cap': 'round', visibility: 'none' },
            paint: { 'line-color': l.kind === 'back' ? YELLOW : GREEN, 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 4, 16, 9] } });
          return l;
        });
        active = -1;
      },
      refreshLegs() {},
      setActiveLeg(i) {
        if (i === active) return;
        legs.forEach((l, k) => legLook(l, k === i));
        active = i;
      },
      async addPlace(o) { return ovl.addPin(o); },
      hidePin: ovl.hidePin,
      async addPin({ lat, lon, fast, label, sub }) { return ovl.addPin({ lat, lon, ev: true, fast, label, sub }); },
      clearMarkers: ovl.clearPins,
      pendingTiles: () => (tilesDone() ? 0 : 6),
      memoryMB: () => 0,
      destroy() { try { map.remove(); } catch (e) { /* 已經關掉 */ } },
    };
    return api;
  }

  window.Sim2D = { create, version: VER };
})();
