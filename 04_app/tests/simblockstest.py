"""Life simulation blocks check (SIM_CONTRACT_20261112: anchor, wdays, kmode, wx, okm, wkd, hometown, outing, tstops).
python simblockstest.py OUTDIR [CASE ...]      (no CASE = all cases below)
Runs each case on website_v2/preview/sim3d.html with map=2d&nopre=1 (no Google 3D session, no TTS), prints the length, chapters,
every 阿電 line with its time (⚠ = overlaps the previous one), the places used, the trip-tab visibility, battery range, JS errors,
and takes one screenshot per chapter (OUTDIR/<case>_tN.png). Never prints the access key."""
import asyncio, json, os, sys, urllib.parse
from playwright.async_api import async_playwright
KEY = open(os.path.join(os.path.dirname(__file__), "..", "gateway", ".access_key")).read().strip()
BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
B = "hlat=25.01577&hlon=121.47300&hname=板橋區&wlat=25.04045&wlon=121.57378&wname=信義區&map=2d&nopre=1"
TS = urllib.parse.quote(json.dumps([{"name": "台中", "lat": 24.1477, "lon": 120.6736, "nights": 1}, {"name": "日月潭", "lat": 23.8665, "lon": 120.9157, "nights": 2}], ensure_ascii=False))
CASES = {
    "default_week": "scene=week&mode=public&map=2d&nopre=1",
    "default_day": "scene=day&mode=work&map=2d&nopre=1",
    "home_kids_market": f"scene=week&mode=public&kids=1&anchor=home&kmode=both&wx=market&{B}",
    "office3": f"scene=week&mode=work&kids=1&anchor=office&wdays=3&{B}",
    "office6_mall_park": f"scene=week&mode=public&kids=1&anchor=office&wdays=6&wkd=mall,park&{B}",
    "office7": f"scene=week&mode=home&kids=0&anchor=office&wdays=7&wkd=hometown&htlat=24.1477&htlon=120.6736&htname=台中&{B}",
    "hometown_park": f"scene=week&mode=home&kids=1&anchor=office&wkd=hometown,park&htlat=24.1477&htlon=120.6736&htname=台中&{B}",
    "outing": f"scene=week&mode=public&kids=0&anchor=office&wkd=outing&{B}",
    "roam_gym": f"scene=week&mode=work&kids=0&anchor=roam&wx=gym,parents&okm=40&{B}",
    "day_office_kids": f"scene=day&mode=public&kids=1&anchor=office&wx=gym&{B}",
    "day_home_kids": f"scene=day&mode=home&kids=1&anchor=home&wx=market,cram&{B}",
    "tstops2": f"scene=trip&kids=1&tstops={TS}&{B}",
    "embed_notrip": f"scene=trip&embed=1&kids=1&anchor=office&{B}",
    "home_empty": "scene=week&mode=home&kids=0&anchor=home&wkd=home&embed=1&hlat=25.01577&hlon=121.47300&hname=板橋區&map=2d&nopre=1",
    "roam_nowork": "scene=week&mode=public&kids=1&kmode=am&anchor=roam&wkd=park&hlat=25.01577&hlon=121.47300&hname=板橋區&map=2d&nopre=1",
    "office1_cram": f"scene=week&mode=home&kids=1&kmode=pm&wdays=1&wx=cram,market&wkd=mall,outing&olat=24.8&olon=121.74&oname=礁溪&{B}",
    "tstops3_long": "scene=trip&embed=1&kids=0&anchor=home&hlat=25.01577&hlon=121.47300&hname=板橋區&map=2d&nopre=1&tstops=" + urllib.parse.quote(json.dumps([{"name": "宜蘭", "lat": 24.7570, "lon": 121.7533, "nights": 1}, {"name": "花蓮", "lat": 23.9930, "lon": 121.6011, "nights": 3}, {"name": "台東", "lat": 22.7583, "lon": 121.1444, "nights": 2}], ensure_ascii=False)),
    "nt_puli_tc": "scene=week&mode=public&kids=1&anchor=office&wdays=5&wkd=mall,park&hlat=23.97074&hlon=120.97371&hname=埔里鎮&wlat=24.16641&wlon=120.65921&wname=西屯區&map=2d&nopre=1",
    "nt_city_home": "scene=week&mode=public&kids=1&anchor=home&wx=market&wkd=outing,park&hlat=23.90962&hlon=120.68542&hname=南投市&map=2d&nopre=1",
    "nt_xinyi_office": "scene=week&mode=public&kids=0&anchor=office&wdays=5&wkd=mall&hlat=23.61259&hlon=120.85626&hname=信義鄉&wlat=23.90962&wlon=120.68542&wname=南投市&map=2d&nopre=1",
    "nt_renai_tc": "scene=week&mode=home&kids=1&anchor=office&wdays=5&wkd=park,hometown&htlat=25.01577&htlon=121.47300&htname=板橋&hlat=24.05497&hlon=121.24266&hname=仁愛鄉&wlat=24.16641&wlon=120.65921&wname=西屯區&map=2d&nopre=1",
}
STATE = """(() => { const tab = document.querySelector('[data-scene="trip"]');
  let bmin = 999, bmax = -999; for (let t = 0; t <= TL.duration; t += 0.5) { const b = TL.stateAt(t).bat; bmin = Math.min(bmin, b); bmax = Math.max(bmax, b); }
  return { dur: TL.duration, chapters: TL.chapters.map(c => c.label + '@' + c.t.toFixed(1)), cues: TL.cues.map(c => [c.at, c.show, c.text]),
    info: window.SCINFO, tripTab: tab ? getComputedStyle(tab).display + ' ' + tab.textContent : 'none', scene: document.querySelector('.tab.on') && document.querySelector('.tab.on').textContent,
    title: document.getElementById('startTitle').textContent, sub: document.getElementById('startSub').textContent, bmin, bmax }; })()"""


async def main():
    names = sys.argv[2:] or list(CASES)
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--enable-webgl"])
        ctx = await b.new_context(viewport={"width": 1600, "height": 900})
        pg = await ctx.new_page()
        try:
            await pg.goto(f"{BASE}/v2/assets/personas.json?key={KEY}", wait_until="commit", timeout=60000)
            await pg.wait_for_timeout(1200)
        except Exception as e:
            raise SystemExit("login step failed: " + type(e).__name__)
        errs = []
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:300]))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text[:200]}") if m.type == "error" else None)
        for name in names:
            errs.clear()
            await pg.goto(f"{BASE}/v2/preview/sim3d.html?{CASES[name]}")
            try:
                await pg.wait_for_function("window.READY === true", timeout=240000, polling=1000)
            except Exception:
                print(f"== {name}: NOT READY", errs[:6]); continue
            await pg.evaluate("AdianAvatar.setTTSServer(null)")
            st = await pg.evaluate(STATE)
            print(f"== {name}: {st['dur']:.1f}s ({int(st['dur'] // 60)}:{int(st['dur'] % 60):02d}) | tab {st['scene']} | trip tab: {st['tripTab']} | battery {st['bmin']:.0f}–{st['bmax']:.0f}%")
            print("   title:", st["title"], "|", st["sub"])
            i = st["info"] or {}
            print("   km", i.get("km"), "charges", i.get("charges"), "| places:", ", ".join(i.get("places") or []))
            print("   chapters:", " | ".join(st["chapters"]))
            prev = -1
            for at, show, text in st["cues"]:
                print(f"    {at:6.1f}s ({show:.1f}) {text}{'  ⚠' if at < prev - 0.2 else ''}")
                prev = at + show
            await pg.screenshot(path=f"{OUT}/{name}_start.png")
            await pg.evaluate("document.getElementById('startLayer').style.display='none'; SIM.showCar(true)")
            ts = await pg.evaluate("TL.chapters.map(c => c.t + 2.5)")
            for k, t in enumerate(ts[:9]):
                await pg.evaluate(f"TL.seek({t})"); await pg.evaluate("SIM.waitTiles(8000)"); await pg.wait_for_timeout(500); await pg.evaluate(f"TL.seek({t})")
                await pg.wait_for_timeout(250)
                await pg.screenshot(path=f"{OUT}/{name}_t{k}.png")
            print("   JS errors:", errs[:6] or "none")
        await b.close()

asyncio.run(main())
