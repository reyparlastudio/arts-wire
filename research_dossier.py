#!/usr/bin/env python3
"""
research_dossier.py  —  many atoms into one weekly brief
=========================================================
A research dossier is the private brief a human or a careful model writes the
Back Room from. It gathers the week's relevant Signal Atoms on a chosen theme,
sets them against their historical echo using taxonomy.json, and produces a
structured synthesis with every source attached.

The dossier is NEVER published. It is the research layer. The Back Room letter
is written from it (see backroom_signal.py), in Rey's voice, by hand or with
the model, always with Rey's review before anything sends.

Fail-soft: with no API key, the dossier is still assembled from the atoms'
own fields, so the pipeline always produces something a human can use.

House style: no em dashes anywhere.
"""

import datetime as dt
import json
import os
import re
import time

DOSSIER_MODEL = os.environ.get("AW_DOSSIER_MODEL", "claude-sonnet-4-6")
DOSSIER_DIR = os.environ.get("AW_DOSSIER_DIR", "research_dossiers")
TAXONOMY_PATH = os.environ.get("AW_TAXONOMY", "taxonomy.json")


def _no_dash(s):
    return s.replace("\u2014", ", ").replace(" -- ", ", ") if isinstance(s, str) else s


def _slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s or "theme")[:60]


def load_taxonomy(path=TAXONOMY_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _parse_obj(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return {}
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return {}


def _words(s):
    return set(re.findall(r"[a-z]{3,}", (s or "").lower()))


def select_atoms(atoms, theme, tags=None, limit=14):
    """Rank atoms by simple relevance to the theme and optional tags."""
    theme_words = _words(theme) | set(t.lower() for t in (tags or []))
    scored = []
    for a in atoms:
        hay = " ".join([
            a.get("title", ""), " ".join(a.get("topic_tags", [])),
            a.get("now_signal", ""), a.get("psychological_need", ""),
            a.get("emotional_signal", ""), a.get("medium", ""),
        ])
        score = len(theme_words & _words(hay))
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    chosen = [a for s, a in scored if s > 0][:limit]
    if not chosen:  # nothing matched: fall back to the freshest atoms
        chosen = atoms[:limit]
    return chosen


def now_before_for(theme, taxonomy):
    """Find the best now-versus-before pairing for a theme, or a gentle default."""
    tw = _words(theme)
    best, best_score = None, 0
    for pair in taxonomy.get("now_versus_before", []):
        score = len(tw & _words(pair.get("now", "")))
        if score > best_score:
            best, best_score = pair, score
    return best or {"now": theme, "before": []}


def _sources_of(atoms):
    seen, out = set(), []
    for a in atoms:
        key = (a.get("source", ""), a.get("url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": a.get("title", ""), "source": a.get("source", ""), "url": a.get("url", "")})
    return out


def _scaffold(theme, atoms, pairing):
    """A deterministic dossier built only from atom fields. Used with no API."""
    pulse = []
    for a in atoms[:8]:
        line = a.get("now_signal") or a.get("title")
        if line:
            pulse.append({"point": _no_dash(line), "source": a.get("source", ""), "url": a.get("url", "")})
    lineage = next((a.get("historical_lineage") for a in atoms if a.get("historical_lineage")), "")
    need = next((a.get("psychological_need") for a in atoms if a.get("psychological_need")), "")
    studio = next((a.get("studio_consequence") for a in atoms if a.get("studio_consequence")), "")
    money = next((a.get("money_consequence") for a in atoms if a.get("money_consequence")), "")
    contact = next((a.get("human_contact_consequence") for a in atoms if a.get("human_contact_consequence")), "")
    return {
        "subject_statement": f"This week, the field is circling {theme}.",
        "pulse": pulse,
        "lineage": _no_dash(lineage) or "; ".join(pairing.get("before", [])),
        "human_need": _no_dash(need),
        "studio_consequence": _no_dash(studio),
        "money_consequence": _no_dash(money),
        "contact_consequence": _no_dash(contact),
        "candidate_moves": [
            "Name the one change this week makes to how you work.",
            "Write the question this raises for your own practice.",
            "Find one peer to talk it through with.",
        ],
    }


def _build_prompt(theme, atoms, pairing):
    compact = [{
        "title": a.get("title", ""), "source": a.get("source", ""), "url": a.get("url", ""),
        "now": a.get("now_signal", ""), "before": a.get("before_signal", ""),
        "lineage": a.get("historical_lineage", ""), "need": a.get("psychological_need", ""),
        "emotion": a.get("emotional_signal", ""), "studio": a.get("studio_consequence", ""),
        "money": a.get("money_consequence", ""), "contact": a.get("human_contact_consequence", ""),
    } for a in atoms]
    return (
        "You are the research desk for The Arts Wire. Build a research dossier for "
        "one weekly Back Room theme, using ONLY the atoms provided. Synthesize in "
        "your own words. Cite by source. Never copy source wording, never fabricate, "
        "no em dashes. Mark any claim the atoms do not support as "
        '"unverified, do not publish".\n\n'
        f"THEME: {theme}\n"
        f"HISTORICAL ECHO TO CONSIDER: now {pairing.get('now','')}, "
        f"before {', '.join(pairing.get('before', [])) or 'choose from the atoms'}\n\n"
        f"ATOMS (json): {json.dumps(compact, ensure_ascii=False)}\n\n"
        "Return ONLY a JSON object shaped exactly as:\n"
        '{"subject_statement": "one paragraph naming the week\'s real subject",\n'
        ' "pulse": [{"point": "what artists are saying now, in your words", "source": "name", "url": "link"}],\n'
        ' "lineage": "the strongest historical echo and why it illuminates now",\n'
        ' "human_need": "the need underneath",\n'
        ' "studio_consequence": "what a working artist should understand",\n'
        ' "money_consequence": "who profits, who pays, who is exposed",\n'
        ' "contact_consequence": "what this means for connection and collaboration",\n'
        ' "candidate_moves": ["three practical One Move This Week options"]}'
    )


def build_dossier(theme, atoms, client=None, model=DOSSIER_MODEL, taxonomy=None, tags=None):
    """Assemble a dossier for a theme. Uses the model to synthesize when a client
    is given; otherwise builds a scaffold from the atoms. Always attaches sources."""
    taxonomy = taxonomy if taxonomy is not None else load_taxonomy()
    chosen = select_atoms(atoms, theme, tags=tags)
    pairing = now_before_for(theme, taxonomy)

    body = None
    if client is not None and chosen:
        prompt = _build_prompt(theme, chosen, pairing)
        delay = 2.0
        for n in range(3):
            try:
                resp = client.messages.create(
                    model=model, max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}])
                body = _parse_obj(resp.content[0].text)
                if body:
                    break
            except Exception:
                time.sleep(delay)
                delay *= 2
    if not body:
        body = _scaffold(theme, chosen, pairing)

    # belt and suspenders on house style
    for k in ("subject_statement", "lineage", "human_need", "studio_consequence",
              "money_consequence", "contact_consequence"):
        if isinstance(body.get(k), str):
            body[k] = _no_dash(body[k])

    dossier = {
        "theme": theme,
        "generated": dt.date.today().isoformat(),
        "now_versus_before": pairing,
        "atom_count": len(chosen),
    }
    dossier.update(body)
    dossier["sources"] = _sources_of(chosen)
    return dossier


def save_dossier(dossier, directory=DOSSIER_DIR):
    try:
        os.makedirs(directory, exist_ok=True)
        name = f"{dossier.get('generated', dt.date.today().isoformat())}-{_slug(dossier.get('theme',''))}.json"
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dossier, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return ""


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build a weekly research dossier from Signal Atoms.")
    ap.add_argument("--theme", required=True)
    ap.add_argument("--atoms", default="signal_atoms_latest.json", help="atoms file from signal_atoms.py")
    ap.add_argument("--no-api", action="store_true")
    args = ap.parse_args()

    try:
        with open(args.atoms, encoding="utf-8") as f:
            data = json.load(f)
        atoms = data.get("atoms", data) if isinstance(data, dict) else data
    except Exception:
        atoms = []

    client = None
    if not args.no_api and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception:
            client = None

    dossier = build_dossier(args.theme, atoms, client=client)
    path = save_dossier(dossier)
    print(f"Dossier on '{args.theme}' built from {dossier['atom_count']} atoms -> {path or 'not saved'}")
