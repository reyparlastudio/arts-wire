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


def translate_map(mapping, lang, client, model):
    """Translate the values of a flat {key: text} map into `lang`.
    One call, with per-key fallback to English so nothing is ever lost."""
    language = NAMES.get(lang, lang)
    d = _translate_json(client, model, language, mapping, 4096)
    if not isinstance(d, dict):
        d = {}
    return {k: d.get(k, v) for k, v in mapping.items()}


def translate_edition(items, chrome, columns, categories, lang, client, model):
    """Return (titems, tchrome, tcolumns, tcategories) translated into `lang`.

    `items` keep their kind/medium/link/source; only title/summary/tags change.
    The work is split across several small calls so a long edition cannot
    truncate. Anything that fails to translate is left in English.
    """
    language = NAMES.get(lang, lang)

    # 1) Chrome + section labels: one small call.
    meta = {
        "chrome": chrome,
        "columns": {k: v for k, v in columns},
        "categories": {k: v for k, v in categories},
    }
    m = _translate_json(client, model, language, meta, 4096) or {}
    mc = m.get("chrome") if isinstance(m.get("chrome"), dict) else {}
    tchrome = {k: mc.get(k, v) for k, v in chrome.items()}   # per-key fallback to English
    tcolumns = [(k, m.get("columns", {}).get(k, v)) for k, v in columns]
    tcategories = [(k, m.get("categories", {}).get(k, v)) for k, v in categories]

    # 2) Stories: small batches, each call independent and retried once.
    done = {}  # global index -> {"title","summary","tags"}
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        payload = {"items": [
            {"i": start + j, "title": it["title"],
             "summary": it.get("summary", ""), "tags": it.get("tags", [])}
            for j, it in enumerate(chunk)]}
        d = _translate_json(client, model, language, payload, 4096)
        for row in d.get("items", []):
            if isinstance(row, dict) and isinstance(row.get("i"), int):
                done[row["i"]] = row
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
        "entities such as &middot; and &amp; intact. Return ONLY the JSON.\n\n"
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
