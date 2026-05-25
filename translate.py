"""
translate.py  —  turn one edition into many languages
======================================================
Translates an assembled edition into any target language using Claude (the
same key the summaries use). One API call per language per edition (we cache
the whole edition, so we translate ONCE per language no matter how many
subscribers want it). Proper nouns, source names, and links are left intact.
Right-to-left languages (Arabic, Hebrew, Persian, Urdu) are flagged so the
page flips direction automatically.

If there's no API key, callers simply skip translation and ship English.
"""

import json
import re

RTL_LANGS = {"ar", "he", "fa", "ur", "yi"}

# Autonyms (a language shown in its own script) for the language switcher.
AUTONYMS = {
    "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch",
    "pt": "Português", "it": "Italiano", "nl": "Nederlands", "pl": "Polski",
    "ru": "Русский", "uk": "Українська", "tr": "Türkçe", "ar": "العربية",
    "he": "עברית", "fa": "فارسی", "ur": "اردو", "hi": "हिन्दी",
    "ja": "日本語", "ko": "한국어", "zh": "中文", "vi": "Tiếng Việt",
    "id": "Bahasa Indonesia", "th": "ไทย", "sw": "Kiswahili", "el": "Ελληνικά",
}

# English-language name, for the translation prompt.
NAMES = {
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "pl": "Polish", "ru": "Russian",
    "uk": "Ukrainian", "tr": "Turkish", "ar": "Arabic", "he": "Hebrew",
    "fa": "Persian", "ur": "Urdu", "hi": "Hindi", "ja": "Japanese",
    "ko": "Korean", "zh": "Chinese (Simplified)", "vi": "Vietnamese",
    "id": "Indonesian", "th": "Thai", "sw": "Swahili", "el": "Greek",
}


# BCP-47 / hreflang codes. Most match the short code; a few need script or
# region refinement so Google serves the right edition (esp. Chinese).
BCP47 = {
    "zh": "zh-Hans", "pt": "pt", "el": "el", "he": "he", "uk": "uk",
}


def bcp47(code):
    """The search-engine-correct language tag for a short code."""
    return BCP47.get(code, code)


def autonym(code):
    return AUTONYMS.get(code, code.upper())


def is_rtl(code):
    return code in RTL_LANGS


def translate_edition(items, chrome, columns, categories, lang, client, model):
    """Return (titems, tchrome, tcolumns, tcategories) translated into `lang`.
    `items` keep their kind/medium/link/source; only title/summary/tags change.
    """
    language = NAMES.get(lang, lang)
    bundle = {
        "chrome": chrome,
        "columns": {k: v for k, v in columns},
        "categories": {k: v for k, v in categories},
        "items": [{"i": i, "title": it["title"], "summary": it.get("summary", ""),
                   "tags": it.get("tags", [])} for i, it in enumerate(items)],
    }
    prompt = (
        f"Translate the VALUES in this JSON into {language} for an arts-and-letters "
        "newsletter. Rules: translate naturally and idiomatically (not literally); "
        "keep JSON keys, the integer 'i' fields, source names, and any URLs exactly "
        "as they are; do not add or drop items. Return ONLY the translated JSON.\n\n"
        + json.dumps(bundle, ensure_ascii=False)
    )
    resp = client.messages.create(
        model=model, max_tokens=8000,
        messages=[{"role": "user", "content": prompt}])
    data = _parse_obj(resp.content[0].text)

    tchrome = data.get("chrome", chrome)
    tcolumns = [(k, data.get("columns", {}).get(k, v)) for k, v in columns]
    tcategories = [(k, data.get("categories", {}).get(k, v)) for k, v in categories]

    by_i = {d["i"]: d for d in data.get("items", []) if "i" in d}
    titems = []
    for i, it in enumerate(items):
        d = by_i.get(i, {})
        copy = dict(it)                          # keep kind/medium/link/source
        copy["title"] = d.get("title", it["title"])
        copy["summary"] = d.get("summary", it.get("summary", ""))
        copy["tags"] = d.get("tags", it.get("tags", []))
        titems.append(copy)
    return titems, tchrome, tcolumns, tcategories


def _parse_obj(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1]) if s != -1 else {}
