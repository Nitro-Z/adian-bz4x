"""Run the real advance('work') logic for every county pair (+ edge cases) and record verdicts."""
import asyncio, os, json, sys, time
from playwright.async_api import async_playwright
KEY = open("/home/lab/Jackie_Pham/和泰汽車黑客松/04_app/gateway/.access_key").read().strip()
OUT = sys.argv[1]
HARNESS = r"""
async ([hc, hd, wc, wd]) => {
  chatEl().innerHTML = '';
  mode = 'guest'; member = null;
  userData = { city: hc, homeCounty: hc, homeDistrict: hd };
  queue = ['lifestyle']; currentKey = null;
  await advance('work', wd ? wc + wd : wc);
  const asked = currentKey;
  const out = { home: hc + hd, work: wd ? wc + wd : wc, asked, workKept: !!userData.work, retry: !!userData.workRetry,
                commuteKm: userData.commuteKm,
                said: [...chatEl().querySelectorAll('.bubble-content')].map(b => b.textContent.trim()).join(' | ').slice(0, 220) };
  if (asked === 'commuteFreq') { await advance('commuteFreq', '每天都要開'); }
  userData.lifestyle = '每天通勤'; userData.seats = '3 到 5 人';
  out.dailyKm = suggestedKm(); userData.dailyKm = out.dailyKm;
  out.verdicts = {};
  for (const ch of ['是，家裡可以', '都不行']) { userData.charge = ch; out.verdicts[ch] = [calculateResult(), evScore().S]; }
  return out;
}
"""
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = await (await b.new_context(viewport={"width": 1366, "height": 900})).new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(f"http://127.0.0.1:8080/advisor.html?key={KEY}", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        await pg.evaluate("loadVillages()")
        reps = await pg.evaluate("""() => { const r = {}; for (const c of countyNames()) { const ds = Object.entries(districtData[c]);
             const m = ds.reduce((a, [, p]) => [a[0] + p[0] / ds.length, a[1] + p[1] / ds.length], [0, 0]);
             r[c] = ds.map(([d, p]) => [d, Math.hypot(p[0] - m[0], p[1] - m[1])]).sort((a, b) => a[1] - b[1])[0][0]; }
             r['金門縣'] = '金城鎮'; r['連江縣'] = '南竿鄉'; r['澎湖縣'] = '馬公市'; return r; }""")
        pairs = [(hc, reps[hc], wc, reps[wc]) for hc in reps for wc in reps]
        edges = [("新北市", "淡水區", "金門縣", "烈嶼鄉"), ("金門縣", "金城鎮", "金門縣", "烈嶼鄉"), ("澎湖縣", "馬公市", "澎湖縣", "七美鄉"),
                 ("澎湖縣", "馬公市", "澎湖縣", "白沙鄉"), ("屏東縣", "東港鎮", "屏東縣", "琉球鄉"), ("台東縣", "台東市", "台東縣", "綠島鄉"),
                 ("連江縣", "南竿鄉", "連江縣", "北竿鄉"), ("花蓮縣", "花蓮市", "台北市", "信義區"), ("台東縣", "台東市", "高雄市", "前鎮區"),
                 ("新北市", "淡水區", "新北市", "淡水區"), ("新北市", "淡水區", "不用通勤", None), ("台北市", "大安區", "新北市", "板橋區"),
                 ("宜蘭縣", "宜蘭市", "台北市", "中山區"), ("新竹縣", "竹北市", "台北市", "內湖區"), ("台中市", "西屯區", "台北市", "中正區")]
        rows = []; t0 = time.time()
        for k, pr in enumerate(edges + pairs):
            try: rows.append(await pg.evaluate(HARNESS, list(pr)))
            except Exception as e: rows.append({"home": pr[0] + pr[1], "work": str(pr[2]) + str(pr[3]), "error": str(e)[:200]})
            if k % 40 == 0: print(f"{k}/{len(edges) + len(pairs)}  {time.time() - t0:.0f}s", flush=True)
            json.dump({"rows": rows, "errors": errs}, open(OUT, "w"), ensure_ascii=False, indent=0)
        print("done", len(rows), "page errors:", errs[:5])
        await b.close()
asyncio.run(main())
