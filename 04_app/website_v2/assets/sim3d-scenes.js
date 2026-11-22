/* sim3d-scenes.js — 阿電 行車模擬的三個情境：你的一天、你的一週、三天兩夜（只用在 website_v2）
 *
 * 每個情境：查路線與充電站、在地圖放地點圖釘，回傳時間軸片段（raw）、阿電的台詞（cues）
 * 與小地圖要標的地點（places）。數字全部由程式計算（阿電的「大腦與算盤」：LLM 不產生數字）。
 *
 *   const sc = await SimScenes.build('day' | 'week' | 'trip', ctx);
 *   ctx = { sim, api, HOME, WORK, DEST, MODE: 'home' | 'work' | 'public', CAM, near, nearWork, nearHome, kids }
 *
 * 陳家：陳先生（dad）、陳太太（mom）、兒子（son）、女兒（daughter）。kids = 用車方式是「接送家人小孩」：
 * 不另外問，阿電用住家附近最近的國小推估，陳先生下班接一個小孩（另一個由太太接；早上不送）。
 * 生活地點（國小、百貨、公園）從家附近的充電站名稱找（TDX 公開資料），找不到就省略那一站。
 * 充電站：只用 bZ4X 能充的（DC 要 CCS1、AC 要 J1772；gateway 已經過濾接頭），另外用名稱排除特斯拉、品牌專用站。
 * 停靠：車子停在路邊（路線終點，一定在路上，不開進建築物），家人下車走過去，車子才淡出、資訊卡說明「這是哪裡、在做什麼」。
 */
(function () {
  'use strict';
  // 與 advisor.html 相同的假設與係數（來源見 advisor.html 的註腳）
  const K = {
    EV_KWH_PER_KM: 0.15, BATTERY_KWH: 74.7, RANGE_KM: 520, AC_KW: 6.6,
    GAS_L_PER_KM: 0.08, GAS_NT_PER_L: 30, HOME_NT_PER_KWH: 3.5, PUBLIC_NT_PER_KWH: 8,
    GRID_CO2: 0.467, GAS_CO2: 2.2631, TREE_KG: 10, WORKDAYS: 260,
    // 定期保養每 10 萬公里：油車約 4.3 萬、bZ4X 約 1.5 萬（U-CAR、8891）
    MAINT_PER_10K: (43000 - 15000) / 10,
    // 模擬用的假設（11/10）：夏天開冷氣約 1 kW（每小時約 1 度電）；上下班尖峰塞車，行車時間 ×1.5（OSRM 是不塞車的時間）
    COOL_KW: 1.0, RUSH: 1.5,
  };
  K.PCT_PER_KM = 100 / K.RANGE_KM;
  K.AC_PCT_PER_H = K.AC_KW / K.BATTERY_KWH * 100;          // 慢充每小時充進幾 %
  K.DC_PCT_PER_MIN = 2;                                   // 快充約 30 分鐘 20→80%
  K.CO2_PER_KM = K.GAS_L_PER_KM * K.GAS_CO2 - K.EV_KWH_PER_KM * K.GRID_CO2;
  K.FUEL_NT_PER_KM = K.GAS_L_PER_KM * K.GAS_NT_PER_L;      // 油車每公里油錢
  const savePerKm = price => K.FUEL_NT_PER_KM - K.EV_KWH_PER_KM * price;
  // 用掉的電（%）：行駛每公里 0.15 度＋冷氣每小時 1 度（塞車時馬達不空轉，主要是冷氣在用電）
  const usePct = (km, min) => (km * K.EV_KWH_PER_KM + K.COOL_KW * min / 60) / K.BATTERY_KWH * 100;

  const DAYS = ['週一', '週二', '週三', '週四', '週五', '週六', '週日'];
  const LEAVE = 7 * 60 + 40, BACK = 18 * 60, DAY = 24 * 60;
  const hhmm = m => `${String(Math.floor(m / 60) % 24).padStart(2, '0')}:${String(Math.floor(m) % 60).padStart(2, '0')}`;
  const r1 = x => Math.round(x * 10) / 10;
  const pctTxt = x => x < 10 ? r1(x) : Math.round(x);
  const distTxt = km => km < 1 ? `${Math.round(km * 100) * 10} 公尺` : `${km.toFixed(1)} 公里`;
  const P = o => [o.lat, o.lon];
  const last = a => a[a.length - 1];
  const headingDeg = (a, b) => Sim3D.deg(Sim3D.bearing(a, b));
  const gasL = k => r1(k * K.GAS_L_PER_KM);
  // 台詞：顯示時間依字數（台灣國語約每秒 4 個字），4.5–9 秒
  const cue = (seg, u, text, show) => ({ seg, u, text, show: show || Math.max(4.5, Math.min(9, text.length / 4.2)) });
  const gasLine = km => `同一段路開油車，要燒掉大約 ${gasL(km)} 公升汽油。`;
  const maintLine = `保養也比油車省，每一萬公里大約少花 NT$${K.MAINT_PER_10K.toLocaleString()}。`;

  // ---------- 充電站：只用 bZ4X 能充的 ----------
  // gateway 已經只回傳有 CCS1（直流）或 J1772（交流）接頭的站；這裡再用名稱排除特斯拉、超級充電站、品牌專用站
  const RESTRICTED = /特斯拉|Tesla|超級充電|Supercharger|專用|專屬|保時捷|Porsche|BMW|賓士|Mercedes|Benz|奧迪|Audi|Volvo|Polestar|Lexus|凌志|Hyundai|現代汽車|起亞|Kia|福特|Ford|日產|Nissan|三菱汽車|Skoda|福斯|Volkswagen|納智捷|Luxgen/i;
  const usable = s => (s.bz4x_dc > 0 || s.bz4x_ac > 0) && !RESTRICTED.test(s.name || '');
  function onlyUsable(res, counter) {
    if (!res || !res.stations) return res;
    const ok = res.stations.filter(usable);
    counter.excluded += res.stations.length - ok.length;
    return { ...res, stations: ok, total: Math.max(0, (res.total || 0) - (res.stations.length - ok.length)) };
  }
  // 充電站資訊卡的第三行：bZ4X 能用的接頭與數量、收費（TDX 沒有提供功率）
  const plugs = s => [s.bz4x_dc ? `CCS1 快充 ×${s.bz4x_dc}` : '', s.bz4x_ac ? `J1772 慢充 ×${s.bz4x_ac}` : ''].filter(Boolean).join('、');
  const rate = s => { const r = (s.charging_rate || '').split('/').pop().trim(); return r && r.length <= 14 ? `｜${r}` : ''; };
  const chargeDetail = s => `bZ4X 可用：${plugs(s) || '規格未提供'}${rate(s)}`;

  // 路線開到地點（停車場、車道）前的最後一小段剪掉：車子停在離地點約 35 公尺的路邊，不開進建築物。
  // atEnd = false 剪的是開頭（從地點出發時，從路邊開始開）
  function trimNear(coords, place, m = 35, atEnd = true) {
    const c = atEnd ? coords.slice().reverse() : coords.slice(), d = p => Sim3D.meters(p, place);
    if (c.length < 3 || d(c[0]) >= m) return coords;
    let i = 1, cutLen = 0;
    while (i < c.length && d(c[i]) < m) { cutLen += Sim3D.meters(c[i - 1], c[i]); i++; }
    if (i >= c.length - 1 || cutLen > 250) return coords;   // 整段都在附近、或要剪太多：不剪
    const a = c[i - 1], b = c[i], da = d(a), db = d(b), f = Math.max(0, Math.min(1, (m - da) / ((db - da) || 1)));
    const kept = [[a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], ...c.slice(i)];
    return atEnd ? kept.reverse() : kept;
  }
  // 路線：去掉 3 公尺（長途 8 公尺）以內的鋸齒，轉彎都保留；路面高度之後沿路量。
  // trim：哪些地點（學校、百貨、公園、公司、充電站）要在路邊停，不開到門口的車道
  async function routes(api, pairs, trim = new Set()) {
    const out = await Promise.all(pairs.map(([a, b]) => api(`api/route?src=${a[0]},${a[1]}&dst=${b[0]},${b[1]}&geometry=2`)));
    out.forEach((r, i) => {
      const [a, b] = pairs[i];
      if (trim.has(b)) r.coords = trimNear(r.coords, b, 35, true);
      if (trim.has(a)) r.coords = trimNear(r.coords, a, 35, false);
      r.coords = Sim3D.simplify(r.coords, r.km > 60 ? 8 : 3);
      r.path = Sim3D.makePath(r.coords); r.kind = pairs[i][2] || 'go';
    });
    return out;
  }
  const legsOf = R => R.map(r => ({ path: r.path, coords: r.coords, kind: r.kind }));
  const stay = (at, orbit, extra) => Object.assign({ type: 'stay', at, orbit }, extra);
  const drive = (path, leg, cam, dur, extra) => Object.assign({ type: 'drive', path, leg, cam, dur }, extra);
  const pickSlow = list => list.find(s => s.bz4x_ac > 0) || list[0];
  const pickFast = list => list.find(s => s.fast) || list[0];

  // ---------- 生活地點：從家附近的充電站名稱找國小、百貨、公園（都是公開地點） ----------
  const MALL = /百貨|遠百|家樂福|好市多|Costco|大潤發|愛買|購物|商場|IKEA|環球|SOGO|三越|Outlet|量販|Mall/i;
  const placeName = n => n.replace(/^(新北市?|臺北市?|台北市?|桃園市?|台中市?|臺中市?|台南市?|臺南市?|高雄市?)/, '')
    .replace(/(地下|立體|平面)?停車場.*$/, '').replace(/(充電站|站)$/, '').trim() || n;
  function lifePlaces(ctx) {
    const st = ctx.nearHome.stations;
    const tag = s => s && { ...s, label: placeName(s.name) };
    return {
      school: ctx.kids ? tag(st.find(s => /國小|小學/.test(s.name))) : null,
      mall: tag(st.find(s => s.fast && MALL.test(s.name)) || st.find(s => MALL.test(s.name))),
      park: tag(st.find(s => /公園/.test(s.name))),
    };
  }

  // 11/16：充電站圖釘的字——TDX 沒有 kW，只寫 bZ4X 能用的接頭（DC 快充 CCS1／AC 慢充 J1772）、數量、費率
  function evRate(st) {
    const t = st.charging_rate || '', seg = t.split(/[,，;；]/).find(x => (st.fast ? /DC|直流|快充/i : /AC|交流|慢充/i).test(x)) || t;
    const m = seg.match(/(\d+(?:\.\d+)?)\s*元/);
    return m ? `${m[1]} 元/度` : /免費/.test(t) ? '免費' : '';
  }
  const evLabel = st => st.fast ? `快充 DC・CCS1 ×${st.bz4x_dc || 1}` : `慢充 AC・J1772 ×${st.bz4x_ac || 1}`;
  const evSub = (st, dist) => [evRate(st), dist && st.distance_km != null ? '離家 ' + distTxt(st.distance_km) : ''].filter(Boolean).join('・');
  // 附近其他充電站（小圖釘）
  function pins(sim, places, list, chosen, n = 9) {
    return Promise.all(list.filter(s => !chosen || s.id !== chosen.id).slice(0, n).map(s => {
      places.push({ lat: s.lat, lon: s.lon, kind: 'alt', fast: s.fast, label: s.name });
      return sim.addPin({ lat: s.lat, lon: s.lon, fast: s.fast, label: evLabel(s), sub: [evRate(s), distTxt(s.distance_km)].filter(Boolean).join('・') });
    }));
  }
  // 地點圖釘（像 Google 地圖；小地圖也標一樣的地點）。key：停靠時資訊卡出來，同一個地點的圖釘先收起來
  async function place(sim, places, p) {
    places.push({ lat: p.lat, lon: p.lon, kind: p.kind, label: p.label, fast: p.fast, icon: p.icon });
    await sim.addPlace({ lat: p.lat, lon: p.lon, icon: p.icon, label: p.label, tone: p.tone, key: p.key || p.kind, side: p.side });
  }
  // 地點在參考點（家、公司）西邊：名字放左邊；東邊：放右邊（高空看的時候圖釘才不會互相蓋住）
  const sideOf = (p, ref) => p.lon < ref.lon - 0.0003 ? 'left' : undefined;

  // ---------- 鏡頭與節奏 ----------
  // 市區：起點、終點低空跟車；中段拉高（最多 3.2 公里）。畫面每秒移動約 12%（ff = 快轉：中段更快、更高）
  // 2 公里內的短程：鏡頭沿用上一段的方向、不轉（巷子裡掉頭、繞路口時才不會暈）
  const cityCam = (ctx, km, ff) => Object.assign({ range: ctx.CAM.range, rangeMax: Math.max(ctx.CAM.range * 1.6, Math.min(3200, km * 220)) * (ff ? 1.3 : 1),
    ramp: 1500, pitch: ctx.CAM.pitch, pitchMax: ctx.CAM.pitchMax || -56 }, km < 2 ? { fixedHeading: 'prev' } : {});
  const cityPace = (km, ff) => ff ? { sigma: 0.12, sigmaMax: 0.32, maxDur: 24 } : km < 2 ? { sigma: 0.12, minDur: 6, maxDur: 10 } : { sigma: 0.12, maxDur: 42 };

  // 時間軸紀錄：時鐘、電量、里程一路累加，片段之間不會接錯
  function tracker(ctx, b0, clock0) {
    const t = { b: b0, clock: clock0, km: 0, used: 0, raw: [], cues: [] };
    t.add = s => { t.raw.push(s); return t.raw.length - 1; };
    t.cue = (i, u, text, show) => t.cues.push(cue(i, u, text, show));
    t.drive = (r, leg, o = {}) => {
      const min = r.minutes * (o.rush === false ? 1 : K.RUSH), used = usePct(r.km, min);
      const s = drive(r.path, leg, o.cam || cityCam(ctx, r.km, o.ff), o.dur != null ? o.dur : null, {
        pace: o.pace || cityPace(r.km, o.ff), ff: o.ff || null, clock: [t.clock, t.clock + min], bat: [t.b, t.b - used],
        km: [t.km, t.km + r.km], night: o.night || [0, 0], state: o.state || '行駛中', chapter: o.chapter || null, flyIn: o.flyIn });
      t.clock += min; t.b -= used; t.km += r.km; t.used += used; t.lastUsed = used;
      return t.add(s);
    };
    // 停留：min = 經過幾分鐘；toBat = 停完的電量（充電）；useKm = 停留期間在附近開的公里數；stop = 停靠資訊卡
    t.stay = (at, o) => {
      const b0 = t.b;
      if (o.toBat != null) t.b = Math.max(t.b, o.toBat);
      if (o.useKm) { const u = usePct(o.useKm, o.useMin || 0); t.b -= u; t.used += u; }
      const s = stay(at, o.orbit, { dur: o.dur, clock: [t.clock, t.clock + (o.min || 0)], bat: [b0, t.b], km: [t.km, t.km + (o.useKm || 0)],
        night: o.night || [0, 0], state: o.state, chapter: o.chapter || null, leg: o.leg, car: o.car, carHeading: o.carHeading, flyIn: o.flyIn, ff: o.ff || null, stop: o.stop });
      t.clock += o.min || 0; t.km += o.useKm || 0;
      return t.add(s);
    };
    return t;
  }
  // ---------- 陳家的人 ----------
  const FAMILY = ['dad', 'mom', 'son', 'daughter'];
  const walk = (who, key, p) => (Array.isArray(who) ? who : [who]).map(w => ({ who: w, [key]: p }));
  // 停靠資訊卡的文字
  const officeStop = (office, b0, to, work) => ({ icon: '⚡', title: office.label, line: `公司旁的充電站・上班時插著慢充 ${Math.round(b0)}% → ${Math.round(to)}%`,
    detail: chargeDetail(office), tone: 'charge', key: 'office', walkIn: work && walk('dad', 'to', work), walkOut: work && walk('dad', 'from', work) });
  const parkStop = (WORK, work) => ({ icon: '🏢', title: `公司（${WORK.name}）`, line: '上班中・車停在公司停車場', key: 'work',
    walkIn: walk('dad', 'to', work), walkOut: walk('dad', 'from', work) });
  // 接小孩：車子不消失；兒子從學校走過來，碰到車子就上車，然後開走
  const schoolStop = (school, S) => ({ icon: '🏫', title: school.label, line: '下班順路接小孩', note: '學校為阿電依住家推估', key: 'school', hideCar: false,
    walkOut: walk('son', 'from', S) });

  // ======================= 你的一天 =======================
  async function day(ctx) {
    const { sim, MODE, HOME, WORK, near } = ctx;
    const places = [], life = lifePlaces(ctx);
    const office = pickSlow(ctx.nearWork.stations), fast = life.mall || pickFast(ctx.nearHome.stations), school = life.school;
    office.label = office.label || placeName(office.name); fast.label = fast.label || placeName(fast.name);
    const H = P(HOME), O = MODE === 'work' ? P(office) : P(WORK), S = school ? P(school) : null, F = P(fast), Wk = P(WORK);
    const pairs = [[H, O, 'go']];
    if (S) pairs.push([O, S, 'back']);
    if (MODE === 'public') pairs.push([S || O, F, 'back'], [F, H, 'back']); else pairs.push([S || O, H, 'back']);
    const R = await routes(ctx.api, pairs, new Set([O, S, F].filter(Boolean)));
    sim.setLegs(legsOf(R));
    const START = R[0].coords[0];
    await place(sim, places, { ...HOME, kind: 'home', icon: '🏠', label: MODE === 'home' ? '家（有充電樁）' : '家', tone: 'home' });
    await place(sim, places, { ...WORK, kind: 'work', icon: '🏢', label: '公司' });
    if (MODE === 'work') {
      await pins(sim, places, ctx.nearWork.stations, office);
      await place(sim, places, { lat: office.lat, lon: office.lon, kind: 'charger', icon: '⚡', label: office.label, tone: 'charge', key: 'office', side: sideOf(office, WORK) || 'left' });
    } else if (MODE === 'public') {
      await pins(sim, places, ctx.nearHome.stations, fast);
      await place(sim, places, { lat: fast.lat, lon: fast.lon, kind: life.mall ? 'mall' : 'charger', icon: life.mall ? '🛍️' : '⚡', label: `${fast.label}・快充`, tone: 'charge', key: 'fast', side: sideOf(fast, HOME) });
    } else places.push({ lat: START[0], lon: START[1], kind: 'charger', label: '家裡的充電樁' });
    if (school) await place(sim, places, { lat: school.lat, lon: school.lon, kind: 'school', icon: '🏫', label: `${school.label}（推估）`, key: 'school', side: sideOf(school, HOME) });

    const t = tracker(ctx, MODE === 'home' ? 100 : MODE === 'work' ? 62 : 32, LEAVE);
    const i0 = t.stay(START, { dur: 5.5, orbit: { range: 1200 * near, pitch: -42 }, state: '停在家', chapter: '出門', leg: 0,
      stop: { hideCar: false, walkOut: walk('dad', 'from', H) } });
    t.cue(i0, 0.08, `早上 ${hhmm(LEAVE)}，你從${HOME.name}出發去上班` + (MODE === 'home' ? '，電是滿的。' : MODE === 'public' ? `。這週還沒充電，電剩 ${t.b}%。` : '。'));
    const iGo = t.drive(R[0], 0, { chapter: '上班' });
    t.cue(iGo, 0.05, '塞車的時候，電動車的馬達不會空轉，主要是冷氣在用電。');
    t.cue(iGo, 0.36, `到公司 ${r1(R[0].km)} 公里，塞車、開冷氣，用掉 ${pctTxt(t.lastUsed)}% 的電。`);
    t.cue(iGo, 0.62, gasLine(R[0].km));
    t.cue(iGo, 0.86, maintLine);
    const atWork = last(R[0].coords);
    if (MODE === 'work') {
      const b0 = t.b, to = Math.min(100, t.b + (BACK - t.clock) / 60 * K.AC_PCT_PER_H);
      const i = t.stay(atWork, { dur: 17, min: BACK - t.clock, toBat: to, orbit: { range: 430 * near, pitch: -30 }, state: '充電中', chapter: '在公司充電', leg: 0, night: [0, 0.15],
        stop: officeStop(office, b0, to, Wk) });
      t.cue(i, 0.02, `公司附近有 ${ctx.nearWork.total} 個 bZ4X 能用的充電站。阿電選了最近的慢充，上班的時候插著。`, 7);
      t.cue(i, 0.45, '插上充電槍只要幾秒鐘，跟幫手機充電一樣。');
      t.cue(i, 0.72, `下班的時候，電已經充到 ${Math.round(to)}%。`);
    } else {
      const i = t.stay(atWork, { dur: 8, min: BACK - t.clock, orbit: { range: 600 * near, pitch: -34 }, state: '停車中', chapter: '上班時間', leg: 0, night: [0, 0.15],
        stop: parkStop(WORK, Wk) });
      t.cue(i, 0.05, '白天車子停在公司，什麼都不用管。');
    }
    // 下班：同一條路的回程用「快轉」（中段拉高、加速），不重複看一次
    const iBack = t.drive(R[1], 1, { ff: '⏩ 下班路上', chapter: '下班', night: [0.3, 0.5] });
    t.cue(iBack, 0.04, '下班囉，回程阿電幫你快轉。');
    let li = 2;
    if (S) {
      const i = t.stay(last(R[1].coords), { dur: 7, min: 10, orbit: { range: 520 * near, pitch: -36 }, state: '接小孩', chapter: '接小孩', leg: 1, night: [0.5, 0.55],
        stop: schoolStop(school, S) });
      t.cue(i, 0.05, `順路到${school.label}接兒子。太太會去接女兒。`);
    }
    const kid = S ? ['dad', 'son'] : 'dad';
    if (MODE === 'public') {
      if (S) {
        const i = t.drive(R[li], li, { night: [0.55, 0.6] });
        t.cue(i, 0.1, `一起去${fast.label}吃晚餐，順便快充。`);
        li++;
      }
      const from = t.b, m = Math.max(5, (80 - from) / K.DC_PCT_PER_MIN), cost = Math.round((80 - from) / 100 * K.BATTERY_KWH * K.PUBLIC_NT_PER_KWH);
      const j = t.stay(last(R[li - 1].coords), { dur: 19, min: m, toBat: 80, orbit: { range: 600 * near, pitch: -55 }, state: '充電中', chapter: '快充', leg: li - 1, night: [0.6, 0.62],
        stop: { icon: life.mall ? '🛍️' : '⚡', title: fast.label, line: `吃晚餐的 ${Math.round(m)} 分鐘・快充 ${Math.round(from)}% → 80%`, detail: chargeDetail(fast), tone: 'charge', key: 'fast',
          walkIn: walk(kid, 'to', F), walkOut: walk(kid, 'from', F) } });
      t.cue(j, 0.06, `家附近有 ${ctx.nearHome.total} 個 bZ4X 能用的充電站。吃個晚餐的 ${Math.round(m)} 分鐘，電就從 ${Math.round(from)}% 充到 80%。`, 8);
      t.cue(j, 0.5, `這次快充大約 NT$${cost}。`); t.cue(j, 0.75, '一週充這一次就夠了。');
    }
    // 沒有接小孩、也不用去充電：下班那一段就直接到家
    const iHome = li < R.length ? t.drive(R[li], li, { chapter: '回家', night: [0.6, 0.66] }) : iBack;
    li = R.length - 1;
    const kmDay = t.km, used = t.used;
    const sumLine = `今天開了 ${r1(kmDay)} 公里，冷氣、塞車都算進去，一共用了 ${pctTxt(used)}% 的電。`;
    const co2Line = `一次加油站都沒去，少排了 ${r1(kmDay * K.CO2_PER_KM)} 公斤 CO₂。`;
    t.cue(iHome, iHome === iBack ? 0.55 : 0.15, sumLine, 7);
    const atHome = last(R[li].coords);
    if (MODE === 'home') {
      const morning = DAY + 7 * 60, bArr = t.b;
      const i = t.stay(atHome, { dur: 15, min: morning - t.clock, toBat: 100, orbit: { range: 650 * near, pitch: -34 }, state: '充電中', chapter: '在家充電', leg: li, night: [0.7, 0.88],
        stop: { icon: '🏠', title: '家裡的充電樁', line: `插上充電線・睡一覺 ${Math.round(bArr)}% → 100%`, tone: 'home', key: 'home', walkIn: walk(kid, 'to', H) } });
      t.cue(i, 0.1, '回家插上充電線，睡一覺，電就滿了。');
      t.cue(i, 0.45, `在家充電一度大約 ${K.HOME_NT_PER_KWH} 元，這一天的電費大約 NT$${Math.round(used / 100 * K.BATTERY_KWH * K.HOME_NT_PER_KWH)}。`, 7);
      const k = t.stay(atHome, { dur: 7, min: 10, orbit: { range: 900 * near, pitch: -38 }, state: '停在家', chapter: '隔天早上', leg: li, night: [0.88, 0], flyIn: 1 });
      t.cue(k, 0.1, co2Line, 6);
    } else {
      const i = t.stay(atHome, { dur: 9, min: 5, orbit: { range: 950 * near, pitch: -38 }, state: '停在家', chapter: '到家', leg: li, night: [0.66, 0.7],
        stop: { icon: '🏠', title: '家', line: `到家了・電還有 ${Math.round(t.b)}%`, tone: 'home', key: 'home', walkIn: walk(kid, 'to', H) } });
      t.cue(i, 0.2, co2Line, 7);
    }
    const price = MODE === 'home' ? K.HOME_NT_PER_KWH : K.PUBLIC_NT_PER_KWH;
    return { raw: t.raw, cues: t.cues, places, legs: legsOf(R), kmTotal: kmDay, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
      label: '今天', firstDay: 1, excluded: ctx.excluded,
      title: MODE === 'home' ? '如果你家裡可以充電' : MODE === 'work' ? '如果你公司可以充電' : '如果家裡、公司都不能充電',
      sub: `從${HOME.name}到${WORK.name}上班${school ? '，下班接小孩' : ''}，這一天開 ${r1(kmDay)} 公里。`,
      co2Line: `一年約等於 ${Math.round(kmDay * K.WORKDAYS * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量（只算上班日）`,
      saveLine: `一年約省 NT$ ${Math.round(kmDay * K.WORKDAYS * savePerKm(price)).toLocaleString()}（只算上班日）`,
      preload: { maxMs: 3500 } };
  }

  // ======================= 你的一週 =======================
  // 週一像「你的一天」完整看一次；週二到週五拉到高空快轉（只有上下班、接小孩，以及要充電的時候）；
  // 週六全家去家附近的百貨（「都不能充」就在那裡快充）；週日全家去附近的公園；最後總結。
  async function week(ctx) {
    const { sim, MODE, HOME, WORK, near } = ctx;
    const places = [], life = lifePlaces(ctx);
    const office = pickSlow(ctx.nearWork.stations), mall = life.mall || { ...pickFast(ctx.nearHome.stations) };
    office.label = office.label || placeName(office.name); mall.label = mall.label || placeName(mall.name);
    const { school, park } = life;
    const H = P(HOME), O = MODE === 'work' ? P(office) : P(WORK), S = school && P(school), B = P(mall), K2 = park && P(park), Wk = P(WORK);
    const want = [], idx = {};
    const need = (k, a, b, kind) => { idx[k] = want.length; want.push([a, b, kind]); };
    need('HO', H, O, 'go');
    if (S) { need('OS', O, S, 'back'); need('SH', S, H, 'back'); } else need('OH', O, H, 'back');
    need('HB', H, B, 'go');
    if (K2) need('HP', H, K2, 'go');   // 回家那一小段不播（下一幕就從家裡出發），里程、電量照算
    const R = await routes(ctx.api, want, new Set([O, S, B, K2].filter(Boolean)));
    const r = k => R[idx[k]], li = k => idx[k], end = k => last(r(k).coords);
    sim.setLegs(legsOf(R));
    const START = R[0].coords[0];
    // 地圖上的地點：高空快轉時也看得到（像 Google 地圖的圖釘）
    await place(sim, places, { ...HOME, kind: 'home', icon: '🏠', label: MODE === 'home' ? '家（有充電樁）' : '家', tone: 'home' });
    await place(sim, places, { ...WORK, kind: 'work', icon: '🏢', label: '公司' });
    if (MODE === 'work') await place(sim, places, { lat: office.lat, lon: office.lon, kind: 'charger', icon: '⚡', label: office.label, tone: 'charge', key: 'office', side: sideOf(office, WORK) || 'left' });
    if (MODE === 'home') places.push({ lat: START[0], lon: START[1], kind: 'charger', label: '家裡的充電樁' });
    if (school) await place(sim, places, { lat: school.lat, lon: school.lon, kind: 'school', icon: '🏫', label: `${school.label}（推估）`, key: 'school', side: sideOf(school, HOME) });
    await place(sim, places, { lat: mall.lat, lon: mall.lon, kind: 'mall', icon: '🛍️', label: mall.label + (MODE === 'public' || mall.fast ? '・快充' : ''), tone: MODE === 'public' ? 'charge' : undefined, key: 'mall', side: sideOf(mall, HOME) });
    if (park) await place(sim, places, { lat: park.lat, lon: park.lon, kind: 'park', icon: '🌳', label: park.label, key: 'park', side: sideOf(park, HOME) });

    // 高空固定鏡頭：家在左、公司在右，整個生活圈都在畫面裡；整段只慢慢轉幾度
    const all = [r('HO'), S ? r('OS') : r('OH')].flatMap(x => x.coords);
    const la = all.map(c => c[0]), lo = all.map(c => c[1]);
    const ctr = [(Math.min(...la) + Math.max(...la)) / 2, (Math.min(...lo) + Math.max(...lo)) / 2];
    const ew = Sim3D.meters([ctr[0], Math.min(...lo)], [ctr[0], Math.max(...lo)]), ns = Sim3D.meters([Math.min(...la), ctr[1]], [Math.max(...la), ctr[1]]);
    const AR = Math.max(2500, Math.max(ew, ns) * 1.1), APITCH = -62, head = headingDeg(H, O) - 90;
    let cur = head - 4;
    const A = dur => { const a = { at: ctr, range: AR, pitch: APITCH, from: cur, to: cur + 0.25 * dur }; cur = a.to; return a; };
    const t = tracker(ctx, MODE === 'home' ? 100 : MODE === 'work' ? 55 : 68, 7 * 60 + 20);
    const mDrive = (k, dur, o = {}) => t.drive(r(k), li(k), Object.assign({ cam: { anchor: A(dur) }, dur, flyIn: 0 }, o));
    const mStay = (car, dur, o = {}) => { const a = A(dur); return t.stay(ctr, Object.assign({ dur, car, orbit: { range: a.range, pitch: a.pitch, from: a.from, to: a.to }, flyIn: 0 }, o)); };
    const hiCam = (km, top = 5000) => Object.assign(cityCam(ctx, km, true), { rangeMax: Math.max(ctx.CAM.range * 1.6, Math.min(top, km * 520)) });
    let charges = 0;

    // ---------- 週一：跟「你的一天」一樣，低空跟車 ----------
    const i0 = t.stay(START, { dur: 5, orbit: { range: 1200 * near, pitch: -42 }, state: '停在家', chapter: '週一', leg: li('HO'),
      stop: { hideCar: false, walkOut: walk('dad', 'from', H) } });
    t.cue(i0, 0.05, `這是你的一週。先看週一：上班${school ? '、接小孩' : ''}。`);
    const iGo = t.drive(r('HO'), li('HO'), { cam: hiCam(r('HO').km), pace: { sigma: 0.12, sigmaMax: 0.3, maxDur: 18 } });
    t.cue(iGo, 0.12, `每天上班單程 ${r1(r('HO').km)} 公里，塞車、開冷氣都算進去。`);
    if (MODE === 'work') {
      const b0 = t.b, to = Math.min(100, t.b + (BACK - t.clock) / 60 * K.AC_PCT_PER_H);
      const i = t.stay(end('HO'), { dur: 8, min: BACK - t.clock, toBat: to, orbit: { range: 430 * near, pitch: -30 }, state: '充電中', leg: li('HO'), night: [0, 0.1],
        stop: officeStop(office, b0, to, Wk) });
      charges++;
      t.cue(i, 0.1, '週一、週四在公司插著充電，一整週就夠了。', 5.5);
    } else {
      const i = t.stay(end('HO'), { dur: 6.5, min: BACK - t.clock, orbit: { range: 600 * near, pitch: -34 }, state: '停車中', leg: li('HO'), night: [0, 0.1],
        stop: parkStop(WORK, Wk) });
      t.cue(i, 0.1, '白天車子停在公司。');
    }
    let homeEnd, homeLeg;
    if (S) {
      t.drive(r('OS'), li('OS'), { ff: '⏩ 下班路上', night: [0.3, 0.45], cam: hiCam(r('OS').km, 6500), pace: { sigma: 0.12, sigmaMax: 0.34, maxDur: 19 } });
      const i = t.stay(end('OS'), { dur: 6, min: 10, orbit: { range: 520 * near, pitch: -36 }, state: '接小孩', leg: li('OS'), night: [0.45, 0.5],
        stop: schoolStop(school, S) });
      t.cue(i, 0.05, `下班順路到${school.label}接兒子。`);
      t.drive(r('SH'), li('SH'), { night: [0.5, 0.6], pace: { sigma: 0.12, minDur: 5, maxDur: 7.5 } });
      homeEnd = end('SH'); homeLeg = li('SH');
    } else { t.drive(r('OH'), li('OH'), { ff: '⏩ 下班路上', night: [0.3, 0.6], cam: hiCam(r('OH').km, 6500), pace: { sigma: 0.12, sigmaMax: 0.34, maxDur: 20 } }); homeEnd = end('OH'); homeLeg = li('OH'); }
    const dayUse = t.used, kid = S ? ['dad', 'son'] : 'dad';
    {
      const morning = DAY + 7 * 60 + 20;
      const i = t.stay(homeEnd, { dur: 5.5, min: Math.max(0, morning - t.clock), orbit: { range: 900 * near, pitch: -38, to: cur }, state: '停在家', leg: homeLeg, night: [0.62, 0.75],
        stop: { icon: '🏠', title: '家', line: `週一開完・用掉 ${pctTxt(dayUse)}% 的電`, tone: 'home', key: 'home', walkIn: walk(kid, 'to', H) } });
      t.cue(i, 0.15, `開冷氣、遇到塞車，一天大約用掉 ${pctTxt(dayUse)}% 的電。`, 5);
    }

    // ---------- 週二～週五：高空快轉，只有上下班、接小孩，以及要充電的時候 ----------
    for (let d = 1; d < 5; d++) {
      const base = d * DAY, k = 0.22, ff = '⏩ 週二～週五 快轉';
      t.clock = Math.max(t.clock, base + 7 * 60 + 20);
      const first = mDrive('HO', 5.5 * k, { ff, chapter: d === 1 ? '週二～週五' : null, flyIn: d === 1 ? undefined : 0 });
      if (d === 1) t.cue(first, 0.05, '週二到週五都差不多：上班、接小孩。阿電幫你快轉。');
      const workMin = base + BACK - t.clock;
      if (MODE === 'work' && d === 3) {
        const b0 = t.b, to = Math.min(100, t.b + workMin / 60 * K.AC_PCT_PER_H);
        const i = mStay(end('HO'), 4, { min: workMin, toBat: to, state: '充電中', ff, leg: li('HO'), night: [0, 0.1], stop: officeStop(office, b0, to, null) });
        charges++;
        t.cue(i, 0.05, `週四在公司再充一次，充到 ${Math.round(to)}%。`, 4);
      } else mStay(end('HO'), 0.5, { min: workMin, state: '停車中', ff, leg: li('HO'), night: [0, 0.1] });
      let hk;
      if (S) {
        mDrive('OS', 5 * k, { ff, night: [0.25, 0.4] });
        mStay(end('OS'), 0.4, { min: 10, state: '接小孩', ff, leg: li('OS'), night: [0.4, 0.45] });
        mDrive('SH', 2 * k, { ff, night: [0.45, 0.55] }); hk = 'SH';
      } else { mDrive('OH', 5.5 * k, { ff, night: [0.3, 0.55] }); hk = 'OH'; }
      // 晚上：家裡可以充 → 週三、週五插著過夜
      const morning = (d + 1) * DAY + 7 * 60 + 20, bArr = t.b;
      if (MODE === 'home' && (d === 2 || d === 4)) {
        const i = mStay(end(hk), 4, { min: Math.max(0, morning - t.clock), toBat: 100, state: '充電中', ff, leg: li(hk), night: [0.75, 0.75],
          stop: { icon: '🏠', title: '家', line: `${DAYS[d]}晚上插著充電・${Math.round(bArr)}% → 100%`, tone: 'home', key: 'home' } });
        charges++;
        t.cue(i, 0.12, d === 2 ? '週三晚上在家插著，睡一覺就滿了。' : '週五晚上再插一次。', 3.6);
      } else if (d === 4) {
        const i = mStay(end(hk), 4, { min: 60, state: '停在家', ff, leg: li(hk), night: [0.7, 0.7],
          stop: { icon: '🏠', title: '家', line: `${DAYS[d]}晚上・電還有 ${Math.round(t.b)}%`, tone: 'home', key: 'home' } });
        t.cue(i, 0.05, `到${DAYS[d]}晚上，電還有 ${Math.round(t.b)}%。`, 3.8);
      } else mStay(end(hk), 0.3, { min: Math.max(0, morning - t.clock), state: '停在家', ff, leg: li(hk), night: [0.7, 0] });
    }

    // ---------- 週六：全家去百貨（「都不能充」就在這裡快充）。車子停在路邊，不開進去 ----------
    t.clock = 5 * DAY + 10 * 60 + 30;
    const iSat0 = t.stay(START, { dur: 5.5, orbit: { range: 900 * near, pitch: -40 }, state: '停在家', chapter: '週六', leg: li('HB'), flyIn: 4.6,
      stop: { hideCar: false, walkOut: walk(FAMILY, 'from', H) } });
    t.cue(iSat0, 0.08, `週六，全家去${mall.label}。`);
    t.drive(r('HB'), li('HB'), { rush: false, pace: { sigma: 0.12, minDur: 7, maxDur: 12 } });
    if (MODE === 'public') {
      const from = t.b, m = Math.max(5, (80 - from) / K.DC_PCT_PER_MIN);
      const i = t.stay(end('HB'), { dur: 14, min: 120, toBat: 80, orbit: { range: 600 * near, pitch: -55 }, state: '充電中', chapter: '逛街＋快充', leg: li('HB'),
        stop: { icon: '🛍️', title: mall.label, line: `逛街、吃飯・順便快充 ${Math.round(from)}% → 80%`, detail: chargeDetail(mall), tone: 'charge', key: 'mall',
          walkIn: walk(FAMILY, 'to', B), walkOut: walk(FAMILY, 'from', B) } });
      charges++;
      t.cue(i, 0.15, `逛街、吃飯的時候插著，${Math.round(m)} 分鐘，電就從 ${Math.round(from)}% 充到 80%。`, 7);
      t.cue(i, 0.66, '這一週，就充這一次。', 4);
    } else {
      const i = t.stay(end('HB'), { dur: 10, min: 120, orbit: { range: 600 * near, pitch: -55 }, state: '停車中', chapter: '逛街', leg: li('HB'),
        stop: { icon: '🛍️', title: mall.label, line: '全家逛街、吃飯', detail: mall.fast ? chargeDetail(mall) : undefined, key: 'mall',
          walkIn: walk(FAMILY, 'to', B), walkOut: walk(FAMILY, 'from', B) } });
      t.cue(i, 0.15, `電還有 ${Math.round(t.b)}%，不用特別充。` + (mall.bz4x_dc ? `想充的話，這裡有 ${mall.bz4x_dc} 支快充。` : ''), 7);
    }
    const backHome = k => { const x = r(k), u = usePct(x.km, x.minutes); t.km += x.km; t.used += u; t.b -= u; t.clock += x.minutes; };
    backHome('HB');

    // ---------- 週日：全家去家附近的公園 ----------
    t.clock = 6 * DAY + 9 * 60 + 30;
    if (K2) {
      const iSun0 = t.stay(START, { dur: 5.5, orbit: { range: 900 * near, pitch: -40 }, state: '停在家', chapter: '週日', leg: li('HP'), flyIn: 2.5,
        stop: { hideCar: false, walkOut: walk(FAMILY, 'from', H) } });
      t.cue(iSun0, 0.08, `週日，全家去${park.label}走走。`);
      t.drive(r('HP'), li('HP'), { rush: false, pace: { sigma: 0.12, minDur: 6, maxDur: 11 } });
      const i = t.stay(end('HP'), { dur: 10, min: 150, orbit: { range: 600 * near, pitch: -50 }, state: '停車中', leg: li('HP'),
        stop: { icon: '🌳', title: park.label, line: '全家到公園走走', detail: chargeDetail(park), key: 'park',
          walkIn: walk(FAMILY, 'to', K2), walkOut: walk(FAMILY, 'from', K2) } });
      t.cue(i, 0.15, `公園的停車場也有充電站，想充隨時可以充。`, 6);
      backHome('HP');
    }
    // ---------- 總結（週日晚上，回到高空） ----------
    t.clock = Math.max(t.clock, 6 * DAY + 17 * 60);
    const price = MODE === 'home' ? K.HOME_NT_PER_KWH : K.PUBLIC_NT_PER_KWH;
    const iSum = t.stay(ctr, { dur: 10, min: 120, car: START, orbit: { range: AR, pitch: APITCH, from: head - 6, to: head + 2 }, state: '停在家', chapter: K2 ? null : '週日', leg: li('HO'), night: [0.2, 0.5] });
    t.cue(iSum, 0.03, `這一週開了 ${Math.round(t.km)} 公里，充電 ${charges} 次，一次加油站都沒去。`, 5);
    t.cue(iSum, 0.55, `少排了 ${r1(t.km * K.CO2_PER_KM)} 公斤 CO₂，省下 NT$${Math.round(t.km * savePerKm(price))}。`, 4.5);
    return { raw: t.raw, cues: t.cues, places, legs: legsOf(R), kmTotal: t.km, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
      label: '這一週', firstDay: 0, excluded: ctx.excluded,
      title: MODE === 'home' ? '你的一週（家裡可以充電）' : MODE === 'work' ? '你的一週（公司可以充電）' : '你的一週（家裡、公司都不能充）',
      sub: `上班、${school ? '接小孩、' : ''}週六逛街、週日${park ? '去公園' : '休息'}：冷氣、塞車都算進去。`,
      co2Line: `一年約等於 ${Math.round(t.km * 52 * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量`,
      saveLine: `一年約省 NT$ ${Math.round(t.km * 52 * savePerKm(price)).toLocaleString()}`,
      preload: { maxMs: 3500 } };
  }

  // ---------- 長途（高速公路快充站、休息站停靠）：三天兩夜、回老家、出遊共用 ----------
  function longKit(ctx, t, places, fw) {
    const { sim } = ctx;
    // 服務區分南北向（或東西向）：只能停自己這一側
    function wrongWay(name, a, b) {
      const north = b[0] > a[0], east = b[1] > a[1];
      return (/北向/.test(name) && !north) || (/南向/.test(name) && north) || (/東向/.test(name) && !east) || (/西向/.test(name) && east);
    }
    // 沿路、方向正確的高速公路快充站（離路線 3 公里內），以及在路線上的位置（公里）
    function along(r) {
      const step = Math.max(1, Math.floor(r.coords.length / 600)), res = [];
      fw.forEach(s => {
        if (wrongWay(s.name, r.coords[0], last(r.coords))) return;
        let best = Infinity, idx = 0;
        const dist = i => { const [la, lo] = r.coords[i]; return Math.hypot((la - s.lat) * 111, (lo - s.lon) * 101); };
        for (let i = 0; i < r.coords.length; i += step) { const dd = dist(i); if (dd < best) { best = dd; idx = i; } }
        // 先跳著找，再在附近逐點找最近的一點（停車的位置才會貼近服務區）
        for (let i = Math.max(0, idx - step), j = Math.min(r.coords.length - 1, idx + step), k = i; k <= j; k++) { const dd = dist(k); if (dd < best) { best = dd; idx = k; } }
        if (best < 3) res.push({ ...s, idx, kmAt: r.path.cum[idx] / 1000 });
      });
      return res.sort((a, b) => a.kmAt - b.kmAt);
    }
    // 電夠：大約 2 小時（約 150 公里）休息時順便充。
    // 電不夠：在路程中間附近停一次、充到 80%（與 advisor.html 的 planTrip 一致）；停之前與到達時都至少留 15%
    function plan(r, soc0, st) {
      const perKm = usePct(r.km, r.minutes) / r.km, need = r.km * perKm;
      if (soc0 - need >= 20) {
        if (r.km < 120 || !st.length) return { stop: null, needed: false, count: st.length };
        const target = Math.min(150, r.km * 0.55);
        return { stop: st.reduce((p, s) => Math.abs(s.kmAt - target) < Math.abs(p.kmAt - target) ? s : p), needed: false, count: st.length };
      }
      const ok = st.filter(s => soc0 - s.kmAt * perKm >= 15 && 80 - (r.km - s.kmAt) * perKm >= 15);
      if (ok.length) return { stop: ok.reduce((p, s) => Math.abs(s.kmAt - r.km / 2) < Math.abs(p.kmAt - r.km / 2) ? s : p), needed: true, count: st.length };
      const reach = st.filter(s => soc0 - s.kmAt * perKm >= 15);
      return { stop: reach.length ? last(reach) : (st[0] || null), needed: true, count: st.length };
    }
    // 長途：出發與到達時低空，中段拉到高空（最高 30 公里，看得到整個台灣西部）。11/11：整體放慢
    const longCam = km => ({ range: 1200, rangeMax: Math.max(6000, Math.min(30000, km * 250)), ramp: Math.min(6000, km * 1000 / 3), pitch: -45, pitchMax: -58 });
    const sname = n => n.replace(/\s*[（(].*[)）]\s*$/, '');

    // 一段長途：可能在休息站停一次（車子停在高速公路旁的路線上，資訊卡寫清楚是哪一站、有哪些 bZ4X 能用的接頭）。
    // ff（回程快轉）：鏡頭固定在高空、看得到整條路線，車子沿著黃線開回家；只有「需要」充電才停
    async function longLeg(r, leg, dayChapter, nightFrom, ff, o = {}) {
      const who = o.who || FAMILY;
      const st = along(r), p1 = plan(r, t.b, st), p0 = o.onlyNeeded && !p1.needed ? { stop: null, needed: false, count: p1.count } : p1;
      const p = ff && !p0.needed ? { stop: null, needed: false, count: p0.count } : p0;
      for (const s of st) {
        if (p.stop && s.id === p.stop.id) continue;
        places.push({ lat: s.lat, lon: s.lon, kind: 'alt', fast: true, label: s.name });
        await sim.addPin({ lat: s.lat, lon: s.lon, fast: true, label: sname(s.name) });
      }
      const stopD = p.stop ? p.stop.kmAt * 1000 : null;
      const parts = p.stop ? [r.path.sub(0, stopD), r.path.sub(stopD, r.path.total)] : [r.path];
      const kmParts = p.stop ? [p.stop.kmAt, r.km - p.stop.kmAt] : [r.km];
      let anchor = null;
      if (ff) {
        const la = r.coords.map(c => c[0]), lo = r.coords.map(c => c[1]);
        const ctr = [(Math.min(...la) + Math.max(...la)) / 2, (Math.min(...lo) + Math.max(...lo)) / 2];
        const ext = Math.max(Sim3D.meters([ctr[0], Math.min(...lo)], [ctr[0], Math.max(...lo)]), Sim3D.meters([Math.min(...la), ctr[1]], [Math.max(...la), ctr[1]]));
        let cur = headingDeg(r.coords[0], last(r.coords)) - 93;
        anchor = d => { const a = { at: ctr, range: Math.max(20000, ext * 1.3), pitch: -64, from: cur, to: cur + 0.3 * d }; cur = a.to; return a; };
      }
      const FF_TOTAL = Math.max(9, Math.min(15, r.km / 30));
      const o0 = o;
      const part = (path, k, o) => {
        const seg = { path, km: k, minutes: r.minutes * k / r.km };
        if (ff) { const d = FF_TOTAL * k / r.km; return t.drive(seg, leg, Object.assign({ cam: { anchor: anchor(d) }, dur: d, ff, rush: false }, o)); }
        return t.drive(seg, leg, Object.assign({ cam: longCam(k), pace: { sigma: 0.1, maxDur: Math.min(o0.maxDur || 99, k > 150 ? 36 : 30) }, rush: false }, o));
      };
      const depart = t.clock;
      const i1 = part(parts[0], kmParts[0], { chapter: dayChapter, night: [nightFrom, nightFrom], flyIn: o0.flyIn });
      let stopInfo = null, i2 = null;
      if (p.stop) {
        const s = p.stop, target = p.needed ? 80 : Math.min(80, t.b + 15 * K.DC_PCT_PER_MIN);
        const m = p.needed ? Math.max(5, (80 - t.b) / K.DC_PCT_PER_MIN) : 15;
        await place(sim, places, { lat: s.lat, lon: s.lon, kind: 'charger', icon: '⚡', label: sname(s.name), tone: 'charge', key: 'stop' + leg });
        const from = t.b, hours = r1((t.clock - depart) / 60), at = r.path.at(stopD);
        const card = { icon: '⚡', title: sname(s.name), line: p.needed ? `休息一下・快充 ${Math.round(from)}% → ${Math.round(target)}%` : `喝杯咖啡・順便充 ${Math.round(m)} 分鐘`,
          detail: chargeDetail(s), tone: 'charge', key: 'stop' + leg };
        let i;
        if (ff) {
          const a = anchor(5);
          i = t.stay(a.at, { dur: 5, car: at, min: m, toBat: target, orbit: { range: a.range, pitch: a.pitch, from: a.from, to: a.to }, state: '充電中', leg, ff, flyIn: 0, night: [nightFrom, nightFrom], stop: card });
        } else i = t.stay(at, { dur: 13, min: m, toBat: target, orbit: { range: 900, pitch: -40 }, state: '充電中', chapter: o0.stopChapter === undefined ? '休息站' : o0.stopChapter, leg, night: [nightFrom, nightFrom],
          stop: Object.assign({ walkIn: walk(who, 'to', [s.lat, s.lon]), walkOut: walk(who, 'from', [s.lat, s.lon]) }, card) });
        stopInfo = { s, m, from, to: t.b, i, needed: p.needed, hours };
        i2 = part(parts[1], kmParts[1], { night: [nightFrom, nightFrom + 0.1], flyIn: ff ? 0 : undefined });
      }
      return { stopInfo, needed: p.needed, count: p.count, i1, i2 };
    }

    return { along, plan, longCam, sname, longLeg };
  }

  // ======================= 三天兩夜 =======================
  async function trip(ctx) {
    const { sim, HOME, DEST } = ctx;
    const places = [];
    const fw = onlyUsable(await ctx.api('api/ev/freeway'), ctx.counter).stations.filter(s => s.fast);
    const nearDest = onlyUsable(await ctx.api(`api/ev/nearby?lat=${DEST.lat}&lon=${DEST.lon}&radius_km=6&limit=12`), ctx.counter);
    // 第二天：在景點附近繞一圈（目的地 → 附近 1.5–3.5 公里的一點 → 回目的地），車子一直看得到
    const far = nearDest.stations.filter(s => s.distance_km >= 1.5 && s.distance_km <= 3.5).sort((a, b) => Math.abs(a.distance_km - 2.5) - Math.abs(b.distance_km - 2.5))[0]
      || nearDest.stations.filter(s => s.distance_km >= 1).sort((a, b) => a.distance_km - b.distance_km)[0];
    const wp = far ? P(far) : [DEST.lat + 0.025, DEST.lon + 0.01];
    const want = [[P(HOME), P(DEST), 'go'], [P(DEST), P(HOME), 'back'], [P(DEST), wp, 'go'], [wp, P(DEST), 'back']];
    const [out, back, loopA, loopB] = await routes(ctx.api, want);
    sim.setLegs(legsOf([out, back, loopA, loopB]));
    await place(sim, places, { ...HOME, kind: 'home', icon: '🏠', label: '家', tone: 'home' });
    await place(sim, places, { ...DEST, kind: 'dest', icon: '🏁', label: DEST.name, key: 'dest' });
    const t = tracker(ctx, 100, 9 * 60);
    const { longLeg } = longKit(ctx, t, places, fw);
    const s0 = t.stay(out.coords[0], { dur: 6, orbit: { range: 3000, pitch: -50 }, state: '停在家', chapter: '出發', leg: 0,
      stop: { hideCar: false, walkOut: walk(FAMILY, 'from', P(HOME)) } });
    t.cue(s0, 0.1, `三天兩夜，全家從${HOME.name}去${DEST.name}，單程 ${Math.round(out.km)} 公里。`);
    const go = await longLeg(out, 0, '去程', 0, null);
    t.cue(go.i1, 0.1, `沿路有 ${go.count} 個 bZ4X 能用的高速公路快充站，阿電都幫你標好了。`);
    t.cue(go.i1, 0.45, '高速公路上有 LTA 車道循跡輔助，長途開起來比較輕鬆。');
    if (go.stopInfo) {
      const x = go.stopInfo;
      t.cue(x.i, 0.05, x.needed
        ? `開了 ${x.hours} 小時，在${x.s.name}休息。上個廁所、買杯咖啡，電就從 ${Math.round(x.from)}% 充到 ${Math.round(x.to)}%。`
        : `電其實夠開到${DEST.name}。開了 ${x.hours} 小時，在${x.s.name}休息喝杯咖啡，順便充 ${x.m} 分鐘。`, 8);
      t.cue(go.i2, 0.4, '下坡的時候，電動車還會回收一點電。');
    } else t.cue(go.i1, 0.8, `${Math.round(out.km)} 公里一路開到，不用中途充電。`);
    for (const s of nearDest.stations.slice(0, 8)) {
      places.push({ lat: s.lat, lon: s.lon, kind: 'alt', fast: s.fast, label: s.name });
      await sim.addPin({ lat: s.lat, lon: s.lon, fast: s.fast, label: `${s.fast ? '快充' : '慢充'} ${distTxt(s.distance_km)}` });
    }
    // 目的地：車子不消失（停在路線終點，看得到），晚上順便充電；第二天在附近繞一圈
    const destEnd = last(out.coords), bArr = t.b;
    let i = t.stay(destEnd, { dur: 8, min: Math.max(0, 20 * 60 - t.clock), orbit: { range: 1800, pitch: -42 }, state: '停車中', chapter: DEST.name, leg: 0, night: [0, 0.55],
      stop: { icon: '🏁', title: DEST.name, line: `到了・電還有 ${Math.round(bArr)}%`, key: 'dest', hideCar: false, walkIn: walk(FAMILY, 'to', P(DEST)) } });
    t.cue(i, 0.1, `到${DEST.name}了，電還有 ${Math.round(t.b)}%。附近有 ${nearDest.total} 個 bZ4X 能用的充電站。`, 7);
    i = t.stay(destEnd, { dur: 7, min: Math.max(0, DAY + 8 * 60 - t.clock), toBat: nearDest.total ? 100 : null, orbit: { range: 1500, pitch: -40, turn: 30 }, state: nearDest.total ? '充電中' : '停車中', chapter: '第一晚', leg: 0, night: [0.6, 0.85], flyIn: 1.4,
      stop: nearDest.total ? { icon: '⚡', title: '第一晚', line: '停車順便充電・隔天又是滿的', tone: 'charge', key: 'dest', hideCar: false } : { icon: '🏨', title: '第一晚', line: '旅館停車過夜', key: 'dest', hideCar: false } });
    if (nearDest.total) t.cue(i, 0.08, '晚上停車順便充，隔天又是滿的。');
    // 第二天：在景點附近繞一圈
    t.clock = DAY + 9 * 60 + 30;
    const iD2 = t.stay(destEnd, { dur: 5.5, orbit: { range: 1200, pitch: -42 }, state: '停車中', chapter: '第二天', leg: 2, night: [0, 0], flyIn: 2,
      stop: { hideCar: false, walkOut: walk(FAMILY, 'from', P(DEST)) } });
    t.cue(iD2, 0.08, `第二天，在${DEST.name}附近繞一圈。`);
    const loopCam = km => Object.assign(cityCam(ctx, km, true), { rangeMax: Math.max(ctx.CAM.range * 1.6, Math.min(3200, km * 600)) });
    const iLa = t.drive(loopA, 2, { rush: false, cam: loopCam(loopA.km), pace: { sigma: 0.12, sigmaMax: 0.3, minDur: 9, maxDur: 19 } });
    const wpName = far ? placeName(far.name) : `${DEST.name}附近`;
    i = t.stay(last(loopA.coords), { dur: 8, min: 120, orbit: { range: 900, pitch: -45 }, state: '出遊中', leg: 2,
      stop: { icon: '📸', title: wpName, line: '下車走走、拍照', key: 'wp', hideCar: false, walkIn: walk(FAMILY, 'to', wp), walkOut: walk(FAMILY, 'from', wp) } });
    t.cue(iLa, 0.3, `在地開 ${r1(loopA.km + loopB.km)} 公里，冷氣也算進去，只用掉 ${pctTxt(usePct(loopA.km + loopB.km, (loopA.minutes + loopB.minutes) * 1.2))}% 的電。`);
    t.drive(loopB, 3, { rush: false, cam: loopCam(loopB.km), pace: { sigma: 0.12, sigmaMax: 0.3, minDur: 8, maxDur: 19 } });
    t.clock = 2 * DAY + 15 * 60;   // 週日 15:00 回程
    const ret = await longLeg(back, 1, '回程', 0.15, '⏩ 回程快轉');
    t.cue(ret.i1, 0.02, '回程一樣輕鬆，阿電幫你快轉。');
    if (ret.stopInfo) t.cue(ret.stopInfo.i, 0.03, `回程在${ret.stopInfo.s.name}休息 ${Math.round(ret.stopInfo.m)} 分鐘，順便充電。`, 5);
    const bHome = t.b;
    i = t.stay(last(back.coords), { dur: 13, min: 10, orbit: { range: 2400, pitch: -45 }, state: '停在家', chapter: '到家', leg: 1, night: [0.6, 0.65],
      stop: { icon: '🏠', title: '到家', line: `三天開了 ${Math.round(t.km)} 公里・電還剩 ${Math.round(bHome)}%`, tone: 'home', key: 'home', walkIn: walk(FAMILY, 'to', P(HOME)) } });
    const price = K.PUBLIC_NT_PER_KWH;
    t.cue(i, 0.15, `到家了，電還剩 ${Math.round(t.b)}%。`);
    t.cue(i, 0.48, `這三天開了 ${Math.round(t.km)} 公里，少排了 ${r1(t.km * K.CO2_PER_KM)} 公斤 CO₂，油錢省下 NT$${Math.round(t.km * savePerKm(price))}。`, 6.5);
    return { raw: t.raw, cues: t.cues, places, legs: legsOf([out, back]), kmTotal: t.km, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
      label: '這趟旅程', firstDay: 4, excluded: ctx.excluded,
      title: `三天兩夜：${HOME.name} → ${DEST.name}`, sub: `單程 ${Math.round(out.km)} 公里，週五出發、週日回家。`,
      co2Line: `等於 ${r1(t.km * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量`, saveLine: '跟開油車比（快充以每度 NT$8 估算）',
      preload: { maxMs: 3000 } };
  }

  // ======================= 照客戶自己的生活（11/12，SIM_CONTRACT_20261112.md） =======================
  // 只有網址帶了新參數（anchor、wdays、kmode、slat、wx、okm、wkd、htlat、olat、tstops）才走這裡；沒帶就是上面原本的情境。
  //   ctx.U = { anchor: 'office'|'home'|'roam', wdays: 1–5, kmode: 'both'|'am'|'pm', school?, wx: [], okm, wkd: [], ht?, out?, tstops?, hasWork }
  const OFFICE_DAYS = { 1: [0], 2: [0, 3], 3: [0, 2, 4], 4: [0, 1, 2, 3], 5: [0, 1, 2, 3, 4], 6: [0, 1, 2, 3, 4, 5], 7: [0, 1, 2, 3, 4, 5, 6] };   // 11/13：週六、週日也上班
  // 平日的其他行程：哪幾天（0 = 週一）。一週買菜兩次、運動兩次、陪爸媽看醫生一次、補習班接小孩兩次（週一要完整播放，排在週二、週四）
  const XDAYS = { market: [0, 3], gym: [1, 4], parents: [2], cram: [1, 3] };
  const XINFO = {
    market: { icon: '🛒', line: '買菜・大約 30 分鐘', min: 30, say: p => `去${p.label}買菜。` },
    gym: { icon: '🏋️', line: '運動一下・大約 1 小時', min: 60, say: p => `去${p.label}運動一下。` },
    parents: { icon: '🏥', line: '陪爸媽看醫生・大約 1.5 小時', min: 90, say: p => `帶爸媽去${p.label}看醫生。` },
    cram: { icon: '📚', line: '補習班下課・接小孩回家', min: 10, say: p => `晚上到${p.label}接小孩下課。` },
  };
  const EST_NOTE = '地點為阿電依住家附近推估';
  const nightOf = c => { const m = ((c % DAY) + DAY) % DAY;
    if (m < 6 * 60) return 0.7; if (m < 7 * 60) return 0.7 * (1 - (m - 360) / 60); if (m < 17 * 60 + 30) return 0; if (m < 19 * 60) return 0.7 * (m - 1050) / 90; return 0.7; };
  const CN = ['零', '一', '兩', '三', '四', '五', '六', '七', '八', '九', '十'];
  const cnDays = n => CN[n] || String(n);   // 三天兩夜、兩天一夜

  // 生活地點：gateway api/poi（OpenStreetMap → TDX 充電站名稱）。端點出錯才自己用充電站名稱找；都找不到就略過那一站，不編地點
  const POI_RE = { school: /國小|小學/, market: /市場|全聯|超市|美聯社/, gym: /運動中心|健身|體育館|游泳|瑜珈|瑜伽/, clinic: /醫院|診所|衛生所/,
    cram: /補習|文理|美語|安親/, park: /公園/, mall: MALL, attraction: /風景|遊樂|農場|老街|國家公園|觀光|森林|步道|博物館|漁港|海水浴場|遊客中心/ };
  async function findPoi(ctx, kind, at, o = {}) {
    const radius = o.radius || 3, limit = o.limit || 8, minKm = o.minKm || 0;
    let items = null;
    try {
      const r = await ctx.api(`api/poi?kind=${kind}&lat=${at.lat}&lon=${at.lon}&radius_km=${radius}&limit=${limit}${minKm ? `&min_km=${minKm}` : ''}`);
      if (r && Array.isArray(r.items)) items = r.items;
    } catch (e) { items = null; }
    if (items == null) {
      let st = o.stations;
      if (!st) st = await ctx.api(`api/ev/nearby?lat=${at.lat}&lon=${at.lon}&radius_km=${radius}&limit=200`).then(r => r.stations || []).catch(() => []);
      items = st.filter(s => POI_RE[kind].test(s.name || '')).map(s => ({ name: s.name, lat: s.lat, lon: s.lon, km: s.distance_km }));
    }
    return items.filter(x => x && x.name && Number.isFinite(+x.lat) && Number.isFinite(+x.lon) && (x.km == null || (x.km >= minKm && x.km <= radius)))
      .map(x => ({ ...x, lat: +x.lat, lon: +x.lon, label: placeName(x.name) })).sort((a, b) => (a.km || 0) - (b.km || 0));
  }
  // 路線（一次最多 3 條，對公用 OSRM 客氣一點）。OSRM 沒回應時 gateway 回傳估計值（沒有路線座標）：稍微挪一點起點再問一次，還是沒有就畫直線
  async function routes2(api, pairs, trim) {
    const out = new Array(pairs.length);
    const one = async (a, b, nudge) => api(`api/route?src=${(a[0] + nudge).toFixed(6)},${a[1].toFixed(6)}&dst=${b[0].toFixed(6)},${b[1].toFixed(6)}&geometry=2`).catch(() => null);
    for (let i = 0; i < pairs.length; i += 3) {
      await Promise.all(pairs.slice(i, i + 3).map(async ([a, b], j) => {
        let r = await one(a, b, 0);
        if (!r || !r.coords || r.coords.length < 2) r = (await one(a, b, 0.000004)) || r;
        if (!r || !r.coords || r.coords.length < 2) {
          const km = Sim3D.meters(a, b) / 1000 * 1.3;
          r = { km: r && r.km || r1(km), minutes: r && r.minutes || Math.max(1, Math.round(km / 40 * 60)), coords: [a.slice(), b.slice()], source: 'line' };
        }
        out[i + j] = r;
      }));
    }
    out.forEach((r, i) => {
      const [a, b, kind] = pairs[i];
      r.minutes = Math.max(1, r.minutes || 0);
      if (trim.has(b)) r.coords = trimNear(r.coords, b, 35, true);
      if (trim.has(a)) r.coords = trimNear(r.coords, a, 35, false);
      r.coords = Sim3D.simplify(r.coords, r.km > 60 ? 8 : 3);
      r.path = Sim3D.makePath(r.coords); r.kind = kind || 'go';
    });
    return out;
  }
  // 週末：最多兩項（第一項週六、第二項週日）。回老家一定是週六去、週日回；另一項（百貨、公園）就在老家附近
  function weekendPlan(list, U) {
    const ok = ['mall', 'park', 'hometown', 'outing', 'home'];
    let L = [...new Set((list || []).filter(x => ok.includes(x)))].slice(0, 2);
    if (!U.ht) L = L.filter(x => x !== 'hometown');
    if (L.includes('hometown')) { const other = L.find(x => x !== 'hometown'); return { ht: true, sun: ['mall', 'park'].includes(other) ? other : null }; }
    return { sat: L[0] || 'home', sun: L[1] || (L.length ? 'quiet' : 'quiet') };
  }

  async function life2(ctx, opt = {}) {
    const { sim, HOME, WORK, near, U } = ctx;
    const dayOnly = !!opt.dayOnly, places = [], kids = !!ctx.kids, anchor = U.anchor;
    const workDays = anchor === 'home' ? [] : (OFFICE_DAYS[U.wdays] || OFFICE_DAYS[5]);
    let MODE = ctx.MODE === 'work' && anchor !== 'office' ? 'public' : ctx.MODE;   // 不去公司：公司的充電樁用不到，跟「都不能充」一樣
    let pubWork = false;   // 11/16：家附近沒有快充的上班族 → 上班時插公司附近的公共充電站
    const am = kids && U.kmode !== 'pm', pm = kids && U.kmode !== 'am';
    const wx = (U.wx || []).filter(x => XINFO[x] && (x !== 'cram' || kids));
    const wantX = k => wx.includes(k);
    let WK = dayOnly ? null : weekendPlan(U.wkd, U);
    // 11/13：週六（或週六日）也上班——那幾天跟平日一樣快轉；週末只剩週日（回老家要兩天，改成週日一個在地行程）
    if (WK && workDays.includes(5)) {
      const keep = (U.wkd || []).find(x => x === 'mall' || x === 'park' || x === 'outing' || x === 'home');
      WK = workDays.includes(6) ? { sat: 'work', sun: 'work' } : { sat: 'work', sun: keep || 'quiet' };
    }
    const wkdHas = k => WK && (WK.sat === k || WK.sun === k);
    const homeSt = ctx.nearHome.stations, life = lifePlaces(Object.assign({}, ctx, { kids: false }));
    const who = kids ? FAMILY : 'dad';
    const mk = (o, kind, icon, extra) => o ? Object.assign({ lat: +o.lat, lon: +o.lon, label: o.label || placeName(o.name || ''), name: o.name, kind, icon, key: kind }, extra, { p: [+o.lat, +o.lon] }) : null;
    const pick1 = (arr, re) => (arr && arr.length) ? ((re && arr.find(x => re.test(x.name))) || arr[0]) : null;
    const H = P(HOME), Hp = { ...HOME, kind: 'home', icon: '🏠', label: MODE === 'home' ? '家（有充電樁）' : '家', key: 'home', p: H };
    const roamArea = U.hasWork ? WORK : HOME;

    // ---------- 地點 ----------
    const [schL, mktL, gymL, cliL, crmL, mallL, parkL, roamSt, outL, fastSt] = await Promise.all([
      kids && !U.school ? findPoi(ctx, 'school', HOME, { radius: 3, stations: homeSt }) : null,
      wantX('market') ? findPoi(ctx, 'market', HOME, { radius: 3, stations: homeSt }) : null,
      wantX('gym') ? findPoi(ctx, 'gym', HOME, { radius: 5 }) : null,
      wantX('parents') ? findPoi(ctx, 'clinic', HOME, { radius: 5 }) : null,
      wantX('cram') ? findPoi(ctx, 'cram', HOME, { radius: 3 }) : null,
      wkdHas('mall') && !life.mall ? findPoi(ctx, 'mall', HOME, { radius: 8 }) : null,
      wkdHas('park') && !life.park ? findPoi(ctx, 'park', HOME, { radius: 3, stations: homeSt }) : null,
      anchor === 'roam' ? ctx.api(`api/ev/nearby?lat=${roamArea.lat}&lon=${roamArea.lon}&radius_km=5&limit=80`).then(r => r.stations || []).catch(() => []) : null,
      wkdHas('outing') && !U.out ? findPoi(ctx, 'attraction', HOME, { radius: 60, minKm: 25, limit: 12 }) : null,
      MODE === 'public' && !homeSt.some(s => s.fast) ? ctx.api(`api/ev/nearby?lat=${HOME.lat}&lon=${HOME.lon}&radius_km=12&limit=30`).then(r => onlyUsable(r, ctx.counter).stations).catch(() => []) : null,
    ]);
    const S = U.school ? mk(U.school, 'school', '🏫', { label: U.school.name }) : kids ? mk(pick1(schL, /國小|小學/), 'school', '🏫', { est: true }) : null;
    const X = {
      market: mk(pick1(mktL), 'market', '🛒', { est: true }), gym: mk(pick1(gymL), 'gym', '🏋️', { est: true }),
      parents: mk(pick1(cliL), 'clinic', '🏥', { est: true }), cram: mk(pick1(crmL), 'cram', '📚', { est: true }),
    };
    const Bp = life.mall ? mk(life.mall, 'mall', '🛍️', { charger: life.mall, est: true }) : mk(pick1(mallL), 'mall', '🛍️', { est: true });
    const Kp = life.park ? mk(life.park, 'park', '🌳', { charger: life.park, est: true }) : mk(pick1(parkL), 'park', '🌳', { est: true });
    let fastL = fastSt || [];
    if (MODE === 'public' && !homeSt.some(s => s.fast) && !fastL.some(s => s.fast)) {   // 11/16：鄉下（例如南投信義鄉）12 公里內沒有快充
      if (anchor === 'office' && (ctx.nearWork.stations || []).length) { MODE = 'work'; pubWork = true; }
      else fastL = await ctx.api(`api/ev/nearby?lat=${HOME.lat}&lon=${HOME.lon}&radius_km=40&limit=30`).then(r => onlyUsable(r, ctx.counter).stations).catch(() => []);
    }
    const fastS = MODE === 'public' ? (homeSt.find(s => s.fast) || fastL.find(s => s.fast) || null) : null;
    const Fp = fastS ? mk(fastS, 'charger', '⚡', { charger: fastS, key: 'fast' }) : null;
    let Op = null;
    if (anchor === 'office') {
      const os = MODE === 'work' ? pickSlow(ctx.nearWork.stations) : null;
      Op = MODE === 'work' ? (os ? mk(os, 'charger', '⚡', { charger: os, key: 'office' }) : { ...WORK, kind: 'work', icon: '🏢', label: '公司的充電樁', key: 'office', p: P(WORK), own: true })
        : { ...WORK, kind: 'work', icon: '🏢', label: '公司', key: 'work', p: P(WORK) };
    }
    const Wk = P(WORK);
    const R = [];
    if (anchor === 'roam') {
      const cand = (roamSt || []).filter(s => s.distance_km >= (U.hasWork ? 0.5 : 1.2)).sort((a, b) => a.distance_km - b.distance_km);
      for (const s of cand) {
        if (R.length >= 3) break;
        if (R.every(r => Sim3D.meters(r.p, P(s)) > 1200) && Sim3D.meters(H, P(s)) > 800)
          R.push(mk(s, 'client', '💼', { label: '客戶（示意）', near: placeName(s.name), key: 'client' + R.length }));
      }
    }
    const OU = WK && wkdHas('outing') ? (U.out ? mk(U.out, 'dest', '📸', { label: U.out.name, key: 'outing' }) : mk(pick1(outL), 'dest', '📸', { est: true, key: 'outing' })) : null;
    if (WK && wkdHas('outing') && !OU) { if (WK.sat === 'outing') WK.sat = 'home'; if (WK.sun === 'outing') WK.sun = 'quiet'; }
    const HT = WK && WK.ht ? { lat: U.ht.lat, lon: U.ht.lon, name: U.ht.name, label: /老家$/.test(U.ht.name) ? U.ht.name : `${U.ht.name}老家`, kind: 'dest', icon: '🏡', key: 'ht', p: [U.ht.lat, U.ht.lon] } : null;
    // 回老家：老家附近的充電站、週日去的地方（百貨、公園，在老家附近）
    let nearHT = null, P2 = null;
    if (HT) {
      [nearHT, P2] = await Promise.all([
        ctx.api(`api/ev/nearby?lat=${HT.lat}&lon=${HT.lon}&radius_km=6&limit=12`).then(r => onlyUsable(r, ctx.counter)).catch(() => ({ stations: [], total: 0 })),
        WK.sun ? findPoi(ctx, WK.sun, HT, { radius: WK.sun === 'mall' ? 8 : 3 }).then(l => mk(pick1(l), WK.sun, WK.sun === 'mall' ? '🛍️' : '🌳', { est: true, key: 'p2' })) : null,
      ]);
    }

    // ---------- 每一天的行程（地點的順序） ----------
    const dayType = d => anchor === 'office' && workDays.includes(d) ? 'office' : anchor === 'roam' && R.length && workDays.includes(d) ? 'roam' : 'home';
    const xOn = (k, d) => wantX(k) && X[k] && XDAYS[k].includes(d);
    const stp = (pl, act, min) => ({ pl, act, min });
    function dayPlan(d) {
      const ty = dayType(d), trips = [];
      const eve = ['market', 'gym', 'parents'].filter(k => xOn(k, d));
      if (ty === 'office') {
        trips.push({ at: 7 * 60 + 20, seq: [stp(Hp, 'start'), am && S && stp(S, 'drop', 5), stp(Op, 'work')].filter(Boolean) });
        trips.push({ at: BACK, seq: [stp(Op, 'start'), pm && S && stp(S, 'pick', 10), ...eve.slice(0, 1).map(k => stp(X[k], k, XINFO[k].min)), stp(Hp, 'home')].filter(Boolean) });
      } else if (ty === 'roam') {
        const cl = R.map((r, i) => stp(r, 'client', i === R.length - 1 ? (pm && S ? 'until' : 60) : i === 1 ? 90 : 60));
        trips.push({ at: 8 * 60 + 30, seq: [stp(Hp, 'start'), am && S && stp(S, 'drop', 5), ...cl, pm && S && stp(S, 'pick', 10), stp(Hp, 'home')].filter(Boolean) });
        if (eve.length) trips.push({ at: 18 * 60 + 30, seq: [stp(Hp, 'start'), stp(X[eve[0]], eve[0], XINFO[eve[0]].min), stp(Hp, 'home')] });
      } else {
        const morn = eve.filter(k => k !== 'parents');
        if (am && S) trips.push({ at: 7 * 60 + 30, seq: [stp(Hp, 'start'), stp(S, 'drop', 5), ...morn.slice(0, 1).map(k => stp(X[k], k, XINFO[k].min)), stp(Hp, 'home')] });
        else if (morn.length) trips.push({ at: 9 * 60 + 30, seq: [stp(Hp, 'start'), stp(X[morn[0]], morn[0], XINFO[morn[0]].min), stp(Hp, 'home')] });
        if (eve.includes('parents')) trips.push({ at: 10 * 60 + 30, seq: [stp(Hp, 'start'), stp(X.parents, 'parents', 90), stp(Hp, 'home')] });
        if (pm && S) trips.push({ at: 16 * 60, seq: [stp(Hp, 'start'), stp(S, 'pick', 10), stp(Hp, 'home')] });
      }
      if (xOn('cram', d)) trips.push({ at: 20 * 60 + 30, seq: [stp(Hp, 'start'), stp(X.cram, 'cram', 10), stp(Hp, 'home')] });
      return { d, ty, trips };
    }
    const plans = (dayOnly ? [0] : [0, 1, 2, 3, 4, ...workDays.filter(d => d > 4)]).map(dayPlan);
    const lastD = plans.length - 1, ffRange = `週二～${DAYS[Math.max(1, lastD)]}`;

    // ---------- 需要的路線（同一段只問一次） ----------
    const want = [], idx = new Map(), trim = new Set();
    const keyOf = (a, b) => a.p.join(',') + '>' + b.p.join(',');
    const need = (a, b, kind) => {
      const k = keyOf(a, b);
      if (!idx.has(k)) { idx.set(k, want.length); want.push([a.p, b.p, kind || (b === Hp || a === Op ? 'back' : 'go')]); }
      [a, b].forEach(x => { if (x !== Hp && x !== HT && x.kind !== 'dest') trim.add(x.p); });
      return k;
    };
    plans.forEach(pl => pl.trips.forEach(tr => tr.seq.forEach((s, i) => { if (i) s.leg = need(tr.seq[i - 1].pl, s.pl); })));
    const wkLegs = new Set(idx.keys());
    let topK = null;
    if (Fp) topK = [need(Hp, Fp, 'go'), need(Fp, Hp, 'back')];
    const wkdNeed = {};
    if (WK) {
      for (const it of [WK.sat, WK.sun]) {
        if (it === 'mall' && Bp) wkdNeed.mall = need(Hp, Bp, 'go');
        if (it === 'park' && Kp) wkdNeed.park = need(Hp, Kp, 'go');
        if (it === 'outing' && OU) { wkdNeed.outGo = need(Hp, OU, 'go'); wkdNeed.outBack = need(OU, Hp, 'back'); }
      }
      if (HT) {
        wkdNeed.htGo = need(Hp, HT, 'go');
        if (P2) { wkdNeed.p2 = need(HT, P2, 'go'); wkdNeed.htBack = need(P2, Hp, 'back'); } else wkdNeed.htBack = need(HT, Hp, 'back');
      }
    }
    const RT = await routes2(ctx.api, want, trim);
    const rt = k => RT[idx.get(k)], li = k => idx.get(k), end = k => last(rt(k).coords);
    sim.setLegs(legsOf(RT));
    const START = RT.length ? RT[0].coords[0] : H;

    // ---------- 地圖上的地點 ----------
    const estLabel = pl => pl.label + (pl.est ? '（推估）' : '');
    await place(sim, places, { ...HOME, kind: 'home', icon: '🏠', label: Hp.label, tone: 'home' });
    if (anchor === 'office') await place(sim, places, { ...WORK, kind: 'work', icon: '🏢', label: '公司' });
    if (anchor === 'office' && MODE === 'work' && !Op.own) await place(sim, places, { lat: Op.lat, lon: Op.lon, kind: 'charger', icon: '⚡', label: Op.label, tone: 'charge', key: 'office', side: sideOf(Op, WORK) || 'left' });
    if (MODE === 'home') places.push({ lat: START[0], lon: START[1], kind: 'charger', label: '家裡的充電樁' });
    const used = new Set(plans.flatMap(p => p.trips.flatMap(t => t.seq.map(s => s.pl))));
    for (const pl of [S, X.market, X.gym, X.parents, X.cram, ...R]) if (pl && used.has(pl)) await place(sim, places, { lat: pl.lat, lon: pl.lon, kind: pl.kind, icon: pl.icon, label: estLabel(pl), key: pl.key, side: sideOf(pl, HOME) });
    if (wkdNeed.mall) await place(sim, places, { lat: Bp.lat, lon: Bp.lon, kind: 'mall', icon: '🛍️', label: estLabel(Bp) + (MODE === 'public' && Bp.charger ? '・快充' : ''), tone: MODE === 'public' && Bp.charger ? 'charge' : undefined, key: 'mall', side: sideOf(Bp, HOME) });
    if (wkdNeed.park) await place(sim, places, { lat: Kp.lat, lon: Kp.lon, kind: 'park', icon: '🌳', label: estLabel(Kp), key: 'park', side: sideOf(Kp, HOME) });
    if (OU && wkdNeed.outGo) await place(sim, places, { lat: OU.lat, lon: OU.lon, kind: 'dest', icon: '📸', label: estLabel(OU), key: 'outing' });
    if (HT) await place(sim, places, { lat: HT.lat, lon: HT.lon, kind: 'dest', icon: '🏡', label: HT.label, key: 'ht' });
    if (P2) await place(sim, places, { lat: P2.lat, lon: P2.lon, kind: P2.kind, icon: P2.icon, label: estLabel(P2), key: 'p2' });
    // 11/16：家、公司、這週會去的地方附近的其他充電站（小圖釘、小地圖小點）——讓顧客看到生活圈裡的充電站
    {
      const seenId = new Set([Fp, Op, Bp, Kp].map(x => x && x.charger && x.charger.id).filter(Boolean));
      const pinned = places.filter(p => p.kind !== 'alt').map(p => [p.lat, p.lon]);
      const kmTo = (a, b) => Math.hypot((a.lat - b[0]) * 111, (a.lon - b[1]) * 111 * Math.cos(a.lat * Math.PI / 180));
      const visits = places.filter(p => /^(school|market|gym|clinic|cram|mall|park)$/.test(p.kind)).slice(0, 6);
      const lists = await Promise.all(visits.map(v => ctx.api(`api/ev/nearby?lat=${v.lat}&lon=${v.lon}&radius_km=1.2&limit=8`).then(r => onlyUsable(r, { excluded: 0 }).stations).catch(() => [])));
      const spots = [[homeSt, 5, true], [anchor === 'office' ? (ctx.nearWork.stations || []) : [], 4, false], ...lists.map(l => [l, 3, false])];
      let n = 0;
      for (const [list, max, dist] of spots) {
        let k = 0;
        for (const s of list) {
          if (k >= max || n >= 26) break;
          if (seenId.has(s.id) || pinned.some(q => kmTo(s, q) < 0.08)) continue;
          seenId.add(s.id); pinned.push([s.lat, s.lon]); k++; n++;
          places.push({ lat: s.lat, lon: s.lon, kind: 'alt', fast: s.fast, label: s.name });
          await sim.addPin({ lat: s.lat, lon: s.lon, fast: s.fast, label: evLabel(s), sub: evSub(s, dist) });
        }
      }
    }

    // ---------- 高空固定鏡頭（週二～週五快轉）：平日所有路線都在畫面裡 ----------
    const wkCoords = [...wkLegs].flatMap(k => rt(k).coords);
    const all = wkCoords.length ? wkCoords : [H];
    const la = all.map(c => c[0]), lo = all.map(c => c[1]);
    const ctr = [(Math.min(...la) + Math.max(...la)) / 2, (Math.min(...lo) + Math.max(...lo)) / 2];
    const ew = Sim3D.meters([ctr[0], Math.min(...lo)], [ctr[0], Math.max(...lo)]), ns = Sim3D.meters([Math.min(...la), ctr[1]], [Math.max(...la), ctr[1]]);
    const AR = Math.max(3000, Math.hypot(ew, ns) * 1.75), APITCH = -62;   // 11/13：整個平日範圍（起點、終點、中間停的點）都要在畫面裡，上面的按鈕和下面的資訊卡不能擋到
    const head = (Op ? headingDeg(H, Op.p) : R.length ? headingDeg(H, R[0].p) : 0) - 90;
    let cur = head - 4;
    const A = dur => { const a = { at: ctr, range: AR, pitch: APITCH, from: cur, to: cur + 0.25 * dur }; cur = a.to; return a; };
    const t = tracker(ctx, MODE === 'home' ? 100 : MODE === 'work' ? 55 : 68, 7 * 60 + 20);
    const nt = (c0, c1) => [nightOf(c0), nightOf(c1)];
    const hiCam = (km, top = 5000) => Object.assign(cityCam(ctx, km, true), { rangeMax: Math.max(ctx.CAM.range * 1.6, Math.min(top, km * 520)) });
    // 行車與停留：夜晚由時鐘決定
    const D = (k, o = {}) => { const r = rt(k), min = r.minutes * (o.rush === false ? 1 : K.RUSH); return t.drive(r, li(k), Object.assign({ night: nt(t.clock, t.clock + min) }, o)); };
    // 11/13（使用者）：回家的路也要真的開，不要從停車處直接跳回家、電量自己扣
    const backHome = k => D(k, { rush: false, pace: { sigma: 0.12, minDur: 4, maxDur: 8 }, state: '回家路上' });
    const St = (at, o) => t.stay(at, Object.assign({ night: nt(t.clock, t.clock + (o.min || 0)) }, o));
    const mDrive = (k, o = {}) => { const km = rt(k).km, dur = o.dur || Math.max(0.45, Math.min(1.4, 0.1 * km + 0.3)); return D(k, Object.assign({ cam: { anchor: A(dur) }, dur, flyIn: 0 }, o)); };
    const mStay = (car, dur, o = {}) => { const a = A(dur); return St(ctr, Object.assign({ dur, car, orbit: { range: a.range, pitch: a.pitch, from: a.from, to: a.to }, flyIn: 0 }, o)); };
    let charges = 0, homeLineSaid = false;
    const seen = new Set();   // 快轉時：第一次出現的行程才跳資訊卡
    const priceOf = () => MODE === 'home' ? K.HOME_NT_PER_KWH : K.PUBLIC_NT_PER_KWH;
    const chargeWhere = () => MODE === 'home' ? '睡覺' : MODE === 'work' ? '去公司' : Bp && Bp.charger && wkdHas('mall') ? `週末去${Bp.label}` : Fp ? `經過${Fp.label}` : '出門';
    const homeLine = () => `平常在家的日子，車子大多停著；${chargeWhere()}的時候順便充一下就好。`;

    // 停靠：每一種行程的資訊卡
    function stopCard(s, ty) {
      const pl = s.pl, note = pl.est ? EST_NOTE : undefined;
      if (s.act === 'drop') return { icon: '🏫', title: pl.label, line: '早上送小孩上學', note: pl.est ? '學校為阿電依住家推估' : undefined, key: pl.key, hideCar: false, walkIn: walk('son', 'to', pl.p) };
      if (s.act === 'pick') return { icon: '🏫', title: pl.label, line: ty === 'office' ? '下班順路接小孩' : '接小孩放學', note: pl.est ? '學校為阿電依住家推估' : undefined, key: pl.key, hideCar: false, walkOut: walk('son', 'from', pl.p) };
      if (s.act === 'cram') return { icon: '📚', title: pl.label, line: XINFO.cram.line, note, key: pl.key, hideCar: false, walkOut: walk('son', 'from', pl.p) };
      if (s.act === 'client') return { icon: '💼', title: '客戶（示意）', line: `拜訪客戶・在${pl.near}附近`, note: '客戶位置為示意', key: pl.key, walkIn: walk('dad', 'to', pl.p), walkOut: walk('dad', 'from', pl.p) };
      if (XINFO[s.act]) return { icon: XINFO[s.act].icon, title: pl.label, line: XINFO[s.act].line, note, key: pl.key, walkIn: walk('dad', 'to', pl.p), walkOut: walk('dad', 'from', pl.p) };
      return null;
    }
    // 在公司：「公司可以充」就插著慢充（電量低於 80%，或週末要出遠門前最後一天上班）
    const lastOffice = Math.max(...workDays.filter(d => dayType(d) === 'office'), -1);
    const longWkd = WK && (WK.ht || WK.sat === 'outing' || WK.sun === 'outing');
    function atWork(s, d, ff, endOfLeg) {
      const workMin = d * DAY + BACK - t.clock;
      if (MODE === 'work' && (t.b < 80 || (d === lastOffice && longWkd && t.b < 95))) {
        const b0 = t.b, to = Math.min(100, t.b + workMin / 60 * K.AC_PCT_PER_H);
        const stop = Op.own ? { icon: '⚡', title: '公司的充電樁', line: `上班時插著慢充 ${Math.round(b0)}% → ${Math.round(to)}%`, tone: 'charge', key: 'office', walkIn: !ff && walk('dad', 'to', Wk), walkOut: !ff && walk('dad', 'from', Wk) }
          : officeStop(Op, b0, to, ff ? null : Wk);
        const i = ff ? mStay(endOfLeg, 4, { min: workMin, toBat: to, state: '充電中', ff, leg: s.legI, stop })
          : St(endOfLeg, { dur: 8, min: workMin, toBat: to, orbit: { range: 430 * near, pitch: -30 }, state: '充電中', leg: s.legI, stop });
        charges++;
        t.cue(i, ff ? 0.05 : 0.1, charges === 1 ? (Op.own ? '上班的時候插著公司的充電樁，下班就充好了。' : `公司附近有 ${ctx.nearWork.total} 個 bZ4X 能用的充電站，上班的時候插著慢充。`) : `${DAYS[d]}在公司再充一次，充到 ${Math.round(to)}%。`, ff ? 4 : 6);
        return i;
      }
      if (ff) return mStay(endOfLeg, 0.5, { min: workMin, state: '停車中', ff, leg: s.legI });
      const i = St(endOfLeg, { dur: 6.5, min: workMin, orbit: { range: 600 * near, pitch: -34 }, state: '停車中', leg: s.legI, stop: parkStop(WORK, Wk) });
      t.cue(i, 0.1, '白天車子停在公司。');
      return i;
    }
    // 「都不能充」：電量低於 30% 就順路去家附近的快充（快轉時畫出來）
    function topUpFF(d, ff) {
      if (MODE !== 'public' || !topK || t.b >= 30) return;
      mDrive(topK[0], { ff });
      const from = t.b, m = Math.max(5, (80 - from) / K.DC_PCT_PER_MIN);
      const i = mStay(end(topK[0]), 4, { min: m, toBat: 80, state: '充電中', ff, leg: li(topK[0]),
        stop: { icon: '⚡', title: Fp.label, line: `${DAYS[d]}晚上順路快充 ${Math.round(from)}% → 80%`, detail: chargeDetail(Fp.charger), tone: 'charge', key: 'fast' } });
      charges++;
      t.cue(i, 0.05, `${DAYS[d]}晚上電剩 ${Math.round(from)}%，順路到${Fp.label}快充 ${Math.round(m)} 分鐘。`, 4.5);
      backHome(topK[1]);
    }
    const minOf = (s, d) => s.min === 'until' ? Math.max(10, d * DAY + 15 * 60 + 40 - t.clock) : (s.min || 5);

    // ---------- 週一（或「你的一天」）：低空跟車，完整看一次 ----------
    const mon = plans[0], monUse0 = t.used;
    const desc = [];
    if (mon.ty === 'office') desc.push('上班'); else if (mon.ty === 'roam') desc.push('跑客戶');
    if (am && S) desc.push('送小孩'); if (pm && S) desc.push('接小孩');
    mon.trips.forEach(tr => tr.seq.forEach(s => { if (XINFO[s.act] && s.act !== 'cram' && !desc.includes(XINFO[s.act].line.split('・')[0])) desc.push(XINFO[s.act].line.split('・')[0]); }));
    if (mon.trips.some(tr => tr.seq.some(s => s.act === 'cram'))) desc.push('補習班接小孩');
    let monEnd = null, monLeg = 0, saidGas = false, pendingHome = false, saidShort = false, saidMaint = false;
    if (!mon.trips.length) {
      t.clock = 9 * 60;
      const i = St(START, { dur: 7, min: 9 * 60, orbit: { range: 1200 * near, pitch: -42 }, state: '停在家', chapter: dayOnly ? '在家' : '週一', leg: 0,
        stop: { icon: '🏠', title: '家', line: '平常的日子・車子停在家', tone: 'home', key: 'home', hideCar: false } });
      t.cue(i, 0.05, dayOnly ? homeLine() : `這是你的一週。${homeLine()}`, 7.5); homeLineSaid = true;
      monEnd = START;
    }
    mon.trips.forEach((tr, ti) => {
      const seq = tr.seq, lastTrip = ti === mon.trips.length - 1;
      t.clock = Math.max(t.clock, tr.at);
      if (seq[0].pl === Hp) {
        const kidsOut = seq.some(s => s.act === 'drop') ? ['dad', 'son'] : 'dad';
        const i0 = St(rt(seq[1].leg).coords[0], { dur: ti ? 4.5 : 5, orbit: { range: 1200 * near, pitch: -42 }, state: '停在家', chapter: ti ? null : (dayOnly ? '出門' : '週一'), leg: li(seq[1].leg), flyIn: ti ? 2.2 : undefined,
          stop: { hideCar: false, walkOut: walk(kidsOut, 'from', H) } });
        if (!ti) {
          t.cue(i0, 0.05, dayOnly ? `早上 ${hhmm(t.clock)}，你從${HOME.name}出發${mon.ty === 'office' ? '去上班' : ''}。` : `這是你的一週。先看週一：${desc.join('、')}。`);
          if (mon.ty === 'home') pendingHome = true;   // 「平常在家的日子…」放在第一段路上說
        } else t.cue(i0, 0.1, `${hhmm(t.clock)}，再出門一趟。`, 3.5);
      }
      for (let j = 1; j < seq.length; j++) {
        const s = seq[j], k = s.leg, r = rt(k), toHome = s.pl === Hp;
        if (toHome && !lastTrip) { backHome(k); continue; }   // 中間回家那一小段不播（下一幕就從家裡出發），里程、電量照算
        s.legI = li(k);
        const fromOffice = seq[j - 1].pl === Op && Op, ffHome = !fromOffice && toHome && r.km >= 5;
        const o = r.km >= (s.act === 'work' || fromOffice || ffHome ? 2 : 3) ? { cam: hiCam(r.km, fromOffice || ffHome ? 6500 : 5000), pace: { sigma: 0.12, sigmaMax: fromOffice || ffHome ? 0.34 : 0.3, maxDur: fromOffice ? 19 : ffHome ? 15 : 18 }, ff: fromOffice ? '⏩ 下班路上' : ffHome ? '⏩ 回家路上' : null }
          : { pace: { sigma: 0.12, minDur: 4.5, maxDur: 7 } };
        if (s.act === 'work') o.chapter = dayOnly ? '上班' : null;
        if (fromOffice) o.chapter = dayOnly ? '下班' : null;
        const iD = D(k, o);
        if (pendingHome) { t.cue(iD, 0.08, homeLine(), 6.5); pendingHome = false; homeLineSaid = true; }
        else if (s.act === 'work') {
          t.cue(iD, 0.12, `${dayOnly ? '到公司' : '每天上班'}單程 ${r1(r.km)} 公里，塞車、開冷氣都算進去。`);
          if (dayOnly) { t.cue(iD, 0.5, gasLine(r.km)); saidGas = true; }
        } else if (fromOffice && j === 1) t.cue(iD, 0.04, '下班囉，回程阿電幫你快轉。');
        else if (dayOnly && !saidGas && r.km >= 3) { t.cue(iD, 0.3, gasLine(r.km)); saidGas = true; }
        else if (ffHome) t.cue(iD, 0.05, `這一天到現在開了 ${r1(t.km)} 公里，用掉 ${pctTxt(t.used - monUse0)}% 的電。回家的路阿電幫你快轉。`, 6);
        else if (!saidShort && j >= 2 && r.km >= 1 && r.km < 3) { t.cue(iD, 0.1, `市區短程很省電：這一段 ${r1(r.km)} 公里，只用掉 ${pctTxt(t.lastUsed)}% 的電。`, 5.5); saidShort = true; }
        else if (dayOnly && !saidMaint && j >= 2) { t.cue(iD, 0.1, maintLine, 6); saidMaint = true; }
        if (s.act === 'work') { atWork(s, 0, null, last(r.coords)); continue; }
        if (toHome) { monEnd = last(r.coords); monLeg = li(k); continue; }
        const m = minOf(s, 0), card = stopCard(s, mon.ty);
        const i = St(last(r.coords), { dur: card && card.hideCar === false ? 5.5 : s.act === 'client' && seq.findIndex(x => x.act === 'client') !== j ? 5 : 6.5, min: m, orbit: { range: 520 * near, pitch: -36 }, state: s.act === 'pick' || s.act === 'drop' || s.act === 'cram' ? '接送中' : '停車中', leg: li(k), stop: card });
        seen.add(s.act);
        if (s.act === 'drop') t.cue(i, 0.05, `早上先送小孩到${s.pl.label}` + (mon.ty === 'office' ? '，再去上班。' : mon.ty === 'roam' ? '，再去拜訪客戶。' : '。'));
        else if (s.act === 'pick') t.cue(i, 0.05, mon.ty === 'office' ? `下班順路到${s.pl.label}接小孩。` : `下午到${s.pl.label}接小孩，來回 ${r1(r.km + (seq[j + 1] ? rt(seq[j + 1].leg).km : r.km))} 公里。`);
        else if (s.act === 'client') { const n = seq.filter((x, q) => q <= j && x.act === 'client').length;
          if (n === 1) t.cue(i, 0.05, `今天去拜訪 ${R.length} 個客戶，都在${U.hasWork ? WORK.name : HOME.name}附近。`, 5.5);
          else if (n === 2) t.cue(i, 0.05, '停在客戶那裡的時候，車子不耗電；冷氣只在開車時才算。', 5); }
        else if (XINFO[s.act]) t.cue(i, 0.08, XINFO[s.act].say(s.pl));
      }
    });
    const monUse = t.used - monUse0;
    // 週一晚上回到家
    if (mon.trips.length) {
      const morning = DAY + 7 * 60 + 20, kid = kids ? ['dad', 'son'] : 'dad';
      if (MODE === 'home' && (dayOnly || t.b < 60)) {
        const bArr = t.b, i = St(monEnd, { dur: dayOnly ? 15 : 6, min: Math.max(0, morning - t.clock), toBat: 100, orbit: { range: 650 * near, pitch: -34 }, state: '充電中', chapter: dayOnly ? '在家充電' : null, leg: monLeg,
          stop: { icon: '🏠', title: '家裡的充電樁', line: `插上充電線・睡一覺 ${Math.round(bArr)}% → 100%`, tone: 'home', key: 'home', walkIn: walk(kid, 'to', H) } });
        charges++;
        t.cue(i, 0.1, '回家插上充電線，睡一覺，電就滿了。');
        if (dayOnly) t.cue(i, 0.45, `在家充電一度大約 ${K.HOME_NT_PER_KWH} 元，這一天的電費大約 NT$${Math.round(monUse / 100 * K.BATTERY_KWH * K.HOME_NT_PER_KWH)}。`, 7);
      } else {
        const i = St(monEnd, { dur: dayOnly ? 9 : 7.5, min: dayOnly ? 5 : Math.max(0, morning - t.clock), orbit: { range: 900 * near, pitch: -38, to: cur }, state: '停在家', chapter: dayOnly ? '到家' : null, leg: monLeg,
          stop: { icon: '🏠', title: '家', line: dayOnly ? `到家了・電還有 ${Math.round(t.b)}%` : `週一開完・用掉 ${pctTxt(monUse)}% 的電`, tone: 'home', key: 'home', walkIn: walk(kid, 'to', H) } });
        t.cue(i, 0.15, dayOnly ? `今天開了 ${r1(t.km)} 公里，冷氣、塞車都算進去，一共用了 ${pctTxt(monUse)}% 的電。` : `開冷氣、遇到塞車，這一天大約用掉 ${pctTxt(monUse)}% 的電。`, dayOnly ? 7 : 4.5);
      }
    }
    if (dayOnly) {
      const price = priceOf(), kmDay = t.km;
      const pubLine = MODE === 'public' && Fp;
      const i = St(monEnd || START, { dur: pubLine ? 13 : 8, min: 10, orbit: { range: 900 * near, pitch: -38 }, state: '停在家', chapter: null, leg: monLeg, flyIn: 1 });
      t.cue(i, 0.05, `一次加油站都沒去，少排了 ${r1(kmDay * K.CO2_PER_KM)} 公斤 CO₂。`, 6);
      if (pubLine) t.cue(i, 0.5, `家裡、公司都不能充也沒關係：一週去${Fp.label}快充一次就夠了。`, 6);
      const yr = mon.ty === 'office' ? `（只算上班日）` : '（以每週五天估）';
      return { raw: t.raw, cues: t.cues, places, legs: legsOf(RT), kmTotal: kmDay, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
        label: '今天', firstDay: 0, excluded: ctx.excluded,
        title: MODE === 'home' ? '你的一天（家裡可以充電）' : MODE === 'work' ? '你的一天（公司可以充電）' : '你的一天（家裡、公司都不能充）',
        sub: `${desc.join('、') || '在家'}：這一天開 ${r1(kmDay)} 公里。`,
        co2Line: `一年約等於 ${Math.round(kmDay * K.WORKDAYS * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量${yr}`,
        saveLine: `一年約省 NT$ ${Math.round(kmDay * K.WORKDAYS * savePerKm(price)).toLocaleString()}${yr}`, preload: { maxMs: 3500 } };
    }

    // ---------- 週二～週五：高空快轉 ----------
    const ff = `⏩ ${ffRange} 快轉`;
    const restTrips = plans.slice(1).some(p => p.trips.length);
    for (let d = 1; d < plans.length; d++) {
      const pl = plans[d];
      t.clock = Math.max(t.clock, d * DAY + 7 * 60);
      let firstSeg = null;
      pl.trips.forEach(tr => {
        const seq = tr.seq;
        t.clock = Math.max(t.clock, d * DAY + tr.at);
        for (let j = 1; j < seq.length; j++) {
          const s = seq[j], k = s.leg; s.legI = li(k);
          const iD = mDrive(k, Object.assign({ ff, chapter: firstSeg == null && d === 1 ? ffRange : null }, firstSeg == null && d === 1 ? { flyIn: 3.5 } : {}));   // 11/13：從週一的近景慢慢飛到高空全景
          if (firstSeg == null) firstSeg = iD;
          if (s.act === 'work') { atWork(s, d, ff, end(k)); continue; }
          if (s.pl === Hp) { mStay(end(k), 0.3, { min: 0, state: '停在家', ff, leg: li(k) }); continue; }
          const m = minOf(s, d), first = !seen.has(s.act);
          const card = first ? stopCard(s, pl.ty) : null;
          if (card) { card.walkIn = undefined; card.walkOut = undefined; }
          const i = mStay(end(k), card ? 3 : 0.4, { min: m, state: '停車中', ff, leg: li(k), stop: card || undefined });
          if (first) { seen.add(s.act); if (XINFO[s.act] && d > 1) t.cue(i, 0.05, `${DAYS[d]}：` + XINFO[s.act].say(s.pl), 3.2); }   // 週二：快轉開頭的台詞還在說，只跳資訊卡
        }
      });
      if (d === 1 && firstSeg != null) {
        const later = workDays.filter(x => x), offTxt = anchor === 'office' && workDays.length < 5 ? (later.length ? `${later.map(x => DAYS[x]).join('、')}去公司，其他天在家。` : '都在家。') : '';
        const hl = !homeLineSaid && plans.slice(1).some(p => p.ty === 'home');
        t.cue(firstSeg, 0.05, (offTxt ? `週二到週五${offTxt === '都在家。' ? '' : '：'}${offTxt}` : lastD > 4 ? `${ffRange.replace('～', '到')}都要上班，都差不多。` : '週二到週五都差不多。') + (hl ? homeLine() : '阿電幫你快轉。'), hl ? 7.5 : 4.5);
        if (hl) homeLineSaid = true;
      }
      // 晚上
      const morning = (d + 1) * DAY + 7 * 60 + 20, lastLeg = t.raw.length ? t.raw[t.raw.length - 1].leg : 0;
      const atH = pl.trips.length ? end(last(pl.trips).seq[last(pl.trips).seq.length - 1].leg) : START;
      if (MODE === 'home' && ((d === 2 || d === 4) && t.b < 90 || t.b < 50 || (d === 4 && longWkd && t.b < 97))) {
        const bArr = t.b, i = mStay(atH, 4, { min: Math.max(0, morning - t.clock), toBat: 100, state: '充電中', ff, leg: lastLeg,
          stop: { icon: '🏠', title: '家', line: `${DAYS[d]}晚上插著充電・${Math.round(bArr)}% → 100%`, tone: 'home', key: 'home' } });
        charges++;
        t.cue(i, 0.12, charges === 1 ? `${DAYS[d]}晚上在家插著，睡一覺就滿了。` : `${DAYS[d]}晚上再插一次。`, 3.6);
      } else if (d === lastD && restTrips) {
        topUpFF(d, ff);
        const i = mStay(atH, 4, { min: 60, state: '停在家', ff, leg: lastLeg, stop: { icon: '🏠', title: '家', line: `週五晚上・電還有 ${Math.round(t.b)}%`, tone: 'home', key: 'home' } });
        t.cue(i, 0.05, `到週五晚上，電還有 ${Math.round(t.b)}%。`, 3.8);
      } else if (pl.trips.length) { topUpFF(d, ff); mStay(atH, 0.3, { min: Math.max(0, morning - t.clock), state: '停在家', ff, leg: lastLeg }); }
      else t.clock = morning;
    }

    // ---------- 週末 ----------
    const startOf = k => rt(k).coords[0];
    let pubCharged = false, arriveCard = null;
    // 「都不能充」、週末又沒有去百貨或出遠門：週六早上買早餐的時候，在家附近快充一次
    const longNeed = !longWkd ? 0 : WK.ht ? usePct(rt(wkdNeed.htGo).km * 2, rt(wkdNeed.htGo).minutes * 2) : usePct(rt(wkdNeed.outGo).km * 2, rt(wkdNeed.outGo).minutes * 2);
    const needSatTop = MODE === 'public' && WK && WK.sat !== 'work' && topK && charges === 0 && (longWkd ? t.b < Math.min(80, longNeed + 25) : !(Bp && Bp.charger && wkdHas('mall')));
    function satTopUp() {
      t.clock = 5 * DAY + 8 * 60 + 30;
      const i0 = St(startOf(topK[0]), { dur: 4.5, orbit: { range: 900 * near, pitch: -40 }, state: '停在家', chapter: '週六', leg: li(topK[0]), flyIn: 4.6, stop: { hideCar: false, walkOut: walk('dad', 'from', H) } });
      t.cue(i0, 0.08, '週六早上，順路去快充一次。');
      D(topK[0], { rush: false, pace: { sigma: 0.12, minDur: 6, maxDur: 10 } });
      const from = t.b, m = Math.max(5, (80 - from) / K.DC_PCT_PER_MIN);
      const i = St(end(topK[0]), { dur: 12, min: m, toBat: 80, orbit: { range: 600 * near, pitch: -55 }, state: '充電中', chapter: '快充', leg: li(topK[0]),
        stop: { icon: '⚡', title: Fp.label, line: `買早餐的 ${Math.round(m)} 分鐘・快充 ${Math.round(from)}% → 80%`, detail: chargeDetail(Fp.charger), tone: 'charge', key: 'fast', walkIn: walk('dad', 'to', Fp.p), walkOut: walk('dad', 'from', Fp.p) } });
      charges++; pubCharged = true;
      t.cue(i, 0.12, `家附近有 ${ctx.nearHome.total} 個 bZ4X 能用的充電站。買個早餐的 ${Math.round(m)} 分鐘，電就從 ${Math.round(from)}% 充到 80%。`, 7);
      t.cue(i, 0.72, '一週充這一次就夠了。', 3.3);
      backHome(topK[1]);
    }
    function localDay(kind, d, first, chap) {
      const dayName = DAYS[d];
      if (kind === 'quiet' || kind === 'home' || (kind === 'mall' && !wkdNeed.mall) || (kind === 'park' && !wkdNeed.park)) {
        t.clock = Math.max(t.clock, d * DAY + 10 * 60);
        const i = St(START, { dur: 5, min: 60, orbit: { range: 1000 * near, pitch: -40 }, state: '停在家', chapter: chap, leg: 0, flyIn: first ? 4 : 2.5,
          stop: { icon: '🏠', title: '家', line: `${dayName}在家休息・車子不用動`, tone: 'home', key: 'home', hideCar: false } });
        t.cue(i, 0.1, `${dayName}在家休息，車子不用動。`, 4);
        return;
      }
      const isMall = kind === 'mall', k = isMall ? wkdNeed.mall : wkdNeed.park, pl = isMall ? Bp : Kp;
      t.clock = Math.max(t.clock, d * DAY + (isMall ? 10 * 60 + 30 : 9 * 60 + 30));
      const i0 = St(startOf(k), { dur: 5.5, orbit: { range: 900 * near, pitch: -40 }, state: '停在家', chapter: chap, leg: li(k), flyIn: first ? 4.6 : 2.5, stop: { hideCar: false, walkOut: walk(who, 'from', H) } });
      t.cue(i0, 0.08, isMall ? `${dayName}，${kids ? '全家' : ''}去${pl.label}逛逛。` : `${dayName}，${kids ? '全家' : ''}去${pl.label}走走。`);
      D(k, { rush: false, pace: { sigma: 0.12, minDur: 6, maxDur: 11 } });
      const P0 = pl.p;
      if (isMall && MODE === 'public' && pl.charger && !pubCharged && t.b < 55) {
        const from = t.b, m = Math.max(5, (80 - from) / K.DC_PCT_PER_MIN);
        const i = St(end(k), { dur: 14, min: 120, toBat: 80, orbit: { range: 600 * near, pitch: -55 }, state: '充電中', chapter: '逛街＋快充', leg: li(k),
          stop: { icon: '🛍️', title: pl.label, line: `逛街、吃飯・順便快充 ${Math.round(from)}% → 80%`, detail: chargeDetail(pl.charger), note: EST_NOTE, tone: 'charge', key: 'mall', walkIn: walk(who, 'to', P0), walkOut: walk(who, 'from', P0) } });
        charges++; pubCharged = true;
        t.cue(i, 0.15, `逛街、吃飯的時候插著，${Math.round(m)} 分鐘，電就從 ${Math.round(from)}% 充到 80%。`, 7);
        t.cue(i, 0.66, '這一週，就充這一次。', 4);
      } else {
        const i = St(end(k), { dur: 9, min: isMall ? 120 : 150, orbit: { range: 600 * near, pitch: isMall ? -55 : -50 }, state: '停車中', chapter: isMall ? '逛街' : null, leg: li(k),
          stop: { icon: pl.icon, title: pl.label, line: isMall ? (kids ? '全家逛街、吃飯' : '逛街、吃飯') : (kids ? '全家到公園走走' : '到公園走走'), detail: pl.charger ? chargeDetail(pl.charger) : undefined, note: EST_NOTE, key: pl.key, walkIn: walk(who, 'to', P0), walkOut: walk(who, 'from', P0) } });
        t.cue(i, 0.15, isMall ? `電還有 ${Math.round(t.b)}%，不用特別充。` + (pl.charger && pl.charger.bz4x_dc ? `想充的話，這裡有 ${pl.charger.bz4x_dc} 支快充。` : '')
          : pl.charger ? '公園的停車場也有充電站，想充隨時可以充。' : `電還有 ${Math.round(t.b)}%，不用特別充。`, 6);
      }
      backHome(k);
    }
    // 出遠門（回老家、出遊）：高速公路快充站（跟三天兩夜一樣），只有電不夠才停
    let fw = null;
    if (longWkd) fw = await ctx.api('api/ev/freeway').then(r => onlyUsable(r, ctx.counter).stations.filter(s => s.fast)).catch(() => []);
    const kit = longWkd ? longKit(ctx, t, places, fw) : null;
    function legCue(go, km, to) {
      if (go.stopInfo) {
        const x = go.stopInfo;
        t.cue(x.i, 0.05, x.needed ? `開了 ${x.hours} 小時，在${x.s.name}休息。上個廁所、買杯咖啡，電就從 ${Math.round(x.from)}% 充到 ${Math.round(x.to)}%。`
          : `電其實夠開到${to}。在${x.s.name}休息喝杯咖啡，順便充 ${x.m} 分鐘。`, 8);
        charges++; pubCharged = true;
      } else t.cue(go.i1, 0.75, `${Math.round(km)} 公里一路開到，不用中途充電。`, 5);
    }
    async function outingDay(d, first, chap) {
      const go = rt(wkdNeed.outGo), back = rt(wkdNeed.outBack);
      t.clock = Math.max(t.clock, d * DAY + 9 * 60);
      const i0 = St(go.coords[0], { dur: 5, orbit: { range: 1500, pitch: -45 }, state: '停在家', chapter: chap, leg: li(wkdNeed.outGo), flyIn: first ? 4.6 : 2.5, stop: { hideCar: false, walkOut: walk(who, 'from', H) } });
      t.cue(i0, 0.08, `${DAYS[d]}去${OU.label}走走，單程 ${Math.round(go.km)} 公里，當天來回。`);
      const g = await kit.longLeg(go, li(wkdNeed.outGo), '出遊', nightOf(t.clock), null, { who, onlyNeeded: true, maxDur: 18, stopChapter: null });
      legCue(g, go.km, OU.label);
      const i = St(last(go.coords), { dur: 8, min: 180, orbit: { range: 1200, pitch: -42 }, state: '出遊中', leg: li(wkdNeed.outGo),
        stop: { icon: '📸', title: OU.label, line: kids ? '全家下車走走、拍照' : '下車走走、拍照', note: OU.est ? '景點為阿電依住家距離推估' : undefined, key: 'outing', walkIn: walk(who, 'to', OU.p), walkOut: walk(who, 'from', OU.p) } });
      t.cue(i, 0.1, `到了，電還有 ${Math.round(t.b)}%。`, 4);
      const r = await kit.longLeg(back, li(wkdNeed.outBack), null, nightOf(t.clock), '⏩ 回程快轉', { who, onlyNeeded: true, flyIn: 3.5 });
      t.cue(r.i1, 0.02, '回程阿電幫你快轉。', 3.5);
      if (r.stopInfo) { t.cue(r.stopInfo.i, 0.03, `回程在${r.stopInfo.s.name}休息 ${Math.round(r.stopInfo.m)} 分鐘，順便充電。`, 5); charges++; pubCharged = true; }
      arriveCard = { icon: '🏠', title: '到家', line: `來回 ${Math.round(go.km + back.km)} 公里・電還剩 ${Math.round(t.b)}%`, tone: 'home', key: 'home', hideCar: false };
    }
    async function hometown() {
      const go = rt(wkdNeed.htGo), back = rt(wkdNeed.htBack);
      t.clock = Math.max(t.clock, 5 * DAY + 9 * 60);
      const i0 = St(go.coords[0], { dur: 5, orbit: { range: 1500, pitch: -45 }, state: '停在家', chapter: needSatTop ? null : '週六', leg: li(wkdNeed.htGo), flyIn: 4.6, stop: { hideCar: false, walkOut: walk(who, 'from', H) } });
      t.cue(i0, 0.08, `週六回${HT.label}，單程 ${Math.round(go.km)} 公里，電還有 ${Math.round(t.b)}%。`, 6);
      const g = await kit.longLeg(go, li(wkdNeed.htGo), '回老家', 0, null, { who, onlyNeeded: true, maxDur: 20, stopChapter: null });
      t.cue(g.i1, 0.12, `沿路有 ${g.count} 個 bZ4X 能用的高速公路快充站，阿電都幫你標好了。`, 5.5);
      legCue(g, go.km, HT.label);
      const arr = t.b, needBack = usePct(back.km, back.minutes) + 20;
      let i = St(last(go.coords), { dur: 6, min: Math.max(0, 5 * DAY + 18 * 60 - t.clock), orbit: { range: 1400, pitch: -42 }, state: '停車中', chapter: HT.label, leg: li(wkdNeed.htGo),
        stop: { icon: '🏡', title: HT.label, line: `到了・電還有 ${Math.round(arr)}%`, key: 'ht', walkIn: walk(who, 'to', HT.p) } });
      t.cue(i, 0.1, `到老家了，電還有 ${Math.round(arr)}%。`, 4.5);
      const nb = nearHT ? nearHT.total : 0;
      if (t.b < needBack && nb) {
        i = St(last(go.coords), { dur: 6, min: Math.max(0, 6 * DAY + 8 * 60 - t.clock), toBat: 100, orbit: { range: 1300, pitch: -40, turn: 25 }, state: '充電中', chapter: null, leg: li(wkdNeed.htGo), flyIn: 1.2,
          stop: { icon: '⚡', title: '老家附近的充電站', line: `晚上停車順便充・${Math.round(t.b)}% → 100%`, tone: 'charge', key: 'ht', hideCar: false } });
        charges++; pubCharged = true;
        t.cue(i, 0.08, `老家附近有 ${nb} 個 bZ4X 能用的充電站，晚上停車順便充，隔天又是滿的。`, 6);
      } else {
        i = St(last(go.coords), { dur: 5, min: Math.max(0, 6 * DAY + 8 * 60 - t.clock), orbit: { range: 1300, pitch: -40, turn: 25 }, state: '停車中', chapter: null, leg: li(wkdNeed.htGo), flyIn: 1.2,
          stop: { icon: '🌙', title: '在老家過夜', line: t.b >= needBack ? `電還有 ${Math.round(t.b)}%・夠開回家` : '回程在休息站充一下', key: 'ht', hideCar: false } });
        t.cue(i, 0.08, t.b >= needBack ? `電還有 ${Math.round(t.b)}%，開回家也夠，不用特別充。` : '回程在高速公路休息站充一下就好。', 5);
      }
      t.clock = 6 * DAY + 9 * 60 + 30;
      if (P2) {
        const k = wkdNeed.p2, r = rt(k);
        const s0 = St(r.coords[0], { dur: 4.5, orbit: { range: 1000 * near, pitch: -42 }, state: '停車中', chapter: '週日', leg: li(k), flyIn: 1.5, stop: { hideCar: false, walkOut: walk(who, 'from', HT.p) } });
        t.cue(s0, 0.08, `週日早上，在老家附近的${P2.label}${P2.kind === 'mall' ? '逛逛' : '走走'}，下午再開回家。`, 5.5);
        D(k, { rush: false, pace: { sigma: 0.12, minDur: 5, maxDur: 7 } });
        St(last(r.coords), { dur: 6, min: 150, orbit: { range: 600 * near, pitch: -50 }, state: '停車中', leg: li(k),
          stop: { icon: P2.icon, title: P2.label, line: kids ? '全家走走' : '走走、吃個午餐', note: EST_NOTE, key: 'p2', walkIn: walk(who, 'to', P2.p), walkOut: walk(who, 'from', P2.p) } });
      } else {
        const s0 = St(back.coords[0], { dur: 4.5, orbit: { range: 1300, pitch: -42 }, state: '停車中', chapter: '週日', leg: li(wkdNeed.htBack), flyIn: 2, stop: { hideCar: false, walkOut: walk(who, 'from', HT.p) } });
        t.cue(s0, 0.08, '週日下午，開回家。', 3.5);
      }
      t.clock = Math.max(t.clock, 6 * DAY + 15 * 60);
      const r = await kit.longLeg(back, li(wkdNeed.htBack), null, 0.1, '⏩ 回程快轉', { who, onlyNeeded: true, flyIn: 3.5 });
      t.cue(r.i1, 0.02, '回程阿電幫你快轉。', 3.5);
      if (r.stopInfo) { t.cue(r.stopInfo.i, 0.03, `回程在${r.stopInfo.s.name}休息 ${Math.round(r.stopInfo.m)} 分鐘，順便充電。`, 5); charges++; }
      arriveCard = { icon: '🏠', title: '到家', line: `回老家來回 ${Math.round(go.km + back.km + (P2 ? rt(wkdNeed.p2).km : 0))} 公里・電還剩 ${Math.round(t.b)}%`, tone: 'home', key: 'home', hideCar: false };
    }
    if (needSatTop) satTopUp();
    if (WK.ht) await hometown();
    else {
      for (const [d, kind] of [[5, WK.sat], [6, WK.sun]]) {
        if (kind === 'work') continue;   // 週末上班：已經在快轉裡開過了
        const first = (d === 5 || WK.sat === 'work') && !needSatTop, chap = d === 5 && needSatTop ? null : DAYS[d];
        if (kind === 'outing') await outingDay(d, first, chap);
        else if (kind === 'quiet' && d === 6 && WK.sat === 'home') continue;   // 兩天都在家：只放一張卡
        else localDay(kind, d, first, chap);
      }
    }

    // ---------- 總結（週日晚上，回到高空）：「其他行程」只算數字，不畫在地圖上 ----------
    t.clock = Math.max(t.clock, 6 * DAY + 17 * 60);
    const price = priceOf(), okm = Math.max(0, Math.min(600, U.okm || 0));
    const okmUse = okm ? usePct(okm, okm * 2) : 0;
    const sumAt = WK.ht || wkdNeed.outGo ? H : ctr;
    const iSum = St(sumAt, { dur: okm ? 12.5 : 10, flyIn: WK.ht || wkdNeed.outGo ? 3.5 : undefined, min: 120, car: START, useKm: okm, useMin: okm * 2, orbit: { range: WK.ht || wkdNeed.outGo ? Math.max(AR, 6000) : AR, pitch: APITCH, from: head - 6, to: head + 2 }, state: '停在家', chapter: '總結', leg: 0, stop: arriveCard || undefined });
    void okmUse;
    let at = 0.03;
    if (okm) { t.cue(iSum, at, `其他行程每週大約 ${Math.round(okm)} 公里，也算進去了。`, 4); at = 0.37; }
    if (t.km < 1) t.cue(iSum, at, `這一週車子幾乎都停在家，電還有 ${Math.round(t.b)}%，不用充電，也不用去加油站。`, 6);
    else t.cue(iSum, at, charges ? `這一週開了 ${Math.round(t.km)} 公里，充電 ${charges} 次，一次加油站都沒去。` : (t.b < 15 ? `這一週開了 ${Math.round(t.km)} 公里。你家附近找不到 bZ4X 能用的充電站，電撐不過一整週；這種情況，阿電會老實建議你先考慮油電車。` : `這一週開了 ${Math.round(t.km)} 公里，電還有 ${Math.round(t.b)}%，一次都不用充，也不用去加油站。`), 5);
    if (t.km >= 1) t.cue(iSum, okm ? 0.76 : 0.55, `少排了 ${r1(t.km * K.CO2_PER_KM)} 公斤 CO₂，省下 NT$${Math.round(t.km * savePerKm(price))}。`, 4.5);
    const wkTxt = WK.ht ? `週末回${HT.label}` : [WK.sat, WK.sun].map((k, j) => ({ mall: '逛街', park: '去公園', outing: OU ? `去${OU.label}` : '', home: '在家', quiet: '' })[k] ? `${DAYS[5 + j]}${({ mall: '逛街', park: '去公園', outing: OU ? `去${OU.label}` : '', home: '在家' })[k]}` : '').filter(Boolean).join('、');
    const base = anchor === 'office' ? (workDays.length !== 5 ? `一週去公司 ${workDays.length} 天` : '上班') : anchor === 'roam' ? '跑客戶' : '平常在家';
    return { raw: t.raw, cues: t.cues, places, legs: legsOf(RT), kmTotal: t.km, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
      label: '這一週', firstDay: 0, excluded: ctx.excluded, charges,
      title: MODE === 'home' ? '你的一週（家裡可以充電）' : MODE === 'work' ? '你的一週（公司可以充電）' : '你的一週（家裡、公司都不能充）',
      sub: [base, kids && S ? (am && pm ? '送小孩、接小孩' : am ? '送小孩' : '接小孩') : '', ...wx.map(k => XINFO[k].line.split('・')[0]), wkTxt].filter(Boolean).join('、') + '：冷氣、塞車都算進去。',
      co2Line: `一年約等於 ${Math.round(t.km * 52 * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量`,
      saveLine: `一年約省 NT$ ${Math.round(t.km * 52 * savePerKm(price)).toLocaleString()}`,
      preload: { maxMs: 3500 } };
  }

  // ======================= 旅行（tstops：最多 3 站，家 → 第 1 站 → … → 家） =======================
  // 模擬最多 5 天：每一站到達、過夜（附近有充電站就順便充）；在同一站多住的日子，用一張卡說明「每天在當地大約開 30 公里」
  async function tripStops(ctx) {
    const { sim, HOME, U } = ctx;
    const stops = U.tstops.slice(0, 3), places = [];
    const fw = onlyUsable(await ctx.api('api/ev/freeway'), ctx.counter).stations.filter(s => s.fast);
    const near = await Promise.all(stops.map(s => ctx.api(`api/ev/nearby?lat=${s.lat}&lon=${s.lon}&radius_km=6&limit=12`).then(r => onlyUsable(r, ctx.counter)).catch(() => ({ stations: [], total: 0 }))));
    const pts = [P(HOME), ...stops.map(P), P(HOME)];
    const RT = await routes2(ctx.api, pts.slice(1).map((b, i) => [pts[i], b, i === stops.length ? 'back' : 'go']), new Set());
    sim.setLegs(legsOf(RT));
    await place(sim, places, { ...HOME, kind: 'home', icon: '🏠', label: '家', tone: 'home' });
    for (let i = 0; i < stops.length; i++) await place(sim, places, { lat: stops[i].lat, lon: stops[i].lon, kind: 'dest', icon: i === stops.length - 1 ? '🏁' : '📍', label: stops[i].name, key: 'dest' + i });
    const nights = stops.reduce((a, s) => a + s.nights, 0), days = nights + 1;
    const t = tracker(ctx, 100, 9 * 60);
    const { longLeg } = longKit(ctx, t, places, fw);
    const LOCAL_KM = 30;
    const s0 = t.stay(RT[0].coords[0], { dur: 6, orbit: { range: 3000, pitch: -50 }, state: '停在家', chapter: '出發', leg: 0, stop: { hideCar: false, walkOut: walk(FAMILY, 'from', P(HOME)) } });
    t.cue(s0, 0.1, `${cnDays(days)}天${CN[nights] || nights}夜，從${HOME.name}出發：${stops.map(s => s.name).join('、')}，總共 ${Math.round(RT.reduce((a, r) => a + r.km, 0))} 公里。`, 7);
    let simDays = 1, extraKm = 0, extraDays = 0;
    for (let i = 0; i < stops.length; i++) {
      const r = RT[i], s = stops[i];
      const g = await longLeg(r, i, i ? `到${s.name}` : '去程', nightOf(t.clock), null, { maxDur: 30, onlyNeeded: true });
      if (!i) t.cue(g.i1, 0.1, `沿路有 ${g.count} 個 bZ4X 能用的高速公路快充站，阿電都幫你標好了。`);
      if (g.stopInfo) {
        const x = g.stopInfo;
        t.cue(x.i, 0.05, x.needed ? `開了 ${x.hours} 小時，在${x.s.name}休息。上個廁所、買杯咖啡，電就從 ${Math.round(x.from)}% 充到 ${Math.round(x.to)}%。`
          : `電其實夠開到${s.name}。開了 ${x.hours} 小時，在${x.s.name}休息喝杯咖啡，順便充 ${x.m} 分鐘。`, 8);
      } else t.cue(g.i1, 0.8, `${Math.round(r.km)} 公里一路開到，不用中途充電。`);
      const at = last(r.coords), nb = near[i];
      let k = t.stay(at, { dur: 7, min: Math.max(0, (simDays - 1) * DAY + 19 * 60 - t.clock), orbit: { range: 1800, pitch: -42 }, state: '停車中', chapter: s.name, leg: i, night: [nightOf(t.clock), 0.55],
        stop: { icon: i === stops.length - 1 ? '🏁' : '📍', title: s.name, line: `到了・電還有 ${Math.round(t.b)}%`, key: 'dest' + i, hideCar: false, walkIn: walk(FAMILY, 'to', P(s)) } });
      t.cue(k, 0.1, `到${s.name}了，電還有 ${Math.round(t.b)}%。附近有 ${nb.total} 個 bZ4X 能用的充電站。`, 6.5);
      k = t.stay(at, { dur: 6, min: Math.max(0, simDays * DAY + 8 * 60 - t.clock), toBat: nb.total ? 100 : null, orbit: { range: 1500, pitch: -40, turn: 30 }, state: nb.total ? '充電中' : '停車中', chapter: null, leg: i, night: [0.6, 0.85], flyIn: 1.4,
        stop: nb.total ? { icon: '⚡', title: `在${s.name}過夜`, line: '停車順便充電・隔天又是滿的', tone: 'charge', key: 'dest' + i, hideCar: false } : { icon: '🏨', title: `在${s.name}過夜`, line: '旅館停車過夜', key: 'dest' + i, hideCar: false } });
      if (nb.total) t.cue(k, 0.08, '晚上停車順便充，隔天又是滿的。', 4.5);
      simDays++;
      // 同一站多住的日子：一張卡（每天在當地大約開 30 公里；最多模擬 5 天，超過的也算進這張卡）
      if (s.nights > 1) {
        const more = s.nights - 1, km = more * LOCAL_KM;
        extraKm += km; extraDays += more;
        t.clock = Math.max(t.clock, (simDays - 1) * DAY + 9 * 60);
        k = t.stay(at, { dur: 6.5, min: more * DAY, useKm: km, useMin: km * 2, toBat: nb.total ? 100 : null, orbit: { range: 1600, pitch: -42, turn: 25 }, state: '出遊中', chapter: `${s.name}其他天`, leg: i, night: [0, 0], flyIn: 1.6,
          stop: { icon: '📸', title: `在${s.name}的其他天`, line: `${more} 天・每天在當地大約開 ${LOCAL_KM} 公里`, note: nb.total ? '晚上停車順便充電' : undefined, key: 'dest' + i, hideCar: false } });
        t.cue(k, 0.08, `在${s.name}的其他天，每天在當地大約開 ${LOCAL_KM} 公里，${more} 天一共 ${km} 公里。`, 6);
        simDays += more;
      }
      t.clock = Math.max(t.clock, (simDays - 1) * DAY + 9 * 60 + 30);
    }
    void extraDays;
    t.clock = Math.max(t.clock, (simDays - 1) * DAY + 14 * 60);
    const back = RT[stops.length], ret = await longLeg(back, stops.length, '回程', 0.15, '⏩ 回程快轉');
    t.cue(ret.i1, 0.02, '回程一樣輕鬆，阿電幫你快轉。');
    if (ret.stopInfo) t.cue(ret.stopInfo.i, 0.03, `回程在${ret.stopInfo.s.name}休息 ${Math.round(ret.stopInfo.m)} 分鐘，順便充電。`, 5);
    const i = t.stay(last(back.coords), { dur: 13, min: 10, orbit: { range: 2400, pitch: -45 }, state: '停在家', chapter: '到家', leg: stops.length, night: [0.6, 0.65],
      stop: { icon: '🏠', title: '到家', line: `${cnDays(days)}天開了 ${Math.round(t.km)} 公里・電還剩 ${Math.round(t.b)}%`, tone: 'home', key: 'home', walkIn: walk(FAMILY, 'to', P(HOME)) } });
    const price = K.PUBLIC_NT_PER_KWH;
    t.cue(i, 0.15, `到家了，電還剩 ${Math.round(t.b)}%。`, 4.2);
    t.cue(i, 0.48, `這${cnDays(days)}天開了 ${Math.round(t.km)} 公里${extraKm ? `（含當地 ${extraKm} 公里）` : ''}，少排了 ${r1(t.km * K.CO2_PER_KM)} 公斤 CO₂，油錢省下 NT$${Math.round(t.km * savePerKm(price))}。`, 7);
    return { raw: t.raw, cues: t.cues, places, legs: legsOf(RT), kmTotal: t.km, savePerKm: savePerKm(price), elecPerKm: K.EV_KWH_PER_KM * price, fuelPerKm: K.FUEL_NT_PER_KM,
      label: '這趟旅程', firstDay: days <= 3 ? 4 : 5, excluded: ctx.excluded,
      title: `${cnDays(days)}天${CN[nights] || nights}夜：${HOME.name} → ${stops.map(s => s.name).join(' → ')}`, sub: `一共 ${Math.round(t.km)} 公里，${days <= 3 ? '週五' : '週六'}出發。`,
      co2Line: `等於 ${r1(t.km * K.CO2_PER_KM / K.TREE_KG)} 棵樹一年吸收的量`, saveLine: '跟開油車比（快充以每度 NT$8 估算）', preload: { maxMs: 3000 } };
  }

  // 建立情境：先把 bZ4X 不能用的充電站濾掉（數量記在 sc.excluded）
  async function build(name, ctx) {
    const counter = { excluded: 0 };
    const c = Object.assign({}, ctx, { counter, nearWork: onlyUsable(ctx.nearWork, counter), nearHome: onlyUsable(ctx.nearHome, counter) });
    // 網址有新參數（ctx.U）：照客戶自己的生活；沒有就是原本的情境（舊連結、測試）
    const U = ctx.U;
    const sc = U && name === 'trip' && U.tstops && U.tstops.length ? await tripStops(c)
      : U && name === 'week' ? await life2(c) : U && name === 'day' ? await life2(c, { dayOnly: true }) : await ({ day, week, trip })[name](c);
    sc.excluded = counter.excluded;
    return sc;
  }
  window.SimScenes = { K, DAYS, hhmm, r1, usePct, build, usable };
})();
