"""BreezyVoice (MediaTek Research) Taiwanese-Mandarin TTS HTTP service.

POST /tts   {"text": "...", "voice": "default", "seed": null, "speed": null}  -> audio/wav (mono, 22050 Hz, 16-bit PCM)
GET  /tts?text=...&voice=default                 -> same (handy for <audio src=...>)
GET  /health                                     -> {"ok": true, "voices": [...]}

The model is loaded once and kept on the GPU. Results are cached in memory (LRU)
and on disk (tts/cache/<voice>/<sha256>.wav), so repeated demo lines are instant
even after a restart. Voices are defined in tts/voices/voices.json (hot-reloaded).
Speaking speed: the cache holds the natural take; it is sped up on the way out with ffmpeg atempo
(pitch unchanged). Default TTS_SPEED=1.15; a request may pass "speed" (1.0 = natural, e.g. for the video).
"""
import asyncio
import contextlib
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
REPO = HERE / "BreezyVoice"
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("HF_HOME", str(HERE / "hf_cache"))
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "third_party" / "Matcha-TTS"))
os.chdir(REPO)  # BreezyVoice code uses repo-relative paths

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
import torchaudio  # noqa: E402
from fastapi import Request, FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from g2pw import G2PWConverter  # noqa: E402

from single_inference import CustomCosyVoice, get_bopomofo_rare  # noqa: E402
from cosyvoice.utils.file_utils import load_wav  # noqa: E402

log = logging.getLogger("tts")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MODEL_PATH = os.environ.get("TTS_MODEL", "MediaTek-Research/BreezyVoice")
VOICES_DIR = HERE / "voices"
VOICES_JSON = VOICES_DIR / "voices.json"
LEXICON_JSON = HERE / "lexicon.json"
CACHE_DIR = HERE / "cache"
SR = 22050
MAX_CHARS = int(os.environ.get("TTS_MAX_CHARS", "600"))
MEM_CACHE_SIZE = 256
CACHE_VERSION = "v3"  # bump to invalidate the on-disk cache after changing synthesis
SENT_GAP = np.zeros(int(0.15 * SR), dtype=np.float32)  # pause between sentences
EDGE_PAD = np.zeros(int(0.05 * SR), dtype=np.float32)   # silence at start/end of the clip
MIN_SEG_CHARS = 6
SPEED_DEFAULT = float(os.environ.get("TTS_SPEED", "1.15"))


def trim_silence(a, thresh_db=-42.0, frame=int(0.01 * SR), keep_head=0.03, keep_tail=0.08):
    """Trim leading/trailing near-silence from one generated segment."""
    n = len(a) // frame
    if n < 3:
        return a
    db = 20 * np.log10(np.sqrt((a[: n * frame].reshape(n, frame) ** 2).mean(1)) + 1e-9)
    idx = np.where(db > thresh_db)[0]
    if idx.size == 0:
        return a
    start = max(0, idx[0] * frame - int(keep_head * SR))
    end = min(len(a), (idx[-1] + 1) * frame + int(keep_tail * SR))
    return a[start:end]


class TTSEngine:
    def __init__(self):
        t0 = time.time()
        self.cv = CustomCosyVoice(MODEL_PATH)
        self.fe = self.cv.frontend
        self.g2p = G2PWConverter()
        self.lock = threading.Lock()
        self.voices = {}
        self.voices_mtime = None
        self.prompts = {}  # voice -> cached prompt features
        self.mem = OrderedDict()
        self.lexicon, self.lexicon_mtime = [], None
        self.reload_voices()
        log.info("model ready in %.1fs (ttsfrd=%s, device=%s)", time.time() - t0,
                 self.fe.use_ttsfrd, self.cv.model.device)

    # ---------- voices ----------
    def reload_voices(self):
        mtime = VOICES_JSON.stat().st_mtime
        if mtime == self.voices_mtime:
            return
        with open(VOICES_JSON, encoding="utf-8") as f:
            self.voices = json.load(f)
        self.voices_mtime = mtime
        self.prompts.clear()
        log.info("voices: %s", list(self.voices))

    def apply_lexicon(self, text):
        mtime = LEXICON_JSON.stat().st_mtime if LEXICON_JSON.exists() else None
        if mtime != self.lexicon_mtime:
            lex = json.load(open(LEXICON_JSON, encoding="utf-8")) if mtime else {}
            items = [(k, v) for k, v in lex.items() if not k.startswith("_")]
            items.sort(key=lambda kv: -len(kv[0]))  # longest match first
            self.lexicon = [(re.compile(re.escape(k), re.IGNORECASE), v) for k, v in items]
            self.lexicon_mtime = mtime
        for pat, rep in self.lexicon:
            text = pat.sub(rep, text)
        return text

    def prompt(self, voice):
        if voice in self.prompts:
            return self.prompts[voice]
        cfg = self.voices[voice]
        wav = VOICES_DIR / cfg["wav"]
        p16 = load_wav(str(wav), 16000)
        ptext = get_bopomofo_rare(self.fe.text_normalize_new(cfg["transcript"]), self.g2p)
        ptok, ptok_len = self.fe._extract_text_token(ptext)
        p22 = torchaudio.transforms.Resample(16000, 22050)(p16)
        feat, feat_len = self.fe._extract_speech_feat(p22)
        stok, stok_len = self.fe._extract_speech_token(p16)
        emb = self.fe._extract_spk_embedding(p16)
        self.prompts[voice] = dict(
            prompt_text=ptok, prompt_text_len=ptok_len,
            llm_prompt_speech_token=stok, llm_prompt_speech_token_len=stok_len,
            flow_prompt_speech_token=stok, flow_prompt_speech_token_len=stok_len,
            prompt_speech_feat=feat, prompt_speech_feat_len=feat_len,
            llm_embedding=emb, flow_embedding=emb)
        return self.prompts[voice]

    # ---------- text ----------
    def prepare(self, text):
        text = text.strip()
        if text[-1] not in "。！？!?.…」』）)":
            text += "。"
        norm = self.fe.text_normalize_new(text, split=False)
        norm = norm.replace("点", "點")  # ttsfrd emits simplified 点 for decimals
        bopo = get_bopomofo_rare(norm, self.g2p)
        # split into sentences (same punctuation as BreezyVoice), never inside [...]
        parts = [p for p in re.split(r"(?<=[？！。?!])\s*", bopo) if p.strip()]
        # merge very short sentences (e.g. "嗨！") into the next one: the LLM is unstable
        # on 1-3 character inputs and tends to produce long silences.
        merged, buf = [], ""
        for p in parts:
            buf += p
            if len(re.sub(r"\[.*?\]|[\W_]", "", buf)) >= MIN_SEG_CHARS:
                merged.append(buf); buf = ""
        if buf:
            if merged:
                merged[-1] += buf
            else:
                merged.append(buf)
        return norm, merged

    # ---------- synthesis ----------
    def key(self, voice, text, seed=None):
        sd = "" if seed is None else f"|seed={seed}"
        return hashlib.sha256(f"{CACHE_VERSION}|{MODEL_PATH}|{voice}|{text}{sd}".encode()).hexdigest()

    def cached(self, text, voice, seed=None):
        """Cache lookup only (no synthesis): wav bytes or None."""
        self.reload_voices()
        if voice not in self.voices:
            return None
        k = self.key(voice, self.apply_lexicon(text), seed)
        if k in self.mem:
            return self.mem[k]
        disk = CACHE_DIR / voice / f"{k}.wav"
        return disk.read_bytes() if disk.exists() else None

    def synth(self, text, voice, seed=None, lock_held=False):
        """Returns (wav_bytes, info dict)."""
        self.reload_voices()
        if voice not in self.voices:
            raise KeyError(voice)
        text = self.apply_lexicon(text)
        k = self.key(voice, text, seed)
        if k in self.mem:
            self.mem.move_to_end(k)
            return self.mem[k], {"cache": "memory"}
        disk = CACHE_DIR / voice / f"{k}.wav"
        if disk.exists():
            data = disk.read_bytes()
            self._mem_put(k, data)
            return data, {"cache": "disk"}

        with (contextlib.nullcontext() if lock_held else self.lock), torch.inference_mode():
            if k in self.mem:  # another request made it while we waited for the GPU
                return self.mem[k], {"cache": "memory"}
            t0 = time.time()
            pr = self.prompt(voice)
            norm, parts = self.prepare(text)
            # deterministic per (voice, text); pass "seed" to re-roll a take that sounds wrong
            torch.manual_seed(int(k[:8], 16) if seed is None else int(seed))
            chunks = []
            for i, part in enumerate(parts):
                ttok, ttok_len = self.fe._extract_text_token(part)
                out = self.cv.model.inference(text=ttok, text_len=ttok_len, **pr)
                chunks.append(trim_silence(out["tts_speech"].squeeze(0).float().numpy()))
                if i < len(parts) - 1:
                    chunks.append(SENT_GAP)
            chunks = [EDGE_PAD] + chunks + [EDGE_PAD]
            audio = np.concatenate(chunks)
            elapsed = time.time() - t0
        peak = float(np.abs(audio).max()) if audio.size else 0.0
        if peak > 0.99:
            audio = audio * (0.99 / peak)
        buf = io.BytesIO()
        sf.write(buf, audio, SR, format="WAV", subtype="PCM_16")
        data = buf.getvalue()
        disk.parent.mkdir(parents=True, exist_ok=True)
        tmp = disk.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(disk)
        self._mem_put(k, data)
        info = {"cache": "miss", "synth_s": round(elapsed, 3), "audio_s": round(len(audio) / SR, 3),
                "normalized": norm}
        log.info("synth %.2fs -> %.2fs audio | %s", elapsed, len(audio) / SR, norm)
        return data, info

    def _mem_put(self, k, data):
        self.mem[k] = data
        self.mem.move_to_end(k)
        while len(self.mem) > MEM_CACHE_SIZE:
            self.mem.popitem(last=False)


engine = TTSEngine()
if os.environ.get("TTS_WARMUP", "1") == "1":
    _t = time.time()
    for _v in engine.voices:
        engine.prompt(_v)
    with engine.lock, torch.inference_mode():  # first CUDA/cuDNN/ORT calls are slow; do them now
        _pr = engine.prompt("default") if "default" in engine.voices else engine.prompt(next(iter(engine.voices)))
        for _p in engine.prepare("你好，歡迎光臨。")[1]:
            _tok, _len = engine.fe._extract_text_token(_p)
            engine.cv.model.inference(text=_tok, text_len=_len, **_pr)
    log.info("warm-up done in %.1fs", time.time() - _t)
app = FastAPI(title="BreezyVoice TTS")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-TTS-Cache", "X-TTS-Synth-Seconds", "X-TTS-Audio-Seconds", "X-TTS-Speed"])


class TTSRequest(BaseModel):
    text: str
    voice: str = "default"
    seed: Optional[int] = None
    speed: Optional[float] = None


_tempo_cache = OrderedDict()


def retime(data, speed):
    """Speed a WAV up/down without changing pitch (ffmpeg atempo); small in-memory LRU."""
    if abs(speed - 1.0) < 0.01:
        return data, None
    key = (hashlib.sha1(data).hexdigest(), round(speed, 2))
    if key in _tempo_cache:
        _tempo_cache.move_to_end(key)
        return _tempo_cache[key]
    audio, sr = sf.read(io.BytesIO(data), dtype="float32")
    out = subprocess.run(["ffmpeg", "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "pipe:0",
                          "-filter:a", f"atempo={speed:.3f}", "-f", "f32le", "-ar", str(sr), "-ac", "1", "pipe:1"],
                         input=audio.astype(np.float32).tobytes(), capture_output=True, check=True).stdout
    fast = np.frombuffer(out, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, np.clip(fast, -1, 1), sr, format="WAV", subtype="PCM_16")
    res = (buf.getvalue(), round(len(fast) / sr, 3))
    _tempo_cache[key] = res
    while len(_tempo_cache) > MEM_CACHE_SIZE:
        _tempo_cache.popitem(last=False)
    return res


def _do(text, voice, seed=None, lock_held=False, speed=None):
    if not text or not text.strip():
        raise HTTPException(400, "text is empty")
    if len(text) > MAX_CHARS:
        raise HTTPException(413, f"text longer than {MAX_CHARS} chars")
    try:
        data, info = engine.synth(text, voice, seed, lock_held=lock_held)
    except KeyError:
        raise HTTPException(404, f"unknown voice '{voice}', have {list(engine.voices)}")
    speed = min(2.0, max(0.5, SPEED_DEFAULT if speed is None else float(speed)))
    data, fast_s = retime(data, speed)
    headers = {"X-TTS-Cache": info["cache"], "Cache-Control": "public, max-age=86400", "X-TTS-Speed": str(speed)}
    if "synth_s" in info:
        headers["X-TTS-Synth-Seconds"] = str(info["synth_s"])
        headers["X-TTS-Audio-Seconds"] = str(fast_s or info["audio_s"])
    return Response(content=data, media_type="audio/wav", headers=headers)


@app.post("/tts")
async def tts_post(req: TTSRequest, request: Request):
    # The GPU does one line at a time. While waiting for it, drop requests whose caller has gone away
    # (the page was interrupted), so stale lines never delay the line the visitor is waiting for.
    if req.text and len(req.text) <= MAX_CHARS and engine.cached(req.text, req.voice, req.seed) is None:
        while not engine.lock.acquire(blocking=False):
            if await request.is_disconnected():
                return Response(status_code=499)
            await asyncio.sleep(0.05)
        try:
            if await request.is_disconnected():
                return Response(status_code=499)
            return await asyncio.to_thread(_do, req.text, req.voice, req.seed, True, req.speed)
        finally:
            engine.lock.release()
    return _do(req.text, req.voice, req.seed, speed=req.speed)


@app.get("/tts")
def tts_get(text: str = Query(...), voice: str = "default", seed: Optional[int] = None, speed: Optional[float] = None):
    return _do(text, voice, seed, speed=speed)


@app.get("/health")
def health():
    engine.reload_voices()
    return {"ok": True, "voices": list(engine.voices), "sample_rate": SR, "model": MODEL_PATH,
            "device": str(engine.cv.model.device),
            "gpu_mem_gb": {"allocated": round(torch.cuda.memory_allocated() / 1e9, 2),
                           "reserved": round(torch.cuda.memory_reserved() / 1e9, 2),
                           "peak_reserved": round(torch.cuda.max_memory_reserved() / 1e9, 2)}
            if torch.cuda.is_available() else None}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("TTS_HOST", "127.0.0.1"), port=int(os.environ.get("TTS_PORT", "8100")))
