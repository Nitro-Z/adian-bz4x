"""v6: short screencasts of the two public pages the result card links to (official bZ4X test drive, iRent).

  python capture_tabs.py OUTDIR   -> OUTDIR/<name>/frames/*.jpg + times.json (about 6 s each, 1920x1080)
"""
import asyncio, base64, json, os, sys
from playwright.async_api import async_playwright

OUT = sys.argv[1]
PAGES = [("toyota", "https://www.toyota.com.tw/showroom/bZ4X/"), ("irent", "https://www.irentcar.com.tw/")]


async def grab(ctx, name, url):
    d = f"{OUT}/{name}/frames"; os.makedirs(d, exist_ok=True)
    pg = await ctx.new_page()
    try:
        await pg.goto(url, wait_until="networkidle", timeout=60000)
    except Exception as e:
        print(name, "load:", type(e).__name__, flush=True)
    await pg.wait_for_timeout(2500)
    cdp = await ctx.new_cdp_session(pg); times = []
    async def on_frame(prm):
        open(f"{d}/{len(times):05d}.jpg", "wb").write(base64.b64decode(prm["data"])); times.append(prm["metadata"]["timestamp"])
        try: await cdp.send("Page.screencastFrameAck", {"sessionId": prm["sessionId"]})
        except Exception: pass
    cdp.on("Page.screencastFrame", lambda prm: asyncio.ensure_future(on_frame(prm)))
    await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 90, "maxWidth": 1920, "maxHeight": 1080})
    await pg.wait_for_timeout(1500)
    await pg.evaluate("window.scrollBy({ top: 320, behavior: 'smooth' })")
    await pg.wait_for_timeout(4500)
    await cdp.send("Page.stopScreencast"); await asyncio.sleep(0.3)
    json.dump(times, open(f"{OUT}/{name}/times.json", "w"))
    print(name, len(times), "frames", flush=True)
    await pg.close()


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, locale="zh-TW")
        for name, url in PAGES:
            await grab(ctx, name, url)
        await b.close()

asyncio.run(main())
