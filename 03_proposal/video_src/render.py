"""Render stage.html frame by frame.

  python render.py stills 1.5,8,15 ...   -> stills/t_XXXX.jpg (review)
  python render.py full                  -> video_noaudio.mp4 (1920x1080, 30 fps, H.264)
"""
import asyncio, json, os, subprocess, sys, time
from playwright.async_api import async_playwright

V = os.path.dirname(os.path.abspath(__file__))
CH = os.path.join(V, "..", "cft", "chrome-headless-shell-linux64", "chrome-headless-shell")
TL = json.load(open(f"{V}/timeline.json"))
html = open(f"{V}/stage.html", encoding="utf-8").read().replace("__TIMELINE__", json.dumps(TL, ensure_ascii=False))
open(f"{V}/stage_built.html", "w", encoding="utf-8").write(html)

async def main():
    mode = sys.argv[1]
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or (CH if os.path.exists(CH) else None), args=["--allow-file-access-from-files", "--font-render-hinting=none"])
        pg = await b.new_page(viewport={"width": 1920, "height": 1080})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + f"{V}/stage_built.html"); await pg.wait_for_timeout(1500)
        await pg.evaluate("document.fonts.ready")
        if mode == "stills":
            os.makedirs(f"{V}/stills", exist_ok=True)
            for t in [float(x) for x in sys.argv[2].split(",")]:
                await pg.evaluate(f"render({t})")
                await pg.screenshot(path=f"{V}/stills/t_{t:07.2f}.jpg", type="jpeg", quality=85)
            print("stills ok", errs)
        else:
            fps = TL["fps"]; n = int(TL["total"] * fps)
            ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(fps), "-i", "-",
                                   "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                                   f"{V}/video_noaudio.mp4"], stdin=subprocess.PIPE)
            t0 = time.time()
            for i in range(n):
                await pg.evaluate(f"render({i / fps})")
                ff.stdin.write(await pg.screenshot(type="jpeg", quality=93))
                if i % 300 == 0: print(f"frame {i}/{n}  {time.time() - t0:.0f}s", flush=True)
            ff.stdin.close(); ff.wait()
            print("video ok", n, "frames", f"{time.time() - t0:.0f}s", errs)
        await b.close()

asyncio.run(main())
