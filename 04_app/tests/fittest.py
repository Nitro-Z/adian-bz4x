"""Fit audit: at common landscape sizes, does each step fit in one screen without page scrolling?
python fittest.py OUTDIR  -> screenshots + a table of elements that end below the visible area."""
import asyncio, os, json, sys
from playwright.async_api import async_playwright
KEY = open(os.path.join(os.path.dirname(__file__), "..", "gateway", ".access_key")).read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
SIZES = [(1920, 1080), (1536, 864), (1366, 768), (1280, 720)]
MEASURE = """(sels) => sels.map(s => { const e = document.querySelector(s); if (!e || !e.offsetParent && getComputedStyle(e).position !== 'fixed') return [s, null];
  const r = e.getBoundingClientRect(); return [s, Math.round(r.bottom - innerHeight)]; })"""
async def step(pg, tag, w, h, sels):
    await pg.wait_for_timeout(1200)
    m = await pg.evaluate(MEASURE, sels)
    doc = await pg.evaluate("[document.documentElement.scrollHeight - innerHeight, Math.round(scrollY)]")
    await pg.screenshot(path=f"{OUT}/{w}x{h}_{tag}.png")
    over = {s: v for s, v in m if v is not None and v > 0}
    print(f"{w}x{h} {tag:12s} below-screen: {json.dumps(over, ensure_ascii=False)}")
async def run(p, w, h, mode):
    b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None,
                                args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    ctx = await b.new_context(viewport={"width": w, "height": h}); pg = await ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    await pg.goto(f"{BASE}/advisor.html?start=member&key={KEY}", wait_until="networkidle"); await pg.wait_for_timeout(800)
    await pg.click("#demo-C button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(500)
    await pg.evaluate(f"chooseMode('{mode}')"); await pg.wait_for_timeout(3500)
    chat = ["#vmMic", "#vmControls", "#chatContainer", "#sliderGroup", "#inputBar", ".wizard"]
    await step(pg, f"{mode}-q1", w, h, chat)
    if mode == "text":
        if await pg.evaluate("currentKey") == "district":
            await pg.select_option("#selOne", "七股區"); await pg.click("#sliderGroup button")
        await pg.wait_for_timeout(2500)
        await step(pg, "text-q2", w, h, chat)
        # jump to results quickly with a fixed profile
        await pg.evaluate("""() => { userData = Object.assign(userData, { homeCounty: '台南市', homeDistrict: '七股區', work: null, lifestyle: '每天通勤', charge: '都不行', weekend: '大賣場／超市', dailyKm: 40, worry: '充電' }); queue = []; finishChat(); }""")
        await pg.wait_for_timeout(7000); await pg.evaluate("stopTour(true)"); await pg.wait_for_timeout(800)
        n = await pg.evaluate("carSlides().length")
        for k in range(n):
            await pg.evaluate(f"carouselGo({k}, true)"); await pg.wait_for_timeout(1100)
            await step(pg, f"res{k:02d}", w, h, [".carousel > .result-card[data-pos='active']", ".car-nav", ".cta-row"])
    print("errors:", errs[:3]); await b.close()
async def main():
    async with async_playwright() as p:
        for w, h in SIZES:
            for mode in ("voice", "text"): await run(p, w, h, mode)
asyncio.run(main())
