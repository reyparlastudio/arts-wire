# The Arts Wire — What We Built (step by step)

A complete, one-person, multilingual cultural-review service: a robot gathers
and curates world arts + ideas, publishes a beautiful daily edition in any
language, installs like an app, deploys itself for free, and turns paying
readers into the right-language email list automatically.

---

## The build, step by step

**Step 1 — Direction.** Chose "build a tool for creatives," narrowed to a
curated cultural digest with a working dramatist's voice as the unfair
advantage.

**Step 2 — The robot (v1).** A Python aggregator that reads RSS sources across
film, theater, and art, removes duplicates, writes fresh summaries in its own
words (linking back, never republishing), and renders an editorial HTML digest.
Plus free daily auto-publishing via GitHub Actions.

**Step 3 — Two-zone review (Arts & Letters Daily–style).** Added **The Review**
— three columns, *Articles of Note · New Books · Essays & Opinions* — on top of
**The Wire**, expanded to nine mediums (film, theater, dance, music, visual art,
photography, design, literature, ideas). Each item is tagged by *medium* and
*kind* so it routes to the right place; the AI classifies per article.

**Step 4 — Subscriptions + translation.** Made every edition publishable in
**any language** with a language switcher and automatic right-to-left layout;
built `translate.py` (one Claude call per language per edition); added
`subscribe.html` with free / $1 Supporter / Patron tiers; wrote `ARCHITECTURE.md`
covering payments, the economics of a $1 subscription (bill annually!), and the
$20k/month math.

**Step 5 — Strategy.** Researched how A&LD, Medium, Substack, The Browser, and
the "good news" outlets actually make money; built competitor SWOTs; landed the
core insight: aggregation is a commodity — your **voice and taste** are the moat,
and the goal is to be *the only one* at one thing, not better at everything.
Chose a composable/serverless model so one person can run it.

**Step 6 — Going live (this step).**
- **PWA** — installs to any device's home screen, works offline (`manifest`,
  `sw.js`, branded icons).
- **Cloudflare Pages deploy** — free global hosting, rebuilt daily.
- **The glue** — a Cloudflare Worker that verifies Lemon Squeezy webhooks and
  syncs each paying reader into MailerLite *in their chosen language*.

---

## File map

```
arts-wire/
├── aggregator.py        the robot: gather → dedupe → summarize → classify → render
├── feeds.py             your editable source list (name, url, medium, kind)
├── artwork.py           "One Beautiful Thing": daily public-domain art (Met / Art Institute)
├── translate.py         turns one edition into any language (Claude), RTL-aware
├── demo_i18n.py         offline sample translations for --demo (Spanish, Arabic)
├── subscribe.html       sign-up page: tiers + language picker → checkout
├── requirements.txt     Python dependencies
├── README.md            how to run it (four levels)
├── ARCHITECTURE.md      full system design, economics, phased plan
├── WHAT-WE-BUILT.md     this file
├── static/              PWA assets copied into every published site
│   ├── manifest.webmanifest
│   ├── sw.js            offline service worker
│   └── icons/           app icons (192, 512, maskable, apple-touch, favicon)
├── glue/                payment → email connector
│   ├── worker.js        Cloudflare Worker (Lemon Squeezy → MailerLite by language)
│   ├── wrangler.toml    worker config
│   └── README.md        15-minute setup
├── .github/workflows/
│   ├── digest.yml             build + publish to GitHub Pages
│   └── deploy-cloudflare.yml  build + publish to Cloudflare Pages
└── output/              the generated site (index.html, index.es.html, …)
```

---

## Run it now
```bash
pip install -r requirements.txt
python aggregator.py --demo --langs es,ar   # see English + Spanish + Arabic (RTL)
open output/index.html
```

## Go live (in order)
1. **Publish free.** Push to GitHub → connect Cloudflare Pages
   (`deploy-cloudflare.yml`) → add your domain. *The free edition is live.*
2. **Turn on AI.** Add `ANTHROPIC_API_KEY` secret → real summaries + translation.
3. **Collect email.** Create MailerLite; add a `language` custom field.
4. **Take money.** Create Lemon Squeezy products (Supporter $12/yr, Patron
   $120/yr); paste the checkout links into `subscribe.html`.
5. **Connect them.** Deploy `glue/` and point the Lemon Squeezy webhook at it.
6. **Send.** Each morning, mail each language segment its edition.

Then the only job left is the one only you can do: show up daily with a voice
worth reading.
