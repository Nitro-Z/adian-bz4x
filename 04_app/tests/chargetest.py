"""For every district: run the real advance('charge') + calculateResult() with no home/work charging at several daily km."""
import asyncio, os, json, sys, collections
from playwright.async_api import async_playwright
KEY = open("/home/lab/Jackie_Pham/和泰汽車黑客松/04_app/gateway/.access_key").read().strip()
HARNESS = r"""
async ([county, district]) => {
  const out = [];
  for (const ch of ['都不行', '還沒有，但可以裝']) for (const km of [30, 50, 80]) {
    chatEl().innerHTML = '';
    mode = 'guest'; member = null;
    userData = { city: county, homeCounty: county, homeDistrict: district, lifestyle: '每天通勤', seats: '3 到 5 人', work: null, weekend: '大賣場／超市' };
    queue = ['km']; currentKey = null;
    await advance('charge', ch);
    const said = [...chatEl().querySelectorAll('.bubble-content')].map(b => b.textContent.trim()).join(' | ').slice(0, 160);
    userData.dailyKm = km;
    const v = calculateResult(), sc = evScore();
    out.push({ county, district, ch, km, near: userData.nearFastKm, C: sc.C, S: sc.S, v, said });
  }
  return out;
}
"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = await (await b.new_context()).new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:8080/advisor.html?key={KEY}", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        ds = await pg.evaluate("Object.entries(districtData).flatMap(([c, d]) => Object.keys(d).map(n => [c, n]))")
        rows = []
        for cd in ds: rows += await pg.evaluate(HARNESS, cd)
        json.dump({"rows": rows, "errors": errs}, open(sys.argv[1], "w"), ensure_ascii=False)
        print("rows", len(rows), "errors", errs[:3])
        await b.close()
asyncio.run(main())
