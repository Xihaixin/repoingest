"""面向服务器模板和前端的轻量级国际化（i18n）。

翻译以扁平的 JSON 字典形式存储在 ``src/server/i18n/`` 目录下。
模板通过 :func:`server.server_config.render_template` 接收 ``t`` 可调用对象
和 ``lang`` 变量；前端通过由 ``base.jinja`` 注入的 ``window.I18N``
接收相同的数据。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Request

# 支持的语言：代码 -> 显示名称。
LANGUAGES: dict[str, str] = {
    "en": "English",
    "zh-CN": "简体中文",
}

# 当没有浏览器/Cookie/查询提示时使用的回退语言。
DEFAULT_LANGUAGE = "zh-CN"

_I18N_DIR = Path(__file__).resolve().parent / "i18n"


def _load(lang: str) -> dict[str, str]:
    """加载某种语言的翻译字典（尽力而为）。"""
    path = _I18N_DIR / f"{lang}.json"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# 缓存已加载的字典（扁平字典，体积小）。
_TRANSLATIONS: dict[str, dict[str, str]] = {code: _load(code) for code in LANGUAGES}


def translate(key: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """将 ``key`` 翻译为 ``lang`` 语言，先回退到英文，再回退到键名。"""
    if lang not in _TRANSLATIONS:
        lang = DEFAULT_LANGUAGE
    value = _TRANSLATIONS[lang].get(key)
    if value is not None:
        return value
    return _TRANSLATIONS.get("en", {}).get(key, key)


def get_language(request: Request) -> str:
    """解析请求语言。

    优先级：``?lang=`` 查询参数 > ``lang`` Cookie >
    ``Accept-Language`` 请求头（zh* -> zh-CN, en* -> en）> 默认语言。
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
    """返回每个渲染模板共享的 i18n 上下文。"""
    lang = get_language(request)
    lang_dict = _TRANSLATIONS.get(lang, {})
    messages = {**_TRANSLATIONS.get("en", {}), **lang_dict}
    return {
        "request": request,
        "lang": lang,
        "t": lambda key: translate(key, lang),
        "messages": messages,
    }
