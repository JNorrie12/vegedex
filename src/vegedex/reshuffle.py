#!/usr/bin/env python3
"""
Vegedex reshuffle: renumber every card so relatives sit together.

Order (fixed, so every reshuffle gives the same result for the same cards):
  1. botanical family, A-Z           (Amaranthaceae, Brassicaceae, Cucurbitaceae, ...)
  2. species, A-Z                    (first two words of the Latin name: "Solanum lycopersicum")
  3. grown, growing, failed, then wishlist           (a wishlist courgette lands right after the grown courgette)
  4. common name, then variant, A-Z
  5. old id                          (tie-break)
Cards with an Unknown family or Latin name go to the end.

What it does:
  * rewrites the ids in cards.json (and sorts the list by the new id)
  * renames the PDFs in --cards to their new NNN-slug.pdf names (two-phase, no clashes)
  * re-renders every card whose number changed (the number is printed on the card),
    then rebuilds veggie-dex-collection.pdf via make_cards.py
  * writes vault_renames.sh: the same renames for the user's Vegedex folder
    (run it there BEFORE copying the new PDFs in, so no stale files are left behind)

Usage:
    python reshuffle.py --dry-run      # show the new order, change nothing
    python reshuffle.py                # do it

It refuses to run if a grown card that needs re-rendering has no photo available,
because that card would come out with the '?' placeholder.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

import paths

UNK = "￿"  # sorts after any real name


def clean(s):
    s = re.sub(r"\s*\[\d+\]", "", s or "").strip()
    return "" if s.lower().startswith("unknown") else s


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def pdf_name(card_id, name):
    return "%03d-%s.pdf" % (card_id, slug(name))


def sort_key(c):
    fam = clean(c.get("family")).lower() or UNK
    words = re.sub(r"\(.*?\)", "", clean(c.get("latin"))).split()
    species = " ".join(words[:2]).lower() or UNK
    status = {"grown": 0, "growing": 1, "failed": 2, "wishlist": 3}.get(c.get("status", "grown"), 0)
    return (fam, species, status, c["name"].lower(), clean(c.get("variant")).lower(), c["id"])


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=paths.CARDS_JSON)
    ap.add_argument("--cards", default=None, help="folder holding the card PDFs (default: the vault)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.cards = a.cards or paths.vault()

    base = os.path.dirname(os.path.abspath(a.data))
    doc = json.load(open(a.data))
    cards = doc["cards"]
    ordered = sorted(cards, key=sort_key)
    moves = []  # (card, old_id, new_id)
    for new_id, c in enumerate(ordered, 1):
        moves.append((c, c["id"], new_id))

    print("%-4s %-4s %-20s %-30s %-16s %s" % ("NEW", "OLD", "NAME", "LATIN", "FAMILY", "STATUS"))
    for c, old, new in moves:
        print("%03d  %03d  %-20s %-30s %-16s %s%s" % (
            new, old, c["name"][:20], clean(c.get("latin"))[:30] or "Unknown",
            clean(c.get("family"))[:16] or "Unknown", c.get("status", "grown"),
            "" if old == new else "   <- moved"))
    changed = [(c, o, n) for c, o, n in moves if o != n]
    if not changed:
        print("\nAlready in order. Nothing to do.")
        return
    if a.dry_run:
        print("\n%d card(s) would be renumbered (dry run, nothing changed)." % len(changed))
        return

    # Safety: every re-rendered card that should have a photo must have it here.
    missing = [c["name"] for c, o, n in changed
               if c.get("photo") and not os.path.exists(os.path.join(base, c["photo"]))]
    if missing:
        sys.exit("Stopped, nothing changed: photo missing for %s. Copy the photos/ folder "
                 "from the Vegedex folder first." % ", ".join(missing))

    # 1. rename PDFs locally, two-phase so 003->005 and 005->003 can't clash
    renames = [(pdf_name(o, c["name"]), pdf_name(n, c["name"])) for c, o, n in changed]
    for old_fn, _ in renames:
        p = os.path.join(a.cards, old_fn)
        if os.path.exists(p):
            os.rename(p, p + ".reshuffle-tmp")
    for old_fn, new_fn in renames:
        p = os.path.join(a.cards, old_fn) + ".reshuffle-tmp"
        if os.path.exists(p):
            os.rename(p, os.path.join(a.cards, new_fn))

    # 2. same renames as a script for the user's Vegedex folder
    os.makedirs(paths.BUILD, exist_ok=True)
    sh = os.path.join(paths.BUILD, "vault_renames.sh")
    with open(sh, "w") as f:
        f.write("#!/bin/sh\n# Run inside the Vegedex folder: sh vault_renames.sh\nset -e\n")
        for old_fn, _ in renames:
            f.write("[ -f %s ] && mv %s %s.reshuffle-tmp || true\n"
                    % (shlex.quote(old_fn), shlex.quote(old_fn), shlex.quote(old_fn)))
        for old_fn, new_fn in renames:
            f.write("[ -f %s.reshuffle-tmp ] && mv %s.reshuffle-tmp %s || true\n"
                    % (shlex.quote(old_fn), shlex.quote(old_fn), shlex.quote(new_fn)))

    # 3. new ids into cards.json
    for c, o, n in moves:
        c["id"] = n
    doc["cards"] = sorted(cards, key=lambda c: c["id"])
    with open(a.data, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 4. re-render the renumbered cards (+ rebuild the collection)
    ids = [str(n) for c, o, n in changed]
    subprocess.run([sys.executable, os.path.join(here, "make_cards.py"), "--data", a.data,
                    "--out", a.cards, "--only"] + ids, check=True)
    print("\nRenumbered %d card(s). Vault renames written to %s" % (len(changed), sh))


if __name__ == "__main__":
    main()
