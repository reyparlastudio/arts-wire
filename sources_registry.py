#!/usr/bin/env python3
"""
sources_registry.py  —  the gate every source must pass through
================================================================
The Artist Signal Engine never fetches or analyzes a source unless this
registry permits it. The registry is the data in source_risk_registry.json;
this module loads it, validates it, and answers one question for the rest of
the engine: is this source allowed, and how may we use it.

Risk follows the green, yellow, red system in ethics_policy.md.
  green   preferred, low risk, ingest freely within polite limits
  yellow  allowed ONLY after a human has checked terms, robots, rate limits
  red     forbidden, never ingested

Seeding: `python sources_registry.py --seed` reads feeds.py (your real RSS
sources) and a curated set of open APIs and public-domain collections, and
writes source_risk_registry.json. `--check` validates an existing registry.

Nothing here calls a network or an API. It is pure, fail-soft configuration.
House style: no em dashes anywhere.
"""

import argparse
import json
import os
import re
import sys

RISK_LEVELS = ("green", "yellow", "red")
ALLOWED_USES = ("summarize-and-link", "short-quote-and-cite", "metadata-only", "image-public-domain")
CATEGORIES = ("arts-journalism", "artist-channel", "podcast", "scholarship", "museum",
              "manifesto", "opportunity", "calendar", "school", "technology",
              "report", "public-domain")

REGISTRY_PATH = os.environ.get("AW_SOURCE_REGISTRY", "source_risk_registry.json")

# Required keys on every registry entry.
REQUIRED = ("id", "name", "category", "allowed_use", "risk_level", "ingestion_method")


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "source"


def _medium_category(medium):
    """Map a feeds.py medium to a registry category."""
    if medium == "podcast":
        return "podcast"
    return "arts-journalism"


def seed_from_feeds():
    """Turn every entry in feeds.py into a green registry record. Each is an RSS
    feed published for syndication, used as summarize-and-link: we write our own
    summary and we link out. Articles themselves stay all-rights-reserved.
    Returns a list of entries, or [] if feeds.py cannot be imported."""
    try:
        import feeds
    except Exception:
        return []
    regional = getattr(feeds, "REGIONAL_SOURCES", set())
    out = []
    for row in getattr(feeds, "FEEDS", []):
        try:
            name, url, medium, kind = row
        except Exception:
            continue
        purpose = ("Regional coverage of Cuba, the Caribbean, and Latin America."
                   if name in regional else f"Daily arts coverage in {medium}.")
        out.append({
            "id": _slug(name),
            "name": name,
            "category": _medium_category(medium),
            "url": url,
            "feed": url,
            "api": None,
            "purpose": purpose,
            "signal_provided": f"what happened and what is argued in {medium}",
            "allowed_use": "summarize-and-link",
            "risk_level": "green",
            "license": "all-rights-reserved",
            "ingestion_method": "rss",
            "medium": medium,
            "rate_limit": "polite, one poll per run",
            "robots_ok": True,
            "terms_checked": False,
            "last_checked": None,
            "notes": "Published RSS feed. Summarize in our own words and link out. Verify terms before any heavier use.",
        })
    return out


# Curated open sources beyond the daily feeds: museum open APIs, public-domain
# collections, open scholarship, technology research, and opportunity listings.
# All are marked terms_checked false on purpose: a human confirms the current
# license and API terms before the engine leans on them. See the verify list
# in ENGINE_README.md.
CURATED = [
    {"id": "met-open-access", "name": "The Metropolitan Museum of Art Open Access", "category": "museum",
     "url": "https://www.metmuseum.org/art/collection", "feed": None,
     "api": "https://collectionapi.metmuseum.org/public/collection/v1/",
     "purpose": "Public-domain artworks and object metadata for The Frame and historical anchors.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public-domain (CC0 items only)",
     "ingestion_method": "api", "rate_limit": "documented API limit", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Use only items flagged public domain. Confirm CC0 status per object."},
    {"id": "art-institute-chicago", "name": "Art Institute of Chicago API", "category": "museum",
     "url": "https://www.artic.edu/collection", "feed": None,
     "api": "https://api.artic.edu/api/v1/",
     "purpose": "Open collection metadata and public-domain images.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "varies per object",
     "ingestion_method": "api", "rate_limit": "documented API limit", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Check is_public_domain per object before reuse."},
    {"id": "cleveland-museum-open-access", "name": "Cleveland Museum of Art Open Access", "category": "museum",
     "url": "https://www.clevelandart.org/art/collection", "feed": None,
     "api": "https://openaccess-api.clevelandart.org/api/",
     "purpose": "Open-access artworks and metadata.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "CC0 for open-access items",
     "ingestion_method": "api", "rate_limit": "documented API limit", "robots_ok": True,
     "terms_checked": False, "last_checked": None, "notes": "Filter to open-access items."},
    {"id": "smithsonian-open-access", "name": "Smithsonian Open Access", "category": "museum",
     "url": "https://www.si.edu/openaccess", "feed": None,
     "api": "https://api.si.edu/openaccess/api/v1.0/",
     "purpose": "CC0 collection metadata and media across Smithsonian units.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "CC0 for open-access items",
     "ingestion_method": "api", "rate_limit": "API key required",
     "robots_ok": True, "terms_checked": False, "last_checked": None,
     "notes": "Requires an API key. Spans all 19 Smithsonian museums plus research centers, including the National Museum of African American History and Culture, the National Portrait Gallery, and the Archives of American Art. Use CC0 items only."},
    {"id": "wikimedia-commons", "name": "Wikimedia Commons", "category": "public-domain",
     "url": "https://commons.wikimedia.org", "feed": None,
     "api": "https://commons.wikimedia.org/w/api.php",
     "purpose": "Public-domain and openly licensed media for historical anchors.",
     "signal_provided": "the deep well of memory",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public-domain / CC, per file",
     "ingestion_method": "api", "rate_limit": "polite, honor maxlag", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Confirm the exact license per file and attribute as required."},
    {"id": "openalex", "name": "OpenAlex", "category": "scholarship",
     "url": "https://openalex.org", "feed": None, "api": "https://api.openalex.org/",
     "purpose": "Open scholarly metadata for the lineage under today's conversations.",
     "signal_provided": "the historical and theoretical depth",
     "allowed_use": "summarize-and-link", "risk_level": "green", "license": "CC0 metadata",
     "ingestion_method": "api", "rate_limit": "polite pool, set a contact email", "robots_ok": True,
     "terms_checked": False, "last_checked": None, "notes": "Metadata is open; full texts follow their own licenses."},
    {"id": "doaj", "name": "Directory of Open Access Journals", "category": "scholarship",
     "url": "https://doaj.org", "feed": None, "api": "https://doaj.org/api/",
     "purpose": "Open-access art and humanities scholarship.",
     "signal_provided": "the lineage under today's conversations",
     "allowed_use": "summarize-and-link", "risk_level": "green", "license": "open access, per article",
     "ingestion_method": "api", "rate_limit": "documented API limit", "robots_ok": True,
     "terms_checked": False, "last_checked": None, "notes": "Summarize and link; confirm each article's license."},
    {"id": "arxiv", "name": "arXiv", "category": "technology",
     "url": "https://arxiv.org", "feed": None, "api": "http://export.arxiv.org/api/",
     "purpose": "Public technology and AI research that reshapes artists' tools and rights.",
     "signal_provided": "what is coming for artists' tools and rights",
     "allowed_use": "summarize-and-link", "risk_level": "green", "license": "per paper, often non-commercial",
     "ingestion_method": "api", "rate_limit": "one request every few seconds", "robots_ok": True,
     "terms_checked": False, "last_checked": None, "notes": "Summarize and link; do not redistribute full PDFs."},
    {"id": "open-calls-placeholder", "name": "Open calls and residencies (add specific feeds)", "category": "opportunity",
     "url": "", "feed": None, "api": None,
     "purpose": "The opportunity layer and a future paid listing product.",
     "signal_provided": "where money, time, and space are being offered to artists",
     "allowed_use": "summarize-and-link", "risk_level": "yellow", "license": "per listing",
     "ingestion_method": "manual-curated", "rate_limit": "n/a", "robots_ok": False,
     "terms_checked": False, "last_checked": None,
     "notes": "Placeholder. Add specific public listing feeds only after checking robots.txt and terms."},
    {"id": "national-gallery-of-art", "name": "National Gallery of Art (NGA Images)", "category": "museum",
     "url": "https://www.nga.gov/artworks", "feed": None,
     "api": "https://github.com/NationalGalleryofArt/opendata",
     "purpose": "Open-access public-domain artworks and open collection data.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "CC0 for open-access items",
     "ingestion_method": "api", "rate_limit": "documented", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Open-access images via NGA Images; open data on GitHub. Use items marked open access."},
    {"id": "getty-open-content", "name": "Getty Open Content", "category": "museum",
     "url": "https://www.getty.edu/art/collection/", "feed": None,
     "api": "https://data.getty.edu/",
     "purpose": "Over 150,000 public-domain images and open linked-data vocabularies.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "Open Content Program / public-domain items",
     "ingestion_method": "api", "rate_limit": "documented", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Use Open Content Program items. Getty also offers IIIF and linked-data vocabularies."},
    {"id": "rijksmuseum", "name": "Rijksmuseum", "category": "museum",
     "url": "https://www.rijksmuseum.nl/en/rijksstudio", "feed": None,
     "api": "https://data.rijksmuseum.nl/",
     "purpose": "Public-domain masterworks with a long-standing open API.",
     "signal_provided": "the visual and historical record",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public domain / CC0 for public-domain works",
     "ingestion_method": "api", "rate_limit": "free API key required", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Requires a free API key. Use public-domain works only."},
    {"id": "nypl-digital-collections", "name": "New York Public Library Digital Collections", "category": "museum",
     "url": "https://digitalcollections.nypl.org/", "feed": None,
     "api": "https://api.repo.nypl.org/",
     "purpose": "Hundreds of thousands of public-domain images, maps, photographs, and manuscripts.",
     "signal_provided": "the deep well of memory",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public domain for items marked public domain",
     "ingestion_method": "api", "rate_limit": "access token required", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Requires an access token. Filter to public-domain items."},
    {"id": "library-of-congress", "name": "Library of Congress (Free to Use and Reuse)", "category": "public-domain",
     "url": "https://www.loc.gov/free-to-use/", "feed": None,
     "api": "https://www.loc.gov/apis/",
     "purpose": "Public-domain photography, documents, and themed sets: civil rights, founding documents, diaspora histories.",
     "signal_provided": "the documentary record of democracy, rights, and marginalized voices",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public domain / no known restrictions per item",
     "ingestion_method": "api", "rate_limit": "public API, no key, rate-limit politely", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Use the Free to Use sets and items marked public domain or no known restrictions. Not every LoC item is public domain."},
    {"id": "national-archives", "name": "U.S. National Archives (NARA)", "category": "public-domain",
     "url": "https://catalog.archives.gov/", "feed": None,
     "api": "https://catalog.archives.gov/api/v2/",
     "purpose": "Federal records in the public domain, including the founding documents: the Constitution, the Bill of Rights, the Declaration.",
     "signal_provided": "the founding documents as public-domain material",
     "allowed_use": "image-public-domain", "risk_level": "green", "license": "public domain (U.S. federal records)",
     "ingestion_method": "api", "rate_limit": "documented", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "U.S. government works carry no copyright. The Constitution and Bill of Rights are free to reproduce and remix."},
    {"id": "dpla", "name": "Digital Public Library of America", "category": "public-domain",
     "url": "https://dp.la/", "feed": None,
     "api": "https://pro.dp.la/developers/api-codex",
     "purpose": "An aggregator of millions of items from U.S. libraries, archives, and museums.",
     "signal_provided": "a wide net across many institutions at once",
     "allowed_use": "summarize-and-link", "risk_level": "green", "license": "rights vary per item; check each",
     "ingestion_method": "api", "rate_limit": "API key required", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Aggregated metadata; rights vary per item, so confirm each item before reuse."},
    {"id": "wikidata", "name": "Wikidata", "category": "public-domain",
     "url": "https://www.wikidata.org/", "feed": None,
     "api": "https://query.wikidata.org/sparql",
     "purpose": "Public-domain structured facts: birth and death dates, places, mediums, links. Powers The Almanac.",
     "signal_provided": "clean dated facts for the daily date piece",
     "allowed_use": "metadata-only", "risk_level": "green", "license": "CC0",
     "ingestion_method": "api", "rate_limit": "public SPARQL, rate-limit politely", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "CC0 facts. Free to state; we still write original prose and link out."},
    {"id": "wikipedia", "name": "Wikipedia (anniversaries and context)", "category": "public-domain",
     "url": "https://en.wikipedia.org/", "feed": None,
     "api": "https://en.wikipedia.org/w/api.php",
     "purpose": "Daily anniversaries and context for The Almanac.",
     "signal_provided": "context for the day's anchor",
     "allowed_use": "summarize-and-link", "risk_level": "green", "license": "CC BY-SA text",
     "ingestion_method": "api", "rate_limit": "MediaWiki API, honor maxlag", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Text is CC BY-SA, so summarize in our own words and cite; never copy."},
    {"id": "moma-collection-data", "name": "MoMA collection data (GitHub)", "category": "museum",
     "url": "https://github.com/MuseumofModernArt/collection", "feed": None,
     "api": "https://github.com/MuseumofModernArt/collection",
     "purpose": "Public-domain metadata for 150,000+ works and artist records, including nationality and gender fields.",
     "signal_provided": "facts and a representation lens; NO images",
     "allowed_use": "metadata-only", "risk_level": "green", "license": "CC0 data; images NOT included",
     "ingestion_method": "manual-curated", "rate_limit": "static dataset", "robots_ok": True,
     "terms_checked": False, "last_checked": None,
     "notes": "Data only. Images are in copyright and licensed via Art Resource/Scala. Use the facts as material, never the images. A springboard for Rey's own original work."},
    {"id": "pamm", "name": "Pérez Art Museum Miami", "category": "museum",
     "url": "https://www.pamm.org/", "feed": None, "api": None,
     "purpose": "Miami and Caribbean and Latinx diaspora exhibitions and news; a portal source, not a data trove.",
     "signal_provided": "Miami, Caribbean, and Latinx art news and exhibitions",
     "allowed_use": "summarize-and-link", "risk_level": "yellow", "license": "contemporary works in copyright",
     "ingestion_method": "manual-curated", "rate_limit": "n/a", "robots_ok": False,
     "terms_checked": False, "last_checked": None,
     "notes": "Contemporary collection, no open-access images. Link and summarize exhibitions and news only. Check terms before any automated fetch."},
    {"id": "youngarts", "name": "National YoungArts Foundation", "category": "opportunity",
     "url": "https://youngarts.org/", "feed": None, "api": None,
     "purpose": "Miami-based national foundation for young artists; open calls, awards, and emerging-artist news.",
     "signal_provided": "opportunities and the next generation of artists",
     "allowed_use": "summarize-and-link", "risk_level": "yellow", "license": "site content in copyright",
     "ingestion_method": "manual-curated", "rate_limit": "n/a", "robots_ok": False,
     "terms_checked": False, "last_checked": None,
     "notes": "Use for open calls, deadlines, winners, and Miami programming. Link and summarize. A natural partner, not a data source."},
    {"id": "alldayeveryday", "name": "Alldayeveryday (creative production company)", "category": "arts-journalism",
     "url": "https://www.alldayeveryday.com/", "feed": None, "api": None,
     "purpose": "An LA Arts District production company; a source for the creative-industry and moving-image beat, and a model for a studio arm.",
     "signal_provided": "the production and creative-industry beat",
     "allowed_use": "summarize-and-link", "risk_level": "yellow", "license": "commercial site in copyright",
     "ingestion_method": "manual-curated", "rate_limit": "n/a", "robots_ok": False,
     "terms_checked": False, "last_checked": None,
     "notes": "Commercial and brand-adjacent. Use as industry news and inspiration, never a content trove. More relevant to a future studio arm than to the daily wire."},
]


def load_registry(path=None):
    """Read the registry. Never raises; returns [] on any problem."""
    path = path or REGISTRY_PATH
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d = d.get("sources", [])
        return d if isinstance(d, list) else []
    except Exception:
        return []


def save_registry(entries, path=None):
    """Write the registry as {"sources": [...]}. Returns count, or -1 on failure."""
    path = path or REGISTRY_PATH
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"_about": "Source risk registry for The Artist Signal Engine. "
                                  "Edit by hand or regenerate with sources_registry.py --seed. "
                                  "Set terms_checked true only after a human confirms terms.",
                       "sources": entries}, f, ensure_ascii=False, indent=2)
        return len(entries)
    except Exception:
        return -1


def validate_entry(e):
    """Return a list of problems with one entry. Empty list means valid."""
    problems = []
    if not isinstance(e, dict):
        return ["not an object"]
    for k in REQUIRED:
        if not e.get(k):
            problems.append(f"missing {k}")
    if e.get("risk_level") not in RISK_LEVELS:
        problems.append(f"bad risk_level {e.get('risk_level')!r}")
    if e.get("allowed_use") not in ALLOWED_USES:
        problems.append(f"bad allowed_use {e.get('allowed_use')!r}")
    if e.get("category") and e["category"] not in CATEGORIES:
        problems.append(f"unknown category {e.get('category')!r}")
    return problems


def is_permitted(e):
    """May the engine ingest this source right now?
    Green is permitted. Yellow is permitted ONLY once a human has set
    terms_checked true. Red is never permitted."""
    if not isinstance(e, dict) or validate_entry(e):
        return False
    risk = e.get("risk_level")
    if risk == "red":
        return False
    if risk == "yellow":
        return bool(e.get("terms_checked"))
    return risk == "green"


def permitted_sources(registry=None, category=None, ingestion=None):
    """All sources the engine may use now, optionally filtered."""
    registry = registry if registry is not None else load_registry()
    out = []
    for e in registry:
        if not is_permitted(e):
            continue
        if category and e.get("category") != category:
            continue
        if ingestion and e.get("ingestion_method") != ingestion:
            continue
        out.append(e)
    return out


def build_seed():
    """The full seeded registry: your feeds plus the curated open sources."""
    return seed_from_feeds() + [dict(c) for c in CURATED]


def main():
    ap = argparse.ArgumentParser(description="Seed or check the source risk registry.")
    ap.add_argument("--seed", action="store_true", help="write source_risk_registry.json from feeds.py + curated sources")
    ap.add_argument("--check", action="store_true", help="validate the existing registry and report problems")
    ap.add_argument("--path", default=REGISTRY_PATH, help="registry file path")
    args = ap.parse_args()

    if args.seed:
        entries = build_seed()
        bad = [(e.get("name"), validate_entry(e)) for e in entries if validate_entry(e)]
        n = save_registry(entries, args.path)
        if n < 0:
            print("Could not write the registry.")
            sys.exit(1)
        green = sum(1 for e in entries if e.get("risk_level") == "green")
        yellow = sum(1 for e in entries if e.get("risk_level") == "yellow")
        print(f"Wrote {n} sources to {args.path}: {green} green, {yellow} yellow.")
        if bad:
            print("  Warnings:")
            for name, probs in bad:
                print(f"   - {name}: {', '.join(probs)}")
        print(f"  Permitted to ingest now: {len(permitted_sources(entries))} "
              f"(green plus any yellow you have checked).")
        return

    if args.check:
        reg = load_registry(args.path)
        if not reg:
            print(f"No registry at {args.path}. Run --seed first.")
            sys.exit(1)
        problems = [(e.get("name", "?"), validate_entry(e)) for e in reg if validate_entry(e)]
        print(f"{len(reg)} sources, {len(permitted_sources(reg))} permitted to ingest now.")
        if problems:
            print("Problems:")
            for name, probs in problems:
                print(f"  - {name}: {', '.join(probs)}")
        else:
            print("All entries valid.")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
