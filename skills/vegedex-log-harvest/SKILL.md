---
name: vegedex-log-harvest
description: Use when the user uploads a photo of a vegetable they have grown or harvested for their Vegedex: makes a grown trading card (or upgrades a wishlist card) and adds it to the Obsidian family tree.
---

# Vegedex: log a harvest

The full instructions are the repo's `README.md` (Flow 1 plus shared steps A–E), in `C:\Users\norri\github\vegedex` (GitHub `JNorrie12/vegedex`). Read it first and follow it exactly. This is the checklist.

1. **Connect (step A).** Needs both the repo `C:\Users\norri\github\vegedex` and the vault `C:\Users\norri\OneDrive\Documents\my_vault`; request whichever isn't connected. Work in the computer's shell from the repo root (`R`); outputs go to the vault automatically (`config.json`).
2. **Save the photo** into `R/data/photos/` and identify the vegetable. Existing card → `python3 src/vegedex/transition.py --id <id> --to grown --photo data/photos/<file>` (wishlist/failed go `--to growing` first). Otherwise a new card with the highest id + 1.
3. **Research (step B, new cards only)** with web search: RHS grow-your-own page, RHS plant entry for Latin name and family, BBC Good Food / Great British Chefs for 2–3 recipe names. Unconfirmed → `Unknown`. Every fact has a `[n]` citation.
4. **Card (steps C–D).** Add the entry to `data/cards.json`, then `make_cards.py --only <id>`, `make_graph.py`, both `make_gallery.py` commands, and check `build/preview.png` (crop, nothing cut off, citations match).
   - `WARNING:` from `make_graph.py` → add the family's APG IV order to `data/taxonomy.json`, rerun.
   - `STALE:` → move those notes into `Vegedex/Family Tree/_to_delete/` and tell the user.
5. **Deliver (step E).** Send the card PDF; republish the gallery artifact to https://claude.ai/artifact/AFBMLRJJat5hRP82AYtQgY with every card PDF; `git commit` in the repo and push to GitHub (via a bundle from the cloud, README step E.4).
6. **Reply** briefly: the card, and where it joined the family tree (e.g. "joins Aubergine under *Solanum*, Solanaceae").

Never redesign the card, gallery or tree, and never write a new generator.
