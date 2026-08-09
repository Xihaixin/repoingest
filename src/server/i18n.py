"""Lightweight internationalization (i18n) for the server templates and frontend.

Translations are stored as flat JSON dictionaries under ``src/server/i18n/``.
Templates receive a ``t`` callable and a ``lang`` variable via
:func:`server.server_config.render_template`; the frontend receives the same
data through ``window.I18N`` injected by ``base.jinja``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request

# Supported languages: code -> display name.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh-CN": "简体中文",
}

# Fallback used when no browser/cookie/query hint is present.
DEFAULT_LANGUAGE = "zh-CN"

_I18N_DIR = Path(__file__).resolve().parent / "i18n"


def _load(lang: str) -> dict[str, str]:
    """Load the translation dictionary for a language (best effort)."""
    path = _I18N_DIR / f"{lang}.json"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# Cache loaded dictionaries (flat dicts, small).
_TRANSLATIONS: dict[str, dict[str, str]] = {code: _load(code) for code in LANGUAGES}


def translate(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """Translate ``key`` for ``lang``, falling back to English then the key."""
    if lang not in _TRANSLATIONS:
        lang = DEFAULT_LANGUAGE
    value = _TRANSLATIONS[lang].get(key)
    if value is not None:
        return value
    return _TRANSLATIONS.get("en", {}).get(key, key)


def get_language(request: Request) -> str:
    """Resolve the request language.

    Priority: ``?lang=`` query parameter > ``lang`` cookie >
    ``Accept-Language`` header (zh* -> zh-CN, en* -> en) > default.
    """
    query_lang = request.query_params.get("lang")
    if query_lang in LANGUAGES:
        return query_lang

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in LANGUAGES:
        return cookie_lang

    accept = request.headers.get("accept-language", "")
    for part in accept.split(","):
        code = part.split(";")[0].strip().lower()
        if code.startswith("zh"):
            return "zh-CN"
        if code.startswith("en"):
            return "en"

    return DEFAULT_LANGUAGE


def i18n_context(request: Request) -> dict[str, Any]:
    """Return the i18n context shared by every rendered template."""
    lang = get_language(request)
    lang_dict = _TRANSLATIONS.get(lang, {})
    messages = {**_TRANSLATIONS.get("en", {}), **lang_dict}
    return {
        "request": request,
        "lang": lang,
        "t": lambda key: translate(key, lang),
        "messages": messages,
    }
