"""Build the v6 demo video (11/17, round 2 after the team's review):

  landing → (no member picker) chat with CDP prefilled → 「💬 用聊的」 + 陳先生's one sentence → ⏩ the rest by tapping
  → verdict reveal (阿電 up to 「恭喜你！」) → 2D week intro (live) → 3D drive to 板橋大遠百 + fast charge while shopping
  (frame by frame) → 2D week summary (live) → cost card + bZ4X card → card 1 → bZ4X official page + iRent with 阿電's
  voice-over (voice only) → end card.

  python build_demo_v6.py WORKDIR OUT.mp4

Every scene carries a zh-TW narration caption at the bottom (not 阿電's words), the 2D / 3D parts a big title at the
top. WORKDIR holds chat3/ (capture_chat_v6.py), sim2d/ + sim2d_sum/ (capture_sim2d.py), clips3d_b/ + tts3d/ +
plan3d_b.json (record_sim.py, fetch_tts.py), tabs2/ (capture_tabs.py), customer/plan.wav (customer_voice.py).
Cut points come from the logged events and the recorded page audio (sentence ends, not TTS chunk boundaries).
Music bed ducked under voices, loudness -16 LUFS. H.264 + AAC, 1920x1080, 30 fps.
"""
import bisect, io, json, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
W, OUT = sys.argv[1], sys.argv[2]
FPS, SR, XF = 30, 48000, 0.4
CAP_FONT = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 40, index=3)
TITLE_FONT = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 58, index=3)
MUSIC = os.path.join(HERE, "..", "audio", "music_bed.wav")
END_CARD = os.path.join(HERE, "card_end.png")
TMP = os.path.join(W, "_build"); os.makedirs(TMP, exist_ok=True)
INK, YELLOW = (20, 27, 45), (255, 216, 77)


def ff(*a, inp=None):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", *a], input=inp, check=True, capture_output=True).stdout


def wav48(path):
    with wave.open(path) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2: x = x[::2]
        sr = w.getframerate()
    return resample_poly(x, SR // 1000, sr // 1000).astype(np.float32) if sr != SR else x


def caption_img(text):
    """narration subtitle: white bold text on a dark rounded bar"""
    pad_x, h = 34, 72
    w = int(CAP_FONT.getlength(text)) + pad_x * 2
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], 18, fill=(*INK, 228))
    d.text((pad_x, h // 2 + 1), text, font=CAP_FONT, fill=(255, 255, 255, 255), anchor="lm")
    return im


def title_img(text):
    """big scene title: yellow pill, thick ink border, hard shadow (deck style)"""
    pad, h = 40, 104
    w = int(TITLE_FONT.getlength(text)) + pad * 2
    im = Image.new("RGBA", (w + 10, h + 10), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([10, 10, w + 9, h + 9], 28, fill=(*INK, 255))
    d.rounded_rectangle([0, 0, w - 1, h - 1], 28, fill=(*YELLOW, 255), outline=(*INK, 255), width=5)
    d.text((pad, h // 2 + 2), text, font=TITLE_FONT, fill=(*INK, 255), anchor="lm")
    return im


class Capture:
    """frames (+ timestamps) and page audio taps of one capture folder; or the frames of an mp4 clip"""
    def __init__(self, d, clip=None):
        self.taps = []
        if clip:                                  # frame-by-frame clip: decode to jpgs, timestamps i / FPS
            self.d = os.path.join(TMP, os.path.basename(clip) + "_frames"); os.makedirs(f"{self.d}/frames", exist_ok=True)
            if not os.listdir(f"{self.d}/frames"):
                ff("-i", clip, "-q:v", "2", "-start_number", "0", f"{self.d}/frames/%05d.jpg")
            n = len(os.listdir(f"{self.d}/frames")); self.F = [i / FPS for i in range(n)]; self.ev = {}
            return
        self.d = d
        self.ev = json.load(open(f"{d}/events.json")) if os.path.exists(f"{d}/events.json") else {}
        self.F = self.ev["frames"] if "frames" in self.ev else json.load(open(f"{d}/times.json"))
        if os.path.exists(f"{d}/taps.json"):
            for i, tp in enumerate(json.load(open(f"{d}/taps.json"))):
                raw = ff("-i", f"{d}/tap{i}.webm", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-")
                self.taps.append((tp["t0"], np.frombuffer(raw, np.float32)))

    def audio(self, a, b):
        n = int(round((b - a) * SR)); out = np.zeros(n, np.float32)
        for t0, x in self.taps:
            i0 = int(round((a - t0) * SR)); lo, hi = max(0, i0), min(len(x), i0 + n)
            if hi > lo: out[lo - i0:hi - i0] += x[lo:hi]
        return out

    def rms(self, t, w=0.1):
        s = self.audio(t, t + w); return float(np.sqrt(np.mean(s * s))) if len(s) else 0.0

    def snap(self, t, span=0.8):
        for dd in np.arange(0, span, 0.05):
            for c in (t + dd, t - dd):
                if self.rms(c) < 0.006: return c
        return t

    def frame(self, t):
        k = max(0, bisect.bisect_right(self.F, t) - 1)
        return f"{self.d}/frames/{k:05d}.jpg"


def render(cap, ranges, name, extra=()):
    """ranges: (start, end, speed, caption, title). extra: (wav path, capture time, gain) voices added at that time."""
    pipe = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", f"{TMP}/{name}.mp4"], stdin=subprocess.PIPE)
    audio = []
    for a, b, sp, cap_txt, ttl in ranges:
        n = int(round((b - a) / sp * FPS))
        cimg = caption_img(cap_txt) if cap_txt else None; timg = title_img(ttl) if ttl else None; cache = {}
        for j in range(n):
            f = cap.frame(a + j * sp / FPS)
            if f not in cache:
                im = Image.open(f).convert("RGB")
                if im.size != (1920, 1080): im = im.resize((1920, 1080))
                if timg: im.paste(timg, (960 - timg.width // 2, 96), timg)
                if cimg: im.paste(cimg, (960 - cimg.width // 2, 1080 - 34 - cimg.height), cimg)
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=90); cache = {f: buf.getvalue()}
            pipe.stdin.write(cache[f])
        seg = np.zeros(int(round(n / FPS * SR)), np.float32)
        if sp == 1:
            x = cap.audio(a, b)[: len(seg)]; seg[: len(x)] += x
            for path, tc, gain in extra:
                if a <= tc < b:
                    v = wav48(path) * gain; i = int((tc - a) * SR); v = v[: max(0, len(seg) - i)]; seg[i:i + len(v)] += v
        audio.append(seg)
    pipe.stdin.close(); pipe.wait()
    L = sum(int(round((b - a) / sp * FPS)) for a, b, sp, _, _ in ranges) / FPS
    return np.concatenate(audio), L


# ------------------------------------------------------------------ chat capture
C = Capture(f"{W}/chat3")
E = sorted(C.ev["events"], key=lambda e: e["t"])
def mark(tag): return next(e["t"] for e in E if e["type"] == "mark" and e["text"] == tag)
def first(typ, after=0): return next(e["t"] for e in E if e["type"] == typ and e["t"] > after)
T0 = C.F[0]
chen_t = next(e["t"] for e in E if e["type"] == "cust" and e["text"] == "chen")
res = mark("results")
ack_end = C.snap(first("say", mark("mic_up")) + 4.7)        # 「了解！住在板橋…」 ends, next question comes later
q_end = C.snap(mark("mic_down") - 0.9)                       # the plan question has finished
reveal_end = res + 4.65                                      # 「你的轉電適配度是 80 分。恭喜你！」 (stop before 「電動車很適合…」)
A = [(T0 + 0.3, T0 + 2.5, 1, "和泰會員收到邀請，點開阿電", None),
     (mark("pick_member") + 1.1, mark("mode_chat") + 0.6, 1, "會員登入：CDP 資料已預先填好，不用重問", None),   # no member picker shown
     (mark("mode_chat") + 0.6, q_end, 1, "切換到「用聊的」：一句話說出自己的一週", None),
     (mark("mic_down") - 0.25, ack_end, 1, "陳先生用說的 → Breeze 轉成文字，Gemma 聽懂並自動填好", None),
     (ack_end, res - 0.3, (res - 0.3 - ack_end) / 3.0, "⏩ 其他問題點一下就好", None),
     (res, reveal_end, 1, "阿電的誠實結論：很適合，80 分", None)]
vA, LA = render(C, A, "A", extra=[(f"{W}/customer/plan.wav", chen_t, 0.9)])
# the reveal line is cut after 「恭喜你！」: fade the last 0.25 s so the cut is soft
k = int(0.25 * SR); vA[-k:] *= np.linspace(1, 0, k)

cost_t, bz_t, again = mark("card2"), mark("card3"), mark("card1_again")
D = [(cost_t + 3.5, cost_t + 10.95, 1, "每月花費：跟他自己的 Camry 比", None),   # 「油錢加保養加稅金…每個月大約省 新台幣2614元」
     (bz_t + 0.4, bz_t + 8.1, 1, "推薦車款：bZ4X", None),                        # 「這就是 bZ4X。…充飽一次可以開大約 14 天」
     (again - 0.2, mark("end") - 0.6, 1, "下一步：一鍵連到和泰的服務", None)]
vD, LD = render(C, D, "D")

# ------------------------------------------------------------------ 2D intro, 3D drive + charge, 2D summary
S2 = Capture(f"{W}/sim2d"); tp = S2.ev["t_play"]
vB1, LB1 = render(S2, [(tp + 0.15, S2.snap(tp + 5.6), 1, "用他真實的路線，排出一整週", "2D 模擬：陳先生真實的一週")], "B1")

plan = json.load(open(f"{W}/plan3d_b.json")); mouth = json.load(open(plan["mouth"]))
cues = json.load(open(f"{W}/clips3d_b/cues_live.json"))
cap3 = ["週六：全家去板橋大遠百", "邊逛街、吃飯，邊快充"]
ttl3 = ["3D 街景模擬", None]
parts3 = []
for i, (a, b) in enumerate(plan["segs"]):
    cp = Capture(None, clip=f"{W}/clips3d_b/seg{i:02d}.mp4")
    voices = [(mouth[c["text"]]["wav"], c["at"] - a, 0.95) for c in cues if a <= c["at"] < b and c["text"] in mouth]
    v, L = render(cp, [(0, b - a, 1, cap3[i], ttl3[i])], f"B3_{i}", extra=voices)
    parts3.append((f"B3_{i}", L, v))

S4 = Capture(f"{W}/sim2d_sum"); tq = S4.ev["t_play"]
vB4, LB4 = render(S4, [(tq + 0.1, S4.snap(tq + 11.3), 1, "一週總結：只充一次電，沒去過加油站", "回到 2D：這一週的總結")], "B4")

# ------------------------------------------------------------------ the two official pages (阿電's voice-over only) + end card
def page_clip(d, name, a_off, secs, caption, line):
    cp = Capture(d)
    return render(cp, [(cp.F[0] + a_off, cp.F[0] + a_off + secs, 1, caption, None)], name,
                  extra=[(mouth[line]["wav"], cp.F[0] + a_off + 0.25, 0.95)])
vT, LT = page_clip(f"{W}/tabs2/toyota", "T", 1.5, 4.0, "Toyota 官網：bZ4X 車款介紹", "想更認識 bZ4X，按一下就到 Toyota 官網。")
vI, LI = page_clip(f"{W}/tabs2/irent", "I", 0.3, 4.9, "和雲 iRent：先租一台試開", "還想再確定？也可以先用 iRent 租一台，開開看。")
ff("-loop", "1", "-t", "3.2", "-i", END_CARD, "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "18", f"{TMP}/end.mp4")

# ------------------------------------------------------------------ final cut
parts = [("A", LA, vA), ("B1", LB1, vB1), *parts3, ("B4", LB4, vB4), ("D", LD, vD), ("T", LT, vT), ("I", LI, vI), ("end", 3.2, None)]
P = [0.0]
for i in range(1, len(parts)): P.append(P[-1] + parts[i - 1][1] - XF)
total = P[-1] + parts[-1][1]
args, fc, prev = [], [], "[0:v]"
for nm, _, _ in parts: args += ["-i", f"{TMP}/{nm}.mp4"]
for i in range(1, len(parts)):
    fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={P[i]:.3f}[p{i}]"); prev = f"[p{i}]"
fc.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 0.8:.3f}:d=0.8[v]")
ff(*args, "-filter_complex", ";".join(fc), "-map", "[v]", "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-maxrate", "14M",
   "-bufsize", "28M", "-pix_fmt", "yuv420p", "-r", "30", f"{TMP}/video.mp4")

N = int(total * SR); voice = np.zeros(N, np.float32)
for (nm, L, v), p in zip(parts, P):
    if v is None: continue
    j = int(p * SR); x = v[: max(0, N - j)]; voice[j:j + len(x)] += x
active = np.convolve(np.abs(voice) > 0.01, np.ones(int(0.05 * SR)), "same") > 0
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
print(" | ".join(f"{nm} {L:.1f}s @ {p:.1f}" for (nm, L, _), p in zip(parts, P)), f"| total {total:.1f}s -> {OUT}")
for a, b, sp, c, _ in A + D: print(f"  {a - T0:7.2f}-{b - T0:7.2f}  x{sp:.2f}  {c or ''}")
