"""Render a scene of scenes_v7.html frame by frame (30 fps, 1920x1080) into an mp4, or a few stills.

  python render_scenes_v7.py WORKDIR intro|bridge|bridge_short OUT.mp4
  python render_scenes_v7.py WORKDIR intro|bridge --stills 1,3,5   -> WORKDIR/<scene>_<t>.jpg

WORKDIR must hold land.jpg (first landing frame of chat3), map0.jpg (first 2D sim frame) and dad.png
(05_brand/characters). The HTML is copied next to them so the relative image paths resolve.
"""
import os, shutil, subprocess, sys
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
W, SCENE, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
shutil.copy(os.path.join(HERE, "scenes_v7.html"), os.path.join(W, "scenes_v7.html"))
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
    pg = b.new_page(viewport={"width": 1920, "height": 1080})
    pg.goto("file://" + os.path.join(W, "scenes_v7.html") + "?scene=" + SCENE.replace("_short", "&short=1"))
    pg.wait_for_load_state("networkidle"); pg.evaluate("document.fonts.ready")
    if OUT == "--stills":
        for t in sys.argv[4].split(","):
            pg.evaluate(f"renderAt({t})"); pg.screenshot(path=os.path.join(W, f"{SCENE}_{t}.jpg"), type="jpeg", quality=85)
    else:
        dur = pg.evaluate("DURATION"); n = int(round(dur * 30))
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", "30", "-i", "-",
                               "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", OUT], stdin=subprocess.PIPE)
        for i in range(n):
            pg.evaluate(f"renderAt({i / 30})")
            ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
        ff.stdin.close(); ff.wait(); print(SCENE, n, "frames ->", OUT)
    b.close()
