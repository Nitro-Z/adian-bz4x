"""Fetch 阿電's voice for each line through the gateway (/tts = Gemini Leda, disk-cached there; new lines cost a little).

  python fetch_tts.py cues.json OUTDIR   -> OUTDIR/<sha1>.wav (24 kHz mono) + OUTDIR/mouth.json

mouth.json: text -> {"wav": path, "dur": seconds, "m": [mouth per 1/30 s]}. The mouth rule follows adian-avatar.js:
loudness relative to the recent peak; closed < 0.45, half, open > 0.78; every shape is held at least 70 ms.
Never prints the access key.
"""
import hashlib, http.cookiejar, json, os, sys, urllib.request, wave
import numpy as np

ROOT = "/home/lab/Jackie_Pham/和泰汽車黑客松/04_app"
KEY = open(f"{ROOT}/gateway/.access_key").read().strip()
BASE = "http://127.0.0.1:8080"
FPS = 30


def opener():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        op.open(f"{BASE}/v2/assets/personas.json?key={KEY}", timeout=30).read()
    except Exception as e:
        raise SystemExit("login failed: " + type(e).__name__)
    return op


def mouth_track(pcm, sr=24000):
    x = pcm.astype(np.float32) / 32768
    hop = sr // FPS
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) if len(x[i:i + hop]) else 0 for i in range(0, len(x), hop)])
    out, peak, cur, held = [], 1e-4, "mouth", 99
    for v in rms:
        peak = max(peak * 0.97, v, 1e-4)          # recent peak, decays over ~1 s
        r = v / peak
        want = "mouth" if r < 0.45 or v < 0.01 else ("mouth-open" if r > 0.78 else "mouth-half")
        if want != cur and held >= 2:             # hold each shape >= 2 frames (~70 ms)
            cur, held = want, 0
        else:
            held += 1
        out.append(cur)
    return out


def main():
    cues, outdir = json.load(open(sys.argv[1])), sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    op = opener()
    texts = list(dict.fromkeys(c["text"] for c in (cues["cues"] if isinstance(cues, dict) else cues)))
    res = {}
    for t in texts:
        f = os.path.join(outdir, hashlib.sha1(t.encode()).hexdigest()[:16] + ".wav")
        if not os.path.exists(f):
            req = urllib.request.Request(f"{BASE}/tts", data=json.dumps({"text": t}).encode(), headers={"content-type": "application/json"}, method="POST")
            with op.open(req, timeout=60) as r:
                ctype, body = r.headers.get("content-type", ""), r.read()
            if "L16" in ctype:
                with wave.open(f, "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(body)
            else:                                   # BreezyVoice fallback answers with a WAV file
                open(f, "wb").write(body)
        with wave.open(f) as w:
            sr, pcm = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            if w.getnchannels() == 2: pcm = pcm[::2]
        res[t] = {"wav": f, "dur": len(pcm) / sr, "sr": sr, "m": mouth_track(pcm, sr)}
        print(f"{res[t]['dur']:5.2f}s  {t}")
    json.dump(res, open(os.path.join(outdir, "mouth.json"), "w"), ensure_ascii=False)


main()
