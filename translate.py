"""
translate.py  —  turn one edition into many languages
======================================================
Translates an assembled edition into any target language using Claude (the
same key the summaries use).

Why this version is robust: instead of translating the whole edition in one
API call (which overruns the token cap on a full day and comes back truncated,
i.e. broken JSON), we translate the chrome once and then the stories in small
BATCHES. Each call is small enough to never truncate, every call is wrapped so
a single failure can't sink a whole language, and any story we cannot translate
simply stays in English. The page is therefore always written.

Proper nouns, source names, and links are left intact. Right-to-left languages
(Arabic, Hebrew, Persian, Urdu) are flagged so the page flips automatically.
If there's no API key, callers skip translation and ship English.
"""

import json
import re
import time
import hashlib

RTL_LANGS = {"ar", "he", "fa", "ur", "yi"}

# Autonyms (a language shown in its own script) for the language switcher.
AUTONYMS = {
    "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch",
    "pt": "Português", "it": "Italiano", "nl": "Nederlands", "pl": "Polski",
    "ru": "Русский", "uk": "Українська", "tr": "Türkçe", "ar": "العربية",
    "he": "עברית", "fa": "فارسی", "ur": "اردو", "hi": "हिन्दी",
    "ja": "日本語", "ko": "한국어", "zh": "中文", "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia", "th": "ไทย", "sw": "Kiswahili", "el": "Ελληνικά",
    "bn": "বাংলা", "ta": "தமிழ்", "ro": "Română", "cs": "Čeština", "hu": "Magyar",
    "sv": "Svenska", "da": "Dansk", "fi": "Suomi", "no": "Norsk", "tl": "Filipino",
    "ms": "Bahasa Melayu",
}

# English-language name, for the translation prompt.
NAMES = {
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "uk": "Ukrainian", "tr": "Turkish", "ar": "Arabic", "he": "Hebrew",
    "fa": "Persian", "ur": "Urdu", "hi": "Hindi", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese (Simplified)", "vi": "Vietnamese",
    "id": "Indonesian", "th": "Thai", "sw": "Swahili", "el": "Greek",
    "bn": "Bengali", "ta": "Tamil", "ro": "Romanian", "cs": "Czech", "hu": "Hungarian",
    "sv": "Swedish", "da": "Danish", "fi": "Finnish", "no": "Norwegian", "tl": "Filipino",
    "ms": "Malay",
}

# BCP-47 / hreflang codes. Most match the short code; a few need script or
# region refinement so Google serves the right edition (esp. Chinese).
BCP47 = {
    "zh": "zh-Hans", "pt": "pt", "el": "el", "he": "he", "uk": "uk",
}

# How many stories to translate per API call. Small enough that the reply
# never hits the token cap, large enough to keep the call count sane.
BATCH = 12

# How big the translation cache may grow before the oldest entries are trimmed.
# A rolling window: it comfortably holds every story across a dozen languages
# for weeks, while keeping the committed cache file small.
CACHE_CAP = 20000


def _key(kind, lang, obj):
    """A stable cache key for one translatable unit: its kind, language, and exact source."""
    raw = f"{kind}|{lang}|" + json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_cache(path):
    """Read the translation cache. Never raises; returns an empty cache on any problem."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_cache(path, cache, cap=CACHE_CAP):
    """Write the cache, trimming the oldest entries if it has grown past the cap.
    Never raises; returns the number of entries written, or -1 on failure."""
    try:
        if len(cache) > cap:                         # keep the most-recently-used tail
            for k in list(cache.keys())[:len(cache) - cap]:
                cache.pop(k, None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        return len(cache)
    except Exception:
        return -1


def bcp47(code):
    """The search-engine-correct language tag for a short code."""
    return BCP47.get(code, code)


def autonym(code):
    return AUTONYMS.get(code, code.upper())


def is_rtl(code):
    return code in RTL_LANGS


def all_langs():
    """Every language we can render: the full supported world set, minus English."""
    return list(NAMES.keys())


def translate_map(mapping, lang, client, model, cache=None):
    """Translate the values of a flat {key: text} map into `lang`.
    One call, with per-key fallback to English so nothing is ever lost.
    Cached by source: a map that has not changed is never retranslated."""
    language = NAMES.get(lang, lang)
    if cache is not None:
        k = _key("map", lang, mapping)
        hit = cache.pop(k, None)                     # pop + reinsert = move to newest
        if isinstance(hit, dict):
            cache[k] = hit
            return {kk: hit.get(kk, vv) for kk, vv in mapping.items()}
    d = _translate_json(client, model, language, mapping, 4096)
    if not isinstance(d, dict):
        d = {}
    out = {kk: d.get(kk, vv) for kk, vv in mapping.items()}
    if cache is not None and d:                      # cache only a real translation
        cache[_key("map", lang, mapping)] = out
    return out


def translate_edition(items, chrome, columns, categories, lang, client, model, cache=None):
    """Return (titems, tchrome, tcolumns, tcategories) translated into `lang`.

    `items` keep their kind/medium/link/source; only title/summary/tags change.
    The work is split across several small calls so a long edition cannot
    truncate. Anything that fails to translate is left in English. When a cache
    is supplied, the chrome and every story already translated are reused, so
    only genuinely new content costs an API call.
    """
    language = NAMES.get(lang, lang)

    # 1) Chrome + section labels: one small call, cached by source.
    meta = {
        "chrome": chrome,
        "columns": {k: v for k, v in columns},
        "categories": {k: v for k, v in categories},
    }
    m = None
    if cache is not None:
        mk = _key("meta", lang, meta)
        hit = cache.pop(mk, None)
        if isinstance(hit, dict):
            cache[mk] = hit                          # move to newest
            m = hit
    if not isinstance(m, dict):
        m = _translate_json(client, model, language, meta, 4096) or {}
        if cache is not None and m:
            cache[_key("meta", lang, meta)] = m
    mc = m.get("chrome") if isinstance(m.get("chrome"), dict) else {}
    tchrome = {k: mc.get(k, v) for k, v in chrome.items()}   # per-key fallback to English
    tcolumns = [(k, m.get("columns", {}).get(k, v)) for k, v in columns]
    tcategories = [(k, m.get("categories", {}).get(k, v)) for k, v in categories]

    # 2) Stories: reuse anything already translated; only new stories cost a call.
    done = {}                                        # global index -> {"title","summary","tags"}
    todo = []                                        # (index, source) still needing translation
    for i, it in enumerate(items):
        src = {"title": it["title"], "summary": it.get("summary", ""), "tags": it.get("tags", [])}
        hit = None
        if cache is not None:
            ik = _key("item", lang, src)
            hit = cache.pop(ik, None)
            if isinstance(hit, dict) and hit.get("title"):
                cache[ik] = hit                      # move to newest
        if isinstance(hit, dict) and hit.get("title"):
            done[i] = hit
        else:
            todo.append((i, src))

    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        payload = {"items": [{"i": idx, "title": src["title"],
                              "summary": src["summary"], "tags": src["tags"]}
                             for idx, src in chunk]}
        d = _translate_json(client, model, language, payload, 4096)
        rows = {r["i"]: r for r in d.get("items", [])
                if isinstance(r, dict) and isinstance(r.get("i"), int)}
        for idx, src in chunk:
            row = rows.get(idx)
            if isinstance(row, dict) and row.get("title"):
                rec = {"title": row.get("title", src["title"]),
                       "summary": row.get("summary", src["summary"]),
                       "tags": row.get("tags", src["tags"])}
                done[idx] = rec
                if cache is not None:
                    cache[_key("item", lang, src)] = rec
        time.sleep(0.4)                              # pace the API between batches

    # 3) Reassemble. Any story we could not translate stays English.
    titems = []
    for i, it in enumerate(items):
        d = done.get(i, {})
        copy = dict(it)                              # keep kind/medium/link/source
        copy["title"] = d.get("title", it["title"])
        copy["summary"] = d.get("summary", it.get("summary", ""))
        copy["tags"] = d.get("tags", it.get("tags", []))
        titems.append(copy)
    return titems, tchrome, tcolumns, tcategories


def translate_rows(rows, lang, client, model, cache=None):
    """Translate a list of {era,title,body} rows into `lang`, per-row cached.
    Stable rows (the XPRMNTL canon) translate once and are reused forever; only
    new rows cost a call. Years stay as written; anything that fails stays English."""
    language = NAMES.get(lang, lang)
    done, todo = {}, []
    for i, r in enumerate(rows):
        src = {"era": r.get("era", ""), "title": r.get("title", ""), "body": r.get("body", "")}
        hit = None
        if cache is not None:
            rk = _key("row", lang, src)
            hit = cache.pop(rk, None)
            if isinstance(hit, dict) and hit.get("title"):
                cache[rk] = hit                          # move to newest
        if isinstance(hit, dict) and hit.get("title"):
            done[i] = hit
        else:
            todo.append((i, src))
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        payload = {"rows": [{"i": idx, "era": s["era"], "title": s["title"], "body": s["body"]}
                            for idx, s in chunk]}
        d = _translate_json(client, model, language, payload, 4096)
        got = {r["i"]: r for r in d.get("rows", [])
               if isinstance(r, dict) and isinstance(r.get("i"), int)}
        for idx, s in chunk:
            row = got.get(idx)
            if isinstance(row, dict) and row.get("title"):
                rec = {"era": row.get("era", s["era"]),
                       "title": row.get("title", s["title"]),
                       "body": row.get("body", s["body"])}
                done[idx] = rec
                if cache is not None:
                    cache[_key("row", lang, s)] = rec
        time.sleep(0.4)                                  # pace the API between batches
    out = []
    for i, r in enumerate(rows):
        d = done.get(i, {})
        out.append({"era": d.get("era", r.get("era", "")),
                    "title": d.get("title", r.get("title", "")),
                    "body": d.get("body", r.get("body", ""))})
    return out


def _translate_json(client, model, language, obj, max_tokens, attempts=3):
    """Translate the VALUES of one small JSON object. Always returns a dict;
    returns {} on any error so the caller can fall back gracefully."""
    prompt = (
        f"Translate the VALUES in this JSON into {language} for an arts-and-letters "
        "newsletter. Translate ALL visible text, including taglines, section labels, "
        "category words, and descriptions, naturally and idiomatically. Keep UNCHANGED "
        "only these: any URLs; the names 'The Arts Wire', 'XPRMNTL', and 'Rey Parlá'; "
        "and publication or source names. Keep every JSON key and every integer 'i' "
        "field exactly, do not add, drop, merge, or reorder items, and keep HTML "
        "entities such as &middot; and &amp;, and any inline tags such as <em>, intact. "
        "Return ONLY the JSON.\n\n"
        + json.dumps(obj, ensure_ascii=False)
    )
    delay = 2.0
    for n in range(attempts):
        try:
            resp = client.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}])
            return _parse_obj(resp.content[0].text)
        except Exception:
            if n < attempts - 1:
                time.sleep(delay)              # gentle backoff for rate limits
                delay *= 2
    return {}


def _parse_obj(text):
    """Pull a JSON object out of a model reply. Never raises; {} on failure."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return {}
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return {}
