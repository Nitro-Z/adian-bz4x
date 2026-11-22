import asyncio, os, sys, time
from playwright.async_api import async_playwright
import chatflow
BASE = "http://127.0.0.1:8080"
KEY = open("/home/lab/Jackie_Pham/和泰汽車黑客松/04_app/gateway/.access_key").read().strip()
OUT = sys.argv[1]
async def clickq(pg, text):
    await pg.wait_for_timeout(1400)
    await pg.click(f".quick-replies button:not([disabled]) >> text={text}")
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        await pg.goto(f"{BASE}/advisor.html?start=member&key={KEY}", wait_until="networkidle"); await pg.wait_for_timeout(800)
        await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(600)
        await pg.evaluate("typeof chooseMode==='function' && chooseMode('text')"); await pg.wait_for_timeout(1500)
        await chatflow.run(pg)   # 11/12: shared driver for the new question set
        print("verdict:", await pg.locator("#verdictTitle").inner_text())
        await pg.evaluate("typeof stopTour==='function' && stopTour(true)"); await pg.wait_for_timeout(800)
        await pg.evaluate("window.scrollTo(0, document.querySelector('#view3').getBoundingClientRect().top + scrollY - 90)"); await pg.wait_for_timeout(600)
        n = await pg.evaluate("carSlides().length"); print("slides:", n, await pg.evaluate("carSlides().map(cardTitle)"))
        await pg.screenshot(path=f"{OUT}/c00.png")
        await pg.evaluate("carouselStep(1, true)"); await pg.wait_for_timeout(250)
        await pg.screenshot(path=f"{OUT}/c01_mid.png")
        await pg.wait_for_timeout(700); await pg.screenshot(path=f"{OUT}/c01.png")
        for k in range(2, n):
            await pg.keyboard.press("ArrowRight"); await pg.wait_for_timeout(1000)
            await pg.screenshot(path=f"{OUT}/c{k:02d}.png")
            print(k, await pg.evaluate("[carousel.i, cardTitle(carousel.cur), carGrid().style.height]"))
        pass
        print("errors:", errs[:6])
        await b.close()
asyncio.run(main())
