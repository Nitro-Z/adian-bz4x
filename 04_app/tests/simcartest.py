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
        # stop any tour so it does not move the page, then play
        await pg.evaluate("typeof stopTour==='function' && stopTour(true)")
        await pg.locator("#simWrap").scroll_into_view_if_needed(); await pg.wait_for_timeout(1500)
        await pg.evaluate("weekAnim.token++"); await pg.wait_for_timeout(300)
        await pg.evaluate("playWeek(); 0")
        t0 = time.time()
        for i in range(10):
            await pg.wait_for_timeout(1500)
            await pg.locator("#simWrap").screenshot(path=f"{OUT}/f{i:02d}.png")
            st = await pg.evaluate("[document.getElementById('simDay').textContent, document.getElementById('simStatus').textContent, document.getElementById('simSoc').textContent, document.getElementById('simEv').textContent, document.getElementById('simFuel').textContent, weekAnim.playing]")
            print(f"{time.time()-t0:5.1f}s", st)
        print("summary:", (await pg.locator("#weekBody p.savings").inner_text())[:200])
        print("errors:", errs[:6])
        await b.close()
asyncio.run(main())
