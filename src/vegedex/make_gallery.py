#!/usr/bin/env python3
"""
Vegedex gallery builder.

Builds ONE self-contained HTML page (Vegedex.html) with two views:
  * Cards: every card in cards.json as a small tile. Click a tile to enlarge the card;
    "Open PDF" opens the matching PDF, which must sit in the same folder as the HTML.
    Wishlist cards are shown greyed out.
  * Family tree: the circular tree-of-life chart (grown in black, growing in green-grey, wishlist in grey), drawn by
    make_graph.py (needs make_graph.py and taxonomy.json next to this script).
    Click a vegetable in the tree to open its card.

Usage:
    python make_gallery.py                       # uses ./cards.json and ./cards/*.pdf
    python make_gallery.py --cards cards --out cards/Vegedex.html

Needs: pillow, and poppler's `pdftoppm` on PATH (renders the PDFs to images).
The card images and the tree are embedded in the HTML, so the page works offline;
only the "Open PDF" links need the PDFs next to it.
"""
import argparse
import base64
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image

import paths

IMG_WIDTH = 720  # px; sharp enough for the enlarged view, small enough to embed


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pdf_to_data_uri(pdf):
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-png", "-r", "150", "-singlefile", pdf, os.path.join(d, "p")], check=True)
        im = Image.open(os.path.join(d, "p.png")).convert("RGB")
    im = im.resize((IMG_WIDTH, round(im.height * IMG_WIDTH / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def family_tree(cards, here, taxonomy):
    """SVG of the family tree from make_graph.py, or '' if it can't be built."""
    sys.path.insert(0, here)
    try:
        import make_graph
        tax = json.load(open(taxonomy, encoding="utf-8"))
        return make_graph.family_tree_svg(cards, tax)
    except (ImportError, OSError) as e:
        print("WARNING: no family tree (%s); needs make_graph.py and taxonomy.json" % e)
        return ""


PAGE = r"""<title>Vegedex</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Atkinson+Hyperlegible:wght@400;700&display=swap">
<style>
/* Layout: a collector's binder. Dark felt page, cards slotted in a numbered grid; click lifts a card out.
   Second view: the family tree, mounted like a printed plate on the felt. */
:root {
  --felt: #1F3327;        /* binder page, matches the card frame */
  --felt-2: #2A4334;      /* empty sleeve / raised surface */
  --ink: #F3EFE3;         /* text on felt */
  --muted: #A9B8A6;
  --accent: #E9A23B;      /* harvest orange from the calendar bars */
  --sow: #7DB561;         /* sow green */
  --line: #3B5646;
  --scrim: rgba(10, 18, 13, .82);
  --display: "Bricolage Grotesque", "Segoe UI", system-ui, sans-serif;
  --body: "Atkinson Hyperlegible", "Segoe UI", system-ui, sans-serif;
  color-scheme: dark;
}
@media (prefers-color-scheme: light) { :root:not([data-theme="dark"]) {
  --felt: #E8EEE4; --felt-2: #D7E1D2; --ink: #1C2B21; --muted: #56685A;
  --accent: #B5501A; --sow: #3E7A2E; --line: #BFCDBB; --scrim: rgba(28, 43, 33, .78); color-scheme: light } }
:root[data-theme="light"] {
  --felt: #E8EEE4; --felt-2: #D7E1D2; --ink: #1C2B21; --muted: #56685A;
  --accent: #B5501A; --sow: #3E7A2E; --line: #BFCDBB; --scrim: rgba(28, 43, 33, .78); color-scheme: light }

* { box-sizing: border-box; }
html, body { background: var(--felt); color: var(--ink); }
body { font-family: var(--body); font-size: 15px; line-height: 1.5; margin: 0;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
.wrap { max-width: 1100px; margin: 0 auto; padding-block: 28px 56px; }

header { display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 16px 32px;
  padding-bottom: 18px; border-bottom: 1px solid var(--line); margin-bottom: 22px; }
h1 { font-family: var(--display); font-weight: 800; font-size: clamp(2.2rem, 6vw, 3.4rem); line-height: 1; margin: 0;
  letter-spacing: -.02em; text-wrap: balance; }
.tally { font-variant-numeric: tabular-nums; color: var(--muted); margin: 8px 0 0; }
.tally b { color: var(--ink); }
.meter { height: 6px; border-radius: 3px; background: var(--felt-2); overflow: hidden; margin-top: 10px; width: min(320px, 100%); }
.meter span { display: block; height: 100%; background: linear-gradient(90deg, var(--sow), var(--accent)); }

.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px; justify-content: flex-end; }
.views { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--felt-2); border: 1.5px solid var(--line); }
.views button { font: 700 .82rem/1 var(--body); cursor: pointer; color: var(--muted); background: transparent;
  border: 0; border-radius: 999px; padding: 9px 15px; }
.views button[aria-selected="true"] { background: var(--accent); color: var(--felt); }
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
.filters button { font: 700 .8rem/1 var(--body); letter-spacing: .06em; text-transform: uppercase; cursor: pointer;
  color: var(--ink); background: transparent; border: 1.5px solid var(--line); border-radius: 999px; padding: 9px 14px; }
.filters button[aria-pressed="true"] { background: var(--ink); color: var(--felt); border-color: var(--ink); }
.filters[hidden] { display: none; }
.filters button:focus-visible, .views button:focus-visible, .tile:focus-visible, dialog button:focus-visible,
dialog a:focus-visible, .tip:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 22px 18px; }
.grid[hidden] { display: none; }
.tile[hidden], .empty[hidden] { display: none; }
.tile { display: flex; flex-direction: column; gap: 8px; text-align: left; background: none; border: 0; padding: 0;
  color: inherit; font: inherit; cursor: pointer; }
.tile .sleeve { position: relative; aspect-ratio: 5 / 7; max-width: 100%; border-radius: 10px; overflow: hidden;
  background: var(--felt-2); box-shadow: 0 1px 0 var(--line), 0 6px 14px rgba(0,0,0,.25);
  transition: transform .18s ease, box-shadow .18s ease; }
.tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
.tile:hover .sleeve { transform: translateY(-4px) rotate(-.6deg); box-shadow: 0 1px 0 var(--line), 0 14px 26px rgba(0,0,0,.32); }
.tile.wish img { filter: grayscale(1) contrast(.9) brightness(1.05); opacity: .62; }
.tile.wish .sleeve::after { content: "WISHLIST"; position: absolute; left: 8px; bottom: 8px; font: 700 .62rem/1 var(--body);
  letter-spacing: .1em; padding: 5px 7px; border-radius: 4px; background: var(--felt); color: var(--ink); }
.tile .cap { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.tile .name { font-family: var(--display); font-weight: 600; font-size: 1.02rem; min-width: 0; }
.tile .no { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted); font-size: .8rem; }
.tile.wish .name, .tile.grow .name, .tile.fail .name { color: var(--muted); }
.tile.fail img { opacity: .8; }
.tile.fail .sleeve::after { content: "FAILED"; position: absolute; left: 8px; bottom: 8px; font: 700 .62rem/1 var(--body);
  letter-spacing: .1em; padding: 5px 7px; border-radius: 4px; background: #B4392E; color: #fff; }
.tile.grow img { opacity: .8; }   /* the card PDF is already greyed with a green tint */
.tile.grow .sleeve::after { content: "GROWING"; position: absolute; left: 8px; bottom: 8px; font: 700 .62rem/1 var(--body);
  letter-spacing: .1em; padding: 5px 7px; border-radius: 4px; background: var(--sow); color: var(--felt); }
.empty { color: var(--muted); padding: 40px 0; }

.tree[hidden] { display: none; }
.tree .plate { overflow-x: auto; border-radius: 22px; box-shadow: 0 1px 0 var(--line), 0 14px 34px rgba(0,0,0,.28); }
.tree svg { display: block; width: 100%; min-width: 760px; height: auto; }
.tree .tip { cursor: pointer; }
.tree .tip:hover text:first-of-type { fill: #B5501A; text-decoration: underline; }
.tree .tip:hover circle { fill: #E9A23B; }
.tree .note { color: var(--muted); margin: 12px 4px 0; font-size: .9rem; }

dialog { border: 0; padding: 0; background: transparent; color: var(--ink); max-width: 100vw; max-height: 100vh;
  width: 100%; height: 100%; }
dialog::backdrop { background: var(--scrim); backdrop-filter: blur(3px); }
.stage { height: 100%; display: grid; grid-template-rows: 1fr auto; justify-items: center; gap: 14px;
  padding: max(16px, env(safe-area-inset-top, 0px)) max(16px, env(safe-area-inset-right, 0px))
           max(16px, env(safe-area-inset-bottom, 0px)) max(16px, env(safe-area-inset-left, 0px)); }
.stage img { max-height: 100%; max-width: min(560px, 100%); min-height: 0; align-self: center; border-radius: 14px;
  box-shadow: 0 20px 50px rgba(0,0,0,.45); }
.controls { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
.controls a, .controls button { font: 700 .85rem/1 var(--body); cursor: pointer; text-decoration: none;
  padding: 11px 16px; border-radius: 999px; border: 1.5px solid #F3EFE3; color: #F3EFE3; background: transparent; }
.controls a.primary { background: #E9A23B; border-color: #E9A23B; color: #1F3327; }
@media (prefers-reduced-motion: reduce) { .tile .sleeve { transition: none; } .tile:hover .sleeve { transform: none; } }
</style>

<div class="wrap">
  <header>
    <div>
      <h1>Vegedex</h1>
      <p class="tally"><b>__GROWN__</b> grown &middot; <b>__GROWING__</b> growing &middot; <b>__FAILED__</b> failed &middot; <b>__WISH__</b> on the wishlist &middot; __TOTAL__ cards</p>
      <div class="meter" aria-hidden="true"><span style="width: __PCT__%"></span></div>
    </div>
    <div class="bar">
      <div class="filters" id="filters" role="group" aria-label="Show">
        <button id="f-all" data-f="all" aria-pressed="true">All</button>
        <button id="f-grown" data-f="grown" aria-pressed="false">Grown</button>
        <button id="f-growing" data-f="growing" aria-pressed="false">Growing</button>
        <button id="f-failed" data-f="failed" aria-pressed="false">Failed</button>
        <button id="f-wish" data-f="wishlist" aria-pressed="false">Wishlist</button>
      </div>
      <div class="views" role="tablist" aria-label="View">
        <button role="tab" data-v="cards" aria-selected="true" aria-controls="grid">Cards</button>
        <button role="tab" data-v="tree" aria-selected="false" aria-controls="tree" __TREE_DISABLED__>Family tree</button>
      </div>
    </div>
  </header>
  <main class="grid" id="grid">
__TILES__
  </main>
  <p class="empty" id="empty" hidden>Nothing here yet.</p>
  <section class="tree" id="tree" hidden aria-label="Family tree of grown, growing and wishlist vegetables">
    <div class="plate">__TREE__</div>
    <p class="note">Every vegetable on the flowering-plant family tree: grown ones in black, growing ones in green-grey, failed ones in red, wishlist ones in grey.
      The centre is their common ancestor; coloured wedges are botanical families. Click a vegetable to see its card.</p>
  </section>
</div>

<dialog id="viewer" aria-label="Card">
  <div class="stage">
    <img id="big" alt="">
    <div class="controls">
      <button id="prev" type="button">&larr; Prev</button>
      <a id="pdf" class="primary" href="#" target="_blank" rel="noopener">Open PDF</a>
      <button id="next" type="button">Next &rarr;</button>
      <button id="close" type="button">Close</button>
    </div>
  </div>
</dialog>

<script>
(function () {
  var grid = document.getElementById('grid'), dlg = document.getElementById('viewer');
  var big = document.getElementById('big'), pdf = document.getElementById('pdf');
  var tiles = Array.prototype.slice.call(grid.querySelectorAll('.tile')), cur = 0;
  function visible() { return tiles.filter(function (t) { return !t.hidden; }); }
  function show(t) {
    var img = t.querySelector('img');
    big.src = img.src; big.alt = img.alt; pdf.href = t.dataset.pdf;
    var v = visible(); cur = v.indexOf(t); if (cur < 0) { cur = tiles.indexOf(t); }
  }
  function open(t) { show(t); if (!dlg.open) dlg.showModal(); }
  tiles.forEach(function (t) { t.addEventListener('click', function () { open(t); }); });
  function step(d) { var v = visible(); if (!v.length) return; show(v[(cur + d + v.length) % v.length]); }
  document.getElementById('prev').onclick = function () { step(-1); };
  document.getElementById('next').onclick = function () { step(1); };
  document.getElementById('close').onclick = function () { dlg.close(); };
  dlg.addEventListener('click', function (e) { if (e.target === dlg || e.target.classList.contains('stage')) dlg.close(); });
  dlg.addEventListener('keydown', function (e) { if (e.key === 'ArrowLeft') step(-1); if (e.key === 'ArrowRight') step(1); });

  var btns = document.querySelectorAll('.filters button');
  function filter(f) {
    btns.forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.f === f ? 'true' : 'false'); });
    tiles.forEach(function (t) { t.hidden = !(f === 'all' || t.dataset.status === f); });
    document.getElementById('empty').hidden = visible().length > 0 || view === 'tree';
    try { localStorage.setItem('vegedex-filter', f); } catch (e) {}
  }
  btns.forEach(function (b) { b.addEventListener('click', function () { filter(b.dataset.f); }); });

  // Cards / Family tree switch
  var view = 'cards', tree = document.getElementById('tree'), filters = document.getElementById('filters');
  var tabs = document.querySelectorAll('.views button');
  function setView(v) {
    if (v === 'tree' && !tree.querySelector('svg')) v = 'cards';
    view = v;
    tabs.forEach(function (b) { b.setAttribute('aria-selected', b.dataset.v === v ? 'true' : 'false'); });
    grid.hidden = v !== 'cards'; filters.hidden = v !== 'cards'; tree.hidden = v !== 'tree';
    document.getElementById('empty').hidden = v === 'tree' || visible().length > 0;
    try { localStorage.setItem('vegedex-view', v); } catch (e) {}
  }
  tabs.forEach(function (b) { b.addEventListener('click', function () { setView(b.dataset.v); }); });

  // Click a vegetable in the tree to open its card
  Array.prototype.forEach.call(tree.querySelectorAll('.tip'), function (g) {
    g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
    function go() { var t = tiles.filter(function (x) { return x.dataset.id === g.dataset.id; })[0]; if (t) open(t); }
    g.addEventListener('click', go);
    g.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  });

  try { var saved = localStorage.getItem('vegedex-filter'); if (saved) filter(saved); } catch (e) {}
  try { var sv = localStorage.getItem('vegedex-view'); if (sv) setView(sv); } catch (e) {}
})();
</script>
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=paths.CARDS_JSON)
    ap.add_argument("--taxonomy", default=paths.TAXONOMY)
    ap.add_argument("--cards", default=None, help="folder holding NNN-slug.pdf files (default: the vault)")
    ap.add_argument("--out", default=None, help="output HTML (default: <cards>/Vegedex.html)")
    ap.add_argument("--fragment", action="store_true",
                    help="omit the <!doctype>/<head> wrapper (for publishing as a claude.ai artifact)")
    a = ap.parse_args()
    a.cards = a.cards or paths.vault()
    out = a.out or os.path.join(a.cards, "Vegedex.html")

    cards = sorted(json.load(open(a.data, encoding="utf-8"))["cards"], key=lambda c: c["id"])
    tiles = []
    for c in cards:
        fn = "%03d-%s.pdf" % (c["id"], slug(c["name"]))
        path = os.path.join(a.cards, fn)
        if not os.path.exists(path):
            raise SystemExit("missing %s - run make_cards.py first" % path)
        st = c.get("status", "grown")
        wish = st != "grown"
        alt = "%s card%s" % (c["name"], "" if st == "grown" else " (%s)" % st)
        tiles.append(
            '    <button class="tile%s" data-id="%d" data-status="%s" data-pdf="%s" aria-label="%s, number %d">'
            '<span class="sleeve"><img src="%s" alt="%s" loading="lazy"></span>'
            '<span class="cap"><span class="name">%s</span><span class="no">No. %03d</span></span></button>'
            % ({"wishlist": " wish", "growing": " grow", "failed": " fail"}.get(st, ""), c["id"], st, fn, html.escape(alt), c["id"],
               pdf_to_data_uri(path), html.escape(alt), html.escape(c["name"]), c["id"]))

    tree = family_tree(cards, here, a.taxonomy)
    grown = sum(1 for c in cards if c.get("status", "grown") == "grown")
    growing = sum(1 for c in cards if c.get("status") == "growing")
    failed = sum(1 for c in cards if c.get("status") == "failed")
    page = (PAGE.replace("__TILES__", "\n".join(tiles))
                .replace("__TREE__", tree)
                .replace("__TREE_DISABLED__", "" if tree else "disabled")
                .replace("__GROWN__", str(grown))
                .replace("__GROWING__", str(growing))
                .replace("__FAILED__", str(failed))
                .replace("__WISH__", str(len(cards) - grown - growing - failed))
                .replace("__TOTAL__", str(len(cards)))
                .replace("__PCT__", str(round(100 * grown / len(cards)) if cards else 0)))
    if not a.fragment:  # full document so it renders properly when opened straight from disk
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                + page.replace("</style>", "</style>\n</head>\n<body>", 1) + "\n</body>\n</html>\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote", out, "(%d cards%s, %.1f MB)" % (len(cards), ", family tree" if tree else "",
                                                   os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()
