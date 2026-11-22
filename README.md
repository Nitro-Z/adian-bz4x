# 阿電 Adian: an honest EV advisor for gasoline-car owners

**Team Autonomind · 佳作 (Honorable Mention, one of 15 finalists), 2026 和泰 AI 黑客松 (Hotai Motor AI Hackathon), Taiwan**
Challenge: *TOYOTA｜智能轉型：AI助攻油轉電 TOYOTA EV 新生活* (helping Toyota gasoline-car owners decide whether to switch to an EV).

阿電 (Adian) is a web advisor that talks with a Toyota owner for about five minutes, about their commute, school runs, weekends and where they could charge. It then replays **their own week with a bZ4X** on a real map and gives an **honest verdict**. If an EV does not fit their life yet, it says so and recommends a Toyota hybrid instead. The motto is 「先誠實，後銷售」: honest first, sell later.

> Demo video: https://youtu.be/pZStLabzcnw
> The live demo ran on a lab GPU machine during the competition and is no longer online.

## What it does

1. **Two ways to answer.** A click-only form, or a conversation by voice or text where one sentence (「平日在信義區上班，下午接小孩去補習班…」) fills several answers at once.
2. **The customer's own week.** The advisor drives the real OSRM routes (home → office → school → mall …) on a 2D vector map (MapLibre) or Google Photorealistic 3D Tiles (CesiumJS). It stops at real charging stations from Taiwan's TDX open data and tracks battery, cost and CO₂ along the way.
3. **An honest verdict from code, not from the LLM.** The suitability score is S = 0.40·charging + 0.30·economics + 0.20·range + 0.10·lifestyle. There are four outcomes: 很適合 / 適合但有一個障礙 / 現在不建議 (the advisor then recommends hybrids) / 座位不夠 (it then recommends 7-seaters).
4. **Monthly cost against the customer's own car.** Fuel or electricity, maintenance and taxes, using official fuel-economy figures and the 財政部 tax table.
5. **Grounded Q&A (RAG).** Free questions are answered only from 35 official public passages (Toyota TW, 財政部, local-government charger guidelines …). Each answer shows its source. A number guard rejects any figure that does not appear in the passages. In an eval of 30 questions, 24/24 in-scope questions were answered from the right source, 3/3 out-of-scope questions got an honest "I don't know", and 3/3 trap questions were handled correctly.

## Design principle: "Gemma understands, code calculates"

The LLM never produces a number. It only maps free text or speech to the allowed answer slots, and the gateway validates its output. Every score, cost and distance is computed in code, so it can be reproduced and checked.

```
browser ──▶ gateway.py (FastAPI, 127.0.0.1 only; login, static site, APIs)
             ├─ /api/ask, /api/plan → Gemma 4 26B (local, Ollama): text → validated slots
             ├─ /api/kb             → EmbeddingGemma retrieval → Gemma answers from passages + number guard
             ├─ /tts                → Gemini TTS (streamed PCM), fallback BreezyVoice (local)
             ├─ /asr                → Breeze-ASR-25 (local; the customer's voice never leaves the machine)
             ├─ /api/ev/*           → TDX charging stations (cached)
             └─ /api/route, /api/poi, /api/geocode → OSRM, Overpass, Nominatim (cached)
```

The models were chosen on purpose. The team avoided PRC-made models, so it used Google Gemma and EmbeddingGemma, plus MediaTek Research's Breeze models for Taiwanese Mandarin speech.

## Repository layout

| Path | What |
|---|---|
| `04_app/website_v2/` | The final advisor (`advisor.html`), landing page and the week simulation (`assets/sim*.js`, `preview/sim3d.html`) |
| `04_app/website/` | The earlier v1 site, still served at `/` by the gateway |
| `04_app/gateway/` | FastAPI gateway, TDX client, RAG (`kb.py`, `kb/adian_kb.json`) |
| `04_app/tts/` | BreezyVoice TTS server and Breeze-ASR-25 server |
| `04_app/tests/` | Playwright harnesses: all 22×22 county commute pairs, all 367 districts × charging cases, one-screen layout audit, simulation timing, phone layout, RAG eval |
| `04_app/gcp/budget_kill/` | Cloud Run function that disables billing when the budget is reached |
| `03_proposal/video_src/` | Demo-video pipeline: HTML motion graphics rendered frame by frame with Playwright, then mixed with ffmpeg |
| `03_proposal/diagrams/` | Architecture diagram generators |

## What is not in this repo

- **Organizer data.** The competition's member data (CDP) and survey data stay with the organizer. That includes the k-means analysis scripts and everything derived from them (persona centroids, peer counts). Without those files the page falls back to simple rules.
- **Toyota photos.** They are replaced by neutral placeholder drawings. The showroom location list is also left out.
- **Secrets, models and media.** None of these are included: API keys, passwords, model weights, caches, videos.

## Running it (for reference)

The demo needs a GPU machine with Ollama (`gemma4:26b`, `embeddinggemma`), the BreezyVoice and Breeze-ASR environments, and a free [TDX](https://tdx.transportdata.tw/) API key. Gemini TTS is optional (`TTS_ENGINE=breezy` uses BreezyVoice only). Some scripts still contain absolute paths from the original lab machine.

```bash
04_app/tts/run_server.sh --bg && 04_app/tts/run_asr.sh --bg
cd 04_app/gateway && python gateway.py   # binds 127.0.0.1:8080; open /v2/
```

## Team Autonomind

林倉裕 (captain) · 范克南 · 阮氏秋賢 · 陳武喬英 · 陳阮雄 · advisors 胡氏妝, 吳安琪

Data credits: 交通部 TDX (charging stations), OpenStreetMap contributors (maps, routes, places), OpenFreeMap / OpenMapTiles, 內政部 open data (district and village boundaries), Google Map Tiles (3D view).

## License

No license is granted. The code is published to be read as a portfolio project; all rights reserved by the authors.
