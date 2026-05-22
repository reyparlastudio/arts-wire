# The Arts Wire 🎭🎬🖼️📚

An automated robot that builds a daily cultural review — on autopilot.
It has **two zones**, modeled on the great intellectual digests:

**THE REVIEW** — long-form picks in three columns, à la *Arts & Letters Daily*:
- **Articles of Note** — deep dives in ideas, science, and culture
- **New Books** — reviews and criticism
- **Essays & Opinions** — arguments and columns

…drawn from across every art form *and* philosophy / science / letters.

**THE WIRE** — timely news, sorted by medium: Film & TV, Theater, Dance,
Music, Visual Art, Photography, Design & Architecture, Literature & Poetry,
and Ideas & Humanities.

It can publish in **any language** (with automatic right-to-left layout),
**installs like an app** (PWA), **deploys itself free** to Cloudflare Pages,
and comes with a **subscribe page** plus a **payment→email connector** so paying
readers auto-join your list in their chosen language. For a step-by-step recap of
everything, see **`WHAT-WE-BUILT.md`**; for the full system design and economics,
see **`ARCHITECTURE.md`**; to wire payments, see **`glue/README.md`**.

You do **not** need to be a programmer. Start at Level 1.

---

## Level 1 — See it now (30 sec, no setup)
```bash
pip install -r requirements.txt
python aggregator.py --demo
```
Open **`output/index.html`**. That's the finished look, with sample pieces
(including the consciousness "hard problem," a James Schuyler retrospective,
and more) so you can see both zones at once.

## Level 2 — Real feeds, free, no key
```bash
python aggregator.py
```
Reads the ~30 live sources in `feeds.py`. Prints a **health report** so you
see which are live. Without a key it uses each source's own blurb and sorts
by each feed's default kind. Dead feeds are skipped — they can't crash it.

## Level 3 — Turn on the AI
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python aggregator.py
```
Now the AI writes original summaries, tags everything, and — crucially —
classifies each *article* into the right Review column or Wire section
(so a book review on a news site still lands under New Books). Uses Claude
Haiku, the cheapest model: about a penny or two per edition.

## Level 4 — Full autopilot (publishes daily, free)
1. Put this folder on GitHub.
2. **Settings → Pages → Source → "GitHub Actions."**
3. (For AI) **Settings → Secrets and variables → Actions → New secret**,
   name `ANTHROPIC_API_KEY`.
4. Done. `.github/workflows/digest.yml` rebuilds and publishes every morning.

---

## Make it yours
- **Sources & sorting:** edit `feeds.py`. Each line is
  `("Name", "url", "medium", "kind")`. Change a source's `kind` to move where
  it lands (`note` / `book` / `essay` → The Review; `news` → The Wire).
- **Add a medium:** add it to `CATEGORIES` in `feeds.py` and tag feeds with it.
- **Schedule / look:** the `cron` line in the workflow; the design lives in
  `TEMPLATE` inside `aggregator.py`.

### Options
```bash
python aggregator.py --hours 72         # look back further
python aggregator.py --max-items 80     # cap the edition
python aggregator.py --langs es,fr,ja,ar   # also publish these languages
python aggregator.py --demo --langs es,ar  # see a Spanish + Arabic (RTL) sample
```

### Languages & subscriptions
- `--langs` writes one page per language (`index.es.html`, etc.) with a
  language switcher; right-to-left languages flip automatically. Translation
  uses your API key; without it, English ships and other languages are skipped.
- `subscribe.html` is your sign-up page (free / $1-a-month Supporter / Patron).
  It's static — wire it to a checkout in ~10 minutes following `ARCHITECTURE.md`.

---

## Doing it right
The robot **links back** to every publisher and summarizes in fresh wording —
it never republishes anyone's work. Your judgment about what matters is the
product; the robot just gathers. That curatorial voice is what built the
reputation of every digest worth imitating.
