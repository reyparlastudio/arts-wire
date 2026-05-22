# The Arts Wire — System Architecture

A practical blueprint for turning the daily robot into a paid, multilingual,
globally-available newsletter — built to be run by one person.

---

## 1. The guiding principle: own the soul, rent the plumbing

There are two kinds of work in this system:

- **Your soul** — curation, voice, the content engine, translation. This is
  what nobody else can copy, and it's what we build and control.
- **Plumbing** — taking money worldwide, remitting tax in 70+ jurisdictions,
  email deliverability, unsubscribes. This is regulated, thankless, and a
  solved problem. **Rent it.** Do not build a billing system or run a mail
  server. A solo creator who tries to operate these will drown.

Everything below follows from that.

---

## 2. The system at a glance

```
                         ┌─────────────────────────┐
   RSS / sources  ─────▶ │  THE ROBOT (this repo)  │
                         │  collect → dedupe →     │
                         │  summarize → classify   │
                         └───────────┬─────────────┘
                                     │ one English edition
                                     ▼
                         ┌─────────────────────────┐
                         │  TRANSLATE (Claude)     │  one call per language,
                         │  → es, fr, ar, ja, …    │  cached per edition
                         └───────────┬─────────────┘
                                     │ HTML + text per language
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                             ▼
  ┌───────────┐            ┌──────────────────┐          ┌─────────────────┐
  │ Static    │            │  EMAIL PLATFORM  │          │  MERCHANT OF    │
  │ web pages │            │  (ESP) sends the │◀────────│  RECORD         │
  │ (free)    │            │  right-language  │  who paid │  (payments+tax) │
  │ GitHub    │            │  edition to each │  + lang   │  Paddle / Lemon │
  │ Pages     │            │  paid segment    │           │  Squeezy        │
  └───────────┘            └──────────────────┘          └─────────────────┘
        ▲                                                         ▲
        └──────────────  subscribe.html (tiers + language)  ─────┘
```

---

## 3. Components & recommended tools

| Layer | Job | Recommended (2026) | Why |
|---|---|---|---|
| **Content engine** | gather, dedupe, summarize, classify | this repo + Claude Haiku | cheap, yours |
| **Translation** | edition → any language | this repo (`translate.py`) + Claude | one call per language, RTL-aware |
| **Hosting (free tier)** | public web editions | GitHub Pages | free, auto-deploys daily |
| **Payments + tax** | charge globally, remit VAT | **Paddle** or **Lemon Squeezy** | Merchant of Record (see §4) |
| **Email delivery** | lists, segments, send, unsubscribe | MailerLite / Buttondown / Resend | deliverability + compliance |

You can start with **just the first three** (free public editions, build an
audience) and add payments + email when you have readers worth charging.

---

## 4. Money — the part most people get wrong

### Use a Merchant of Record (MoR), not raw Stripe

When you sell directly with Stripe, **you** become legally responsible for
collecting and remitting sales tax / VAT in every country and US state where a
buyer lives. For a solo operator selling worldwide, that is an unmanageable
compliance burden. A **Merchant of Record** (Paddle, Lemon Squeezy, Polar)
becomes the legal seller: they collect and file all that tax for you, handle
chargebacks, and offer local payment methods and currencies. You receive a
clean payout.

Approximate 2026 economics (verify on each provider's current pricing page):

| Provider | Rough all-in fee | Notes |
|---|---|---|
| **Paddle** | ~5% + $0.50 | Broadest tax coverage; no extra international surcharge |
| **Lemon Squeezy** | ~5–7% + ~$0.50 | Now owned by Stripe; easiest for non-developers; 95+ currencies |
| **Polar** | ~4% base (more intl.) | Developer-focused; newer |
| Gumroad | ~10% | Simplest, priciest; fine to start |

### Why $1/month must be billed annually

A fixed per-transaction fee (~$0.50) is brutal on a $1 charge.

| Plan | Charges/yr | Fees/yr (~5%+$0.50) | **You keep / yr** | Effective /mo |
|---|---|---|---|---|
| $1 billed monthly | 12 | ~$6.60 | **~$5.40** | ~$0.45 |
| **$12 billed yearly** | 1 | ~$1.10 | **~$10.90** | **~$0.91** |

Same price to the reader. **~2× the money to you.** Charge **$12/year**,
presented as "$1/month."

### What $20k/month actually requires

At ~$0.90 net per supporter, $20,000/mo ≈ **~22,000 paying subscribers** —
a steep climb on a single $1 tier. So structure tiers:

- **Reader (free)** — the funnel; grows the audience.
- **Supporter ($12/yr)** — the accessibility mission; high volume.
- **Patron ($120/yr)** — a smaller number of larger gifts.
- Later: **sponsorships** of the daily edition, and a **Pro** tier for
  industry readers (curated by beat/region) — likely your highest margin.

A realistic path to $20k/mo blends these, not 22k dollars.

---

## 5. Translation design

- The robot builds **one English edition**, then `translate.py` produces one
  translation **per language, per edition** — not per subscriber. 1,000 Spanish
  readers cost one Spanish translation, not 1,000.
- Proper nouns, source names, and links are preserved; only headlines,
  summaries, and UI strings are translated.
- Right-to-left languages (Arabic, Hebrew, Persian, Urdu) flip layout
  automatically (`dir="rtl"`).
- Cost is tiny: a full edition is a few thousand words; at Haiku rates,
  translating into a dozen languages runs cents per day.
- **Quality ladder:** Claude is excellent for most languages today. As you
  grow, add a human proofreader for your top 2–3 markets, and/or route
  specific languages to a specialist engine (e.g. DeepL) — the architecture
  lets you swap the translator without touching the rest.

---

## 6. Data flow: from "Subscribe" to inbox

1. Reader picks a **language** and tier on `subscribe.html`.
2. They check out on the **MoR**; the language travels as checkout metadata.
3. MoR confirms payment → you receive the subscriber's **email + language**
   (via the MoR's webhook, native ESP integration, or a periodic export).
4. They're added to the matching **language segment** in your ESP.
5. Each morning the robot builds + translates editions and the **ESP sends
   each segment its language's edition**.
6. Unsubscribe, receipts, and tax are handled by the ESP and MoR — not you.

> Lowest-tech version to start: connect the MoR to your ESP with a no-code
> automation (e.g. Zapier), and segment by the `lang` field. No backend code.

---

## 7. Compliance, briefly (not legal advice)

- **Tax:** handled by the MoR. This is the main reason to use one.
- **Email law (CAN-SPAM, GDPR, CASL):** use a reputable ESP — they provide
  unsubscribe links, consent tracking, and double opt-in. Always honor opt-out.
- **Copyright:** the robot links back and summarizes in fresh wording; it never
  republishes articles. Keep it that way.
- **Privacy:** store as little personal data as possible; let the MoR/ESP hold
  payment and contact info rather than rolling your own database.

---

## 8. Build it in phases (don't boil the ocean)

- **Phase 1 — Audience (now, free).** Run the robot, auto-publish to GitHub
  Pages daily, share it. Prove people want it. *No money, no email yet.*
- **Phase 2 — List.** Add a free email edition via an ESP. Grow subscribers.
- **Phase 3 — Paid.** Add the MoR + `subscribe.html`; turn on Supporter
  ($12/yr) and Patron. Wire MoR → ESP segmentation.
- **Phase 4 — Languages.** Switch on `--langs`; offer per-language editions.
- **Phase 5 — Revenue mix.** Sponsorships + a Pro tier for professionals.

Each phase stands on its own and earns the right to the next.
