"""Localized text, one folder per language in togf_save/locales:

    <lang>/names.json   data names by id ("item.consumable.0", "shard.type.1", ...)
    <lang>/ui.json      interface text for the CLI and the website ("shards.used", ...),
                        str.format templates; "language.name" is the language's own name

Either file may be missing. Missing keys fall back to FALLBACK_LANG, then to the key itself.
The language used when none is given is $DEFAULT_LANG (also settable in .env), or FALLBACK_LANG.
"""
import json
import os
from functools import cache
from pathlib import Path
from typing import Literal

LOCALES_DIR = Path(__file__).parent / "locales"
FALLBACK_LANG = "ja"  # the complete locale: every key of every other language

Kind = Literal["names", "ui"]


def default_lang() -> str:
    return os.environ.get("DEFAULT_LANG") or FALLBACK_LANG


def available() -> dict[str, str]:
    """{language code: language name} of all locale folders."""
    return {p.name: load(p.name, "ui").get("language.name", p.name)
            for p in sorted(LOCALES_DIR.iterdir()) if p.is_dir()}


@cache
def load(lang: str, kind: Kind) -> dict[str, str]:
    folder = LOCALES_DIR / lang
    if not folder.is_dir():
        raise ValueError(f"unknown language {lang!r}")
    path = folder / f"{kind}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _lookup(kind: Kind, key: str, lang: str | None) -> str:
    return load(lang or default_lang(), kind).get(key) or load(FALLBACK_LANG, kind).get(key) or key


def name(key: str, lang: str | None = None) -> str:
    """Display name of a data id."""
    return _lookup("names", key, lang)


def text(key: str, lang: str | None = None, **values) -> str:
    """Interface text, formatted with `values`."""
    template = _lookup("ui", key, lang)
    return template.format(**values) if values else template


def ui_strings(lang: str | None = None) -> dict[str, str]:
    """All interface text for a language, with fallbacks filled in (for the website)."""
    return load(FALLBACK_LANG, "ui") | load(lang or default_lang(), "ui")
