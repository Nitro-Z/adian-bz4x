from pathlib import Path
import asyncio, json, sys, time, os
from playwright.async_api import async_playwright
V = sys.argv[1]; CH = sys.argv[2]; MIC = sys.argv[3]
BASE = "http://127.0.0.1:8080"; KEY = "key=" + (Path(__file__).resolve().parents[2] / "04_app/gateway/.access_key").read_text().strip()
W, H = 1600, 900

async def burst(pg, outdir, seconds, stop=None, every=0.09):
    os.makedirs(outdir, exist_ok=True); t0 = time.time(); idx = []; i = 0
    while time.time() - t0 < seconds:
        f = f"{outdir}/{i:04d}.jpg"
        await pg.screenshot(path=f, type="jpeg", quality=88)
        idx.append(round(time.time() - t0, 3)); i += 1
        if stop and await stop(): 
            for _ in range(int(2.0 / every)):   # 2 more seconds after the stop condition
                f = f"{outdir}/{i:04d}.jpg"; await pg.screenshot(path=f, type="jpeg", quality=88)
                idx.append(round(time.time() - t0, 3)); i += 1; await asyncio.sleep(every * 0.5)
            break
        await asyncio.sleep(every * 0.3)
    json.dump(idx, open(f"{outdir}/times.json", "w"))
    print(outdir, len(idx), "frames over", idx[-1], "s")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or (CH if os.path.exists(CH) else None), args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                     f"--use-file-for-fake-audio-capture={MIC}", "--autoplay-policy=no-user-gesture-required"])
        # ---------- D1: voice mode, auto-listen, live caption
        ctx = await b.new_context(viewport={"width": W, "height": H}, permissions=["microphone"])
        pg = await ctx.new_page()
        await pg.goto(f"{BASE}/advisor.html?start=member&{KEY}", wait_until="networkidle"); await pg.wait_for_timeout(1200)
        await pg.screenshot(path=f"{V}/demo/members.jpg", type="jpeg", quality=92)
        await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →")
        await pg.wait_for_timeout(300)
        await burst(pg, f"{V}/demo/d1_open", 7.5)                     # greeting being spoken
        for _ in range(200):
            if await pg.evaluate("listening"): break
            await pg.wait_for_timeout(100)
        await burst(pg, f"{V}/demo/d1_voice", 16, stop=lambda: pg.evaluate("!!userData.homeDistrict"))
        await ctx.close()

        # ---------- D2: results with tour (B, no home charging, 65 km)
        ctx = await b.new_context(viewport={"width": W, "height": H}); pg = await ctx.new_page()
        await pg.goto(f"{BASE}/advisor.html?start=member&{KEY}", wait_until="networkidle"); await pg.wait_for_timeout(800)
        await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(400)
        await pg.evaluate("""() => { stopSpeaking(); Object.assign(userData, {homeCounty:'新北市', homeDistrict:'板橋區', work:{county:'台北市', district:'信義區'}, commuteKm:14.1,
             lifestyle:'假日出遊露營', seats:'3 到 5 人', charge:'都不行', weekend:'大賣場／超市', dailyKm:65, worry:'充電'}); finishChat(); }""")
        for _ in range(200):
            if await pg.evaluate("tour.running"): break
            await pg.wait_for_timeout(100)
        await burst(pg, f"{V}/demo/d2_tour", 30, every=0.15)
        await pg.evaluate("stopTour(true)"); await pg.wait_for_timeout(600)
        for sel, name in (("#weekCard", "week"), ("#tripCard", "trip"), ("#lineupCard", "lineup"), ("#rentCard", "rent"), ("#cheatCard", "cheat")):
            el = pg.locator(sel); await el.scroll_into_view_if_needed(); await pg.wait_for_timeout(700)
            await el.screenshot(path=f"{V}/demo/{name}.png")
        await pg.locator(".result-card.verdict").scroll_into_view_if_needed(); await pg.wait_for_timeout(500)
        await pg.locator(".result-card.verdict").screenshot(path=f"{V}/demo/score_ok.png")
        await ctx.close()

        # ---------- D3: honest verdicts
        for tag, prof in (("notnow", "{homeCounty:'新北市', homeDistrict:'八里區', work:{county:'新竹市', district:'北區'}, commuteKm:69.5, lifestyle:'每天通勤', charge:'都不行', weekend:'很少去', dailyKm:145, worry:'充電'}"),
                          ("seats", "{homeCounty:'新北市', homeDistrict:'淡水區', work:null, lifestyle:'接送家人小孩', seats:'6 人以上', charge:'是，家裡可以', dailyKm:50, worry:'價格'}")):
            ctx = await b.new_context(viewport={"width": W, "height": H}); pg = await ctx.new_page()
            await pg.goto(f"{BASE}/advisor.html?start=member&{KEY}", wait_until="networkidle"); await pg.wait_for_timeout(800)
            await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(400)
            await pg.evaluate(f"() => {{ stopSpeaking(); Object.assign(userData, {prof}); finishChat(); setTimeout(() => stopTour(true), 200); }}")
            await pg.wait_for_timeout(6000)
            await pg.evaluate("window.scrollTo(0, 0)"); await pg.wait_for_timeout(400)
            await pg.locator(".result-card.verdict").screenshot(path=f"{V}/demo/verdict_{tag}.png")
            if tag == "seats":
                el = pg.locator("#sevenCard"); await el.scroll_into_view_if_needed(); await pg.wait_for_timeout(500)
                await el.screenshot(path=f"{V}/demo/seven.png")
            await ctx.close()

        # ---------- landing page
        ctx = await b.new_context(viewport={"width": W, "height": H}); pg = await ctx.new_page()
        await pg.goto(f"{BASE}/?{KEY}", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{V}/demo/landing.jpg", type="jpeg", quality=92)
        await pg.locator("#bz4x").scroll_into_view_if_needed(); await pg.wait_for_timeout(600)
        await pg.locator("#bz4x").screenshot(path=f"{V}/demo/banner.png")
        await ctx.close(); await b.close()
asyncio.run(main())
