"""Phone layout check (v2, 11/16).

    python mobiletest.py OUTDIR [W H]        (default 390 844, touch, DPR 2)
Landing → 開始和阿電聊聊 (?start=go) → form (guest, taps only) → 看結果 → every result card. Screenshots in OUTDIR,
prints horizontal overflow and elements wider than the screen. Never prints the access key.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright
KEY = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gateway", ".access_key")).read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080/v2")
OUT = sys.argv[1] if len(sys.argv) > 1 else "."; W = int(sys.argv[2]) if len(sys.argv) > 2 else 390; H = int(sys.argv[3]) if len(sys.argv) > 3 else 844

WIDE = """(() => { const w = innerWidth, out = [];
  document.querySelectorAll('body *').forEach(e => { const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
    if (r.width && cs.visibility !== 'hidden' && cs.display !== 'none' && (r.right > w + 2 || r.left < -2) && !e.closest('.result-grid, .carousel, #simLayer, .marquee, [aria-hidden=true]'))
      out.push((e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].slice(0, 2).join('.')) + ' ' + Math.round(r.left) + '..' + Math.round(r.right)); });
  return { docW: document.documentElement.scrollWidth, w, wide: out.slice(0, 12) }; })()"""


async def shot(pg, name):
    await pg.screenshot(path=f"{OUT}/{name}.png")
    print(name, await pg.evaluate(WIDE))


async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        try: await pg.goto(f"{BASE}/assets/personas.json?key={KEY}", wait_until="commit")
        except Exception as e: print("login", type(e).__name__)
        await pg.goto(f"{BASE}/index.html", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await shot(pg, "01_landing")
        await pg.goto(f"{BASE}/advisor.html?start=go", wait_until="domcontentloaded"); await pg.wait_for_timeout(700)
        await shot(pg, "02_loading")
        await pg.wait_for_function("window.formOpen === true || (typeof formOpen !== 'undefined' && formOpen)", timeout=30000)
        await pg.wait_for_timeout(1500)
        await shot(pg, "03_form_top")
        await pg.evaluate("setVoice(false)")
        await pg.select_option("#pfCity", "台中市"); await pg.wait_for_timeout(300); await pg.select_option("#pfHomeDist", "北屯區")
        await pg.fill("#pfNick", "王先生")
        await pg.tap("[data-car='其他品牌']"); await pg.wait_for_timeout(400)
        await shot(pg, "04_car_other")
        if await pg.query_selector("#pfCarOther"): await pg.fill("#pfCarOther", "Mazda 3")
        for key, v in [("carAge", "8–12 年"), ("ownerAge", "40–50 歲")]:
            await pg.tap(f".pf-chips[data-key={key}] button >> text={v}"); await pg.wait_for_timeout(250)
        await pg.tap(".pf-chips[data-key=anchor] button[data-v='office']"); await pg.wait_for_timeout(500)
        await shot(pg, "05_office")
        dist = await pg.query_selector("#pfDist")
        if dist: await pg.select_option("#pfDist", "西屯區"); await pg.wait_for_timeout(300)
        for key, v in [("wkd", "公園、運動、戶外")]:
            await pg.tap(f".pf-chips[data-key={key}] button >> text={v}"); await pg.wait_for_timeout(250)
        await pg.tap(".pf-chips[data-key=charge] button[data-v='都不行']"); await pg.wait_for_timeout(400)
        await shot(pg, "06_filled")
        print("missing:", await pg.evaluate("formMissing()"))
        await pg.tap("#pfGo")
        await pg.wait_for_function("!document.getElementById('view3').classList.contains('hidden')", timeout=90000)
        await pg.wait_for_timeout(9000)
        await shot(pg, "07_results")
        n = await pg.evaluate("carSlides().length")
        for i in range(n):
            await pg.evaluate(f"carouselGo({i})"); await pg.wait_for_timeout(1800)
            await shot(pg, f"08_card{i + 1}")
        print("errors:", errs or "none")
        await b.close()
if __name__ == "__main__":
    asyncio.run(main())
