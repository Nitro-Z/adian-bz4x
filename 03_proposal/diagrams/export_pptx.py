"""Chuyển sơ đồ kiến trúc (architecture*.svg do architecture.py tạo) thành PowerPoint có thể sửa tay.

Chạy: python export_pptx.py   → architecture.pptx (2 slide: tiếng Việt, 繁體中文)
Mỗi hộp, dòng chữ, mũi tên là một đối tượng PowerPoint riêng (không phải ảnh). Icon nhỏ được bỏ qua;
mascot được chèn dạng ảnh PNG. Font: Arial / Microsoft JhengHei / Consolas (có sẵn trên Windows, Mac Office).
Cần python-pptx.
"""
import os
import re
import xml.etree.ElementTree as ET

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

HERE = os.path.dirname(os.path.abspath(__file__))
MASCOT_PNG = os.path.join(HERE, "..", "..", "05_brand", "mascot", "adian.png")
NS = "{http://www.w3.org/2000/svg}"
W_PX, H_PX = 2000, 1560
SLIDE_W = 12192000                      # 13.333 in
EMU = SLIDE_W / W_PX                    # EMU per SVG px
SLIDE_H = int(H_PX * EMU)
PT = 13.333 * 72 / W_PX                 # pt per SVG px


def px(v):
    return Emu(int(float(v) * EMU))


def rgb(hexstr):
    h = hexstr.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def text_width(s, size):
    return sum(size if ord(c) > 0x2E80 else size * 0.58 for c in s)


def set_fonts(run, font_attr):
    mono = "Mono" in font_attr
    latin = "Consolas" if mono else "Arial"
    run.font.name = latin
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = etree.SubElement(rpr, qn(tag))
        el.set("typeface", "Microsoft JhengHei")


def add_rect(slide, el):
    x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
    if w >= W_PX - 1 and h >= H_PX - 1:   # background
        return
    rx = float(el.get("rx", 0))
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rx else MSO_SHAPE.RECTANGLE, px(x), px(y), px(w), px(h))
    if rx:
        shp.adjustments[0] = min(0.5, rx / min(w, h))
    fill = el.get("fill", "none")
    if fill == "none":
        shp.fill.background()
    else:
        shp.fill.solid(); shp.fill.fore_color.rgb = rgb(fill)
    stroke = el.get("stroke")
    if stroke and stroke != "none":
        shp.line.color.rgb = rgb(stroke); shp.line.width = Pt(float(el.get("stroke-width", 1)) * PT)
    else:
        shp.line.fill.background()
    shp.shadow.inherit = False
    shp.text_frame.text = ""


def add_text(slide, el):
    if el.get("stroke"):          # halo underlay copy: skip
        return
    s = "".join(el.itertext())
    x, y = float(el.get("x")), float(el.get("y"))
    size = float(el.get("font-size", 16))
    anchor = el.get("text-anchor", "start")
    w = text_width(s, size) * 1.08 + 8
    h = size * 1.45
    left = x if anchor == "start" else x - w / 2 if anchor == "middle" else x - w
    top = y - size * 1.08
    rot = 0
    m = re.search(r"rotate\((-?[\d.]+)", el.get("transform", ""))
    if m:
        rot = float(m.group(1))
        # PowerPoint rotates around the box centre: place the unrotated box centred on the text centre
        cx, cy = x, y - size * 0.35
        left, top = cx - w / 2, cy - h / 2
    tb = slide.shapes.add_textbox(px(left), px(top), px(w), px(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = False
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = {"start": PP_ALIGN.LEFT, "middle": PP_ALIGN.CENTER, "end": PP_ALIGN.RIGHT}[anchor]
    r = p.add_run(); r.text = s
    r.font.size = Pt(size * PT)
    r.font.bold = el.get("font-weight", "400") in ("600", "700", "800", "900")
    r.font.color.rgb = rgb(el.get("fill", "#1F2733"))
    set_fonts(r, el.get("font-family", ""))
    if rot:
        tb.rotation = rot % 360


def add_arrow(slide, el):
    nums = [float(v) for v in re.findall(r"-?[\d.]+", el.get("d", ""))]
    pts = list(zip(nums[0::2], nums[1::2]))
    if len(pts) < 2:
        return
    fb = slide.shapes.build_freeform(px(pts[0][0]), px(pts[0][1]), scale=1.0)
    fb.add_line_segments([(px(a), px(b)) for a, b in pts[1:]], close=False)
    shp = fb.convert_to_shape()
    shp.fill.background()
    color = el.get("stroke", "#3A4352")
    shp.line.color.rgb = rgb(color)
    shp.line.width = Pt(float(el.get("stroke-width", 2)) * PT)
    ln = shp.line._get_or_add_ln()
    if el.get("stroke-dasharray"):
        dash = etree.SubElement(ln, qn("a:prstDash")); dash.set("val", "dash")
    if el.get("marker-end"):
        tail = etree.SubElement(ln, qn("a:tailEnd")); tail.set("type", "triangle"); tail.set("w", "med"); tail.set("len", "med")
    if el.get("marker-start"):
        head = etree.SubElement(ln, qn("a:headEnd")); head.set("type", "triangle"); head.set("w", "med"); head.set("len", "med")
    shp.shadow.inherit = False


def add_slide(prs, svg_path):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    root = ET.parse(svg_path).getroot()
    for el in root:                    # only top-level elements; icons live inside <g> and are skipped
        tag = el.tag.replace(NS, "")
        if tag == "rect":
            add_rect(slide, el)
        elif tag == "text":
            add_text(slide, el)
        elif tag == "path" and el.get("marker-end"):
            add_arrow(slide, el)
        elif tag == "image" and os.path.exists(MASCOT_PNG):
            slide.shapes.add_picture(MASCOT_PNG, px(el.get("x")), px(el.get("y")), width=px(el.get("width")))
    return slide


def main():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(SLIDE_W), Emu(SLIDE_H)
    for stem in ("architecture", "architecture_zh"):
        add_slide(prs, os.path.join(HERE, stem + ".svg"))
    out = os.path.join(HERE, "architecture.pptx")
    prs.save(out)
    print("ok", out)


if __name__ == "__main__":
    main()
