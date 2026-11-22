"""Build timeline.json: scene windows, narration line timings, animation cues, SFX events, demo frame maps."""
import json, os, sys

V = os.path.dirname(os.path.abspath(__file__))
L = {x["id"]: x for x in json.load(open(f"{V}/script.json"))}

PLAN = [  # scene, line ids, lead-in (s), tail (s)
    ("hook", ["s1a", "s1b"], 1.0, 1.3),
    ("problem", ["s2a", "s2b", "s2c"], 0.8, 1.2),
    ("personas", ["p1", "p2"], 0.8, 1.4),
    ("intro", ["s3a", "s3b"], 1.0, 1.1),
    ("demo_voice", ["s4a", "s4b"], 1.0, 1.6),
    ("demo_score", ["s5a"], 0.8, 1.0),
    ("demo_tour", ["s5b"], 0.6, 2.0),
    ("demo_week", ["s6a"], 0.8, 0.9),
    ("demo_trip", ["s6b"], 0.6, 1.4),
    ("demo_lineup", ["l1", "l2"], 0.8, 1.3),
    ("demo_honest", ["s7a", "s7b"], 0.8, 1.4),
    ("ai", ["s8a", "s8b"], 1.0, 1.3),
    ("biz", ["s9a", "s9b", "s9c"], 0.9, 1.3),
    ("close", ["s10a"], 1.2, 7.5),
]
GAP = 0.75  # pause between sentences inside a scene
t = 0.0
scenes, lines = [], []
for name, ids, lead, tail in PLAN:
    start = t
    cur = start + lead
    for lid in ids:
        x = L[lid]
        lines.append({"id": lid, "scene": name, "start": round(cur, 3), "end": round(cur + x["dur_fast"], 3), "cap": x["cap"]})
        cur += x["dur_fast"] + GAP
    end = cur - GAP + tail
    scenes.append({"name": name, "start": round(start, 3), "end": round(end, 3)})
    t = end
TOTAL = round(t, 3)
ln = {l["id"]: l for l in lines}
sc = {s["name"]: s for s in scenes}

# ---- animation cues (absolute seconds); the page and the audio mix both read these
cues = {}
h = sc["hook"]["start"]
cues["hook_chips"] = [round(h + 0.25 + i * 0.32, 3) for i in range(6)]
cues["hook_title"] = ln["s1b"]["end"] - 0.6
cues["problem_cards"] = [ln["s2a"]["start"] + 0.2, ln["s2b"]["start"] + 0.1, ln["s2c"]["start"] + 0.1]
cues["persona_cards"] = [round(ln["p1"]["start"] + 0.2 + i * 0.3, 3) for i in range(5)]
cues["persona_hl"] = [ln["p2"]["start"] + 0.2, ln["p2"]["start"] + 2.4]
cues["lineup_note"] = ln["l2"]["start"] - 0.2
cues["intro_mascot"] = sc["intro"]["start"] + 0.35
cues["intro_bubble"] = ln["s3b"]["start"]
cues["voice_mic"] = None
cues["score_zoom"] = sc["demo_score"]["start"] + 0.4
cues["honest_cards"] = [ln["s7a"]["start"] + 0.2, ln["s7b"]["start"] + 3.3]
cues["ai_brain"] = ln["s8a"]["start"] + 0.3
cues["ai_abacus"] = ln["s8a"]["start"] + 3.2
cues["ai_chips"] = [round(ln["s8b"]["start"] + i * 0.55, 3) for i in range(5)]
cues["ai_badge"] = ln["s8b"]["end"] - 1.8
cues["biz_cheat"] = ln["s9a"]["start"] + 0.2
cues["biz_rent"] = ln["s9a"]["start"] + 4.6
cues["biz_gap"] = ln["s9b"]["start"] + 0.2
cues["biz_ab"] = ln["s9c"]["start"] + 0.1
cues["close_logo"] = ln["s10a"]["end"] + 0.4

# ---- demo frame maps: list of (video_time, dir, frame_index) built from capture timestamps
def frames(d):
    return json.load(open(f"{V}/demo/{d}/times.json"))
def seq(scene, parts, t0, t1):
    """parts: [(dir, from_s, to_s), ...] played back-to-back, stretched uniformly over [t0, t1]."""
    total = sum(b - a for _, a, b in parts)
    out, acc = [], 0.0
    for d, a, b in parts:
        ts = frames(d)
        for i, ft in enumerate(ts):
            if a <= ft <= b:
                out.append([round(t0 + (acc + ft - a) / total * (t1 - t0), 3), d, i])
        acc += b - a
    return out
v = sc["demo_voice"]
voice_seq = seq("demo_voice", [("d1_open", 3.5, 7.4), ("d1_voice", 0.0, frames("d1_voice")[-1])], v["start"] + 0.2, v["end"] - 0.1)
# mic turns on at the first d1_voice frame
cues["voice_mic"] = next(x[0] for x in voice_seq if x[1] == "d1_voice")
tr = sc["demo_tour"]
tour_seq = seq("demo_tour", [("d2_tour", 3.0, 23.0)], tr["start"] + 0.1, tr["end"] - 0.1)

# ---- SFX events (file, time, gain dB)
sfx = []
for s in scenes[1:]:
    sfx.append(("whoosh_in", s["start"] - 0.05, -9))
for tt in cues["hook_chips"]: sfx.append(("pop", tt, -10))
sfx.append(("swell", cues["hook_title"] - 1.2, -14))
sfx.append(("whoosh_in", cues["hook_title"], -8))
for tt in cues["problem_cards"]: sfx.append(("ding", tt + 0.15, -12))
for tt in cues["persona_cards"]: sfx.append(("pop", tt, -11))
for tt in cues["persona_hl"]: sfx.append(("click", tt, -8))
sfx.append(("ding", cues["lineup_note"], -11))
sfx.append(("pop", cues["intro_mascot"], -4))
sfx.append(("pop", cues["intro_bubble"], -9))
sfx.append(("mic_on", cues["voice_mic"], -6))
sfx.append(("success", cues["score_zoom"] + 0.6, -11))
for tt in cues["honest_cards"]: sfx.append(("click", tt, -6))
sfx.append(("pop", cues["ai_brain"], -8)); sfx.append(("pop", cues["ai_abacus"], -8))
for tt in cues["ai_chips"]: sfx.append(("click", tt, -8))
sfx.append(("ding", cues["ai_badge"], -11))
sfx.append(("whoosh_in", cues["biz_cheat"], -10)); sfx.append(("pop", cues["biz_rent"], -9)); sfx.append(("ding", cues["biz_gap"] + 0.4, -10)); sfx.append(("click", cues["biz_ab"], -8))
sfx.append(("swell", cues["close_logo"] - 1.4, -12)); sfx.append(("success", cues["close_logo"], -8))

out = {"total": TOTAL, "fps": 30, "scenes": scenes, "lines": lines, "cues": cues,
       "voice_seq": voice_seq, "tour_seq": tour_seq, "sfx": [[f, round(tt, 3), g] for f, tt, g in sfx]}
json.dump(out, open(f"{V}/timeline.json", "w"), ensure_ascii=False, indent=1)
print("total", TOTAL, "s |", " ".join(f"{s['name']}:{s['start']:.1f}-{s['end']:.1f}" for s in scenes))
