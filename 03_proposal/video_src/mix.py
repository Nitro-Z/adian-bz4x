"""Mix narration + SFX + music bed from timeline.json -> mix.wav (48 kHz stereo)."""
import json, os, subprocess
import numpy as np

V = os.path.dirname(os.path.abspath(__file__))
SR = 48000
TL = json.load(open(f"{V}/timeline.json"))
N = int(round(TL["total"] * SR))

def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()

def place(bus, x, t, gain_db=0.0):
    i = int(round(t * SR))
    if i >= N: return
    x = x[: N - i] * 10 ** (gain_db / 20)
    bus[i:i + len(x)] += x

# narration: loudness-match each take to ~-16 LUFS-ish via RMS, then place
voice = np.zeros((N, 2), np.float32)
for l in TL["lines"]:
    x = load(f"{V}/tts_fast/{l['id']}.wav")
    rms = np.sqrt(np.mean(x ** 2) + 1e-12)
    x *= 0.12 / rms
    place(voice, x, l["start"])

sfx = np.zeros((N, 2), np.float32)
cache = {}
for f, t, g in TL["sfx"]:
    if f not in cache: cache[f] = load(f"{V}/audio/{f}.wav")
    place(sfx, cache[f], max(t, 0), g)

music = load(f"{V}/audio/music_bed.wav")
# land the bed's final chord (177.5 s) on the closing logo: drop whole 4-bar phrases (10 s) from the
# reflective section (from 130 s), then shift the start; 50 ms crossfade at the splice
FINAL, PHRASE, CUT_AT = 177.5, 10.0, 130.0
target = TL["cues"]["close_logo"]
k = max(0, round((FINAL - target) / PHRASE))
if k:
    a, b, xf = int(CUT_AT * SR), int((CUT_AT + k * PHRASE) * SR), int(0.05 * SR)
    ramp = np.linspace(0, 1, xf)[:, None]
    joint = music[a:a + xf] * (1 - ramp) + music[b:b + xf] * ramp
    music = np.concatenate([music[:a], joint, music[b + xf:]])
shift = target - (FINAL - k * PHRASE)
if shift >= 0: music = np.concatenate([np.zeros((int(shift * SR), 2), np.float32), music])
else: music = music[int(-shift * SR):]
print(f"music: cut {k} phrases, shift {shift:+.2f} s")
music = music[:N]
fm = int(1.5 * SR); music[:fm] *= np.linspace(0, 1, fm)[:, None]  # head was trimmed, so re-fade in
music = np.pad(music, ((0, N - len(music)), (0, 0)))
# duck: envelope from narration line windows (attack 0.15 s, release 0.5 s), -9 dB under voice
duck = np.zeros(N, np.float32)
for l in TL["lines"]:
    duck[int(l["start"] * SR):int(l["end"] * SR)] = 1
k_a, k_r = 1 / (0.15 * SR), 1 / (0.5 * SR)
env = np.zeros(N, np.float32); e = 0.0
for i in range(0, N, 64):  # block-rate smoothing
    target = duck[i]
    e += (target - e) * min(1, (k_a if target > e else k_r) * 64)
    env[i:i + 64] = e
gain = 10 ** ((-3 - 9 * env) / 20)
music *= gain[:, None]

mix = voice + sfx + music
# fades
fi, fo = int(0.3 * SR), int(2.5 * SR)
mix[:fi] *= np.linspace(0, 1, fi)[:, None]
mix[-fo:] *= np.linspace(1, 0, fo)[:, None]
peak = np.abs(mix).max()
if peak > 0.89: mix *= 0.89 / peak
print("peak before limit", round(float(peak), 3))
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "f32le", "-ac", "2", "-ar", str(SR), "-i", "-",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), f"{V}/mix.wav"],
               input=mix.astype(np.float32).tobytes(), check=True)
print("mix ok")
