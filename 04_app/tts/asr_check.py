"""Transcribe samples/*.wav with openai-whisper (large-v3) as an intelligibility check."""
import glob, sys, numpy as np, soundfile as sf, whisper, opencc
m = whisper.load_model("large-v3", download_root=sys.argv[1] if len(sys.argv) > 1 else "whisper_models")
cc = opencc.OpenCC("s2t")
for f in sorted(glob.glob("samples/*.wav")):
    a, sr = sf.read(f, dtype="float32")
    # silence profile (20 ms frames below -45 dBFS)
    fr = a[: len(a) // 441 * 441].reshape(-1, 441); db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    voiced = np.where(db > -45)[0]
    lead, trail = voiced[0] * 0.02, (len(db) - 1 - voiced[-1]) * 0.02
    sil = (db[voiced[0]:voiced[-1]] < -45).mean()
    r = m.transcribe(f, language="zh", initial_prompt="以下是台灣華語。", temperature=0)
    print(f"{f}: lead {lead:.2f}s trail {trail:.2f}s internal-silence {sil:.0%}\n   ASR: {cc.convert(r['text'])}")
