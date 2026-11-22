"""Typing-mode form test (v2 advisor, 11/12).

    python formtest.py OUTDIR [W H]
Member B: clicks office 信義區, kids, weekend mall, picks 都不行, presses 看結果 → results.
Guest: fills the form by clicking only → results. Screenshots in OUTDIR. Never prints the access key.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright
KEY = open("/home/lab/Jackie_Pham/和泰汽車黑客松/04_app/gateway/.access_key").read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/v2")
OUT = sys.argv[1]; W = int(sys.argv[2]) if len(sys.argv) > 2 else 1920; H = int(sys.argv[3]) if len(sys.argv) > 3 else 1080
os.makedirs(OUT, exist_ok=True)

async def results(pg, tag):
    await pg.wait_for_function("!document.getElementById('view3').classList.contains('hidden')", timeout=40000)
    await pg.wait_for_timeout(6000)
    print(tag, "verdict:", await pg.evaluate("document.getElementById('verdictTitle').textContent"),
          "| cards:", await pg.evaluate("carSlides().map(c => cardTitle(c)).join(' / ')"))
    print(tag, "sim:", (await pg.evaluate("simUrl() ? simUrl().replace(/hlat=[^&]+&hlon=[^&]+/, '') : '(none)'"))[:300])

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for who in (sys.argv[4].split(",") if len(sys.argv) > 4 else ("B", "guest")):
            pg = await (await b.new_context(viewport={"width": W, "height": H})).new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            try: await pg.goto(f"{BASE}/assets/personas.json?key={KEY}", wait_until="commit")
            except Exception as e: print("login", type(e).__name__)
            if who == "B":
                await pg.goto(f"{BASE}/advisor.html?start=member", wait_until="networkidle"); await pg.wait_for_timeout(600)
                await pg.click("#demo-B button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(800)
            else:
                await pg.goto(f"{BASE}/advisor.html?start=new", wait_until="networkidle"); await pg.wait_for_timeout(600)
                await pg.click("text=開始和阿電聊聊 →"); await pg.wait_for_timeout(800)
            await pg.evaluate("setVoice(false); chooseMode('text')"); await pg.wait_for_timeout(800)
            print(who, "form open:", await pg.evaluate("formOpen"))
            await pg.screenshot(path=f"{OUT}/{who}_1_form.png")
            if who == "B":
                # 11/16：點選模式不再有「一句話填表」，全部用點的
                await pg.click(".pf-chips[data-key=anchor] button[data-v='office']"); await pg.wait_for_timeout(400)
                if await pg.query_selector("#pfCounty"): await pg.select_option("#pfCounty", "台北市"); await pg.wait_for_timeout(300)
                await pg.select_option("#pfDist", "信義區"); await pg.wait_for_timeout(300)
                await pg.click(".pf-chips[data-key=kids] button >> text=早上送、下午接"); await pg.wait_for_timeout(250)
                await pg.click(".pf-chips[data-key=wkd] button >> text=逛街、賣場"); await pg.wait_for_timeout(250)
                await pg.screenshot(path=f"{OUT}/{who}_2_filled.png")
                await pg.click(".pf-chips[data-key=charge] button >> text=都不行")
                if await pg.evaluate("!document.querySelector('[data-row=seats]').classList.contains('hidden')"):
                    await pg.click(".pf-chips[data-key=seats] button >> text=3 到 5 人")
            else:
                await pg.select_option("#pfCity", "台中市"); await pg.wait_for_timeout(300); await pg.select_option("#pfHomeDist", "北屯區")
                await pg.fill("#pfNick", "王先生"); await pg.fill("#pfCarQ", "rav"); await pg.wait_for_timeout(300); await pg.click("[data-car='RAV4']"); await pg.wait_for_timeout(300); await pg.click("[data-carv='RAV4 油電']"); await pg.wait_for_timeout(400)
                print(who, "car:", await pg.evaluate("form.brand"))
                for key, v in [("carAge", "8–12 年"), ("ownerAge", "40–50 歲"), ("anchor", "平日在家（居家工作、家管、做生意）"),
                               ("wx", "買菜、超市"), ("wkd", "公園、運動、戶外"), ("charge", "還沒有，但可以裝")]:
                    sel = f".pf-chips[data-key={key}] button[data-v='home']" if key == "anchor" else f".pf-chips[data-key={key}] button[data-v='{v}']" if key == "charge" else f".pf-chips[data-key={key}] button >> text={v}"
                    await pg.click(sel); await pg.wait_for_timeout(250)
            await pg.wait_for_timeout(1500)
            await pg.screenshot(path=f"{OUT}/{who}_3_ready.png", full_page=False)
            print(who, "missing:", await pg.evaluate("formMissing()"))
            pg.on("console", lambda m: print(who, "LOG", m.text[:120]) if m.text.startswith("TRACE") else None)
            await pg.evaluate("""(() => { const a = ask, v = advance; let n = 0;
              window.ask = function (k, p) { if (++n < 60) console.log('TRACE ask ' + k + ' prefill=' + JSON.stringify(prefill[k] || null)); return a.apply(this, arguments); };
              window.advance = function (k, val) { if (n < 60) console.log('TRACE advance ' + k + ' = ' + String(val).slice(0, 40)); return v.apply(this, arguments); }; })()""")
            await pg.click("#pfGo")
            await pg.wait_for_timeout(12000)
            print(who, "after submit: key=", await pg.evaluate("currentKey"), "| queue=", await pg.evaluate("queue.join(',')"), "| prefill left=", await pg.evaluate("Object.keys(prefill).join(',')"),
                  "| last=", await pg.evaluate("[...document.querySelectorAll('#chatContainer .bubble-content')].slice(-2).map(e => e.textContent.slice(0, 80)).join(' || ')"))
            await results(pg, who)
            await pg.screenshot(path=f"{OUT}/{who}_4_results.png")
            print(who, "errors:", errs or "none")
            await pg.close()
        await b.close()
asyncio.run(main())
