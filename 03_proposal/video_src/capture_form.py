"""Capture the v2 advisor (demo member B = 陳先生) in voice mode, for the demo video.

  python capture_chat.py OUTDIR

- A virtual microphone replaces getUserMedia: 陳先生's answers (customer/*.wav) are played into it while the mic
  button is held, so the real pipeline runs (Breeze-ASR-25 -> Gemma 4 -> next question).
- Voice answers: district, work, charge. If 阿電 asks the same voice question again (Gemma did not get it), the
  answer is spoken once more; a third time the button is used (FALLBACK). Other questions: the buttons a visitor sees.
- Frames: CDP screencast (JPEG + wall-clock timestamps) -> OUTDIR/frames/*.jpg.
- Audio: everything the page plays is tapped per AudioContext (OUTDIR/tap*.webm, taps.json); 陳先生's voice is logged.
- Events: when each 阿電 line appears (= starts speaking), user bubbles, 陳先生's voice, results, every /tts text
  (OUTDIR/events.json, written even if the flow fails). Never prints the access key.
"""
import asyncio, base64, json, os, sys, time
from playwright.async_api import async_playwright

ROOT = "/home/lab/Jackie_Pham/和泰汽車黑客松/04_app"
KEY = open(f"{ROOT}/gateway/.access_key").read().strip()
BASE = "http://127.0.0.1:8080"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
VOICE = {"plan": "a1_plan", "charge": "a3_charge"}   # 11/12: one sentence for the week, then charging
CLICK = {"stillOwn": "還在開", "seats": "3 到 5 人", "commuteFreq": "每天都要開", "wdays": "週一到週五", "wx": "都沒有",
         "trip": "沒有", "budget": "想看分期月付", "worry": "充電", "kids": "早上送、下午接", "wkd": "逛街、賣場、回老家", "hometown": "台中市"}
FALLBACK = {"charge": "都不行"}

INIT = """
(() => {
  const st = { ctx: null, dest: null };
  const orig = navigator.mediaDevices && navigator.mediaDevices.getUserMedia ? navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices) : null;
  navigator.mediaDevices.getUserMedia = async (c) => {
    if (c && c.audio) {
      if (!st.ctx) { st.ctx = new AudioContext({ sampleRate: 48000 }); st.dest = st.ctx.createMediaStreamDestination(); }
      if (st.ctx.state === 'suspended') { try { await st.ctx.resume(); } catch (e) {} }
      return st.dest.stream;
    }
    return orig(c);
  };
  window.__events = [];
  window.__ev = (type, text) => window.__events.push({ t: (performance.timeOrigin + performance.now()) / 1000, type, text: text || '' });
  window.__vmicPlay = async (b64, tag) => {
    const bin = Uint8Array.from(atob(b64), ch => ch.charCodeAt(0)).buffer;
    const buf = await st.ctx.decodeAudioData(bin);
    const s = st.ctx.createBufferSource(); s.buffer = buf; s.connect(st.dest); s.start();
    __ev('cust', tag);
    return buf.duration;
  };
  // Audio tap: everything the page sends to a speaker (阿電's voice, sound effects) is also recorded, per AudioContext.
  const taps = [];
  const origConnect = AudioNode.prototype.connect;
  AudioNode.prototype.connect = function (dest, ...rest) {
    const r = origConnect.call(this, dest, ...rest);
    try {
      if (dest instanceof AudioDestinationNode && this.context !== st.ctx) {
        const ctx = this.context;
        if (!ctx.__tap) {
          ctx.__tap = ctx.createMediaStreamDestination();
          // keep the recording continuous: Chrome's recorder drops silent stretches, which would squeeze the
          // timeline (audio drifts earlier than the video). A 30 Hz tone at -80 dB is inaudible but never silent.
          const keep = ctx.createOscillator(), kg = ctx.createGain();
          keep.frequency.value = 30; kg.gain.value = 0.0001;
          origConnect.call(keep, kg); origConnect.call(kg, ctx.__tap); keep.start();
          const mr = new MediaRecorder(ctx.__tap.stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 128000 });
          const rec = { mr, chunks: [], t0: 0 };
          mr.ondataavailable = e => { if (e.data && e.data.size) rec.chunks.push(e.data); };
          mr.onstart = () => { rec.t0 = (performance.timeOrigin + performance.now()) / 1000; };
          mr.start(1000);
          taps.push(rec);
        }
        origConnect.call(this, ctx.__tap);
      }
    } catch (e) {}
    return r;
  };
  window.__stopTaps = async () => {
    const out = [];
    for (const rec of taps) {
      await new Promise(res => { rec.mr.onstop = res; rec.mr.stop(); });
      const buf = await new Blob(rec.chunks, { type: 'audio/webm' }).arrayBuffer();
      let s = ''; const u = new Uint8Array(buf);
      for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
      out.push({ t0: rec.t0, b64: btoa(s) });
    }
    return out;
  };
})();
"""
HOOK = """
(() => {
  const plain = s => String(s).replace(/<br\\s*\\/?>/g, ' ').replace(/<[^>]+>/g, '');
  if (window.showSubtitle && !window.showSubtitle.__hooked) {
    const f = window.showSubtitle; window.showSubtitle = function (t) { __ev('say', plain(t)); return f.apply(this, arguments); }; window.showSubtitle.__hooked = 1;
  }
  if (window.userSay && !window.userSay.__hooked) {
    const g = window.userSay; window.userSay = function (t) { __ev('user', plain(t)); return g.apply(this, arguments); }; window.userSay.__hooked = 1;
  }
  return [typeof window.showSubtitle, typeof window.userSay];
})()
"""
READY = """(() => typeof currentKey !== 'undefined' && currentKey && pendingSpeech === 0 && !listening
  && !document.querySelector('.chat-bubble.pending') ? currentKey : null)()"""


MARKS = []
async def ev(pg, tag):
    MARKS.append({"t": time.time(), "type": "mark", "text": tag})   # wall clock (same base as the screencast timestamps)


async def run_flow(pg, t0):
    """11/13 demo: landing → 開始聊 → form → hold 🎤, 陳先生 says one sentence → Gemma fills → a few clicks → 看結果
    → verdict reveal → tour (card 1 … card 4) → open the week sim briefly."""
    await pg.wait_for_timeout(2600)
    await ev(pg, "landing_scroll")
    await pg.evaluate("window.scrollBy({ top: innerHeight * 0.9, behavior: 'smooth' })"); await pg.wait_for_timeout(1700)
    await ev(pg, "click_start")
    await pg.click(".go-btn")
    await pg.wait_for_function("typeof formOpen !== 'undefined' && formOpen", timeout=30000)
    await pg.wait_for_timeout(1800)
    print("hooks:", await pg.evaluate(HOOK), flush=True)
    await pg.evaluate("setVoice(true); fb.autoShown = true")   # no feedback questionnaire in the demo video
    await ev(pg, "form")
    await pg.wait_for_timeout(1500)
    # hold the form mic, play 陳先生's sentence into the virtual mic
    wav = open(f"{HERE}/customer/chen.wav", "rb").read()
    await ev(pg, "mic_down")
    await pg.evaluate("formMicDown()")
    await asyncio.sleep(0.5)
    dur = await pg.evaluate("([b, k]) => __vmicPlay(b, k)", [base64.b64encode(wav).decode(), "chen"])
    await asyncio.sleep(dur + 0.4)
    await pg.evaluate("micUp()"); await ev(pg, "mic_up")
    await pg.wait_for_function("(() => { const m = document.getElementById('pfAiMsg'); return m && /填了|沒找到|沒聽清楚/.test(m.textContent); })()", timeout=90000)
    await ev(pg, "filled")
    print("AI:", await pg.evaluate("document.getElementById('pfAiMsg').textContent"), flush=True)
    print("SAY:", await pg.evaluate("form.say"), flush=True)
    await pg.wait_for_timeout(4200)          # rows flash, the right column fills
    # a few clicks for what the sentence did not say
    async def click(sel, scroll=True):
        el = pg.locator(sel).first
        if await el.count() == 0: return False
        if scroll: await el.evaluate("e => e.scrollIntoView({ block: 'center', behavior: 'smooth' })"); await pg.wait_for_timeout(650)
        await el.click(); await pg.wait_for_timeout(700); return True
    f = await pg.evaluate("JSON.parse(JSON.stringify(form))")
    if not f.get("brand"): await click("[data-car='Camry']"); await click("[data-carv='Camry 汽油']", False)
    if not f.get("ownerAge"): await click(".pf-chips[data-key=ownerAge] button[data-v='40–50 歲']")
    if not f.get("carAge"): await click(".pf-chips[data-key=carAge] button[data-v='5–8 年']")
    if not f.get("seats"): await click(".pf-chips[data-key=seats] button[data-v='3 到 5 人']")
    print("form now:", await pg.evaluate("JSON.stringify({brand: form.brand, home: form.city + form.homeDistrict, anchor: form.anchor, dist: form.district, kids: form.kids, seats: form.seats, wx: form.wx, wkd: form.wkd, charge: form.charge, km: form.km})"), flush=True)
    print("missing:", await pg.evaluate("formMissing()"), flush=True)
    await pg.wait_for_timeout(800)
    await ev(pg, "submit")
    await pg.click("#pfGo")
    for _ in range(240):
        await asyncio.sleep(0.25)
        if await pg.evaluate("!document.getElementById('view3').classList.contains('hidden')"): break
        k = await pg.evaluate("currentKey")
        if k: print("follow-up:", k, flush=True); await pg.evaluate("answer('不清楚')")
    await pg.evaluate("__ev('results', '')"); MARKS.append({"t": time.time(), "type": "mark", "text": "results"}); print("results; verdict", await pg.evaluate("tour.verdict"), flush=True)
    # let the reveal + tour run through card 4 (bZ4X)
    t_res = time.time()
    while time.time() - t_res < 150:
        await asyncio.sleep(0.5)
        i = await pg.evaluate("typeof carousel !== 'undefined' ? carousel.i : -1")
        if i >= 4 or (i == 3 and not await pg.evaluate("tour.running")): break
    await pg.wait_for_timeout(1500)
    await ev(pg, "tour_done")
    # open the week sim (2D) for a few seconds to show the button + the overlay
    await pg.evaluate("stopTour && stopTour(true)"); await pg.evaluate("carouselGo(1, true)"); await pg.wait_for_timeout(1500)
    await ev(pg, "sim_click")
    await pg.click("#weekBody .sim-launch .go"); await pg.wait_for_timeout(9000)
    await ev(pg, "sim_open")


async def main():
    os.makedirs(f"{OUT}/frames", exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, permissions=["microphone"])
        await ctx.add_init_script(INIT)
        pg = await ctx.new_page()
        errs, tts = [], []
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:200]))
        def on_req(r):
            if r.url.endswith("/tts") and r.method == "POST":
                try: tts.append({"t": time.time(), "text": json.loads(r.post_data or "{}").get("text", "")})
                except Exception: pass
        pg.on("request", on_req)
        try:
            await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000)
            await pg.wait_for_timeout(1000)
        except Exception as e:
            raise SystemExit("login failed: " + type(e).__name__)
        await pg.goto(f"{BASE}/v2/index.html", wait_until="networkidle")
        await pg.wait_for_timeout(1200)
        print("hooks:", await pg.evaluate(HOOK), flush=True)

        frames = []
        cdp = await ctx.new_cdp_session(pg)
        async def on_frame(prm):
            i = len(frames)
            open(f"{OUT}/frames/{i:05d}.jpg", "wb").write(base64.b64decode(prm["data"]))
            frames.append(prm["metadata"]["timestamp"])
            try: await cdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]})
            except Exception: pass
        cdp.on("Page.screencastFrame", lambda prm: asyncio.ensure_future(on_frame(prm)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        t0 = time.time()
        status = "ok"
        try:
            await run_flow(pg, t0)
        except SystemExit as e:
            status = str(e)
        finally:
            await cdp.send("Page.stopScreencast")
            await asyncio.sleep(0.5)
            taps = await pg.evaluate("__stopTaps()")
            for i, tp in enumerate(taps):
                open(f"{OUT}/tap{i}.webm", "wb").write(base64.b64decode(tp["b64"])); tp.pop("b64")
            json.dump(taps, open(f"{OUT}/taps.json", "w"))
            ev = (await pg.evaluate("window.__events || []")) + MARKS
            json.dump({"frames": frames, "events": ev, "tts": tts, "status": status,
                       "userData": await pg.evaluate("typeof userData !== 'undefined' ? JSON.parse(JSON.stringify(userData)) : null"),
                       "simUrl": await pg.evaluate("typeof simUrl === 'function' ? simUrl() : ''"), "tourSteps": await pg.evaluate("typeof tourSteps === 'function' ? tourSteps(tour.verdict).map(s => s.text) : []")},
                      open(f"{OUT}/events.json", "w"), ensure_ascii=False, indent=1)
            print(f"status {status} | frames {len(frames)}  events {len(ev)}  tts {len(tts)}  errors {errs or 'none'}", flush=True)
        await b.close()
        if status != "ok": sys.exit(1)

asyncio.run(main())
