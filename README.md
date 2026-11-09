# Vegedex

A collectible trading-card log of everything grown on the allotment, what's in the ground right now, and a wishlist of things still to grow.
Each vegetable becomes a 5 × 7 in PDF card with a photo, its Latin name and botanical family, a sow/harvest calendar, growing notes, recipe ideas and cited sources.
A gallery page shows the whole collection, and a family tree (a circular tree-of-life chart, in the gallery and in Obsidian) shows how every vegetable is related: grown ones in black, growing ones in green-grey, failed ones in red, wishlist ones in grey.

> **For Claude in any new chat:** read this file first and follow it exactly. Never redesign the card, the gallery or the family tree, and never write a new generator. Always render through `make_cards.py`, `make_gallery.py` and `make_graph.py` (renumber only through `reshuffle.py`, change status only through `transition.py`), and store every card's data in `data/cards.json`.
>
> **Work on the user's computer, not the cloud.** The repo and the vault are both on the user's computer; run everything there through the computer's shell (`device_bash`), which has Python, reportlab, pillow, pypdf and `pdftoppm`. Don't retype scripts or copy files back and forth.

---

## Repo vs vault

This repo is the **source of truth**. The Obsidian vault only holds what the scripts **produce**.

| Repo `C:\Users\norri\github\vegedex` (in git) | Vault `C:\Users\norri\OneDrive\Documents\my_vault\Vegedex` (generated) |
|---|---|
| `src/vegedex/*.py`: the generators | `NNN-slug.pdf`: one PDF per card |
| `data/cards.json`: every card's data | `veggie-dex-collection.pdf` |
| `data/taxonomy.json`: family → order → clades (APG IV) | `Vegedex.html`: the gallery page |
| `data/photos/`: every image a card uses | `Family Tree/`: notes + `Vegedex Family Tree.svg` |
| `skills/`: the Claude skill(s) for the Vegedex | |
| `config.json`: where the vault is | |
| `build/`: scratch (previews, artifact fragment), gitignored | |

`src/vegedex/paths.py` finds everything: data from the repo, outputs to the first existing folder in `config.json` → `vault_paths` (or the `VEGEDEX_VAULT` environment variable). So every script runs from the repo root with **no path arguments**.

In the Claude computer shell the two folders are:
- repo `R` = `$HOME/mnt/norri/github/vegedex` (or `$HOME/mnt/vegedex` if only the repo folder is connected)
- vault `V` = `$HOME/mnt/my_vault/Vegedex`

| Other things | Where |
|---|---|
| GitHub | `JNorrie12/vegedex` (private) |
| Gallery page (published) | https://claude.ai/artifact/AFBMLRJJat5hRP82AYtQgY (always republish to this same URL) |
| Project knowledge `claude/` | A fallback snapshot of this README, the scripts and data. GitHub is the real backup |

Set up on a new machine:
```bash
git clone https://github.com/JNorrie12/vegedex.git && cd vegedex
pip install -r requirements.txt          # plus poppler for pdftoppm (gallery + previews)
# edit config.json -> vault_paths if the vault lives somewhere else
```

---

## Ways to use the Vegedex

| # | The user says | What happens |
|---|---|---|
| 1 | Uploads a photo of a harvest | A new **grown** card (or a wishlist / growing card upgraded to grown), added to the family tree (skill `vegedex-log-harvest`) |
| 2 | "Add X to the wishlist" (+ variant if known) | A new **wishlist** card with a greyed-out reference image, added to the chart in grey |
| 3 | "View Vegedex" | The gallery page (cards + family tree) is rebuilt and republished |
| 4 | "Reshuffle" | Every card is renumbered by botanical family, so relatives sit next to each other |
| 5 | "I'm growing X" / "X is in the ground" | A new **growing** card (or wishlist / failed → growing): greyed with a green tint, "?" placeholder, green-grey on the chart |
| 6 | "X failed" / "X died" | growing → **failed**: red, "!" placeholder, red on the chart |

Every status change goes through `transition.py`, which also rebuilds the card, family tree and gallery.

---

## Status transitions

`status` is one of `wishlist`, `growing`, `failed`, `grown`. Only these moves are allowed:

| From | To | When | Needs |
|---|---|---|---|
| wishlist | growing | sown or planted out | — (optional `--date`, `--variant`) |
| growing | failed | it didn't make it | — (optional `--date`) |
| failed | growing | resown or replanted | — (optional `--date`) |
| growing | grown | harvested | **a photo** (`--photo`) |

```bash
cd "$R" && export PYTHONDONTWRITEBYTECODE=1
python3 src/vegedex/transition.py --id <id> --to growing|failed|grown [--date "Oct 2026"] [--photo data/photos/x.jpg] [--variant "..."] [--dry-run]
```

It refuses any other move and refuses `--to grown` without an existing photo. It edits `data/cards.json` in place, re-renders the card and collection into the vault, rebuilds the family tree and both gallery pages, and writes `build/preview.png`. After it, only step E is left. A wishlist card harvested without being logged as growing goes wishlist → growing → grown in two commands.

What each move does to the fields:
- **→ growing**: `planted` = `--date` or this month. From wishlist it drops `added`, the reference `photo`, `photo_credit` and the crop settings. From failed it drops `failed`.
- **→ failed**: `failed` = `--date` or this month; keeps `planted` and any growing photo (tinted red).
- **→ grown**: copies the photo into `data/photos/` if it's elsewhere (named `<name>[-<variant>].jpg`); `harvested` = `--date`, else the date in a phone file name (`20260711_…`), else this month; drops `added`, `planted`, `failed`, `photo_credit`; resets the crop (or `--focus X Y`, `--zoom Z`). Check the preview and tune the crop if needed.

---

## Shared steps

### A. Connect (start of every flow)
1. Check the connected folders (`get_device_info`). The flow needs **both** `C:\Users\norri\github\vegedex` and `C:\Users\norri\OneDrive\Documents\my_vault` (or its `Vegedex` subfolder). Request whichever is missing, in one request. Folder access is per chat.
2. `cd "$R" && git status -sb && python3 -c "import reportlab, PIL, pypdf"` (if a library is missing: `pip install -r requirements.txt`). Uncommitted changes from a previous run? Mention them before starting.
3. Read `data/cards.json` only as far as needed (e.g. `python3 -c` to print ids and names). New cards get the highest `id` + 1. Numbers only change on "reshuffle".
4. Fallback only if the computer can't be reached: clone the repo in the cloud and work there; tell the user this run is slower and why.

### B. Research with web search
Always search, even for familiar crops. Fetch the page and take facts from it; don't fill in from memory. (RHS URLs can be refused until they've appeared in a search result, so search first, then fetch.)

| Field | Preferred source |
|---|---|
| Planting window, harvest window, special instructions | RHS "grow your own" page (UK timings): `rhs.org.uk/vegetables/<crop>/grow-your-own` |
| Latin name and family | RHS plant entry for the species or a cultivar (`rhs.org.uk/plants/...`) |
| Variant-specific details | RHS plant entry or the seed supplier's page |
| Recipes | BBC Good Food, then Great British Chefs, then other reputable recipe sites |
| Order of a family not yet in `taxonomy.json` | APG IV (the two sources in `taxonomy.json`) |

Anything that can't be found or confirmed is `Unknown`.

### C. Card data in `data/cards.json`
Add or edit the entry in place with a short `python3` read-modify-write (never retype the whole file). Shape:

```json
{
  "id": 7,
  "name": "Carrot",
  "latin": "Daucus carota [3]",
  "family": "Apiaceae [3]",
  "variant": "Unknown",
  "category": "Root",
  "status": "grown",
  "harvested": "Oct 2026",
  "added": "Oct 2026",
  "planted": "Sep 2026",
  "photo": "photos/carrot.jpg",
  "photo_focus": [0.5, 0.5],
  "photo_zoom": 1.0,
  "photo_credit": "Author name, CC BY-SA 4.0, Wikimedia Commons",
  "sow_months": [3, 4, 5, 6],
  "harvest_months": [6, 7, 8, 9, 10],
  "planting_window": "Short text with a citation [1]",
  "harvest_window": "Short text with a citation [1]",
  "special_instructions": ["Bullet one [1]", "Bullet two [1]", "Bullet three [1]"],
  "recipes": ["Dish name [2]", "Dish name [2]", "Dish name [3]"],
  "sources": ["https://www.rhs.org.uk/vegetables/...", "https://www.bbcgoodfood.com/..."]
}
```

Field rules:
- `name`: the vegetable. `variant`: the cultivar only if the user states it; otherwise `Unknown`. A visible type hint may go in brackets, e.g. `Unknown (purple-top type)`. Never guess a named cultivar.
- `latin`: botanical name as RHS gives it, without the cultivar. `family`: botanical family. Both end with a citation; they drive the reshuffle order and the family tree. `Unknown` if not found.
- `category` sets the colour of grown cards: `Root`, `Fruiting`, `Leafy`, `Legume`, `Allium`, `Brassica`, `Herb`, `Other`.
- `status`: set by hand only when a card is first added; after that use `transition.py`.
- Dates: `harvested` (grown), `planted` (growing; kept on failed), `failed` (failed), `added` (wishlist), as "Mon YYYY".
- `photo`: **relative to `data/`**, i.e. `photos/<name>[-<variant>].jpg`, lower-case-with-hyphens; `-ref` suffix for a wishlist reference image, `-growing` for a photo of the plant still growing. Grown cards require the user's photo. Leave it out if there's no image.
- `photo_credit`: required whenever the image isn't the user's own.
- `photo_focus` [x, y] (0–1) and `photo_zoom` (≥ 1) tune the crop.
- `sow_months` / `harvest_months`: 1–12. `[]` if unknown.
- `special_instructions`: 2–3 short bullets. `recipes`: 2–3 dish names only.
- Every fact ends with `[n]`, the 1-based position of its URL in `sources`. Keep text short.

Photos the user uploads arrive in the cloud workspace: copy to `/mnt/user-data/outputs/` and save into `R/data/photos/` with `device_commit_files` before rendering.

### D. Render and check (in `R`)
```bash
cd "$R" && export PYTHONDONTWRITEBYTECODE=1 && mkdir -p build
python3 src/vegedex/make_cards.py --only <id>            # card(s) + rebuilt collection, into the vault
python3 src/vegedex/make_graph.py                        # vault/Family Tree
python3 src/vegedex/make_gallery.py                      # vault/Vegedex.html
python3 src/vegedex/make_gallery.py --fragment --out build/vegedex-fragment.html
pdftoppm -r 110 -png -singlefile "$V/<NNN-slug>.pdf" build/preview
```
Always use `--only` with just the cards you changed; the collection is stitched from the per-card PDFs already in the vault. Never render a grown card without its photo.

Check the preview (stage `R/build/preview.png`): vegetable centred and filling the photo window; no text running into the footer; every `[n]` matches a source.

Check `make_graph.py` output:
- `WARNING:` → the card's family is missing from `data/taxonomy.json`: add its APG IV order (and the order's clade path if new) and rerun.
- `STALE:` → generated notes no longer needed: move them into `V/Family Tree/_to_delete/` with `mv` and tell the user.
- Before adding a new note name, check no note with that name exists elsewhere in the vault.

### E. Deliver, commit, push
1. Send the new card PDF(s) in the chat (stage from `V`, then `SendUserFile`).
2. Republish the gallery artifact to its URL: stage `R/build/vegedex-fragment.html` and every `V/NNN-slug.pdf` in one `device_stage_files` call, copy them into the cloud scratchpad, publish the fragment as `vegedex.html` with each card PDF as a supporting file at the root.
3. **Commit** in `R`: `git add -A && git commit -m "<what changed, e.g. Add Leek (No. 021, grown)>"`.
4. **Push.** The computer's shell can't reach GitHub, so push from the cloud: `git bundle create build/push.bundle main` in `R`, stage it, then in the cloud `git clone` (or `fetch`) from the bundle, `add_repo` JNorrie12/vegedex with push access, and `git push origin main`. Finally, in `R`: `git update-ref refs/remotes/origin/main main`. (Or the user runs `git push` themselves.)
5. Only change the scripts if the user asks for a design change; then re-render all cards.

---

## Flow 1: Log a harvest (photo upload)
1. Step A.
2. Identify the vegetable from the photo and the user's words. Save the photo into `R/data/photos/` first. If it's already a card:
   - **growing** → `transition.py --id <id> --to grown --photo data/photos/<file>`, check the preview, then step E.
   - **wishlist** → `--to growing`, then `--to grown --photo ...`.
   - **failed** → `--to growing`, then `--to grown --photo ...`.
3. Otherwise a new entry with the next id: steps B–E. Several photos: research all, add all, render with one `--only id1 id2 ...`.
4. If something is visible in the photo (e.g. split roots), one instruction may tie it to a cited cause.
5. Family tree always: say where it landed, e.g. "joins Tomato under *Solanum* (Solanaceae)".

## Flow 2: Add to the wishlist
1. Step A. Vegetable name and optional variant.
2. Step B.
3. Reference image (greyed automatically): an image the user attaches (ask for its credit if not theirs); else a freely licensed Wikimedia Commons image via `curl` (record author and licence in `photo_credit`); if downloads are blocked, leave `photo` out (the "?" silhouette) and tell the user they can allow `upload.wikimedia.org` and `commons.wikimedia.org` under Settings > Capabilities, or attach a picture. Never photos of people, brand artwork, or images without a clear free licence.
4. `status: "wishlist"`, `added`: this month. Steps C–E including the family tree.

## Flow 3: View Vegedex
1. Step A.
2. The two `make_gallery.py` commands from step D.
3. Republish the artifact (step E.2). Nothing to commit unless data changed.
4. Reply with how many are grown, growing, failed and on the wishlist.

The gallery has two views (Cards / Family tree). Cards: grid with All / Grown / Growing / Failed / Wishlist filters and a progress bar; click to enlarge, Prev / Next or arrow keys, "Open PDF". Family tree: the same chart as `Vegedex Family Tree.svg`; click a vegetable to open its card. Opened from the vault, it works offline.

## Flow 4: Reshuffle
Only when the user says "reshuffle".
1. Step A.
2. Fill in missing `latin` / `family` (step B).
3. `python3 src/vegedex/reshuffle.py --dry-run`. Order: family A–Z, species A–Z, then grown, growing, failed, wishlist, then name and variant.
4. `python3 src/vegedex/reshuffle.py`. It renames the PDFs in the vault in place, rewrites the ids, re-renders the renumbered cards and rebuilds the collection. (`build/vault_renames.sh` is a record only; it isn't needed.)
5. `make_graph.py` (notes embed card PDFs by number).
6. Rebuild and republish the gallery; commit and push (step E).
7. Reply with a short old → new table.

## Flow 5: Add something that's growing
1. Step A. Name, optional variant and when it was sown/planted.
2. Already a **wishlist** or **failed** card → `transition.py --id <id> --to growing [--date ...] [--variant ...]`, then step E.
3. Otherwise a new entry: step B, `status: "growing"`, `planted` if given, no `photo` unless the user sends one of the plant growing.
4. Steps C–E including the family tree.
5. Harvested later → Flow 1. Failed → `transition.py --id <id> --to failed`, then step E.

## Correcting a card
Edit the entry in `data/cards.json`, re-render with `--only <id>`, rerun `make_graph.py` and the gallery, republish, commit and push.

## The family tree (Obsidian)
`make_graph.py` turns every grown card into linked notes in `V/Family Tree/` and draws every card on the chart:
`Vegedex Family Tree` › Angiosperms › clades › order › family › genus › species › vegetable.
- Family from the card (RHS); order and clades from `data/taxonomy.json` (APG IV).
- Each note links only to its parent and children, so the graph view is a clean tree. Each vegetable note embeds its card PDF.
- `Vegedex Family Tree.svg`: a half-circle tree-of-life chart (full circle past 30 vegetables), redrawn on every run.
- Notes are tagged `vegedex/rank/<rank>`. Never edit `.obsidian/` settings. The whole set is regenerated every run, so it can't drift.

## Why the output stays consistent
- One generator each for cards, gallery and family tree, versioned in git and run as-is.
- Fixed design in code (360 × 504 pt page, category colours, calendar, section order); built-in Helvetica only.
- Data separated from design: cards differ only by their `cards.json` entry.
- Fixed rules for unknowns and sources, numbering (`reshuffle.py` only) and status (`transition.py` only).
- Every data change is a git commit, so any card can be traced or rolled back.

## Design notes
The card is an original trading-card layout inspired by collectible-card games. It does not use Pokémon names, logos, symbols or artwork, and future versions should keep it that way.
