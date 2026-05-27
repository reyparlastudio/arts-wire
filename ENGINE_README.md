# The Artist Signal Engine: build notes and how to run it

This is the research layer for The Arts Wire. It listens to permitted public sources, turns them into structured Signal Atoms, gathers a week's atoms into a research dossier on a theme, and drafts a Back Room letter from that dossier in Rey's voice. It runs beside the daily site, never inside it. It cannot take the live wire down, and it never publishes anything on its own. The most it ever does is create a Buttondown draft and email Rey a preview. Style rule everywhere: no em dashes.

## The files

ethics_policy.md, the charter, in the repository so the rules travel with the code.

taxonomy.json, the mediums, the psychological vocabulary, and the now-versus-before pairings, used to tag atoms and shape dossiers.

source_risk_registry.json, every source with its risk level and allowed use. Already seeded from your feeds plus a curated set of open APIs and public-domain collections.

sources_registry.py, the gate. Loads and validates the registry and answers one question: may we use this source, and how. Green is allowed. Yellow is allowed only after a human sets terms_checked to true. Red is never allowed.

signal_atoms.py, turns permitted public signals into Signal Atoms. The model fills the reading and consequence fields. The ethics fields are set by us from the registry, never by the model, so an atom can never claim a permission it does not have. Atoms store our original analysis and a citation, never the full text of a source.

research_dossier.py, gathers the theme's atoms into one weekly brief with its historical echo and every source attached. The dossier is private research, never published.

backroom_signal.py, drafts a Back Room letter from a dossier on the eight-part spine, in Rey's voice, as a draft only. It reuses newsletter.py for the sendable Markdown, the preview, and the Buttondown draft path, so every letter goes through the same one-human-tap workflow.

engine.py, one handle over all of the above.

## Install

The engine adds no new dependencies beyond what the site already uses: feedparser for reading feeds, and the anthropic client for analysis and drafting. Both are already in requirements.txt. Upload all eight engine files to the repository root, beside aggregator.py, feeds.py, newsletter.py, and translate.py.

## Run it

Everything is fail-soft. With no API key, every step still produces a real, human-usable scaffold. With keys set, the model does the analysis and the writing.

    python engine.py seed
        Writes source_risk_registry.json from feeds.py plus the curated open sources.

    python engine.py atoms
        Builds Signal Atoms from permitted sources into signal_atoms_latest.json.

    python engine.py dossier --theme "pricing your work without apology"
        Builds a weekly research dossier from the latest atoms.

    python engine.py draft --dossier research_dossiers/THE-FILE.json
        Drafts a Back Room letter and creates a Buttondown draft plus a preview to Rey.

    python engine.py weekly --theme "..."
        The full chain at once. Add --dry-run to touch no services and write local files only.

## Environment variables

    ANTHROPIC_API_KEY     enables analysis and drafting; without it, scaffolds are used
    BUTTONDOWN_API_KEY    enables creating the draft and sending Rey a preview
    REVIEW_EMAIL          where the [PREVIEW] is sent
    AW_ATOM_MODEL         optional, defaults to the fast model for analysis
    AW_DOSSIER_MODEL      optional, defaults to a strong prose model
    AW_PROSE_MODEL        optional, defaults to the newsletter prose model

## How it stays ethical in code, not just on paper

The registry is the only door. signal_atoms.py refuses to build an atom for any source the registry does not permit, so a private or unvetted source is skipped before it is ever read. The ethics fields on every atom, allowed use, risk level, citation required, and ethical status, are written by us from the registry, never by the model. The dossier carries every source forward, so a citation can never be lost between research and writing. And nothing reaches a reader without Rey opening Buttondown and clicking Publish.

## Where this sits in the roadmap

This is the engine, and the engine is real now. The business still becomes real in the order the master plan sets: connect payment, write the first letters, grow the list, then let the engine deepen the letters week after week. The engine is built so you can turn it on gently, one green source at a time, the day you are ready.

## Assumptions to verify before leaning on them

The curated open sources in the registry are marked terms_checked false on purpose. Before the engine relies on any of them, confirm at the source: each museum API's current terms and per-object public-domain status; OpenAlex, DOAJ, and arXiv usage and rate limits; and the license of any specific artwork or text before reuse. For any yellow source you add, check robots.txt, terms of service, and rate limits, and only then set terms_checked to true. Buttondown's paid tiers and whether it takes a platform cut, and Stripe's current fees, also remain items to confirm in your own accounts.
