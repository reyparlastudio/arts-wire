#!/usr/bin/env python3
"""
THE ARTS WIRE, automated culture review, now multilingual
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
import random
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
    "kicker": "Film &middot; Theater &middot; Art &middot; Letters &middot; Ideas",
    "pieces": "pieces",
    "review_label": "The Review: long reads, books &amp; ideas",
    "wire_label": "The Wire: today&rsquo;s news, by medium",
    "subscribe": "Subscribe &middot; $12/year",
    "art_label": "The Frame",
    "regional_label": "Latin America &amp; the Caribbean",
    "threads_label": "Threads: reading across the arts",
    "foot1": "Curated by reyparla.com &copy; Time &amp; Space Art, LLC {year} for The Arts Wire&trade;. Every title links to its original publisher; summaries are written fresh and link out to the full piece. Built with care.",
    "foot2": "built with care, run on autopilot.",
    "empty": "Nothing today.",
    "banner": "",
}


# ----------------------------------------------------------------------------
# IMAGE QUALITY STANDARD
# A weak image cheapens the page, so every lead image must clear a measurable
# "golden standard" or it is dropped and the card / section simply renders with
# no image, which reads far better than a blurry or tiny one. The gate is
# deliberately conservative: it never *guesses* an image is bad.
#   1. Obvious non-photos (logos, icons, spacers, tracking pixels, svg, gif)
#      are rejected by URL and format before anything is downloaded.
#   2. Real photos are measured in actual pixels (via Pillow); anything below
#      the minimum resolution or outside a sane shape is dropped.
#   3. If an image cannot be measured (a transient build-time hiccup), it is
#      KEPT, since a timeout is not proof of poor quality, and the browser still
#      hides anything that genuinely fails to load.
# Tune the two numbers below: raise them for a stricter wall, lower for more art.
MIN_IMG_W = 680            # px. below this a photo looks soft stretched in a card
MIN_IMG_H = 400            # px
_IMG_ASPECT_MIN = 0.62     # drop slivers / skyscrapers that crop to nothing at 3:2
_IMG_ASPECT_MAX = 2.60     # drop ultra-wide banner strips
_JUNK_IMG = re.compile(
    r"(logo|sprite|favicon|/icon|placeholder|default-|blank|spacer|avatar|"
    r"gravatar|pixel|1x1|transparent|doubleclick|feedburner|/ads?[/_-])", re.I)

try:
    from PIL import Image as _PILImage          # pillow: the pixel-level gate
except Exception:                               # noqa: BLE001
    _PILImage = None


def _img_url_ok(u):
    """Cheap pre-filter, no network: reject vector/animated formats and the
    usual logo / icon / tracking-pixel junk by extension and URL pattern."""
    u = (u or "").strip()
    if not u:
        return False
    if re.search(r"\.(svg|gif)(\?|$)", u, re.I):
        return False
    return not _JUNK_IMG.search(u)


def _dims_from_bytes(data):
    """Pixel size (w, h) from an image's bytes, or None if unreadable or Pillow
    is unavailable. Never raises."""
    if not _PILImage or not data:
        return None
    try:
        import io
        with _PILImage.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:                            # noqa: BLE001
        return None


def _meets_standard(w, h):
    """True only if the image is big enough and sanely shaped for a card."""
    if not w or not h:
        return False
    if w < MIN_IMG_W or h < MIN_IMG_H:
        return False
    return _IMG_ASPECT_MIN <= (w / float(h)) <= _IMG_ASPECT_MAX


def _probe_image_ok(url, timeout=8):
    """Fetch a card image, measure it, and decide if it clears the standard.
    Returns True (keep) or False (drop). Unmeasurable -> True (keep), so a
    transient build hiccup never strips a good image."""
    if not _img_url_ok(url):
        return False
    if not _PILImage:
        return True                              # no gauge here; browser backstops
    try:
        import urllib.request
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (The Arts Wire)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read(3_000_000)             # 3 MB is plenty to read dimensions
        dims = _dims_from_bytes(data)
        return True if dims is None else _meets_standard(*dims)
    except Exception:                            # noqa: BLE001
        return True                              # transient; keep, do not penalize


# ----------------------------------------------------------------------------
# COLLECT / DEDUPE / ENRICH  (unchanged core)
# ----------------------------------------------------------------------------
def _entry_image(e):
    """Best-effort lead image straight from the feed entry, no page fetch, so
    it stays fast for ~120 stories. Tries media:thumbnail, media:content,
    image enclosures, then the first <img> in the content/summary HTML. Returns
    an https URL or "" (cards with no image fall back cleanly)."""
    def _ok(u):
        u = (u or "").strip()
        if not u:
            return ""
        if u.startswith("http://"):          # the site is https; upgrade or it's blocked
            u = "https://" + u[len("http://"):]
        return u if (u.startswith("https://") and _img_url_ok(u)) else ""
    for th in (e.get("media_thumbnail") or []):
        u = _ok(th.get("url"))
        if u:
            return u
    for mc in (e.get("media_content") or []):
        if mc.get("medium") == "image" or str(mc.get("type", "")).startswith("image") \
                or re.search(r"\.(jpe?g|png|gif|webp)(\?|$)", mc.get("url", ""), re.I):
            u = _ok(mc.get("url"))
            if u:
                return u
    for ln in (e.get("links") or []):
        if ln.get("rel") == "enclosure" and str(ln.get("type", "")).startswith("image"):
            u = _ok(ln.get("href"))
            if u:
                return u
    blobs = [c.get("value", "") for c in (e.get("content") or [])] + [e.get("summary", "")]
    for blob in blobs:
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob or "", re.I)
        if m:
            u = _ok(m.group(1))
            if u:
                return u
    return ""


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
                    "image": _entry_image(e),
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


# Commerce and affiliate URL verticals that some arts/entertainment outlets
# (Variety, and others) pipe through their MAIN rss feed. These are shopping
# and "how to watch" posts, never arts coverage, so we drop them outright.
_JUNK_PATH = re.compile(
    r"/(shopping|commerce|deals?|coupons?|buying-guides?|best-deals|affiliate)(/|$)", re.I)

# Headline patterns for shopping round-ups and streaming/sports "how to watch"
# guides. Kept deliberately specific so genuine arts pieces survive: a film
# "now streaming," a studio "deal," or a "best films of 2026" list all stay in.
_JUNK_TITLE = re.compile(
    r"\bhow to watch\b|\bwhere to watch\b|\blive ?stream\b|\bstreaming guide\b|"
    r"\bbest deals?\b|\bdeals? on\b|\bsave on\b|\b\d{1,3}% off\b|\bcoupon\b|"
    r"\bpromo code\b|\bblack friday\b|\bcyber monday\b|\bprime day\b|"
    r"\bwhere to buy\b|\bgift guide\b|\bbest gifts?\b", re.I)


# Names and brands you have chosen to keep off the Arts Wire entirely. Matched
# as whole words, case-insensitive, in BOTH the headline and the source blurb,
# so the item is dropped before it can reach any section, lens, or the AI.
# Edit freely: add or remove a name on its own line, in quotes, with a comma.
BLOCKLIST = [
    "trump",
    "melania",
    "ivanka",
    "kushner",
]
_BLOCK = (re.compile(r"\b(?:" + "|".join(re.escape(w) for w in BLOCKLIST) + r")\b", re.I)
          if BLOCKLIST else None)


def _is_blocked(it):
    if _BLOCK is None:
        return False
    return bool(_BLOCK.search(it.get("title") or "")
                or _BLOCK.search(it.get("raw_summary") or ""))


def _is_offtopic(it):
    if _JUNK_PATH.search(it.get("link") or ""):
        return True
    return bool(_JUNK_TITLE.search(it.get("title") or ""))


def drop_offtopic(items):
    """Remove (1) shopping, affiliate, and 'how to watch' streaming guides that
    some entertainment feeds mix into their main RSS, and (2) any item naming a
    person or brand on the BLOCKLIST above. Applied to ALL feeds before
    de-duplication, so neither class ever reaches a section, a lens, or the AI."""
    return [it for it in items if not _is_offtopic(it) and not _is_blocked(it)]


def dedupe(items):
    """Drop duplicates and near-duplicates. A story is a dup of one we've kept if
    ANY of: same link; titles are >80% character-identical; their significant
    words overlap strongly (same event under a different headline); or they share
    the SAME photo and at least two key words (the cross-outlet case). Guarded so
    unrelated stories that merely share a stock/logo image are NOT merged."""
    kept, meta, seen_links = [], [], set()
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        link = it["link"].rstrip("/").lower()
        if link and link in seen_links:
            continue
        norm = _norm_title(it["title"])
        if not norm:
            continue
        toks = _sig_tokens(it["title"])
        img = (it.get("image") or "").strip().lower()
        dup = False
        for m in meta:
            if SequenceMatcher(None, norm, m["norm"]).ratio() > 0.80:
                dup = True
                break
            shared = toks & m["toks"]
            inter = len(shared)
            if inter:
                union = len(toks | m["toks"]) or 1
                jaccard = inter / union
                contain = inter / min(len(toks), len(m["toks"]))
                # Distinctive shared words: proper nouns, titles, places (5+
                # letters). Three or more in common is a strong same-story signal
                # even when outlets word the rest of the headline very differently
                # (e.g. one says "seven", another "seventh"), or pad it with extra
                # names. This is what catches cross-outlet repeats of one event.
                strong = sum(1 for w in shared if len(w) >= 5)
                if (jaccard >= 0.5
                        or (contain >= 0.55 and inter >= 4)
                        or strong >= 3
                        or (img and img == m["img"] and inter >= 2)):
                    dup = True
                    break
        if dup:
            continue
        seen_links.add(link)
        meta.append({"norm": norm, "toks": toks, "img": img})
        kept.append(it)
    return kept


def _norm_title(t):
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower()).strip()


# Common function/filler words ignored when comparing headlines, so the match
# keys on distinctive words (names, places, subjects) rather than glue.
_STOP = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "will", "would", "this", "that", "these", "those",
    "its", "it", "his", "her", "their", "our", "your", "now", "new", "more",
    "most", "than", "into", "over", "after", "before", "amid", "says", "said",
    "how", "why", "what", "who", "when", "where", "review", "reviews",
    "exclusive", "watch", "trailer", "recap", "interview", "first", "best",
    "video", "photos", "may", "about",
}


def _sig_tokens(t):
    return {w for w in _norm_title(t).split() if len(w) >= 4 and w not in _STOP}


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
            "- summary: a neutral 1-2 sentence summary IN YOUR OWN WORDS (no em dashes; use commas, colons, or periods)\n"
            "- kind: news (a timely report), note (a long feature or profile), "
            "book (a review of or essay about a specific book or author), "
            "essay (an opinion or argument)\n"
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
                # Trust dedicated review outlets, their column is their specialty.
                # Only let the AI set 'kind' for sources that default to news
                # (so a book review on a news site can still reach New Books),
                # while a dedicated book/essay/note source keeps its column.
                if b["kind"] not in REVIEW_KINDS and d.get("kind") in ALL_KINDS:
                    b["kind"] = d["kind"]
                if b["medium"] != "experimental" and d.get("medium") in media:
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
    # Show only the OTHER languages, a quiet "read in" strip. The current
    # language (e.g. English on the English edition) never labels itself, so the
    # word "English" no longer sits at the top of the English page.
    others = [c for c in langs if c != current]
    if not others:
        return ""
    parts = []
    for code in others:
        target = "index.html" if code == "en" else f"index.{code}.html"
        parts.append(f'<a class="lang" href="{target}">{T.autonym(code)}</a>')
    return ('<nav class="switch"><span class="globe" aria-hidden="true">\u25c9</span>'
            + "".join(parts) + "</nav>")


# --- Interstitial frames -----------------------------------------------------
# The Frame, extended into a gallery that runs the full length of the wire: a
# matched public-domain artwork falls BETWEEN every section, each one rhyming
# with the section that follows it. Add a category here (and to CATEGORIES) and
# it joins the rhythm automatically, the page extends as far as the content
# does. Each value is a list of search terms; one is chosen at random per build,
# so the gallery refreshes day to day. "regional" is the Latin America & the
# Caribbean block (curated by source, not a medium in CATEGORIES).
FRAME_SECTIONS = {
    "film":        ["nocturne", "moonlight", "shadow", "lantern", "night"],
    "animation":   ["caricature", "silhouette", "magic lantern", "shadow play", "puppet"],
    "games":       ["chess players", "card players", "playing cards", "dice", "game board"],
    "theater":     ["theater", "stage", "harlequin", "masquerade", "opera"],
    "dance":       ["dancer", "ballet", "dance", "Degas dancer"],
    "music":       ["musician", "lute", "violin", "concert", "song"],
    "art":         ["painting", "palette", "studio", "still life", "easel"],
    "photography": ["photograph", "daguerreotype", "portrait photograph"],
    "comics":      ["caricature", "satirical print", "Daumier", "broadsheet", "engraving"],
    "design":      ["architecture", "ornament", "interior", "facade", "pattern"],
    "gastronomy":  ["still life fruit", "banquet", "kitchen", "feast", "table"],
    "fashion":     ["costume", "dress", "gown", "textile", "embroidery"],
    "literature":  ["book", "manuscript", "letter", "library", "reading"],
    "ideas":       ["philosopher", "allegory", "scholar", "study", "manuscript"],
    "podcast":     ["conversation", "salon", "gathering", "two figures"],
    "regional":    ["Cuban", "Caribbean", "Havana", "Spanish", "Spanish colonial", "Latin American", "Mexican"],
    "artsci":      ["botanical", "anatomical", "astronomical chart", "scientific illustration", "natural history"],
    "artjustice":  ["allegory of justice", "liberty", "crowd", "procession", "laborer"],
    "review":      ["reading", "open book", "scholar", "letter", "study"],
}


# The page's section order, edit this single list to reorder the whole site.
# Keys are the medium keys from feeds.CATEGORIES, plus "artsci" / "artjustice"
# (the cross-cutting Art & Science / Art & Social Justice lenses) and "regional"
# (Latin America & the Caribbean). Any medium NOT named here is appended at the
# end automatically, so a section can never silently vanish. The Review always
# closes the page, after this sequence.
SECTION_ORDER = [
    "theater",       # Theater & Stage
    "photography",   # Photography
    "design",        # Design & Architecture
    "film",          # Film & Television
    "art",           # Visual Art
    "fashion",       # Fashion & Style
    "ideas",         # Ideas & Humanities
    "artsci",        # Art & Science  (lens)
    "artjustice",    # Art & Social Justice  (lens)
    "music",         # Music
    "podcast",       # Podcasts
    "literature",    # Literature & Poetry
    "regional",      # Latin America & the Caribbean
    "gastronomy",    # Gastronomy & Culinary Arts
    "animation",     # Animation
    "games",         # Games & Interactive
]

# Set to False to keep the fixed SECTION_ORDER above every day. True means the
# running order reorganizes itself each day, seeded by the date, so it is stable
# for the whole day and reshuffles at midnight, exactly the way the daily color
# and the design skin rotate. XPRMNTL still opens the page and The Review still
# closes it; only the sequence of sections inside The Wire is reshuffled.
SHUFFLE_SECTIONS = True

# ---------------------------------------------------------------------------
# THREADS, cross-cutting themes. The robot reads every story's title, summary,
# and tags and pulls matches into a slim themed list, so these gather strength
# from the WHOLE edition instead of needing their own (scarce) feeds. A story
# can appear both in its medium section and in a thread, the thread is a lens,
# not a duplicate. Tune the keyword lists freely; matching is whole-word and
# case-insensitive, so add distinctive words/phrases (avoid short ambiguous ones).
THEMES = [
    ("artsci", "Art &amp; Science", [
        "science", "scientific", "scientist", "physics", "biology", "biologist",
        "neuroscience", "neuroscientist", "astronomy", "astrophysics", "cosmos",
        "cosmic", "quantum", "mathematics", "mathematician", "chemistry",
        "genetics", "genome", "evolution", "evolutionary", "ecology",
        "ecological", "climate", "laboratory", "experiment", "algorithm",
        "artificial intelligence", "machine learning", "robotics", "telescope",
        "botanical", "naturalist", "anatomy", "biotech", "bioart", "bio-art",
        "natural history", "species", "fossil", "paleontology", "the brain",
    ]),
    ("artjustice", "Art &amp; Social Justice", [
        "social justice", "activism", "activist", "civil rights", "human rights",
        "racism", "racial", "anti-racist", "antiracist", "equity", "inequality",
        "feminism", "feminist", "queer", "lgbtq", "transgender", "trans rights",
        "indigenous", "decoloniz", "decolonis", "decolonial", "colonialism",
        "reparations", "immigration", "immigrant", "refugee", "migrant",
        "disability", "disabled", "accessibility", "censorship", "banned",
        "oppression", "liberation", "solidarity", "marginaliz", "marginalis",
        "apartheid", "slavery", "segregation", "abolition", "incarceration",
        "climate justice", "environmental justice", "protest",
    ]),
]


def _theme_rx(terms):
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")", re.I)


_THEME_RX = [(k, label, _theme_rx(terms)) for k, label, terms in THEMES]


def _theme_text(it):
    return " ".join([it.get("title", ""), it.get("summary", ""),
                     it.get("raw_summary", ""), " ".join(it.get("tags", []))])


# Sub-filters inside Visual Art (Painting / Sculpture / Performance / Video & New
# Media). Each art card is tagged with whichever apply; on-page chips filter the
# grid. Cards that match none stay visible only under "All". Tunable, whole-word.
_ART_FILTERS = [
    ("painting",    ["painting", "painter", "canvas", "mural", "fresco",
                     "watercolor", "watercolour", "oil paint", "portraitist"]),
    ("sculpture",   ["sculpture", "sculptor", "statue", "bronze", "marble",
                     "carving", "relief", "ceramic", "terracotta"]),
    ("performance", ["performance art", "performative", "live art", "happening",
                     "body art", "performance piece"]),
    ("video",       ["video art", "new media", "digital art", "video installation",
                     "moving image", "generative art", "virtual reality",
                     "augmented reality", "net art", "nft"]),
]
_ART_RX = [(k, _theme_rx(terms)) for k, terms in _ART_FILTERS]


def _art_filters(it):
    text = _theme_text(it)
    return " ".join(k for k, rx in _ART_RX if rx.search(text))


def _save_image(url, dest, timeout=20, enforce=True):
    """Download an image to a local file. Returns True on success, else False ,
    never raises, so a museum hiccup can't break the build (we fall back to the
    remote URL, and the <img> hides itself if even that fails in the browser).
    With enforce=True, an image that reads below the golden standard is refused
    so a tiny or oddly-shaped artwork never lands in a frame."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (The Arts Wire)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if not data or len(data) < 512:          # too small to be a real image
            return False
        if enforce:
            dims = _dims_from_bytes(data)
            if dims is not None and not _meets_standard(*dims):
                return False                     # below the golden standard
        with open(dest, "wb") as f:
            f.write(data)
        return True
    except Exception:                            # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# XPRMNTL, the experimental core. Avant-garde across time: the long-ago, the
# now, and the not-yet, written here with AI. A daily artist quote (verified,
# with attribution) sits on top; non-linear "transmissions" run beneath; and a
# short set of links points to where experimental & sound art can be heard.
# Quotes are real and sourced; transmissions are original editorial prose about
# well-documented works (no invented quotations). Expand these lists freely.
# ---------------------------------------------------------------------------
XPRMNTL_QUOTES = [
    ("I am interested in ideas, not merely in visual products.", "Marcel Duchamp", "1946"),
    ("The creative act is not performed by the artist alone.", "Marcel Duchamp", "1957"),
    ("I have nothing to say and I am saying it.", "John Cage", "1949"),
    ("In the nineteenth century, with the invention of the machine, Noise was born.", "Luigi Russolo", "1913"),
    ("We must enlarge and enrich more and more the domain of musical sounds.", "Luigi Russolo", "1913"),
    ("Imagine an eye unruled by man-made laws of perspective.", "Stan Brakhage", "1963"),
    ("Dada means nothing.", "Tristan Tzara", "1918"),
    ("Honour thy error as a hidden intention.", "Brian Eno & Peter Schmidt", "1975"),
    ("Someday artists will work with capacitors, resistors and semiconductors.", "Nam June Paik", "1965"),
    ("Listen to the sound of the earth turning.", "Yoko Ono", "1964"),
]

# (era, title, body[HTML ok], link), chronology intentionally non-linear.
XPRMNTL_TRANSMISSIONS = [
    ("1952", "Four Minutes of the Room Listening to Itself",
     "David Tudor sat at the piano and played nothing. John Cage&rsquo;s <em>4&prime;33&Prime;</em> framed the hall&rsquo;s own sounds as the music, and reopened the question of where a work begins and ends.", ""),
    ("1913", "The First Orchestra of Machines",
     "In a Milan studio, Luigi Russolo built the <em>intonarumori</em>: cranked boxes that hummed, roared and hissed. <em>The Art of Noises</em> insisted the modern ear had outgrown pure tone.", ""),
    ("the not-yet", "Toward a Generative Avant-Garde",
     "What happens when the readymade is a prompt and the studio is a model? XPRMNTL will follow artists who treat AI as a material, a collaborator and not a vending machine, and ask what is gained and what is lost.", ""),
    ("1963", "Painting Directly on Light",
     "Stan Brakhage pressed moth wings and seed-pods between strips of film for <em>Mothlight</em>, and scratched the emulsion by hand, frame by frame: cinema made by the hand, not only the lens.", ""),
    ("1917", "A Urinal Asks a Question We Never Stopped Answering",
     "Signed &lsquo;R. Mutt&rsquo; and titled <em>Fountain</em>, Duchamp&rsquo;s readymade proposed that choosing could be making: that the idea, not the hand, might be the art.", ""),
    ("1948", "Music Built From Recorded Reality",
     "In a Paris radio studio, Pierre Schaeffer spliced whistles, tops and voices into <em>musique concr&egrave;te</em>, composing with the recorded world itself, years before the synthesizer.", ""),
]

# Where to actually hear it, established, free-to-browse archives.
XPRMNTL_SOUND = [
    ("UbuWeb Sound", "https://www.ubu.com/sound/"),
    ("WFMU freeform radio", "https://www.wfmu.org/"),
    ("Internet Archive Audio", "https://archive.org/details/audio"),
    ("Bandcamp Experimental", "https://bandcamp.com/tag/experimental"),
]

# A rotating cast of figures and movements the robot draws from to compose a
# fresh transmission (or two) each day. Seeds only: the model writes original,
# factual prose about the real work, with no fabricated quotations. The cast
# leans global and includes Cuban, Caribbean and Latin American voices.
XPRMNTL_CAST = [
    ("Ana Mendieta and her earth-body Siluetas", "1973"),
    ("Wifredo Lam and the Afro-Cuban avant-garde", "1943"),
    ("H&eacute;lio Oiticica and the Tropic&aacute;lia environments", "1967"),
    ("Lygia Clark and her participatory Bichos", "1960"),
    ("Maya Deren and the trance film", "1943"),
    ("Pauline Oliveros and Deep Listening", "1989"),
    ("Hannah H&ouml;ch and Dada photomontage", "1919"),
    ("Delia Derbyshire and the BBC Radiophonic Workshop", "1963"),
    ("La Monte Young and sustained-tone minimalism", "1964"),
    ("Daphne Oram and the Oramics drawn-sound machine", "1957"),
    ("Sun Ra and the Arkestra&rsquo;s cosmic jazz", "1972"),
    ("Tony Conrad and structural film", "1966"),
    ("Meredith Monk and the extended voice", "1971"),
    ("Carolee Schneemann and the body as material", "1964"),
]


def generate_ai_transmissions(generated, n=2):
    """Compose fresh XPRMNTL transmissions for today through the model.
    Factual notes on real avant-garde work, no invented quotations, no em
    dashes. Returns a list of (era, title, body, "") or [] on any failure."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return []
    try:
        from anthropic import Anthropic
        client = Anthropic()
        idx = generated.toordinal()
        picks = [XPRMNTL_CAST[(idx + i) % len(XPRMNTL_CAST)] for i in range(n)]
        seeds = "; ".join(f"{name} (around {era})" for name, era in picks)
        prompt = (
            "You write XPRMNTL, a dispatch on avant-garde art history for an arts wire. "
            "For EACH subject below, write one short 'transmission':\n"
            f"{seeds}\n\n"
            "Each transmission is two sentences of vivid, accurate prose about the real "
            "work and why it mattered to experimental art, music, film, or performance. "
            "Rules: do NOT invent, paraphrase, or fabricate any quotation, and do not put "
            "words in anyone's mouth. Never use em dashes; use commas, colons, or periods. "
            "Give each a short evocative title (under eight words) and an era tag (a year "
            "or short epoch). If unsure of a specific detail, stay general rather than guess.\n"
            'Reply ONLY a JSON array of {"era":str,"title":str,"body":str}.'
        )
        resp = client.messages.create(model=MODEL, max_tokens=900,
                                      messages=[{"role": "user", "content": prompt}])
        out = []
        for d in _parse_arr(resp.content[0].text):
            era = str(d.get("era", "")).strip().replace("\u2014", ", ")
            title = str(d.get("title", "")).strip().replace("\u2014", ", ")
            body = str(d.get("body", "")).strip().replace("\u2014", ", ")
            if title and body:
                out.append((era or "now", title, body, ""))
        return out
    except Exception as exc:                            # noqa: BLE001
        print(f"  ! XPRMNTL transmissions skipped ({exc}).", file=sys.stderr)
        return []


def xprmntl_block(generated, live_items=None, ai_transmissions=None):
    """Render the XPRMNTL signature section: a daily verified quote, fresh AI
    transmissions ahead of the curated canon, a live experimental strip, and
    listening links. The daily quote rotates by date."""
    esc = html.escape
    q = XPRMNTL_QUOTES[generated.toordinal() % len(XPRMNTL_QUOTES)]
    quote = (f'<blockquote class="xpr-quote">&ldquo;{esc(q[0])}&rdquo;'
             f'<span class="who">{esc(q[1])} &middot; {esc(q[2])}</span></blockquote>')

    rows = list(ai_transmissions or []) + list(XPRMNTL_TRANSMISSIONS)
    stream = ""
    for row in rows:
        era, title, body = row[0], row[1], row[2]
        link = row[3] if len(row) > 3 else ""
        more = (f' <a class="xpr-link" href="{esc(link)}" target="_blank" rel="noopener">read &rarr;</a>'
                if link else "")
        stream += (f'<div class="xpr-item"><span class="xpr-era">{era}</span>'
                   f'<div class="xpr-ttl">{title}</div>'
                   f'<p class="xpr-body">{body}{more}</p></div>')

    live = ""
    if live_items:
        rowhtml = ""
        for it in live_items[:5]:
            rowhtml += (f'<a class="xpr-liveitem" href="{esc(it.get("link", "#"))}" '
                        f'target="_blank" rel="noopener">'
                        f'<span class="xpr-livesrc">{esc(it.get("source", ""))}</span>'
                        f'<span class="xpr-livettl">{esc(it.get("title", ""))}</span></a>')
        live = (f'<div class="xpr-live"><span class="xpr-livehead">On the wire now: '
                f'experimental &amp; sound art</span>{rowhtml}</div>')

    sound = "".join(
        f'<a class="xpr-snd" href="{esc(u)}" target="_blank" rel="noopener">{name} &nearr;</a>'
        for name, u in XPRMNTL_SOUND)
    return (
        '<section class="xprmntl" id="xprmntl">'
        '<div class="xpr-head"><span class="xpr-word">XPRMNTL</span>'
        '<span class="xpr-tag">Avant-garde across time: the long-ago, the now, the not-yet.'
        '</span></div>'
        f'{quote}<div class="xpr-stream">{stream}</div>{live}'
        '<div class="xpr-sound"><span class="xpr-sndhead">Listen: experimental &amp; sound art</span>'
        f'{sound}</div></section>'
    )


def render_html(items, columns, categories, generated, used_ai, *,
                lang="en", chrome=None, langs=("en",), artwork=None,
                regional_sources=(), frames=None, ai_transmissions=None):
    chrome = chrome or CHROME_EN
    esc = html.escape
    direction = "rtl" if T.is_rtl(lang) else "ltr"

    # Section-matched interstitial frames (same anatomy as the hero Frame:
    # linked, lazy-loaded, web-size image + artist / title / date / museum).
    frames = frames or {}

    def frame_block(key):
        fr = frames.get(key)
        if not fr or not fr.get("image"):
            return ""
        meta = esc(fr.get("artist", ""))
        if fr.get("date"):
            meta += f", {esc(fr['date'])}"
        return (
            f'<figure class="oneart frame-mid">'
            f'<a href="{esc(fr.get("url","#"))}" target="_blank" rel="noopener">'
            f'<img src="{esc(fr["image"])}" alt="{esc(fr.get("title",""))}" loading="lazy" '
            f'onerror="this.closest(\'.oneart\').style.display=\'none\'"></a>'
            f'<figcaption><span class="art-title">{esc(fr.get("title",""))}</span>. {meta}'
            f'<span class="art-src">{esc(fr.get("source",""))}</span></figcaption></figure>'
        )

    # "One Beautiful Thing", a daily public-domain artwork hero.
    oneart = ""
    if artwork and artwork.get("image"):
        meta = esc(artwork.get("artist", ""))
        if artwork.get("date"):
            meta += f", {esc(artwork['date'])}"
        oneart = (
            f'<div class="zone-label frame-label">{chrome.get("art_label","One Beautiful Thing")}</div>'
            f'<figure class="oneart"><a href="{esc(artwork.get("url","#"))}" target="_blank" rel="noopener">'
            f'<img src="{esc(artwork["image"])}" alt="{esc(artwork.get("title",""))}" loading="lazy" '
            f'onerror="this.closest(\'.oneart\').style.display=\'none\'"></a>'
            f'<figcaption><span class="art-title">{esc(artwork.get("title",""))}</span>. {meta}'
            f'<span class="art-src">{esc(artwork.get("source",""))}</span></figcaption></figure>'
        )

    regset = set(regional_sources or ())
    reg_items = [it for it in items if it.get("source") in regset]
    main_items = [it for it in items if it.get("source") not in regset]
    # Experimental items live only in the XPRMNTL band, never as a Wire section.
    xpr_live = [it for it in main_items if it.get("medium") == "experimental"]
    main_items = [it for it in main_items if it.get("medium") != "experimental"]

    def teaser(it):
        im = ""
        if it.get("image"):
            im = (f'<a class="t-imglink" href="{esc(it["link"])}" target="_blank" rel="noopener">'
                  f'<img class="t-img" src="{esc(it["image"])}" alt="" loading="lazy" '
                  f'onerror="this.closest(\'.t-imglink\').remove()"></a>')
        return (f'<p class="teaser">{im}<a href="{esc(it["link"])}" target="_blank" '
                f'rel="noopener">{esc(it["title"])}</a>. '
                f'{esc(_short(it.get("summary","")))}'
                f'<span class="src">{esc(it["source"])}</span></p>')

    def card(it):
        tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in it.get("tags", []))
        img = ""
        if it.get("image"):
            img = (f'<a class="card-img" href="{esc(it["link"])}" target="_blank" rel="noopener">'
                   f'<img src="{esc(it["image"])}" alt="" loading="lazy" '
                   f'onerror="this.closest(\'.card\').classList.add(\'noimg\');this.remove()"></a>')
        vsub = ""
        if it.get("medium") == "art":
            f = _art_filters(it)
            if f:
                vsub = f' data-vsub="{f}"'
        return (f'<article class="card{" has-img" if img else ""}"{vsub}>{img}'
                f'<h3><a href="{esc(it["link"])}" target="_blank" '
                f'rel="noopener">{esc(it["title"])}</a></h3>'
                f'<p class="sum">{esc(it.get("summary",""))}</p>'
                f'<div class="meta"><span class="csrc">{esc(it["source"])}</span>{tags}</div></article>')

    cols_html = ""
    for kind, label in columns:
        picks = [it for it in main_items if it["kind"] == kind]
        body = "".join(teaser(it) for it in picks) or f'<p class="empty">{chrome["empty"]}</p>'
        cols_html += f'<div class="col"><h3>{label}</h3>{body}</div>'
    review = (frame_block("review")
              + f'<div class="zone-label">{chrome["review_label"]}</div>'
              f'<section class="review">{cols_html}</section>')

    # The Latin America & the Caribbean block, rendered exactly like every other
    # category (same <h2>: Saira Condensed, ink, underlined, with a count) so it
    # reads in the same visual language as the rest of The Wire.
    regional_block = ""
    if reg_items:
        rcards = "".join(card(it) for it in reg_items)
        regional_block = (f'<section class="section"><h2>'
                          f'{chrome.get("regional_label","Latin America &amp; the Caribbean")}'
                          f'<span class="ct">{len(reg_items)}</span></h2>'
                          f'<div class="grid">{rcards}</div></section>')

    # ------------------------------------------------------------------
    # ONE ordered sequence of sections (SECTION_ORDER), with a matched frame
    # between each. Medium sections are card grids; Art & Science and Art & Social
    # Justice are cross-cutting "lens" lists drawn from the whole edition; Latin
    # America is its own card section. The Review closes the page (rendered after).
    # ------------------------------------------------------------------
    label_of = dict(categories)

    def medium_section(medium):
        group = [it for it in main_items if it["kind"] == "news" and it["medium"] == medium]
        if not group:
            return ""
        head = f'<h2>{label_of.get(medium, medium)}<span class="ct">{len(group)}</span></h2>'
        cards_html = "".join(card(it) for it in group)
        if medium == "art":
            present = set()
            for it in group:
                present |= {s for s in _art_filters(it).split() if s}
            chips = '<button class="vchip active" data-f="all">All</button>'
            for fk, flabel in (("painting", "Painting"), ("sculpture", "Sculpture"),
                               ("performance", "Performance"),
                               ("video", "Video &amp; New Media")):
                if fk in present:
                    chips += f'<button class="vchip" data-f="{fk}">{flabel}</button>'
            bar = f'<div class="vfilter">{chips}</div>' if present else ""
            return (f'<section class="section">{head}{bar}'
                    f'<div class="grid art-grid">{cards_html}</div></section>')
        return f'<section class="section">{head}<div class="grid">{cards_html}</div></section>'

    def theme_section(key):
        for k, label, rx in _THEME_RX:
            if k == key:
                picks = [it for it in items if rx.search(_theme_text(it))][:10]
                if not picks:
                    return ""
                return (f'<section class="section thread"><h2>{label}'
                        f'<span class="ct">{len(picks)}</span></h2>'
                        f'<div class="threadlist">'
                        f'{"".join(teaser(it) for it in picks)}</div></section>')
        return ""

    order = list(SECTION_ORDER)
    for m, _ in categories:                 # append any medium not explicitly ordered
        if m not in order:
            order.append(m)
    # Daily reshuffle: like the color and the skin, the running order of the
    # sections reorganizes itself each day. The seed is the date, so the order is
    # identical for every reader all day and changes at midnight. SECTION_ORDER
    # is just the starting deck. XPRMNTL, the Frame, and the Review are untouched.
    if SHUFFLE_SECTIONS:
        random.Random(generated.toordinal()).shuffle(order)

    blocks = []  # list of (frame_key, section_html)
    for key in order:
        if key in ("artsci", "artjustice"):
            sec_html = theme_section(key)
        elif key == "regional":
            sec_html = regional_block
        else:
            sec_html = medium_section(key)
        if sec_html:
            blocks.append((key, sec_html))

    wire_inner = ""
    for i, (key, block_html) in enumerate(blocks):
        if i > 0:
            wire_inner += frame_block(key)   # a frame between sections, matched to what follows
        wire_inner += block_html
    wire = (f'<div class="zone-label">{chrome["wire_label"]}</div>' + wire_inner) if wire_inner else ""

    regional = ""   # rendered inline in the sequence above
    threads = ""    # Art & Science / Art & Social Justice are now inline sections

    banner = f'<div class="banner">{chrome["banner"]}</div>' if chrome.get("banner") else ""
    mode = "Curated by Rey Parl&aacute;"
    repl = {
        "LANG": lang, "DIR": direction, "SWITCH": switcher_html(langs, lang),
        "KICKER": chrome["kicker"], "PIECES": chrome["pieces"], "SUBSCRIBE": chrome["subscribe"],
        "DATE": generated.strftime("%A %B %-d, %Y"), "MODE": mode, "TOTAL": len(items),
        "BANNER": banner, "ONEART": oneart, "REGIONAL": regional, "REVIEW": review,
        "WIRE": wire, "THREADS": threads,
        "XPRMNTL": xprmntl_block(generated, xpr_live, ai_transmissions),
        "FOOT1": chrome["foot1"].replace("{year}", str(generated.year)),
        "FOOT2": chrome["foot2"], "YEAR": generated.year,
    }
    page = TEMPLATE
    for _k, _v in repl.items():
        page = page.replace("@@" + _k + "@@", str(_v))
    return page


TEMPLATE = """<!DOCTYPE html>
<html lang="@@LANG@@" dir="@@DIR@@"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Arts Wire</title>
<meta name="theme-color" content="#0b0b0b">
<link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Arts Wire">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&family=Saira+Condensed:wght@500;600;700;800&family=Spectral:ital,wght@0,300;0,400;0,500;0,600;1,400&family=Noto+Naskh+Arabic:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root{
    --paper:#ffffff;--alt:#f7f7f6;--ink:#0b0b0b;--soft:#6f6f6f;--line:#e9e9e9;
    /* Parlá rotating accent, set per-day by the script below; olive defaults */
    --accent:#817e30;--accent-ink:#47451a;--on-accent:#ffffff;
    --phone:500px;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
  body{background:#e4e2dd;color:var(--ink);font-family:"Spectral",Georgia,serif;
    font-size:17px;line-height:1.5;-webkit-font-smoothing:antialiased}
  [dir=rtl] body{font-family:"Noto Naskh Arabic","Spectral",serif}
  a{color:inherit;text-decoration:none}
  /* the phone column, one design on every device, vertical scroll */
  .wrap{position:relative;width:100%;max-width:var(--phone);margin:0 auto;background:var(--paper);
    min-height:100vh;overflow-x:hidden;box-shadow:0 0 0 1px #00000010,0 30px 80px #00000026;padding:0 20px}

  /* language switch, slim strip */
  .switch{display:flex;flex-wrap:wrap;gap:12px;justify-content:center;padding:10px 0 0;
    font-family:"DM Mono",monospace;font-size:11px}
  .switch .lang{color:var(--soft)}
  .switch .lang:hover{color:var(--ink)}
  .switch .on{color:var(--accent-ink);font-weight:500}
  .switch .globe{color:var(--soft);font-size:12px}

  /* masthead = sticky bar + ticker */
  header.masthead{position:sticky;top:0;z-index:40;background:#ffffffec;backdrop-filter:blur(10px);
    margin:0 -20px;padding:0 14px;border-bottom:1px solid var(--line)}
  .mast-bar{display:grid;grid-template-columns:34px 1fr auto;align-items:center;height:52px}
  .mast-bar .menu{font-size:20px;line-height:1;color:var(--ink);background:none;border:none;cursor:pointer;padding:0;text-align:left}
  .navdrawer{display:none;border-top:1px solid var(--line);background:var(--paper);padding:8px 0 12px}
  .navdrawer.open{display:block}
  .navdrawer .nd-label{display:block;font-family:"Archivo",sans-serif;font-weight:700;font-size:9.5px;
    text-transform:uppercase;letter-spacing:.1em;color:var(--soft);padding:8px 2px 4px}
  .navdrawer a{display:block;font-family:"Saira Condensed",sans-serif;font-weight:600;font-size:18px;
    color:var(--ink);padding:7px 2px;letter-spacing:.01em}
  .navdrawer a:hover{color:var(--accent-ink)}
  .navdrawer .nd-div{display:block;height:1px;background:var(--line);margin:7px 0}
  .brand{font-family:"Saira Condensed",sans-serif;font-weight:800;font-size:20px;letter-spacing:.01em;
    text-align:center;white-space:nowrap;cursor:pointer}
  .brand .tm{font-size:.42em;font-weight:600;vertical-align:super;color:var(--accent-ink);margin-left:.05em}
  .sub{font-family:"Archivo",sans-serif;font-weight:800;font-size:10px;text-transform:uppercase;
    letter-spacing:.05em;color:var(--on-accent);background:var(--accent);padding:8px 11px;border-radius:2px;justify-self:end}
  .ticker{font-family:"DM Mono",monospace;font-size:10.5px;color:var(--soft);text-align:center;
    padding:7px 0;border-bottom:1px solid var(--line);background:var(--alt);margin:0 -20px;
    overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  .ticker b{font-weight:500}
  .editionline{text-align:center;font-family:"DM Mono",monospace;font-size:10.5px;color:var(--soft);
    padding:11px 0 0;line-height:1.5}
  .editionline b{color:var(--ink);font-weight:500}
  .editionline .curator{display:block;margin-top:5px;color:var(--ink);letter-spacing:.02em}

  /* utility: newsletter + search */
  .utility{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;align-items:center;padding:14px 0 2px}
  .news-btn{font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;letter-spacing:.05em;
    text-transform:uppercase;background:transparent;color:var(--accent-ink);border:1px solid var(--line);
    padding:8px 13px;border-radius:2px;cursor:pointer}
  .news-btn:hover{border-color:var(--accent-ink)}
  .searchbar{display:flex;border:1px solid var(--line);border-radius:2px;overflow:hidden;flex:1;min-width:150px}
  .searchbar input{font-family:"DM Mono",monospace;font-size:12px;padding:8px 11px;border:none;
    background:transparent;color:var(--ink);flex:1;min-width:0;outline:none}
  .searchbar button{font-family:"Archivo",sans-serif;font-weight:700;font-size:11px;border:none;
    text-transform:uppercase;letter-spacing:.05em;background:var(--accent);color:var(--on-accent);padding:0 14px;cursor:pointer}
  .search-note{width:100%;text-align:center;font-style:italic;color:var(--soft);font-size:13px;margin-top:6px;min-height:1px}
  .hidden-by-search{display:none !important}

  .banner{background:var(--alt);border:1px solid var(--line);color:var(--soft);font-style:italic;
    text-align:center;padding:10px 14px;margin:14px 0 0;font-size:13.5px}

  .anchor{display:block;height:0;scroll-margin-top:92px}
  /* ---- XPRMNTL, the experimental core (dark signature band) ---- */
  .xprmntl{background:var(--ink);color:var(--paper);margin:16px -20px 0;padding:28px 20px 30px;scroll-margin-top:92px}
  .xpr-head{border-bottom:1px solid #ffffff22;padding-bottom:14px;margin-bottom:18px}
  .xpr-word{font-family:"Saira Condensed",sans-serif;font-weight:800;font-size:clamp(40px,13vw,58px);
    letter-spacing:.07em;line-height:.9;display:block;color:var(--paper)}
  .xpr-tag{font-family:"Archivo",sans-serif;font-size:11px;letter-spacing:.04em;color:#b9b9b9;
    display:block;margin-top:10px;line-height:1.45;max-width:36ch}
  .xpr-quote{font-family:"Spectral",serif;font-style:italic;font-weight:400;font-size:21px;line-height:1.34;
    color:var(--paper);border-left:2px solid var(--accent);padding:2px 0 2px 16px;margin:6px 0 22px}
  .xpr-quote .who{display:block;font-family:"Archivo",sans-serif;font-style:normal;font-weight:700;
    font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);margin-top:10px}
  .xpr-item{padding:14px 0;border-bottom:1px solid #ffffff14}
  .xpr-item:last-child{border-bottom:none}
  .xpr-era{font-family:"DM Mono",monospace;font-size:11px;letter-spacing:.04em;color:var(--accent);text-transform:uppercase}
  .xpr-ttl{font-family:"Spectral",serif;font-weight:500;font-size:18px;line-height:1.22;margin-top:5px;color:var(--paper)}
  .xpr-body{font-family:"Spectral",serif;font-size:14.5px;line-height:1.5;color:#c4c4c4;margin-top:6px}
  .xpr-link{font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);white-space:nowrap}
  .xpr-sound{margin-top:20px;padding-top:16px;border-top:1px solid #ffffff22}
  .xpr-sndhead{display:block;font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:#b9b9b9;margin-bottom:12px}
  .xpr-snd{display:inline-block;font-family:"Archivo",sans-serif;font-weight:700;font-size:11px;letter-spacing:.03em;
    color:var(--paper);border:1px solid #ffffff3a;border-radius:2px;padding:8px 12px;margin:0 8px 8px 0}
  .xpr-snd:hover{border-color:var(--accent);color:var(--accent)}
  .xpr-live{margin-top:20px;padding-top:16px;border-top:1px solid #ffffff22}
  .xpr-livehead{display:block;font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--accent);margin-bottom:10px}
  .xpr-liveitem{display:block;padding:9px 0;border-bottom:1px solid #ffffff14;font-family:"Spectral",serif;font-size:14.5px;line-height:1.3}
  .xpr-liveitem:last-child{border-bottom:none}
  .xpr-livesrc{display:block;font-family:"DM Mono",monospace;font-size:10px;letter-spacing:.04em;text-transform:uppercase;color:#9a9a9a;margin-bottom:2px}
  .xpr-livettl{color:var(--paper)}
  .xpr-liveitem:hover .xpr-livettl{color:var(--accent)}

  /* the Frame + interstitial frames, full-bleed images */
  .oneart{margin:18px -20px 0;text-align:left}
  .oneart img{width:100%;height:auto;display:block;background:var(--alt)}
  .oneart figcaption{font-style:italic;color:var(--soft);font-size:13.5px;margin:10px 20px 0;line-height:1.45}
  .oneart .art-title{font-style:normal;font-weight:600;color:var(--ink)}
  .oneart .art-src{font-family:"Archivo",sans-serif;font-style:normal;font-weight:700;font-size:10px;
    text-transform:uppercase;letter-spacing:.06em;color:var(--accent-ink);display:block;margin-top:4px}
  .frame-mid{margin:30px -20px}

  /* zone labels: The Wire / The Review */
  .zone-label{font-family:"Saira Condensed",sans-serif;font-weight:800;text-transform:none;
    letter-spacing:-.005em;font-size:22px;color:var(--ink);border-bottom:1.5px solid var(--ink);
    padding-bottom:9px;margin:42px 0 20px;line-height:1.05}
  .frame-label{font-size:26px;border-bottom:none;margin-bottom:12px}

  /* per-medium section header */
  .section{padding:6px 0}
  h2{font-family:"Saira Condensed",sans-serif;font-weight:800;font-size:28px;line-height:1;
    letter-spacing:-.005em;border-bottom:1.5px solid var(--ink);padding-bottom:9px;margin:34px 0 18px;
    display:flex;align-items:baseline;gap:10px}
  h2 .ct{font-family:"DM Mono",monospace;font-size:12px;color:var(--soft);font-weight:400}

  /* card grid -> single-column stack */
  .grid{display:grid;grid-template-columns:1fr;gap:0}
  .card{display:flex;flex-direction:column;padding:0 0 22px;margin-bottom:22px;
    border-bottom:1px solid var(--line);background:transparent}
  .card:last-child{border-bottom:none}
  .card-img{order:1;display:block;overflow:hidden;background:var(--alt);margin:0 -20px}
  .card-img img{width:100%;height:auto;aspect-ratio:3/2;object-fit:cover;display:block}
  .card.noimg .card-img{display:none}
  .card .meta{order:2;margin:13px 0 0;padding:0;border:none;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
  .card h3{order:3;font-family:"Spectral",serif;font-weight:500;font-size:21px;line-height:1.2;
    letter-spacing:-.005em;margin-top:6px}
  .card h3 a:hover{color:var(--accent-ink)}
  .card .sum{order:4;color:#2c2c2c;font-size:15.5px;margin-top:7px;line-height:1.42}
  .csrc{font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;text-transform:uppercase;
    letter-spacing:.05em;color:var(--accent-ink)}
  .tag{font-family:"Archivo",sans-serif;font-size:9.5px;background:var(--alt);border:1px solid var(--line);
    padding:2px 7px;border-radius:20px;color:var(--soft);text-transform:uppercase;letter-spacing:.04em;font-weight:600}

  /* visual-art filter chips */
  .vfilter{display:flex;flex-wrap:wrap;gap:7px;margin:-2px 0 16px}
  .vchip{font-family:"Archivo",sans-serif;font-weight:700;font-size:10.5px;letter-spacing:.04em;
    text-transform:uppercase;padding:6px 12px;cursor:pointer;background:transparent;color:var(--soft);
    border:1px solid var(--line);border-radius:20px}
  .vchip:hover{color:var(--ink);border-color:var(--ink)}
  .vchip.active{background:var(--ink);color:var(--paper);border-color:var(--ink)}

  /* lens threads + teasers (compact list rows) */
  .threadlist{display:block}
  .teaser{padding:13px 0;border-bottom:1px solid var(--line);font-size:16px;line-height:1.32;overflow:hidden}
  .teaser:last-child{border-bottom:none}
  .teaser a{font-family:"Spectral",serif;font-weight:500;letter-spacing:-.004em}
  .teaser a:hover{color:var(--accent-ink)}
  .teaser .src{display:block;font-family:"Archivo",sans-serif;font-weight:700;font-size:9.5px;
    text-transform:uppercase;letter-spacing:.05em;color:var(--accent-ink);margin-top:4px}
  .t-imglink{float:left;margin:2px 12px 2px 0}
  .t-img{width:70px;height:70px;object-fit:cover;display:block;background:var(--alt)}
  [dir=rtl] .t-imglink{float:right;margin:2px 0 2px 12px}
  .empty{color:var(--soft);font-style:italic;padding:11px 0;font-size:14px}

  /* the review -> stacked columns */
  .review{display:block;border-top:1.5px solid var(--ink);border-bottom:1.5px solid var(--ink);padding:2px 0}
  .col{padding:14px 0;border-bottom:1px solid var(--line)}
  .col:last-child{border-bottom:none}
  .col h3{font-family:"Archivo",sans-serif;font-weight:700;font-size:11.5px;text-transform:uppercase;
    letter-spacing:.06em;color:var(--accent-ink);border-bottom:1px solid var(--ink);padding-bottom:8px;margin-bottom:4px}

  footer{text-align:left;padding:34px 0 28px;border-top:1px solid var(--line);margin-top:30px;
    color:var(--soft);font-family:"DM Mono",monospace;font-size:11px;line-height:1.7;font-style:normal}
  footer b{color:var(--ink);font-weight:500}

  /* sticky bottom CTA */
  .cta{position:sticky;bottom:0;z-index:35;display:flex;align-items:center;gap:12px;
    background:var(--accent);color:var(--on-accent);margin:24px -20px 0;
    padding:11px 16px calc(11px + env(safe-area-inset-bottom));box-shadow:0 -10px 30px #00000022}
  .cta .t{flex:1;font-family:"Spectral",serif;font-size:13.5px;line-height:1.25}
  .cta .t b{font-family:"Archivo",sans-serif;font-weight:800;letter-spacing:.02em}
  .cta a{font-family:"Archivo",sans-serif;font-weight:800;font-size:10.5px;text-transform:uppercase;
    letter-spacing:.05em;background:var(--paper);color:var(--accent-ink);padding:10px 12px;border-radius:2px;white-space:nowrap}

  .cta .totop{font-family:"Archivo",sans-serif;font-weight:800;font-size:14px;line-height:1;
    background:transparent;color:var(--on-accent);border:1px solid var(--on-accent);
    width:30px;height:30px;border-radius:50%;cursor:pointer;flex:0 0 auto;opacity:.8}
  .cta .totop:hover{opacity:1}

  /* newsletter modal */
  .aw-overlay{position:fixed;inset:0;background:#0b0b0bcc;display:none;align-items:center;justify-content:center;z-index:9999;padding:20px}
  .aw-overlay.show{display:flex}
  .aw-modal{background:var(--paper);max-width:430px;width:100%;padding:34px 26px 22px;border:1px solid var(--ink);
    box-shadow:0 22px 64px #00000055;position:relative;text-align:center}
  .aw-modal .x{position:absolute;top:9px;right:14px;font-size:24px;line-height:1;color:var(--soft);background:none;border:none;cursor:pointer}
  .aw-modal .x:hover{color:var(--accent-ink)}
  .aw-kicker{font-family:"Archivo",sans-serif;letter-spacing:.12em;text-transform:uppercase;font-size:10px;color:var(--accent-ink);font-weight:700}
  .aw-modal h2{font-family:"Saira Condensed",sans-serif;font-weight:800;font-size:30px;line-height:1;border:none;padding:0;margin:8px 0;display:block;letter-spacing:-.01em;color:var(--ink)}
  .aw-modal .lede{color:#2c2c2c;font-size:15px;margin-bottom:16px}
  .aw-form{display:flex;border:1px solid var(--ink)}
  .aw-form input{flex:1;min-width:0;font-family:"DM Mono",monospace;font-size:14px;padding:11px 12px;border:none;background:#fff;color:var(--ink);outline:none}
  .aw-form button{font-family:"Archivo",sans-serif;font-weight:800;font-size:13px;border:none;text-transform:uppercase;letter-spacing:.05em;background:var(--accent);color:var(--on-accent);padding:0 20px;cursor:pointer}
  .aw-fine{font-size:12px;color:var(--soft);font-style:italic;margin-top:12px}
  .aw-msg{font-family:"Archivo",sans-serif;font-weight:700;font-size:14px;color:var(--accent-ink);text-transform:uppercase;letter-spacing:.05em;margin-top:12px;min-height:1px}
  .aw-dismiss{display:block;margin:12px auto 0;background:none;border:none;color:var(--soft);font-size:12px;text-decoration:underline;cursor:pointer}

  /* ===================== TELETYPE skin ===================== */
  /* Monospace on dark, a teleprinter that glows in the day's    */
  /* rotating Parlá color. Same HTML; the script swaps it daily  */
  /* or by the visitor's choice. The Wire skin is the default.   */
  html[data-skin="teletype"]{--paper:#0c0c0e;--alt:#141417;--ink:#e7e4db;--soft:#8c8c8c;--line:#2a2a30}
  html[data-skin="teletype"] body{background:#070708}
  html[data-skin="teletype"] *{font-family:"DM Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace !important;border-radius:0 !important}
  html[data-skin="teletype"] body::after{content:"";position:fixed;inset:0;z-index:9998;pointer-events:none;
    background:repeating-linear-gradient(180deg,rgba(255,255,255,.04) 0 1px,transparent 1px 3px);mix-blend-mode:soft-light}
  html[data-skin="teletype"] .wrap{box-shadow:0 0 0 1px #ffffff14}
  html[data-skin="teletype"] header.masthead{background:rgba(10,10,12,.92);border-bottom-color:var(--line)}
  html[data-skin="teletype"] .brand::after{content:"_";color:var(--accent);margin-left:.12em;animation:awblink 1.1s steps(1) infinite}
  @keyframes awblink{50%{opacity:0}}
  html[data-skin="teletype"] .zone-label::before{content:"// ";color:var(--accent)}
  html[data-skin="teletype"] .section h2::before{content:"> ";color:var(--accent)}
  html[data-skin="teletype"] .xprmntl{background:#050506;border-top:1px solid var(--accent);border-bottom:1px solid var(--accent)}
  html[data-skin="teletype"] .xpr-word,
  html[data-skin="teletype"] .xpr-ttl,
  html[data-skin="teletype"] .xpr-quote,
  html[data-skin="teletype"] .xpr-snd,
  html[data-skin="teletype"] .xpr-livettl{color:var(--ink)}
  html[data-skin="teletype"] .card .sum{color:#b8b5ac}
  html[data-skin="teletype"] .aw-modal .lede{color:#c9c6bd}
  html[data-skin="teletype"] .aw-form input{background:#111114;color:var(--ink)}
  html[data-skin="teletype"] .card img,
  html[data-skin="teletype"] .oneart img,
  html[data-skin="teletype"] .t-img{border:1px solid var(--line);filter:grayscale(.35) contrast(1.04)}
  html[data-skin="teletype"] .card:hover img,
  html[data-skin="teletype"] .oneart:hover img,
  html[data-skin="teletype"] .t-img:hover{filter:none}
</style></head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="mast-bar">
      <button class="menu" id="navToggle" aria-label="Open index" aria-expanded="false">&#9776;</button>
      <span class="brand" id="brand" title="Tap to preview the next color">The Arts Wire<sup class="tm">&trade;</sup></span>
      <a class="sub" href="subscribe.html">Subscribe</a>
    </div>
    <nav class="navdrawer" id="navdrawer" aria-label="Index">
      <span class="nd-label">Index</span>
      <a href="#xprmntl">XPRMNTL</a>
      <a href="#frame">The Frame</a>
      <a href="#wire">The Wire</a>
      <a href="#review">The Review</a>
      <span class="nd-div"></span>
      <a href="subscribe.html">Subscribe</a>
      <a href="#" onclick="awOpenNews();return false;">Newsletter</a>
      <a href="#" id="skinToggle">Switch design</a>
      <span class="nd-div"></span>
      <a href="https://reyparla.com" target="_blank" rel="noopener">reyparla.com &nearr;</a>
      <a href="https://parlastudios.com" target="_blank" rel="noopener">parlastudios.com &nearr;</a>
    </nav>
    <div class="ticker">@@DATE@@ &nbsp;&middot;&nbsp; <b>World Arts in Your Language</b></div>
  </header>
  @@SWITCH@@
  <div class="editionline">@@KICKER@@<span class="curator">@@MODE@@</span></div>
  <div class="utility">
    <button class="news-btn" onclick="awOpenNews()">Newsletter</button>
    <div class="searchbar">
      <input id="awSearch" type="search" placeholder="Search this edition&hellip;" aria-label="Search this edition">
      <button onclick="awDoSearch()">Go</button>
    </div>
    <div class="search-note" id="awSearchNote"></div>
  </div>
  @@XPRMNTL@@
  @@BANNER@@
  <span class="anchor" id="frame"></span>@@ONEART@@
  @@REGIONAL@@
  <span class="anchor" id="wire"></span>@@WIRE@@
  @@THREADS@@
  <span class="anchor" id="review"></span>@@REVIEW@@
  <footer><p>@@FOOT1@@</p></footer>
  <div class="cta">
    <button class="totop" onclick="window.scrollTo({top:0,behavior:'smooth'})" aria-label="Back to top">&uarr;</button>
    <div class="t"><b>World Arts in Your Language.</b></div>
    <a href="subscribe.html">@@SUBSCRIBE@@</a>
  </div>
</div>
<div class="aw-overlay" id="awOverlay" role="dialog" aria-modal="true" aria-label="Subscribe to The Arts Wire">
  <div class="aw-modal">
    <button class="x" onclick="awCloseNews()" aria-label="Close">&times;</button>
    <div class="aw-kicker">The Arts Wire</div>
    <h2>World Arts in Your Language.</h2>
    <p class="lede">A daily dispatch of film, theater, art, books, fashion, culture, and much more.</p>
    <form class="aw-form" id="awNewsForm" action="" method="post" target="aw_sink" onsubmit="return awSubmitNews(event)">
      <input id="awNewsEmail" type="email" name="email" placeholder="Your email&hellip;" required>
      <button type="submit">Subscribe</button>
    </form>
    <p class="aw-msg" id="awNewsMsg"></p>
    <p class="aw-fine">One edition a day. Unsubscribe anytime.</p>
    <button class="aw-dismiss" onclick="awDontShow()">Don&rsquo;t show this again</button>
  </div>
</div>
<iframe name="aw_sink" style="display:none" title="signup target" tabindex="-1"></iframe>
<script>
/* ---- Daily Parlá color + design-skin rotation ---- */
(function(){
  var root=document.documentElement;
  var PAL=[{n:"Slate Blue",c:"#7593BA"},{n:"Seafoam",c:"#9FD5BD"},{n:"Marigold",c:"#E7AB48"},{n:"Olive",c:"#817E30"},{n:"Coral",c:"#F37E66"}];
  var SKINS=["wire","teletype"];
  function rgb(h){h=h.replace("#","");return [parseInt(h.substr(0,2),16),parseInt(h.substr(2,2),16),parseInt(h.substr(4,2),16)];}
  function hx(r,g,b){function f(x){x=Math.max(0,Math.min(255,Math.round(x)));return ("0"+x.toString(16)).slice(-2);}return "#"+f(r)+f(g)+f(b);}
  function store(k,v){try{localStorage.setItem(k,v);}catch(e){}}
  function load(k){try{return localStorage.getItem(k);}catch(e){return null;}}
  var skin;
  function applyColor(i){
    var p=PAL[((i%PAL.length)+PAL.length)%PAL.length],c=rgb(p.c);
    var lum=(0.299*c[0]+0.587*c[1]+0.114*c[2])/255;
    var on=lum<0.5?"#ffffff":"#111111";
    // On the dark Teletype skin links and labels glow in the bright accent;
    // on the light Wire skin they use a darkened sibling for contrast on white.
    var ink=(skin==="teletype")?p.c:hx(c[0]*0.55,c[1]*0.55,c[2]*0.55);
    var s=root.style;
    s.setProperty("--accent",p.c);s.setProperty("--accent-ink",ink);s.setProperty("--on-accent",on);
    var m=document.querySelector('meta[name=theme-color]');
    if(m){m.setAttribute("content",(skin==="teletype")?"#0b0b0d":p.c);}
  }
  var day=Math.floor(Date.now()/86400000);
  var view=day%PAL.length;
  var daySkin=SKINS[day%SKINS.length];
  function applySkin(s){skin=s;root.setAttribute("data-skin",s);applyColor(view);}
  // priority: a hard lock (used by previews) > the visitor's saved choice > the day's skin
  applySkin(root.getAttribute("data-skin-lock") || load("aw-skin") || daySkin);
  var b=document.getElementById("brand");
  if(b){b.addEventListener("click",function(){view=(view+1)%PAL.length;applyColor(view);});}
  var st=document.getElementById("skinToggle");
  if(st){st.addEventListener("click",function(e){e.preventDefault();var s=(skin==="teletype")?"wire":"teletype";store("aw-skin",s);applySkin(s);});}
})();

/* ---- Index drop-down (the hamburger) ---- */
(function(){
  var t=document.getElementById("navToggle"),d=document.getElementById("navdrawer");
  if(!t||!d){return;}
  t.addEventListener("click",function(){var o=d.classList.toggle("open");t.setAttribute("aria-expanded",o?"true":"false");});
  d.addEventListener("click",function(e){if(e.target.tagName==="A"){d.classList.remove("open");t.setAttribute("aria-expanded","false");}});
})();

if("serviceWorker" in navigator){
  if(window.top===window.self){
    window.addEventListener("load",function(){navigator.serviceWorker.register("sw.js").catch(function(){});});
  }else{
    navigator.serviceWorker.getRegistrations().then(function(rs){rs.forEach(function(r){r.unregister();});}).catch(function(){});
  }
}

var NEWSLETTER={ endpoint:"https://buttondown.com/api/emails/embed-subscribe/theartswire", emailField:"email" };
function awOpenNews(){window.location.href="subscribe.html";}
function awCloseNews(){document.getElementById("awOverlay").classList.remove("show");}
function awDontShow(){try{localStorage.setItem("aw_news_dismissed","1");}catch(e){}awCloseNews();}
function awSubmitNews(ev){
  var msg=document.getElementById("awNewsMsg");
  if(!NEWSLETTER.endpoint){ev.preventDefault();msg.textContent="Thank you. Signups open in just a moment.";return false;}
  var f=document.getElementById("awNewsForm");f.setAttribute("action",NEWSLETTER.endpoint);
  document.getElementById("awNewsEmail").setAttribute("name",NEWSLETTER.emailField);
  setTimeout(function(){msg.textContent="You\u2019re in. Check your inbox to confirm.";try{localStorage.setItem("aw_news_done","1");}catch(e){}},350);
  return true;
}
function awDoSearch(){
  var q=(document.getElementById("awSearch").value||"").trim().toLowerCase();
  var items=document.querySelectorAll(".card,.teaser");var shown=0;
  items.forEach(function(el){var hit=!q||el.textContent.toLowerCase().indexOf(q)>=0;el.classList.toggle("hidden-by-search",!hit);if(hit){shown++;}});
  document.querySelectorAll(".section,.col").forEach(function(sec){
    var its=sec.querySelectorAll(".card,.teaser");if(its.length===0){return;}
    var anyShown=Array.prototype.some.call(its,function(el){return !el.classList.contains("hidden-by-search");});
    sec.style.display=anyShown?"":"none";
  });
  document.querySelectorAll(".zone-label,.oneart,.banner,.xprmntl").forEach(function(el){el.style.display=q?"none":"";});
  var note=document.getElementById("awSearchNote");
  note.textContent=q?(shown+" "+(shown===1?"piece":"pieces")+" match \u201c"+q+"\u201d"):"";
}
(function(){
  var s=document.getElementById("awSearch");
  if(s){s.addEventListener("input",awDoSearch);s.addEventListener("keydown",function(e){if(e.key==="Enter"){e.preventDefault();awDoSearch();}});}
  try{var done=localStorage.getItem("aw_news_done");var dismissed=localStorage.getItem("aw_news_dismissed");if(!done&&!dismissed){setTimeout(awOpenNews,3500);}}catch(e){}
  var ov=document.getElementById("awOverlay");
  if(ov){ov.addEventListener("click",function(e){if(e.target===ov){awCloseNews();}});}
  document.addEventListener("keydown",function(e){if(e.key==="Escape"){awCloseNews();}});
})();
document.querySelectorAll(".vfilter").forEach(function(bar){
  var grid=bar.parentElement.querySelector(".art-grid");if(!grid){return;}
  bar.addEventListener("click",function(e){
    var bb=e.target.closest(".vchip");if(!bb){return;}
    bar.querySelectorAll(".vchip").forEach(function(c){c.classList.remove("active");});
    bb.classList.add("active");var f=bb.getAttribute("data-f");
    grid.querySelectorAll(".card").forEach(function(card){var subs=(card.getAttribute("data-vsub")||"").split(" ");card.style.display=(f==="all"||subs.indexOf(f)>=0)?"":"none";});
  });
});
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
        ("Tania Bruguera y el arte de conducta, de La Habana a Nueva York", "Rialta", "art", "news",
         "Una mirada al arte político cubano dentro y fuera de la isla.", ["cuba", "arte"]),
        ("El nuevo pop caribeño: identidad y reinvención", "Remezcla", "music", "news",
         "Cómo una generación caribeña rehace el sonido del pop global.", ["caribbean", "music"]),
        ("A Modular-Synth Composer Maps the Sound of Melting Ice", "The Quietus", "experimental", "news",
         "Field recordings from a retreating glacier become a slow, generative drone work.", ["sound", "drone"]),
        ("Inside a New Generation of Tape-Loop Improvisers", "Fact Magazine", "experimental", "news",
         "A scene built on degraded magnetic tape finds beauty in hiss, wow and flutter.", ["tape", "improv"]),
        ("AI as Bandmate: Live Coders Trade Sets With a Model", "XLR8R", "experimental", "news",
         "At a Berlin night, performers improvised against a system writing patches in real time.", ["live-coding", "ai"]),
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
    ap = argparse.ArgumentParser(description="The Arts Wire: multilingual culture review")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--langs", default="", help="comma list, e.g. es,fr,ja,ar")
    ap.add_argument("--hours", type=int, default=48)
    ap.add_argument("--max-items", type=int, default=120)
    ap.add_argument("--no-art", action="store_true", help="skip the daily artwork hero")
    ap.add_argument("--out", default=OUTPUT_DIR)
    args = ap.parse_args()

    try:
        from feeds import FEEDS, CATEGORIES, COLUMNS, REGIONAL_SOURCES
    except ImportError:
        from feeds import FEEDS, CATEGORIES, COLUMNS
        REGIONAL_SOURCES = set()
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
        before = len(raw)
        raw = drop_offtopic(raw)
        if before - len(raw):
            print(f"\nFiltered {before - len(raw)} off-topic or blocked item(s).")
        items = dedupe(raw)[:args.max_items]
        print(f"\n{len(raw)} -> {len(items)} after de-duplication.")
        items, used_ai = ai_enrich(items, media)
        print(f"AI: {'on' if used_ai else 'off (source blurbs)'}.")

        # Image quality gate: measure each lead image and drop any that fails
        # the golden standard, so that card (and its teaser thumb) runs clean
        # with no image rather than a weak one. Only the final, surviving
        # stories are probed, so it stays fast.
        seen, dropped = {}, 0
        for it in items:
            u = (it.get("image") or "").strip()
            if not u.startswith("http"):
                continue
            ok = seen.get(u)
            if ok is None:
                ok = _probe_image_ok(u)
                seen[u] = ok
            if not ok:
                it["image"] = ""
                dropped += 1
        if dropped:
            print(f"Image gate: dropped {dropped} sub-standard image(s); "
                  f"those cards run clean.")

    # "One Beautiful Thing", daily public-domain artwork hero.
    art = None
    frames = {}
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
            # Demo only: reuse the sample so frame placement is visible offline.
            frames = {k: {**art, "title": f"Sample frame ({k})"}
                      for k in FRAME_SECTIONS}
        else:
            import artwork as A
            art = A.fetch_artwork()
            print(f"Artwork: {('featured: ' + art['source']) if art else 'none reachable; hero skipped'}.")
            # The gallery: one matched, web-size, public-domain work per framed
            # section, deduped against the hero and one another.
            used = {art["image"]} if art and art.get("image") else set()
            for key, terms in FRAME_SECTIONS.items():
                fr = A.fetch_section_frame(random.choice(terms), exclude=used)
                if fr and fr.get("image"):
                    frames[key] = fr
                    used.add(fr["image"])
            print(f"Frames: {len(frames)} section-matched works"
                  f"{(': ' + ', '.join(frames)) if frames else ' (none reachable)'}.")

            # Self-host the artwork so the browser never depends on a museum CDN
            # (which has 404'd before). Any failure falls back to the remote URL.
            adir = os.path.join(args.out, "assets")
            os.makedirs(adir, exist_ok=True)
            if art and str(art.get("image", "")).startswith("http"):
                if _save_image(art["image"], os.path.join(adir, "frame-hero.jpg")):
                    art["image"] = "assets/frame-hero.jpg"
            saved = 0
            for key, fr in frames.items():
                if str(fr.get("image", "")).startswith("http"):
                    if _save_image(fr["image"], os.path.join(adir, f"frame-{key}.jpg")):
                        fr["image"] = f"assets/frame-{key}.jpg"
                        saved += 1
            print(f"Self-hosted artwork: hero + {saved} frames saved locally.")

    def write(page, lang):
        name = "index.html" if lang == "en" else f"index.{lang}.html"
        for path in ((os.path.join(args.out, name),) +
                     ((os.path.join(args.out, f"arts-wire-{now:%Y-%m-%d}.html"),) if lang == "en" else ())):
            with open(path, "w", encoding="utf-8") as f:
                f.write(page)

    # Fresh XPRMNTL transmissions, composed once per build (English, shared by
    # every edition). Falls back to the curated canon when AI is unavailable.
    xpr_ai = [] if args.demo else generate_ai_transmissions(now)

    # English
    write(render_html(items, COLUMNS, CATEGORIES, now, used_ai, lang="en",
                       chrome=CHROME_EN, langs=langs, artwork=art, frames=frames,
                       regional_sources=REGIONAL_SOURCES, ai_transmissions=xpr_ai), "en")

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
                              chrome=tchrome, langs=langs, artwork=art, frames=frames,
                              regional_sources=REGIONAL_SOURCES, ai_transmissions=xpr_ai), lang)
            print(f"  translated -> {lang}")
        except Exception as exc:                        # noqa: BLE001
            print(f"  ! {lang} failed: {exc}", file=sys.stderr)

    print(f"\nDone. Open: {os.path.join(args.out, 'index.html')}")


if __name__ == "__main__":
    main()
