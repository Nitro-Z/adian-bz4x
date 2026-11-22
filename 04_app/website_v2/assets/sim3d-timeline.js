/* sim3d-timeline.js — 把 3D 模擬變成可以播放、暫停、拖曳、倍速的「影片」（只用在 website_v2）
 *
 * 畫面上的一切（車子的位置與方向、鏡頭、電量、時鐘、里程、夜晚、停靠資訊卡）都只由時間 t 決定，
 * 所以可以任意跳到某一秒，也可以一格一格畫出來錄成影片（renderAt + sim.waitTiles）。
 *
 *   const tl = SimTimeline.create({ sim, raw, cues, onState, onCue });
 *   await tl.preload(p => …);   // 照真正播放的鏡頭走一遍，把 3D 圖塊載好、順便量路面高度
 *   tl.play(); tl.pause(); tl.seek(秒); tl.setSpeed(2);
 *
 * raw 片段：
 *   { type: 'drive', path, leg, cam, pace?, dur?, clock: [分, 分], bat: [%, %], km: [, ], night: [0–1, 0–1], state, chapter, ff? }
 *   { type: 'stay', at: [lat, lon], orbit: { range, pitch, from?, to?, turn? }, car?, carHeading?, stop?, dur, clock, bat, km, night, state, chapter, ff? }
 * 兩段之間自動插入鏡頭轉場（flyIn 秒；沒給就依角度與距離自動決定，0 = 直接接上）。
 * cues：[{ seg, u, text, show }]（seg = raw 的索引，u = 該段的 0–1）
 *
 * 停靠（stay.stop = { icon, title, line, tone, key, hideCar?, walkIn?, walkOut? }）：
 *   車子停在路邊（路線終點，在路上）→ 淡出 → 資訊卡在那裡跳出來（是什麼地方、在做什麼）→ 要走前卡片收起、車子再出現。
 *   walkIn { emoji, to }：下車的人走向地點；walkOut { emoji, from }：人從地點走回車子（例如接小孩）。
 *
 * 行車節奏（不暈的關鍵）：畫面上的移動速度固定在「每秒約 12% 個畫面」。起點、終點附近鏡頭低、車子慢；
 * 中段鏡頭拉高（cam.rangeMax），車子在地上開得快，但畫面看起來一樣慢。
 *   cam  = { range, rangeMax?, ramp?(公尺), pitch, pitchMax?, fixedHeading?, anchor? }
 *   pace = { sigma: 0.12, sigmaMax?, maxDur?, minDur? }（有 dur 就照 dur，例如快轉）
 *   cam.anchor = { at: [lat, lon], range, pitch, from, to }：鏡頭不跟車，固定看一個地方（一週的快轉）
 */
(function () {
  'use strict';
  const { bearing, meters, angleLerpDeg, smooth, deg } = Sim3D;
  const lerp = (a, b, u) => a + (b - a) * u;
  const clamp01 = x => Math.max(0, Math.min(1, x));
  const ramp = (t, a, b) => clamp01((t - a) / (b - a));
  const gentle = u => lerp(u, smooth(u), 0.6);   // 起步、停車稍微慢一點
  const wrap = a => ((a % 360) + 540) % 360 - 180;   // 角度差換到 −180…180
  const easeOutBack = x => 1 + 2.70158 * (x - 1) ** 3 + 1.70158 * (x - 1) ** 2;   // 彈出來（稍微超過再回來）

  // 追車鏡頭的方向：取前後一段路（span 公尺）的平均方向。只由位置決定，所以拖曳時間軸也不會抖。
  function chaseHeading(path, d, span = 300) {
    let x = 0, y = 0;
    const step = span / 6;
    for (let k = -2; k <= 4; k++) {
      const a = path.at(d + k * step), b = path.at(d + k * step + step * 0.8);
      if (meters(a, b) > 2) { const br = bearing(a, b), w = k < 0 ? 0.6 : 1; x += Math.cos(br) * w; y += Math.sin(br) * w; }
    }
    return deg(Math.atan2(y, x));
  }
  // 車頭方向：前後各 15 公尺的方向（避開路線折點的抖動）
  function roadHeading(path, d) {
    const a = path.at(d - 15), b = path.at(d + 15);
    return meters(a, b) > 1 ? deg(bearing(a, b)) : null;
  }

  // 大範圍的地面高度（~110 公尺的格子）：高空固定鏡頭的中心、找不到路面高度時的備用
  function heightField(dflt = 40) {
    const cells = new Map(), key = (la, lo) => `${Math.round(la * 900)},${Math.round(lo * 900)}`;
    let sum = 0, n = 0;
    return {
      add(la, lo, h) {
        if (!Number.isFinite(h)) return;
        const k = key(la, lo), old = cells.get(k);
        cells.set(k, old == null ? h : Math.min(old, h));   // 取低的（避開屋頂）
        sum += h; n++;
      },
      at(la, lo) {
        const r = Math.round(la * 900), c = Math.round(lo * 900);
        for (let k = 0; k <= 2; k++) for (let i = -k; i <= k; i++) for (let j = -k; j <= k; j++) {
          const v = cells.get(`${r + i},${c + j}`); if (v != null) return v;
        }
        return n ? sum / n : dflt;
      },
    };
  }

  // 行車：準備鏡頭高度、俯角與「時間 → 距離」對照表
  function setupDrive(s) {
    const L = s.path.total, c = s.cam;
    const rMin = c.range, rMax = Math.max(rMin, c.rangeMax || rMin);
    const R = Math.max(1, Math.min(c.ramp || 1500, L / 2));
    const varies = rMax > rMin || c.pitchMax != null;
    s.rampAt = d => varies ? smooth(clamp01(Math.min(d, L - d) / R)) : 0;
    s.rangeAt = d => rMin + (rMax - rMin) * s.rampAt(d);
    s.pitchAt = d => c.pitchMax != null ? lerp(c.pitch, c.pitchMax, s.rampAt(d)) : c.pitch;
    s.legHeading = deg(bearing(s.path.at(0), s.path.at(L)));
    if (c.anchor && s.dur == null) s.dur = 4;
    if (s.dur != null) { s.distAt = u => L * gentle(clamp01(u)); return; }
    const pc = s.pace || {}, sg0 = pc.sigma || 0.12, sg1 = pc.sigmaMax || sg0;
    const E = Math.min(70, L / 4), N = Math.max(60, Math.min(2000, Math.ceil(L / 12)));
    const ts = new Float64Array(N + 1);
    for (let i = 1; i <= N; i++) {
      const dm = L * (i - 0.5) / N, k = s.rampAt(dm);
      const v = (sg0 + (sg1 - sg0) * k) * s.rangeAt(dm) * (0.2 + 0.8 * smooth(clamp01(Math.min(dm, L - dm) / E)));
      ts[i] = ts[i - 1] + (L / N) / v;
    }
    let f = 1;
    if (pc.maxDur && ts[N] > pc.maxDur) f = pc.maxDur / ts[N];
    if (pc.minDur && ts[N] < pc.minDur) f = pc.minDur / ts[N];
    for (let i = 0; i <= N; i++) ts[i] *= f;
    s.dur = ts[N];
    s.distAt = u => {
      const t = clamp01(u) * ts[N];
      let lo = 0, hi = N;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
      return L * (lo + (t - ts[lo]) / ((ts[hi] - ts[lo]) || 1)) / N;
    };
  }

  // 鏡頭方向表：沿時間先算好，再限制轉動速度（每秒最多 MAX_TURN 度）。急彎、迴轉時鏡頭也只會慢慢轉
  // startH：從上一個畫面結束時的方向開始轉（轉場就不用大轉彎；大轉彎改在開車時以每秒 14° 慢慢轉）
  const MAX_TURN = 14;
  function headingTable(s, startH) {
    const c = s.cam;
    if (c.anchor || c.fixedHeading != null) return;
    const N = 400, ds = new Float64Array(N + 1), hs = new Float64Array(N + 1), dt = s.dur / N;
    for (let k = 0; k <= N; k++) {
      const d = s.distAt(k / N), ch = chaseHeading(s.path, d, c.span || Math.max(300, s.rangeAt(d) * 0.9));
      const want = angleLerpDeg(ch, s.legHeading, s.rampAt(d));   // 拉高時固定一個方向，不跟著彎路轉
      ds[k] = d;
      hs[k] = k ? hs[k - 1] + Math.max(-MAX_TURN * dt, Math.min(MAX_TURN * dt, wrap(want - hs[k - 1]))) : (startH != null ? startH : want);
    }
    s.headAt = d => {
      let lo = 0, hi = N;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ds[m] <= d) lo = m; else hi = m; }
      const f = clamp01((d - ds[lo]) / ((ds[hi] - ds[lo]) || 1));
      return hs[lo] + (hs[hi] - hs[lo]) * f;
    };
  }

  // northUp：鏡頭一律北方朝上（2D 點陣地圖用：字才不會跟著轉、倒過來）
  function create({ sim, raw, cues = [], onState, onCue, onEnd, adaptive = true, northUp = false }) {
    const hf = heightField(sim.flat ? 0 : 40);   // 2D 地圖：地面就是高度 0
    if (sim.setHeightFn) sim.setHeightFn((la, lo) => hf.at(la, lo));   // 地點圖釘畫在地面高度
    raw.forEach((s, i) => { s.raw = i; if (s.type === 'drive') setupDrive(s); });
    // 所有路線（路面高度存在路線上；休息站前後兩段共用一條）
    const paths = [...new Set(raw.filter(s => s.type === 'drive').map(s => s.path.root || s.path))];
    paths.forEach(p => p.setFallback && p.setFallback((la, lo) => hf.at(la, lo)));

    // 停著的車子在哪一條路線的哪一點（路面高度跟路線一樣，車子才會貼在線上）
    raw.forEach((s, i) => {
      if (s.type !== 'stay') return;
      const pos = s.car || s.at, cand = [];
      const prev = raw[i - 1], next = raw[i + 1];
      if (prev && prev.type === 'drive') cand.push({ path: prev.path, d: prev.path.total });
      if (next && next.type === 'drive') cand.push({ path: next.path, d: 0 });
      raw.forEach(x => { if (x.type === 'drive') cand.push({ path: x.path, d: x.path.total }, { path: x.path, d: 0 }); });
      s.carRef = cand.find(c => meters(pos, c.path.at(c.d)) < 40) || null;
    });
    const stayCarH = s => s.carRef ? s.carRef.path.hAt(s.carRef.d) : hf.at((s.car || s.at)[0], (s.car || s.at)[1]);
    // 停靠時車子隱藏：要走的時候，車子在下一段路線的起點出現（路邊剪過的路線起點可能跟停的位置差幾十公尺）
    raw.forEach((s, i) => {
      const next = raw[i + 1];
      if (s.type !== 'stay' || !s.stop || s.stop.hideCar === false || !next || next.type !== 'drive' || next.cam.anchor) return;
      const p0 = next.path.at(0), gap = meters(p0, s.car || s.at);
      if (gap > 2 && gap < 250) s.carOut = { p: p0, h: roadHeading(next.path, 15) ?? next.legHeading, path: next.path };
    });
    // 同一個地方連續停留（例如目的地：到達、過夜、第二天）：中間車子不要一下出現一下消失
    const hidesCar = x => x && x.type === 'stay' && x.stop && x.stop.hideCar !== false && x.dur >= 2.6;
    raw.forEach((s, i) => {
      if (!hidesCar(s)) return;
      const pos = s.car || s.at, same = x => hidesCar(x) && meters(x.car || x.at, pos) < 40;
      s.chainIn = same(raw[i - 1]); s.chainOut = same(raw[i + 1]);
    });

    // ---------- 鏡頭 ----------
    function driveView(s, d, u) {
      const c = s.cam;
      if (c.anchor) {
        const a = c.anchor;
        // 北方朝上（2D）時路線是橫的，拉遠一點才不會被右邊的面板蓋住
        return { lat: a.at[0], lon: a.at[1], h: hf.at(a.at[0], a.at[1]), heading: northUp ? 0 : lerp(a.from, a.to, u), pitch: a.pitch, range: northUp ? a.range * 1.18 : a.range };
      }
      const p = s.path.at(d);
      const heading = northUp ? 0 : c.fixedHeading != null ? c.fixedHeading : s.headAt(d);
      return { lat: p[0], lon: p[1], h: s.path.hAt(d), heading, pitch: s.pitchAt(d), range: s.rangeAt(d) };
    }
    const stayView = (s, u) => {
      const pos = s.car || s.at, onCar = meters(s.at, pos) < 40;
      return { lat: s.at[0], lon: s.at[1], h: onCar ? stayCarH(s) : hf.at(s.at[0], s.at[1]),
        heading: northUp ? 0 : lerp(s.orbit.from, s.orbit.to, u), pitch: s.orbit.pitch, range: northUp && s.orbit.range > 8000 ? s.orbit.range * 1.18 : s.orbit.range };
    };
    const endView = s => s.type === 'drive' ? driveView(s, s.path.total, 1) : stayView(s, 1);
    const startView = s => s.type === 'drive' ? driveView(s, 0, 0) : stayView(s, 0);

    // 依順序決定鏡頭方向：
    //  - 停留：從「上一段結束的方向」慢慢轉到「下一段開始的方向」，中間的轉場就不用大轉彎（不會暈）
    //  - cam.fixedHeading = 'prev' 的短程：沿用上一段的方向，整段不轉（掉頭、繞路口時鏡頭不跟著轉）
    raw.forEach((s, i) => {
      const prev = raw[i - 1], next = raw[i + 1];
      if (s.type === 'drive') {
        if (s.cam.fixedHeading === 'prev') s.cam.fixedHeading = prev ? endView(prev).heading : s.legHeading;
        headingTable(s, prev && !(prev.cam && prev.cam.anchor) ? endView(prev).heading : null);
        return;
      }
      const o = s.orbit;
      const nextHeading = () => {
        if (!next || next.type !== 'drive' || next.cam.anchor || o.toNext === false) return null;
        if (next.cam.fixedHeading === 'prev') return null;
        if (next.cam.fixedHeading != null) return next.cam.fixedHeading;
        return chaseHeading(next.path, 0, next.cam.span || Math.max(300, next.rangeAt(0) * 0.9));
      };
      if (o.from == null) {
        if (prev) o.from = endView(prev).heading;
        else { const nh = o.to != null ? o.to : nextHeading(); o.from = nh != null ? nh - (o.turn || 20) : 0; }
      }
      if (o.to == null) { const nh = nextHeading(); o.to = nh != null ? nh : o.from + (o.turn || 20); }
      const maxTurn = MAX_TURN * 0.9 * s.dur;   // 停留時也不轉太快
      o.to = o.from + Math.max(-maxTurn, Math.min(maxTurn, wrap(o.to - o.from)));
    });
    // 停著的車頭方向：沿用上一段開到這裡的方向，或下一段出發的方向
    const carEndHeading = s => s.type === 'drive' ? (roadHeading(s.path, s.path.total - 15) ?? s.legHeading) : s.carHeadingR;
    raw.forEach((s, i) => {
      if (s.type !== 'stay') return;
      const pos = s.car || s.at, prev = raw[i - 1], next = raw[i + 1];
      if (s.carHeading != null) s.carHeadingR = s.carHeading;
      else if (prev && prev.type === 'drive' && meters(pos, prev.path.at(prev.path.total)) < 200) s.carHeadingR = carEndHeading(prev);
      else if (next && next.type === 'drive' && meters(pos, next.path.at(0)) < 200) s.carHeadingR = roadHeading(next.path, 15) ?? next.legHeading;
      else s.carHeadingR = prev ? (carEndHeading(prev) ?? 0) : 0;
    });

    // 轉場：依角度變化、高度變化與距離決定秒數；距離遠就先拉高再降下（像 Google 地球）
    const segs = [];
    raw.forEach((s, i) => {
      if (i > 0) {
        const p = raw[i - 1], a = endView(p), b = startView(s);
        const D = meters([a.lat, a.lon], [b.lat, b.lon]), rr = Math.max(a.range, b.range);
        const turn = Math.abs(wrap(b.heading - a.heading));
        const auto = Math.max(1 + turn / 40 + Math.abs(Math.log(b.range / a.range)) * 0.75 + 0.7 * Math.log(1 + D / rr) + Math.abs(b.pitch - a.pitch) / 30,
          turn / (MAX_TURN * 0.66));   // 平滑轉場的最大轉速約是平均的 1.5 倍
        // 拉高、降低很多的轉場（例如到高空快轉）可以久一點，畫面才不會晃太快
        const cap = 6 + Math.min(3, Math.abs(Math.log(b.range / a.range)));
        segs.push({ type: 'fly', dur: s.flyIn != null ? s.flyIn : Math.max(1, Math.min(cap, auto)), prev: p, next: s,
          clock: [p.clock[1], p.clock[1]], bat: [p.bat[1], p.bat[1]], km: [p.km[1], p.km[1]],
          night: [p.night[1], s.night[0]], state: p.state, leg: p.leg != null ? p.leg : s.leg, chapter: null, ff: p.ff && s.ff ? s.ff : null });
      }
      segs.push(s);
    });
    let T = 0; segs.forEach(s => { s.t0 = T; T += s.dur; s.t1 = T; });
    const duration = T;
    const absCues = cues.map(c => ({ ...c, at: raw[c.seg].t0 + c.u * raw[c.seg].dur, show: c.show || 5 })).sort((a, b) => a.at - b.at);
    const chapters = raw.filter(s => s.chapter).map(s => ({ t: s.t0, label: s.chapter }));

    // 停靠：車子淡出、資訊卡彈出、走路的人（時間點單位是秒；停留太短就不做，車子一直顯示）
    //   stop.walkIn / walkOut：一個人或好幾個人 { who: 'dad' | 'mom' | 'son' | 'daughter', to / from: [lat, lon] }
    //   下車：大家先走向地點（每人錯開 0.3 秒、走 1.4 秒），車子才淡出、資訊卡才出來；
    //   上車：卡片收起、車子先出現，大家再走回車子，碰到車子就消失（上車），然後開走。
    //   hideCar === false（接小孩、出門）：車子一直在，小孩走過來上車
    const WALK = 1.4, GAP = 0.3;
    const listOf = w => (Array.isArray(w) ? w : w ? [w] : []).filter(x => x && (x.to || x.from));
    function stopFx(s, u) {
      const st = s.stop, D = s.dur, t = u * D, pos = s.car || s.at, outPos = s.carOut ? s.carOut.p : pos;
      const fx = { alpha: 1, card: null, walker: null };
      if (!st || D < 2.6) return fx;
      const h = stayCarH(s), hide = st.hideCar !== false;
      const ins = s.chainIn ? [] : listOf(st.walkIn), outs = s.chainOut ? [] : listOf(st.walkOut);
      const inEnd = ins.length ? 0.15 + GAP * (ins.length - 1) + WALK : 0;
      const outStart = outs.length ? D - 0.25 - GAP * (outs.length - 1) - WALK : D;
      const room = outStart - inEnd > (hide ? 2.4 : 0.6);   // 時間不夠就不畫人
      const tA = room && ins.length ? 0.15 + 0.6 : 0.1;                         // 車子開始淡出
      const tB = room && outs.length ? outStart - 0.65 : D - 0.7;               // 車子開始出現
      if (hide) fx.alpha = Math.max(s.chainIn ? 0 : 1 - ramp(t, tA, tA + 0.5), s.chainOut ? 0 : ramp(t, tB, tB + 0.5));
      if (st.title) {
        const c0 = hide ? tA + 0.35 : 0.75, c1 = hide ? tB - 0.35 : (room && outs.length ? outStart - 0.3 : D - 1.0);
        const kin = ramp(t, c0, c0 + 0.45), kout = ramp(t, c1 - 0.3, c1);
        const k = (kin < 1 ? easeOutBack(kin) : 1) * (1 - smooth(kout));
        if (kin > 0 && k > 0.01) fx.card = { p: pos, h, icon: st.icon, title: st.title, line: st.line, detail: st.detail, note: st.note, tone: st.tone, key: st.key, k, lift: hide ? 0 : 74 };   // 車子看得到時，卡片放高一點，不蓋住車子
      }
      const ws = [];
      if (room) {
        ins.forEach((w, i) => { const t0 = 0.15 + GAP * i; if (t >= t0 && t <= t0 + WALK) ws.push({ from: pos, to: w.to, h, f: ramp(t, t0, t0 + WALK), who: w.who, fromCar: true }); });
        outs.forEach((w, i) => { const t0 = outStart + GAP * i; if (t >= t0 && t <= t0 + WALK) ws.push({ from: w.from, to: outPos, h, f: ramp(t, t0, t0 + WALK), who: w.who, toCar: true }); });
      }
      fx.walker = ws.length ? ws : null;
      return fx;
    }
    function carOf(s, u) {
      if (s.type === 'drive') { const d = s.distAt(u); return { p: s.path.at(d), h: roadHeading(s.path, d) ?? s.legHeading, z: s.path.hAt(d), fx: null }; }
      if (s.type === 'stay') {
        const fx = stopFx(s, u);
        // 車子隱藏的停靠：後半段改停在下一段路線的起點（出現時就在那裡）
        if (s.carOut && s.dur >= 2.6 && s.stop && s.stop.hideCar !== false && u > 0.5) return { p: s.carOut.p, h: s.carOut.h, z: s.carOut.path.hAt(0), fx };
        return { p: s.car || s.at, h: s.carHeadingR, z: stayCarH(s), fx };
      }
      // 轉場：車子停在上一段的終點（如果上一段結束時車子是隱藏的，就繼續隱藏）
      const c = carOf(s.prev, 1);
      return Object.assign(c, { fx: { alpha: c.fx ? c.fx.alpha : 1, card: null, walker: null } });
    }
    function viewOf(s, u) {
      if (s.type === 'drive') return driveView(s, s.distAt(u), u);
      if (s.type === 'stay') return stayView(s, u);
      const a = endView(s.prev), b = startView(s.next), v = smooth(u);
      const D = meters([a.lat, a.lon], [b.lat, b.lon]);
      const base = Math.exp(lerp(Math.log(a.range), Math.log(b.range), v));
      // 位置在「高的時候」移動：往下降就先移過去再降，往上升就先升再移（地面才不會從眼前快速掠過）
      const k = Math.abs(Math.log(b.range / a.range)) > 0.7 ? (b.range < a.range ? 1 - (1 - u) ** 3 : u ** 3) : v;
      return { lat: lerp(a.lat, b.lat, k), lon: lerp(a.lon, b.lon, k), h: lerp(a.h, b.h, v),
        heading: angleLerpDeg(a.heading, b.heading, lerp(u, v, 0.5)), pitch: lerp(a.pitch, b.pitch, v),   // 方向用比較平均的速度轉（最快的那一刻不會太快）
        range: Math.max(base, 1.1 * D * Math.sin(Math.PI * v)) };
    }
    function stateAt(t) {
      t = Math.max(0, Math.min(duration, t));
      let s = segs[segs.length - 1];
      for (const x of segs) if (t < x.t1) { s = x; break; }
      const u = s.dur ? (t - s.t0) / s.dur : 1;
      let g = u, ff = s.ff || null;
      if (s.type === 'drive') {
        const d = s.distAt(u); g = d / s.path.total;
        if (ff && !s.cam.anchor && s.rampAt(d) < 0.35) ff = null;   // 只在鏡頭拉高的中段顯示「快轉」
      }
      const cue = absCues.filter(c => c.at <= t && t < c.at + c.show).pop() || null;
      let chapter = raw[0].chapter;
      for (const r of raw) if (r.t0 <= t && r.chapter) chapter = r.chapter;
      const car = carOf(s, u), fx = car.fx || { alpha: 1, card: null, walker: null };
      return {
        t, u, seg: s, type: s.type, chapter, ff: ff === true ? '⏩ 快轉' : ff,
        clock: lerp(s.clock[0], s.clock[1], g), bat: lerp(s.bat[0], s.bat[1], g), km: lerp(s.km[0], s.km[1], g),
        night: lerp(s.night[0], s.night[1], u), state: s.state, leg: s.leg,
        car: car.p, carHeading: car.h, carH: car.z, carAlpha: fx.alpha, card: fx.card, walker: fx.walker,
        view: viewOf(s, u), cue,
      };
    }

    let t = 0, playing = false, speed = 1, last = 0, raf = 0, lastState = null, buffering = false, hold = 0;
    function renderAt(time, quiet) {
      const st = stateAt(time);
      sim.view(st.view);
      sim.setCar(st.car, st.carHeading, st.carH, st.type === 'drive', st.carAlpha);
      if (sim.setStop) sim.setStop(st.card);
      if (sim.setWalker) sim.setWalker(st.walker);
      if (sim.hidePin) sim.hidePin(st.card ? st.card.key : null);   // 資訊卡出來時，同一個地點的圖釘先收起來
      sim.setNight(st.night);
      if (st.leg != null) sim.setActiveLeg(st.leg);
      lastState = st;
      if (onState && !quiet) onState(st, api);
      return st;
    }
    function loop() {
      if (!playing) { raf = 0; return; }
      // 用真正經過的時間（不用 requestAnimationFrame 給的時間戳）：放在顧問頁的 iframe 裡時，瀏覽器有時一秒呼叫上萬次，
      // 時間戳又不可靠，會一下子跳到結尾。間隔不到 8 ms 的呼叫直接略過
      const now = performance.now();
      if (now - last < 8) { raf = requestAnimationFrame(loop); return; }
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      // 緩衝：3D 圖塊還在大量下載時先停住（最多 2.5 秒），等街景清楚再播；下載量不多時放慢
      const pend = adaptive && sim.pendingTiles ? sim.pendingTiles() : 0;
      let lf = 1;
      if (pend > 24 && hold < 2.5) { lf = 0; hold += dt; }
      else if (pend > 10) lf = 0.35;
      else hold = 0;
      buffering = lf < 1;
      const t0 = t; t = Math.min(duration, t + dt * speed * lf);
      if (onCue && speed === 1) absCues.forEach(c => { if (c.at > t0 && c.at <= t) onCue(c, api); });
      renderAt(t);
      if (t >= duration) { playing = false; raf = 0; if (onEnd) onEnd(api); return; }
      raf = requestAnimationFrame(loop);
    }

    // 預先載入的步伐：沿時間軸走，鏡頭每移動約 0.3 個畫面、轉 10°、拉近拉遠 22%（或最多 4 秒）就停一次
    function planSteps({ move = 0.3, turn = 10, zoom = 1.22, pitch = 6, minDt = 0.3, maxDt = 4 } = {}) {
      const times = [0];
      let tp = 0, vp = stateAt(0).view;
      for (let x = 0.05; x < duration; x += 0.05) {
        const v = stateAt(x).view, dt = x - tp;
        const big = meters([vp.lat, vp.lon], [v.lat, v.lon]) / Math.min(vp.range, v.range) > move
          || Math.abs(wrap(v.heading - vp.heading)) > turn || Math.max(v.range / vp.range, vp.range / v.range) > zoom
          || Math.abs(v.pitch - vp.pitch) > pitch;
        if ((big && dt >= minDt) || dt >= maxDt) { times.push(x); tp = x; vp = v; }
      }
      times.push(duration);
      return times;
    }
    // 量路面高度：車子附近一段路（鏡頭越低量得越密、越準）。圖塊沒載完時量的，可信度打折
    function measure(st, loaded) {
      const v = st.view, q = loaded ? v.range : v.range * 4, s = st.seg;
      hf.add(v.lat, v.lon, sim.sampleHeight(v.lat, v.lon));
      const along = (path, dc, W) => {
        const root = path.root || path, off = path.off || 0;
        if (!root.addSample) return;
        const c = off + dc, sp = Math.max(root.ds, v.range / 50);
        for (let x = Math.max(0, c - W); x <= Math.min(root.total, c + W); x += sp) {
          if (!root.wants(x, q)) continue;
          const p = root.at(x); root.addSample(x, sim.sampleHeight(p[0], p[1]), q);
        }
      };
      const W = Math.min(2500, Math.max(150, 0.5 * v.range));
      if (s.type === 'drive') {
        if (s.cam.anchor) along(s.path, s.path.total / 2, s.path.total / 2 + 1);   // 高空固定鏡頭：整段都在畫面裡
        else along(s.path, s.distAt(st.u), W);
      } else if (s.type === 'stay') { if (s.carRef) along(s.carRef.path, s.carRef.d, W); }
      else if (s.prev.type === 'drive') along(s.prev.path, s.prev.path.total, W);
      else if (s.prev.carRef) along(s.prev.carRef.path, s.prev.carRef.d, W);
    }

    const api = {
      duration, chapters, cues: absCues, stateAt, renderAt, heights: hf, paths, planSteps,
      get time() { return t; }, get playing() { return playing; }, get speed() { return speed; }, get buffering() { return buffering; },
      play() {
        if (t >= duration) t = 0;
        if (!playing) { playing = true; last = performance.now(); hold = 0; raf = requestAnimationFrame(loop); }
        // 從某一句台詞的中間開始播，也把那一句說出來
        if (onCue && speed === 1) { const c = absCues.find(c => c.at <= t && t < c.at + 0.6); if (c) onCue(c, api); }
      },
      pause() { playing = false; if (raf) cancelAnimationFrame(raf); raf = 0; },
      seek(time) { t = Math.max(0, Math.min(duration, time)); renderAt(t); },
      setSpeed(s) { speed = s; },
      // 照真正播放時的鏡頭，一步一步走完整段時間軸：每一步等 3D 圖塊載完，順便量路面高度。
      // 走完再把路面高度整理好（去掉屋頂等離群值、平滑），重畫路線 → 車子和路線用同一份高度。
      async preload(onProgress, o = {}) {
        const maxMs = o.maxMs || 3500, times = planSteps(o), t0 = performance.now();
        let timeouts = 0;
        for (let i = 0; i < times.length; i++) {
          const st = renderAt(times[i], true);
          const ok = await sim.waitTiles(maxMs);
          if (!ok) timeouts++;
          measure(st, ok);
          if (onProgress) onProgress((i + 1) / times.length);
        }
        paths.forEach(p => p.finalize && p.finalize());
        if (sim.refreshLegs) sim.refreshLegs();
        renderAt(0);
        return { steps: times.length, timeouts, ms: Math.round(performance.now() - t0) };
      },
      // 不預先載入（測試用）：只把路面高度整理好
      finalizeHeights() { paths.forEach(p => p.finalize && p.finalize()); if (sim.refreshLegs) sim.refreshLegs(); },
      get state() { return lastState; },
    };
    return api;
  }

  window.SimTimeline = { create, chaseHeading };
})();
