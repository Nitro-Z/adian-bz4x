"""Sơ đồ kiến trúc tổng thể của 阿電 (phong cách: khung xám nhạt, hộp trắng có icon, nhãn mũi tên kiểu code,
luồng chính màu xanh dương, lớp kiểm soát màu cam).

Chạy: python architecture.py
  → architecture.svg / architecture.png / architecture_1600.png        (tiếng Việt)
  → architecture_zh.svg / architecture_zh.png / architecture_zh_1600.png (繁體中文)
Cần cairosvg. Sửa chữ trong TEXT bên dưới; bố cục nằm trong build().
"""
import base64
import os
import sys

import cairosvg

HERE = os.path.dirname(os.path.abspath(__file__))
MASCOT = os.path.join(HERE, "..", "..", "05_brand", "mascot", "adian.svg")

W, H = 2000, 1560
FONT = "Noto Sans CJK TC"
MONO = "Noto Sans Mono CJK TC"
INK, MUTED, LINE = "#1F2733", "#5B6577", "#3A4352"
PANEL, PANEL_LINE = "#EEF1F5", "#D7DCE4"
BLUE, ORANGE, ORANGE_BG, GREEN, DEEP = "#1F6FE5", "#C2410C", "#FFF1EA", "#27F550", "#0A7A2B"

# ------------------------------------------------------------------ text (vi / zh)
TEXT = {
    "vi": {
        "title": "Kiến trúc tổng thể của 阿電",
        "customer": ("Khách hàng", ["chủ xe xăng · điện thoại / máy tính"]),
        "channels": ("Kênh tiếp cận", []),
        "ch_items": [("Website 阿電", "đang chạy"), ("LINE OA", "lộ trình"), ("Tablet tại xưởng", "lộ trình")],
        "ch_note": ["Hội viên đăng nhập (dữ liệu CDP", "điền sẵn) hoặc khách mới"],
        "p1": ("Trình duyệt · trang tư vấn 阿電", "advisor.html · JavaScript"),
        "p1_note": "mọi con số đều do code tính, LLM không tự tính số",
        "identify": ("Nhận diện khách", ["Hội viên: hồ sơ CDP mẫu điền sẵn", "Khách mới: 4 câu hỏi nhanh"]),
        "persona": ("Ghép persona (k-means)", ["tâm cụm gần nhất trong 5 persona A–E", "→ câu mở đầu & lời khuyên theo Playbook"]),
        "flow": ("Luồng hội thoại", ["quận → 里 → nơi làm → mục đích → số chỗ", "→ sạc → km/ngày → nỗi lo",
                                       "bấm nút: xử lý ngay · gõ tự do: hỏi LLM"]),
        "verdict": ("Kết luận trung thực · điểm S", []),
        "verdict_chips": ["很適合", "有一個障礙", "現在不建議", "座位不夠"],
        "verdict_sub": "điểm S 0–100 · loại ngay: cần 7 chỗ, sạc quá khó",
        "calc": ("Bộ tính toán", ["chi phí tháng · TCO 5 năm", "so với RAV4 / Corolla Cross", "mô phỏng 1 tuần · đi xa · xe 7 chỗ"]),
        "voice": ("阿電 nói · 業務小抄", ["nhép miệng theo âm lượng · phụ đề", "5 dòng tóm tắt gửi sales"]),
        "p2": ("Gateway · FastAPI", "máy lab · Cloudflare tunnel"),
        "p2_note": "mật khẩu · noindex · không chứa dữ liệu CDP",
        "geo": ("/api/route · /api/ev", ["tuyến đường OSRM (cache)", "trạm sạc gần nhà / công ty · cache TDX 72 giờ"]),
        "tts": ("/tts · /asr · giọng nói", ["TTS: chia câu, tải trước, hủy câu cũ", "ASR: ghi âm WAV → Breeze-ASR-25"]),
        "ask": ("/api/ask · lớp kiểm soát LLM", ["gửi: câu khách + 8 tin gần nhất + các lựa chọn hợp lệ",
                                                 "chỉ nhận đáp án nằm trong lựa chọn · địa điểm phải tồn tại",
                                                 "câu đáp chỉ dựa trên FACTS chính thức · không bịa số"]),
        "p3": ("AI chạy local", "máy lab · 1 GPU RTX 5090"),
        "p3_note": "dữ liệu khách không rời máy lab · không dùng model Trung Quốc",
        "breezy": ("BreezyVoice · MediaTek Research", ["TTS tiếng Phổ thông Đài Loan, giọng nữ tự nhiên", "câu đầu ≈ 1,5 giây · cache trên đĩa"]),
        "gemma": ("Gemma 4 26B · Google (Ollama)", ["hiểu câu gõ tự do, trả lời câu ngoài lề",
                                                     "trích thông tin phụ (vd. cần 7 chỗ) · ≈ 0,3 giây"]),
        "asr": ("Breeze-ASR-25 · MediaTek Research", ["nghe khách nói → chữ, ≈ 0,3 giây · chạy mọi trình duyệt"]),
        "whisper": ("Whisper large-v3", ["kiểm tra phát âm mọi câu thoại (offline QA)"]),
        "p4": ("Dữ liệu công khai", ""),
        "tdx": ("TDX · Bộ Giao thông", ["API trạm sạc (thành phố, cao tốc)", "3.207 trạm · 2.871 hợp bZ4X", "bản thật: + OpenHub (My Toyota)"]),
        "osm": ("OpenStreetMap / OSRM", ["tuyến đường · thời gian · bản đồ"]),
        "admin": ("Quận & 里", ["OSM 367 quận · 內政部 7.780 里"]),
        "spec": ("Nguồn chính thức", ["toyota.com.tw · U-CAR · 8891", "thông số · giá · bảo dưỡng"]),
        "p6": ("Bảo vệ dữ liệu & trung thực", ""),
        "p6_items": ["CDP chỉ ở máy team; server chỉ có số tổng hợp", "Demo có mật khẩu, không cho Google index",
                     "LLM không tự tính số; số liệu từ code + nguồn chính thức", "Mọi câu trả lời của LLM được kiểm tra trước khi dùng",
                     "Không hợp thì nói thẳng → gợi ý hybrid / xe 7 chỗ", "Xóa dữ liệu ban tổ chức sau cuộc thi"],
        "p5": ("Phân tích offline", "chạy trên máy team, không lên server"),
        "off": [("CDP · 1,05 triệu dòng", ["dữ liệu ban tổ chức", "+ khảo sát Kantar W3"]),
                ("Làm sạch & tạo biến", ["≈ 800 nghìn chủ xe xăng", "5 biến chuẩn hóa"]),
                ("k-means · k = 5", ["scikit-learn", "silhouette ≈ 0,31"]),
                ("5 persona A–E", ["Persona Playbook", "kênh · thời điểm · câu mở đầu"]),
                ("personas.json", ["mean · std · tâm cụm", "không có dữ liệu cá nhân"])],
        "a_cust": "tin nhắn · giọng nói · bấm chọn", "a_back": "giọng nói + phụ đề", "a_https": "HTTPS",
        "a_ask": "POST /api/ask", "a_ok": "đáp án hợp lệ + câu đáp", "a_geo": "GET /api/route · /api/ev", "a_tts": "POST /tts · /asr",
        "a_gemma": "chat() · JSON", "a_breezy": "từng câu → wav", "a_json": "personas.json · chỉ số tổng hợp",
        "a_tdx": "OAuth · API", "a_osm": "route()",
    },
    "zh": {
        "title": "阿電整體架構",
        "customer": ("顧客", ["汽油車車主 · 手機／電腦"]),
        "channels": ("接觸通路", []),
        "ch_items": [("阿電官網", "已上線"), ("LINE OA", "規劃中"), ("展示中心平板", "規劃中")],
        "ch_note": ["會員登入（CDP 資料預填）", "或新訪客"],
        "p1": ("瀏覽器 · 阿電諮詢頁", "advisor.html · JavaScript"),
        "p1_note": "所有數字都由程式計算，LLM 不自行計算",
        "identify": ("辨識顧客", ["會員：CDP 示範資料預填", "新訪客：4 個快速問題"]),
        "persona": ("Persona 比對（k-means）", ["找出 A–E 中最近的群中心", "→ 依 Playbook 給開場白與建議"]),
        "flow": ("對話流程", ["行政區 → 里 → 公司 → 用途 → 座位", "→ 充電 → 每日里程 → 擔心的事",
                               "點選：直接處理 · 自由輸入：交給 LLM"]),
        "verdict": ("誠實的結論 · 適配度 S", []),
        "verdict_chips": ["很適合", "有一個障礙", "現在不建議", "座位不夠"],
        "verdict_sub": "S（0–100）· 一票否決：座位、充電",
        "calc": ("試算引擎", ["每月費用 · 5 年總持有成本", "對比 RAV4／Corolla Cross", "一週模擬 · 長途旅程 · 7 人座"]),
        "voice": ("阿電說話與業務小抄", ["依真實音量對嘴 · 字幕", "5 行看車小抄（經顧客同意）"]),
        "p2": ("Gateway · FastAPI", "實驗室主機 · Cloudflare tunnel"),
        "p2_note": "密碼登入 · noindex · 不存放 CDP 資料",
        "geo": ("/api/route · /api/ev", ["OSRM 路線（快取）", "住家／公司附近充電站 · TDX 快取 72 小時"]),
        "tts": ("/tts · /asr · 語音", ["TTS：逐句生成、預先產生、取消舊句", "ASR：錄音 WAV → Breeze-ASR-25"]),
        "ask": ("/api/ask · LLM 防護層", ["傳入：顧客訊息 + 最近 8 則對話 + 允許的選項",
                                         "只接受允許的選項 · 地點必須存在",
                                         "回答只根據官方事實 · 不編造數字"]),
        "p3": ("本機 AI 模型", "實驗室主機 · 1 張 RTX 5090"),
        "p3_note": "顧客資料不離開實驗室 · 不使用中國大陸模型",
        "breezy": ("BreezyVoice · 聯發創新基地", ["台灣華語語音合成，自然女聲", "第一句約 1.5 秒 · 磁碟快取"]),
        "gemma": ("Gemma 4 26B · Google（Ollama）", ["理解自由輸入、回答題外話", "擷取附帶資訊（如需 7 人座）· 約 0.3 秒"]),
        "asr": ("Breeze-ASR-25 · 聯發創新基地", ["顧客語音轉文字，約 0.3 秒 · 各種瀏覽器皆可"]),
        "whisper": ("Whisper large-v3", ["檢查每句台詞的發音（離線品管）"]),
        "p4": ("公開資料與 API", ""),
        "tdx": ("TDX · 交通部", ["縣市與服務區充電站 API", "3,207 站 · 2,871 站適用 bZ4X", "正式版：＋ OpenHub（My Toyota）"]),
        "osm": ("OpenStreetMap / OSRM", ["路線 · 時間 · 地圖"]),
        "admin": ("行政區與村里", ["OSM 367 區 · 內政部 7,780 里"]),
        "spec": ("官方與公開來源", ["toyota.com.tw · U-CAR · 8891", "規格 · 價格 · 保養費用"]),
        "p6": ("資料保護與誠實", ""),
        "p6_items": ["CDP 只在團隊電腦；伺服器只有統計值", "Demo 需密碼，不被搜尋引擎收錄",
                     "LLM 不算數字；數字來自程式與官方來源", "LLM 的每個回答都先經過檢查",
                     "不適合就直說 → 建議油電車／7 人座", "比賽結束後刪除主辦單位資料"],
        "p5": ("離線分析", "在團隊電腦執行，不上伺服器"),
        "off": [("CDP · 105 萬筆", ["主辦單位資料", "＋ Kantar W3 調查"]),
                ("清理與特徵", ["約 80 萬名汽油車車主", "5 個標準化變數"]),
                ("k-means · k = 5", ["scikit-learn", "silhouette ≈ 0.31"]),
                ("5 個 Persona A–E", ["Persona Playbook", "通路 · 時機 · 開場白"]),
                ("personas.json", ["平均 · 標準差 · 群中心", "不含個人資料"])],
        "a_cust": "訊息 · 語音 · 點選", "a_back": "語音 + 字幕", "a_https": "HTTPS",
        "a_ask": "POST /api/ask", "a_ok": "有效答案 + 回覆", "a_geo": "GET /api/route · /api/ev", "a_tts": "POST /tts · /asr",
        "a_gemma": "chat() · JSON", "a_breezy": "逐句 → wav", "a_json": "personas.json · 只有統計值",
        "a_tdx": "OAuth · API", "a_osm": "route()",
    },
}


# ------------------------------------------------------------------ drawing helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def t(x, y, s, size=17, weight=400, fill=INK, anchor="start", font=FONT, rotate=None):
    tr = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
            f'text-anchor="{anchor}"{tr}>{esc(s)}</text>')


TOP = []  # panel headers, drawn last (above the arrows) with a halo


def halo(svg_text, color=PANEL, width=7):
    # cairosvg ignores paint-order, so draw a stroked copy underneath, then the real text on top
    under = svg_text.replace("<text ", f'<text stroke="{color}" stroke-width="{width}" stroke-linejoin="round" ', 1)
    return under + svg_text


def panel(x, y, w, h, icon_name, title, sub, note=None):
    TOP.append(f'<rect x="{x + 22}" y="{y + 22}" width="38" height="38" rx="8" fill="{PANEL}"/>' + icon(icon_name, x + 28, y + 26, 30))
    TOP.append(halo(t(x + 70, y + 50, title, 26, 700)))
    if sub:
        TOP.append(halo(t(x + 78 + len_px(title, 26), y + 50, sub, 17, 400, MUTED)))
    if note:
        TOP.append(halo(t(x + 30, y + 84, note, 17, 600, ORANGE)))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{PANEL}" stroke="{PANEL_LINE}" stroke-width="2"/>'


def len_px(s, size):
    # rough width: CJK ≈ 1 em, latin ≈ 0.55 em
    return sum(size if ord(c) > 0x2E80 else size * 0.56 for c in s)


def box(x, y, w, h, icon_name, title, lines=(), stroke=LINE, fill="#FFFFFF", title_fill=INK, line_fill=MUTED, size=21):
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2.4"/>']
    tx = x + 22
    if icon_name:
        out.append(icon(icon_name, x + 20, y + 20, 24))
        tx = x + 54
    out.append(t(tx, y + 40, title, size, 700, title_fill))
    for i, ln in enumerate(lines):
        out.append(t(x + 22, y + 70 + i * 25, ln, 16, 400, line_fill))
    return "\n".join(out)


def chip(x, y, label, fill="#FFFFFF", stroke="#C9D0DA", color=INK, size=15, font=FONT, weight=600):
    w = len_px(label, size) + 26
    return (f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="15" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
            + t(x + w / 2, y + 21, label, size, weight, color, "middle", font)), w


def arrow(points, color=LINE, width=2.4, dashed=False, both=False):
    d = "M " + " L ".join(f"{px} {py}" for px, py in points)
    dash = ' stroke-dasharray="8 7"' if dashed else ""
    mid = "ah_blue" if color == BLUE else "ah_green" if color == DEEP else "ah"
    start = f' marker-start="url(#{mid}_s)"' if both else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{dash} '
            f'marker-end="url(#{mid})"{start} stroke-linejoin="round"/>')


def label(x, y, s, color=LINE, anchor="start", rotate=None, size=15):
    return halo(t(x, y, s, size, 500, color, anchor, MONO, rotate), "#FFFFFF", 5)


ICONS = {
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    "browser": '<rect x="2.5" y="4" width="19" height="16" rx="2.5"/><path d="M2.5 9h19"/><circle cx="6" cy="6.5" r=".6"/><circle cx="8.5" cy="6.5" r=".6"/>',
    "server": '<rect x="3" y="3.5" width="18" height="7" rx="2"/><rect x="3" y="13.5" width="18" height="7" rx="2"/><path d="M7 7h.01M7 17h.01"/>',
    "chip": '<path d="M12 2l2.4 6.2L21 10.5l-6.6 2.3L12 19l-2.4-6.2L3 10.5l6.6-2.3z"/>',
    "db": '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "shield": '<path d="M12 2.5 4 5.5v6c0 5 3.4 9.3 8 11 4.6-1.7 8-6 8-11v-6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    "map": '<path d="M12 21s-7-6.3-7-11.5a7 7 0 0 1 14 0C19 14.7 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "cluster": '<circle cx="6" cy="7" r="2.2"/><circle cx="9" cy="10" r="1.6"/><circle cx="17" cy="6" r="2"/><circle cx="15" cy="16" r="2.2"/><circle cx="18.5" cy="18" r="1.4"/><circle cx="7" cy="17" r="1.8"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4z"/><path d="M8 9h8M8 12h5"/>',
    "calc": '<rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M8 6.5h8M8.5 11h.01M12 11h.01M15.5 11h.01M8.5 14.5h.01M12 14.5h.01M15.5 14.5h.01M8.5 18h.01M12 18h3.5"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "wave": '<path d="M4 10v4M8 7v10M12 4v16M16 8v8M20 10v4"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    "route": '<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><circle cx="9" cy="11" r="2.2"/><path d="M5.5 16c.6-1.6 1.9-2.4 3.5-2.4s2.9.8 3.5 2.4M14.5 10h4M14.5 13.5h3"/>',
    "verdict": '<path d="M12 3v18M5 7h14M5 7l-2.5 6a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0z"/>',
    "plug": '<path d="M9 2v5M15 2v5M6.5 7h11v4a5.5 5.5 0 0 1-11 0zM12 16.5V22"/>',
    "bolt": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "doc": '<path d="M6 2.5h8l4.5 4.5v14.5H6z"/><path d="M14 2.5V7h4.5M9 12h6M9 15.5h6"/>',
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


# ------------------------------------------------------------------ layout
def build(lang):
    T = TEXT[lang]
    o = []
    o.append(f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>')
    # markers
    o.append("<defs>" + "".join(
        f'<marker id="{mid}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>'
        f'<marker id="{mid}_s" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{col}"/></marker>'
        for mid, col in (("ah", LINE), ("ah_blue", BLUE), ("ah_green", DEEP))) + "</defs>")

    # ---- left column: customer, channels, public data
    o.append(box(40, 130, 300, 120, "user", T["customer"][0], T["customer"][1]))
    o.append(f'<rect x="40" y="330" width="300" height="300" rx="14" fill="#FFFFFF" stroke="{LINE}" stroke-width="2.4"/>')
    o.append(icon("chat", 60, 350, 24))
    o.append(t(94, 370, T["channels"][0], 21, 700))
    for i, (name, state) in enumerate(T["ch_items"]):
        yy = 395 + i * 52
        live = i == 0
        o.append(f'<rect x="60" y="{yy}" width="260" height="40" rx="10" fill="{"#E9FCEB" if live else "#F7F8FA"}" '
                 f'stroke="{DEEP if live else "#C9D0DA"}" stroke-width="1.8"/>')
        o.append(t(76, yy + 26, name, 17, 700))
        o.append(t(306, yy + 26, state, 14, 600, DEEP if live else MUTED, "end"))
    for i, ln in enumerate(T["ch_note"]):
        o.append(t(60, 572 + i * 24, ln, 15, 400, MUTED))

    o.append(panel(20, 680, 340, 535, "db", T["p4"][0], ""))
    o.append(box(40, 750, 300, 135, "plug", T["tdx"][0], T["tdx"][1]))
    o.append(box(40, 897, 300, 90, "route", T["osm"][0], T["osm"][1], size=19))
    o.append(box(40, 999, 300, 85, "map", T["admin"][0], T["admin"][1]))
    o.append(box(40, 1096, 300, 106, "doc", T["spec"][0], T["spec"][1]))

    # ---- center top: browser
    o.append(panel(380, 40, 840, 715, "browser", T["p1"][0], T["p1"][1], T["p1_note"]))
    o.append(box(410, 145, 380, 135, "id", T["identify"][0], T["identify"][1]))
    o.append(box(830, 145, 360, 135, "cluster", T["persona"][0], T["persona"][1]))
    o.append(box(410, 330, 380, 150, "chat", T["flow"][0], T["flow"][1], stroke=BLUE))
    # verdict box with chips
    o.append(box(830, 330, 360, 150, "verdict", T["verdict"][0]))
    # chips in two rows
    row = [(852, 385), (852, 425)]
    xs = [852, 852]
    for i, c in enumerate(T["verdict_chips"]):
        r = 0 if i < 2 else 1
        fill, col = [("#E9FCEB", DEEP), ("#FFF4E5", ORANGE), ("#EEF1F5", "#475569"), ("#EEF1F5", "#475569")][i]
        svg, w = chip(xs[r], row[r][1], c, fill, col, col, 15)
        o.append(svg)
        xs[r] += w + 10
    o.append(t(852, 473, T["verdict_sub"], 14, 400, MUTED))
    o.append(box(410, 530, 380, 140, "calc", T["calc"][0], T["calc"][1]))
    o.append(box(830, 530, 360, 135, "wave", T["voice"][0], T["voice"][1]))
    o.append(mascot_image(1095, 545, 80))

    # ---- center bottom: gateway
    o.append(panel(380, 800, 840, 415, "server", T["p2"][0], T["p2"][1], T["p2_note"]))
    o.append(box(410, 905, 380, 120, "route", T["geo"][0], T["geo"][1]))
    o.append(box(830, 905, 360, 120, "wave", T["tts"][0], T["tts"][1]))
    o.append(box(410, 1060, 780, 140, "shield", T["ask"][0], T["ask"][1], stroke=ORANGE, fill=ORANGE_BG, title_fill=INK, line_fill="#7A2E0B"))

    # ---- right top: local AI
    o.append(panel(1300, 40, 680, 600, "chip", T["p3"][0], T["p3"][1], T["p3_note"]))
    o.append(box(1330, 140, 620, 125, "wave", T["breezy"][0], T["breezy"][1]))
    o.append(box(1330, 290, 620, 135, "chip", T["gemma"][0], T["gemma"][1], stroke=BLUE))
    o.append(box(1330, 445, 620, 85, "mic", T["asr"][0], T["asr"][1], size=19))
    o.append(box(1330, 543, 620, 85, "check", T["whisper"][0], T["whisper"][1], size=19))

    # ---- right bottom: data protection
    o.append(panel(1300, 680, 680, 535, "shield", T["p6"][0], ""))
    for i, item in enumerate(T["p6_items"]):
        yy = 755 + i * 74
        o.append(f'<rect x="1330" y="{yy}" width="620" height="60" rx="12" fill="#FFFFFF" stroke="{LINE}" stroke-width="2"/>')
        o.append(icon("check", 1346, yy + 18, 24))
        o.append(t(1382, yy + 37, item, 17, 600, INK))

    # ---- bottom: offline analysis
    o.append(panel(20, 1270, 1960, 265, "cluster", T["p5"][0], T["p5"][1]))
    bw, gap, bx0 = 344, 46, 50
    for i, (title, lines) in enumerate(T["off"]):
        bx = bx0 + i * (bw + gap)
        stroke = DEEP if i == 4 else LINE
        o.append(box(bx, 1355, bw, 140, ["db", "calc", "cluster", "id", "doc"][i], title, lines, stroke=stroke))
        if i < 4:
            o.append(arrow([(bx + bw + 2, 1425), (bx + bw + gap - 4, 1425)]))

    # ================================================================ arrows
    # customer <-> channels / browser
    o.append(arrow([(150, 250), (150, 328)]))
    o.append(label(162, 295, T["a_cust"], size=14))
    o.append(arrow([(340, 470), (378, 470)]))
    o.append(label(344, 460, T["a_https"], size=12))
    o.append(arrow([(380, 112), (190, 112), (190, 127)], color=BLUE))
    o.append(label(200, 102, T["a_back"], BLUE, size=14))
    # inside browser
    o.append(arrow([(790, 212), (828, 212)]))
    o.append(arrow([(600, 280), (600, 328)]))
    o.append(arrow([(600, 480), (600, 528)]))
    o.append(arrow([(1010, 280), (1010, 328)]))
    o.append(arrow([(1010, 480), (1010, 528)]))
    # flow -> /api/ask (blue loop) and back
    o.append(arrow([(410, 400), (395, 400), (395, 1120), (408, 1120)], color=BLUE))
    o.append(label(402, 790, T["a_ask"], BLUE))
    o.append(arrow([(810, 1058), (810, 440), (792, 440)], color=BLUE))
    o.append(label(818, 790, T["a_ok"], BLUE))
    # calc -> geo, voice -> tts
    o.append(arrow([(600, 670), (600, 903)]))
    o.append(label(608, 712, T["a_geo"]))
    o.append(arrow([(1010, 665), (1010, 903)]))
    o.append(label(1018, 712, T["a_tts"]))
    # geo -> public data (left)
    o.append(arrow([(410, 960), (368, 960), (368, 815), (342, 815)]))
    o.append(arrow([(368, 945), (368, 942), (342, 942)]))
    # tts -> BreezyVoice ; ask <-> Gemma ; personas.json -> persona
    o.append(arrow([(1190, 960), (1240, 960), (1240, 200), (1328, 200)]))
    o.append(label(1236, 640, T["a_breezy"], rotate=-90, anchor="middle", size=14))
    o.append(arrow([(1190, 1130), (1262, 1130), (1262, 355), (1328, 355)], color=BLUE, both=True))
    o.append(label(1258, 860, T["a_gemma"], BLUE, rotate=-90, anchor="middle", size=14))
    o.append(arrow([(1760, 1353), (1760, 1242), (1284, 1242), (1284, 250), (1192, 250)], color=DEEP, dashed=True))
    o.append(label(1300, 1236, T["a_json"], DEEP, size=14))

    o.extend(TOP); TOP.clear()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "\n".join(o) + "</svg>")
    return svg


def main():
    for lang, stem in (("vi", "architecture"), ("zh", "architecture_zh")):
        svg = build(lang)
        open(os.path.join(HERE, stem + ".svg"), "w", encoding="utf-8").write(svg)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(HERE, stem + ".png"), output_width=W)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=os.path.join(HERE, stem + "_1600.png"), output_width=1600)
        print("ok", stem)


if __name__ == "__main__":
    sys.exit(main())
