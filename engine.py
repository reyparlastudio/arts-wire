#!/usr/bin/env python3
"""
engine.py  —  the Artist Signal Engine, one handle
===================================================
A thin orchestrator over the four modules. It never auto-publishes anything;
the most it does is create a Buttondown DRAFT and email Rey a preview, exactly
like the existing newsletter workflow. Every step is fail-soft and runs beside
the daily site, never inside it.

Commands:
  python engine.py seed
      Write source_risk_registry.json from feeds.py plus curated open sources.

  python engine.py atoms [--limit 60] [--no-api]
      Build Signal Atoms from permitted public sources into signal_atoms_latest.json.

  python engine.py dossier --theme "..." [--no-api]
      Build a weekly research dossier from the latest atoms.

  python engine.py draft --dossier PATH [--dry-run] [--no-preview]
      Draft a Back Room letter from a dossier (creates a Buttondown draft unless --dry-run).

  python engine.py weekly --theme "..." [--dry-run] [--no-preview] [--limit 60]
      The full chain: atoms, dossier, draft. With --dry-run it touches no services.

Environment:
  ANTHROPIC_API_KEY    enables analysis and drafting (without it, scaffolds are used)
  BUTTONDOWN_API_KEY   enables creating the draft and sending Rey a preview
  REVIEW_EMAIL         where the [PREVIEW] goes
  AW_ATOM_MODEL, AW_DOSSIER_MODEL, AW_PROSE_MODEL   optional model overrides

House style: no em dashes anywhere.
"""

import argparse
import json
import os
import sys

import sources_registry as REG
import signal_atoms as ATOMS
import research_dossier as DOSSIER
import backroom_signal as DRAFT

ATOMS_FILE = os.environ.get("AW_ATOMS_FILE", "signal_atoms_latest.json")


def _client(enabled=True):
    if not enabled or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        return None


def cmd_seed(_):
    entries = REG.build_seed()
    n = REG.save_registry(entries)
    green = sum(1 for e in entries if e.get("risk_level") == "green")
    print(f"Seeded {n} sources, {green} green, "
          f"{len(REG.permitted_sources(entries))} permitted now.")


def cmd_atoms(args):
    reg = REG.load_registry()
    if not reg:
        print("No registry. Run: python engine.py seed")
        sys.exit(1)
    client = _client(not args.no_api)
    items = ATOMS.items_from_feeds(reg, limit=args.limit)
    if not items:
        print("  ! No items gathered (feeds unreachable or feedparser missing). Nothing to do.")
        return
    cache = ATOMS.load_cache()
    atoms = ATOMS.build_atoms(items, client, cache=cache, registry=reg)
    ATOMS.save_cache(cache)
    ATOMS.save_atoms(atoms, ATOMS_FILE)
    print(f"Built {len(atoms)} atoms from {len(items)} items -> {ATOMS_FILE} "
          f"({'with' if client else 'without'} model).")


def _load_atoms():
    try:
        with open(ATOMS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("atoms", []) if isinstance(data, dict) else data
    except Exception:
        return []


def cmd_dossier(args):
    atoms = _load_atoms()
    if not atoms:
        print(f"No atoms in {ATOMS_FILE}. Run: python engine.py atoms")
        sys.exit(1)
    client = _client(not args.no_api)
    dossier = DOSSIER.build_dossier(args.theme, atoms, client=client)
    path = DOSSIER.save_dossier(dossier)
    print(f"Dossier on '{args.theme}' from {dossier['atom_count']} atoms -> {path or 'not saved'}")


def cmd_draft(args):
    with open(args.dossier, encoding="utf-8") as f:
        dossier = json.load(f)
    client = _client(not args.dry_run)
    DRAFT.run(dossier, dry_run=args.dry_run, no_preview=args.no_preview, client=client)


def cmd_weekly(args):
    reg = REG.load_registry()
    if not reg:
        cmd_seed(args)
        reg = REG.load_registry()
    client = _client(not args.dry_run)
    items = ATOMS.items_from_feeds(reg, limit=args.limit)
    cache = ATOMS.load_cache()
    atoms = ATOMS.build_atoms(items, client, cache=cache, registry=reg)
    ATOMS.save_cache(cache)
    ATOMS.save_atoms(atoms, ATOMS_FILE)
    print(f"  atoms: {len(atoms)} from {len(items)} items")
    dossier = DOSSIER.build_dossier(args.theme, atoms, client=client)
    dpath = DOSSIER.save_dossier(dossier)
    print(f"  dossier: {dpath or 'not saved'} ({dossier['atom_count']} atoms)")
    DRAFT.run(dossier, dry_run=args.dry_run, no_preview=args.no_preview, client=client)


def main():
    ap = argparse.ArgumentParser(description="The Artist Signal Engine.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seed").set_defaults(func=cmd_seed)

    p = sub.add_parser("atoms"); p.add_argument("--limit", type=int, default=60)
    p.add_argument("--no-api", action="store_true"); p.set_defaults(func=cmd_atoms)

    p = sub.add_parser("dossier"); p.add_argument("--theme", required=True)
    p.add_argument("--no-api", action="store_true"); p.set_defaults(func=cmd_dossier)

    p = sub.add_parser("draft"); p.add_argument("--dossier", required=True)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--no-preview", action="store_true")
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("weekly"); p.add_argument("--theme", required=True)
    p.add_argument("--limit", type=int, default=60); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-preview", action="store_true"); p.set_defaults(func=cmd_weekly)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
