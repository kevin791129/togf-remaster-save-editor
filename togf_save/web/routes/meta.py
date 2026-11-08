"""GET /api/meta: languages, interface text, and the list of tables and shard values."""
from fastapi import APIRouter

from ... import __version__, i18n
from ...native import has_set_all, layout as L, table as get_table
from ..deps import Lang, check_lang

router = APIRouter(prefix="/api", tags=["meta"])


def _table_info(tid: str, name: str) -> dict:
    t = get_table(tid)
    return {"id": tid, "name": name, "count": t.count, "max": t.max_value, "set_all": has_set_all(t)}


@router.get("/meta")
def meta(lang: Lang = None):
    lang = check_lang(lang)
    return {
        "version": __version__,
        "languages": i18n.available(),
        "default_lang": i18n.default_lang(),
        "ui": i18n.ui_strings(lang),
        "characters": [{"id": c, "name": i18n.name(f"character.{c}", lang),
                        "tables": [_table_info(tid, i18n.name(f"section.{section}", lang)) | {"section": section}
                                   for section, tid in sections.items()]}
                       for c, sections in L.CHARACTER_SECTIONS.items()],
        "groups": [{"id": g, "name": i18n.text(f"group.{g}", lang),
                    "tables": [_table_info(tid, i18n.name(get_table(tid).name_key or tid, lang)) for tid in ids]}
                   for g, ids in L.GROUPS.items()],
        "shards": {
            "name": i18n.text("group.shards", lang),
            "slots": L.SHARD_SLOTS,
            "types": [{"value": n, "name": i18n.name(f"shard.type.{n}", lang)}
                      for n in range(1, L.SHARD_TYPES + 1)],
            "natures": [{"value": n, "name": i18n.name(f"shard.nature.{n}", lang)}
                        for n in range(1, L.SHARD_NATURES + 1)],
            "max_strength": L.SHARD_MAX_STRENGTH,
        },
    }
