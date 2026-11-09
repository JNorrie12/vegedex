"""The Vegedex web app: every README flow through a browser UI.

Run from the repo root:
    .venv\\Scripts\\python src/vegedex/server.py          (Windows)
    python3 src/vegedex/server.py                         (anywhere else)
then open http://127.0.0.1:5173

It never draws anything itself. Data goes into data/cards.json and data/photos/, and every
output is rendered by the existing scripts (make_cards.py, make_graph.py, make_gallery.py,
transition.py, reshuffle.py), exactly as the README's command-line flows do. Research uses
Mistral's web search (research.py).
"""
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

import paths
import research

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
PHOTOS = os.path.join(paths.DATA, "photos")
PREVIEWS = os.path.join(paths.BUILD, "previews")
UPLOADS = os.path.join(paths.BUILD, "uploads")
STATUSES = ["grown", "growing", "failed", "wishlist"]
ALLOWED = {("wishlist", "growing"), ("growing", "failed"), ("failed", "growing"), ("growing", "grown")}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
EDITABLE = ["name", "variant", "category", "latin", "family", "planting_window", "harvest_window",
            "special_instructions", "recipes", "sources", "sow_months", "harvest_months",
            "photo_focus", "photo_zoom", "photo_credit", "harvested", "planted", "failed", "added"]

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
lock = threading.Lock()   # one write/render at a time


# ---------- helpers ----------

def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", (t or "").lower()).strip("-")


def this_month():
    return datetime.date.today().strftime("%b %Y")


def month_label(v):
    """'2026-10' (from <input type=month>) or 'Oct 2026' -> 'Oct 2026'."""
    v = (v or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})", v)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), 1).strftime("%b %Y")
    return v


def load():
    with open(paths.CARDS_JSON, encoding="utf-8") as f:
        return json.load(f)


def save(doc):
    tmp = paths.CARDS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, paths.CARDS_JSON)


def find(doc, cid):
    c = next((c for c in doc["cards"] if c["id"] == cid), None)
    if c is None:
        abort(404, "No card with id %d." % cid)
    return c


def vault():
    return paths.vault()


def card_pdf(cid):
    hits = sorted(glob.glob(os.path.join(vault(), "%03d-*.pdf" % cid)))
    return hits[0] if hits else None


def env():
    return dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(args):
    """Run one of the repo's scripts; returns (ok, output)."""
    p = subprocess.run([sys.executable] + args, cwd=paths.REPO, env=env(), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode == 0, out.strip()


def render(ids):
    """README step D for the given card ids: card(s) + collection, family tree, both gallery pages."""
    V = vault()
    os.makedirs(paths.BUILD, exist_ok=True)
    tax = paths.TAXONOMY
    steps = []
    if ids:
        steps.append(["src/vegedex/make_cards.py", "--out", V, "--only"] + [str(i) for i in ids])
    steps += [
        ["src/vegedex/make_graph.py", "--out", os.path.join(V, "Family Tree")],
        ["src/vegedex/make_gallery.py", "--taxonomy", tax, "--cards", V, "--out", os.path.join(V, "Vegedex.html")],
        ["src/vegedex/make_gallery.py", "--taxonomy", tax, "--cards", V, "--fragment",
         "--out", os.path.join(paths.BUILD, "vegedex-fragment.html")],
    ]
    log = []
    for s in steps:
        ok, out = run(s)
        log.append("$ python " + " ".join(os.path.basename(x) if i == 0 else x for i, x in enumerate(s)))
        if out:
            log.append(out)
        if not ok:
            return False, "\n".join(log)
    return True, "\n".join(log)


def notices(log):
    return [l.strip() for l in log.splitlines() if l.strip().startswith(("WARNING", "STALE"))]


def result(ok, log, **extra):
    body = dict(ok=ok, log=log, notices=notices(log), **extra)
    return jsonify(body), (200 if ok else 500)


def save_upload(file, stem):
    """Save an uploaded image as data/photos/<stem>.<ext>; returns the path relative to data/."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in IMAGE_EXT:
        abort(400, "Photos must be .jpg, .png or .webp.")
    ext = ".jpg" if ext == ".jpeg" else ext
    os.makedirs(PHOTOS, exist_ok=True)
    name = stem + ext
    file.save(os.path.join(PHOTOS, name))
    return "photos/" + name


def photo_stem(card, suffix=""):
    v = card.get("variant") or "Unknown"
    return slug(card["name"]) + ("" if v.startswith("Unknown") else "-" + slug(v)) + suffix


def date_from_filename(fn):
    m = re.search(r"(20\d\d)(\d\d)(\d\d)", fn or "")
    if m and 1 <= int(m.group(2)) <= 12:
        return datetime.date(int(m.group(1)), int(m.group(2)), 1).strftime("%b %Y")
    return None


def clean_fields(data):
    """Pick and tidy the editable fields from a submitted card."""
    out = {}
    for k in EDITABLE:
        if k not in data:
            continue
        v = data[k]
        if k in ("special_instructions", "recipes", "sources"):
            v = [str(x).strip() for x in (v or []) if str(x).strip()]
        elif k in ("sow_months", "harvest_months"):
            v = sorted({int(x) for x in (v or []) if 1 <= int(x) <= 12})
        elif k == "photo_focus":
            v = [max(0.0, min(1.0, float(x))) for x in v][:2]
        elif k == "photo_zoom":
            v = max(1.0, float(v))
        elif k in ("harvested", "planted", "failed", "added"):
            v = month_label(v)
        else:
            v = str(v).strip()
        out[k] = v
    return out


def public(card):
    c = dict(card)
    pdf = card_pdf(card["id"])
    c["pdf"] = bool(pdf)
    # in the preview URL, so a re-render (or a change of rasteriser) busts the browser cache
    c["pdf_version"] = "%d-%s" % (int(os.path.getmtime(pdf)), (paths.rasteriser() or "x")[3]) if pdf else "0"
    c["moves"] = sorted(to for (frm, to) in ALLOWED if frm == card.get("status", "grown"))
    return c


# ---------- pages and files ----------

@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(WEB, name)


@app.get("/photos/<path:name>")
def photos(name):
    return send_from_directory(PHOTOS, name)


@app.get("/api/cards/<int:cid>/pdf")
def pdf(cid):
    p = card_pdf(cid)
    if not p:
        abort(404, "Card PDF not rendered yet.")
    return send_file(p, mimetype="application/pdf", download_name=os.path.basename(p))


@app.get("/api/collection.pdf")
def collection():
    p = os.path.join(vault(), "veggie-dex-collection.pdf")
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="application/pdf")


@app.get("/api/cards/<int:cid>/preview.png")
def preview(cid):
    p = card_pdf(cid)
    if not p:
        abort(404)
    os.makedirs(PREVIEWS, exist_ok=True)
    tool = paths.rasteriser()
    if not tool:
        abort(404, "poppler (pdftocairo or pdftoppm) not installed")
    stem = "%03d-%d-%s" % (cid, int(os.path.getmtime(p)), tool[3])   # tool in the name: old pdftoppm renders are redone
    png = os.path.join(PREVIEWS, stem + ".png")
    if not os.path.exists(png):
        for old in glob.glob(os.path.join(PREVIEWS, "%03d-*.png" % cid)):
            os.remove(old)
        subprocess.run([tool, "-r", "144", "-png", "-singlefile", p, os.path.join(PREVIEWS, stem)],
                       check=True, capture_output=True)
    return send_file(png, mimetype="image/png", max_age=3600)


@app.get("/api/tree.svg")
def tree():
    p = os.path.join(vault(), "Family Tree", "Vegedex Family Tree.svg")
    if not os.path.exists(p):
        abort(404, "No family tree yet: rebuild first.")
    return send_file(p, mimetype="image/svg+xml", max_age=0)


# ---------- API ----------

@app.get("/api/cards")
def cards():
    doc = load()
    cs = [public(c) for c in sorted(doc["cards"], key=lambda c: c["id"])]
    counts = {s: sum(1 for c in cs if c.get("status", "grown") == s) for s in STATUSES}
    try:
        v = vault()
    except SystemExit as e:
        v = None
        app.logger.warning(str(e))
    return jsonify(cards=cs, counts=counts, total=len(cs), vault=v, categories=research.CATEGORIES)


@app.post("/api/research")
def do_research():
    body = request.get_json(force=True)
    try:
        return jsonify(research.research(body.get("name"), body.get("variant")))
    except Exception as e:  # surface API/key problems to the UI
        return jsonify(error=str(e)), 502


@app.post("/api/cards")
def add_card():
    """New card (README flows 1, 2 and 5): fields as JSON in 'card', photo optional except for grown."""
    data = json.loads(request.form.get("card", "{}"))
    status = data.get("status", "wishlist")
    if status not in ("wishlist", "growing", "grown"):
        abort(400, "A new card is wishlist, growing or grown.")
    fields = clean_fields(data)
    if not fields.get("name"):
        abort(400, "A name is needed.")
    photo = request.files.get("photo")
    if status == "grown" and not photo:
        abort(400, "A grown card needs your harvest photo.")
    with lock:
        doc = load()
        cid = max((c["id"] for c in doc["cards"]), default=0) + 1
        card = {"id": cid, "name": fields["name"], "latin": "Unknown", "family": "Unknown",
                "variant": fields.get("variant") or "Unknown", "category": "Other", "status": status}
        card.update({k: v for k, v in fields.items() if k not in ("harvested", "planted", "failed", "added")})
        card["variant"] = card.get("variant") or "Unknown"
        when = {"grown": "harvested", "growing": "planted", "wishlist": "added"}[status]
        if photo:
            suffix = {"grown": "", "growing": "-growing", "wishlist": "-ref"}[status]
            card["photo"] = save_upload(photo, photo_stem(card, suffix))
            card.setdefault("photo_focus", [0.5, 0.5])
            card.setdefault("photo_zoom", 1.0)
        card[when] = fields.get(when) or (date_from_filename(photo.filename) if photo and status == "grown" else None) or this_month()
        if status == "grown":
            card.pop("photo_credit", None)
        elif not card.get("photo_credit"):
            card.pop("photo_credit", None)
        for k in ("sow_months", "harvest_months", "special_instructions", "recipes", "sources"):
            card.setdefault(k, [])
        for k in ("planting_window", "harvest_window"):
            card.setdefault(k, "Unknown")
        doc["cards"].append(card)
        save(doc)
        ok, log = render([cid])
    return result(ok, log, id=cid)


@app.put("/api/cards/<int:cid>")
def edit_card(cid):
    """Correcting a card: edit fields (not id or status), optionally replace the photo, re-render."""
    data = json.loads(request.form.get("card", "{}"))
    fields = clean_fields(data)
    photo = request.files.get("photo")
    with lock:
        doc = load()
        card = find(doc, cid)
        for k, v in fields.items():
            if v in ("", None) and k in ("photo_credit", "harvested", "planted", "failed", "added"):
                card.pop(k, None)
            else:
                card[k] = v
        if photo:
            suffix = {"grown": "", "growing": "-growing", "wishlist": "-ref", "failed": "-growing"}[card.get("status", "grown")]
            card["photo"] = save_upload(photo, photo_stem(card, suffix))
        if request.form.get("remove_photo") == "1" and card.get("status") != "grown":
            for k in ("photo", "photo_focus", "photo_zoom", "photo_credit"):
                card.pop(k, None)
        save(doc)
        ok, log = render([cid])
    return result(ok, log, id=cid)


@app.post("/api/cards/<int:cid>/transition")
def transition(cid):
    """Status change, through transition.py (it re-renders everything itself)."""
    to = request.form.get("to")
    args = ["src/vegedex/transition.py", "--id", str(cid), "--to", to]
    if request.form.get("date"):
        args += ["--date", month_label(request.form["date"])]
    if request.form.get("variant"):
        args += ["--variant", request.form["variant"].strip()]
    photo = request.files.get("photo")
    with lock:
        if photo:
            ext = os.path.splitext(photo.filename or "")[1].lower()
            if ext not in IMAGE_EXT:
                abort(400, "Photos must be .jpg, .png or .webp.")
            os.makedirs(UPLOADS, exist_ok=True)
            # keep the phone's file name so transition.py can read the date from it
            tmp = os.path.join(UPLOADS, re.sub(r"[^\w.\-]", "_", os.path.basename(photo.filename)))
            photo.save(tmp)
            args += ["--photo", tmp]
        ok, log = run(args)
    return result(ok, log, id=cid)


@app.post("/api/reshuffle")
def reshuffle():
    dry = bool(request.get_json(force=True).get("dry_run", True))
    with lock:
        ok, log = run(["src/vegedex/reshuffle.py"] + (["--dry-run"] if dry else []))
        if ok and not dry and "Nothing to do" not in log:
            ok2, log2 = render([])
            ok, log = ok2, log + "\n\n" + log2
    return result(ok, log)


@app.post("/api/rebuild")
def rebuild():
    """Flow 3: rebuild the family tree and both gallery pages (no card changes)."""
    with lock:
        ok, log = render([])
    return result(ok, log)


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
def err(e):
    return jsonify(ok=False, error=getattr(e, "description", str(e))), getattr(e, "code", 500)


if __name__ == "__main__":
    port = int(os.environ.get("VEGEDEX_PORT", "5173"))
    print("Vegedex app on http://127.0.0.1:%d  (vault: %s)" % (port, vault()))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
