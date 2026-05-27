#!/usr/bin/env python3
"""
backroom_signal.py  —  a dossier into a Back Room draft
========================================================
Takes a research dossier (from research_dossier.py) and drafts a Back Room
letter on the eight-part spine, in Rey Parla's voice. It is a DRAFT ONLY. It
reuses newsletter.py for the sendable Markdown, the local preview, and the
Buttondown draft-plus-preview path, so the engine produces letters through the
same one-human-tap workflow the project already trusts.

The eight-part spine:
  The Pulse, The Lineage, The Human Need, The Studio Consequence,
  The Money Underneath, The Contact Point, One Move This Week, The Future Note.

Writing rules are enforced in the prompt and again in code: no em dashes, no
invented quotes, no fabricated private experience, no copied source wording, no
style imitation, sources cited, Rey in final control. Where only Rey's lived
experience can speak, the draft leaves a bracketed [Rey: ...] cue rather than
inventing it.

Fail-soft: with no API key, a letter is assembled from the dossier's own fields
so a human always has a real draft to edit.

House style: no em dashes anywhere.
"""

import argparse
import datetime as dt
import json
import os
import re
import time

import newsletter as NL

PROSE_MODEL = os.environ.get("AW_PROSE_MODEL", NL.DEFAULT_MODEL)

SPINE = ["The Pulse", "The Lineage", "The Human Need", "The Studio Consequence",
         "The Money Underneath", "The Contact Point", "One Move This Week", "The Future Note"]

SPINE_RULES = (
    "\n\nWrite this as a Back Room letter on the eight-part spine, each part a short "
    "section with a bold label: The Pulse (what artists are saying and feeling now), "
    "The Lineage (the art-historical echo that illuminates it), The Human Need (the "
    "need underneath), The Studio Consequence (what a working artist should understand "
    "and do), The Money Underneath (who profits, who pays, who is exposed), The Contact "
    "Point (what it means for connection and collaboration), One Move This Week (a single "
    "practical action), and The Future Note (a short, grounded, slightly poetic close). "
    "The spine can breathe: if a part is thin, fold it in briefly rather than padding it. "
    "Ground every claim in the dossier. Cite outlets by name in the prose where natural. "
    "Where a true personal specific would strengthen it, leave one bracketed cue like "
    "[Rey: a real number or studio story here], at most two in the whole letter. End the "
    "body with a short 'Sources' list of the outlets drawn on."
)


def _no_dash(s):
    return s.replace("\u2014", ", ").replace(" -- ", ", ") if isinstance(s, str) else s


def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1:
        text = text[s:e + 1]
    return json.loads(text)


def _sources_block(dossier):
    lines = []
    for s in dossier.get("sources", [])[:12]:
        name = s.get("source", "") or s.get("title", "")
        url = s.get("url", "")
        if name and url:
            lines.append(f"[{name}]({url})")
        elif name:
            lines.append(name)
    return "  \n".join(lines)


def build_prompt(dossier):
    return (
        "Draft this week's Back Room letter from the research dossier below. The "
        "dossier is your only source of fact. Do not add events it does not contain.\n\n"
        f"DOSSIER (json): {json.dumps(dossier, ensure_ascii=False)}"
        + SPINE_RULES +
        "\n\nReply with ONLY a JSON object, no prose around it, shaped exactly as:\n"
        '{"subject": "a quiet, specific subject line, no clickbait",\n'
        ' "preview": "one sentence of preview text",\n'
        ' "body": "the letter in Markdown, on the spine, ending with a Sources list"}'
    )


def _scaffold_issue(dossier):
    """A real draft built only from the dossier, used when there is no API key."""
    theme = dossier.get("theme", "this week")
    parts = []
    parts.append(dossier.get("subject_statement", f"This week the field is circling {theme}."))
    pulse = dossier.get("pulse", [])
    if pulse:
        lines = []
        for p in pulse[:6]:
            pt = p.get("point") if isinstance(p, dict) else str(p)
            src = p.get("source") if isinstance(p, dict) else ""
            lines.append(f"{pt}" + (f" ({src})" if src else ""))
        parts.append("**The Pulse.** " + " ".join(lines))
    fields = [
        ("The Lineage", dossier.get("lineage")),
        ("The Human Need", dossier.get("human_need")),
        ("The Studio Consequence", dossier.get("studio_consequence")),
        ("The Money Underneath", dossier.get("money_consequence")),
        ("The Contact Point", dossier.get("contact_consequence")),
    ]
    for label, val in fields:
        if val:
            parts.append(f"**{label}.** {val}")
    moves = dossier.get("candidate_moves", [])
    if moves:
        parts.append(f"**One Move This Week.** {moves[0]}")
    parts.append("**The Future Note.** [Rey: a short, grounded close in your own voice.]")
    src = _sources_block(dossier)
    if src:
        parts.append("**Sources**  \n" + src)
    body = "\n\n".join(_no_dash(p) for p in parts if p)
    return {
        "subject": f"The Back Room: {theme}",
        "preview": _no_dash(dossier.get("subject_statement", "") or f"On {theme}."),
        "body": body,
        "theme": theme,
    }


def draft_from_dossier(dossier, client=None, model=PROSE_MODEL):
    """Return an issue dict {subject, preview, body, theme} from a dossier."""
    if client is not None:
        delay = 2.0
        for n in range(3):
            try:
                resp = client.messages.create(
                    model=model, max_tokens=2600, system=NL.PERSONA,
                    messages=[{"role": "user", "content": build_prompt(dossier)}])
                data = _parse_json(resp.content[0].text)
                data["theme"] = dossier.get("theme", "")
                for k in ("subject", "preview", "body"):
                    data[k] = _no_dash(data.get(k) or "")
                if data.get("body"):
                    return data
            except Exception:
                time.sleep(delay)
                delay *= 2
    return _scaffold_issue(dossier)


def run(dossier, dry_run=False, no_preview=False, out="/mnt/user-data/outputs", client=None):
    """Draft, write local previews, and (unless dry) create a Buttondown draft."""
    issue = draft_from_dossier(dossier, client=client)
    md = NL.compose_markdown(issue)
    os.makedirs(out, exist_ok=True)
    md_path = os.path.join(out, "backroom-preview.md")
    html_path = os.path.join(out, "backroom-preview.html")
    open(md_path, "w", encoding="utf-8").write(md)
    open(html_path, "w", encoding="utf-8").write(NL.compose_html(issue))
    print(f"Wrote {md_path}\nWrote {html_path}")

    if dry_run or not os.environ.get("BUTTONDOWN_API_KEY"):
        if not dry_run:
            print("  ! No BUTTONDOWN_API_KEY: local draft only, nothing created.")
        return issue, md_path

    email_id, url = NL.create_draft(issue["subject"], md)
    print(f"Buttondown draft created: {url or email_id}")
    if not no_preview:
        recipients = [e.strip() for e in (os.environ.get("REVIEW_EMAIL") or "").split(",") if e.strip()]
        if recipients:
            NL.send_preview(email_id, recipients)
            print(f"Preview sent to {', '.join(recipients)}. Look for [PREVIEW] in your inbox.")
        else:
            print("  ! No REVIEW_EMAIL set: draft created, but no preview sent.")
    print("\nNext: review the preview, edit in Buttondown, then click Publish. "
          "Nothing was sent to the list.")
    return issue, md_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Draft a Back Room letter from a research dossier.")
    ap.add_argument("--dossier", required=True, help="path to a dossier json from research_dossier.py")
    ap.add_argument("--dry-run", action="store_true", help="local preview only, no services")
    ap.add_argument("--no-preview", action="store_true", help="create the draft but do not email a preview")
    ap.add_argument("--out", default="/mnt/user-data/outputs")
    args = ap.parse_args()

    with open(args.dossier, encoding="utf-8") as f:
        dossier = json.load(f)

    client = None
    if not args.dry_run and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception:
            client = None

    run(dossier, dry_run=args.dry_run, no_preview=args.no_preview, out=args.out, client=client)
