"""Move a Vegedex card from one status to another in one step.

Allowed transitions (anything else is refused):
    wishlist -> growing     sown / planted out
    growing  -> failed      it didn't make it
    failed   -> growing     resown / replanted
    growing  -> grown       harvested: needs --photo

Usage, from the repo root:
    python3 src/vegedex/transition.py --id 12 --to growing [--date "Sep 2026"] [--variant "Musselburgh"]
    python3 src/vegedex/transition.py --id 12 --to failed  [--date "Oct 2026"]
    python3 src/vegedex/transition.py --id 12 --to grown   --photo photos/leek.jpg [--date "Nov 2026"]
                                                        [--focus 0.5 0.5] [--zoom 1.0]
    add --dry-run to see the change without saving, --no-render to skip rebuilding.

What each move does to the card's fields (cards.json is edited in place):
    -> growing  status, planted = --date or this month; from wishlist drops added, the
                reference photo and photo_credit (back to the "?"); from failed drops failed
    -> failed   status, failed = --date or this month; keeps planted and any growing photo
    -> grown    status, photo (copied into photos/ if it lives elsewhere), harvested = --date,
                else the date in a phone file name (20260711_...), else this month;
                drops added, planted, failed, photo_credit; resets the crop unless given
Then it re-renders that card and the collection, the family tree and both gallery pages,
and writes a preview PNG to build/preview.png (in the repo).
Data and photos live in the repo (data/); outputs go to the vault (see paths.py).
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys

ALLOWED = {("wishlist", "growing"), ("growing", "failed"), ("failed", "growing"), ("growing", "grown")}
import paths

HERE = os.path.dirname(os.path.abspath(__file__))


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def month(d):
    return d.strftime("%b %Y")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--id", type=int, required=True)
    ap.add_argument("--to", required=True, choices=["growing", "failed", "grown"])
    ap.add_argument("--date", help='month and year, e.g. "Oct 2026" (default: this month)')
    ap.add_argument("--photo", help="harvest photo (required for --to grown)")
    ap.add_argument("--variant", help="set the variant if it is now known")
    ap.add_argument("--focus", type=float, nargs=2, metavar=("X", "Y"))
    ap.add_argument("--zoom", type=float)
    ap.add_argument("--data", default=paths.CARDS_JSON)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    base = os.path.dirname(os.path.abspath(a.data))

    data = json.load(open(a.data, encoding="utf-8"))
    card = next((c for c in data["cards"] if c["id"] == a.id), None)
    if card is None:
        sys.exit("No card with id %d." % a.id)
    old = card.get("status", "grown")
    if (old, a.to) not in ALLOWED:
        ok = ", ".join("%s -> %s" % t for t in sorted(ALLOWED))
        sys.exit("Refused: %s (No. %03d) is %s; %s -> %s isn't allowed. Allowed: %s."
                 % (card["name"], a.id, old, old, a.to, ok))
    when = a.date or month(datetime.date.today())

    if a.to == "grown":
        if not a.photo:
            sys.exit("Refused: moving to grown needs a harvest photo (--photo path/to/photo.jpg).")
        src = a.photo if os.path.isabs(a.photo) else os.path.join(base, a.photo)
        if not os.path.isfile(src):
            sys.exit("Refused: photo not found: %s" % src)
        photos = os.path.join(base, "photos")
        if os.path.dirname(os.path.abspath(src)) == os.path.abspath(photos):
            rel = "photos/" + os.path.basename(src)
        else:
            v = (a.variant or card.get("variant", "Unknown"))
            stem = slug(card["name"]) + ("" if v.startswith("Unknown") else "-" + slug(v))
            rel = "photos/%s%s" % (stem, os.path.splitext(src)[1].lower() or ".jpg")
            if not a.dry_run:
                os.makedirs(photos, exist_ok=True)
                shutil.copy2(src, os.path.join(base, rel))
        m = re.search(r"(20\d\d)(\d\d)(\d\d)", os.path.basename(src))
        harvested = a.date or (month(datetime.date(int(m.group(1)), int(m.group(2)), 1)) if m else when)
        for k in ("added", "planted", "failed", "photo_credit"):
            card.pop(k, None)
        card.update(status="grown", photo=rel, harvested=harvested,
                    photo_focus=list(a.focus) if a.focus else [0.5, 0.5], photo_zoom=a.zoom or 1.0)
    elif a.to == "growing":
        if old == "wishlist":
            for k in ("added", "photo_credit", "photo", "photo_focus", "photo_zoom"):
                card.pop(k, None)
        card.pop("failed", None)
        card.update(status="growing", planted=when)
    else:  # failed
        card.update(status="failed", failed=when)
    if a.variant:
        card["variant"] = a.variant

    shown = {k: card.get(k) for k in ("status", "variant", "planted", "failed", "harvested", "added", "photo") if k in card}
    print("%s (No. %03d): %s -> %s  %s" % (card["name"], a.id, old, a.to, json.dumps(shown)))
    if a.dry_run:
        print("Dry run: nothing saved.")
        return
    tmp = a.data + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, a.data)
    if a.no_render:
        return

    py, tax = sys.executable, os.path.join(base, "taxonomy.json")
    V = paths.vault()   # outputs go to the vault; data and photos stay in the repo
    build = paths.BUILD
    os.makedirs(build, exist_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    steps = [
        [py, os.path.join(HERE, "make_cards.py"), "--data", a.data, "--out", V, "--only", str(a.id)],
        [py, os.path.join(HERE, "make_graph.py"), "--data", a.data, "--taxonomy", tax, "--out", os.path.join(V, "Family Tree")],
        [py, os.path.join(HERE, "make_gallery.py"), "--data", a.data, "--taxonomy", tax, "--cards", V,
         "--out", os.path.join(V, "Vegedex.html")],
        [py, os.path.join(HERE, "make_gallery.py"), "--data", a.data, "--taxonomy", tax, "--cards", V,
         "--fragment", "--out", os.path.join(build, "vegedex-fragment.html")],
    ]
    for s in steps:
        subprocess.run(s, check=True, env=env)
    pdf = glob.glob(os.path.join(V, "%03d-*.pdf" % a.id))
    if pdf and shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", "110", "-png", "-singlefile", pdf[0], os.path.join(build, "preview")], check=True)
        print("preview: build/preview.png")


if __name__ == "__main__":
    main()
