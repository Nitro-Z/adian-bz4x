"""Demo gateway: one HTTPS-friendly origin for the website + TTS, protected by a password.

- Serves ../website as static files.
- Proxies /tts and /health to the BreezyVoice server (default http://127.0.0.1:8100),
  so the browser talks to a single origin (no mixed-content / CORS problems behind a tunnel).
- Login: a normal password page (/login) that sets a session cookie. This works in phone browsers
  and in-app browsers (LINE, Messenger, ...) that never show the HTTP Basic Auth dialog.
  A shareable link /?key=<access key> logs the visitor in directly.
  HTTP Basic Auth still works for scripts and tests.
  Credentials live in 04_app/gateway/.credentials ("user:password").

Run with the TTS env (has fastapi/uvicorn/httpx):  ./run_demo.sh
"""
import asyncio
import base64
import hashlib
import hmac
import html
import json as _json
import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, quote

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
WEBSITE = HERE.parent / "website"
WEBSITE_V2 = HERE.parent / "website_v2"   # redesign preview, served at /v2/ (same APIs, same login)
TTS_UPSTREAM = os.environ.get("TTS_UPSTREAM", "http://127.0.0.1:8100")
USER, PASSWORD = (HERE / ".credentials").read_text().strip().split(":", 1)
# optional second password for the judges (shown in the deck/video); delete .judge_password to revoke it
JUDGE_FILE = HERE / ".judge_password"
JUDGE_PASSWORD = JUDGE_FILE.read_text().strip() if JUDGE_FILE.exists() else ""

COOKIE = "adian_session"
SESSION_TOKEN = hmac.new(PASSWORD.encode(), b"adian-session-v1", hashlib.sha256).hexdigest()
ACCESS_KEY = hmac.new(PASSWORD.encode(), b"adian-link-v1", hashlib.sha256).hexdigest()[:20]
JUDGE_TOKEN = hmac.new(JUDGE_PASSWORD.encode(), b"adian-judge-v1", hashlib.sha256).hexdigest() if JUDGE_PASSWORD else ""
# separate key for the shareable no-password link (/v2/?share=...); delete .share_key and restart to revoke it
SHARE_FILE = HERE / ".share_key"
SHARE_KEY = SHARE_FILE.read_text().strip() if SHARE_FILE.exists() else ""
SHARE_TOKEN = hmac.new(SHARE_KEY.encode(), b"adian-share-v1", hashlib.sha256).hexdigest() if SHARE_KEY else ""
PUBLIC_PATHS = {"/login", "/robots.txt", "/assets/adian.svg", "/v2/favicon.ico", "/v2/assets/favicon-32.png",   # login page assets, including the tab icon
                "/favicon.ico", "/assets/favicon-32.png", "/assets/favicon-192.png", "/assets/apple-touch-icon.png"}  # the mascot image is shown on the login page

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
client = httpx.AsyncClient(base_url=TTS_UPSTREAM, timeout=120)


def is_https(request: Request) -> bool:
    return request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"


def with_session(response: Response, request: Request, token: str = SESSION_TOKEN) -> Response:
    response.set_cookie(COOKIE, token, max_age=30 * 24 * 3600, httponly=True,
                        samesite="lax", secure=is_https(request), path="/")
    return response


def authorized(request: Request) -> bool:
    cookie = request.cookies.get(COOKIE, "")
    if secrets.compare_digest(cookie, SESSION_TOKEN) or (JUDGE_TOKEN and secrets.compare_digest(cookie, JUDGE_TOKEN)) \
            or (SHARE_TOKEN and secrets.compare_digest(cookie, SHARE_TOKEN)):
        return True
    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode().partition(":")
            return secrets.compare_digest(user, USER) and secrets.compare_digest(pw, PASSWORD)
        except Exception:
            return False
    return False


@app.middleware("http")
async def auth(request: Request, call_next):
    path = request.url.path
    # /v2/ pages call relative URLs (api/…, tts, asr): send those to the shared endpoints
    if path.startswith("/v2/") and path[4:].split("/")[0] in ("api", "tts", "asr", "health"):
        path = path[3:]
        request.scope["path"] = path
        request.scope["raw_path"] = path.encode()
    # shareable link: /?key=... logs in and redirects to the clean URL
    key = request.query_params.get("key")
    if key is not None:
        if secrets.compare_digest(key, ACCESS_KEY):
            return with_session(RedirectResponse(path or "/", status_code=303), request)
        await asyncio.sleep(1)
    share = request.query_params.get("share")
    if share is not None:
        if SHARE_KEY and secrets.compare_digest(share, SHARE_KEY):
            return with_session(RedirectResponse(path or "/", status_code=303), request, SHARE_TOKEN)
        await asyncio.sleep(1)
    if path not in PUBLIC_PATHS and not authorized(request):
        if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
            return RedirectResponse("/login?next=" + quote(path), status_code=303)
        return Response("Authentication required", status_code=401)
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"  # keep the demo out of search engines
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"  # browsers/Cloudflare must revalidate, so edits show up immediately
    return response


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="32x32" href="/assets/favicon-32.png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png"><title>阿電 Demo｜登入</title>
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px;
         background: #27F550; color: #141B2D; font-family: "Noto Sans TC", -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif; }}
  form {{ width: 100%; max-width: 380px; background: #fff; border: 3px solid #141B2D; border-radius: 22px;
         box-shadow: 6px 6px 0 #141B2D; padding: 28px 24px; text-align: center; }}
  img {{ width: 150px; }}
  h1 {{ font-size: 1.5rem; margin: 6px 0 4px; }}
  p {{ color: #4B5568; margin-bottom: 16px; }}
  input {{ width: 100%; font-size: 1.1rem; padding: 12px 16px; border: 2px solid #141B2D; border-radius: 999px; }}
  button {{ margin-top: 14px; width: 100%; font-size: 1.1rem; font-weight: 900; padding: 12px; border: 3px solid #141B2D;
           border-radius: 999px; background: #141B2D; color: #27F550; box-shadow: 4px 4px 0 #141B2D; cursor: pointer; }}
  .err {{ color: #C2410C; font-weight: 700; margin: 10px 0 0; }}
</style></head><body>
<form method="post" action="/login">
  <img src="/assets/adian.svg" alt="阿電">
  <h1>阿電 Demo</h1>
  <p>2026 和泰 AI 黑客松・請輸入密碼</p>
  <input type="hidden" name="next" value="{next}">
  <input type="password" name="password" placeholder="密碼" autocomplete="current-password" autofocus required>
  <button type="submit">進入</button>
  {error}
</form></body></html>"""


def safe_next(value: str) -> str:
    return value if value.startswith("/") and not value.startswith("//") else "/"


@app.get("/login")
async def login_page(request: Request):
    if authorized(request):
        return RedirectResponse(safe_next(request.query_params.get("next", "/")), status_code=303)
    return HTMLResponse(LOGIN_PAGE.format(next=html.escape(safe_next(request.query_params.get("next", "/"))), error=""))


@app.post("/login")
async def login(request: Request):
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    password = form.get("password", [""])[0]
    nxt = safe_next(form.get("next", ["/"])[0])
    if secrets.compare_digest(password, PASSWORD):
        return with_session(RedirectResponse(nxt, status_code=303), request)
    if JUDGE_PASSWORD and secrets.compare_digest(password, JUDGE_PASSWORD):
        return with_session(RedirectResponse(nxt, status_code=303), request, JUDGE_TOKEN)
    await asyncio.sleep(1)  # slow down guessing
    return HTMLResponse(LOGIN_PAGE.format(next=html.escape(nxt), error='<p class="err">密碼不正確，請再試一次。</p>'),
                        status_code=401)


async def proxy(request: Request, path: str) -> Response:
    upstream = await client.request(request.method, path, params=request.query_params,
                                    content=await request.body(),
                                    headers={"content-type": request.headers.get("content-type", "application/json")})
    keep = {k: v for k, v in upstream.headers.items() if k.lower() in ("content-type", "cache-control")}
    return Response(upstream.content, status_code=upstream.status_code, headers=keep)


# 阿電's voice: Gemini 3.8 Flash TTS (voice Leda, chosen 11/05) on Vertex AI, paid from the GCP credits.
# Only 阿電's own line (text) is sent, never the customer's voice. Every take is cached on disk, so repeated
# lines cost nothing. If Google fails or is slow, the line falls back to the local BreezyVoice server.
# TTS_ENGINE=breezy switches back to BreezyVoice only.
TTS_ENGINE = os.environ.get("TTS_ENGINE", "gemini")
GEMINI_VOICE = os.environ.get("GEMINI_VOICE", "Leda")
GCP_PROJECT = os.environ.get("GCP_PROJECT") or ((HERE / ".gcp_project").read_text().strip()
                                              if (HERE / ".gcp_project").exists() else "")   # private, not in git
GEMINI_URL = (f"https://aiplatform.googleapis.com/v1/projects/{GCP_PROJECT}/locations/global/"
              "publishers/google/models/gemini-3.8-flash-tts:generateContent")   # this model only answers at "global"
GCLOUD = os.path.expanduser("~/google-cloud-sdk/bin/gcloud")
GEMINI_CACHE = HERE / "cache" / "gemini_tts"
_gtoken = {"value": "", "until": 0.0}


async def gemini_token() -> str:
    import time
    if time.time() < _gtoken["until"]:
        return _gtoken["value"]
    proc = await asyncio.create_subprocess_exec(GCLOUD, "auth", "print-access-token",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError("gcloud token failed")
    # gcloud hands back its cached token, which may have only minutes left: refresh often
    _gtoken.update(value=out.decode().strip(), until=time.time() + 8 * 60)
    return _gtoken["value"]


def _gemini_body(text: str) -> dict:
    # send only the line itself: any style instruction would be read aloud
    return {"contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": GEMINI_VOICE}}}}}


def _gemini_cache_file(text: str) -> Path:
    return GEMINI_CACHE / (hashlib.sha256(f"{GEMINI_VOICE}|{text}".encode()).hexdigest() + ".wav")


def _wav_pcm(data: bytes) -> bytes:
    import io, wave
    with wave.open(io.BytesIO(data)) as w:
        return w.readframes(w.getnframes())


def _save_gemini(f: Path, pcm: bytes) -> None:
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    GEMINI_CACHE.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(f)


def _trim_lead(pcm: bytes) -> bytes:
    """Every Gemini take starts with a short click (10-40 ms) and a low hiss before the voice.
    Cut everything up to 60 ms before the voice starts and fade in over those 60 ms."""
    import array
    a = array.array("h", pcm[: len(pcm) // 2 * 2])
    win, onset = 240, None                    # 10 ms windows at 24 kHz
    for i in range(0, len(a) - win, win):
        if sum(x * x for x in a[i:i + win]) / win > 1500 ** 2:
            onset = i
            break
    if onset is None:
        return b""
    start = max(0, onset - 1440)
    out = a[start:]
    ramp = onset - start
    for k in range(ramp):
        out[k] = int(out[k] * k / ramp)
    return out.tobytes()


async def gemini_stream(text: str):
    """Yield raw PCM (16-bit little-endian, 24 kHz, mono) as Gemini produces it: the first sound arrives
    after ~1 s whatever the length, instead of waiting for the whole line (~2-6 s)."""
    f = _gemini_cache_file(text)
    if f.exists():
        pcm = _wav_pcm(f.read_bytes())
        yield _trim_lead(pcm[:24000 * 2]) + pcm[24000 * 2:] if len(pcm) > 48000 else _trim_lead(pcm)
        return
    pcm, sent = bytearray(), 0                # sent < 0: still looking for where the voice starts
    for attempt in (1, 2):                    # a stale token gives 401: refresh once and retry
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, read=10)) as c:
            async with c.stream("POST", GEMINI_URL.replace(":generateContent", ":streamGenerateContent") + "?alt=sse",
                                json=_gemini_body(text), headers={"Authorization": f"Bearer {await gemini_token()}"}) as r:
                if r.status_code == 401 and attempt == 1:
                    _gtoken["until"] = 0
                    continue
                r.raise_for_status()
                head = None                   # the cleaned-up start, sent once the voice has begun
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    for part in _json.loads(line[5:]).get("candidates", [{}])[0].get("content", {}).get("parts", []):
                        data = part.get("inlineData", {}).get("data")
                        if not data:
                            continue
                        pcm += base64.b64decode(data)
                        if head is None:
                            trimmed = _trim_lead(bytes(pcm))
                            if trimmed or len(pcm) > 24000 * 2:   # voice found (or 1 s of nothing: send as is)
                                head = trimmed or bytes(pcm)
                                sent = len(pcm)
                                yield head
                        else:
                            yield bytes(pcm[sent:])
                            sent = len(pcm)
                if head is None and pcm:
                    yield bytes(pcm)
        break
    if pcm:
        _save_gemini(f, bytes(pcm))   # complete take only: an interrupted line is never cached


async def tts_any(request: Request) -> Response:
    if TTS_ENGINE == "gemini":
        try:
            if request.method == "POST":
                text = (_json.loads(await request.body() or b"{}").get("text") or "").strip()
            else:
                text = request.query_params.get("text", "").strip()
            if text and len(text) <= 600:
                gen = gemini_stream(text)
                first = await gen.__anext__()   # fail over to BreezyVoice only before any sound was sent

                async def body():
                    yield first
                    try:
                        async for chunk in gen:
                            yield chunk
                    except Exception as e:
                        print("gemini tts broke mid-line:", repr(e)[:200], flush=True)
                return StreamingResponse(body(), media_type="audio/L16; rate=24000; channels=1",
                                         headers={"cache-control": "no-store", "x-accel-buffering": "no"})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("gemini tts failed, using BreezyVoice:", repr(e)[:200], flush=True)
    return await proxy(request, "/tts")


@app.api_route("/tts", methods=["GET", "POST"])
async def tts(request: Request):
    # if the browser gives up on this line (the visitor interrupted), drop it upstream too,
    # so the TTS server can skip it instead of delaying newer lines
    await request.body()  # read (and cache) the body first, before polling for a disconnect
    task = asyncio.create_task(tts_any(request))
    while not task.done():
        if await request.is_disconnected():
            task.cancel()
            return Response(status_code=499)
        await asyncio.wait({task}, timeout=0.1)
    return task.result()


@app.get("/health")
async def health(request: Request):
    return await proxy(request, "/health")


ASR_UPSTREAM = os.environ.get("ASR_UPSTREAM", "http://127.0.0.1:8101")


@app.post("/asr")
async def asr(request: Request):
    # speech-to-text: the page records WAV and sends it here; Breeze-ASR-25 runs on the lab GPU
    data = await request.body()
    if len(data) > 5_000_000:
        return Response("audio too long", status_code=413)
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{ASR_UPSTREAM}/asr", params={"prompt": request.query_params.get("prompt", "")[:400]}, content=data,
                             headers={"content-type": request.headers.get("content-type", "audio/wav")})
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    except Exception:
        return Response('{"text": "", "error": "asr offline"}', status_code=503, media_type="application/json")


# ---------- EV charging stations (TDX) + driving routes (OSRM) for the week simulation ----------
import math
import threading

import tdx

EV = {"stations": [], "updated": None, "status": "no-data"}


def _load_ev(refresh_if_stale=True):
    data, stale = tdx.load_cache()
    if data:
        EV.update(stations=data["stations"], updated=data["updated"], status="ok")
    if (stale or not data) and refresh_if_stale and tdx.credentials():
        def worker():
            try:
                out = tdx.fetch_all(verbose=False)
                EV.update(stations=out["stations"], updated=out["updated"], status="ok")
            except Exception as e:  # keep serving the old cache
                EV["status"] = EV["status"] if EV["stations"] else f"error: {e}"
        threading.Thread(target=worker, daemon=True).start()


_load_ev()


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


@app.get("/api/ev/status")
async def ev_status():
    return {"status": EV["status"], "updated": EV["updated"], "count": len(EV["stations"]),
            "has_credentials": bool(tdx.credentials())}


@app.get("/api/ev/nearby")
async def ev_nearby(lat: float, lon: float, radius_km: float = 5, limit: int = 30, kind: str = "city", compatible: int = 1):
    items = []
    for s in EV["stations"]:
        if kind != "all" and s["kind"] != kind:
            continue
        if compatible and not s.get("compatible"):  # only connectors a bZ4X can use (CCS1 DC / J1772 AC)
            continue
        d = _km(lat, lon, s["lat"], s["lon"])
        if d <= radius_km:
            items.append({**s, "distance_km": round(d, 2)})
    items.sort(key=lambda s: s["distance_km"])
    nearest_fast = next((s["distance_km"] for s in items if s.get("fast")), None)  # used by the charging score C
    return {"updated": EV["updated"], "status": EV["status"], "total": len(items),
            "fast_total": sum(1 for s in items if s.get("fast")), "nearest_fast_km": nearest_fast,
            "stations": items[:max(1, min(limit, 200))]}


@app.get("/api/ev/freeway")
async def ev_freeway():
    return {"updated": EV["updated"], "stations": [s for s in EV["stations"] if s["kind"] == "freeway"]}


# Google Photorealistic 3D Tiles for the 3D drive simulation (website_v2/assets/sim3d.js).
# Browser key restricted to the Map Tiles API and our domains, capped at 200 sessions/day in GCP.
# Read on every request: delete .maps_key to turn 3D off (the page then falls back to the 2D map).
MAPS_KEY_FILE = HERE / ".maps_key"


@app.get("/api/maps-config")
async def maps_config():
    key = MAPS_KEY_FILE.read_text().strip() if MAPS_KEY_FILE.exists() else ""
    return Response(_json.dumps({"key": key}), media_type="application/json", headers={"Cache-Control": "no-store"})


ROUTE_CACHE: dict = {}


@app.get("/api/route")
async def route(src: str, dst: str, geometry: int = 0):
    """src/dst as 'lat,lon'. Driving distance and duration from the public OSRM server (cached)."""
    key = (src, dst, geometry)
    if key in ROUTE_CACHE:
        return ROUTE_CACHE[key]
    (la1, lo1), (la2, lo2) = [tuple(float(x) for x in p.split(",")) for p in (src, dst)]
    overview = {0: "false", 2: "full"}.get(geometry, "simplified")  # 2 = every road point, for the 3D drive
    url = (f"https://router.project-osrm.org/route/v1/driving/{lo1},{la1};{lo2},{la2}"
           f"?overview={overview}&geometries=geojson")
    try:
        async with httpx.AsyncClient(timeout=6, headers={"user-agent": "adian-hackathon-demo/0.1"}) as c:  # slow answers fall back to an estimate
            r = await c.get(url)
            r.raise_for_status()
            best = r.json()["routes"][0]
        out = {"km": round(best["distance"] / 1000, 1), "minutes": round(best["duration"] / 60),
               "coords": [[p[1], p[0]] for p in best["geometry"]["coordinates"]] if geometry else None, "source": "osrm"}
    except Exception:
        # fallback: straight line x 1.3 at 40 km/h average
        d = _km(la1, lo1, la2, lo2) * 1.3
        out = {"km": round(d, 1), "minutes": round(d / 40 * 60), "coords": None, "source": "estimate"}
    ROUTE_CACHE[key] = out
    return out



# ---------- LLM: understand free-text answers and off-script questions (local Gemma via Ollama) ----------
# The conversation flow and every number stay in the page's code; the LLM only maps what the user typed
# to one of the allowed answers, or answers a side question from the FACTS below. Output is validated here.
import json as _json
import re as _re

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:26b")
DISTRICTS = {c: list(ds) for c, ds in _json.loads((WEBSITE / "assets" / "districts.json").read_text())["counties"].items()}

FACTS = """bZ4X（台灣，Toyota 官網 2025/10 規配）：建議售價 128 萬元；單一車型；前輪驅動；最大馬力 227 ps、扭力 27.4 kgm；
電池 74.7 kWh；續航 743 km（NEDC，實際以約 520 km 保守估算）；電能效率 6.7 km/kWh；5 人座；
AC 慢充 SAE J1772、6.6 kW，0→100% 約 10 小時；DC 快充 CCS1、150 kW，約 30 分鐘到 80%；
TSS 3.0（PCS、全速域 ACC、LTA）、8 具 SRS 氣囊、SEA 安全離座警示、環景影像（附底盤透視）、14 吋螢幕、無線 CarPlay／Android Auto、後車廂 110V 插座。
每公里電費約 1 元（在家充電約 0.5 元），汽油約 3–4 元；定期保養費約比同級汽油休旅低六成（和泰會員資料）。
電動車使用牌照稅、燃料費（公路養管費）現行免徵至 2030 年底。
電池保固等正式條件：不要給數字，說會請業務提供。不知道的事就說不知道，不要編造。"""

SYSTEM = """你是「阿電」，和泰汽車的誠實電動車顧問，一台可愛的綠色電動車吉祥物。你正在和車主聊天，幫他判斷換電動車適不適合他。
說話要像真人：台灣華語、繁體中文、親切自然、口語、簡短，不要像客服罐頭訊息。
你會收到：最近的對話、你剛剛問的問題、允許的選項（可能為空）、使用者最新的訊息。只輸出 JSON：
{"intent": "answer" | "chat", "value": ..., "reply": "..."}

intent=answer（使用者回答了你的問題，即使說法很口語）：
- value 必須「完全等於」允許選項之一；地點題 value 為 {"county": "XX市/縣", "district": "XX區/鄉/鎮/市" 或 null}（用「台」不用「臺」）；公里題 value 為整數。
- reply：一句很短的自然回應（15 字內，不要問問題），例如「上下班通勤啊，了解！」「好，記下來了！」。

intent=chat（打招呼、聊別的、問問題、看不懂你在問什麼、用別的語言、亂打字……）：
- reply 先自然地回應他說的話（1–2 句）：
  - 打招呼就親切打招呼；用越南文、英文等其他語言，就用中文簡單說你目前只會說中文，並親切回應。
  - 問「你要問什麼」「什麼意思」：用更白話的方式解釋剛剛的問題為什麼要問。
  - 問車子、充電、價格等：只根據【事實】回答；不知道就老實說會請業務確認，絕不編造數字。
  - 無意義的字：輕鬆幽默地帶過。
- 然後換句話再問一次剛剛的問題，如果有選項就自然地舉出選項。
- reply 總長 90 字內，不要用 emoji、不要用 markdown。

不論 intent 為何，如果使用者「順便」提到其他項目的資訊（例如要坐 7 個人、家裡不能充電、一天開 50 公里），
把它放進 "extra"：{"項目代號": 值}；值必須「完全等於」該項目的選項之一（km 為整數）。沒有就給 {}。
例如：「但我要開 7 人座的車」→ "extra": {"seats": "6 人以上"}；「我家大樓不能裝充電樁」→ "extra": {"charge": "都不行"}；「我住透天，還沒裝充電樁」→ "extra": {"charge": "還沒有，但可以裝"}。
完整輸出格式：{"intent": ..., "value": ..., "reply": ..., "extra": {...}}

【事實】
""" + FACTS

def _place(value, home_county):
    if not isinstance(value, dict):
        return None
    county = (value.get("county") or "").replace("臺", "台").strip()
    district = (value.get("district") or "").replace("臺", "台").strip()
    if county and county not in DISTRICTS:
        county = next((c for c in DISTRICTS if c.startswith(county[:2])), "")
    if district:
        def find(c):
            return next((d for d in DISTRICTS.get(c, []) if d == district or d[:-1] == district or d.startswith(district)), None)
        for c in ([county] if county else []) + [home_county] + list(DISTRICTS):
            d = find(c)
            if d:
                return {"county": c, "district": d}
    return {"county": county, "district": None} if county else None


@app.post("/api/ask")
async def ask(request: Request):
    body = await request.json()
    key, text = str(body.get("key", "")), str(body.get("text", ""))[:300]
    options = [str(o) for o in (body.get("options") or [])][:20]
    home = str(body.get("homeCounty") or "")
    slots = {str(k): [str(o) for o in v][:12] if isinstance(v, list) else "整數（公里）"
             for k, v in (body.get("slots") or {}).items() if k != key and k in ("seats", "charge", "lifestyle", "weekend", "worry", "km")}
    kind = "place" if key in ("work", "district") else "km" if key == "km" else "options"
    history = "\n".join(f"{'使用者' if h.get('role') == 'user' else '阿電'}：{str(h.get('text', ''))[:200]}"
                        for h in (body.get("history") or [])[-8:] if isinstance(h, dict))
    user = (f"最近的對話：\n{history or '（無）'}\n"
            f"你剛剛問的問題：{body.get('question', '')}\n"
            f"問題類型：{ {'place': '地點（縣市＋行政區）', 'km': '每日公里數', 'options': '選擇題'}[kind] }\n"
            f"允許的選項：{_json.dumps(options, ensure_ascii=False) if options else '（無）'}\n"
            f"使用者住在：{home or '未知'}{body.get('homeDistrict') or ''}\n"
            f"其他項目（可放進 extra）：{_json.dumps(slots, ensure_ascii=False) if slots else '（無）'}\n"
            f"使用者最新的訊息：{text}")
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(f"{OLLAMA}/api/chat", json={
                "model": LLM_MODEL, "stream": False, "think": False, "format": "json", "keep_alive": "24h",
                "options": {"temperature": 0.4, "num_predict": 220},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]})
            r.raise_for_status()
            out = _json.loads(r.json()["message"]["content"])
    except Exception as e:
        return {"intent": "error", "value": None, "reply": "", "detail": str(e)[:120]}
    intent = "answer" if out.get("intent") == "answer" else "chat"
    value, reply = out.get("value"), _re.sub(r"<[^>]+>", "", str(out.get("reply") or ""))[:240]
    if intent == "answer":  # never trust the model blindly
        if kind == "place":
            value = _place(value, home)
        elif kind == "km":
            try:
                value = int(float(value)); value = value if 5 <= value <= 500 else None
            except Exception:
                value = None
        else:
            value = value if value in options else None
        if value is None:
            intent, reply = "chat", ""
    if intent == "chat" and not reply:
        reply = f"抱歉，我不太確定你的意思。{body.get('question', '')}"
    extra = {}
    for k, v in (out.get("extra") or {}).items() if isinstance(out.get("extra"), dict) else []:
        if k not in slots:
            continue
        if k == "km":
            try:
                n = int(float(v))
                if 5 <= n <= 500:
                    extra[k] = n
            except Exception:
                pass
        elif v in slots[k]:
            extra[k] = v
    return {"intent": intent, "value": value, "reply": reply, "extra": extra}


# ---------------------------------------------------------------------------------------------
# 11/12: places near home (OpenStreetMap Overpass → TDX names), geocoding (Nominatim), and one-sentence week plans (Gemma)
# Both OSM services are free/fair-use: at most 1 request a second each, results cached on disk for 72 h.
# ---------------------------------------------------------------------------------------------
import time as _time

POI_CACHE = HERE / "cache" / "poi"
GEO_CACHE = HERE / "cache" / "geocode"
UA = {"User-Agent": "adian-hackathon-demo/1.0"}
_osm_lock = {"overpass": asyncio.Lock(), "nominatim": asyncio.Lock()}
_osm_last = {"overpass": 0.0, "nominatim": 0.0}
POI_KINDS = {
    "market": ['nwr["shop"="supermarket"]', 'nwr["amenity"="marketplace"]', 'nwr["shop"="greengrocer"]'],
    "gym": ['nwr["leisure"="fitness_centre"]', 'nwr["leisure"="sports_centre"]'],
    "clinic": ['nwr["amenity"="hospital"]', 'nwr["amenity"="clinic"]'],
    "cram": ['nwr["amenity"="prep_school"]', 'nwr["name"~"補習|文理|美語|安親"]'],
    "school": ['nwr["amenity"="school"]["name"~"國小|國民小學|小學|實小"]'],
    "park": ['nwr["leisure"="park"]["name"]'],
    "mall": ['nwr["shop"="mall"]', 'nwr["shop"="department_store"]', 'nwr["name"~"好市多|Costco|家樂福|大遠百|百貨|購物中心"]'],
    "attraction": ['nwr["tourism"~"attraction|viewpoint|theme_park"]["name"]', 'nwr["leisure"="nature_reserve"]["name"]'],
}
# Nominatim keyword search inside a box around the point (Overpass public servers are often overloaded)
POI_NOMI = {"market": ["全聯", "市場"], "gym": ["運動中心", "健身"], "clinic": ["醫院", "診所"], "cram": ["補習班"],
            "school": ["國小"], "park": ["公園"], "mall": ["百貨", "好市多"], "attraction": []}
POI_NOMI_TYPES = {"clinic": {"clinic", "hospital", "doctors"}, "gym": {"sports_centre", "fitness_centre", "stadium", "pitch"}}
POI_TDX = {"market": r"市場|全聯|家樂福|超市", "gym": r"運動中心|健身|體育", "clinic": r"醫院|診所", "cram": r"補習",
           "school": r"國小|小學", "park": r"公園", "mall": r"百貨|大遠百|好市多|Costco|家樂福|購物|商場|廣場", "attraction": r"風景|遊客中心|園區|農場"}


async def _polite(service):
    async with _osm_lock[service]:
        wait = 1.1 - (_time.time() - _osm_last[service])
        if wait > 0:
            await asyncio.sleep(wait)
        _osm_last[service] = _time.time()


def _disk_get(folder: Path, key: str, max_age=72 * 3600):
    f = folder / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")
    if f.exists() and _time.time() - f.stat().st_mtime < max_age:
        try:
            return _json.loads(f.read_text())
        except Exception:
            return None
    return None


def _disk_put(folder: Path, key: str, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (hashlib.sha256(key.encode()).hexdigest()[:24] + ".json")).write_text(_json.dumps(data, ensure_ascii=False))


@app.get("/api/poi")
async def api_poi(kind: str, lat: float, lon: float, radius_km: float = 3, limit: int = 8, min_km: float = 0):
    if kind not in POI_KINDS:
        return {"items": [], "source": "none", "error": "unknown kind"}
    radius_km = max(0.3, min(radius_km, 60)); limit = max(1, min(limit, 30))
    key = f"{kind}|{lat:.3f}|{lon:.3f}|{radius_km:.1f}"
    raw = _disk_get(POI_CACHE, key)
    source = "osm"
    if raw is None:
        q = "[out:json][timeout:20];(" + "".join(f"{sel}(around:{int(radius_km * 1000)},{lat},{lon});" for sel in POI_KINDS[kind]) + ");out center 120;"
        try:
            await _polite("overpass")
            async with httpx.AsyncClient(timeout=8, headers=UA) as c:
                r = await c.post("https://overpass-api.de/api/interpreter", data={"data": q})
                r.raise_for_status()
                raw = []
                for e in r.json().get("elements", []):
                    t = e.get("tags", {})
                    name = t.get("name:zh-TW") or t.get("name:zh") or t.get("name")
                    la, lo = e.get("lat") or (e.get("center") or {}).get("lat"), e.get("lon") or (e.get("center") or {}).get("lon")
                    if name and la and lo:
                        raw.append({"name": name, "lat": la, "lon": lo})
                _disk_put(POI_CACHE, key, raw)
        except Exception:
            raw = None
    if not raw and POI_NOMI[kind] and radius_km <= 8:   # Nominatim keyword search in a box around the point
        dlat, dlon = radius_km / 111, radius_km / (111 * max(0.3, math.cos(lat * math.pi / 180)))
        found = []
        for word in POI_NOMI[kind]:
            try:
                await _polite("nominatim")
                async with httpx.AsyncClient(timeout=10, headers=UA) as c:
                    r = await c.get("https://nominatim.openstreetmap.org/search", params={
                        "format": "jsonv2", "limit": 20, "accept-language": "zh-TW", "bounded": 1, "q": word,
                        "viewbox": f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"})
                    r.raise_for_status()
                    for x in r.json():
                        if kind in POI_NOMI_TYPES and x.get("type") not in POI_NOMI_TYPES[kind] and not _re.search("運動中心|健身|醫院", x.get("name") or ""):
                            continue
                        if x.get("name"):
                            found.append({"name": x["name"], "lat": float(x["lat"]), "lon": float(x["lon"])})
            except Exception:
                pass
            if len(found) >= 3:
                break
        if found:
            raw = found; source = "osm"
            _disk_put(POI_CACHE, key, raw)
    if not raw:  # fall back to TDX charger site names (real places that also have a bZ4X-usable charger)
        source = "tdx"
        pat = _re.compile(POI_TDX[kind])
        clean = lambda n: _re.sub(r"(B\d+)?(地下)?(停車場|充電站)$", "", _re.sub(r"^[^_]{1,12}_", "", n)).strip() or n
        raw = [{"name": clean(s["name"]), "lat": s["lat"], "lon": s["lon"]} for s in EV["stations"]
               if s.get("compatible") and pat.search(s.get("name", "")) and _km(lat, lon, s["lat"], s["lon"]) <= radius_km]
    seen, items = set(), []
    for it in raw:
        d = _km(lat, lon, it["lat"], it["lon"])
        if d < min_km or d > radius_km or it["name"] in seen:
            continue
        seen.add(it["name"]); items.append({**it, "km": round(d, 2)})
    items.sort(key=lambda x: x["km"])
    return {"items": items[:limit], "source": source if items else "none"}


@app.get("/api/geocode")
async def api_geocode(q: str):
    q = q.strip()[:120]
    if not q:
        return {}
    hit = _disk_get(GEO_CACHE, q, max_age=30 * 86400)
    if hit is not None:
        return hit
    out = {}
    try:
        await _polite("nominatim")
        async with httpx.AsyncClient(timeout=12, headers=UA) as c:
            r = await c.get("https://nominatim.openstreetmap.org/search", params={
                "format": "jsonv2", "countrycodes": "tw", "limit": 1, "accept-language": "zh-TW", "addressdetails": 1, "q": q})
            r.raise_for_status()
            j = r.json()
        if j:
            a = j[0].get("address", {})
            vals = [str(v).replace("臺", "台") for v in a.values()]
            county = next((v for v in vals if v in DISTRICTS), "")
            district = next((v for v in vals if county and v in DISTRICTS[county]), "")
            out = {"name": j[0].get("name") or q, "lat": float(j[0]["lat"]), "lon": float(j[0]["lon"]), "county": county, "district": district}
    except Exception:
        return {}
    _disk_put(GEO_CACHE, q, out)
    return out


PLAN_SYSTEM = """你是「阿電」，和泰汽車的誠實電動車顧問。使用者會用一兩句話描述他平常一週怎麼用車。
你的工作只有一個：把他說的內容整理成 JSON，給程式畫出他的一週。不要計算任何數字，也不要編造他沒說的事。沒提到的欄位填 null 或空陣列。
只輸出 JSON，格式：
{
 "anchor": "office"（平日去公司或固定地點上班；「開車去上班」「開車去工作」「開車去公司」都是 office）| "home"（在家工作、家管、在家做生意、退休）| "roam"（只有明說跑客戶、外送、跑業務、送貨、到處跑才是 roam）| null,
 "work": {"county": "XX市/縣", "district": "XX區"} 或 null（平日上班或常跑的地方；用「台」不用「臺」；說了好幾區就填第一個）,
 "wdays": 1–7 的整數或 null（一週去公司幾天；週六也上班＝6、天天上班／一週七天＝7）,
 "kids": true | false | null（要不要接送小孩）,
 "kmode": "both"（早上送、下午接）| "am" | "pm" | null,
 "school": "學校名稱" 或 null,
 "wx": 平日其他固定行程，只能用這些代號的陣列：["market"（買菜、超市、市場）, "gym"（健身、運動、瑜伽）, "parents"（載爸媽看醫生、探望長輩）, "cram"（接小孩補習班）],
 "wkd": 週末，最多兩個，依週六、週日順序，只能用：["mall"（逛街、百貨、賣場、好市多）, "park"（公園、戶外走走、運動、打球、騎車）, "hometown"（回老家）, "outing"（出遊、一日遊）, "home"（在家休息）],
 "hometown": {"county": "XX市/縣", "district": "XX區" 或 null} 或 null（老家在哪）,
 "home": {"county": "XX市/縣", "district": "XX區"} 或 null（使用者自己現在住在哪；只有他說了「我住在…」「家在…」才填，不要拿公司或老家來填）,
 "age": 使用者自己的年齡整數或 null（只有他說了才填）,
 "car_years": 現在這台車開了幾年的整數或 null（例如「開了七年」＝7；說「去年買的」＝1）,
 "outing": "一日遊的地點" 或 null,
 "trip": [{"name": "地點", "nights": 整數}]（最多 3 個，有提到要出遠門旅行才填，否則 []；nights 是住幾晚：玩三天＝2、三天兩夜＝2、一週＝6）,
 "charge": "是，家裡可以" | "還沒有，但可以裝" | "是，公司可以" | "都不行" | "不確定" | null,
 "km": 每天大約開幾公里的整數或 null（只有他自己說了數字才填）,
 "seats": "1 到 2 人" | "3 到 5 人" | "6 人以上" | null,
 "other": "其他沒辦法放進上面欄位的行程，原文簡短寫下" 或 "",
 "reply": "一句很短、自然的台灣華語回應（25 字內），例如「了解！平日上班、週末回台中老家。」"
}"""
PLAN_ENUM = {"anchor": {"office", "home", "roam"}, "kmode": {"both", "am", "pm"},
             "charge": {"是，家裡可以", "還沒有，但可以裝", "是，公司可以", "都不行", "不確定"}, "seats": {"1 到 2 人", "3 到 5 人", "6 人以上"}}


# 11/13: real-user test feedback. One JSON line per session in gateway/feedback/feedback.jsonl (lab machine only,
# never uploaded). No name or address: a tester code (T01, T02… or what the team typed), the scores, the free text,
# and a short summary of the session (car, week blocks, verdict). Values are validated and size-limited.
FEEDBACK_DIR = HERE / "feedback"
_fb_lock = asyncio.Lock()


@app.post("/api/feedback")
async def api_feedback(request: Request):
    import datetime
    try:
        body = await request.json()
    except Exception:
        return {"ok": False}
    def score(v):
        try:
            n = int(v)
            return n if 1 <= n <= 5 else None
        except Exception:
            return None
    ans = body.get("answers") or {}
    rec = {
        "scores": {k: score(ans.get(k)) for k in ("verdict", "week", "easy")},
        "testdrive": ans.get("testdrive") if ans.get("testdrive") in ("想", "也許", "不想") else None,
        "comment": str(ans.get("comment") or "")[:800],
    }
    summ = body.get("summary") or {}
    rec["summary"] = {str(k)[:24]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:160])
                      for k, v in list(summ.items())[:40]} if isinstance(summ, dict) else {}
    code = _re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("tester") or ""))[:12]
    async with _fb_lock:
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        f = FEEDBACK_DIR / "feedback.jsonl"
        n = sum(1 for _ in f.open(encoding="utf-8")) if f.exists() else 0
        rec = {"id": code or f"T{n + 1:02d}", "at": datetime.datetime.now().isoformat(timespec="seconds"), **rec}
        with f.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "id": rec["id"]}


@app.post("/api/plan")
async def api_plan(request: Request):
    body = await request.json()
    text = str(body.get("text", ""))[:400]
    home = str(body.get("homeCounty") or "")
    user = f"使用者住在：{home or '未知'}{body.get('homeDistrict') or ''}\n使用者說：{text}"
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{OLLAMA}/api/chat", json={
                "model": LLM_MODEL, "stream": False, "think": False, "format": "json", "keep_alive": -1,
                "options": {"temperature": 0.2, "num_predict": 420},
                "messages": [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": user}]})
            r.raise_for_status()
            out = _json.loads(r.json()["message"]["content"])
    except Exception as e:
        return {"ok": False, "detail": str(e)[:120]}
    # never trust the model blindly: keep only valid values
    plan = {}
    for k, allowed in PLAN_ENUM.items():
        if out.get(k) in allowed:
            plan[k] = out[k]
    w = _place(out.get("work"), home)
    if w and w.get("district"):
        plan["work"] = w
    try:
        n = int(out.get("wdays")); plan["wdays"] = n if 1 <= n <= 7 else None
    except Exception:
        pass
    if isinstance(out.get("kids"), bool):
        plan["kids"] = out["kids"]
    if isinstance(out.get("school"), str) and 1 < len(out["school"]) <= 30:
        plan["school"] = out["school"].strip()
    plan["wx"] = [x for x in (out.get("wx") or []) if x in {"market", "gym", "parents", "cram"}][:4] if isinstance(out.get("wx"), list) else []
    plan["wkd"] = [x for x in (out.get("wkd") or []) if x in {"mall", "park", "hometown", "outing", "home"}][:2] if isinstance(out.get("wkd"), list) else []
    hm = _place(out.get("home"), "")
    if hm and hm.get("district"):
        plan["home"] = hm
    for k, lo, hi in (("age", 18, 95), ("car_years", 0, 40)):
        try:
            n = int(float(out.get(k))); plan[k] = n if lo <= n <= hi else None
        except Exception:
            pass
    ht = _place(out.get("hometown"), "")
    if ht and ht.get("county"):
        plan["hometown"] = ht
    if isinstance(out.get("outing"), str) and 1 < len(out["outing"]) <= 30:
        plan["outing"] = out["outing"].strip()
    trip = []
    for t in (out.get("trip") or [])[:3] if isinstance(out.get("trip"), list) else []:
        if isinstance(t, dict) and isinstance(t.get("name"), str) and 1 < len(t["name"]) <= 30:
            try:
                nights = max(0, min(30, int(t.get("nights") or 1)))
            except Exception:
                nights = 1
            trip.append({"name": t["name"].strip(), "nights": nights})
    plan["trip"] = trip
    try:
        km = int(float(out.get("km"))); plan["km"] = km if 5 <= km <= 400 else None
    except Exception:
        pass
    plan["other"] = str(out.get("other") or "")[:80]
    plan = {k: v for k, v in plan.items() if v not in (None, "")}
    return {"ok": True, "plan": plan, "reply": _re.sub(r"<[^>]+>", "", str(out.get("reply") or ""))[:60]}


@app.on_event("startup")
async def _warm_llm():
    async def warm():  # load the model into GPU memory so the first visitor does not wait
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                await c.post(f"{OLLAMA}/api/generate", json={"model": LLM_MODEL, "prompt": "", "keep_alive": "24h"})
        except Exception:
            pass
    asyncio.create_task(warm())


# ---------- 11/16：阿電知識庫（RAG）。只用官方公開資料，回答附出處；找不到就老實說 ----------
import kb as _kb


@app.on_event("startup")
async def _load_kb():
    async def go():
        try:
            n = await _kb.load(OLLAMA)
            print(f"knowledge base: {n} passages", flush=True)
        except Exception as e:
            print("knowledge base not loaded:", str(e)[:120], flush=True)
    asyncio.create_task(go())


@app.post("/api/kb")
async def api_kb(request: Request):
    body = await request.json()
    q = str(body.get("q", "")).strip()[:200]
    if not q:
        return {"found": False, "sources": []}
    try:
        return await _kb.answer(OLLAMA, LLM_MODEL, q, str(body.get("context", ""))[:60])
    except Exception as e:
        return {"found": False, "error": str(e)[:120], "sources": []}


@app.get("/robots.txt")
async def robots():
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain")


app.mount("/v2", StaticFiles(directory=WEBSITE_V2, html=True, check_dir=False), name="website_v2")
app.mount("/", StaticFiles(directory=WEBSITE, html=True), name="website")


if __name__ == "__main__":
    import uvicorn
    print("Share link key:", ACCESS_KEY)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("DEMO_PORT", "8080")))
