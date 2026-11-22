import json, sys, urllib.request, difflib, re, subprocess
import whisper, opencc
V = sys.argv[1]
L = json.load(open(f"{V}/script.json")); by = {x["id"]: x for x in L}
IDS = sys.argv[2].split(",")
NEW = {i: (by[i]["cap"], by[i]["say"]) for i in IDS}
m = whisper.load_model("large-v3", download_root="whisper_models", device="cpu")
cc = opencc.OpenCC("s2t")
norm = lambda s: re.sub(r"[\s，。！？：、,.!?:；;（）()「」]", "", s).replace("臺", "台")
def synth(text, seed):
    body = {"text": text, "speed": 1.0}  # natural take; the video applies its own tempo
    if seed is not None: body["seed"] = seed
    req = urllib.request.Request("http://127.0.0.1:8100/tts", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=180).read()
for lid, (cap, say) in NEW.items():
    best = None
    for seed in (None, 7, 21, 42):
        wav = synth(say, seed); f = f"{V}/tts/_try.wav"; open(f, "wb").write(wav)
        heard = cc.convert(m.transcribe(f, language="zh", initial_prompt="以下是台灣華語。", temperature=0)["text"])
        target = say.replace("B Z 四 X", "BZ4X").replace("T D X", "TDX").replace("A B", "AB")
        sim = difflib.SequenceMatcher(None, norm(target), norm(heard)).ratio()
        print(f"{lid} seed={seed} {sim:.2f} heard: {heard}", flush=True)
        if best is None or sim > best[0]: best = (sim, seed, wav)
        if sim >= 0.95: break
    open(f"{V}/tts/{lid}.wav", "wb").write(best[2])
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"{V}/tts/{lid}.wav"]))
    by[lid].update(cap=cap, say=say, dur=round(d, 3), seed=best[1])
    print(f"==> {lid} keep seed={best[1]} sim={best[0]:.2f} dur={d:.2f}", flush=True)
json.dump(L, open(f"{V}/script.json", "w"), ensure_ascii=False, indent=1)
