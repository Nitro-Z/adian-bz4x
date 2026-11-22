"""阿電知識庫 (RAG), 11/16.

Passages: kb/adian_kb.json (official public sources only, each with a link and a check date; no CDP/Kantar).
Retrieval: EmbeddingGemma (Google) on the local Ollama; vectors cached in kb/.emb_cache.json (by text hash).
Answer: Gemma 4 answers ONLY from the retrieved passages and must say which ones it used; every number in the
answer must appear in those passages, otherwise the answer is replaced by the passage text itself (rule 8:
numbers are never invented by the LLM). Nothing found -> {"found": False} and the page says it honestly.
"""
import hashlib
import json
import math
import re
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
KB_FILE = HERE / "kb" / "adian_kb.json"
CACHE_FILE = HERE / "kb" / ".emb_cache.json"
EMB_MODEL = "embeddinggemma"
MIN_SIM = 0.42          # below this the best passage is treated as "not about this" (tuned on kb_eval.py)
TOP_K = 4

_kb = {"passages": [], "vecs": [], "sources": {}}


def _doc_text(p):
    return f"title: {p['title']} | text: {p['text']}"


def _query_text(q):
    return f"task: question answering | query: {q}"


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


async def _embed(client, ollama, texts):
    r = await client.post(f"{ollama}/api/embed", json={"model": EMB_MODEL, "input": texts, "keep_alive": -1})
    r.raise_for_status()
    return [_norm(v) for v in r.json()["embeddings"]]


async def load(ollama):
    """Read the passages and embed the ones not in the cache. Safe to call again (reload after edits)."""
    data = json.loads(KB_FILE.read_text(encoding="utf-8"))
    cache = json.loads(CACHE_FILE.read_text()) if CACHE_FILE.exists() else {}
    ps = data["passages"]
    keys = [hashlib.sha1(_doc_text(p).encode()).hexdigest() for p in ps]
    todo = [i for i, k in enumerate(keys) if k not in cache]
    async with httpx.AsyncClient(timeout=120) as c:
        for s in range(0, len(todo), 16):
            idx = todo[s:s + 16]
            vecs = await _embed(c, ollama, [_doc_text(ps[i]) for i in idx])
            for i, v in zip(idx, vecs):
                cache[keys[i]] = v
    CACHE_FILE.write_text(json.dumps({k: cache[k] for k in keys}))
    _kb.update(passages=ps, vecs=[cache[k] for k in keys], sources=data.get("sources", {}), checked=data.get("checked", ""))
    return len(ps)


async def search(ollama, q, k=TOP_K):
    if not _kb["passages"]:
        await load(ollama)
    async with httpx.AsyncClient(timeout=20) as c:
        qv = (await _embed(c, ollama, [_query_text(q)]))[0]
    sims = [(sum(a * b for a, b in zip(qv, v)), i) for i, v in enumerate(_kb["vecs"])]
    sims.sort(reverse=True)
    return [(s, _kb["passages"][i]) for s, i in sims[:k]]


ANSWER_SYSTEM = """你是「阿電」，和泰汽車的誠實電動車顧問，用台灣的繁體中文、口語、溫暖地回答。
規則（一定要遵守）：
1. 只能根據下面編號的「資料」回答。資料沒有寫的，不可以自己補充、推測或用你的記憶。
2. 數字（價格、公里、年數、kWh、百分比…）只能照抄資料裡的原文，不可以換算、加總或四捨五入。
3. 資料寫了「沒有列出」「請洽經銷商」「以官網為準」這類說明，也算有答案：照實告訴顧客（found=true）。
4. 資料只能回答一部分時，回答有的部分，再說其餘建議問展示中心（found=true）。
5. 「顧客正在看」的車只是參考。資料是 Toyota 全車系共同的規定（例如新車保固、牌照稅、充電樁申裝）時，一樣可以拿來回答（found=true）。
6. 只有資料完全沒有相關內容時，found 才設為 false，answer 留空。
7. 回答最多 3 句，先直接回答，再補一句最重要的說明。稱呼顧客用「你」，不要用「您」。不要說「根據資料」。
8. used 是你實際用到的資料編號（例如 [1,3]）。
只輸出 JSON：{"found": true 或 false, "answer": "...", "used": [編號]}"""

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _nums(s):
    return {n.replace(",", "") for n in _NUM.findall(s or "")}


async def answer(ollama, model, q, context=""):
    # search the question as asked, and with the car the customer is looking at ("這台車多少錢" → bZ4X);
    # keep the best score per passage, so a general question (condo chargers) is not pulled towards the car
    hits = (await search(ollama, q, 3)) if context and context not in q else await search(ollama, q, TOP_K)
    if context and context not in q:   # the top 3 of the plain question always stay; add up to 2 from "car + question"
        have = {p["id"] for _, p in hits}
        hits += [(s, p) for s, p in await search(ollama, f"{context} {q}", 3) if p["id"] not in have][:2]
    best = max((s for s, _ in hits), default=0)
    if best < MIN_SIM:
        return {"found": False, "best": round(best, 3), "sources": []}
    ctx = "\n".join(f"[{n}] {p['title']}：{p['text']}" for n, (_, p) in enumerate(hits, 1))
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{ollama}/api/chat", json={
                "model": model, "stream": False, "think": False, "format": "json", "keep_alive": -1,
                "options": {"temperature": 0, "seed": 7, "num_predict": 300},
                "messages": [{"role": "system", "content": ANSWER_SYSTEM},
                             {"role": "user", "content": f"資料：\n{ctx}\n\n" + (f"（顧客正在看：{context}）\n" if context else "") + f"顧客的問題：{q}"}]})
            r.raise_for_status()
            out = json.loads(r.json()["message"]["content"])
    except Exception as e:
        return {"found": False, "error": str(e)[:120], "best": round(best, 3), "sources": []}
    used = [u for u in (out.get("used") or []) if isinstance(u, int) and 1 <= u <= len(hits)] or [1]
    ans = str(out.get("answer") or "").strip()
    if not out.get("found") or not ans:
        return {"found": False, "best": round(best, 3), "sources": []}
    allowed = set().union(*[_nums(hits[u - 1][1]["text"]) for u in used]) | _nums(q)   # numbers the customer said may be repeated
    guarded = False
    if not _nums(ans) <= allowed:            # a number that is not in the passages: show the passage text instead
        ans, guarded = hits[used[0] - 1][1]["text"], True
    srcs, seen = [], set()
    for u in used:
        p = hits[u - 1][1]
        s = _kb["sources"].get(p["src"], {})
        if s.get("name") and s["name"] not in seen:
            seen.add(s["name"]); srcs.append({"name": s["name"], "url": s.get("url", ""), "title": p["title"]})
    return {"found": True, "answer": ans, "sources": srcs, "checked": _kb.get("checked", ""), "guarded": guarded,
            "best": round(best, 3), "ids": [hits[u - 1][1]["id"] for u in used]}
