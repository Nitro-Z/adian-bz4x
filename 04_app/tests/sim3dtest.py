"""3D life simulation check (website_v2/preview/sim3d.html): length, 阿電 lines, motion comfort, bZ4X shown, stop cards, screenshots.
python sim3dtest.py OUTDIR NAME "scene=day&mode=work[&map=2d][&nopre=1]" [SHOTS]
  - add &nopre=1 to skip the tile preload (fast logic check; road heights are then a default, so screenshots are approximate)
  - add &map=2d for the street-map version (no Google 3D session)
  - SHOTS = screenshots, one per chapter (0 = none)
  - env GPU=1: use the lab GPU through Vulkan (much faster); default is CPU WebGL (SwiftShader) because the GPU runs Gemma/TTS/ASR
  - env VP=1600x900: viewport
Prints: preparation time, preload steps / timeouts, tiles loaded and GPU memory; duration; max screen motion sigma (target movement /
camera range per second; ~0.12 is comfortable, fast-forward parts up to ~0.35); max camera turn rate (deg/s; capped at 14);
seconds of fast-forward; every line with its start time (⚠ = overlaps the previous line); per screenshot the state, whether the
bZ4X overlay is shown (and its opacity) and the stop card text. TTS is switched off (no Gemini calls). Never prints the access key."""
import asyncio, os, sys, time
from playwright.async_api import async_playwright
KEY = open(os.path.join(os.path.dirname(__file__), "..", "gateway", ".access_key")).read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
OUT, NAME, QS = sys.argv[1], sys.argv[2], sys.argv[3]
NSHOT = int(sys.argv[4]) if len(sys.argv) > 4 else 6
W, H = (int(x) for x in os.environ.get("VP", "1600x900").split("x"))
os.makedirs(OUT, exist_ok=True)
CPU = ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"]
GPU = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--enable-gpu"]
METRICS = """(() => {
  const D = TL.duration, out = { dur: D, maxSigma: 0, maxSigmaAt: 0, maxTurn: 0, maxTurnAt: 0, ffSec: 0, batJumps: [], cards: 0 };
  const m = (a, b) => Sim3D.meters([a.lat, a.lon], [b.lat, b.lon]);
  let prev = TL.stateAt(0);
  for (let t = 0.1; t <= D; t += 0.1) {
    const s = TL.stateAt(t), v0 = prev.view, v1 = s.view;
    const sig = m(v0, v1) / Math.min(v0.range, v1.range) / 0.1;
    const turn = Math.abs(((v1.heading - v0.heading) % 360 + 540) % 360 - 180) / 0.1;
    if (sig > out.maxSigma) { out.maxSigma = sig; out.maxSigmaAt = t; }
    if (turn > out.maxTurn) { out.maxTurn = turn; out.maxTurnAt = t; }
    if (s.ff) out.ffSec += 0.1;
    if (s.card && !prev.card) out.cards++;
    if (Math.abs(s.bat - prev.bat) > 3) out.batJumps.push([+t.toFixed(1), Math.round(prev.bat), Math.round(s.bat)]);
    prev = s;
  }
  out.segs = TL.chapters.map(c => c.label + '@' + c.t.toFixed(1));
  out.pre = window.PRELOAD || null;
  out.loads = SIM.stats ? SIM.stats.loads : null;
  out.mem = SIM.memoryMB ? SIM.memoryMB() : null;
  return out;
})()"""
SHOT_STATE = """((t) => { const s = TL.stateAt(t);
  const car = [...document.querySelectorAll('#map3d canvas')].find(x => x.style.width === '480px');
  const card = document.querySelector('.sim-stop');
  return [s.chapter, s.state, Math.round(s.bat), s.km.toFixed(1), s.ff, s.cue ? s.cue.text.slice(0, 22) : '',
    car ? car.style.display + (car.style.opacity !== '' && car.style.opacity !== '1' ? ' a=' + (+car.style.opacity).toFixed(2) : '') : 'missing',
    card && card.style.display === 'flex' ? card.textContent.trim().slice(0, 40) : '']; })"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=GPU if os.environ.get("GPU") else CPU)
        pg = await (await b.new_context(viewport={"width": W, "height": H})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text[:300]}") if m.type == "error" else None)
        try:
            await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000)
            await pg.wait_for_timeout(1500)
        except Exception as e:  # never print the URL (it contains the key)
            raise SystemExit("login step failed: " + type(e).__name__)
        t0 = time.time()
        await pg.goto(f"{BASE}/v2/preview/sim3d.html?{QS}")
        await pg.wait_for_function("window.READY === true", timeout=3000000, polling=2000)
        await pg.evaluate("AdianAvatar.setTTSServer(null)")   # no Gemini TTS calls from tests
        print(f"{NAME}: prepared in {time.time() - t0:.0f}s")
        met = await pg.evaluate(METRICS)
        pre = met["pre"] or {}
        print(f"  preload steps {pre.get('steps', '-')} (timeouts {pre.get('timeouts', '-')}, {pre.get('ms', 0) / 1000:.0f}s) | tiles loaded {met['loads']} | GPU memory {met['mem']} MB")
        print(f"  duration {met['dur']:.1f}s | max sigma {met['maxSigma']:.2f}/s @ {met['maxSigmaAt']:.1f}s | "
              f"max turn {met['maxTurn']:.0f} deg/s @ {met['maxTurnAt']:.1f}s | fast-forward {met['ffSec']:.0f}s | stop cards {met['cards']}")
        print("  chapters:", " | ".join(met["segs"]))
        if met["batJumps"]:
            print("  battery jumps:", met["batJumps"][:8])
        prev_end = -1
        for at, show, text in await pg.evaluate("TL.cues.map(c => [c.at, c.show, c.text])"):
            print(f"   {at:6.1f}s ({show:.1f}) {text}{'  ⚠ overlap' if at < prev_end - 0.2 else ''}")
            prev_end = at + show
        await pg.screenshot(path=f"{OUT}/{NAME}_start.png")
        await pg.evaluate("document.getElementById('startLayer').style.display='none'; SIM.showCar(true)")
        if NSHOT:
            ts = await pg.evaluate(f"TL.chapters.map(c => c.t + 2.5).slice(0, {NSHOT})")
            for i, t in enumerate(ts):
                await pg.evaluate(f"TL.renderAt({t})")
                await pg.evaluate("SIM.waitTiles(25000)")
                await pg.wait_for_timeout(800)
                await pg.evaluate(f"TL.seek({t})")
                await pg.wait_for_timeout(400)
                st = await pg.evaluate(SHOT_STATE + f"({t})")
                await pg.screenshot(path=f"{OUT}/{NAME}_t{i}.png")
                print(f"  shot t={t:5.1f}s {st[:6]} bZ4X={st[6]} card={st[7]!r}")
        print("  JS errors:", errs[:8] or "none")
        await b.close()

asyncio.run(main())
