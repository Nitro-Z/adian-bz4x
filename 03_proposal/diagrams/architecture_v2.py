"""阿電整體架構 v2 (11/17): 16:9 version for the final deck, updated to the current system.

Same visual language as architecture.py (light grey panels, white boxes with icons, code-style arrow labels,
blue = main conversation loop, orange = guard layer, green = live), but laid out for a full 16:9 slide with
larger text and no separate offline row (the offline k-means step is one item in the data-protection panel).

Changes vs the 10/13 diagram: Gemini TTS (voice Leda) is the main voice and BreezyVoice only the fallback;
knowledge base (RAG, EmbeddingGemma, 30/30) and the number guard; two modes (click form / chat);
2D/3D week simulation; hybrid recommendations; Whisper and the customer-facing persona box removed.

Run: python architecture_v2.py  → architecture_v2_{zh,vi}.svg / .png (2400 px wide, chip 「06」 for pitch slide 7)
Needs cairosvg or Playwright + Chromium, and the Noto Sans CJK TC font.
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MASCOT = os.path.join(HERE, "..", "..", "05_brand", "mascot", "adian.svg")

W, H = 2000, 1125
FONT = "Noto Sans CJK TC"
MONO = "Noto Sans Mono CJK TC"
INK, MUTED, LINE = "#1F2733", "#4B5567", "#3A4352"
PANEL, PANEL_LINE = "#EEF1F5", "#D7DCE4"
BLUE, ORANGE, ORANGE_BG, GREEN, DEEP = "#1F6FE5", "#C2410C", "#FFF1EA", "#27F550", "#0A7A2B"

T = {
    "chip": "3｜AI 應用方法",
    "title": "阿電整體架構：Gemma 負責聽懂，程式負責算數",
    "customer": ("顧客", ["汽油車車主・手機／電腦"]),
    "channels": "接觸通路",
    "ch_items": [("阿電網站", "已上線"), ("LINE OA", "規劃中"), ("My Toyota App", "規劃中"), ("保養廠平板", "規劃中")],
    "p4": "公開資料與雲端",
    "tdx": ("TDX 充電站・交通部", ["只留 bZ4X 能用的 CCS1／J1772"]),
    "osm": ("OSRM 路線・OSM 地點", ["真實路線、學校、商場、公園"]),
    "spec": ("官方公開資料", ["Toyota 官網・財政部・347 據點"]),
    "gcp": ("Google Cloud", ["Gemini 語音：只送阿電的台詞", "3D 地圖圖磚（Map Tiles）"]),
    "p1": ("瀏覽器・阿電網頁", "advisor.html"),
    "p1_note": "所有數字都由程式計算，LLM 不自行算數",
    "modes": ("兩種用法", ["👆 點選表單・💬 用聊的", "語音、打字、按鈕都可以"]),
    "identify": ("辨識顧客", ["會員：CDP 資料預填，不重問", "新朋友：只問到「區」"]),
    "flow": ("一週規劃", ["上班・接送・週末・充電・出遊", "一句話說一週 → Gemma 填好"]),
    "verdict": ("誠實結論・適配度 S", []),
    "verdict_chips": ["很適合", "有一個障礙", "現在不建議", "座位不夠"],
    "calc": ("試算引擎", ["每月費用 vs 顧客自己的車", "不適合 → 推薦 Toyota 油電車"]),
    "sim": ("你的一週・2D／3D 模擬", ["真實路線、充電、CO₂、省錢", "阿電語音導覽＋字幕"]),
    "p2": ("Gateway・FastAPI", "實驗室主機"),
    "p2_note": "密碼登入・noindex・不存放 CDP 資料",
    "geo": ("/api/route・/api/ev・/api/poi", ["路線快取・充電站快取 72 小時"]),
    "tts": ("/tts・/asr", ["Gemini 語音逐句串流", "備援 BreezyVoice・ASR 在本機"]),
    "ask": ("/api/ask・/api/plan・/api/kb：LLM 防護層", ["只接受允許的選項・地點必須存在",
                                                        "知識庫只用官方資料回答，附來源（測試 30/30）",
                                                        "數字守門：回答裡的數字必須出自資料"]),
    "p3": ("本機 AI 模型", "1 張 RTX 5090"),
    "p3_note": "顧客的聲音不外傳・不使用中國製模型",
    "gemma": ("Gemma 4 26B・Google", ["聽懂自由說法、填行程、回答題外話"]),
    "embed": ("EmbeddingGemma・Google", ["知識庫檢索：35 段官方資料"]),
    "asr": ("Breeze-ASR-25・聯發創新基地", ["顧客語音轉文字"]),
    "breezy": ("BreezyVoice・聯發創新基地", ["語音備援（Gemini 無法使用時）"]),
    "p6": "資料保護與誠實",
    "p6_items": ["CDP 只在團隊電腦離線分析（K-means）", "網站只有統計值（每格 ≥ 10 人）",
                 "Demo 需密碼，不被搜尋引擎收錄", "LLM 不算數字；數字來自程式與官方資料",
                 "不適合就直說 → 油電車／7 人座", "比賽後刪除主辦單位資料"],
    "a_cust": "點選・語音・打字", "a_back": "阿電語音＋字幕", "a_https": "HTTPS",
    "a_ask": "POST /api/ask・plan・kb", "a_ok": "有效答案＋附來源的回覆",
    "a_geo": "GET 路線・充電站・地點", "a_tts": "POST /tts・/asr", "a_gemma": "JSON・檢索",
    "a_asr": "語音 → 文字", "a_pub": "API・快取",
}

TV = {
    "chip": "3｜Phương pháp ứng dụng AI",
    "title": "Kiến trúc A-Dian: Gemma lo hiểu, chương trình lo tính",
    "customer": ("Khách hàng", ["chủ xe xăng・điện thoại, PC"]),
    "channels": "Kênh tiếp cận",
    "ch_items": [("Web A-Dian", "đã chạy"), ("LINE OA", "kế hoạch"), ("My Toyota App", "kế hoạch"), ("Tablet ở xưởng", "kế hoạch")],
    "p4": "Dữ liệu & cloud",
    "tdx": ("Trạm sạc TDX", ["chuẩn CCS1/J1772 hợp bZ4X"]),
    "osm": ("OSRM・OSM", ["tuyến đường, trường, TTTM"]),
    "spec": ("Dữ liệu chính thức", ["web Toyota・Bộ Tài chính"]),
    "gcp": ("Google Cloud", ["Gemini: chỉ đọc lời A-Dian", "Ô bản đồ 3D (Map Tiles)"]),
    "p1": ("Trình duyệt・web A-Dian", "advisor.html"),
    "p1_note": "Mọi con số do chương trình tính, LLM không tự tính",
    "modes": ("Hai cách dùng", ["👆 Bấm chọn・💬 Trò chuyện", "giọng nói, gõ chữ, nút bấm"]),
    "identify": ("Nhận diện khách", ["Hội viên: điền sẵn từ CDP", "Khách mới: chỉ hỏi tới quận"]),
    "flow": ("Kế hoạch một tuần", ["đi làm・đưa đón・cuối tuần・sạc", "nói 1 câu → Gemma điền sẵn"]),
    "verdict": ("Kết luận trung thực・điểm S", []),
    "verdict_chips": ["Rất phù hợp", "Còn 1 trở ngại", "Chưa nên", "Thiếu chỗ"],
    "calc": ("Bộ tính toán", ["chi phí tháng vs xe hiện tại", "không hợp → gợi ý hybrid Toyota"]),
    "sim": ("Mô phỏng tuần 2D/3D", ["tuyến thật, sạc, CO₂, tiết kiệm", "A-Dian thuyết minh + phụ đề"]),
    "p2": ("Gateway・FastAPI", "máy lab"),
    "p2_note": "Mật khẩu・noindex・không lưu dữ liệu CDP",
    "geo": ("/api/route・/api/ev・/api/poi", ["cache tuyến・cache trạm sạc 72 giờ"]),
    "tts": ("/tts・/asr", ["Giọng Gemini, phát từng câu", "dự phòng BreezyVoice・ASR tại máy"]),
    "ask": ("/api/ask・/api/plan・/api/kb: lớp kiểm soát LLM", ["chỉ nhận lựa chọn hợp lệ・địa điểm phải có thật",
                                                             "kho tri thức chỉ dùng tài liệu chính thức, có nguồn (30/30)",
                                                             "chặn số liệu: số trong câu trả lời phải có trong tài liệu"]),
    "p3": ("AI chạy tại máy", "1 GPU RTX 5090"),
    "p3_note": "Giọng khách không rời máy・không dùng model Trung Quốc",
    "gemma": ("Gemma 4 26B・Google", ["hiểu câu nói tự do, điền lịch, trả lời ngoài lề"]),
    "embed": ("EmbeddingGemma・Google", ["tìm trong kho tri thức: 35 đoạn chính thức"]),
    "asr": ("Breeze-ASR-25・MediaTek Research", ["chuyển giọng khách thành chữ"]),
    "breezy": ("BreezyVoice・MediaTek Research", ["giọng dự phòng (khi Gemini lỗi)"]),
    "p6": "Bảo vệ dữ liệu & trung thực",
    "p6_items": ["CDP chỉ phân tích offline trên máy đội (K-means)", "Web chỉ có số thống kê (mỗi ô ≥ 10 người)",
                 "Demo có mật khẩu, không cho Google index", "LLM không tính số; số do chương trình tính",
                 "Không hợp thì nói thẳng → hybrid / xe 7 chỗ", "Xóa dữ liệu BTC sau cuộc thi"],
    "a_cust": "bấm・nói・gõ", "a_back": "", "a_https": "HTTPS",
    "a_ask": "", "a_ok": "", "a_geo": "GET tuyến・trạm sạc・địa điểm", "a_tts": "POST /tts・/asr", "a_gemma": "",
    "a_asr": "", "a_pub": "",
}
TEXTS = {"zh": T, "vi": TV}
# chip text when the diagram is used as pitch slide 7
PITCH_CHIP = {"zh": "06｜AI 架構", "vi": "06｜Kiến trúc AI"}

BODY = 20      # body text in boxes
BOX_T = 24     # box titles
PANEL_T = 28   # panel titles


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=BODY, weight=400, fill=INK, anchor="start", font=FONT, rotate=None):
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{tr}>{esc(s)}</text>')


def len_px(s, size):
    return sum(size if ord(c) > 0x2E80 else size * 0.56 for c in s)


TOP = []


def halo(svg_text, color=PANEL, width=7):
    under = svg_text.replace("<text ", f'<text stroke="{color}" stroke-width="{width}" stroke-linejoin="round" ', 1)
    return under + svg_text


def panel(x, y, w, h, icon_name, title, sub="", note=None):
    TOP.append(f'<rect x="{x + 18}" y="{y + 16}" width="40" height="40" rx="8" fill="{PANEL}"/>' + icon(icon_name, x + 23, y + 21, 30))
    TOP.append(halo(t(x + 66, y + 47, title, PANEL_T, 700)))
    if sub:
        TOP.append(halo(t(x + 78 + len_px(title, PANEL_T), y + 47, sub, 19, 400, MUTED)))
    if note:
        TOP.append(halo(t(x + 24, y + 82, note, 19, 700, ORANGE)))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="{PANEL}" stroke="{PANEL_LINE}" stroke-width="2"/>'


def box(x, y, w, h, icon_name, title, lines=(), stroke=LINE, fill="#FFFFFF", title_fill=INK, line_fill=MUTED,
        size=BOX_T, body=BODY, gap=27):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2.6"/>']
    tx = x + 18
    if icon_name:
        out.append(icon(icon_name, x + 16, y + 14, 26))
        tx = x + 52
    out.append(t(tx, y + 36, title, size, 700, title_fill))
    for i, ln in enumerate(lines):
        out.append(t(x + 18, y + 66 + i * gap, ln, body, 400, line_fill))
    return "\n".join(out)


def chip(x, y, label, fill, stroke, color, size=18):
    w = len_px(label, size) + 24
    return (f'<rect x="{x}" y="{y}" width="{w}" height="32" rx="16" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'
            + t(x + w / 2, y + 23, label, size, 700, color, "middle")), w


def arrow(points, color=LINE, width=2.6, dashed=False, both=False):
    d = "M " + " L ".join(f"{px} {py}" for px, py in points)
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    mid = "ah_blue" if color == BLUE else "ah_green" if color == DEEP else "ah"
    start = f' marker-start="url(#{mid}_s)"' if both else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
            f'marker-end="url(#{mid})"{start} stroke-linejoin="round"/>')


LABELS = []


def label(x, y, s, color=LINE, anchor="start", rotate=None, size=17):
    LABELS.append(halo(t(x, y, s, size, 500, color, anchor, MONO, rotate), "#FFFFFF", 6))


ICONS = {
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    "browser": '<rect x="2.5" y="4" width="19" height="16" rx="2.5"/><path d="M2.5 9h19"/><circle cx="6" cy="6.5" r=".6"/><circle cx="8.5" cy="6.5" r=".6"/>',
    "server": '<rect x="3" y="3.5" width="18" height="7" rx="2"/><rect x="3" y="13.5" width="18" height="7" rx="2"/><path d="M7 7h.01M7 17h.01"/>',
    "chip": '<path d="M12 2l2.4 6.2L21 10.5l-6.6 2.3L12 19l-2.4-6.2L3 10.5l6.6-2.3z"/>',
    "db": '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "shield": '<path d="M12 2.5 4 5.5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11v-6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "map": '<path d="M12 21s-7-6.3-7-11.5a7 7 0 0 1 14 0C19 14.7 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    "calc": '<rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M8 6.5h8M8.5 11h.01M12 11h.01M15.5 11h.01M8.5 14.5h.01M12 14.5h.01M15.5 14.5h.01M8.5 18h.01M12 18h3.5"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "wave": '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10v4"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    "route": '<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="11" r="2.2"/><path d="M5.5 16c.6-1.6 1.9-2.4 3.5-2.4s2.9.8 3.5 2.4M14.5 10h4M14.5 13.5h3"/>',
    "verdict": '<path d="M12 3v18M5 7h14M5 7l-2.5 6a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0z"/>',
    "plug": '<path d="M9 2v5M15 2v5M6.5 7h11v4a5.5 5.5 0 0 1-11 0zM12 16.5V22"/>',
    "doc": '<path d="M6 2.5h8l4.5 4.5v14.5H6z"/><path d="M14 2.5V7h4.5M9 12h6M9 15.5h6"/>',
    "cloud": '<path d="M7 18h10.5a4 4 0 0 0 .6-7.95A6 6 0 0 0 6.6 9.6 4.2 4.2 0 0 0 7 18z"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6"/><path d="m15 15 5.5 5.5"/>',
    "hand": '<path d="M9 11V4.5a1.5 1.5 0 0 1 3 0V10M12 10V3.5a1.5 1.5 0 0 1 3 0V10M15 10V5a1.5 1.5 0 0 1 3 0v8a7 7 0 0 1-7 7 6 6 0 0 1-5-2.7L3.5 13a1.5 1.5 0 0 1 2.4-1.8L9 14"/>',
}


def icon(name, x, y, size):
    s = size / 24
    return (f'<g transform="translate({x} {y}) scale({s})" fill="none" stroke="{INK}" stroke-width="{1.9 / s * 0.9:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')


def mascot_image(x, y, w):
    try:
        data = base64.b64encode(open(MASCOT, "rb").read()).decode()
        return f'<image x="{x}" y="{y}" width="{w}" height="{w * 0.62}" href="data:image/svg+xml;base64,{data}"/>'
    except OSError:
        return ""


def build(T=T):
    o = [f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    o.append("<defs>" + "".join(
        f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>'
        f'<marker id="{mid}_s" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>'
        for mid, col in (("ah", LINE), ("ah_blue", BLUE), ("ah_green", DEEP))) + "</defs>")

    # header: chip + title (deck style)
    cw = len_px(T["chip"], 22) + 40
    o.append(f'<rect x="36" y="22" width="{cw}" height="44" rx="22" fill="{GREEN}" stroke="#141B2D" stroke-width="3"/>')
    o.append(t(36 + cw / 2, 52, T["chip"], 22, 700, "#141B2D", "middle"))
    o.append(t(36, 124, T["title"], 44, 700, "#141B2D"))

    Y0 = 160
    # ---- left column
    o.append(box(30, Y0, 330, 96, "user", T["customer"][0], T["customer"][1]))
    o.append(f'<rect x="30" y="{Y0 + 130}" width="330" height="262" rx="12" fill="#FFFFFF" stroke="{LINE}" stroke-width="2.6"/>')
    o.append(icon("chat", 46, Y0 + 144, 26))
    o.append(t(82, Y0 + 166, T["channels"], BOX_T, 700))
    for i, (name, state) in enumerate(T["ch_items"]):
        yy = Y0 + 186 + i * 50
        live = i == 0
        o.append(f'<rect x="46" y="{yy}" width="298" height="40" rx="10" fill="{"#E9FCEB" if live else "#F7F8FA"}" '
                 f'stroke="{DEEP if live else "#C9D0DA"}" stroke-width="2"/>')
        o.append(t(62, yy + 28, name, 20, 700))
        o.append(t(330, yy + 28, state, 17, 700, DEEP if live else MUTED, "end"))

    py = Y0 + 418
    o.append(panel(14, py, 362, H - py - 14, "db", T["p4"]))
    bx, bw = 30, 330
    o.append(box(bx, py + 72, bw, 92, "plug", T["tdx"][0], T["tdx"][1]))
    o.append(box(bx, py + 176, bw, 92, "route", T["osm"][0], T["osm"][1]))
    o.append(box(bx, py + 280, bw, 92, "doc", T["spec"][0], T["spec"][1]))
    o.append(box(bx, py + 384, bw, 122, "cloud", T["gcp"][0], T["gcp"][1]))

    # ---- center top: browser
    cx, cw2 = 400, 900
    o.append(panel(cx, Y0, cw2, 496, "browser", T["p1"][0], T["p1"][1], T["p1_note"]))
    c1, c2, bw2 = cx + 24, cx + 462, 414
    r1, r2, r3, bh = Y0 + 100, Y0 + 230, Y0 + 360, 120
    o.append(box(c1, r1, bw2, bh, "hand", T["modes"][0], T["modes"][1]))
    o.append(box(c2, r1, bw2, bh, "id", T["identify"][0], T["identify"][1]))
    o.append(box(c1, r2, bw2, bh, "chat", T["flow"][0], T["flow"][1], stroke=BLUE))
    o.append(box(c2, r2, bw2, bh, "verdict", T["verdict"][0]))
    xs, yrow = [c2 + 18, c2 + 18], [r2 + 50, r2 + 88]
    for i, c in enumerate(T["verdict_chips"]):
        r = 0 if i < 2 else 1
        fill, col = [("#E9FCEB", DEEP), ("#FFF4E5", ORANGE), ("#EEF1F5", "#475569"), ("#EEF1F5", "#475569")][i]
        svg, w = chip(xs[r], yrow[r], c, fill, col, col)
        o.append(svg)
        xs[r] += w + 10
    o.append(box(c1, r3, bw2, bh, "calc", T["calc"][0], T["calc"][1]))
    o.append(box(c2, r3, bw2, bh, "map", T["sim"][0], T["sim"][1], stroke=DEEP))
    o.append(mascot_image(c2 + bw2 - 86, r3 + 6, 72))
    # inner arrows
    o.append(arrow([(c1 + bw2, r1 + 62), (c2 - 2, r1 + 62)]))
    o.append(arrow([(c1 + bw2 / 2, r1 + bh), (c1 + bw2 / 2, r2 - 2)]))
    o.append(arrow([(c1 + bw2, r2 + 62), (c2 - 2, r2 + 62)], color=BLUE))
    o.append(arrow([(c2 + bw2 / 2, r2 + bh), (c2 + bw2 / 2, r3 - 2)]))
    o.append(arrow([(c2, r3 + 62), (c1 + bw2 + 2, r3 + 62)], both=True))

    # ---- center bottom: gateway
    gy = Y0 + 552
    o.append(panel(cx, gy, cw2, H - gy - 14, "server", T["p2"][0], T["p2"][1], T["p2_note"]))
    o.append(box(c1, gy + 92, bw2, 98, "route", T["geo"][0], T["geo"][1], size=22))
    o.append(box(c2, gy + 92, bw2, 124, "wave", T["tts"][0], T["tts"][1]))
    o.append(box(c1, gy + 230, cw2 - 48, 150, "shield", T["ask"][0], T["ask"][1],
                 stroke=ORANGE, fill=ORANGE_BG, title_fill=INK, line_fill="#7A2E0B", body=20, gap=29))

    # ---- right top: local AI
    rx, rw = 1330, 656
    o.append(panel(rx, Y0, rw, 496, "chip", T["p3"][0], T["p3"][1], T["p3_note"]))
    rb, rbw = rx + 22, rw - 44
    o.append(box(rb, Y0 + 100, rbw, 88, "chip", T["gemma"][0], T["gemma"][1], stroke=BLUE))
    o.append(box(rb, Y0 + 198, rbw, 88, "search", T["embed"][0], T["embed"][1]))
    o.append(box(rb, Y0 + 296, rbw, 88, "mic", T["asr"][0], T["asr"][1]))
    o.append(box(rb, Y0 + 394, rbw, 88, "wave", T["breezy"][0], T["breezy"][1]))

    # ---- right bottom: data protection
    o.append(panel(rx, gy, rw, H - gy - 14, "shield", T["p6"]))
    for i, item in enumerate(T["p6_items"]):
        yy = gy + 66 + i * 54
        o.append(f'<rect x="{rb}" y="{yy}" width="{rbw}" height="46" rx="10" fill="#FFFFFF" stroke="{LINE}" stroke-width="2"/>')
        o.append(icon("check", rb + 12, yy + 11, 24))
        o.append(t(rb + 46, yy + 31, item, 20, 600, INK))

    # ================================================================ arrows between layers
    # customer -> channels
    o.append(arrow([(195, Y0 + 96), (195, Y0 + 128)]))
    label(206, Y0 + 120, T["a_cust"], size=16)
    # channels -> browser (HTTPS)
    o.append(arrow([(360, Y0 + 206), (398, Y0 + 206)]))
    label(364, Y0 + 196, T["a_https"], size=14)
    # browser -> customer (voice + captions)
    o.append(arrow([(400, Y0 + 48), (362, Y0 + 48)], color=BLUE))
    # flow (blue) -> guard and back
    fx = c1 - 12
    o.append(arrow([(c1, r2 + 90), (fx, r2 + 90), (fx, gy + 290), (c1 - 2, gy + 290)], color=BLUE))
    bxl = c2 - 24
    o.append(arrow([(bxl, gy + 228), (bxl, r2 + 100), (c1 + bw2 + 2, r2 + 100)], color=BLUE))
    # calc -> geo ; sim -> tts
    o.append(arrow([(c1 + 120, r3 + bh), (c1 + 120, gy + 90)]))
    label(c1 + 128, gy - 16, T["a_geo"], size=16)
    o.append(arrow([(c2 + 300, r3 + bh), (c2 + 300, gy + 90)]))
    label(c2 + 308, gy - 16, T["a_tts"], size=16)
    # geo -> public data (left)
    o.append(arrow([(c1, gy + 141), (cx - 6, gy + 141), (cx - 6, py + 118), (bx + bw + 2, py + 118)]))
    o.append(arrow([(cx - 6, py + 222), (bx + bw + 2, py + 222)]))
    # tts -> Google Cloud (Gemini voice) and -> ASR / BreezyVoice (right)
    o.append(arrow([(cx - 6, py + 222), (cx - 6, py + 445), (bx + bw + 2, py + 445)]))
    o.append(arrow([(c2 + bw2, gy + 154), (1312, gy + 154), (1312, Y0 + 340), (rb - 2, Y0 + 340)]))
    o.append(arrow([(1312, Y0 + 438), (rb - 2, Y0 + 438)]))
    # guard <-> Gemma / EmbeddingGemma (blue)
    o.append(arrow([(cx + cw2 - 24, gy + 305), (1322, gy + 305), (1322, Y0 + 144), (rb - 2, Y0 + 144)], color=BLUE, both=True))
    o.append(arrow([(1322, Y0 + 242), (rb - 2, Y0 + 242)], color=BLUE))

    o.extend(TOP); TOP.clear()
    o.extend(LABELS); LABELS.clear()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "\n".join(o) + "</svg>")


def render_png(svg, out_png):
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg.encode(), write_to=out_png, output_width=2400)
        return
    except ImportError:
        pass
    # no cairosvg on the lab machine: headless Chromium (the Playwright download) screenshots the SVG
    import glob, subprocess, tempfile
    chrome = (glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
              + glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))[0]
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(f'<html><body style="margin:0">{svg}</body></html>')
    subprocess.run([chrome, "--headless", "--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1.2",
                    f"--window-size={W},{H}", f"--screenshot={out_png}", "file://" + f.name],
                   check=True, capture_output=True)
    os.unlink(f.name)


def main():
    # pitch version (slide 7) for each language: architecture_v2_zh.png / architecture_v2_vi.png
    for lang in ("zh", "vi"):
        tx = dict(TEXTS[lang], chip=PITCH_CHIP[lang])
        svg = build(tx)
        stem = os.path.join(HERE, f"architecture_v2_{lang}")
        open(stem + ".svg", "w", encoding="utf-8").write(svg)
        render_png(svg, stem + ".png")
        print("ok", os.path.basename(stem))


if __name__ == "__main__":
    sys.exit(main())
