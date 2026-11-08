"""Per-character blocks: one CHAR_STRIDE-byte block per character, from CHAR_BASE.

Block base = CHAR_BASE + index * CHAR_STRIDE, index in CHARACTERS order. Offsets inside
a block (REL below) are the same for every character. Full map and notes on each
field: docs/character-block.md.

Sections per character (CHARACTER_SECTIONS): stats, artes, counters, together, with
table ids "<character>.<table>" (asbel.stat, asbel.arte, asbel.counter, asbel.together).
Field names are shared between characters through name_key ("stat.attack", ...).
"""
from .types import Field, FieldTable, Flag, IntTable

CHAR_BASE = 0x84
CHAR_STRIDE = 0xBD8
CHARACTERS = ("asbel", "sophie", "hubert", "cheria", "malik", "pascal", "richard")  # block order
# Characters whose tables are built. Richard's block exists but nothing in it is mapped yet;
# to enable him, add him here and give him an arte count below.
ACTIVE_CHARACTERS = CHARACTERS[:6]

RO, HIDDEN, SET_ALL = Flag.READ_ONLY, Flag.HIDDEN, Flag.SET_ALL


def char_offset(character: str | int, rel: int) -> int:
    """Absolute offset of `rel` (offset from the block base) in a character's block."""
    index = CHARACTERS.index(character) if isinstance(character, str) else character
    if not 0 <= index < len(CHARACTERS):
        raise IndexError(f"character index {index} out of range 0-{len(CHARACTERS) - 1}")
    return CHAR_BASE + index * CHAR_STRIDE + rel


def _fields(character: str, prefix: str, spec, limits: dict[int, int] | None = None) -> tuple[Field, ...]:
    """Fields of one character from (key, rel, size, extra Field kwargs) rows; names "<prefix>.<key>".
    `limits` gives a default cap by size, for rows without their own limit."""
    return tuple(Field(key, char_offset(character, rel), size, name_key=f"{prefix}.{key}",
                       **({"limit": limits[size]} if limits and "limit" not in extra else {}), **extra)
                 for key, rel, size, extra in spec)


# --- stats: the whole table is read-only ---
LEVEL_LIMIT = 200
HP_LIMIT = 9999
STAT_LIMIT = 1999  # attack .. evasion

_LINKED_EXP = {"hint_key": "hint.linked_exp"}
_LINKED_HP = {"hint_key": "hint.linked_hp"}
_STAT = {"kind": "float", "limit": STAT_LIMIT, "flags": SET_ALL}

STAT_SPEC = (
    ("exp", 0x000, 4, _LINKED_EXP),
    ("next", 0x004, 4, _LINKED_EXP),
    ("level", 0x008, 2, _LINKED_EXP | {"limit": LEVEL_LIMIT}),
    ("hp", 0x018, 4, _LINKED_HP | {"limit": HP_LIMIT}),
    ("attack", 0x020, 4, _STAT),
    ("arte_attack", 0x024, 4, _STAT),
    ("accuracy", 0x028, 4, _STAT),
    ("defense", 0x02C, 4, _STAT),
    ("arte_defense", 0x030, 4, _STAT),
    ("evasion", 0x034, 4, _STAT),
    ("max_hp", 0x038, 4, _LINKED_HP | {"kind": "float", "limit": HP_LIMIT}),
)


def _stats(character: str) -> FieldTable:
    return FieldTable(f"{character}.stat", _fields(character, "stat", STAT_SPEC), name_key="section.stats",
                      flags=RO)


# --- arte usage counts: u16 LE every 12 bytes (only the count of each 12-byte record is mapped) ---
ARTE_REL = 0x6DE
ARTE_STRIDE = 12
ARTE_LIMIT = 9999
ARTE_COUNTS = {
    "asbel": 36,
    "sophie": 36,
    "hubert": 31,
    "cheria": 32,
    "malik": 33,
    "pascal": 32,
    # "richard": 26,  # unconfirmed
}


def _artes(character: str) -> IntTable:
    return IntTable(f"{character}.arte", char_offset(character, ARTE_REL), ARTE_COUNTS[character],
                    size=2, stride=ARTE_STRIDE, name_key="section.artes", limit=ARTE_LIMIT,
                    flags=SET_ALL, hint_key="hint.usage_count")


# --- combat counters ---
COUNTER_LIMITS = {2: 9999, 4: 9999999}  # default cap by size: u16, u32

_COUNT = {"flags": SET_ALL}
_UNKNOWN = {"flags": RO | HIDDEN}

COUNTER_SPEC = (
    ("combo_15", 0xB14, 2, _COUNT),
    ("combo_30", 0xB16, 2, _COUNT),
    ("combo_50", 0xB18, 2, _COUNT),
    ("combo_100", 0xB1A, 2, _COUNT),
    ("enemies_defeated", 0xB1C, 4, _COUNT),
    ("defeated_2_at_once", 0xB20, 4, _COUNT),
    ("defeated_4_at_once", 0xB24, 4, _COUNT),
    ("unknown_b28", 0xB28, 4, _UNKNOWN),
    ("critical_hits", 0xB2C, 4, _COUNT),
    ("weakness_hits", 0xB30, 4, _COUNT),
    ("damage_received", 0xB34, 4, _COUNT),
    ("quick_battles", 0xB38, 2, _COUNT),
    ("cc1_artes", 0xB3A, 2, _COUNT),
    ("cc2_artes", 0xB3C, 2, _COUNT),
    ("cc3_artes", 0xB3E, 2, _COUNT),
    ("cc4_artes", 0xB40, 2, _COUNT),
    ("unknown_b42", 0xB42, 2, _UNKNOWN),
    ("a_artes", 0xB44, 2, _COUNT),
    ("b_artes", 0xB46, 2, _COUNT),
    ("items_stolen", 0xB48, 2, _COUNT),
    ("items_received", 0xB4A, 2, _COUNT),
    ("battles_controlled", 0xB4C, 2, _COUNT),
    ("defended_poison", 0xB4E, 2, _COUNT),
    ("defended_paralysis", 0xB50, 2, _COUNT),
    ("defended_freeze", 0xB52, 2, _COUNT),
    ("defended_burn", 0xB54, 2, _COUNT),
    ("defended_petrify", 0xB56, 2, _COUNT),
    ("defended_heavy", 0xB58, 2, _COUNT),
    ("defended_seal", 0xB5A, 2, _COUNT),
    ("defended_curse", 0xB5C, 2, _COUNT),
    ("defended_weaken", 0xB5E, 2, _COUNT),
    ("dishes_cooked", 0xB60, 2, {"flags": SET_ALL, "hint_key": "hint.dishes_cooked"}),
)


def _counters(character: str) -> FieldTable:
    return FieldTable(f"{character}.counter", _fields(character, "counter", COUNTER_SPEC, COUNTER_LIMITS),
                      name_key="section.counters", hint_key="hint.perform_count")


# --- battles fought together: u16 per partner, in CHARACTERS order; own slot hidden ---
TOGETHER_REL = 0xB62


def _together(character: str) -> FieldTable:
    fields = tuple(Field(partner, char_offset(character, TOGETHER_REL + 2 * j), 2,
                         name_key=f"character.{partner}",
                         flags=HIDDEN if partner == character else Flag.NONE)
                   for j, partner in enumerate(CHARACTERS))
    return FieldTable(f"{character}.together", fields, name_key="section.together",
                      flags=RO, hint_key="hint.pair")


ARTES = tuple(_artes(c) for c in ACTIVE_CHARACTERS)
STATS = tuple(_stats(c) for c in ACTIVE_CHARACTERS)
COUNTERS = tuple(_counters(c) for c in ACTIVE_CHARACTERS)
TOGETHER = tuple(_together(c) for c in ACTIVE_CHARACTERS)

SECTIONS = ("stats", "artes", "counters", "together")  # names: "section.<id>"
# {character: {section: table id}} for the active characters; table ids are "<character>.<table>"
CHARACTER_SECTIONS: dict[str, dict[str, str]] = {
    c: {"stats": f"{c}.stat", "artes": f"{c}.arte", "counters": f"{c}.counter", "together": f"{c}.together"}
    for c in ACTIVE_CHARACTERS
}
