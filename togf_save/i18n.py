"""Display names for data ids, one JSON file per language in togf_save/locales.

A file maps ids ("item.consumable.0", "shard.type.1", ...) to names, plus
"language.name" for the language's own name. Missing keys fall back to the default
language, then to the id itself.
"""
import json
from functools import cache
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANG = "zh-Hant"


def available() -> dict[str, str]:
    """{language code: language name} of all locale files."""
    return {p.stem: load(p.stem).get("language.name", p.stem) for p in sorted(LOCALES_DIR.glob("*.json"))}


@cache
def load(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        raise ValueError(f"unknown language {lang!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def name(key: str, lang: str = DEFAULT_LANG) -> str:
    return load(lang).get(key) or load(DEFAULT_LANG).get(key) or key
