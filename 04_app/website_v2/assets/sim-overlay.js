/* sim-overlay.js — 模擬地圖上面的一層（DOM）：bZ4X 小車、地點圖釘、走路的人、停靠資訊卡（只用在 website_v2）
 *
 * 3D（sim3d.js，Cesium）和 2D（sim2d.js，MapLibre）共用。地圖每畫完一格就呼叫 draw()，位置與地圖完全同步。
 *   const ov = SimOverlay.create(container, {
 *     project: (lat, lon, h) => ({ x, y }) | null,          // 地圖上的點 → 畫面座標（CSS px）
 *     camera:  (lat, lon, h) => ({ heading, pitch, dist }),  // 從這一點看鏡頭的方向（度）、俯角（度，負的）、距離（公尺）
 *     avoid:   () => [DOMRect…],                             // 資訊卡要避開的面板（例如阿電的字幕）
 *     spriteBase: '../assets/characters/',                   // 陳家人物圖（dad/mom/son/daughter.png 或 .svg）；沒有就用表情符號
 *   });
 * 疊放順序（下→上）：車子 → 圖釘 → 走路的人 → 資訊卡。圖釘是 DOM 文字，任何縮放都清楚，而且不會被車子蓋住。
 */
(function () {
  'use strict';
  const INK = '#141B2D', GREEN = '#27F550', YELLOW = '#FFD84D';
  const EMOJI = '"Noto Color Emoji", "Segoe UI Emoji", "Apple Color Emoji", sans-serif';
  const PEOPLE = { dad: '👨', mom: '👩', son: '👦', daughter: '👧', walker: '🚶', kid: '🧒' };
  const CSS = `
    .sim-ov { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 1; }
    .sim-ov > .lyr { position: absolute; inset: 0; }
    .sim-ov > .lyr.car { z-index: 1; } .sim-ov > .lyr.pin { z-index: 2; } .sim-ov > .lyr.walk { z-index: 3; }   /* 11/13：人物一定畫在車子上面 */
    .sim-pin { position: absolute; left: 0; top: 0; display: none; align-items: center; will-change: transform;
      font-family: "Noto Sans TC", -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif; color: ${INK}; }
    .sim-pin i { position: relative; z-index: 1; flex: none; width: 54px; height: 54px; border-radius: 50%; background: #fff; border: 4px solid ${INK};
      box-sizing: border-box; box-shadow: 3px 3px 0 ${INK}; display: flex; align-items: center; justify-content: center;
      font-style: normal; font-size: 28px; line-height: 1; font-family: ${EMOJI}; }
    .sim-pin i::after { content: ""; position: absolute; left: 50%; bottom: -15px; margin-left: -9px;
      border-left: 9px solid transparent; border-right: 9px solid transparent; border-top: 12px solid ${INK}; }
    .sim-pin.home i { background: ${GREEN}; }
    .sim-pin.charge i { background: ${YELLOW}; }
    .sim-pin b { margin-left: -12px; padding: 5px 14px 5px 20px; background: #fff; border: 3px solid ${INK}; border-radius: 10px;
      box-shadow: 3px 3px 0 ${INK}; font-size: 20px; font-weight: 900; white-space: nowrap; }
    .sim-pin.left { flex-direction: row-reverse; }
    .sim-pin.left b { margin-left: 0; margin-right: -12px; padding: 5px 20px 5px 14px; }
    .sim-pin.mini i { width: 34px; height: 34px; font-size: 17px; border-width: 3px; box-shadow: 2px 2px 0 ${INK}; }
    .sim-pin.mini i::after { bottom: -11px; margin-left: -6px; border-left-width: 6px; border-right-width: 6px; border-top-width: 9px; }
    .far .sim-pin.mini b { display: none; } .far .sim-pin.mini i { width: 26px; height: 26px; font-size: 13px; }
    .sim-pin.mini b { font-size: 14px; padding: 2px 9px 2px 14px; border-width: 2px; box-shadow: 2px 2px 0 ${INK}; }
    .sim-pin.ev { align-items: flex-start; }   /* 11/16：充電站＝定位圖釘＋閃電（快充黃、慢充綠），旁邊寫接頭、費率 */
    .sim-pin.ev svg { flex: none; width: 36px; height: 46px; filter: drop-shadow(2px 2px 0 ${INK}); }
    .sim-pin.ev .evl { margin: 2px 0 0 3px; padding: 3px 9px 4px; background: #fff; border: 2px solid ${INK}; border-radius: 9px; box-shadow: 2px 2px 0 ${INK}; white-space: nowrap; line-height: 1.25; }
    .sim-pin.ev .evl span { display: block; font-size: 13px; font-weight: 900; } .sim-pin.ev .evl small { display: block; font-size: 11.5px; font-weight: 700; color: #3a4256; }
    .far .sim-pin.ev .evl { display: none; } .far .sim-pin.ev svg { width: 26px; height: 33px; }
    .sim-stop { position: absolute; left: 0; top: 0; display: none; align-items: center; gap: 14px; padding: 12px 24px 12px 12px;
      background: #fff; border: 4px solid ${INK}; border-radius: 16px; box-shadow: 6px 6px 0 ${INK}; color: ${INK}; white-space: nowrap;
      transform-origin: 50% 100%; will-change: transform, opacity; font-family: "Noto Sans TC", -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif; }
    .sim-stop::after { content: ""; position: absolute; left: 50%; bottom: -21px; margin-left: -13px;
      border-left: 13px solid transparent; border-right: 13px solid transparent; border-top: 17px solid ${INK}; }
    .sim-stop.away::after { display: none; }
    .sim-stop .ic { flex: none; width: 62px; height: 62px; border-radius: 50%; background: #fff; border: 4px solid ${INK};
      display: flex; align-items: center; justify-content: center; font-size: 32px; line-height: 1; font-family: ${EMOJI}; }
    .sim-stop.charge .ic { background: ${YELLOW}; }
    .sim-stop.home .ic { background: ${GREEN}; }
    .sim-stop b { display: block; font-size: 26px; font-weight: 900; line-height: 1.2; }
    .sim-stop span { display: block; font-size: 18px; font-weight: 700; line-height: 1.35; color: #3a4256; margin-top: 2px; }
    .sim-stop em { display: block; font-style: normal; font-size: 17px; font-weight: 900; line-height: 1.35; margin-top: 6px;
      padding: 4px 10px; border: 3px solid ${INK}; border-radius: 10px; background: #FFF6CC; }
    .sim-stop small { display: block; font-size: 14px; font-weight: 700; color: #6b7385; margin-top: 4px; }
    .sim-stop.big .ic { width: 78px; height: 78px; font-size: 40px; }
    .sim-stop.big b { font-size: 30px; }
    .sim-walk { position: absolute; left: 0; top: 0; display: none; font-size: 36px; line-height: 1; font-family: ${EMOJI};
      filter: drop-shadow(0 0 2px #fff) drop-shadow(2px 2px 0 ${INK}); will-change: transform; }
    .sim-walk img { display: block; height: 56px; width: auto; }
    .sim-walk:has(img) { filter: none; }
    @media (max-height: 760px) { .sim-stop b { font-size: 22px; } .sim-stop span { font-size: 16px; } .sim-stop .ic { width: 52px; height: 52px; font-size: 27px; }
      .sim-pin i { width: 46px; height: 46px; font-size: 24px; } .sim-pin b { font-size: 17px; } }`;
  function injectCss() {
    if (document.getElementById('sim-overlay-css')) return;
    const st = document.createElement('style'); st.id = 'sim-overlay-css'; st.textContent = CSS;
    document.head.appendChild(st);
  }
  const div = cls => { const d = document.createElement('div'); if (cls) d.className = cls; return d; };

  // 陳家人物圖（05_brand/characters 的 walk_<名字>_<0|1>.png，複製到 assets/characters/）：兩格走路動作、面向右、腳在 (46%, 95%)。
  // 圖還沒載好或找不到時，用表情符號
  const FILE = { dad: 'dad', mom: 'mum', son: 'son', daughter: 'daughter' };
  const sprites = {};
  function sprite(id, frame, base) {
    if (!base || !FILE[id]) return null;
    const key = id + frame;
    if (!(key in sprites)) {
      sprites[key] = null;
      const img = new Image();
      img.onload = () => { sprites[key] = img.src; };
      img.src = `${base}walk_${FILE[id]}_${frame}.png`;
    }
    return sprites[key];
  }

  function create(container, hooks, opts = {}) {
    injectCss();
    Object.keys(FILE).forEach(id => { sprite(id, 0, opts.spriteBase); sprite(id, 1, opts.spriteBase); });   // 先載好人物圖
    const ov = div('sim-ov'); container.appendChild(ov);
    const carLayer = div('lyr'), pinLayer = div('lyr'), walkLayer = div('lyr');
    carLayer.classList.add('car'); pinLayer.classList.add('pin'); walkLayer.classList.add('walk');
    ov.append(carLayer, pinLayer, walkLayer);
    const stopEl = div('sim-stop');
    stopEl.innerHTML = '<div class="ic"></div><div class="tx"><b></b><span></span><em></em><small></small></div>';
    ov.appendChild(stopEl);
    const icEl = stopEl.querySelector('.ic'), tEl = stopEl.querySelector('b'), lEl = stopEl.querySelector('span'), dEl = stopEl.querySelector('em'), nEl = stopEl.querySelector('small');

    let car3d = null, carOn = true, heightFn = () => 0;
    const carReady = (window.BZ4XCar ? BZ4XCar.create(carLayer) : Promise.resolve(null))
      .then(c => { car3d = c; return c; }).catch(e => { console.warn('bZ4X 小車無法建立', e); return null; });
    const carSt = { p: null, heading: 0, h: 0, night: 0, moving: false, alpha: 1 };
    let stopSt = null, stopShown = false, stopSig = '', walkers = [], hiddenKey = null;
    const walkEls = [], pins = [];
    const W = () => container.clientWidth, H = () => container.clientHeight;

    function drawCar() {
      if (!car3d) return;
      if (!carOn || !carSt.p || carSt.alpha <= 0.01) { car3d.hide(); return; }
      const xy = hooks.project(carSt.p[0], carSt.p[1], carSt.h);
      if (!xy) { car3d.hide(); return; }
      const cam = hooks.camera(carSt.p[0], carSt.p[1], carSt.h);
      // 車長：近的時候約 104 px，拉遠慢慢變小（最小 56 px），像導航 App 的車
      const lengthPx = Math.max(56, Math.min(104, 104 - 15 * Math.log2(Math.max(1, cam.dist / 520))));
      // 車頭方向做一點點平滑（約 0.12 秒）：路線上很短的折線會讓方向每格跳幾度，看起來在抖；轉超過 60 度（換場景、拖時間軸）直接跳過去
      const now = performance.now(), dt = Math.min(0.2, Math.max(0, (now - (carSt.tDraw || now)) / 1000)); carSt.tDraw = now;
      const diff = ((carSt.heading - (carSt.hShow ?? carSt.heading)) % 360 + 540) % 360 - 180;
      carSt.hShow = Math.abs(diff) > 60 || carSt.hShow == null ? carSt.heading : carSt.hShow + diff * (1 - Math.exp(-dt / 0.12));
      carSt.lenPx = lengthPx;
      car3d.render({ x: xy.x, y: xy.y, yaw: carSt.hShow - cam.heading, pitch: cam.pitch, lengthPx, night: carSt.night, moving: carSt.moving, alpha: carSt.alpha });
    }
    function drawPins() {
      const w = W(), h = H();
      // 11/16：鏡頭拉高（快轉、總覽）時，附近充電站的小圖釘只留閃電，不顯示「快充 670 公尺」，免得字疊在一起
      const ref = carSt.p || (pins[0] && [pins[0].lat, pins[0].lon]), cam = ref && hooks.camera ? hooks.camera(ref[0], ref[1], 0) : null;
      pinLayer.classList.toggle('far', !!(cam && cam.dist > 1800));
      pins.forEach(p => {
        const xy = p.key != null && p.key === hiddenKey ? null : hooks.project(p.lat, p.lon, heightFn(p.lat, p.lon));
        if (!xy || xy.x < -300 || xy.y < -100 || xy.x > w + 300 || xy.y > h + 100) { if (p.on) { p.el.style.display = 'none'; p.on = false; } return; }
        if (!p.on) { p.el.style.display = 'flex'; p.on = true; p.w = p.el.offsetWidth; }
        if (p.ev) { const f = pinLayer.classList.contains('far') ? 26 / 36 : 1; p.el.style.transform = `translate(${(xy.x - 18 * f).toFixed(1)}px, ${(xy.y - 45 * f).toFixed(1)}px)`; return; }
        const r = p.mini ? 17 : 27, tip = p.mini ? 29 : 42;   // 圓的半徑、尖端到圓心的距離
        const ax = p.left ? p.w - r : r;
        p.el.style.transform = `translate(${(xy.x - ax).toFixed(1)}px, ${(xy.y - r - tip + (p.mini ? 6 : 8)).toFixed(1)}px)`;
      });
    }
    function drawWalkers() {
      walkers.forEach((w, i) => {
        let el = walkEls[i];
        if (!el) { el = walkEls[i] = div('sim-walk'); walkLayer.appendChild(el); }
        const a = w && w.from && w.to && w.f >= 0 && w.f < 0.985 ? hooks.project(w.from[0], w.from[1], w.h) : null;
        const b = a ? hooks.project(w.to[0], w.to[1], w.h) : null;
        let ax, ay, dx, dy, L;
        if (b) { ax = a.x; ay = a.y; dx = b.x - ax; dy = b.y - ay; L = Math.hypot(dx, dy); }
        if (!b || L < 18) { el.style.display = 'none'; return; }   // 太近（鏡頭很高）、或已經上車：不畫
        const clipped = L > 170;
        if (clipped) { ax = b.x - dx / L * 170; ay = b.y - dy / L * 170; dx = b.x - ax; dy = b.y - ay; L = 170; }   // 地點離路邊很遠：只畫最後一小段
        // 11/13：一碰到車身就消失（上車）；下車的人從車身邊緣出現，不從車子中間冒出來
        const carR = (carSt.lenPx || 80) * 0.38;
        if ((w.toCar && (1 - w.f) * L < carR) || (w.fromCar && !clipped && w.f * L < carR)) { el.style.display = 'none'; return; }
        const x = ax + dx * w.f, y = ay + dy * w.f - Math.abs(Math.sin(w.f * Math.PI * 5)) * 5;
        // 走路動作：兩格輪流（依走了多遠換格，一格一格錄影也一樣）
        const frame = Math.floor(w.f * 8) % 2, img = sprite(w.who, frame, opts.spriteBase) || sprite(w.who, 1 - frame, opts.spriteBase);
        const sig = img || PEOPLE[w.who] || w.emoji || '🚶';
        if (el.dataset.sig !== sig) { el.dataset.sig = sig; el.innerHTML = img ? `<img alt="" src="${img}">` : ''; if (!img) el.textContent = sig; }
        el.style.display = 'block';
        // 表情符號預設面向左；人物圖面向右。往另一邊走就左右翻轉
        const flip = img ? (dx < 0 ? -1 : 1) : (dx > 0 ? -1 : 1);
        el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(${img ? '-46%, -95%' : '-50%, -90%'}) scaleX(${flip})`;
        el.style.opacity = w.fromCar ? '1' : Math.min(1, w.f * 10).toFixed(2);
      });
      for (let i = walkers.length; i < walkEls.length; i++) walkEls[i].style.display = 'none';
    }
    function hideStop() { if (stopShown) { stopEl.style.display = 'none'; stopShown = false; } }
    function drawStop() {
      const s = stopSt;
      if (!s || !s.p || !(s.k > 0.01)) { hideStop(); return; }
      const xy = hooks.project(s.p[0], s.p[1], s.h);
      if (!xy) { hideStop(); return; }
      const sig = [s.icon, s.title, s.line, s.detail, s.note, s.tone].join('|');
      if (sig !== stopSig) {
        stopSig = sig; stopEl.className = 'sim-stop' + (s.tone ? ' ' + s.tone : '') + (s.detail ? ' big' : '');
        icEl.textContent = s.icon || ''; tEl.textContent = s.title || ''; lEl.textContent = s.line || ''; lEl.style.display = s.line ? '' : 'none';
        dEl.textContent = s.detail || ''; dEl.style.display = s.detail ? '' : 'none';
        nEl.textContent = s.note || ''; nEl.style.display = s.note ? '' : 'none';
      }
      if (!stopShown) { stopEl.style.display = 'flex'; stopShown = true; }
      // 卡片不要跑出畫面（上面留給分頁與時鐘），也不要被阿電的字幕、下面的數字蓋住
      const cw = stopEl.offsetWidth, ch = stopEl.offsetHeight, w = W();
      let x = Math.max(cw / 2 + 16, Math.min(w - cw / 2 - 16, xy.x)), y = Math.max(ch + 104, xy.y - (s.lift || 0));
      const box = container.getBoundingClientRect();
      let moved = false;
      (hooks.avoid ? hooks.avoid() : []).forEach(r => {
        if (!r || !r.width) return;
        const L = r.left - box.left, T = r.top - box.top, R = L + r.width;
        const cl = x - cw / 2, cr = x + cw / 2, cb = y - 22, ct = cb - ch;
        if (cr < L || cl > R || cb < T || ct > T + r.height) return;
        if (T - 12 - ch >= 104) { y = T - 12 + 22; moved = true; }                  // 移到面板上面
        else { x = Math.min(w - cw / 2 - 16, R + 16 + cw / 2); moved = true; }      // 不然移到右邊
      });
      stopEl.classList.toggle('away', moved);
      stopEl.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%) translateY(-22px) scale(${s.k.toFixed(3)})`;
      stopEl.style.opacity = Math.min(1, s.k * 1.6).toFixed(3);
    }

    return {
      carReady,
      draw() { drawCar(); drawPins(); drawWalkers(); drawStop(); },
      setCar(p, heading = 0, h = 0, moving = false, alpha = 1) {
        carSt.p = p || null; carSt.heading = heading; carSt.h = Number.isFinite(h) ? h : 0; carSt.moving = moving; carSt.alpha = alpha;
      },
      showCar(on) { carOn = !!on; },
      setNight(f) { carSt.night = f; },
      setStop(s) { stopSt = s || null; },
      setWalkers(list) { walkers = (list || []).filter(Boolean); },
      setHeightFn(fn) { if (typeof fn === 'function') heightFn = fn; },
      // 地點圖釘（像 Google 地圖）：一直顯示；停靠時被資訊卡取代（hidePin）。mini = 附近其他充電站
      addPin({ lat, lon, icon, label, tone, key, side, mini, ev, fast, sub }) {
        if (ev) {   // 附近的充電站
          const el = div('sim-pin ev' + (fast ? ' fast' : ''));
          el.innerHTML = `<svg viewBox="0 0 36 46" aria-hidden="true"><path d="M18 2.5C9.4 2.5 2.5 9.3 2.5 17.7 2.5 28.8 18 44 18 44s15.5-15.2 15.5-26.3C33.5 9.3 26.6 2.5 18 2.5z" fill="${fast ? YELLOW : GREEN}" stroke="${INK}" stroke-width="3"/><circle cx="18" cy="17.5" r="9.5" fill="#fff" stroke="${INK}" stroke-width="2.5"/><path d="M19.8 10.6 13.4 18.9h4.3l-1.6 6.2 6.6-8.7h-4.4z" fill="${INK}"/></svg>`
            + (label ? '<div class="evl"><span></span>' + (sub ? '<small></small>' : '') + '</div>' : '');
          if (label) { el.querySelector('.evl span').textContent = label; if (sub) el.querySelector('.evl small').textContent = sub; }
          pinLayer.appendChild(el);
          const p = { lat, lon, key, ev: true, el, on: false, w: 0 };
          pins.push(p);
          return p;
        }
        const el = div('sim-pin' + (tone ? ' ' + tone : '') + (side === 'left' ? ' left' : '') + (mini ? ' mini' : ''));
        el.innerHTML = '<i></i>' + (label ? '<b></b>' : '');
        el.querySelector('i').textContent = icon || '📍';
        if (label) el.querySelector('b').textContent = label;
        pinLayer.appendChild(el);
        const p = { lat, lon, key, mini: !!mini, left: side === 'left' && !!label, el, on: false, w: 0 };
        pins.push(p);
        return p;
      },
      hidePin(key) { hiddenKey = key; },
      clearPins() { pins.splice(0).forEach(p => p.el.remove()); },
    };
  }

  window.SimOverlay = { create, PEOPLE };
})();
