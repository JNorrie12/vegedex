"""Where the Vegedex lives.

The repo holds the source of truth (scripts, data/cards.json, data/taxonomy.json,
data/photos/). Everything the scripts *produce* (card PDFs, the collection PDF,
Vegedex.html and the Family Tree notes) is written into the Obsidian vault folder.

The vault folder is the first existing path from:
  1. the VEGEDEX_VAULT environment variable
  2. "vault_paths" in config.json at the repo root (tried in order)
"""
import json
import os

SRC = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(SRC))
DATA = os.path.join(REPO, "data")
CARDS_JSON = os.path.join(DATA, "cards.json")
TAXONOMY = os.path.join(DATA, "taxonomy.json")
BUILD = os.path.join(REPO, "build")   # scratch (gitignored): previews, artifact fragment


def vault():
    cands = []
    if os.environ.get("VEGEDEX_VAULT"):
        cands.append(os.environ["VEGEDEX_VAULT"])
    try:
        with open(os.path.join(REPO, "config.json"), encoding="utf-8") as f:
            cands += json.load(f).get("vault_paths", [])
    except OSError:
        pass
    for c in cands:
        p = os.path.expandvars(os.path.expanduser(c))
        if os.path.isdir(p):
            return p
    raise SystemExit("Vegedex vault folder not found. Tried: %s. Set vault_paths in config.json "
                     "or the VEGEDEX_VAULT environment variable." % (", ".join(cands) or "nothing"))
