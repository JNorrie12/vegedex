#!/usr/bin/env python3
"""
Vegedex family tree for Obsidian.

Turns every GROWN card in cards.json into a linked set of Obsidian notes, so the
graph view shows the vegetables as a botanical family tree (APG IV):

    Vegedex Family Tree > Angiosperms > clades > order > family > genus > species > vegetable

The notes cover grown cards only. The circular chart (Vegedex Family Tree.svg, also shown
in the gallery) includes wishlist cards too, drawn in grey: a branch turns black as soon as
anything on it is grown, so upgrading a card (wishlist -> grown) darkens its path.

Usage:
    python make_graph.py                       # ./cards.json, ./taxonomy.json -> ./graph
    python make_graph.py --out "graph"         # point --out at a copy of the vault's
                                               # Vegedex/Family Tree folder

Output (all notes carry `vegedex_graph: generated`, so they can be recognised later):
    <out>/Vegedex Family Tree.md     index: tree diagram + list of grown veg
    <out>/Vegedex Family Tree.svg    the circular chart, grown in black + wishlist in grey (top of the index)
    <out>/Taxa/<name>.md             one note per clade, order, family, genus, species
    <out>/Grown/<Vegetable>.md       one note per grown card, embedding its card PDF

Every run rewrites the whole set from cards.json, so the tree always matches the data.
A note's `created` date is kept if the note already exists in --out. Generated notes
that are no longer needed (e.g. a card was renamed) are listed as STALE, not deleted.
Each note links only to its parent and its children, so the graph is a clean tree;
the index links only to the top of the tree (its by-family list is plain text).

Standard library only.
"""
import argparse
import datetime
import json
import math
import os
import re
from xml.sax.saxutils import escape

import paths

ROOT = "Vegedex Family Tree"
MARK = "vegedex_graph: generated"
NO_SPECIES = "Unknown"


def clean(s):
    s = re.sub(r"\s*\[\d+\]", "", s or "").strip()
    return "" if s.lower().startswith("unknown") else s


def cite_url(card, field):
    m = re.search(r"\[(\d+)\]", card.get(field, ""))
    srcs = card.get("sources") or []
    if m and 0 < int(m.group(1)) <= len(srcs):
        return srcs[int(m.group(1)) - 1]
    return None


def species_of(latin):
    words = re.sub(r"\(.*?\)", "", latin).split()
    if len(words) >= 3 and words[1] in ("×", "x"):
        return " ".join(words[:3])
    return " ".join(words[:2]) if len(words) >= 2 else ""


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def safe_file(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "-", name).strip()


def veg_note_name(card):
    v = clean(card.get("variant"))
    return "%s (%s)" % (card["name"], v) if v else card["name"]


def read_created(path):
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(2000)
        m = re.search(r"^created:\s*(\S+)", head, re.M)
        return m.group(1) if m else None
    except OSError:
        return None


class Node:
    def __init__(self, name, rank, parent=None):
        self.name, self.rank, self.parent = name, rank, parent
        self.children = []
        self.card = None


def build_tree(cards, tax):
    nodes = {ROOT: Node(ROOT, "root")}
    warnings = []

    def get(name, rank, parent):
        if name in nodes:
            n = nodes[name]
            if n.rank != rank or n.parent is not parent:
                raise SystemExit("Name clash in the tree: '%s' used as %s under %s and as %s under %s"
                                 % (name, n.rank, n.parent.name if n.parent else "-", rank, parent.name))
            return n
        n = Node(name, rank, parent)
        parent.children.append(n)
        nodes[name] = n
        return n

    for c in cards:
        fam = clean(c.get("family"))
        latin = clean(c.get("latin"))
        order = tax["families"].get(fam) if fam else None
        node = nodes[ROOT]
        if order:
            for clade in tax["orders"][order]:
                node = get(clade, "clade", node)
            node = get(order, "order", node)
        elif fam:
            warnings.append("family %s (card %d) is not in taxonomy.json: add its APG IV order"
                            % (fam, c["id"]))
            node = get("Unknown order", "order", node)
        node = get(fam or "Unknown family", "family", node)
        sp = species_of(latin) if latin else ""
        if sp:
            node = get(sp.split()[0], "genus", node)
            node = get(sp, "species", node)
        name = veg_note_name(c)
        if name in nodes:
            name = "%s No. %03d" % (name, c["id"])
        leaf = get(name, "vegetable", node)
        leaf.card = c
    return nodes, warnings


def sort_children(n):
    n.children.sort(key=lambda x: (x.rank == "vegetable", x.name.lower()))
    for ch in n.children:
        sort_children(ch)


def leaves(n):
    if n.rank == "vegetable":
        return [n]
    out = []
    for ch in n.children:
        out += leaves(ch)
    return out


def lineage(n):
    path = []
    while n.parent is not None and n.parent.rank != "root":
        n = n.parent
        path.append(n.name)
    return " › ".join(reversed(path))


def frontmatter(created, rank, extra=()):
    lines = ["---", "created: %s" % created, "tags: [vegedex, vegedex/rank/%s]" % rank,
             "rank: %s" % rank] + list(extra) + ["source: claude", MARK, "---", ""]
    return "\n".join(lines)


def link(n):
    return "[[%s]]" % n.name


def taxon_note(n, created):
    grown = leaves(n)
    rank_label = n.rank.capitalize()
    L = [frontmatter(created, n.rank), "# %s" % n.name, "",
         "*%s* · part of %s" % (rank_label, link(n.parent)), ""]
    if lineage(n):
        L += ["Lineage: %s › %s" % (lineage(n), n.name), ""]
    L += ["Grown so far: %d" % len(grown), "", "## Contains", ""]
    for ch in n.children:
        if ch.rank == "vegetable":
            L.append("- %s · card No. %03d" % (link(ch), ch.card["id"]))
        else:
            k = len(leaves(ch))
            L.append("- %s (%s, %d grown)" % (link(ch), ch.rank, k))
    return "\n".join(L) + "\n"


def veg_note(n, created):
    c = n.card
    pdf = "%03d-%s.pdf" % (c["id"], slug(c["name"]))
    latin = clean(c.get("latin")) or "Unknown"
    fam = clean(c.get("family")) or "Unknown"
    extra = ["vegedex_id: %d" % c["id"], 'latin: "%s"' % latin, "family: %s" % fam,
             "category: %s" % c.get("category", "Other"), 'harvested: "%s"' % c.get("harvested", "Unknown")]
    L = [frontmatter(created, "vegetable", extra), "# %s" % n.name, "",
         "*%s* · Variant: %s · Card No. %03d · Harvested %s" % (
             latin, c.get("variant", "Unknown"), c["id"], c.get("harvested", "Unknown")), "",
         "Part of %s" % link(n.parent), "",
         "Lineage: %s" % lineage(n), ""]
    src = cite_url(c, "latin") or cite_url(c, "family")
    if src:
        L += ["Latin name and family: [RHS](%s)" % src, ""]
    L += ["## Card", "", "![[%s#height=640]]" % pdf, ""]
    return "\n".join(L) + "\n"


def mermaid(nodes):
    ids, L = {}, ["```mermaid", "flowchart LR"]
    order = []

    def walk(n):
        order.append(n)
        for ch in n.children:
            walk(ch)
    walk(nodes[ROOT])
    for i, n in enumerate(order):
        ids[n.name] = "n%d" % i
        shape = '(["%s"])' if n.rank == "vegetable" else '["%s"]'
        L.append("  %s%s" % (ids[n.name], shape % n.name.replace('"', "'")))
    for n in order:
        for ch in n.children:
            L.append("  %s --> %s" % (ids[n.name], ids[ch.name]))
    L.append("  class %s internal-link;" % ",".join(ids[n.name] for n in order))
    L.append("```")
    return "\n".join(L)


def root_note(nodes, tax, created):
    root = nodes[ROOT]
    grown = leaves(root)
    fams = sorted((n for n in nodes.values() if n.rank == "family"), key=lambda x: x.name)
    L = ["---", "created: %s" % created, "tags: [vegedex, vegedex/rank/root]", "rank: root",
         "source: claude", MARK, "---", "",
         "# %s" % ROOT, "",
         "Every vegetable grown on the allotment, placed on the flowering-plant family tree. "
         "%d grown, from %d botanical families. Wishlist vegetables are on the chart in grey and get their own note once grown." % (
             len(grown), len(fams)), "",
         "![[%s.svg]]" % ROOT, "",
         "Starts at: %s" % ", ".join(link(ch) for ch in root.children), "",
         "## By family", ""]
    for f in fams:
        # plain text, not links: links here would short-circuit the tree in the graph view
        L.append("- %s: %s" % (f.name, ", ".join(v.name for v in sorted(leaves(f), key=lambda x: x.name))))
    L += ["", "## Viewing it as a graph", "",
          "- Global graph: filter with `path:\"Vegedex/Family Tree\"`.",
          "- Colour groups by rank: `tag:#vegedex/rank/family`, `tag:#vegedex/rank/order`, "
          "`tag:#vegedex/rank/vegetable` and so on.",
          "- Or open the local graph on this note and set depth to 8.", "",

          "Families come from each card (RHS). Orders and clades follow APG IV: "
          + ", ".join("[%d](%s)" % (i, u) for i, u in enumerate(tax.get("sources", []), 1)) + ".", "",
          "Generated by `make_graph.py` from `cards.json`. Don't edit by hand: changes are overwritten.", ""]
    return "\n".join(L)


# ---------- Circular tree (SVG): the picture of the family tree ----------
# Half-circle fan like a classic tree-of-life chart; switches to a full circle past HALF_MAX
# vegetables so labels never crowd. Right-angled branches, outer bands for the big groups
# (Superrosids, Superasterids, Monocots...), a coloured wedge per family, tips angled outward.
HALF_MAX = 30

RING = {"root": 0, "order": 6, "family": 7, "genus": 8, "species": 9, "vegetable": 10}
BANDS = {  # big outer groups, like Bacteria / Archaea / Eukaryotes in the reference
    "Superrosids": "#CFE6F5", "Superasterids": "#F6D3E4", "Monocots": "#F7EDB8",
    "Magnoliids": "#E3DDF3", "Other": "#E6E2D8"}
FAMILY_TINTS = ["#BFE3C0", "#F5C9A6", "#C9D7F2", "#F2E29B", "#E1C4EA", "#B9E2DC", "#F1B9B9", "#D6E5A8"]
WISH_INK, WISH_LINE = "#9AA19B", "#B9BEB9"   # wishlist: grey instead of black
GROW_INK, GROW_LINE = "#6F9A75", "#9FC3A4"   # growing: grey with a green tint
FAIL_INK, FAIL_LINE = "#B4574C", "#DDA59E"   # failed: red
PAPER, INK, LINE, MUTED = "#FBF8F1", "#1E2A22", "#4F5B52", "#7A857C"
SKIP_LABEL = {"Angiosperms", "Eudicots"}  # true of every vegetable, so not worth a label
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"


def band_of(n):
    """The node under Eudicots (Superrosids/Superasterids...), or Monocots/Magnoliids."""
    chain = []
    while n is not None:
        chain.append(n.name)
        n = n.parent
    chain.reverse()  # root, Angiosperms, Eudicots, Superxxx, ...
    if len(chain) > 3 and chain[2] == "Eudicots":
        return chain[3]
    if len(chain) > 2 and chain[2] in ("Monocots", "Magnoliids"):
        return chain[2]
    return "Other"


def tree_svg(nodes, root_name, leaves, mode="auto"):
    root = nodes[root_name]
    tips = leaves(root)
    n = max(1, len(tips))
    if mode == "auto":
        mode = "half" if n <= HALF_MAX else "full"
    if mode == "half":
        start, sweep = math.radians(180), math.radians(180)   # left -> over the top -> right
    else:
        start, sweep = math.radians(90), math.radians(330)    # 12 o'clock, clockwise
    pad = sweep / n / 2
    gap = max(52.0, (n * 34) / sweep / 10)                     # ring spacing grows with tips
    r_out = 10 * gap
    label_room = max(150, 24 + 11 * max(len(veg_note_name(t.card)) for t in tips))  # room for the longest name
    r_band = r_out + label_room + 44

    ang, ring, k = {}, {}, [0]

    def place(x, d):
        ring[x.name] = RING.get(x.rank, d)
        for ch in x.children:
            place(ch, d + 1)
        if x.children:
            a = [ang[c.name] for c in x.children]
            ang[x.name] = (min(a) + max(a)) / 2
        else:
            ang[x.name] = start - (pad + k[0] * (sweep - 2 * pad) / max(1, n - 1)) if n > 1 else start - sweep / 2
            k[0] += 1
    place(root, 0)

    # a node is "grown" if anything under it has been grown; wishlist-only branches are drawn grey
    grown = {}

    def mark(x):
        if x.rank == "vegetable":
            grown[x.name] = x.card.get("status", "grown") == "grown"
        else:
            grown[x.name] = any([mark(c) for c in x.children])
        return grown[x.name]
    mark(root)
    n_grown = sum(1 for t in tips if grown[t.name])
    n_growing = sum(1 for t in tips if t.card.get("status") == "growing")
    n_failed = sum(1 for t in tips if t.card.get("status") == "failed")

    size = r_band + 70
    if mode == "half":
        W, H = 2 * size, size + 60
        cx, cy = size, size
    else:
        W = H = 2 * size
        cx = cy = size

    def P(r, a):
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def R(x):
        return ring[x.name] * gap

    def arc(r, a1, a2):  # a1 > a2 in math angle = clockwise on screen
        x1, y1 = P(r, a1)
        x2, y2 = P(r, a2)
        large = 1 if (a1 - a2) > math.pi else 0
        return "M%.1f %.1f A%.1f %.1f 0 %d 1 %.1f %.1f" % (x1, y1, r, r, large, x2, y2)

    def wedge(r1, r2, a1, a2):
        x1, y1 = P(r2, a1)
        x2, y2 = P(r2, a2)
        x3, y3 = P(r1, a2)
        x4, y4 = P(r1, a1)
        large = 1 if (a1 - a2) > math.pi else 0
        return ("M%.1f %.1f A%.1f %.1f 0 %d 1 %.1f %.1f L%.1f %.1f A%.1f %.1f 0 %d 0 %.1f %.1f Z"
                % (x1, y1, r2, r2, large, x2, y2, x3, y3, r1, r1, large, x4, y4))

    half = (sweep - 2 * pad) / max(1, n - 1) / 2 if n > 1 else sweep / 2
    out = ['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 %d %d" width="%d" height="%d" '
           'font-family="%s">' % (W, H, W, H, FONT.replace('"', "'")),
           '<rect x="0" y="0" width="%d" height="%d" rx="28" fill="%s"/>' % (W, H, PAPER)]
    defs = []

    # 1. big bands
    bands = {}
    for t in tips:
        bands.setdefault(band_of(t), []).append(ang[t.name])
    for i, (b, a) in enumerate(sorted(bands.items(), key=lambda kv: -max(kv[1]))):
        a1, a2 = max(a) + half, min(a) - half
        out.append('<path d="%s" fill="%s"/>' % (wedge(gap * 2.5, r_band, a1, a2), BANDS.get(b, BANDS["Other"])))
        mid = (a1 + a2) / 2
        rr = r_band - 22
        bottom = math.sin(mid) < -0.2
        pid = "band%d" % i
        defs.append('<path id="%s" d="%s" fill="none"/>' % (
            pid, arc(rr, a1, a2) if not bottom else
            "M%.1f %.1f A%.1f %.1f 0 %d 0 %.1f %.1f" % (*P(rr + 16, a2), rr + 16, rr + 16,
                                                       1 if a1 - a2 > math.pi else 0, *P(rr + 16, a1))))
        out.append('<text font-size="30" font-weight="700" fill="%s" fill-opacity="0.55" letter-spacing="1">'
                   '<textPath xlink:href="#%s" href="#%s" startOffset="50%%" text-anchor="middle">%s</textPath></text>'
                   % (INK, pid, pid, escape(b)))

    # 2. family wedges
    fams = sorted((x for x in nodes.values() if x.rank == "family"), key=lambda x: -ang[x.name])
    for i, f in enumerate(fams):
        a = [ang[t.name] for t in leaves(f)]
        a1, a2 = max(a) + half * 0.92, min(a) - half * 0.92
        out.append('<path d="%s" fill="%s" fill-opacity="%s"/>' % (
            wedge(R(f) - gap * 0.45, r_out + label_room, a1, a2),
            FAMILY_TINTS[i % len(FAMILY_TINTS)] if grown[f.name] else "#E4E6E2", "0.85" if grown[f.name] else "0.9"))
        mid = (a1 + a2) / 2
        rr = r_out + label_room - 14
        bottom = math.sin(mid) < -0.2
        pid = "fam%d" % i
        if bottom:
            d = "M%.1f %.1f A%.1f %.1f 0 0 0 %.1f %.1f" % (*P(rr + 10, a2), rr + 10, rr + 10, *P(rr + 10, a1))
        else:
            d = arc(rr, a1, a2)
        defs.append('<path id="%s" d="%s" fill="none"/>' % (pid, d))
        fs = max(8.0, min(15.0, rr * (a1 - a2) * 0.85 / (0.62 * len(f.name))))  # shrink to fit the wedge
        out.append('<text font-size="%.1f" font-weight="700" fill="%s" fill-opacity="0.75">'
                   '<textPath xlink:href="#%s" href="#%s" startOffset="50%%" text-anchor="middle">%s</textPath></text>'
                   % (fs, INK if grown[f.name] else WISH_INK, pid, pid, escape(f.name)))

    # 3. branches: radial segment from parent's ring to child, arc at parent's ring
    for want in (False, True):
        for x in nodes.values():
            rp = R(x)
            for c in x.children:
                if grown[c.name] != want:
                    continue
                col = LINE if want else WISH_LINE
                a0, ac = ang[x.name], ang[c.name]
                if abs(a0 - ac) > 1e-6:
                    out.append('<path d="%s" fill="none" stroke="%s" stroke-width="2.2"/>'
                               % (arc(rp, max(a0, ac), min(a0, ac)), col))
                x1, y1 = P(rp, ac)
                x2, y2 = P(R(c), ac)
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2.2"/>'
                           % (x1, y1, x2, y2, col))

    # 4. small internal-node labels (clades, orders, genera) and dots
    for x in nodes.values():
        if x.rank in ("root", "vegetable"):
            continue
        px, py = P(R(x), ang[x.name])
        out.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="%s"/>' % (px, py, LINE if grown[x.name] else WISH_LINE))
        if x.rank in ("clade", "order", "genus") and x.name not in SKIP_LABEL and x.name not in BANDS:
            deg = -math.degrees(ang[x.name])
            flip = math.cos(ang[x.name]) < -0.01
            rot = deg + 180 if flip else deg
            out.append('<text x="%.1f" y="%.1f" font-size="11" fill="%s" font-style="%s" '
                       'transform="rotate(%.1f %.1f %.1f)" text-anchor="%s" dy="-5">%s</text>'
                       % (px, py, MUTED if grown[x.name] else WISH_LINE, "italic" if x.rank == "genus" else "normal",
                          rot, px, py, "end" if flip else "start", escape(x.name)))

    # 5. tips: dot, name and species, written outward
    for t in tips:
        a = ang[t.name]
        px, py = P(r_out, a)
        # each tip is a group tagged with its card number, so the gallery can open the card on click
        g = grown[t.name]
        st = t.card.get("status", "grown")
        ink, sub, ln = (INK, MUTED, LINE) if g else {
            "growing": (GROW_INK, GROW_LINE, GROW_LINE),
            "failed": (FAIL_INK, FAIL_LINE, FAIL_LINE)}.get(st, (WISH_INK, WISH_LINE, WISH_LINE))
        out.append('<g class="tip%s" data-id="%d"><title>%s · card No. %03d%s</title>'
                   % ("" if g else {"growing": " growing", "failed": " failed"}.get(st, " wish"), t.card["id"],
                      escape(veg_note_name(t.card)), t.card["id"],
                      "" if g else {"growing": " · growing now", "failed": " · failed"}.get(st, " · wishlist")))
        out.append('<circle cx="%.1f" cy="%.1f" r="6" fill="%s" stroke="%s" stroke-width="2"%s/>'
                   % (px, py, PAPER, ln, "" if g else ' stroke-dasharray="3 2.4"'))
        lx, ly = P(r_out + 14, a)
        deg = -math.degrees(a)
        flip = math.cos(a) < -0.01
        rot = deg + 180 if flip else deg
        anchor = "end" if flip else "start"
        sp = t.parent.name if t.parent and t.parent.rank == "species" else ""
        out.append('<g transform="rotate(%.1f %.1f %.1f)">'
                   '<text x="%.1f" y="%.1f" font-size="19" font-weight="700" fill="%s" text-anchor="%s" dy="1">%s</text>'
                   '<text x="%.1f" y="%.1f" font-size="12" font-style="italic" fill="%s" text-anchor="%s" dy="17">%s</text></g>'
                   % (rot, lx, ly, lx, ly, ink, anchor, escape(veg_note_name(t.card)), lx, ly, sub, anchor, escape(sp)))
        out.append('</g>')

    # 6. centre
    out.append('<circle cx="%.1f" cy="%.1f" r="9" fill="%s"/>' % (cx, cy, INK))
    if mode == "half":
        out.append('<text x="%.1f" y="%.1f" font-size="14" font-weight="700" fill="%s" text-anchor="middle">'
                   'Common ancestor</text>' % (cx, cy + 32, INK))
    out.append('<text x="36" y="56" font-size="34" font-weight="800" fill="%s">Vegedex family tree</text>' % INK)
    out.append('<text x="38" y="84" font-size="15" fill="%s">%d grown · %d growing (green-grey) · %d failed (red) · %d on the wishlist (grey) · '
               'centre = common ancestor of all flowering plants · coloured wedges = botanical families</text>'
               % (MUTED, n_grown, n_growing, n_failed, n - n_grown - n_growing - n_failed))
    out.insert(2, "<defs>%s</defs>" % "".join(defs))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def family_tree_svg(cards, tax):
    """The circular family-tree chart: grown cards in black, wishlist cards in grey."""
    cards = sorted(cards, key=lambda x: x["id"])
    if not cards:
        return ""
    nodes, _ = build_tree(cards, tax)
    sort_children(nodes[ROOT])
    return tree_svg(nodes, ROOT, leaves)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=paths.CARDS_JSON)
    ap.add_argument("--taxonomy", default=paths.TAXONOMY)
    ap.add_argument("--out", default=None, help='default: "<vault>/Family Tree"')
    a = ap.parse_args()
    a.out = a.out or os.path.join(paths.vault(), "Family Tree")

    cards = sorted(json.load(open(a.data, encoding="utf-8"))["cards"], key=lambda x: x["id"])
    grown = [c for c in cards if c.get("status", "grown") == "grown"]
    tax = json.load(open(a.taxonomy, encoding="utf-8"))
    nodes, warnings = build_tree(grown, tax)
    warnings = sorted(set(warnings) | set(build_tree(cards, tax)[1]))  # the chart includes wishlist cards
    sort_children(nodes[ROOT])
    today = datetime.date.today().isoformat()

    written = set()

    def write(rel, render):
        path = os.path.join(a.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        text = render(read_created(path) or today)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        written.add(os.path.normpath(path))

    write(ROOT + ".md", lambda d: root_note(nodes, tax, d))
    write(ROOT + ".svg", lambda d: family_tree_svg(cards, tax))  # wishlist included, in grey
    for n in nodes.values():
        if n.rank == "root":
            continue
        if n.rank == "vegetable":
            write(os.path.join("Grown", safe_file(n.name) + ".md"), lambda d, n=n: veg_note(n, d))
        else:
            write(os.path.join("Taxa", safe_file(n.name) + ".md"), lambda d, n=n: taxon_note(n, d))

    stale = []
    for dp, _, fns in os.walk(a.out):
        for fn in fns:
            p = os.path.normpath(os.path.join(dp, fn))
            if fn.endswith(".md") and p not in written:
                try:
                    if MARK in open(p, encoding="utf-8").read(2000):
                        stale.append(os.path.relpath(p, a.out))
                except OSError:
                    pass
    for w in warnings:
        print("WARNING:", w)
    for s in stale:
        print("STALE:", s)
    print("wrote %d notes to %s (%d grown of %d cards; notes are grown only; the chart shows growing in green-grey, failed in red, wishlist in grey)"
          % (len(written), a.out, len(grown), len(cards)))


if __name__ == "__main__":
    main()
