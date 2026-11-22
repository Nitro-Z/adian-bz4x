"""End-to-end (v2 advisor): demo member B (陳先生) chats through to the results and the new life simulation.
python e2e_sim_member.py OUTDIR [MEMBER=B] [CHARGE=是，公司可以]
  - answers every question with fixed values, accepts the address popup (member: address from the CRM demo),
  - prints the score S (C/E/M/V) and the verdict, checks the simulation was preloaded during the chat,
  - opens the simulation full screen from the week card and checks it plays; screenshots along the way.
TTS is switched off in every frame (no Gemini calls). Never prints the access key. Env GPU=1 uses the lab GPU (Vulkan)."""
import asyncio, os, sys, time
from playwright.async_api import async_playwright
KEY = open(os.path.join(os.path.dirname(__file__), "..", "gateway", ".access_key")).read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
OUT = sys.argv[1]; MEMBER = sys.argv[2] if len(sys.argv) > 2 else "B"; CHARGE = sys.argv[3] if len(sys.argv) > 3 else "是，公司可以"
W, H = (int(x) for x in os.environ.get("VP", "1920x1080").split("x"))
os.makedirs(OUT, exist_ok=True)
GPU = ["--use-angle=vulkan", "--enable-features=Vulkan", "--ignore-gpu-blocklist", "--enable-gpu"]
CPU = ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"]
NO_TTS = """(() => { let v; Object.defineProperty(window, 'AdianAvatar', { configurable: true,
  get() { return v; }, set(x) { if (x) x.setTTSServer = function () {}; v = x; } }); })();"""
ANSWERS = {"district": "板橋區", "plan": "一題一題回答", "work": "台北市信義區", "wdays": "週一到週五", "kids": "早上送、下午接",
           "seats": "3 到 5 人", "wx": "都沒有", "wkd": "逛街、賣場、公園、戶外走走", "charge": CHARGE, "km": "40", "trip": "沒有",
           "budget": "想看分期月付", "worry": "充電", "villages": "不清楚", "commuteFreq": "每天都要開", "hometown": "台中市"}


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=(GPU if os.environ.get("GPU") else CPU) + ["--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(viewport={"width": W, "height": H})
        await ctx.add_init_script(NO_TTS)
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text[:200]}") if m.type == "error" else None)
        try:
            await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000)
            await pg.wait_for_timeout(800)
        except Exception as e:
            raise SystemExit("login step failed: " + type(e).__name__)
        await pg.goto(f"{BASE}/v2/advisor.html?start=member", wait_until="networkidle")   # 11/13：示範會員只在 ?start=member 出現
        await pg.wait_for_timeout(800)
        await pg.click(f"#demo-{MEMBER} button"); await pg.click("text=同意，開始聊聊 →"); await pg.wait_for_timeout(600)
        await pg.evaluate("chooseMode('voice')"); await pg.wait_for_timeout(600)   # 11/13：預設是點選表單；這個測試走對話
        await pg.evaluate("setVoice(false)")   # 11/12: stay in the chat (typing mode is now a form; see formtest.py)
        t0 = time.time(); seen = []; preload_seen_at = None
        while time.time() - t0 < 240:
            await pg.wait_for_timeout(700)
            if await pg.evaluate("!document.getElementById('addrModal').classList.contains('hidden')"):
                val = await pg.evaluate("document.getElementById('addrInput').value")
                await pg.screenshot(path=f"{OUT}/1_address_popup.png")
                print("address popup shown; prefilled:", bool(val))
                await pg.evaluate("document.getElementById('addrYes').click()")
                await pg.wait_for_timeout(2500)
                print("  geocoded:", await pg.evaluate("userData.homeExact ? 'yes' : 'no (district centre)'"), "|", await pg.evaluate("document.getElementById('addrMsg').textContent"))
                if not await pg.evaluate("document.getElementById('addrModal').classList.contains('hidden')"):
                    await pg.evaluate("document.getElementById('addrNo').click()")
                continue
            if preload_seen_at is None and await pg.evaluate("!!document.querySelector('#simLayer iframe')"):
                preload_seen_at = time.time() - t0
            key = await pg.evaluate("currentKey")
            if not key:
                if await pg.evaluate("!document.getElementById('view3').classList.contains('hidden')"): break
                continue
            if seen and seen[-1] == key: continue
            seen.append(key)
            await pg.evaluate(f"answer({ANSWERS.get(key, '不清楚')!r})")
        print("questions:", " → ".join(seen))
        print(f"simulation iframe created during the chat at {preload_seen_at:.0f}s" if preload_seen_at is not None else "simulation iframe NOT created during the chat")
        await pg.wait_for_function("document.getElementById('verdictTitle').textContent.trim().length > 0", timeout=60000)
        sc = await pg.evaluate("(() => { const s = evScore(); return [s.S, s.C, s.E, s.M, s.V]; })()")
        verdict = await pg.evaluate("document.getElementById('verdictTitle').textContent.trim()")
        print(f"member {MEMBER}: S={sc[0]} (C={sc[1]} E={sc[2]} M={sc[3]} V={sc[4]}) | verdict: {verdict}")
        # 其他常見答案組合的分數（同一位會員，只換用車方式與充電方式）
        combos = await pg.evaluate("""(() => { const keep = { ...userData }, out = [];
          for (const ls of ['每天通勤', '接送家人小孩']) for (const ch of ['是，公司可以', '是，家裡可以', '都不行']) {
            userData.lifestyle = ls; userData.charge = ch; const s = evScore(); out.push([ls, ch, s.S, s.C, s.V]); }
          Object.assign(userData, keep); return out; })()""")
        for c in combos: print("   ", c)
        # 結論揭曉後導覽才開始：等導覽真的開始，再停掉（不然導覽翻卡片時會把模擬關掉）
        try: await pg.wait_for_function("tour.running === true", timeout=30000)
        except Exception: pass
        await pg.evaluate("stopTour(true)"); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{OUT}/2_results.png")
        # the simulation should be ready (preloaded during the chat)
        try:
            await pg.wait_for_function("simState.ready === true", timeout=180000)
            print("simulation ready:", await pg.evaluate("simState.url.replace(/hlat=[^&]+&hlon=[^&]+/, 'hlat=…&hlon=…')"))
        except Exception:
            print("simulation NOT ready after 180 s")
        idx = await pg.evaluate("carSlides().indexOf(document.getElementById('weekCard'))")
        if idx >= 0:
            await pg.evaluate(f"carouselGo({idx}, true)"); await pg.wait_for_timeout(1500)
            await pg.screenshot(path=f"{OUT}/3_week_card.png")
        fr = next((f for f in pg.frames if "sim3d.html" in f.url), None)
        # 使用者的做法：按週卡片上的「▶ 播放你的一週」
        await pg.click(".sim-launch .go")
        for k, wait in enumerate([6000, 9000]):
            await pg.wait_for_timeout(wait)
            st = await fr.evaluate("[TL.time.toFixed(1), TL.duration.toFixed(1), TL.playing, SCINFO]") if fr else None
            print(f"  after click +{6 if k == 0 else 15}s:", st, "| overlay shown:", await pg.evaluate("document.getElementById('simLayer').classList.contains('show')"), "| closedBy:", await pg.evaluate("simState.closedBy || '-'"))
            await pg.screenshot(path=f"{OUT}/4_sim_playing_{k}.png")
        await pg.evaluate("closeSim()"); await pg.wait_for_timeout(600)
        print("overlay closed:", await pg.evaluate("!document.getElementById('simLayer').classList.contains('show')"))
        print("JS errors:", [e for e in errs if "favicon" not in e][:8] or "none")
        await b.close()

asyncio.run(main())
