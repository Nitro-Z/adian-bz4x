"""Build the final demo video: title card -> chat (real voice pipeline) -> 陳先生's week (3D) -> verdict -> end card.

  python build_demo.py CHATDIR WEEKPLAN WEEKCLIPS OUT.mp4

Chat: CDP screencast frames + the page's own audio (tap) + 陳先生's voice (virtual mic). Cut points are found from the
logged events and snapped to silence in the tap audio, so no word is cut. Button-only answers are fast-forwarded
with a 「⏩ 快轉」 badge. Week: the frame-by-frame clips (some short lines dropped to keep ~2:15). Music: the
procedurally generated bed, ducked under any voice, loudness -16 LUFS. Output: H.264 + AAC, 1920x1080, 30 fps.
"""
import bisect, io, json, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import resample_poly

V = os.path.dirname(os.path.abspath(__file__))
CHAT, P2, C2, P3, C3, OUT = sys.argv[1:7]   # 11/13: form demo + 2D + 3D week clips
FPS, SR, XF = 30, 48000, 0.4
FONT = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 40, index=3)
MUSIC = "/home/lab/Jackie_Pham/和泰汽車黑客松/03_proposal/video_src/audio/music_bed.wav"
TMP = os.path.join(os.path.dirname(OUT), "_build"); os.makedirs(TMP, exist_ok=True)
WEEK_DROP = set(json.loads(os.environ.get("WEEK_DROP", "[]")))   # 11/12: chosen per run


def ff(*a, inp=None):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", *a], input=inp, check=True, capture_output=inp is not None or True).stdout


def wav24(path):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        sr = w.getframerate()
    return resample_poly(x, SR // 1000, sr // 1000).astype(np.float32) if sr != SR else x


# ------------------------------------------------------------------ chat
ev = json.load(open(f"{CHAT}/events.json"))
FR = ev["frames"]; E = ev["events"]; T = ev["tts"]
def say(p): return next(e["t"] for e in E if e["type"] == "say" and e["text"].startswith(p))
def cust(tag): return [e["t"] for e in E if e["type"] == "cust" and e["text"] == tag][-1]   # last take = the one that worked
def user_after(t): return next(e["t"] for e in E if e["type"] == "user" and e["t"] > t)
def tts(p, after=0): return next(x["t"] for x in T if x["text"].startswith(p) and x["t"] >= after)
RES = next(e["t"] for e in E if e["type"] == "results")

taps = []
for i, tp in enumerate(json.load(open(f"{CHAT}/taps.json"))):
    raw = ff("-i", f"{CHAT}/tap{i}.webm", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-")
    taps.append((tp["t0"], np.frombuffer(raw, np.float32)))
    span = FR[-1] - tp["t0"]; dur = len(taps[-1][1]) / SR
    print(f"tap{i}: {dur:.1f}s of audio for {span:.1f}s of capture", flush=True)
    if i == 0 and abs(dur - span) > 1.0:
        raise SystemExit(f"tap{i} is {dur - span:+.1f}s off the capture: the audio would drift, not building")

def tap(a, b):
    n = int(round((b - a) * SR)); out = np.zeros(n, np.float32)
    for t0, x in taps:
        i0 = int(round((a - t0) * SR)); lo, hi = max(0, i0), min(len(x), i0 + n)
        if hi > lo: out[lo - i0:hi - i0] += x[lo:hi]
    return out

def rms_at(t, w=0.1):
    s = tap(t, t + w); return float(np.sqrt(np.mean(s * s))) if len(s) else 0.0

def snap(t, span=0.7):
    """nearest quiet moment (100 ms below the voice level) to t, so a cut never lands inside a word"""
    for d in np.arange(0, span, 0.05):
        for c in (t + d, t - d):
            if rms_at(c) < 0.006: return c
    return t

def onset(t, maxs=6.0):
    for d in np.arange(0, maxs, 0.02):
        if rms_at(t + d, 0.04) > 0.02: return t + d
    return t

c1 = cust("chen")
def mark(tag): return next(e["t"] for e in E if e["type"] == "mark" and e["text"] == tag)
T0 = FR[0]
R = lambda a: T0 + a
# (start, end, speed, badge) in capture seconds
A = [(R(0.3), mark("results") + 9.4, 1, None),                    # landing → form → 🎤 sentence → Gemma fills → 看結果 → verdict reveal
     (mark("sim_click") - 1.0, mark("sim_click") + 8.6, 1, None)]  # week card: 「▶ 播放你的一週」 → the 2D week starts in the page
C = [(R(67.0), R(82.3), 2.4, "▶▶ 每個月要花多少：跟你的 Camry 比"),   # cost card: quick, no voice
     (R(82.4), R(97.0), 1, None)]                                  # bZ4X card (focus) + 阿電's goodbye
def badge(text):
    pad = 26; w = int(FONT.getlength(text)) + pad * 2; h = 74
    im = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([8, 8, w + 7, h + 7], 37, fill=(20, 27, 45, 255))
    d.rounded_rectangle([0, 0, w - 1, h - 1], 37, fill=(255, 216, 77, 255), outline=(20, 27, 45, 255), width=4)
    d.text((pad, h // 2), text, font=FONT, fill=(20, 27, 45, 255), anchor="lm")
    return im

def render_chat(ranges, name):
    files = [f"{CHAT}/frames/{i:05d}.jpg" for i in range(len(FR))]
    pipe = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", f"{TMP}/{name}.mp4"], stdin=subprocess.PIPE)
    audio, cache = [], {}
    for a, b, sp, bd in ranges:
        n = int(round((b - a) / sp * FPS)); bimg = badge(bd) if bd else None
        for j in range(n):
            k = max(0, bisect.bisect_right(FR, a + j * sp / FPS) - 1)
            if bimg is None:
                pipe.stdin.write(open(files[k], "rb").read()); continue
            if k not in cache:
                im = Image.open(files[k]).convert("RGB"); im.paste(bimg, (960 - bimg.width // 2, 950), bimg)   # bottom band of the results page
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=90); cache = {k: buf.getvalue()}
            pipe.stdin.write(cache[k])
        seg = np.zeros(int(round(n / FPS * SR)), np.float32)
        if sp == 1:
            x = tap(a, b)[: len(seg)]; seg[: len(x)] += x
            for tag, tc in (("chen", c1),):
                if a <= tc < b:
                    v = wav24(f"{V}/customer/{tag}.wav") * 0.9; i = int((tc - a) * SR); v = v[: max(0, len(seg) - i)]; seg[i:i + len(v)] += v
        audio.append(seg)
    pipe.stdin.close(); pipe.wait()
    return np.concatenate(audio), sum(int(round((b - a) / sp * FPS)) for a, b, sp, _ in ranges) / FPS

vA, LA = render_chat(A, "A"); vC, LC = render_chat(C, "C")
# the in-page 2D sim plays its own line inside an iframe, which the audio tap does not record: add that line here
_m = json.load(open(json.load(open(P3))["mouth"]))
_intro = next(k for k in _m if k.startswith("這是你的一週"))
_t = (A[0][1] - A[0][0]) + 1.0 + 1.4          # start of the 2D part + click + overlay opening
_x = wav24(_m[_intro]["wav"]) * 0.95; _j = int(_t * SR); vA[_j:_j + len(_x)] += _x[: max(0, len(vA) - _j)]

# ------------------------------------------------------------------ week (3D)
files, cues_all, segs_all = [], [], []
for P, CL in ((P3, C3),):   # 2D comes from the live capture above; 3D frame by frame
    plan = json.load(open(P)); mouth = json.load(open(plan["mouth"])); cl = json.load(open(f"{CL}/cues_live.json"))
    for k, sg in enumerate(plan["segs"]):
        files.append(f"{CL}/seg{k:02d}.mp4"); segs_all.append(sg); cues_all.append([c for c in cl if sg[0] <= c["at"] < sg[1]])
Ls = [b - a for a, b in segs_all]; O = [0.0]
for i in range(1, len(files)): O.append(O[-1] + Ls[i - 1] - XF)
LB = O[-1] + Ls[-1]
args = []
for f in files: args += ["-i", f]
fc, prev = [], "[0:v]"
for i in range(1, len(files)):
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={O[i]:.3f}[w{i}]"); prev = f"[w{i}]"
ff(*args, "-filter_complex", ";".join(fc), "-map", prev, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "30", f"{TMP}/B.mp4")
vB = np.zeros(int(LB * SR) + SR, np.float32); prev_end = -1
for i, cs in enumerate(cues_all):
    for c in sorted(cs, key=lambda c: c["at"]):
        if c["text"] not in mouth: continue
        t = max(O[i] + c["at"] - segs_all[i][0], prev_end + 0.12)
        x = wav24(mouth[c["text"]]["wav"]) * 0.95; j = int(t * SR); x = x[: max(0, len(vB) - j)]; vB[j:j + len(x)] += x; prev_end = t + len(x) / SR

# ------------------------------------------------------------------ cards + final cut
for nm, dur in (("end", 4.2),):
    ff("-loop", "1", "-t", str(dur), "-i", f"{V}/card_{nm}.png", "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18", f"{TMP}/{nm}.mp4")
parts = [("A", LA, vA), ("B", LB, vB), ("C", LC, vC), ("end", 4.2, None)]   # no title card: the video opens on the landing page
P = [0.0]
for i in range(1, len(parts)): P.append(P[-1] + parts[i - 1][1] - XF)
total = P[-1] + parts[-1][1]
args, fc, prev = [], [], "[0:v]"
for nm, _, _ in parts: args += ["-i", f"{TMP}/{nm}.mp4"]
for i in range(1, len(parts)):
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={P[i]:.3f}[p{i}]"); prev = f"[p{i}]"
fc.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.8:.3f}:d=0.8[v]")
ff(*args, "-filter_complex", ";".join(fc), "-map", "[v]", "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "14M", "-bufsize", "28M",
   "-pix_fmt", "yuv420p", "-r", "30", f"{TMP}/video.mp4")

N = int(total * SR); voice = np.zeros(N, np.float32)
for (nm, L, v), p in zip(parts, P):
    if v is None: continue
    j = int(p * SR); x = v[: max(0, N - j)]; voice[j:j + len(x)] += x
env_t = np.abs(voice); k = int(0.05 * SR)
active = np.convolve(env_t > 0.01, np.ones(k), "same") > 0
with wave.open(MUSIC) as w:
    music = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32).reshape(-1, 2) / 32768
music = np.pad(music[:N], ((0, max(0, N - len(music))), (0, 0)))
env = np.zeros(N, np.float32); e = 0.0
for i in range(0, N, 64):
    tg = 1.0 if active[i] else 0.0; e += (tg - e) * min(1, (1 / (0.15 * SR) if tg > e else 1 / (0.6 * SR)) * 64); env[i:i + 64] = e
music *= (10 ** ((-6 - 10 * env) / 20))[:, None]
mix = voice[:, None] + music
fi, fo = int(0.5 * SR), int(1.2 * SR)
mix[:fi] *= np.linspace(0, 1, fi)[:, None]; mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
peak = float(np.abs(mix).max())
if peak > 0.89: mix *= 0.89 / peak
ff("-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), f"{TMP}/mix.wav",
   inp=mix.astype(np.float32).tobytes())
ff("-i", f"{TMP}/video.mp4", "-i", f"{TMP}/mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
   "-movflags", "+faststart", "-shortest", OUT)
print(f"chat A {LA:.1f}s | week {LB:.1f}s | verdict {LC:.1f}s | total {total:.1f}s -> {OUT}")
for a, b, sp, bd in A + C: print(f"  {a - FR[0]:7.2f}-{b - FR[0]:7.2f}  x{sp}  {bd or ''}")
