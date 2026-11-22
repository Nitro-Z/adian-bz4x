import asyncio, os, sys, time
from playwright.async_api import async_playwright
import chatflow
BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
KEY = open("/home/lab/Jackie_Pham/和泰汽車黑客松/04_app/gateway/.access_key").read().strip()
OUT = sys.argv[1]
async def clickq(pg, text):
    await pg.wait_for_timeout(1400)
    await pg.click(f".quick-replies button:not([disabled]) >> text={text}")
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = await (await b.new_context(viewport={"width": int(sys.argv[2]), "height": int(sys.argv[3])})).new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        await pg.goto(f"{BASE}/advisor.html?start=member&key={KEY}", wait_until="networkidle"); await pg.wait_for_timeout(800)
        await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(600)
        await pg.evaluate("typeof chooseMode==='function' && chooseMode('text')"); await pg.wait_for_timeout(1500)
        await chatflow.run(pg)   # 11/12: shared driver for the new question set
        print("verdict:", await pg.locator("#verdictTitle").inner_text())
        await pg.evaluate("typeof stopTour==='function' && stopTour(true)"); await pg.wait_for_timeout(800)
        if await pg.evaluate("!!document.getElementById('v2reveal')"):   # v2: close the verdict poster first
            await pg.click("#v2reveal"); await pg.wait_for_timeout(1500)
            await pg.evaluate("typeof stopTour==='function' && stopTour(true)"); await pg.wait_for_timeout(600)
        await pg.evaluate("window.scrollTo(0, document.querySelector('#view3').getBoundingClientRect().top + scrollY - 90)"); await pg.wait_for_timeout(600)
        await pg.wait_for_timeout(1500)
        for s in await pg.evaluate("tourSteps(tour.verdict || '適合但有一個障礙').map(s => s.text)"): print("SAY:", s)
        n = await pg.evaluate("carSlides().length"); print("slides", n, "stacked:", await pg.evaluate("carGrid().classList.contains('stacked')"), await pg.evaluate("[carGrid().style.getPropertyValue('--main-w'), carGrid().style.getPropertyValue('--side-w')]"))
        for k in range(n):
            await pg.evaluate(f"carouselGo({k}, true)"); await pg.wait_for_timeout(1300)
            await pg.screenshot(path=f"{OUT}/s{k:02d}.png")
        print("errors:", errs[:6])
        await b.close()
asyncio.run(main())
