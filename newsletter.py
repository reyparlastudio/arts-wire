#!/usr/bin/env python3
"""
The Back Room: the weekly letter robot for The Arts Wire.

A separate engine from the site. Where the site is the daily firehose, this is a
single, authored, essayistic letter drawn from Rey Parla's two decades running a
studio and representing an artist. Each week the robot:

  1. picks the week's theme (a rotating bank of art-world experience topics),
  2. optionally folds in a seed note you leave in newsletter_seed.txt,
  3. asks the model to draft the letter in your first-person voice,
  4. creates it in Buttondown as a DRAFT (never sent automatically),
  5. emails YOU a [PREVIEW] of that draft to review and edit.

You then open Buttondown, make any edits, and click Publish to send it to your
subscribers. Nothing ever reaches the list without that one human tap.

House style: no em dashes anywhere, ever. Use commas, colons, periods.

Environment variables (set as repo secrets for the GitHub Action):
  ANTHROPIC_API_KEY   required to write the letter (without it, a sample is used)
  BUTTONDOWN_API_KEY  required to create the draft and send your preview
  REVIEW_EMAIL        the address that receives the [PREVIEW] (yours)
  NEWSLETTER_MODEL    optional, defaults to a strong prose model

Run:
  python newsletter.py                 draft this week's letter + email you a preview
  python newsletter.py --dry-run       write a local preview only, call no services
  python newsletter.py --theme "..."   override the week's theme
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
import urllib.error

# ----------------------------------------------------------------------------
# Identity. Rename freely: this is a working title.
# ----------------------------------------------------------------------------
NEWSLETTER_NAME = "The Back Room"
TAGLINE = "An exclusive letter from The Arts Wire, on the working life of art."
SITE_URL = "https://reyparlastudio.github.io/arts-wire/"
LINKS = [("reyparla.com", "https://reyparla.com"),
         ("parlastudios.com", "https://parlastudios.com"),
         ("The Arts Wire", SITE_URL)]

BD_BASE = "https://api.buttondown.com"
DEFAULT_MODEL = os.environ.get("NEWSLETTER_MODEL", "claude-sonnet-4-6")

# The Back Room is members-only. "premium" means it is delivered ONLY to paying
# subscribers and stays paywalled (locked) in any public archive. Free readers
# never receive it and cannot read it on the web. Set to "public" only if you
# ever deliberately want a free, openly readable issue.
EMAIL_TYPE = os.environ.get("NEWSLETTER_EMAIL_TYPE", "premium")

# ----------------------------------------------------------------------------
# The voice. This is what the model is told about who is writing and how.
# ----------------------------------------------------------------------------
PERSONA = (
    "You are ghostwriting a weekly letter in the first-person voice of Rey Parla, "
    "a Cuban-American experimental artist, filmmaker, and dramatist who has spent "
    "more than twenty years as the studio manager, business manager, and agent for "
    "the artist Jose Parla. You write from the operational inside of a serious art "
    "practice: pricing and money, the artist-gallery relationship, representation, "
    "studio systems, fabrication and logistics, museum and biennial commissions, "
    "collectors and institutions, contracts, archives, cash flow, hiring, and the "
    "emotional labor of sustaining a creative life. Your reader is a working artist "
    "or creative who would pay for candid, generous, hard-won insight they cannot "
    "get anywhere else.\n\n"
    "Voice: first person, calm, plainspoken, specific, generous, never preachy. "
    "Short paragraphs. Concrete over abstract. A point of view, not a summary.\n\n"
    "Hard rules:\n"
    "1. NEVER use em dashes. Use commas, colons, or periods.\n"
    "2. NEVER fabricate private events, figures, dollar amounts, dates, or quotes, "
    "and never put invented words or claims into the mouth of Jose Parla or any "
    "other real person. Where a true personal specific would strengthen the piece, "
    "leave a bracketed cue for the author to fill, like [personalize: a time a "
    "price negotiation taught you something], and write at most two such cues.\n"
    "3. Keep insight evergreen and defensible: principles and observations the "
    "author can stand behind, not reportage you are unsure of.\n"
    "4. Roughly 650 to 900 words. One clear through-line per letter."
)

# Rotating themes. The week number selects one, so each week is fresh and the
# bank cycles. Add, remove, or reorder freely.
THEMES = [
    "Pricing your work, and holding the line when you are pressured to discount.",
    "What a studio actually runs on: systems, not inspiration.",
    "The artist and the gallery: how the money and the trust really work.",
    "What an agent or manager actually does for an artist, day to day.",
    "Protecting an artist's time and attention as the real scarce resource.",
    "Saying no, and the hidden cost of saying yes to the wrong opportunity.",
    "The anatomy of a museum or biennial commission, from invitation to install.",
    "Cash flow for a creative practice: surviving the gaps between payments.",
    "Building a small team around an artist without losing the soul of the work.",
    "Negotiating with collectors and institutions without burning the relationship.",
    "Archives and provenance: why good records are quiet power.",
    "Fabrication and logistics: the unglamorous backbone of ambitious work.",
    "Career longevity versus the hype cycle: playing the long game.",
    "The contracts every artist should understand before they sign.",
    "Handling success, and the specific dangers that come with it.",
    "Dealer, agent, manager: who does what, and why the difference matters.",
    "When to hire, when to outsource, and when to do it yourself.",
    "Reputation and relationships: the compounding interest of an art career.",
]


def weekly_theme(today=None):
    today = today or dt.date.today()
    week = today.isocalendar()[1]
    return THEMES[week % len(THEMES)]


# ----------------------------------------------------------------------------
# Writing the letter
# ----------------------------------------------------------------------------
def _parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1:
        text = text[s:e + 1]
    return json.loads(text)


def build_prompt(theme, seed):
    extra = ""
    if seed:
        extra = ("\n\nThe author left this seed note for the week. Build the letter "
                 "around it, in his voice:\n\"\"\"\n" + seed.strip() + "\n\"\"\"")
    return (
        f"Write this week's letter. The theme is:\n\"{theme}\"{extra}\n\n"
        "Structure the body in Markdown: a brief, inviting opening; the core essay "
        "with two or three short section headers (##); and a closing called "
        "\"One thing\" that recommends a single book, show, film, idea, or practice "
        "relevant to the theme. Do not include a salutation or signature; those are "
        "added automatically.\n\n"
        "Reply with ONLY a JSON object, no prose around it, shaped exactly as:\n"
        '{"subject": "a quiet, specific subject line, no clickbait",\n'
        ' "preview": "one sentence of preview text",\n'
        ' "body": "the letter in Markdown"}'
    )


def sample_issue(theme):
    """Used when ANTHROPIC_API_KEY is absent (dry runs and previews), so you can
    see the shape of a letter without calling the model."""
    body = (
        "There is a moment in every negotiation where the room goes quiet and you "
        "are expected to lower your number. I want to talk about that moment, "
        "because how you handle it shapes a career more than any single sale.\n\n"
        "## The price is a sentence about the work\n\n"
        "A price is not a guess and it is not a hope. It is a statement about what "
        "the work is and where it sits. When you discount casually, you are not "
        "being generous, you are quietly editing that statement in front of the "
        "person least entitled to edit it. Collectors remember the number. So do "
        "institutions. The first price you accept becomes the ceiling you spend "
        "years trying to climb back from.\n\n"
        "## Holding the line is a practice, not a mood\n\n"
        "Holding the line does not mean being rigid. It means knowing, before you "
        "walk in, what you will trade and what you will not. You can give on terms, "
        "on timing, on a future commitment. You give slowly on price, and only for "
        "something real in return. [personalize: a time you held a price and were "
        "glad you did, or wish you had]\n\n"
        "The hardest part is silence. Let the number sit. The pressure you feel to "
        "fill the quiet is the same pressure the other side is counting on.\n\n"
        "## One thing\n\n"
        "Read the chapter on anchoring in any serious negotiation book this week, "
        "then notice the first number in your next three conversations. You will "
        "start to see the whole game differently."
    )
    return {"subject": "On the moment you are asked to lower your price",
            "preview": "Why the first number you accept becomes the ceiling.",
            "body": body, "theme": theme}


def generate_issue(theme, seed, model):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ! No ANTHROPIC_API_KEY: using the built-in sample letter.",
              file=sys.stderr)
        return sample_issue(theme)
    try:
        from anthropic import Anthropic
    except ImportError:
        sys.exit("Run: pip install anthropic")
    client = Anthropic()
    resp = client.messages.create(
        model=model, max_tokens=2400, system=PERSONA,
        messages=[{"role": "user", "content": build_prompt(theme, seed)}])
    data = _parse_json(resp.content[0].text)
    data["theme"] = theme
    # Belt and suspenders on the house style.
    for k in ("subject", "preview", "body"):
        data[k] = (data.get(k) or "").replace("\u2014", ", ").replace(" -- ", ", ")
    return data


# ----------------------------------------------------------------------------
# Composing the sendable letter (Markdown for Buttondown) and a viewable preview
# ----------------------------------------------------------------------------
def compose_markdown(issue, today=None):
    today = today or dt.date.today()
    date_line = today.strftime("%B %-d, %Y") if os.name != "nt" else today.strftime("%B %d, %Y")
    sig_links = "  ".join(f"[{name}]({url})" for name, url in LINKS)
    return (
        f"*{NEWSLETTER_NAME}* &middot; {date_line}\n\n"
        f"{issue['body'].strip()}\n\n"
        "---\n\n"
        "Yours,  \nRey Parla\n\n"
        f"{sig_links}\n\n"
        f"_{TAGLINE}_"
    )


def compose_html(issue, today=None):
    """A clean, intimate preview so you can see the letter as a reader would.
    Buttondown renders the Markdown itself; this is only for local viewing."""
    today = today or dt.date.today()
    date_line = today.strftime("%B %d, %Y")
    # very small Markdown-to-HTML pass for headers, bold, italics, links
    html_body = []
    for para in issue["body"].strip().split("\n\n"):
        p = para.strip()
        if p.startswith("## "):
            html_body.append(f"<h2>{p[3:].strip()}</h2>")
        else:
            p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
            p = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', p)
            p = re.sub(r"\[personalize:(.+?)\]",
                       r'<span class="cue">[personalize:\1]</span>', p)
            html_body.append(f"<p>{p}</p>")
    sig = "  ".join(f'<a href="{url}">{name}</a>' for name, url in LINKS)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{NEWSLETTER_NAME}: {issue['subject']}</title>
<style>
  body{{margin:0;background:#e4e2dd;font-family:Georgia,"Spectral",serif;color:#1a1a1a}}
  .sheet{{max-width:600px;margin:0 auto;background:#fff;padding:40px 32px 48px}}
  .kicker{{font-family:Menlo,monospace;font-size:11px;letter-spacing:.06em;
    text-transform:uppercase;color:#7a7a7a;border-bottom:1px solid #e6e6e6;padding-bottom:14px}}
  h1{{font-family:"Saira Condensed","Arial Narrow",sans-serif;font-weight:800;
    font-size:30px;line-height:1.08;margin:22px 0 4px}}
  .preview{{color:#6a6a6a;font-style:italic;font-size:16px;margin-bottom:22px}}
  h2{{font-family:"Saira Condensed","Arial Narrow",sans-serif;font-weight:700;
    font-size:20px;margin:26px 0 6px}}
  p{{font-size:17px;line-height:1.62;margin:0 0 16px}}
  a{{color:#47451a}}
  .cue{{background:#fff3cf;color:#7a5a00;padding:1px 5px;border-radius:3px;font-style:italic}}
  hr{{border:none;border-top:1px solid #e6e6e6;margin:30px 0}}
  .sig{{font-size:16px;line-height:1.6}}
  .tag{{color:#8a8a8a;font-style:italic;font-size:14px;margin-top:14px}}
</style></head><body><div class="sheet">
  <div class="kicker">{NEWSLETTER_NAME} &middot; {date_line}</div>
  <h1>{issue['subject']}</h1>
  <div class="preview">{issue['preview']}</div>
  {''.join(html_body)}
  <hr>
  <div class="sig">Yours,<br>Rey Parla<br><br>{sig}</div>
  <div class="tag">{TAGLINE}</div>
</div></body></html>"""


# ----------------------------------------------------------------------------
# Buttondown API: create a draft, then send YOU a preview. Never auto-publish.
# ----------------------------------------------------------------------------
def _bd_post(path, payload):
    key = os.environ["BUTTONDOWN_API_KEY"]
    req = urllib.request.Request(
        BD_BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Token {key}",
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise SystemExit(f"Buttondown error {e.code} on {path}: {detail[:300]}")


def create_draft(subject, body):
    # status=draft so it can NEVER queue to the whole list on its own, and
    # email_type premium so the letter reaches ONLY paying members and stays
    # paywalled in any archive. Free subscribers never receive or read it.
    data = _bd_post("/v1/emails", {"subject": subject, "body": body,
                                   "status": "draft", "email_type": EMAIL_TYPE})
    return data.get("id"), data.get("absolute_url") or data.get("web_url")


def send_preview(email_id, recipients):
    # recipients is a list of one or more email addresses
    return _bd_post(f"/v1/emails/{email_id}/send-draft", {"recipients": recipients})


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Draft the weekly letter for The Arts Wire.")
    ap.add_argument("--dry-run", action="store_true",
                    help="write a local preview only, call no external services")
    ap.add_argument("--theme", default="", help="override this week's theme")
    ap.add_argument("--no-preview", action="store_true",
                    help="create the draft but do not email yourself a preview")
    ap.add_argument("--out", default="/mnt/user-data/outputs",
                    help="where to write the local preview files")
    args = ap.parse_args()

    theme = args.theme or weekly_theme()
    seed = ""
    if os.path.exists("newsletter_seed.txt"):
        seed = open("newsletter_seed.txt", encoding="utf-8").read()
        print("  Using newsletter_seed.txt as this week's seed note.")

    print(f"Theme: {theme}")
    issue = generate_issue(theme, seed, DEFAULT_MODEL)
    md = compose_markdown(issue)

    # Always write a local preview you can open and read.
    os.makedirs(args.out, exist_ok=True)
    md_path = os.path.join(args.out, "newsletter-preview.md")
    html_path = os.path.join(args.out, "newsletter-preview.html")
    open(md_path, "w", encoding="utf-8").write(md)
    open(html_path, "w", encoding="utf-8").write(compose_html(issue))
    print(f"Wrote {md_path}\nWrote {html_path}")

    if args.dry_run or not os.environ.get("BUTTONDOWN_API_KEY"):
        if not args.dry_run:
            print("  ! No BUTTONDOWN_API_KEY: skipping draft + preview (local files only).")
        return

    email_id, url = create_draft(issue["subject"], md)
    print(f"Buttondown draft created: {url or email_id}")
    if not args.no_preview:
        # REVIEW_EMAIL may hold one address or several, separated by commas.
        recipients = [e.strip() for e in (os.environ.get("REVIEW_EMAIL") or "").split(",") if e.strip()]
        if not recipients:
            print("  ! No REVIEW_EMAIL set: draft created, but no preview sent.")
        else:
            send_preview(email_id, recipients)
            print(f"Preview sent to {', '.join(recipients)}. Look for [PREVIEW] in your inbox.")
    print("\nNext: review the preview, edit in Buttondown if needed, then click "
          "Publish to send it to your subscribers. Nothing was sent to the list.")


if __name__ == "__main__":
    main()
