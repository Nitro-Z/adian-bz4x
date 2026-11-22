"""Synthesize the demo lines via the running server, save to samples/, print stats."""
import io, json, re, sys, time, urllib.request
import numpy as np, soundfile as sf
URL = "http://localhost:8100"
LINES = [
    ("01_greeting", "嗨！我是阿電，你的誠實電動車顧問。"),
    ("02_benefits", "換電動車的好處很多：每公里電費大約一元、定期保養費低約六成，開起來安靜又有力。"),
    ("03_range", "官方續航七百四十三公里是NEDC標準，實際會比較少。"),
    ("04_mixed", "bZ4X 有 TSS 3.0 和無線 CarPlay。"),
]
def post(text):
    req = urllib.request.Request(URL + "/tts", json.dumps({"text": text, "voice": "default"}).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.time(); r = urllib.request.urlopen(req); data = r.read()
    return data, time.time() - t0, r.headers.get("X-TTS-Cache")
rows = []
for name, text in LINES:
    d1, t1, c1 = post(text); d2, t2, c2 = post(text)
    assert d1 == d2
    open(f"samples/{name}.wav", "wb").write(d1)
    a, sr = sf.read(io.BytesIO(d1)); dur = len(a) / sr
    rms = float(np.sqrt(np.mean(a ** 2))); nchar = len(re.sub(r"[\s，。！？：、,.!?:]", "", text))
    rows.append(dict(name=name, first_s=round(t1, 2), first_cache=c1, cached_s=round(t2, 4), cached=c2, sr=sr,
                     dur_s=round(dur, 2), rms=round(rms, 4), rms_dbfs=round(20 * np.log10(rms + 1e-12), 1),
                     chars=nchar, chars_per_s=round(nchar / dur, 2)))
    print(rows[-1], flush=True)
print(json.dumps(json.load(urllib.request.urlopen(URL + "/health")), ensure_ascii=False))
