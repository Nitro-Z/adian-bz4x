"""Record the 3D life simulation frame by frame (sharp tiles, no live playback).

  python record_sim.py cues  QS OUT.json            -> dump TL.cues + chapters (fast, nopre)
  python record_sim.py frames QS PLAN.json OUTDIR   -> one H.264 clip per segment, 1920x1080 @ 30 fps

QS: e.g. "scene=week&mode=public". PLAN.json: {"segs": [[a, b], ...], "mouth": "mouth.json"}.
Lip-sync: mouth.json maps cue text -> {"dur": s, "m": [mouth state per 1/30 s]}; the narrator avatar's mouth
is set per frame from the 阿電 line that plays at that moment. Uses the lab GPU (Vulkan). Never prints the key.
"""
import asyncio, json, os, subprocess, sys, time
from playwright.async_api import async_playwright

ROOT = "/home/lab/Jackie_Pham/和泰汽車黑客松/04_app"
KEY = open(f"{ROOT}/gateway/.access_key").read().strip()
BASE = "http://127.0.0.1:8080"
FPS = 30
GPU = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--enable-gpu"]
MOUTH_JS = """(s) => {
  const names = ['mouth-half', 'mouth-open', 'mouth-flat', 'mouth-o', 'mouth'];
  document.querySelectorAll('#subAvatar svg [id]').forEach(el => {
    const id = el.id;
    const m = names.find(n => id === n || (id.endsWith(n) && /[^a-z]/i.test(id[id.length - n.length - 1] || '-')));
    if (m) el.setAttribute('opacity', m === s ? '1' : '0');
  });
}"""


async def open_sim(p, qs, w=1920, h=1080):
    b = await p.chromium.launch(args=GPU)
    pg = await (await b.new_context(viewport={"width": w, "height": h})).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:200]))
    try:
        await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000)
        await pg.wait_for_timeout(1200)
    except Exception as e:
        raise SystemExit("login failed: " + type(e).__name__)
    t0 = time.time()
    await pg.goto(f"{BASE}/v2/preview/sim3d.html?{qs}")
    await pg.wait_for_function("window.READY === true", timeout=3000000, polling=2000)
    await pg.evaluate("AdianAvatar.setTTSServer(null)")
    await pg.evaluate("document.getElementById('startLayer').style.display='none'; SIM.showCar(true)")
    # the narrator bubble fades in over a few hundred ms; in a frame-by-frame recording show it at once
    await pg.add_style_tag(content="#sub { transition: none !important; }")
    print(f"ready in {time.time() - t0:.0f}s", flush=True)
    return b, pg, errs


async def main():
    mode, qs = sys.argv[1], sys.argv[2]
    async with async_playwright() as p:
        if mode == "cues":
            b, pg, errs = await open_sim(p, qs + "&nopre=1")
            data = await pg.evaluate("({dur: TL.duration, cues: TL.cues.map(c => ({at: c.at, show: c.show, text: c.text})), chapters: TL.chapters})")
            json.dump(data, open(sys.argv[3], "w"), ensure_ascii=False, indent=1)
            print("cues", len(data["cues"]), "duration", round(data["dur"], 1), "errors", errs or "none")
            await b.close(); return

        plan = json.load(open(sys.argv[3])); out = sys.argv[4]; os.makedirs(out, exist_ok=True)
        mouth = json.load(open(plan["mouth"])) if plan.get("mouth") else {}
        b, pg, errs = await open_sim(p, qs)
        cues = await pg.evaluate("TL.cues.map(c => ({at: c.at, text: c.text}))")
        json.dump(cues, open(f"{out}/cues_live.json", "w"), ensure_ascii=False, indent=1)

        def mouth_at(t):
            for c in cues:
                m = mouth.get(c["text"])
                if m and c["at"] <= t < c["at"] + m["dur"]:
                    i = int((t - c["at"]) * FPS)
                    return m["m"][min(i, len(m["m"]) - 1)]
            return "mouth"

        t_all = time.time()
        for k, (a, bnd) in enumerate(plan["segs"]):
            n = int(round((bnd - a) * FPS))
            ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS), "-i", "-",
                                   "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", f"{out}/seg{k:02d}.mp4"], stdin=subprocess.PIPE)
            late = 0
            for i in range(n):
                t = a + i / FPS
                await pg.evaluate("t => TL.renderAt(t)", t)
                ok = await pg.evaluate("SIM.waitTiles(6000)")
                if not ok: late += 1
                await pg.evaluate(MOUTH_JS, mouth_at(t))
                ff.stdin.write(await pg.screenshot(type="jpeg", quality=92))
            ff.stdin.close(); ff.wait()
            print(f"seg {k}: {a:.1f}-{bnd:.1f}s  {n} frames  tiles-late {late}  total {time.time() - t_all:.0f}s", flush=True)
        print("errors:", errs or "none")
        await b.close()

asyncio.run(main())
