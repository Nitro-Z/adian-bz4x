#!/usr/bin/env python3
"""Procedural audio generator for the 阿電 product video.

Everything here is synthesized from scratch with numpy/scipy (oscillators,
filtered noise, envelopes, a synthetic-IR reverb). No external samples.

Outputs (48 kHz / 16-bit / stereo WAV) go to ./audio/ next to this script.
"""
import os
import re
import subprocess
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audio")
os.makedirs(OUT, exist_ok=True)
rng = np.random.default_rng(20261014)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


def db(x):
    return 20 * np.log10(max(x, 1e-12))


def fades(x, fin=0.008, fout=0.015):
    n_in, n_out = int(fin * SR), int(fout * SR)
    x = x.copy()
    if n_in:
        x[:n_in] *= (np.sin(np.linspace(0, np.pi / 2, n_in)) ** 2)[:, None] if x.ndim == 2 else np.sin(np.linspace(0, np.pi / 2, n_in)) ** 2
    if n_out:
        w = np.cos(np.linspace(0, np.pi / 2, n_out)) ** 2
        x[-n_out:] *= w[:, None] if x.ndim == 2 else w
    return x


def write(name, x):
    """x: (N,2) float. Writes 16-bit stereo with TPDF dither."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    y = x * 32767.0 + (rng.random(x.shape) - rng.random(x.shape))
    y = np.clip(np.round(y), -32768, 32767).astype(np.int16)
    wavfile.write(os.path.join(OUT, name), SR, y)


def sos_lp(fc, order=2):
    return signal.butter(order, fc, "low", fs=SR, output="sos")


def sos_hp(fc, order=2):
    return signal.butter(order, fc, "high", fs=SR, output="sos")


def sos_bp(lo, hi, order=2):
    return signal.butter(order, [lo, hi], "band", fs=SR, output="sos")


# ----------------------------------------------------------------------------
# MUSIC BED
# ----------------------------------------------------------------------------
BPM = 96
BEAT = 60.0 / BPM          # 0.625 s
BAR = 4 * BEAT             # 2.5 s
DUR = 185.0
N = int(DUR * SR)

# chord voicings (MIDI); root for bass
CH = {
    "Cmaj7": ([60, 64, 67, 71], 36),
    "Am7": ([57, 60, 64, 67], 45),
    "Fmaj7": ([53, 57, 60, 64], 41),
    "G6": ([55, 59, 62, 64], 43),
    # reflective voicings (more open, add9 colours)
    "Am9": ([57, 64, 67, 71], 45),
    "Fmaj9": ([53, 60, 64, 67], 41),
    "C/E": ([52, 60, 67, 72], 40),
    "Gsus": ([55, 60, 62, 67], 43),
    "Cfinal": ([48, 60, 64, 67, 72], 36),
}
MAIN = ["Cmaj7", "Am7", "Fmaj7", "G6"]
REFL = ["Am9", "Fmaj9", "C/E", "Gsus"]
N_BARS = 71                 # bars 0..70 (0..177.5 s); final chord at 177.5
FINAL_T = N_BARS * BAR


def chord_for_bar(b):
    if 48 <= b < 66:        # 120..165 s reflective
        return REFL[(b - 48) % 4]
    return MAIN[b % 4]


def section_gain(t, points):
    """piecewise-linear automation from list of (time, value)."""
    ts, vs = zip(*points)
    return np.interp(t, ts, vs)


_pad_cache = {}


def pad_note(m, dur):
    key = (m, round(dur, 3))
    if key in _pad_cache:
        return _pad_cache[key]
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = mtof(m)
    out = np.zeros((n, 2))
    for vi, (det, pan) in enumerate([(-7, 0.25), (6, 0.75), (0, 0.5)]):
        f = f0 * 2 ** (det / 1200.0)
        ph = rng.random() * 2 * np.pi
        v = np.zeros(n)
        for k in range(1, 9):
            if f * k > 6000:
                break
            v += np.sin(2 * np.pi * f * k * t + ph * k) / k
        # slow chorus-ish amplitude wobble
        v *= 1 + 0.08 * np.sin(2 * np.pi * (0.13 + 0.05 * vi) * t + vi)
        out[:, 0] += v * np.cos(pan * np.pi / 2)
        out[:, 1] += v * np.sin(pan * np.pi / 2)
    _pad_cache[key] = out
    return out


def adsr(n, a, r, sustain_len):
    """attack a s, hold until sustain_len s, release r s (n total samples)."""
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / a)
    rel = np.clip(1 - (t - sustain_len) / r, 0, 1)
    env = env * np.where(t > sustain_len, rel, 1.0)
    return np.sin(env * np.pi / 2) ** 2


def render_pad():
    out = np.zeros((N, 2))
    for b in range(N_BARS + 1):
        if b < N_BARS:
            name = chord_for_bar(b)
            start, hold, rel = b * BAR, BAR, 0.9
        else:
            name = "Cfinal"
            start, hold, rel = FINAL_T, 1.5, 4.0
        notes, _ = CH[name]
        dur = hold + rel
        seg = np.zeros((int(dur * SR), 2))
        for m in notes:
            seg += pad_note(m, dur)
        seg *= adsr(len(seg), 0.6 if b else 2.5, rel, hold)[:, None]
        i0 = int(start * SR)
        i1 = min(N, i0 + len(seg))
        out[i0:i1] += seg[: i1 - i0]
    out = signal.sosfiltfilt(sos_lp(1900, 2), out, axis=0)
    return out / np.max(np.abs(out))


def pluck(m, dur=0.6, decay=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = mtof(m)
    # marimba-ish: fundamental + 4th partial (~3.9x) decaying fast
    v = np.sin(2 * np.pi * f * t) * np.exp(-t / decay)
    v += 0.25 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t / (decay * 0.25))
    v += 0.15 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t / (decay * 0.5))
    att = np.minimum(1, t / 0.003)
    return v * att


def render_arp():
    out = np.zeros((N, 2))
    step = BEAT / 2  # 8th notes
    pattern_idx = [0, 1, 2, 3, 2, 1, 3, 2]
    for b in range(N_BARS):
        notes, _ = CH[chord_for_bar(b)]
        tones = sorted(n + 12 for n in notes)
        bt = b * BAR
        for s in range(8):
            t0 = bt + s * step
            # density by section
            if t0 < 34:
                if s not in (0, 3, 6):
                    continue
            elif t0 < 48:
                if s % 2 == 1 and s != 3:
                    continue
            elif 120 <= t0 < 165:
                if s in (5, 7):
                    continue
            m = tones[pattern_idx[s] % len(tones)]
            if s == 7 and b % 2:
                m += 12 if m + 12 < 90 else 0
            vel = 0.75 if s % 2 == 0 else 0.55
            vel *= 0.9 + 0.2 * rng.random()
            p = pluck(m) * vel
            pan = 0.5 + 0.35 * np.sin(s * 1.3 + b * 0.7)
            i0 = int(t0 * SR)
            i1 = min(N, i0 + len(p))
            out[i0:i1, 0] += p[: i1 - i0] * np.cos(pan * np.pi / 2)
            out[i0:i1, 1] += p[: i1 - i0] * np.sin(pan * np.pi / 2)
    # final strum
    for k, m in enumerate([72, 76, 79, 84]):
        p = pluck(m, 2.5, 0.6) * 0.7
        i0 = int((FINAL_T + k * 0.09) * SR)
        pan = 0.3 + 0.13 * k
        i1 = min(N, i0 + len(p))
        out[i0:i1, 0] += p[: i1 - i0] * np.cos(pan * np.pi / 2)
        out[i0:i1, 1] += p[: i1 - i0] * np.sin(pan * np.pi / 2)
    out = signal.sosfilt(sos_lp(5000, 2), out, axis=0)
    return out / np.max(np.abs(out))


def render_bass():
    out = np.zeros(N)
    for b in range(N_BARS + 1):
        root = CH[chord_for_bar(b) if b < N_BARS else "Cfinal"][1]
        hits = [(0, 1.45), (1.5 * BEAT, 0.95)] if b < N_BARS else [(0, 4.0)]
        for off, d in hits:
            n = int((d + 0.3) * SR)
            t = np.arange(n) / SR
            f = mtof(root)
            v = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(4 * np.pi * f * t)
            env = np.minimum(1, t / 0.02) * np.clip(1 - (t - d) / 0.3, 0, 1) * np.exp(-t / (d * 1.5))
            i0 = int((b * BAR + off) * SR)
            i1 = min(N, i0 + n)
            out[i0:i1] += (v * env)[: i1 - i0] * (1.0 if off == 0 else 0.7)
    out = signal.sosfilt(sos_lp(400, 2), out)
    out /= np.max(np.abs(out))
    return np.stack([out, out], axis=1)


def render_kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 48 + 70 * np.exp(-t / 0.035)
    ph = 2 * np.cumsum(np.pi * f / SR) * 1
    k = np.sin(ph) * np.exp(-t / 0.12) * np.minimum(1, t / 0.002)
    k = signal.sosfilt(sos_lp(300, 2), k)
    out = np.zeros(N)
    for b in range(N_BARS):
        for beat in (0, 2):
            i0 = int((b * BAR + beat * BEAT) * SR)
            i1 = min(N, i0 + n)
            out[i0:i1] += k[: i1 - i0]
    out /= np.max(np.abs(out))
    return np.stack([out, out], axis=1)


def render_shaker():
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    env = (t / 0.012) * np.exp(1 - t / 0.012)
    sos = sos_bp(5500, 11000, 2)
    out = np.zeros((N, 2))
    for b in range(N_BARS):
        for s in range(4):
            t0 = b * BAR + s * BEAT + BEAT / 2 + 0.004 * rng.standard_normal()
            nz = signal.sosfilt(sos, rng.standard_normal((n, 2)), axis=0) * env[:, None]
            nz *= 0.8 + 0.3 * rng.random()
            i0 = int(t0 * SR)
            i1 = min(N, i0 + n)
            out[i0:i1] += nz[: i1 - i0]
    return out / np.max(np.abs(out))


def reverb_ir(seconds=2.4, seed=7):
    r = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = r.standard_normal((n, 2)) * np.exp(-t / 0.45)[:, None]
    # darker tail: low-pass progressively by blending with a filtered copy
    dark = signal.sosfilt(sos_lp(2500, 2), ir, axis=0)
    w = np.clip(t / 1.0, 0, 1)[:, None]
    ir = ir * (1 - w) + dark * w
    pre = int(0.018 * SR)
    ir = np.concatenate([np.zeros((pre, 2)), ir])
    ir = signal.sosfilt(sos_hp(180, 2), ir, axis=0)
    ir /= np.sqrt(np.sum(ir ** 2, axis=0))
    return ir


def measure_lufs(path):
    p = subprocess.run(["/usr/bin/ffmpeg", "-hide_banner", "-nostats", "-i", path,
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    txt = p.stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", txt)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", txt)
    return (float(m[-1]) if m else None), (float(tp[-1]) if tp else None)


def make_music():
    t = np.arange(N) / SR
    print("pad..."); pad = render_pad()
    print("arp..."); arp = render_arp()
    print("bass..."); bass = render_bass()
    print("kick..."); kick = render_kick()
    print("shaker..."); shk = render_shaker()

    g_pad = section_gain(t, [(0, 0.55), (34, 0.55), (48, 0.6), (120, 0.6), (122, 0.62), (165, 0.6), (185, 0.6)])
    g_arp = section_gain(t, [(0, 0.22), (33, 0.24), (35, 0.28), (47, 0.3), (49, 0.33), (119, 0.33), (122, 0.27),
                             (164, 0.27), (166, 0.32), (185, 0.32)])
    g_bass = section_gain(t, [(0, 0), (33, 0), (36, 0.38), (119, 0.4), (122, 0.3), (164, 0.3), (166, 0.4), (185, 0.4)])
    g_kick = section_gain(t, [(0, 0), (47.8, 0), (48.0, 0.32), (119.9, 0.32), (120.05, 0),
                              (164.9, 0), (165.0, 0.28), (176.0, 0.28), (177.4, 0), (185, 0)])
    g_shk = section_gain(t, [(0, 0), (51, 0), (55, 0.07), (117, 0.07), (120, 0), (185, 0)])

    dry = pad * g_pad[:, None] + arp * g_arp[:, None] + bass * g_bass[:, None] \
        + kick * g_kick[:, None] + shk * g_shk[:, None]

    print("reverb...")
    ir = reverb_ir()
    wet_src = pad * g_pad[:, None] * 0.6 + arp * g_arp[:, None] + shk * g_shk[:, None] * 0.5
    wet = np.stack([signal.fftconvolve(wet_src[:, c], ir[:, c])[:N] for c in range(2)], axis=1)
    # dotted-8th ping-pong echo on the arp for width
    d = int(0.75 * BEAT * SR)
    echo = np.zeros_like(dry)
    a = arp * g_arp[:, None]
    echo[d:, 0] += 0.22 * a[:-d, 1]
    echo[2 * d:, 1] += 0.14 * a[:-2 * d, 0]
    mix = dry + 0.35 * wet + echo

    mix = signal.sosfiltfilt(sos_hp(30, 2), mix, axis=0)
    # master fades: 3 s in, fade to silence by 185
    fin = np.clip(t / 3.0, 0, 1) ** 2
    fout = np.clip((DUR - 0.05 - t) / (DUR - 0.05 - 180.0), 0, 1) ** 1.5
    mix *= (fin * fout)[:, None]
    mix -= mix.mean(axis=0)
    mix = fades(mix, 0.005, 0.05)

    # loudness: iterate gain to ~-18 LUFS with peak ceiling -3 dBFS
    mix /= np.max(np.abs(mix))
    mix *= 10 ** (-3 / 20)
    path = os.path.join(OUT, "music_bed.wav")
    write("music_bed.wav", mix)
    lufs, _ = measure_lufs(path)
    print("pre-norm LUFS", lufs)
    if lufs is not None:
        gain_db = -18.0 - lufs
        if gain_db < 0:
            mix *= 10 ** (gain_db / 20)
        elif gain_db > 0:
            # gentle soft-knee limiting above -3 dBFS to gain loudness
            mix *= 10 ** (gain_db / 20)
            ceil = 10 ** (-3.2 / 20)
            thr = 10 ** (-6 / 20)
            ab = np.abs(mix)
            over = ab > thr
            mix[over] = np.sign(mix[over]) * (thr + (ceil - thr) * np.tanh((ab[over] - thr) / (ceil - thr)))
        write("music_bed.wav", mix)
    return mix


# ----------------------------------------------------------------------------
# SFX
# ----------------------------------------------------------------------------
def norm_peak(x, target_db=-6.0):
    x = x - x.mean(axis=0)
    return x / np.max(np.abs(x)) * 10 ** (target_db / 20)


def noise_sweep(dur, f_start, f_end, curve, seed):
    """band-bank noise sweep: centre frequency moves from f_start to f_end."""
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    fc = f_start * (f_end / f_start) ** u
    centres = np.geomspace(250, 12000, 18)
    out = np.zeros((n, 2))
    for c in centres:
        lo, hi = c / 1.25, min(c * 1.25, SR / 2 - 100)
        b = signal.sosfilt(sos_bp(lo, hi, 2), r.standard_normal((n, 2)), axis=0)
        w = np.exp(-0.5 * (np.log(c / fc) / 0.45) ** 2)
        out += b * w[:, None]
    return out * curve(u)[:, None]


def whoosh_in():
    dur = 0.45
    curve = lambda u: np.sin(np.pi * np.clip(u / 0.7, 0, 1) ** 1.2 / 2) ** 2 * np.clip((1 - u) / 0.3, 0, 1) ** 1.5
    x = noise_sweep(dur, 500, 6000, curve, 1)
    # stereo motion L->R
    u = np.linspace(0, 1, len(x))
    pan = 0.3 + 0.4 * u
    x[:, 0] *= np.cos(pan * np.pi / 2) * 1.41
    x[:, 1] *= np.sin(pan * np.pi / 2) * 1.41
    return fades(norm_peak(x), 0.005, 0.03)


def whoosh_out():
    dur = 0.4
    curve = lambda u: np.clip(u / 0.15, 0, 1) ** 1.5 * np.exp(-3.2 * u)
    x = noise_sweep(dur, 5000, 400, curve, 2)
    u = np.linspace(0, 1, len(x))
    pan = 0.6 - 0.3 * u
    x[:, 0] *= np.cos(pan * np.pi / 2) * 1.41
    x[:, 1] *= np.sin(pan * np.pi / 2) * 1.41
    return fades(norm_peak(x), 0.005, 0.03)


def pop():
    dur = 0.18
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 380 + 900 * np.exp(-t / 0.025)          # quick downward chirp
    ph = 2 * np.pi * np.cumsum(f) / SR
    v = np.sin(ph) * np.exp(-t / 0.045) * np.minimum(1, t / 0.002)
    v += 0.3 * np.sin(2 * ph) * np.exp(-t / 0.02)
    # small bubbly upward blip at start
    v += 0.25 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t / 0.006)
    return fades(norm_peak(np.stack([v, v], 1)), 0.002, 0.02)


def click():
    dur = 0.06
    n = int(dur * SR)
    t = np.arange(n) / SR
    v = np.sin(2 * np.pi * 2200 * t) * np.exp(-t / 0.004)
    v += 0.6 * np.sin(2 * np.pi * 900 * t) * np.exp(-t / 0.009)
    nz = signal.sosfilt(sos_bp(2000, 7000), rng.standard_normal(n)) * np.exp(-t / 0.002) * 0.4
    v = (v + nz) * np.minimum(1, t / 0.0008)
    return fades(norm_peak(np.stack([v, v], 1)), 0.0008, 0.012)


def bell(f, dur, decay=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    v = np.sin(2 * np.pi * f * t) * np.exp(-t / decay)
    v += 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t / (decay * 0.35))
    v += 0.15 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t / (decay * 0.15))
    v += 0.2 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / (decay * 0.6))
    return v * np.minimum(1, t / 0.002)


def ding():
    dur = 0.8
    a = bell(mtof(88), dur, 0.32)   # E6
    b = bell(mtof(95), dur, 0.26)   # B6
    l = a + 0.75 * b
    r = 0.85 * a + b
    x = np.stack([l, r], 1)
    x = signal.sosfilt(sos_lp(9000), x, axis=0)
    return fades(norm_peak(x), 0.002, 0.08)


def success():
    dur = 1.0
    n = int(dur * SR)
    x = np.zeros((n, 2))
    for k, (m, pan) in enumerate([(72, 0.35), (76, 0.5), (79, 0.65)]):
        i0 = int(k * 0.11 * SR)
        b = bell(mtof(m + 12), dur - k * 0.11, 0.35 if k < 2 else 0.45) * (0.8 if k < 2 else 1.0)
        b += 0.5 * pluck(m, dur - k * 0.11, 0.3)
        x[i0:i0 + len(b), 0] += b * np.cos(pan * np.pi / 2)
        x[i0:i0 + len(b), 1] += b * np.sin(pan * np.pi / 2)
    x = signal.sosfilt(sos_lp(9000), x, axis=0)
    return fades(norm_peak(x), 0.002, 0.12)


def type_ticks():
    dur = 1.2
    n = int(dur * SR)
    x = np.zeros((n, 2))
    times = np.cumsum(np.r_[0.03, 0.07 + 0.08 * rng.random(9)])
    times = times / times[-1] * 1.08 + 0.02
    m = int(0.03 * SR)
    t = np.arange(m) / SR
    for tt in times:
        f = 2600 + 900 * rng.random()
        v = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.0025)
        v += 0.5 * np.sin(2 * np.pi * (700 + 200 * rng.random()) * t) * np.exp(-t / 0.006)
        v += signal.sosfilt(sos_bp(3000, 9000), rng.standard_normal(m)) * np.exp(-t / 0.0012) * 0.5
        v *= (0.6 + 0.4 * rng.random()) * np.minimum(1, t / 0.0005)
        pan = 0.4 + 0.2 * rng.random()
        i0 = int(tt * SR)
        i1 = min(n, i0 + m)
        x[i0:i1, 0] += v[: i1 - i0] * np.cos(pan * np.pi / 2)
        x[i0:i1, 1] += v[: i1 - i0] * np.sin(pan * np.pi / 2)
    x = signal.sosfilt(sos_lp(8000), x, axis=0)
    return fades(norm_peak(x, -9.0), 0.002, 0.02)


def swell():
    dur = 1.5
    n = int(dur * SR)
    t = np.arange(n) / SR
    u = t / dur
    nz = rng.standard_normal((n, 2))
    nz = signal.sosfilt(sos_hp(2500, 2), nz, axis=0)
    nz = signal.sosfilt(sos_lp(12000, 2), nz, axis=0)
    # reversed exponential decay -> rising swell, then a quick 60 ms tail
    env = np.exp((u - 0.94) * 6.0)
    env = np.where(u > 0.94, np.exp(-(u - 0.94) * dur / 0.03), env)
    # add a soft airy band rising
    rise = noise_sweep(dur, 800, 7000, lambda uu: np.exp((uu - 0.94) * 5.0) * (uu <= 0.94) + (uu > 0.94) * np.exp(-(uu - 0.94) * dur / 0.03), 3)
    x = nz * env[:, None] + 0.6 * rise / np.max(np.abs(rise)) * np.max(np.abs(nz * env[:, None]))
    return fades(norm_peak(x), 0.01, 0.03)


def mic_on():
    dur = 0.35
    n = int(dur * SR)
    x = np.zeros(n)
    for k, (m, t0, d) in enumerate([(76, 0.0, 0.17), (83, 0.12, 0.23)]):  # E5 -> B5
        mm = int(d * SR)
        t = np.arange(mm) / SR
        f = mtof(m) * (1 + 0.02 * (1 - np.exp(-t / 0.03)))  # slight upward glide
        ph = 2 * np.pi * np.cumsum(f) / SR
        v = (np.sin(ph) + 0.15 * np.sin(2 * ph)) * np.minimum(1, t / 0.006) * np.exp(-t / (0.07 if k == 0 else 0.09))
        i0 = int(t0 * SR)
        x[i0:i0 + mm] += v[: n - i0]
    return fades(norm_peak(np.stack([x, x], 1)), 0.003, 0.03)


SFX = {
    "whoosh_in.wav": (whoosh_in, "Airy filtered-noise sweep rising then fading (L->R), for text/cards flying in."),
    "whoosh_out.wav": (whoosh_out, "Falling airy noise sweep (R->L), for elements leaving."),
    "pop.wav": (pop, "Cute bubbly pop: fast pitch-dropping sine blip, for mascot appearing / chips popping in."),
    "click.wav": (click, "Soft UI tap."),
    "ding.wav": (ding, "Bell chime E6+B6, for a big number / highlight appearing."),
    "success.wav": (success, "Rising C-E-G bell arpeggio, for a positive result."),
    "type_ticks.wav": (type_ticks, "~10 very soft keyboard ticks (peak -9 dBFS), for text being typed."),
    "swell.wav": (swell, "Reverse-cymbal-like noise swell rising into a transition."),
    "mic_on.wav": (mic_on, "Gentle two-tone low->high 'listening' chirp (E5->B5), mic turning on."),
}


def stats(name):
    sr, y = wavfile.read(os.path.join(OUT, name))
    x = y.astype(np.float64) / 32768
    return sr, y.shape, len(y) / sr, db(np.max(np.abs(x))), x.mean(axis=0), x


if __name__ == "__main__":
    lines = []
    print("music bed...")
    make_music()
    for name, (fn, _) in SFX.items():
        write(name, fn())

    report = []
    sr, shp, dur, pk, dc, x = stats("music_bed.wav")
    lufs, tpk = measure_lufs(os.path.join(OUT, "music_bed.wav"))
    report.append(("music_bed.wav", dur, pk,
                   f"Calm 96 BPM C major underscore (pad, marimba-like arp, sub bass, soft pulse/shaker), "
                   f"intro/lift/groove/reflective/outro; integrated {lufs:.1f} LUFS."))
    print(f"music_bed: sr={sr} shape={shp} dur={dur:.3f}s peak={pk:.2f} dBFS DC={dc} LUFS={lufs}")
    secs = [("intro 0-34", 3, 34), ("lift 34-48", 34, 48), ("groove 48-120", 48, 120),
            ("reflective 120-165", 120, 165), ("outro 165-177.5", 165, 177.5), ("tail 177.5-185", 177.5, 185)]
    for lab, a, b in secs:
        seg = x[int(a * SR):int(b * SR)]
        print(f"  {lab:20s} RMS {db(np.sqrt(np.mean(seg ** 2))):6.1f} dBFS")
    print("  edges (first/last sample abs):", np.abs(x[0]).max(), np.abs(x[-1]).max())

    for name, (_, desc) in SFX.items():
        sr, shp, dur, pk, dc, xx = stats(name)
        edge = max(np.abs(xx[0]).max(), np.abs(xx[-1]).max())
        print(f"{name:16s} sr={sr} ch={shp[1]} dur={dur:.3f}s peak={pk:6.2f} dBFS DC={np.abs(dc).max():.1e} edge={edge:.1e}")
        report.append((name, dur, pk, desc))

    with open(os.path.join(OUT, "README.txt"), "w", encoding="utf-8") as f:
        f.write("Audio for the 阿電 product video\n")
        f.write("All files: 48 kHz, 16-bit, stereo WAV.\n\n")
        for name, dur, pk, desc in report:
            f.write(f"{name:16s} {dur:7.3f} s   peak {pk:6.2f} dBFS   {desc}\n")
        f.write("\nEverything here is procedurally generated by ../make_audio.py "
                "(numpy + scipy oscillators, filtered noise, envelopes and a synthetic-IR reverb).\n"
                "No external samples, downloads or copyrighted material were used. Re-run the script to regenerate.\n")
