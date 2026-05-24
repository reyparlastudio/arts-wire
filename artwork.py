"""
artwork.py — "One Beautiful Thing"
==================================
Fetches a single public-domain masterwork (image + credit) to feature at the
top of each edition, à la Google Arts & Culture. Sources are open-access museum
APIs that explicitly release these images into the public domain:

  - The Metropolitan Museum of Art (no key)
  - The Art Institute of Chicago (no key)
  - The Cleveland Museum of Art (no key, CC0)
  - The Victoria and Albert Museum, London (no key)
  - SMK, the National Gallery of Denmark (no key, CC0)
  - Smithsonian Open Access (free key: SI_API_KEY, CC0)
  - Rijksmuseum, Amsterdam (free key: RIJKS_API_KEY)
  - Europeana, pan-European incl. Spain (free key: EUROPEANA_API_KEY, open only)
  - Harvard Art Museums (free key: HARVARD_API_KEY)
  - The New York Public Library Digital Collections (token: NYPL_TOKEN, CC0)

Keyed sources are skipped automatically when their environment variable is not
set, so the feed always works with whatever is available. We favor works flagged
public-domain or openly licensed, always credit and link back, and never crash:
any unreachable source is simply skipped, and the next one is tried.
"""

import json
import os
import random
import urllib.request
from urllib.parse import quote

MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/"
AIC_ART = "https://api.artic.edu/api/v1/artworks"
AIC_IIIF = "https://www.artic.edu/iiif/2/{id}/full/843,/0/default.jpg"

# Rotating query terms so the featured work varies day to day.
TERMS = ["painting", "portrait", "landscape", "still life", "drawing",
         "sculpture", "watercolor", "print", "sunset", "garden", "sea"]
UA = {"User-Agent": "TheArtsWire/1.0 (daily public-domain artwork feature)"}


def _get(url, timeout=20, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
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
    """Return one public-domain artwork dict for the hero, or None.

    Prefers the Met and the Art Institute (which carry a credit line), then
    widens to the full open-access pool so the hero varies too.
    """
    funcs = [_from_met, _from_aic]
    random.shuffle(funcs)
    for source in funcs:
        try:
            art = source(timeout)
            if art:
                return art
        except Exception:
            continue
    term = random.choice(TERMS)
    pool = _enabled_sources()
    random.shuffle(pool)
    for src in pool:
        try:
            art = src(term, timeout, set())
            if art and art.get("image"):
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
VAM_SEARCH   = "https://api.vam.ac.uk/v2/objects/search"                     # V&A, no key
VAM_IIIF     = "https://framemark.vam.ac.uk/collections/{id}/full/843,/0/default.jpg"
SMK_SEARCH   = "https://api.smk.dk/api/v1/art/search/"                       # SMK, CC0, no key
SI_SEARCH    = "https://api.si.edu/openaccess/api/v1.0/search"               # Smithsonian (key)
RIJKS_SEARCH = "https://www.rijksmuseum.nl/api/en/collection"                # Rijksmuseum (key)
EUR_SEARCH   = "https://api.europeana.eu/record/v2/search.json"              # Europeana (key)
HARV_SEARCH  = "https://api.harvardartmuseums.org/object"                    # Harvard (key)
NYPL_SEARCH  = "https://api.repo.nypl.org/api/v2/items/search"               # NYPL (token)


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


def _vam_match(theme, timeout, exclude):
    url = f"{VAM_SEARCH}?q={quote(theme)}&images_exist=1&page_size=40"
    recs = _get(url, timeout).get("records") or []
    random.shuffle(recs)
    for d in recs:
        iid = d.get("_primaryImageId")
        if not iid:
            continue
        img = VAM_IIIF.format(id=iid)
        if img in exclude:
            continue
        maker = (d.get("_primaryMaker") or {}).get("name") or "Unknown"
        return {
            "title": d.get("_primaryTitle") or "Untitled",
            "artist": maker,
            "date": d.get("_primaryDate") or "",
            "image": img,
            "source": "Victoria and Albert Museum",
            "url": f"https://collections.vam.ac.uk/item/{d.get('systemNumber', '')}",
        }
    return None


def _smk_match(theme, timeout, exclude):
    # CC0, public-domain works that have an image.
    flt = "%5Bhas_image%3Atrue%5D%2C%5Bpublic_domain%3Atrue%5D"
    url = f"{SMK_SEARCH}?keys={quote(theme)}&filters={flt}&offset=0&rows=40"
    items = _get(url, timeout).get("items") or []
    random.shuffle(items)
    for d in items:
        img = d.get("image_thumbnail") or d.get("image_native")
        if not img or img in exclude:
            continue
        titles = d.get("titles") or []
        title = (titles[0].get("title") if titles else "") or "Untitled"
        prod = d.get("production") or []
        artist = (prod[0].get("creator") if prod else "") or "Unknown"
        date = ""
        pd = d.get("production_date") or []
        if pd and isinstance(pd[0], dict):
            date = (pd[0].get("start") or "")[:4]
        return {
            "title": title, "artist": artist, "date": date, "image": img,
            "source": "SMK (National Gallery of Denmark)",
            "url": f"https://open.smk.dk/en/artwork/image/{d.get('object_number', '')}",
        }
    return None


def _si_match(theme, timeout, exclude):
    key = os.environ.get("SI_API_KEY")
    if not key:
        return None
    url = f"{SI_SEARCH}?api_key={key}&q={quote(theme)}&rows=60"
    rows = ((_get(url, timeout).get("response") or {}).get("rows")) or []
    random.shuffle(rows)
    for d in rows:
        c = d.get("content") or {}
        dnr = c.get("descriptiveNonRepeating") or {}
        media = ((dnr.get("online_media") or {}).get("media")) or []
        img = None
        for m in media:
            if (m.get("usage") or {}).get("access") == "CC0":
                img = m.get("content") or m.get("thumbnail")
                if img:
                    break
        if not img or img in exclude:
            continue
        names = (c.get("freetext") or {}).get("name") or []
        artist = (names[0].get("content") if names else "") or "Smithsonian"
        return {
            "title": d.get("title") or "Untitled", "artist": artist, "date": "",
            "image": img, "source": "Smithsonian Open Access",
            "url": dnr.get("record_link") or "https://www.si.edu/openaccess",
        }
    return None


def _rijks_match(theme, timeout, exclude):
    key = os.environ.get("RIJKS_API_KEY")
    if not key:
        return None
    url = (f"{RIJKS_SEARCH}?key={key}&q={quote(theme)}&imgonly=true"
           "&ps=40&p=0&s=relevance")
    arts = _get(url, timeout).get("artObjects") or []
    random.shuffle(arts)
    for d in arts:
        img = (d.get("webImage") or {}).get("url")
        if not img:
            continue
        if img.endswith("=s0"):                 # trim the full-res suffix to web size
            img = img[:-3] + "=w843"
        if img in exclude:
            continue
        return {
            "title": d.get("title") or d.get("longTitle") or "Untitled",
            "artist": d.get("principalOrFirstMaker") or "Unknown",
            "date": "", "image": img, "source": "Rijksmuseum",
            "url": (d.get("links") or {}).get("web") or "https://www.rijksmuseum.nl/",
        }
    return None


def _europeana_match(theme, timeout, exclude):
    key = os.environ.get("EUROPEANA_API_KEY")
    if not key:
        return None
    url = (f"{EUR_SEARCH}?wskey={key}&query={quote(theme)}&reusability=open"
           "&media=true&qf=TYPE%3AIMAGE&rows=40&profile=rich")
    items = _get(url, timeout).get("items") or []
    random.shuffle(items)
    for d in items:
        img = None
        for fld in ("edmPreview", "edmIsShownBy"):
            v = d.get(fld)
            if isinstance(v, list) and v:
                img = v[0]; break
        if not img or img in exclude:
            continue
        title = d.get("title") or ["Untitled"]
        title = title[0] if isinstance(title, list) else title
        prov = d.get("dataProvider") or ["Europeana"]
        prov = prov[0] if isinstance(prov, list) else prov
        return {
            "title": title or "Untitled", "artist": prov or "Europeana", "date": "",
            "image": img, "source": "Europeana",
            "url": d.get("guid") or "https://www.europeana.eu/",
        }
    return None


def _harvard_match(theme, timeout, exclude):
    key = os.environ.get("HARVARD_API_KEY")
    if not key:
        return None
    url = (f"{HARV_SEARCH}?apikey={key}&q={quote(theme)}&hasimage=1&size=40"
           "&fields=title,people,dated,primaryimageurl,url")
    recs = _get(url, timeout).get("records") or []
    random.shuffle(recs)
    for d in recs:
        img = d.get("primaryimageurl")
        if not img or img in exclude:
            continue
        people = d.get("people") or []
        artist = (people[0].get("name") if people else "") or "Unknown"
        return {
            "title": d.get("title") or "Untitled", "artist": artist,
            "date": d.get("dated") or "", "image": img,
            "source": "Harvard Art Museums",
            "url": d.get("url") or "https://harvardartmuseums.org/",
        }
    return None


def _nypl_match(theme, timeout, exclude):
    token = os.environ.get("NYPL_TOKEN")
    if not token:
        return None
    hdr = {"Authorization": f'Token token="{token}"'}
    url = f"{NYPL_SEARCH}?q={quote(theme)}&publicDomainOnly=true&per_page=40"
    resp = ((_get(url, timeout, hdr).get("nyplAPI") or {}).get("response")) or {}
    items = resp.get("result") or []
    random.shuffle(items)
    for d in items:
        iid = d.get("imageID")
        if isinstance(iid, list):
            iid = iid[0] if iid else None
        if not iid:
            continue
        img = f"https://images.nypl.org/index.php?id={iid}&t=w"
        if img in exclude:
            continue
        title = d.get("title")
        if isinstance(title, list):
            title = title[0] if title else None
        return {
            "title": title or "Untitled",
            "artist": "The New York Public Library", "date": "",
            "image": img, "source": "New York Public Library",
            "url": d.get("itemLink") or "https://digitalcollections.nypl.org/",
        }
    return None


def _enabled_sources():
    """Key-free sources always; keyed sources only when their env var is set."""
    srcs = [_met_match, _aic_match, _cma_match, _vam_match, _smk_match]
    if os.environ.get("SI_API_KEY"):
        srcs.append(_si_match)
    if os.environ.get("RIJKS_API_KEY"):
        srcs.append(_rijks_match)
    if os.environ.get("EUROPEANA_API_KEY"):
        srcs.append(_europeana_match)
    if os.environ.get("HARVARD_API_KEY"):
        srcs.append(_harvard_match)
    if os.environ.get("NYPL_TOKEN"):
        srcs.append(_nypl_match)
    return srcs


def fetch_section_frame(theme, timeout=15, exclude=None):
    """One public-domain or openly licensed work matched to `theme`, or None.

    Draws from every available open-access collection in RANDOM order, so the
    gallery that runs the length of the wire varies institution to institution.
    `exclude` is the set of image URLs already on the page, so frames never
    repeat. Never raises: any unreachable source is skipped.
    """
    exclude = exclude or set()
    sources = _enabled_sources()
    random.shuffle(sources)
    for src in sources:
        try:
            art = src(theme, timeout, exclude)
            if art and art.get("image"):
                return art
        except Exception:
            continue
    return None
