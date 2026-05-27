#!/usr/bin/env python3
"""
signal_atoms.py  —  public signals into structured research
============================================================
A Signal Atom is the private research object at the heart of the engine. Each
permitted PUBLIC signal becomes one atom: its identity and citation, a reading
of what it is really about, its place in the now-versus-before frame, and its
consequences for an artist's practice, money, and relationships.

Two rules of this module:
  1. We only ever build atoms from sources the registry permits (green, or
     yellow a human has checked). Red and unpermitted sources are skipped.
  2. The MODEL fills the reading and consequence fields only. The ethics fields
     (allowed_use, risk_level, citation_required, ethical_use_status) are set by
     US from the registry, never by the model, so an atom can never claim a
     permission it does not have.

Atoms store our original analysis and a citation. They never store the full
text of a source. Caching mirrors translate.py: stable signals are analyzed
once and reused. Everything is fail-soft: with no API key, atoms are built
with identity and citation only, and the daily site is never touched.

House style: no em dashes anywhere.
"""

import hashlib
import json
import os
import re
import time

import sources_registry as REG

ATOM_MODEL = os.environ.get("AW_ATOM_MODEL", "claude-haiku-4-5-20251001")
ATOM_CACHE = os.environ.get("AW_ATOM_CACHE", "signal_atoms.json")
CACHE_CAP = 8000

# The fields the model is asked to fill. Identity and ethics are set by us.
ANALYSIS_FIELDS = ("speaker_type", "artist_voice_score", "topic_tags",
                   "emotional_signal", "psychological_need", "social_tension",
                   "historical_lineage", "now_signal", "before_signal",
                   "future_signal", "studio_consequence", "money_consequence",
                   "human_contact_consequence")

SPEAKER_TYPES = ("artist", "critic", "curator", "institution", "journalist", "scholar", "other")


def _key(item):
    raw = "|".join([item.get("title", ""), item.get("url", ""), item.get("source", "")])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_cache(path=ATOM_CACHE):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_cache(cache, path=ATOM_CACHE, cap=CACHE_CAP):
    try:
        if len(cache) > cap:
            for k in list(cache.keys())[:len(cache) - cap]:
                cache.pop(k, None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return len(cache)
    except Exception:
        return -1


def _parse_obj(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return {}
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return {}


def _no_dash(s):
    return s.replace("\u2014", ", ").replace(" -- ", ", ") if isinstance(s, str) else s


def _permitted_by_source(registry):
    """A name -> entry map of sources the engine may use now."""
    return {e.get("name"): e for e in REG.permitted_sources(registry)}


def items_from_feeds(registry=None, per_source=3, limit=60):
    """Pull recent PUBLIC entries (title, link, date) from permitted RSS sources.
    Metadata only: titles and links, never stored article bodies. Fail-soft:
    returns [] if feedparser is missing or all feeds fail."""
    try:
        import feedparser
    except Exception:
        return []
    registry = registry if registry is not None else REG.load_registry()
    permitted = _permitted_by_source(registry)
    items = []
    for e in permitted.values():
        if e.get("ingestion_method") != "rss" or not e.get("feed"):
            continue
        try:
            parsed = feedparser.parse(e["feed"])
        except Exception:
            continue
        for entry in parsed.entries[:per_source]:
            items.append({
                "title": _no_dash(getattr(entry, "title", "") or ""),
                "source": e.get("name", ""),
                "url": getattr(entry, "link", "") or e.get("url", ""),
                "date": (getattr(entry, "published", "") or getattr(entry, "updated", "") or "")[:32],
                "medium": e.get("medium", ""),
                "language": "en",
                "region": "",
            })
            if len(items) >= limit:
                return items
    return items


def _build_prompt(item):
    return (
        "You are the research desk for The Arts Wire. Analyze this PUBLIC arts "
        "signal from its title and source only. Do not invent facts the title "
        "does not imply. Write original short phrases in your own words. Never "
        "copy source wording, never fabricate quotes, no em dashes.\n\n"
        f"TITLE: {item.get('title','')}\n"
        f"SOURCE: {item.get('source','')}\n"
        f"MEDIUM: {item.get('medium','')}\n"
        f"LINK: {item.get('url','')}\n\n"
        "Return ONLY a JSON object with these keys:\n"
        '{"speaker_type": one of artist|critic|curator|institution|journalist|scholar|other,\n'
        ' "artist_voice_score": a number 0 to 1 for how directly this is an artist\'s own voice,\n'
        ' "topic_tags": up to 5 short lowercase tags,\n'
        ' "emotional_signal": a few words,\n'
        ' "psychological_need": a few words,\n'
        ' "social_tension": a few words,\n'
        ' "historical_lineage": one short phrase naming an art-historical echo,\n'
        ' "now_signal": one short sentence on what this says about now,\n'
        ' "before_signal": one short sentence on the historical parallel,\n'
        ' "future_signal": one short sentence on where it points,\n'
        ' "studio_consequence": one short sentence for a working artist,\n'
        ' "money_consequence": one short sentence on who profits or pays,\n'
        ' "human_contact_consequence": one short sentence on connection or collaboration}\n'
        "If the title is too thin to judge a field, give a brief honest best reading, not an invention."
    )


def _analyze(item, client, model, attempts=3):
    """Ask the model for the analysis fields only. Returns {} fail-soft."""
    if client is None:
        return {}
    prompt = _build_prompt(item)
    delay = 2.0
    for n in range(attempts):
        try:
            resp = client.messages.create(
                model=model, max_tokens=900,
                messages=[{"role": "user", "content": prompt}])
            d = _parse_obj(resp.content[0].text)
            return d if isinstance(d, dict) else {}
        except Exception:
            if n < attempts - 1:
                time.sleep(delay)
                delay *= 2
    return {}


def _atom_from(item, analysis, src_entry):
    """Assemble one atom: identity from the item, reading from the model, ethics
    from the registry. Missing analysis fields fall back to safe blanks."""
    a = {f: "" for f in ANALYSIS_FIELDS}
    a["topic_tags"] = []
    a["artist_voice_score"] = 0.3
    a["speaker_type"] = "journalist"
    if isinstance(analysis, dict):
        for f in ANALYSIS_FIELDS:
            if f in analysis and analysis[f] not in (None, ""):
                a[f] = analysis[f]
    # sanitize
    if a["speaker_type"] not in SPEAKER_TYPES:
        a["speaker_type"] = "other"
    try:
        a["artist_voice_score"] = max(0.0, min(1.0, float(a["artist_voice_score"])))
    except Exception:
        a["artist_voice_score"] = 0.3
    if not isinstance(a["topic_tags"], list):
        a["topic_tags"] = []
    for f in ANALYSIS_FIELDS:
        a[f] = _no_dash(a[f]) if isinstance(a[f], str) else a[f]
    a["topic_tags"] = [_no_dash(t) for t in a["topic_tags"] if isinstance(t, str)][:5]

    atom = {
        "title": item.get("title", ""),
        "source": item.get("source", ""),
        "url": item.get("url", ""),
        "date": item.get("date", ""),
        "language": item.get("language", "en"),
        "region": item.get("region", ""),
        "medium": item.get("medium", ""),
    }
    atom.update(a)
    # Ethics fields come from the registry, never the model.
    atom["allowed_use"] = src_entry.get("allowed_use", "summarize-and-link")
    atom["risk_level"] = src_entry.get("risk_level", "green")
    atom["ethical_use_status"] = "approved" if REG.is_permitted(src_entry) else "needs-review"
    atom["citation_required"] = True
    return atom


def build_atoms(items, client, model=ATOM_MODEL, cache=None, registry=None):
    """Build atoms for every item whose source the registry permits.
    Reuses cached atoms for unchanged signals. Returns a list of atoms."""
    registry = registry if registry is not None else REG.load_registry()
    permitted = _permitted_by_source(registry)
    atoms = []
    for item in items:
        src_entry = permitted.get(item.get("source"))
        if not src_entry:
            continue  # unpermitted or unknown source: skip, never ingest
        if cache is not None:
            k = _key(item)
            hit = cache.pop(k, None)
            if isinstance(hit, dict) and hit.get("title"):
                cache[k] = hit  # move to newest
                atoms.append(hit)
                continue
        analysis = _analyze(item, client, model)
        atom = _atom_from(item, analysis, src_entry)
        atoms.append(atom)
        if cache is not None and atom.get("title"):
            cache[_key(item)] = atom
        if client is not None:
            time.sleep(0.3)  # pace the API
    return atoms


def save_atoms(atoms, path):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"generated_atoms": len(atoms), "atoms": atoms}, f, ensure_ascii=False, indent=2)
        return len(atoms)
    except Exception:
        return -1


if __name__ == "__main__":
    # Manual run: build atoms from permitted feeds, cache, and write a file.
    import argparse
    ap = argparse.ArgumentParser(description="Build Signal Atoms from permitted public sources.")
    ap.add_argument("--out", default="signal_atoms_latest.json")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--no-api", action="store_true", help="skip the model; identity-only atoms")
    args = ap.parse_args()

    client = None
    if not args.no_api and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception:
            client = None

    reg = REG.load_registry()
    items = items_from_feeds(reg, limit=args.limit)
    cache = load_cache()
    atoms = build_atoms(items, client, cache=cache, registry=reg)
    save_cache(cache)
    n = save_atoms(atoms, args.out)
    print(f"Built {n} atoms from {len(items)} items -> {args.out} "
          f"({'with' if client else 'without'} model analysis).")
