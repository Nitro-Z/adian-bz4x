"""Speech-to-text server: MediaTek Research Breeze-ASR-25 (Whisper large-v2 fine-tuned for Taiwanese Mandarin
and Mandarin-English code-switching). Runs on the lab GPU, so visitors' voices never leave the lab.

POST /asr   body: audio file (WAV 16 kHz mono from the page; other formats are decoded with ffmpeg)
            → {"text": "...", "seconds": audio length, "asr_s": processing time}
GET  /health

Run:  ./run_asr.sh --bg      (port 8101; the demo gateway proxies /asr to it)
"""
import io
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(HERE / "hf_cache"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from transformers import WhisperForConditionalGeneration, WhisperProcessor  # noqa: E402

MODEL = os.environ.get("ASR_MODEL", "MediaTek-Research/Breeze-ASR-25")
SR = 16000
MAX_SECONDS = 30
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("asr")

t0 = time.time()
processor = WhisperProcessor.from_pretrained(MODEL)
model = WhisperForConditionalGeneration.from_pretrained(MODEL, torch_dtype=torch.float16).to("cuda").eval()
lock = threading.Lock()
log.info("loaded %s in %.1fs", MODEL, time.time() - t0)


def decode(data: bytes) -> np.ndarray:
    """WAV (what the page sends) is read directly; anything else goes through ffmpeg."""
    try:
        audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
        audio = audio.mean(axis=1)
        if sr != SR:
            idx = np.linspace(0, len(audio) - 1, int(len(audio) * SR / sr))
            audio = np.interp(idx, np.arange(len(audio)), audio).astype(np.float32)
        return audio
    except Exception:
        out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
                             input=data, capture_output=True, timeout=30)
        if out.returncode != 0:
            raise HTTPException(400, "cannot decode audio")
        return np.frombuffer(out.stdout, dtype=np.float32)


# Whisper sometimes invents these on silence or noise
HALLUCINATIONS = ("謝謝觀看", "謝謝收看", "字幕", "訂閱", "點贊", "按讚", "請不吝", "明鏡", "Thank you", "感謝觀看")


def transcribe(audio: np.ndarray, prompt: str = "") -> str:
    feats = processor(audio, sampling_rate=SR, return_tensors="pt").input_features.to("cuda", torch.float16)
    kw = {}
    if prompt:
        # context prompt (the current question and its possible answers) biases Whisper toward the right words
        kw["prompt_ids"] = torch.tensor(processor.get_prompt_ids(prompt[:300]), device="cuda")
    with lock, torch.inference_mode():
        ids = model.generate(feats, language="zh", task="transcribe", max_new_tokens=120, **kw)
    text = processor.batch_decode(ids, skip_special_tokens=True)[0].strip()
    if prompt and text.startswith(prompt[:20]):          # some versions echo the prompt
        text = text[len(prompt[:300]):].strip()
    if any(h in text for h in HALLUCINATIONS):
        return ""
    return text


app = FastAPI(title="Breeze-ASR-25")


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}


@app.post("/asr")
async def asr(request: Request):
    data = await request.body()
    if not data:
        raise HTTPException(400, "empty audio")
    audio = decode(data)
    secs = len(audio) / SR
    if secs < 0.3:
        return {"text": "", "seconds": round(secs, 2), "asr_s": 0}
    audio = audio[: SR * MAX_SECONDS]
    if float(np.sqrt(np.mean(audio ** 2))) < 0.002:     # basically silence
        return {"text": "", "seconds": round(secs, 2), "asr_s": 0}
    peak = float(np.abs(audio).max())
    if 0 < peak < 0.5:                                   # quiet microphone: normalize volume
        audio = audio * min(8.0, 0.9 / peak)
    prompt = request.query_params.get("prompt", "")
    t = time.time()
    import asyncio
    text = await asyncio.to_thread(transcribe, audio, prompt)
    took = time.time() - t
    log.info("asr %.1fs audio in %.2fs: %s", secs, took, text)
    return {"text": text, "seconds": round(secs, 2), "asr_s": round(took, 2)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("ASR_PORT", "8101")))
