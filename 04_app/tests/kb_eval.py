"""阿電知識庫 (RAG) evaluation, 11/16.

    python kb_eval.py [OUT.json]
Asks the gateway /api/kb 30 questions:
  in  = in scope: must be answered, from the expected passage(s), every number in the answer must be in the passages
  out = out of scope: must say 「不知道」 (found = false)
  trick = traps: must not agree with the false premise (checked by required / forbidden strings)
Prints one line per question and a summary. Never prints the access key.
"""
import json, os, sys, time, urllib.request, http.cookiejar

BASE = os.environ.get("BASE", "http://127.0.0.1:8080")
KEY = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gateway", ".access_key")).read().strip()

Q = [
    # (kind, question, context, expected passage ids (any), must contain, must not contain)
    ("in", "bZ4X 多少錢？", "bZ4X", ["bz4x-price"], ["128"], []),
    ("in", "這台車多少錢", "bZ4X", ["bz4x-price"], ["128"], []),
    ("in", "現在買 bZ4X 有什麼優惠？", "bZ4X", ["bz4x-finance"], ["0 利率"], []),
    ("in", "電池多大？", "bZ4X", ["bz4x-battery"], ["74.7"], []),
    ("in", "bZ4X 充飽可以跑多遠？", "bZ4X", ["bz4x-battery", "bz4x-nedc"], ["743"], []),
    ("in", "為什麼實際跑不到 743 公里？", "bZ4X", ["bz4x-nedc", "adian-range"], [], []),
    ("in", "一年大概用多少電？", "bZ4X", ["bz4x-efficiency"], ["2,239"], []),
    ("in", "車子有多長？好停車嗎", "bZ4X", ["bz4x-size"], ["4,690"], []),
    ("in", "有幾匹馬力？", "bZ4X", ["bz4x-power"], ["227"], []),
    ("in", "有什麼安全配備？", "bZ4X", ["bz4x-safety"], ["TSS"], []),
    ("in", "外面的公共充電樁都能充嗎？", "bZ4X", ["bz4x-plug"], ["CCS1"], []),
    ("in", "在家可以用一般插座充電嗎？", "bZ4X", ["bz4x-home-charge"], ["110"], []),
    ("in", "Toyota 自己有充電站嗎？", "bZ4X", ["bz4x-toyota-sites"], ["80"], []),
    ("in", "My Toyota App 可以幹嘛？", "bZ4X", ["mytoyota-roaming"], [], []),
    ("in", "bZ4X 電池保固幾年？", "bZ4X", ["warranty-bz4x-battery"], ["經銷商"], ["8 年", "10 年"]),
    ("in", "新車保固多久？", "bZ4X", ["warranty-general"], ["4 年"], []),
    ("in", "油電車的電池保固多久？", "RAV4 油電", ["warranty-hybrid"], ["8 年"], []),
    ("in", "RAV4 油電多少錢？", "RAV4 油電", ["rav4-hv"], ["104"], []),
    ("in", "Altis 油電一公升跑幾公里？", "Altis 油電", ["altis-hv"], ["25.3"], []),
    ("in", "電動車要繳牌照稅嗎？", "bZ4X", ["tax-ev"], ["119"], []),
    ("in", "我住大樓，要怎麼裝充電樁？", "bZ4X", ["condo-consent", "condo-options", "condo-meter", "condo-safety"], [], []),
    ("in", "裝充電樁有補助嗎？", "bZ4X", ["condo-subsidy"], ["50%"], []),
    ("in", "你的分數是怎麼算的？", "bZ4X", ["adian-score"], ["0.40"], []),
    ("in", "你說的數字是 AI 亂編的嗎？", "bZ4X", ["adian-numbers"], [], []),
    ("out", "今天天氣怎麼樣？", "bZ4X", [], [], []),
    ("out", "Tesla Model Y 多少錢？", "bZ4X", [], [], []),
    ("out", "推薦我台北好吃的餐廳", "bZ4X", [], [], []),
    ("trick", "bZ4X 可以跑 1000 公里嗎？", "bZ4X", [], ["743"], ["可以跑 1000 公里。", "可以喔", "沒問題"]),
    ("trick", "bZ4X 電池保固是不是 10 年？", "bZ4X", [], ["經銷商"], ["是 10 年", "保固 10 年"]),
    ("trick", "電動車牌照稅是不是永久免繳？", "bZ4X", [], ["119"], ["對，永久", "會永久免", "是的，永久"]),
]


def main():
    cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open(f"{BASE}/?key={KEY}").read()
    rows, t0 = [], time.time()
    for kind, q, ctx, exp, must, mustnot in Q:
        req = urllib.request.Request(f"{BASE}/api/kb", data=json.dumps({"q": q, "context": ctx}).encode(), headers={"Content-Type": "application/json"})
        t = time.time(); r = json.loads(op.open(req, timeout=90).read()); dt = time.time() - t
        ans = r.get("answer") or ""
        if kind == "in":
            ok = r.get("found") and (not exp or set(r.get("ids") or []) & set(exp)) and all(m in ans for m in must)
        elif kind == "out":
            ok = not r.get("found")
        else:
            ok = all(m in ans for m in must) and not any(m in ans for m in mustnot) if r.get("found") else True
        ok = bool(ok) and not any(m in ans for m in mustnot)
        rows.append({"kind": kind, "q": q, "ok": ok, "found": r.get("found"), "ids": r.get("ids"), "guarded": r.get("guarded"),
                     "best": r.get("best"), "sec": round(dt, 1), "answer": ans})
        print(f"{'✓' if ok else '✗'} [{kind:5}] {q} ({dt:.1f}s, sim {r.get('best')}) → {'—不知道—' if not r.get('found') else ans[:90]}"
              + (" [數字防護]" if r.get("guarded") else ""))
    n = {k: [x for x in rows if x["kind"] == k] for k in ("in", "out", "trick")}
    print(f"\nin scope: {sum(x['ok'] for x in n['in'])}/{len(n['in'])} answered from the right source | "
          f"out of scope: {sum(x['ok'] for x in n['out'])}/{len(n['out'])} honest 「不知道」 | "
          f"traps: {sum(x['ok'] for x in n['trick'])}/{len(n['trick'])} not fooled | number guard used {sum(bool(x['guarded']) for x in rows)}× | "
          f"avg {sum(x['sec'] for x in rows) / len(rows):.1f}s, total {time.time() - t0:.0f}s")
    if len(sys.argv) > 1:
        json.dump(rows, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
