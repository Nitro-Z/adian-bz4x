"""Narrator lines for the v7 demo video (a third voice, not 阿電 / 陳先生): Gemini TTS (Vertex AI, voice from $VOICE,
default Sulafat), cleaned the same way as customer_voice.py.

  python narrator_voice.py OUTDIR      -> OUTDIR/<key>_raw.wav and OUTDIR/<key>.wav (cleaned, 24 kHz mono)

Cleaning (Gemini quirks seen in v5): a ~10 ms click at the very start and a loud ~0.1 s burst after the last word.
We cut both, fade in 15 ms / out 120 ms and set the peak to 0.85. Only these scripted lines are sent to Google;
the gcloud token is never printed.
"""
import base64, json, os, subprocess, sys, urllib.request, wave
import numpy as np

URL = ("https://aiplatform.googleapis.com/v1/projects/" + os.environ.get("GCP_PROJECT", "YOUR_GCP_PROJECT") + "/locations/global/"
       "publishers/google/models/gemini-3.8-flash-tts:generateContent")
VOICE = os.environ.get("VOICE", "Sulafat")
LINES = {
    "n1": "陳先生想換電動車，可是家裡不能充電。他打開了阿電。",
    "n2": "和泰會員登入，車子和年齡，阿電已經知道了。",
    "n3": "他說一句話，阿電就聽懂、填好；其他問題，點一下就好。",
    "n4": "為什麼適合？阿電把他說的一週，放到真實的地圖上。",
    "n5": "先誠實，後銷售。",
}
SR = 24000


def tts(text, tok):
    body = {"contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {tok}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.loads(r.read())
    return b"".join(base64.b64decode(p["inlineData"]["data"]) for p in res["candidates"][0]["content"]["parts"] if "inlineData" in p)


def clean(x):
    x = x.astype(np.float32) / 32768
    hop = SR // 100                                   # 10 ms frames
    rms = np.array([np.sqrt(np.mean(x[i:i + hop] ** 2)) for i in range(0, len(x) - hop, hop)])
    voiced = rms > 0.02
    # voiced islands, gaps under 50 ms merged
    isl, k = [], 0
    while k < len(voiced):
        if voiced[k]:
            s0 = k
            while k < len(voiced) and voiced[k]: k += 1
            if isl and s0 - isl[-1][1] < 5: isl[-1][1] = k
            else: isl.append([s0, k])
        else:
            k += 1
    # start click: a tiny island (<= 30 ms) followed by >= 100 ms of silence
    while len(isl) > 1 and isl[0][1] - isl[0][0] <= 3 and isl[1][0] - isl[0][1] >= 10: isl.pop(0)
    # tail burst: a short island (<= 300 ms) at the very end after >= 150 ms of silence
    while len(isl) > 1 and isl[-1][1] - isl[-1][0] <= 30 and isl[-1][0] - isl[-2][1] >= 15: isl.pop()
    first, last = isl[0][0], isl[-1][1]
    a = max(0, (first - 4) * hop); b = min(len(x), (last + 12) * hop)   # keep 40 ms before, 120 ms after
    y = x[a:b].copy()
    fi, fo = int(0.015 * SR), int(0.12 * SR)
    y[:fi] *= np.linspace(0, 1, fi); y[-fo:] *= np.linspace(1, 0, fo)
    y *= 0.85 / max(1e-6, float(np.abs(y).max()))
    return (y * 32767).astype(np.int16), (a / SR, b / SR, len(x) / SR)


def save(f, pcm):
    with wave.open(f, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes() if hasattr(pcm, "tobytes") else pcm)


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    tok = subprocess.run([os.path.expanduser("~/google-cloud-sdk/bin/gcloud"), "auth", "print-access-token"],
                         capture_output=True, text=True, check=True).stdout.strip()
    for key, text in LINES.items():
        raw = os.path.join(out, key + "_raw.wav")
        if not os.path.exists(raw):
            save(raw, tts(text, tok))
        with wave.open(raw) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        y, (a, b, n) = clean(x)
        save(os.path.join(out, key + ".wav"), y)
        print(f"{key}: raw {n:.2f}s -> kept {a:.2f}-{b:.2f}s ({len(y) / SR:.2f}s)  voice {VOICE}  {text}")


main()
