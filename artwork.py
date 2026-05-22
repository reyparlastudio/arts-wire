"""
artwork.py — "One Beautiful Thing"
==================================
Fetches a single public-domain masterwork (image + credit) to feature at the
top of each edition, à la Google Arts & Culture. Sources are open-access museum
APIs that explicitly release these images into the public domain:

  - The Metropolitan Museum of Art (no key required)
  - The Art Institute of Chicago (fallback, no key required)

We only ever use works flagged public-domain, and we always credit and link
back to the museum. If both sources are unreachable, we return None and the
edition simply omits the hero image (never crashes).
"""

import json
import random
import urllib.request
from urllib.parse import quote

MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/"
AIC_ART = "https://api.artic.edu/api/v1/artworks"
AIC_IIIF = "https://www.artic.edu/iiif/2/{id}/full/1200,/0/default.jpg"

# Rotating query terms so the featured work varies day to day.
TERMS = ["painting", "portrait", "landscape", "still life", "drawing",
         "sculpture", "watercolor", "print", "sunset", "garden", "sea"]
UA = {"User-Agent": "TheArtsWire/1.0 (daily public-domain artwork feature)"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _from_met(timeout):
    data = _get(f"{MET_SEARCH}?hasImages=true&q={random.choice(TERMS)}", timeout)
    ids = data.get("objectIDs") or []
    random.shuffle(ids)
    for oid in ids[:12]:
        try:
            o = _get(f"{MET_OBJECT}{oid}", timeout)
        except Exception:
            continue
        img = o.get("primaryImage") or o.get("primaryImageSmall")
        if o.get("isPublicDomain") and img:
            return {
                "title": o.get("title") or "Untitled",
                "artist": o.get("artistDisplayName") or "Unknown",
                "date": o.get("objectDate") or "",
                "image": img,
                "credit": o.get("creditLine") or "",
                "source": "The Met",
                "url": o.get("objectURL") or "https://www.metmuseum.org/",
            }
    return None


def _from_aic(timeout):
    fields = "id,title,artist_display,date_display,image_id,is_public_domain"
    page = random.randint(1, 80)
    data = _get(f"{AIC_ART}?fields={fields}&limit=50&page={page}", timeout)
    rows = [d for d in data.get("data", [])
            if d.get("is_public_domain") and d.get("image_id")]
    if not rows:
        return None
    d = random.choice(rows)
    return {
        "title": d.get("title") or "Untitled",
        "artist": (d.get("artist_display") or "Unknown").split("\n")[0],
        "date": d.get("date_display") or "",
        "image": AIC_IIIF.format(id=d["image_id"]),
        "credit": "Art Institute of Chicago",
        "source": "Art Institute of Chicago",
        "url": f"https://www.artic.edu/artworks/{d['id']}",
    }


def fetch_artwork(timeout=20):
    """Return one public-domain artwork dict, or None if unreachable."""
    for source in (_from_met, _from_aic):
        try:
            art = source(timeout)
            if art:
                return art
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Section-matched frames — "the gallery that runs the length of the wire."
# Given a theme (a search term that rhymes with a section), return ONE
# public-domain work, web-size, from whichever open-access museum answers
# first. The three sources are tried in RANDOM order, so the gallery draws on
# collections around the world and never leans on a single institution.
# All three are open access, no API key required.
# ---------------------------------------------------------------------------
AIC_SEARCH   = "https://api.artic.edu/api/v1/artworks/search"
AIC_IIIF_WEB = "https://www.artic.edu/iiif/2/{id}/full/843,/0/default.jpg"   # web-size
CMA_ART      = "https://openaccess-api.clevelandart.org/api/artworks/"       # Cleveland, CC0


def _met_match(theme, timeout, exclude):
    data = _get(f"{MET_SEARCH}?hasImages=true&q={quote(theme)}", timeout)
    ids = data.get("objectIDs") or []
    random.shuffle(ids)
    for oid in ids[:24]:
        try:
            o = _get(f"{MET_OBJECT}{oid}", timeout)
        except Exception:
            continue
        img = o.get("primaryImageSmall") or o.get("primaryImage")   # web-size first
        if o.get("isPublicDomain") and img and img not in exclude:
            return {
                "title": o.get("title") or "Untitled",
                "artist": o.get("artistDisplayName") or "Unknown",
                "date": o.get("objectDate") or "",
                "image": img,
                "source": "The Met",
                "url": o.get("objectURL") or "https://www.metmuseum.org/",
            }
    return None


def _aic_match(theme, timeout, exclude):
    fields = "id,title,artist_display,date_display,image_id,is_public_domain"
    url = f"{AIC_SEARCH}?q={quote(theme)}&fields={fields}&limit=40"
    rows = [d for d in (_get(url, timeout).get("data") or [])
            if d.get("is_public_domain") and d.get("image_id")]
    random.shuffle(rows)
    for d in rows:
        img = AIC_IIIF_WEB.format(id=d["image_id"])
        if img in exclude:
            continue
        return {
            "title": d.get("title") or "Untitled",
            "artist": (d.get("artist_display") or "Unknown").split("\n")[0],
            "date": d.get("date_display") or "",
            "image": img,
            "source": "Art Institute of Chicago",
            "url": f"https://www.artic.edu/artworks/{d['id']}",
        }
    return None


def _cma_match(theme, timeout, exclude):
    url = f"{CMA_ART}?q={quote(theme)}&cc0=1&has_image=1&limit=40"
    rows = _get(url, timeout).get("data") or []
    random.shuffle(rows)
    for d in rows:
        img = ((d.get("images") or {}).get("web") or {}).get("url")
        if not img or img in exclude:
            continue
        creators = d.get("creators") or []
        artist = (creators[0].get("description") if creators else "") or "Unknown"
        return {
            "title": d.get("title") or "Untitled",
            "artist": artist.split(" (")[0],           # trim trailing life-dates
            "date": d.get("creation_date") or "",
            "image": img,
            "source": "Cleveland Museum of Art",
            "url": d.get("url") or "https://www.clevelandart.org/art/collection",
        }
    return None


def fetch_section_frame(theme, timeout=15, exclude=None):
    """One public-domain work matched to `theme`, web-size, or None.

    Tries the Met, the Art Institute of Chicago, and the Cleveland Museum of
    Art (all open access, no key) in random order. `exclude` is a set of image
    URLs already used on the page, so frames never repeat. Never raises.
    """
    exclude = exclude or set()
    sources = [_met_match, _aic_match, _cma_match]
    random.shuffle(sources)
    for src in sources:
        try:
            art = src(theme, timeout, exclude)
            if art and art.get("image"):
                return art
        except Exception:
            continue
    return None
