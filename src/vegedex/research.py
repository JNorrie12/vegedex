"""Research a vegetable with Mistral's web search and draft its card data.

Two steps:
  1. A Mistral conversation with the built-in `web_search` tool looks up the RHS
     grow-your-own page, the RHS plant entry and recipes, and writes research notes
     where every fact is followed by the URL it came from.
  2. A JSON-mode chat call turns those notes into the card fields from README step C,
     citing sources by number. Unused sources are dropped and citations renumbered.

The API key is MISTRAL_API_KEY, from the environment, a .env file at the repo root,
or the file named by "mistral_env_file" in config.json.

Usage (for a quick check from the repo root):
    python src/vegedex/research.py "Leek" ["Musselburgh"]
"""
import json
import os
import re
import sys

import paths

try:
    from mistralai.client import Mistral  # mistralai >= 2
except ImportError:  # pragma: no cover
    from mistralai import Mistral  # mistralai 1.x

CATEGORIES = ["Root", "Fruiting", "Leafy", "Legume", "Allium", "Brassica", "Herb", "Other"]
TEXT_FIELDS = ["latin", "family", "planting_window", "harvest_window"]
LIST_FIELDS = ["special_instructions", "recipes"]


def _config():
    try:
        with open(os.path.join(paths.REPO, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def api_key():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(paths.REPO, ".env"))
    extra = _config().get("mistral_env_file")
    if extra:
        load_dotenv(os.path.expandvars(os.path.expanduser(extra)))
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY not found. Put it in a .env file at the repo root, "
                           "set it as an environment variable, or point config.json "
                           "\"mistral_env_file\" at a .env file that has it.")
    return key


def models():
    cfg = _config().get("mistral_models", {})
    return cfg.get("search", "mistral-medium-latest"), cfg.get("extract", "mistral-medium-latest")


SEARCH_INSTRUCTIONS = """You research vegetables for a UK allotment grower's trading-card collection.
Use web_search several times. Look for, in this order of preference:
1. The RHS "grow your own" page for the crop (rhs.org.uk/vegetables/<crop>/grow-your-own):
   the sowing/planting months, the harvest months, and 2-3 practical growing tips (UK timings).
2. The RHS plant entry (rhs.org.uk/plants/...) for the species or a cultivar: the botanical
   (Latin) name without the cultivar, and the botanical family.
3. If a variety/cultivar is named: the RHS plant entry or a seed supplier's page for that variety.
4. Recipes: BBC Good Food first, then Great British Chefs, then other reputable recipe sites:
   2-3 dish names that feature the vegetable.
Write plain research notes. After EVERY fact put the exact URL it came from in brackets.
Use only what the search results say; never fill in from memory. If something can't be found,
write "Unknown" for it."""

EXTRACT_PROMPT = """Turn these research notes into card data for a vegetable trading card.

Vegetable: {name}
Variety: {variant}

### Research notes
{notes}

### Numbered sources
{sources}

Return a JSON object with exactly these keys:
- "latin": botanical name without the cultivar, then its citation, e.g. "Daucus carota [3]"
- "family": botanical family, then its citation, e.g. "Apiaceae [3]"
- "category": one of {categories}
- "sow_months": list of month numbers 1-12 when it is sown or planted in the UK
- "harvest_months": list of month numbers 1-12 when it is harvested
- "planting_window": one short sentence (under 120 characters) ending with a citation
- "harvest_window": one short sentence (under 120 characters) ending with a citation
- "special_instructions": 2-3 short growing tips (under 90 characters each), each ending with a citation
- "recipes": 2-3 dish names only (no descriptions), each ending with a citation

Rules:
- Citations are "[n]" where n is the number of a source in the list above. Cite only sources
  the fact came from.
- Use only facts in the notes. Anything not in the notes is "Unknown" (no citation), and
  months that aren't in the notes are [].
- Months like "late winter" map to their months (Feb), "spring" to Mar-May, "autumn" to Sep-Nov.
"""


def _urls_in(text):
    return [u.rstrip(").,;]") for u in re.findall(r"https?://[^\s\)\]\"'<>]+", text)]


def search_notes(client, name, variant, model):
    """Step 1: web search. Returns (notes text, ordered list of source URLs)."""
    ask = "Research the vegetable: %s" % name
    if variant and not variant.lower().startswith("unknown"):
        ask += " (variety: %s)" % variant
    r = client.beta.conversations.start(model=model, inputs=ask, instructions=SEARCH_INSTRUCTIONS,
                                        tools=[{"type": "web_search"}], store=False)
    parts, refs, seen_results = [], [], []
    for entry in r.outputs:
        kind = getattr(entry, "type", "")
        if kind == "tool.execution":
            info = getattr(entry, "info", None) or {}
            res = info.get("result") if isinstance(info, dict) else None
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except ValueError:
                    res = None
            items = res.values() if isinstance(res, dict) else res if isinstance(res, list) else []
            seen_results += [v.get("url") for v in items if isinstance(v, dict) and v.get("url")]
        elif kind == "message.output":
            content = entry.content
            if isinstance(content, str):
                parts.append(content)
                continue
            for chunk in content:
                ctype = getattr(chunk, "type", "")
                if ctype == "text":
                    parts.append(chunk.text)
                elif ctype == "tool_reference" and getattr(chunk, "url", None):
                    refs.append(chunk.url)
                    parts.append(" (%s)" % chunk.url)
    notes = "".join(parts).strip()
    sources = []
    for u in refs + _urls_in(notes):
        if u and "translate.goog" not in u and u not in sources:
            sources.append(u)
    return notes, sources, seen_results


def _renumber(card, sources):
    """Keep only cited sources (in order of first citation) and renumber [n] to match."""
    order = []

    def collect(t):
        for n in re.findall(r"\[(\d+)\]", t or ""):
            n = int(n)
            if 1 <= n <= len(sources) and n not in order:
                order.append(n)

    fields = [card[k] for k in TEXT_FIELDS] + [x for k in LIST_FIELDS for x in card[k]]
    for t in fields:
        collect(t)
    mapping = {old: new for new, old in enumerate(order, 1)}

    def fix(t):
        t = re.sub(r"\[(\d+)\]", lambda m: "[%d]" % mapping[int(m.group(1))] if int(m.group(1)) in mapping else "", t)
        return re.sub(r"\s+", " ", t).strip()

    for k in TEXT_FIELDS:
        card[k] = fix(card[k])
    for k in LIST_FIELDS:
        card[k] = [fix(x) for x in card[k] if fix(x)]
    card["sources"] = [sources[n - 1] for n in order]
    return card


def _months(v):
    out = []
    for m in v if isinstance(v, list) else []:
        try:
            m = int(m)
        except (TypeError, ValueError):
            continue
        if 1 <= m <= 12 and m not in out:
            out.append(m)
    return sorted(out)


def research(name, variant="Unknown"):
    """Research one vegetable. Returns {"card": {...draft fields...}, "notes": str, "all_sources": [...]}."""
    name = (name or "").strip()
    if not name:
        raise ValueError("A vegetable name is needed.")
    variant = (variant or "").strip() or "Unknown"
    client = Mistral(api_key=api_key())
    search_model, extract_model = models()
    notes, sources, results = search_notes(client, name, variant, search_model)
    if not sources:
        sources = [u for u in dict.fromkeys(results) if "translate.goog" not in u][:8]
    numbered = "\n".join("[%d] %s" % (i, u) for i, u in enumerate(sources, 1)) or "(none)"
    prompt = EXTRACT_PROMPT.format(name=name, variant=variant, notes=notes or "(no notes)",
                                   sources=numbered, categories=", ".join(CATEGORIES))
    resp = client.chat.complete(model=extract_model, messages=[{"role": "user", "content": prompt}],
                                response_format={"type": "json_object"}, temperature=0.1)
    raw = json.loads(resp.choices[0].message.content)

    card = {
        "latin": str(raw.get("latin") or "Unknown"),
        "family": str(raw.get("family") or "Unknown"),
        "category": raw.get("category") if raw.get("category") in CATEGORIES else "Other",
        "sow_months": _months(raw.get("sow_months")),
        "harvest_months": _months(raw.get("harvest_months")),
        "planting_window": str(raw.get("planting_window") or "Unknown"),
        "harvest_window": str(raw.get("harvest_window") or "Unknown"),
        "special_instructions": [str(x) for x in (raw.get("special_instructions") or [])][:3],
        "recipes": [str(x) for x in (raw.get("recipes") or [])][:3],
    }
    card = _renumber(card, sources)
    return {"card": card, "notes": notes, "all_sources": sources}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = research(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Unknown")
    print(json.dumps(out, indent=2, ensure_ascii=False))
