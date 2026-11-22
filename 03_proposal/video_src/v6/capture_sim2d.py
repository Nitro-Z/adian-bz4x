"""v6: live capture of 陳先生's week in the 2D map (the same embed page the advisor opens), with 阿電's voice.

  python capture_sim2d.py OUTDIR QS SECONDS [START]   -> OUTDIR/frames/*.jpg, tap*.webm, taps.json, events.json

QS is the advisor's simUrl query (map=2d). Playback starts at t = 0 at 1x so 阿電 speaks; the screencast and the
audio tap use the same tricks as capture_chat_v6.py. Never prints the access key.
"""
import asyncio, base64, json, os, re, sys, time
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
INIT = re.search(r'INIT = """(.*?)"""', open(f"{HERE}/capture_chat_v6.py", encoding="utf-8").read(), re.S).group(1)
ROOT = "/home/lab/Jackie_Pham/和泰汽車黑客松/04_app"
KEY = open(f"{ROOT}/gateway/.access_key").read().strip()
BASE = "http://127.0.0.1:8080"
OUT, QS, SECS = sys.argv[1], sys.argv[2], float(sys.argv[3])
START = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0   # timeline second to start playing from


async def main():
    os.makedirs(f"{OUT}/frames", exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080})
        await ctx.add_init_script(INIT)
        pg = await ctx.new_page()
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        try:
            await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000); await pg.wait_for_timeout(1000)
        except Exception as e:
            raise SystemExit("login failed: " + type(e).__name__)
        await pg.goto(f"{BASE}/v2/preview/sim3d.html?{QS}&embed=1")
        await pg.wait_for_function("window.READY === true", timeout=600000, polling=1000)
        await pg.wait_for_timeout(1500)
        frames = []; cdp = await ctx.new_cdp_session(pg)
        async def on_frame(prm):
            open(f"{OUT}/frames/{len(frames):05d}.jpg", "wb").write(base64.b64decode(prm["data"])); frames.append(prm["metadata"]["timestamp"])
            try: await cdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]})
            except Exception: pass
        cdp.on("Page.screencastFrame", lambda prm: asyncio.ensure_future(on_frame(prm)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080})
        if START:
            await pg.evaluate("document.getElementById('startLayer').style.display='none'; SIM.showCar(true)")
            await pg.evaluate("t => TL.seek(t)", START); await pg.wait_for_timeout(2500)   # let the map settle at that moment
        await pg.wait_for_timeout(600)
        t_play = time.time()
        await pg.evaluate("window.postMessage({ to: 'adian-sim', type: 'play' }, location.origin)")
        tl_at = []
        while time.time() - t_play < SECS:
            await asyncio.sleep(0.5)
            tl_at.append([time.time(), await pg.evaluate("TL.time")])
        await cdp.send("Page.stopScreencast"); await asyncio.sleep(0.5)
        taps = await pg.evaluate("__stopTaps()")
        for i, tp in enumerate(taps):
            open(f"{OUT}/tap{i}.webm", "wb").write(base64.b64decode(tp["b64"])); tp.pop("b64")
        json.dump(taps, open(f"{OUT}/taps.json", "w"))
        json.dump({"frames": frames, "t_play": t_play, "start": START, "tl": tl_at, "events": [], "errors": errs}, open(f"{OUT}/events.json", "w"))
        print(f"frames {len(frames)}  taps {len(taps)}  TL reached {tl_at[-1][1]:.1f}s  errors {errs or 'none'}")
        await b.close()

asyncio.run(main())
