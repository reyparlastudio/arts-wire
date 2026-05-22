#!/usr/bin/env python3
"""
THE ARTS WIRE  —  automated culture review, now multilingual
=============================================================
Two zones (The Review + The Wire), assembled daily, and publishable in any
language: pass --langs and the robot writes one page per language, with a
language switcher and automatic right-to-left layout where needed.

  python aggregator.py --demo --langs es,ar   # sample, incl. a full Spanish
                                                 edition and an RTL Arabic one
  python aggregator.py --langs es,fr,ja,ar      # live, AI translates each
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
from difflib import SequenceMatcher

try:
    import feedparser
except ImportError:
    feedparser = None

import translate as T

MODEL = "claude-haiku-4-5-20251001"
OUTPUT_DIR = "output"
REVIEW_KINDS = ("note", "book", "essay")
ALL_KINDS = REVIEW_KINDS + ("news",)

CHROME_EN = {
    "kicker": "Film &middot; Theater &middot; Art &middot; Letters &middot; Ideas &middot; Worldwide",
    "pieces": "pieces",
    "review_label": "The Review &mdash; long reads, books &amp; ideas",
    "wire_label": "The Wire &mdash; today&rsquo;s news, by medium",
    "subscribe": "Subscribe &middot; $1/month",
    "art_label": "The Frame",
    "foot1": "Curated and assembled by reyparla.com & automatically by Time & Space Art, LLC for The Arts Wire. Every title links to its original publisher; summaries are written fresh and link out to the full piece.",
    "foot2": "built with care, run on autopilot.",
    "empty": "Nothing today.",
    "banner": "",
}


# ----------------------------------------------------------------------------
# COLLECT / DEDUPE / ENRICH  (unchanged core)
# ----------------------------------------------------------------------------
def collect(feeds, hours):
    import socket
    socket.setdefaulttimeout(20)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    items, health = [], []
    for name, url, medium, kind in feeds:
        try:
            parsed = feedparser.parse(url)
            if getattr(parsed, "bozo", 0) and not parsed.entries:
                raise ValueError(parsed.get("bozo_exception", "unreadable feed"))
            count = 0
            for e in parsed.entries:
                published = _entry_date(e)
                if published and published < cutoff:
                    continue
                items.append({
                    "title": _clean(e.get("title", "")).strip(),
                    "link": e.get("link", "").strip(), "source": name,
                    "medium": medium, "kind": kind,
                    "published": published.isoformat() if published else "",
                    "raw_summary": _clean(e.get("summary", ""))[:400]})
                count += 1
            health.append((name, "ok", count))
        except Exception as exc:                        # noqa: BLE001
            health.append((name, f"skipped: {str(exc)[:55]}", 0))
    return items, health


def _entry_date(entry):
    import time
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return dt.datetime.fromtimestamp(time.mktime(t), tz=dt.timezone.utc)
    return None


def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def dedupe(items):
    seen, kept = set(), []
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        link = it["link"].rstrip("/").lower()
        if link and link in seen:
            continue
        norm = _norm_title(it["title"])
        if not norm or any(
                SequenceMatcher(None, norm, _norm_title(k["title"])).ratio() > 0.85
                for k in kept):
            continue
        seen.add(link)
        kept.append(it)
    return kept


def _norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


def ai_enrich(items, media, batch_size=10):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        for it in items:
            it["summary"] = it["raw_summary"] or "(Open the piece for details.)"
            it["tags"] = [it["medium"]]
        return items, False
    from anthropic import Anthropic
    client = Anthropic()
    media_list = ", ".join(media)
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        payload = [{"i": i, "title": b["title"], "source": b["source"],
                    "blurb": b["raw_summary"]} for i, b in enumerate(batch)]
        prompt = (
            "You are an arts-and-letters desk editor. For each item return:\n"
            "- summary: a neutral 1-2 sentence summary IN YOUR OWN WORDS\n"
            "- kind: one of note, book, essay, news\n"
            f"- medium: one of [{media_list}]\n- tags: 2-4 short lowercase tags\n"
            'Reply ONLY a JSON array of {"i":int,"summary":str,"kind":str,'
            '"medium":str,"tags":[str]}.\n\n' + json.dumps(payload, ensure_ascii=False))
        try:
            resp = client.messages.create(model=MODEL, max_tokens=1800,
                                          messages=[{"role": "user", "content": prompt}])
            by_i = {d["i"]: d for d in _parse_arr(resp.content[0].text)}
            for i, b in enumerate(batch):
                d = by_i.get(i, {})
                b["summary"] = d.get("summary") or b["raw_summary"] or "(Open the piece.)"
                b["tags"] = d.get("tags") or [b["medium"]]
                if d.get("kind") in ALL_KINDS:
                    b["kind"] = d["kind"]
                if d.get("medium") in media:
                    b["medium"] = d["medium"]
        except Exception as exc:                        # noqa: BLE001
            print(f"  ! AI batch failed ({exc}).", file=sys.stderr)
            for b in batch:
                b["summary"] = b["raw_summary"] or "(Open the piece.)"
                b["tags"] = [b["medium"]]
    return items, True


def _parse_arr(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("["), text.rfind("]")
    return json.loads(text[s:e + 1]) if s != -1 else []


# ----------------------------------------------------------------------------
# RENDER  (now i18n-aware)
# ----------------------------------------------------------------------------
def _short(text, n=170):
    text = text or ""
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "\u2026"


def switcher_html(langs, current):
    parts = []
    for code in langs:
        target = "index.html" if code == "en" else f"index.{code}.html"
        cls = "lang on" if code == current else "lang"
        parts.append(f'<a class="{cls}" href="{target}">{T.autonym(code)}</a>')
    return '<nav class="switch">' + "".join(parts) + "</nav>"


def render_html(items, columns, categories, generated, used_ai, *,
                lang="en", chrome=None, langs=("en",), artwork=None):
    chrome = chrome or CHROME_EN
    esc = html.escape
    direction = "rtl" if T.is_rtl(lang) else "ltr"

    # "One Beautiful Thing" — a daily public-domain artwork hero.
    oneart = ""
    if artwork and artwork.get("image"):
        meta = esc(artwork.get("artist", ""))
        if artwork.get("date"):
            meta += f", {esc(artwork['date'])}"
        oneart = (
            f'<div class="zone-label">{chrome.get("art_label","One Beautiful Thing")}</div>'
            f'<figure class="oneart"><a href="{esc(artwork.get("url","#"))}" target="_blank" rel="noopener">'
            f'<img src="{esc(artwork["image"])}" alt="{esc(artwork.get("title",""))}" loading="lazy"></a>'
            f'<figcaption><span class="art-title">{esc(artwork.get("title",""))}</span> &mdash; {meta}'
            f'<span class="art-src">{esc(artwork.get("source",""))}</span></figcaption></figure>'
        )

    def teaser(it):
        return (f'<p class="teaser"><a href="{esc(it["link"])}" target="_blank" '
                f'rel="noopener">{esc(it["title"])}</a> &mdash; '
                f'{esc(_short(it.get("summary","")))}'
                f'<span class="src">{esc(it["source"])}</span></p>')

    def card(it):
        tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in it.get("tags", []))
        return (f'<article class="card"><h3><a href="{esc(it["link"])}" target="_blank" '
                f'rel="noopener">{esc(it["title"])}</a></h3>'
                f'<p class="sum">{esc(it.get("summary",""))}</p>'
                f'<div class="meta"><span class="csrc">{esc(it["source"])}</span>{tags}</div></article>')

    cols_html = ""
    for kind, label in columns:
        picks = [it for it in items if it["kind"] == kind]
        body = "".join(teaser(it) for it in picks) or f'<p class="empty">{chrome["empty"]}</p>'
        cols_html += f'<div class="col"><h3>{label}</h3>{body}</div>'
    review = (f'<div class="zone-label">{chrome["review_label"]}</div>'
              f'<section class="review">{cols_html}</section>')

    wire_inner = ""
    for medium, label in categories:
        group = [it for it in items if it["kind"] == "news" and it["medium"] == medium]
        if not group:
            continue
        wire_inner += (f'<section class="section"><h2>{label}<span class="ct">'
                       f'{len(group)}</span></h2><div class="grid">'
                       + "".join(card(it) for it in group) + "</div></section>")
    wire = (f'<div class="zone-label">{chrome["wire_label"]}</div>' + wire_inner) if wire_inner else ""

    banner = f'<div class="banner">{chrome["banner"]}</div>' if chrome.get("banner") else ""
    mode = "AI-curated edition" if used_ai else "source-summary edition"
    return TEMPLATE.format(
        lang=lang, dir=direction, switch=switcher_html(langs, lang),
        kicker=chrome["kicker"], pieces=chrome["pieces"], subscribe=chrome["subscribe"],
        date=generated.strftime("%Y-%m-%d"), mode=mode, total=len(items),
        banner=banner, oneart=oneart, review=review, wire=wire,
        foot1=chrome["foot1"], foot2=chrome["foot2"], year=generated.year)


TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}" dir="{dir}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Arts Wire</title>
<meta name="theme-color" content="#191512">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Arts Wire">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,900&family=Newsreader:ital,opsz@0,6..72;1,6..72&family=Noto+Naskh+Arabic:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root{{--paper:#f5efe3;--ink:#191512;--muted:#6f6253;--line:#d8cdb8;--accent:#b8412a;--gold:#9a7b32}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--paper);color:var(--ink);font-family:"Newsreader",Georgia,serif;
    font-size:18px;line-height:1.5;
    background-image:radial-gradient(#00000008 1px,transparent 1px);background-size:4px 4px}}
  [dir=rtl] body,[dir=rtl]{{font-family:"Noto Naskh Arabic","Newsreader",serif}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:1140px;margin:0 auto;padding:0 22px}}
  .switch{{display:flex;flex-wrap:wrap;gap:14px;justify-content:center;padding:12px 0 0;
    font-family:"Fraunces";font-size:13px}}
  .switch .lang{{color:var(--muted);border-bottom:1px solid transparent;padding-bottom:2px}}
  .switch .lang:hover{{color:var(--ink)}}
  .switch .on{{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}}

  header.masthead{{text-align:center;padding:14px 0 20px;border-bottom:3px double var(--ink)}}
  .kicker{{font-family:"Fraunces";letter-spacing:.34em;text-transform:uppercase;
    font-size:12px;color:var(--accent);font-weight:600}}
  h1.title{{font-family:"Fraunces";font-weight:900;font-size:clamp(46px,9vw,94px);
    line-height:.92;letter-spacing:-.02em;margin:6px 0 12px}}
  .sub{{display:inline-block;font-family:"Fraunces";font-weight:600;font-size:14px;
    background:var(--accent);color:var(--paper);padding:7px 18px;border-radius:2px;margin-bottom:12px}}
  .dateline{{display:flex;justify-content:center;gap:18px;flex-wrap:wrap;font-style:italic;
    color:var(--muted);font-size:15px;border-top:1px solid var(--line);
    border-bottom:1px solid var(--line);padding:8px 0;max-width:700px;margin:0 auto}}
  .dateline b{{font-style:normal;font-weight:600;color:var(--ink)}}
  .banner{{background:#00000008;border:1px solid var(--line);color:var(--muted);
    font-style:italic;text-align:center;padding:10px 16px;margin:16px 0 0;font-size:14px}}
  .oneart{{margin:6px auto 0;max-width:760px;text-align:center}}
  .oneart img{{width:100%;height:auto;border:1px solid var(--line);
    box-shadow:0 14px 40px #00000022;background:var(--paper)}}
  .oneart figcaption{{font-style:italic;color:var(--muted);font-size:14.5px;margin-top:10px}}
  .oneart .art-title{{font-style:normal;font-weight:600;color:var(--ink)}}
  .oneart .art-src{{font-family:"Fraunces";font-style:normal;font-weight:600;font-size:10.5px;
    text-transform:uppercase;letter-spacing:.06em;color:var(--gold);display:block;margin-top:4px}}

  .zone-label{{font-family:"Fraunces";font-weight:600;text-transform:uppercase;
    letter-spacing:.16em;font-size:13px;color:var(--accent);text-align:center;
    margin:36px 0 14px;position:relative}}
  .zone-label::before,.zone-label::after{{content:"";position:absolute;top:50%;width:24%;
    height:1px;background:var(--line)}}
  .zone-label::before{{left:0}} .zone-label::after{{right:0}}

  .review{{display:grid;grid-template-columns:repeat(3,1fr);border-top:2px solid var(--ink);
    border-bottom:2px solid var(--ink)}}
  .col{{padding:18px 22px;border-right:1px solid var(--line)}}
  .col:last-child{{border-right:none}}
  [dir=rtl] .col{{border-right:none;border-left:1px solid var(--line)}}
  [dir=rtl] .col:last-child{{border-left:none}}
  .col h3{{font-family:"Fraunces";font-weight:600;font-size:16px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--accent);padding-bottom:8px;margin-bottom:6px;
    border-bottom:2px solid var(--accent)}}
  .teaser{{padding:11px 0;border-bottom:1px dotted var(--line);font-size:16.5px;line-height:1.42}}
  .teaser:last-child{{border-bottom:none}}
  .teaser a{{font-family:"Fraunces";font-weight:600}}
  .teaser a:hover{{color:var(--accent)}}
  .teaser .src{{display:block;font-family:"Fraunces";font-weight:600;font-size:10.5px;
    text-transform:uppercase;letter-spacing:.06em;color:var(--gold);margin-top:3px}}
  .empty{{color:var(--muted);font-style:italic;padding:11px 0;font-size:15px}}

  .section{{padding:24px 0}}
  h2{{font-family:"Fraunces";font-weight:600;font-size:28px;letter-spacing:-.01em;
    border-bottom:2px solid var(--ink);padding-bottom:8px;margin-bottom:20px;
    display:flex;align-items:baseline;gap:12px}}
  h2 .ct{{font-family:"Newsreader";font-size:14px;font-style:italic;color:var(--muted)}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:18px}}
  .card{{background:var(--paper);border:1px solid var(--line);padding:18px 18px 16px;
    display:flex;flex-direction:column;gap:8px}}
  .card h3{{font-family:"Fraunces";font-weight:600;font-size:20px;line-height:1.18}}
  .card h3 a:hover{{color:var(--accent)}}
  .sum{{color:#3a322a;font-size:16px}}
  .meta{{margin-top:auto;display:flex;flex-wrap:wrap;align-items:center;gap:8px;
    padding-top:6px;border-top:1px solid var(--line)}}
  .csrc{{font-family:"Fraunces";font-weight:600;font-size:11.5px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--gold)}}
  .tag{{font-size:11px;background:#00000008;border:1px solid var(--line);padding:2px 8px;
    border-radius:20px;color:var(--muted)}}

  footer{{text-align:center;padding:40px 0 60px;border-top:3px double var(--ink);
    margin-top:24px;color:var(--muted);font-style:italic;font-size:14px}}
  footer b{{font-style:normal}}
  @media (max-width:760px){{.review{{grid-template-columns:1fr}}
    .col{{border-right:none;border-bottom:1px solid var(--line)}}.col:last-child{{border-bottom:none}}}}
</style></head>
<body>
<div class="wrap">
  {switch}
  <header class="masthead">
    <div class="kicker">{kicker}</div>
    <h1 class="title">The Arts Wire</h1>
    <a class="sub" href="subscribe.html">{subscribe}</a>
    <div class="dateline"><span>{date}</span><span><b>{total}</b> {pieces}</span><span>{mode}</span></div>
  </header>
  {banner}
  {oneart}
  {review}
  {wire}
  <footer><p>{foot1}</p><p>&copy; {year} &middot; {foot2}</p></footer>
</div>
<script>
if("serviceWorker" in navigator){{
  if(window.top===window.self){{
    window.addEventListener("load",function(){{navigator.serviceWorker.register("sw.js").catch(function(){{}});}});
  }}else{{
    navigator.serviceWorker.getRegistrations().then(function(rs){{rs.forEach(function(r){{r.unregister();}});}}).catch(function(){{}});
  }}
}}
</script>
</body></html>"""


# ----------------------------------------------------------------------------
# DEMO
# ----------------------------------------------------------------------------
def demo_items():
    rows = [
        ("Does Chalmers's 'Hard Problem' of Consciousness Still Hold Up?", "Aeon", "ideas", "note",
         "A wide-ranging look at whether subjective experience remains a genuine puzzle or a confusion of categories.", ["consciousness", "philosophy"]),
        ("The Quiet Revolution in How We Write Narrative History", "The Paris Review", "literature", "note",
         "On a generation of historians trading grand theory for texture, scene, and the lives of ordinary people.", ["history", "craft"]),
        ("James Schuyler, Reconsidered", "New York Review of Books", "literature", "book",
         "A new collected edition prompts a fresh appraisal of the New York School poet's offhand, luminous attention.", ["poetry", "retrospective"]),
        ("A Major Biography Reframes a Forgotten Modernist", "Los Angeles Review of Books", "literature", "book",
         "The critic argues the painter's late work has been badly misread for half a century.", ["biography", "modernism"]),
        ("Before Lithium: A Strange History of Treating Mania", "The Point", "ideas", "essay",
         "How psychiatry stumbled toward a treatment it still does not fully understand.", ["medicine", "history"]),
        ("The Trouble With Teaching 'AI Literacy' on Campus", "Public Books", "ideas", "essay",
         "An argument that universities are mistaking tool training for the deeper work of judgment.", ["education", "ai"]),
        ("Cannes Unveils a Competition Heavy on First-Time Directors", "Variety", "film", "news",
         "Eleven debut filmmakers will compete for the Palme d'Or, the festival's most in a decade.", ["festival", "cannes"]),
        ("National Theatre Names a New Artistic Director", "The Stage (UK)", "theater", "news",
         "The London institution appoints a director known for large-scale revivals.", ["leadership", "uk"]),
        ("A Landmark Restaging Revives a Forgotten Ballet", "Dance Magazine", "dance", "news",
         "Reconstructed from notation and old film, the work returns to the stage after eighty years.", ["ballet", "revival"]),
        ("A Quietly Radical Album Reshapes a Veteran's Sound", "Pitchfork", "music", "news",
         "The record trades arena polish for something rawer and more searching.", ["album", "review"]),
        ("Record Auction Night Signals Renewed Collector Confidence", "The Art Newspaper", "art", "news",
         "A strong evening sale suggests the high end of the market is stabilizing.", ["market", "auction"]),
        ("A Striking New Museum Opens on a Reclaimed Waterfront", "Dezeen", "design", "news",
         "The architects turned a derelict pier into a daylit hall for contemporary work.", ["architecture", "museum"]),
    ]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    return [{"title": t, "link": "https://example.com", "source": s, "medium": m,
             "kind": k, "published": now, "raw_summary": sm, "summary": sm, "tags": tg}
            for t, s, m, k, sm, tg in rows]


def demo_translation(lang, items, columns, categories):
    """Offline sample translations so --demo can show real translated pages.
    Returns (titems, tchrome, tcolumns, tcategories) or None if unsupported."""
    from demo_i18n import DEMO_I18N
    pack = DEMO_I18N.get(lang)
    if not pack:
        return None
    chrome = dict(CHROME_EN); chrome.update(pack["chrome"])
    tcols = [(k, pack["columns"].get(k, v)) for k, v in columns]
    tcats = [(k, pack["categories"].get(k, v)) for k, v in categories]
    titems = []
    for it in items:
        copy = dict(it)
        tr = pack.get("items", {}).get(it["title"])
        if tr:
            copy["title"], copy["summary"], copy["tags"] = tr["title"], tr["summary"], tr["tags"]
        titems.append(copy)
    return titems, chrome, tcols, tcats


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="The Arts Wire — multilingual culture review")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--langs", default="", help="comma list, e.g. es,fr,ja,ar")
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--max-items", type=int, default=120)
    ap.add_argument("--no-art", action="store_true", help="skip the daily artwork hero")
    ap.add_argument("--out", default=OUTPUT_DIR)
    args = ap.parse_args()

    from feeds import FEEDS, CATEGORIES, COLUMNS
    media = [m for m, _ in CATEGORIES]
    os.makedirs(args.out, exist_ok=True)

    # Make the published site self-contained: copy PWA assets + subscribe page.
    here = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(here, "static")
    if os.path.isdir(static_dir):
        for root, _, files in os.walk(static_dir):
            rel = os.path.relpath(root, static_dir)
            dest = args.out if rel == "." else os.path.join(args.out, rel)
            os.makedirs(dest, exist_ok=True)
            for fn in files:
                shutil.copy2(os.path.join(root, fn), os.path.join(dest, fn))
    sub = os.path.join(here, "subscribe.html")
    if os.path.isfile(sub):
        shutil.copy2(sub, os.path.join(args.out, "subscribe.html"))

    now = dt.datetime.now()
    extra = [c.strip() for c in args.langs.split(",") if c.strip()]
    langs = ["en"] + extra

    if args.demo:
        items, used_ai = demo_items(), False
        print("DEMO mode.")
    else:
        if feedparser is None:
            sys.exit("Run: pip install -r requirements.txt")
        print(f"Reading {len(FEEDS)} sources (last {args.hours}h)...")
        raw, health = collect(FEEDS, args.hours)
        print("\nFeed health:")
        for name, status, n in health:
            print(f"  {'OK ' if status=='ok' else '-- '}{name:<28} {n if status=='ok' else status}")
        items = dedupe(raw)[:args.max_items]
        print(f"\n{len(raw)} -> {len(items)} after de-duplication.")
        items, used_ai = ai_enrich(items, media)
        print(f"AI: {'on' if used_ai else 'off (source blurbs)'}.")

    # "One Beautiful Thing" — daily public-domain artwork hero.
    art = None
    if not args.no_art:
        if args.demo:
            import base64
            img_uri = "demo-art.jpg"
            p = os.path.join(here, "static", "demo-art.jpg")
            if os.path.isfile(p):
                with open(p, "rb") as f:
                    img_uri = "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
            art = {"image": img_uri, "title": "Sample image",
                   "artist": "Live editions feature a real public-domain masterwork",
                   "date": "", "source": "Met / Art Institute (open access)", "url": "#"}
        else:
            import artwork as A
            art = A.fetch_artwork()
            print(f"Artwork: {('featured — ' + art['source']) if art else 'none reachable; hero skipped'}.")

    def write(page, lang):
        name = "index.html" if lang == "en" else f"index.{lang}.html"
        for path in ((os.path.join(args.out, name),) +
                     ((os.path.join(args.out, f"arts-wire-{now:%Y-%m-%d}.html"),) if lang == "en" else ())):
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)

    # English
    write(render_html(items, COLUMNS, CATEGORIES, now, used_ai, lang="en",
                       chrome=CHROME_EN, langs=langs, artwork=art), "en")

    # Other languages
    client = None
    if extra and not args.demo and os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic
        client = Anthropic()
    for lang in extra:
        try:
            if args.demo:
                tr = demo_translation(lang, items, COLUMNS, CATEGORIES)
                if tr is None:
                    print(f"  ({lang}: no offline sample; skipped in demo)"); continue
                titems, tchrome, tcols, tcats = tr
            elif client:
                titems, tchrome, tcols, tcats = T.translate_edition(
                    items, {k: v for k, v in CHROME_EN.items()}, COLUMNS, CATEGORIES,
                    lang, client, MODEL)
            else:
                print(f"  ({lang}: needs ANTHROPIC_API_KEY; skipped)"); continue
            write(render_html(titems, tcols, tcats, now, used_ai, lang=lang,
                              chrome=tchrome, langs=langs, artwork=art), lang)
            print(f"  translated -> {lang}")
        except Exception as exc:                        # noqa: BLE001
            print(f"  ! {lang} failed: {exc}", file=sys.stderr)

    print(f"\nDone. Open: {os.path.join(args.out, 'index.html')}")


if __name__ == "__main__":
    main()
