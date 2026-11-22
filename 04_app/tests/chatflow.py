"""Shared chat driver for the advisor tests (11/12: the questions now follow the 「你的一週」 blocks).

    await chatflow.run(pg)                     # member flow with the default answers
    await chatflow.run(pg, {"charge": "是，家裡可以"})   # override some answers
Answers every question through the page's own answer() (no LLM), until the results view shows.
"""
DEFAULT = {"district": "板橋區", "plan": "一題一題回答", "work": "台北市信義區", "wdays": "週一到週五", "kids": "不用接送",
           "roamArea": "新北市新莊區", "seats": "3 到 5 人", "wx": "都沒有", "wkd": "逛街、賣場、公園、戶外走走", "hometown": "台中市",
           "charge": "都不行", "km": "35", "trip": "沒有", "budget": "想看分期月付", "worry": "充電", "villages": "不清楚",
           "commuteFreq": "每天都要開", "stillOwn": "還在開"}


async def run(pg, overrides=None, wait_ms=7000):
    ans = {**DEFAULT, **(overrides or {})}
    asked = []
    # 11/12: typing mode is now a one-screen form; these tests drive the chat, so switch the form back to the chat
    await pg.evaluate("(() => { if (typeof formOpen !== 'undefined' && formOpen) { form = {}; chooseMode('voice'); } })()")
    for _ in range(600):
        await pg.wait_for_timeout(300)
        k = await pg.evaluate("currentKey")
        if not k:
            if await pg.evaluate("!document.getElementById('view3').classList.contains('hidden')"):
                break
            continue
        if asked and asked[-1] == k:
            continue
        asked.append(k)
        await pg.evaluate(f"answer({ans.get(k, '不清楚')!r})")
    await pg.wait_for_timeout(wait_ms)
    return asked
