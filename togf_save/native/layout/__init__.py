"""Known fields of slot2.NativeData, as offsets into the decoded bytes.

Found by diffing saves before and after single in-game changes. Display names are
not here: every entry has a stable id (`<table id>.<index>`, or `<table id>.<key>` in
a FieldTable) and a name key (the id, or a key shared between fields) that the locale
files in togf_save/locales map to names.

    types.py       Flag, IntTable, Field, FieldTable
    characters.py  per-character blocks (CHAR_BASE + index * CHAR_STRIDE): stats, arte
                   usage counts, combat counters, battles fought together
    items.py       item counts
    misc.py        single values (gald)
    shards.py      shard slots and per-type counts
"""
from .characters import (ACTIVE_CHARACTERS, ARTE_COUNTS, ARTE_LIMIT, ARTE_REL, ARTE_STRIDE, ARTES, CHAR_BASE,
                         CHAR_STRIDE, CHARACTER_SECTIONS, CHARACTERS, COUNTER_LIMITS, COUNTER_SPEC, COUNTERS, HP_LIMIT, LEVEL_LIMIT,
                         SECTIONS, STAT_LIMIT, STAT_SPEC, STATS, TOGETHER, TOGETHER_REL, char_offset)
from .items import CONSUMABLE_LIMIT, ITEM_LIMIT, ITEMS, MATERIAL_COUNT, SELLABLE_COUNT
from .misc import GALD_LIMIT, MISC
from .shards import (SHARD_COUNT_OFFSET, SHARD_MARKER, SHARD_MAX_STRENGTH, SHARD_NATURES, SHARD_OFFSET,
                     SHARD_SIZE, SHARD_SLOTS, SHARD_TYPES)
from .types import Field, FieldTable, Flag, IntTable, is_float

TABLES: dict[str, IntTable | FieldTable] = {
    t.id: t for t in ARTES + ITEMS + (MISC,) + STATS + COUNTERS + TOGETHER}
# Groups of the other tables; the per-character tables are listed by CHARACTER_SECTIONS instead.
GROUPS: dict[str, tuple[str, ...]] = {
    "items": tuple(t.id for t in ITEMS),
    "misc": (MISC.id,),
}

MIN_SIZE = max([t.end for t in TABLES.values()]
               + [SHARD_OFFSET + SHARD_SLOTS * SHARD_SIZE, SHARD_COUNT_OFFSET + SHARD_TYPES + 1])

__all__ = [
    "Flag", "IntTable", "Field", "FieldTable", "is_float",
    "CHAR_BASE", "CHAR_STRIDE", "CHARACTERS", "ACTIVE_CHARACTERS", "char_offset",
    "LEVEL_LIMIT", "HP_LIMIT", "STAT_LIMIT", "STAT_SPEC", "STATS",
    "ARTE_REL", "ARTE_STRIDE", "ARTE_LIMIT", "ARTE_COUNTS", "ARTES",
    "COUNTER_LIMITS", "COUNTER_SPEC", "COUNTERS", "TOGETHER_REL", "TOGETHER",
    "SECTIONS", "CHARACTER_SECTIONS",
    "CONSUMABLE_LIMIT", "ITEM_LIMIT", "MATERIAL_COUNT", "SELLABLE_COUNT", "ITEMS",
    "GALD_LIMIT", "MISC",
    "SHARD_OFFSET", "SHARD_SLOTS", "SHARD_SIZE", "SHARD_MARKER", "SHARD_COUNT_OFFSET",
    "SHARD_TYPES", "SHARD_NATURES", "SHARD_MAX_STRENGTH",
    "TABLES", "GROUPS", "MIN_SIZE",
]
