#!/usr/bin/env python3
"""
Veggie Dex card generator.

Turns entries in cards.json into collectible trading-card PDFs (5 x 7 in),
one PDF per vegetable plus a combined collection PDF.

Usage:
    python make_cards.py                 # all cards in cards.json
    python make_cards.py --only 3 5      # just card ids 3 and 5
    python make_cards.py --data other.json --out outdir

Needs: reportlab, pillow, pypdf  (pip install reportlab pillow pypdf)

The collection PDF is stitched together from the per-card PDFs already in the
output folder, so copy the existing PDFs in first; only the cards you render
(or that have no PDF yet) are drawn fresh.
Uses only built-in PDF fonts, so output looks the same on any machine.

Data rules (keep these so every card stays consistent):
  * status: "grown" (photo required), "growing" (in the ground now; greyed with a green tint,
    "?" placeholder unless a photo is given), "failed" (red tint, "!" placeholder) or
    "wishlist" (greyed; placeholder if no photo). Change status only through transition.py.
  * category: Root | Fruiting | Leafy | Legume | Allium | Brassica | Herb | Other
  * anything not known -> the string "Unknown"
  * citation markers like [1] refer to the card's sources list (1-based)
"""
import argparse
import io
import json
import os
import re
from urllib.parse import urlparse

from PIL import Image, ImageOps
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

import paths

W, H = 360, 504  # 5 x 7 inches, trading-card proportions
MONTHS = "JFMAMJJASOND"

PALETTES = {
    #            panel      accent     soft
    "Root":     ("#F1D9CC", "#8B2E3F", "#E3BBA8"),
    "Fruiting": ("#F8E3B0", "#B5501A", "#EDCB82"),
    "Leafy":    ("#DCEBC6", "#3E7A2E", "#BFD99E"),
    "Legume":   ("#E2EDC0", "#5F7A1E", "#C9DA95"),
    "Allium":   ("#EADFF0", "#6B3F86", "#D3C0E0"),
    "Brassica": ("#D6E8E2", "#2E6B5E", "#B2D3C8"),
    "Herb":     ("#DDEFD9", "#2F7A4B", "#BCDDB4"),
    "Other":    ("#E6E2D8", "#5A5446", "#CFC8B8"),
}
WISHLIST = ("#E3E7EC", "#4A5A70", "#C7D0DB")
GROWING = ("#E2EBE2", "#4F7A56", "#C3D6C5")   # greyed with a green tint
FAILED = ("#F3E2DF", "#A8372C", "#E6C3BE")    # red: it didn't make it
TINTS = {"growing": (214, 236, 216), "failed": (244, 208, 202)}  # photo wash per status (default grey)
FRAME = HexColor("#22362A")
INK = HexColor("#1E1E1E")
SOW_C = HexColor("#4E8B3A")
HARV_C = HexColor("#D9822B")


def palette(card):
    if card.get("status") == "wishlist":
        return [HexColor(c) for c in WISHLIST]
    if card.get("status") == "growing":
        return [HexColor(c) for c in GROWING]
    if card.get("status") == "failed":
        return [HexColor(c) for c in FAILED]
    return [HexColor(c) for c in PALETTES.get(card.get("category", "Other"), PALETTES["Other"])]


def cropped_photo(path, box_w, box_h, focus=(0.5, 0.5), zoom=1.0, grey=False, tint=(235, 238, 242)):
    """Centre-crop the photo to the box aspect around `focus`, honouring EXIF rotation.
    grey=True gives the faded black-and-white look used for wishlist cards; `tint` sets the wash
    (green for growing cards)."""
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if grey:
        g = ImageOps.grayscale(im)
        im = Image.blend(Image.merge("RGB", (g, g, g)), Image.new("RGB", im.size, tint), 0.35)
    iw, ih = im.size
    target = box_w / box_h
    if iw / ih > target:
        ch, cw = ih, ih * target
    else:
        cw, ch = iw, iw / target
    cw, ch = cw / zoom, ch / zoom
    cx, cy = focus[0] * iw, focus[1] * ih
    left = min(max(cx - cw / 2, 0), iw - cw)
    top = min(max(cy - ch / 2, 0), ih - ch)
    im = im.crop((int(left), int(top), int(left + cw), int(top + ch)))
    im.thumbnail((int(box_w * 4), int(box_h * 4)))  # ~288 dpi
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    buf.seek(0)
    return ImageReader(buf)


def esc(t):
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\[(\d+)\]", r"<super><font size='-2'>[\1]</font></super>", t)


def rrect(c, x, y, w, h, r, fill=None, stroke=None, lw=1):
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(lw)
    c.roundRect(x, y, w, h, r, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)


def pill(c, x, y, text, bg, fg=white, size=7, right=False):
    c.setFont("Helvetica-Bold", size)
    tw = c.stringWidth(text, "Helvetica-Bold", size)
    w, h = tw + 12, size + 6
    if right:
        x -= w
    rrect(c, x, y, w, h, h / 2, fill=bg)
    c.setFillColor(fg)
    c.drawString(x + 6, y + 3.6, text)
    return w


def section_height(blocks, width, size):
    total = 0
    for kind, content in blocks:
        if kind == "head":
            total += size + 6
        else:
            st = ParagraphStyle("b", fontName="Helvetica", fontSize=size, leading=size * 1.25,
                                leftIndent=content[1], alignment=TA_LEFT)
            p = Paragraph(content[0], st)
            _, h = p.wrap(width, 1000)
            total += h + 2
    return total


def draw_card(c, card, base_dir):
    panel, accent, soft = palette(card)
    status = card.get("status", "grown")
    wish = status == "wishlist"
    growing = status == "growing"
    failed = status == "failed"
    ghost = wish or growing or failed   # not harvested: tinted photo / "?" or "!" placeholder
    not_yet = {"growing": "GROWING NOW", "failed": "FAILED"}.get(status, "NOT YET GROWN")
    glyph = "!" if failed else "?"

    # Outer frame + inner panel
    c.setFillColor(FRAME)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    rrect(c, 9, 9, W - 18, H - 18, 12, fill=panel)
    rrect(c, 9, 9, W - 18, H - 18, 12, stroke=accent, lw=1.5)

    # Header
    top = H - 20
    pill(c, 20, top - 13, {"wishlist": "WISHLIST", "growing": "GROWING", "failed": "FAILED"}.get(status, "GROWN"), accent, size=6.5)
    pill(c, W - 20, top - 13, card.get("category", "Other").upper(), FRAME, size=6.5, right=True)
    c.setFillColor(INK)
    name = card["name"]
    size = 24
    while c.stringWidth(name, "Helvetica-Bold", size) > W - 60 and size > 14:
        size -= 1
    c.setFont("Helvetica-Bold", size)
    c.drawString(20, top - 40, name)
    # Latin name (italic, as botanical names are written) + variant on one line
    latin = card.get("latin", "Unknown")
    m = re.search(r"\s*\[(\d+)\]\s*$", latin)
    latin_txt, latin_ref = (latin[:m.start()], "[%s]" % m.group(1)) if m else (latin, "")
    variant = "Variant: " + card.get("variant", "Unknown")
    sep = "   ·   "
    fs = 9
    while fs > 6.5 and (c.stringWidth(latin_txt, "Helvetica-Oblique", fs) + c.stringWidth(latin_ref, "Helvetica", fs - 3)
                        + c.stringWidth(sep + variant, "Helvetica", fs)) > W - 42:
        fs -= 0.25
    x, y = 21, top - 54
    c.setFillColor(accent)
    c.setFont("Helvetica-Oblique" if latin_txt != "Unknown" else "Helvetica", fs)
    c.drawString(x, y, latin_txt)
    x += c.stringWidth(latin_txt, "Helvetica-Oblique" if latin_txt != "Unknown" else "Helvetica", fs)
    if latin_ref:
        c.setFont("Helvetica", fs - 3)
        c.drawString(x + 0.5, y + 3, latin_ref)
        x += c.stringWidth(latin_ref, "Helvetica", fs - 3) + 0.5
    c.setFillColor(INK)
    c.setFont("Helvetica", fs)
    c.drawString(x, y, sep + variant)

    # Photo window
    px, pw = 20, W - 40
    ph = 176
    py = top - 62 - ph
    rrect(c, px - 3, py - 3, pw + 6, ph + 6, 6, fill=accent)
    photo_path = os.path.join(base_dir, card["photo"]) if card.get("photo") else None
    if photo_path and os.path.exists(photo_path):
        img = cropped_photo(photo_path, pw, ph, card.get("photo_focus", (0.5, 0.5)),
                            card.get("photo_zoom", 1.0), grey=ghost,
                            tint=TINTS.get(status, (235, 238, 242)))
        c.saveState()
        p = c.beginPath()
        p.roundRect(px, py, pw, ph, 4)
        c.clipPath(p, stroke=0, fill=0)
        c.drawImage(img, px, py, pw, ph)
        c.restoreState()
        if ghost:  # "not yet grown" / "growing now" band across the bottom of the greyed photo
            c.setFillColor(accent)
            c.setFillAlpha(0.85)
            c.rect(px, py + 10, pw, 16, stroke=0, fill=1)
            c.setFillAlpha(1)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(W / 2, py + 15, not_yet)
    else:
        rrect(c, px, py, pw, ph, 4, fill=soft)
        c.setFillColor(accent)
        c.setFont("Helvetica-Bold", 64)
        c.drawCentredString(W / 2, py + ph / 2 - 22, glyph)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(W / 2, py + 18, not_yet)

    # Info strip under photo
    sy = py - 17
    rrect(c, px, sy, pw, 12, 6, fill=soft)
    c.setFillColor(INK)
    c.setFont("Helvetica-Oblique", 7)
    left = "No. %03d" % card["id"]
    if wish:
        mid = "Wishlist" + (" since " + card["added"] if card.get("added") else "")
    elif growing:
        mid = "Growing" + (" since " + card["planted"] if card.get("planted") else "")
    elif failed:
        mid = "Failed" + (" " + card["failed"] if card.get("failed") else "")
    else:
        mid = "Harvested " + card.get("harvested", "Unknown")
    c.drawString(px + 7, sy + 3.3, left)
    c.drawCentredString(W / 2, sy + 3.3, mid)
    family = re.sub(r"\s*\[\d+\]\s*$", "", card.get("family", "Unknown"))
    c.drawRightString(px + pw - 7, sy + 3.3, "Family: " + family)

    # Growing calendar
    cy = sy - 30
    lab_w = 40
    cell = (pw - lab_w) / 12
    c.setFont("Helvetica-Bold", 6.5)
    c.setFillColor(INK)
    for i, m in enumerate(MONTHS):
        c.drawCentredString(px + lab_w + cell * i + cell / 2, cy + 21, m)
    for row, (label, months, col) in enumerate((("SOW", card.get("sow_months", []), SOW_C),
                                                ("HARVEST", card.get("harvest_months", []), HARV_C))):
        ry = cy + 10 - row * 10
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(col)
        c.drawString(px, ry + 1.5, label)
        for i in range(12):
            filled = (i + 1) in months
            rrect(c, px + lab_w + cell * i + 0.8, ry, cell - 1.6, 8, 2,
                  fill=col if filled else white)
    if not card.get("sow_months") and not card.get("harvest_months"):
        c.setFont("Helvetica-Oblique", 6.5)
        c.setFillColor(INK)
        c.drawCentredString(px + lab_w + (pw - lab_w) / 2, cy + 6, "Calendar: Unknown")

    # Text body: auto-shrinks to fit the space above the footer
    body_top = cy - 6
    body_bottom = 48
    instr = card.get("special_instructions") or ["Unknown"]
    if isinstance(instr, str):
        instr = [instr]
    recipes = card.get("recipes") or ["Unknown"]
    blocks = [
        ("head", "PLANTING WINDOW"), ("text", (esc(card.get("planting_window", "Unknown")), 0)),
        ("head", "HARVEST WINDOW"), ("text", (esc(card.get("harvest_window", "Unknown")), 0)),
        ("head", "SPECIAL INSTRUCTIONS"),
        *[("text", ("&bull;&nbsp;" + esc(s), 7)) for s in instr],
        ("head", "GOOD RECIPES"), ("text", (esc("  ·  ".join(recipes)), 0)),
    ]
    size = 8.2
    while size > 5.6 and section_height(blocks, pw, size) > body_top - body_bottom:
        size -= 0.2
    y = body_top
    for kind, content in blocks:
        if kind == "head":
            y -= size + 2
            c.setFillColor(accent)
            c.setFont("Helvetica-Bold", size - 0.6)
            c.drawString(px, y, content)
            c.setStrokeColor(soft)
            c.setLineWidth(0.8)
            c.line(px + c.stringWidth(content, "Helvetica-Bold", size - 0.6) + 5, y + 2.5, px + pw, y + 2.5)
            y -= 4
        else:
            st = ParagraphStyle("b", fontName="Helvetica", fontSize=size, leading=size * 1.25,
                                leftIndent=content[1], firstLineIndent=-content[1] if content[1] else 0,
                                textColor=INK)
            p = Paragraph(content[0], st)
            _, h = p.wrap(pw, 1000)
            p.drawOn(c, px, y - h)
            y -= h + 2

    # Footer: sources
    srcs = card.get("sources") or []
    rrect(c, 15, 15, W - 30, 30, 6, fill=soft)
    st = ParagraphStyle("s", fontName="Helvetica", fontSize=5.2, leading=6.2, textColor=INK)
    parts = []
    for i, u in enumerate(srcs, 1):
        short = re.sub(r"^www\.", "", urlparse(u).netloc) + urlparse(u).path.rstrip("/")
        if len(short) > 62:
            short = short[:60] + "…"
        parts.append("<b>[%d]</b> <a href='%s'>%s</a>" % (i, u, esc(short)))
    text = "<b>Sources:</b> " + ("&nbsp;&nbsp; ".join(parts) if parts else "Unknown")
    if card.get("photo_credit"):
        text += "&nbsp;&nbsp; <b>Image:</b> " + esc(card["photo_credit"])
    p = Paragraph(text, st)
    _, h = p.wrap(W - 44, 30)
    p.drawOn(c, 22, 15 + (30 - h) / 2)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=paths.CARDS_JSON)
    ap.add_argument("--out", default=None, help="folder for the card PDFs (default: the vault)")
    ap.add_argument("--only", type=int, nargs="*")
    ap.add_argument("--no-collection", action="store_true")
    a = ap.parse_args()
    a.out = a.out or paths.vault()

    base = os.path.dirname(os.path.abspath(a.data))
    cards = json.load(open(a.data))["cards"]
    cards.sort(key=lambda x: x["id"])
    os.makedirs(a.out, exist_ok=True)
    chosen = [x for x in cards if not a.only or x["id"] in a.only]

    def pdf_path(card):
        slug = re.sub(r"[^a-z0-9]+", "-", card["name"].lower()).strip("-")
        return os.path.join(a.out, "%03d-%s.pdf" % (card["id"], slug))

    def photo_missing(card):
        return bool(card.get("photo")) and not os.path.exists(os.path.join(base, card["photo"]))

    for card in chosen:
        fn = pdf_path(card)
        if photo_missing(card):
            print("WARNING: photo %s not found for card %d; it will show the '?' placeholder"
                  % (card["photo"], card["id"]))
        c = canvas.Canvas(fn, pagesize=(W, H))
        c.setTitle("%s - Veggie Dex card" % card["name"])
        draw_card(c, card, base)
        c.save()
        print("wrote", fn)

    if not a.no_collection:
        # Each page is the card's own PDF, so photos that only exist in an earlier
        # chat are kept. A card with no PDF yet is drawn fresh.
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        for card in cards:
            fn = pdf_path(card)
            if not os.path.exists(fn):
                c = canvas.Canvas(fn, pagesize=(W, H))
                c.setTitle("%s - Veggie Dex card" % card["name"])
                draw_card(c, card, base)
                c.save()
                print("wrote", fn)
            writer.add_page(PdfReader(fn).pages[0])
        writer.add_metadata({"/Title": "Veggie Dex - full collection"})
        out = os.path.join(a.out, "veggie-dex-collection.pdf")
        with open(out, "wb") as f:
            writer.write(f)
        print("wrote", out, "(%d cards)" % len(cards))


if __name__ == "__main__":
    main()
