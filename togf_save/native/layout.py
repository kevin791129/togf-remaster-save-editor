"""Known fields of slot2.NativeData, as offsets into the decoded bytes.

Found by diffing saves before and after single in-game changes. Display names are
not here: every entry has a stable id (`<table id>.<index>`) that the locale files
in togf_save/locales map to names.
"""
from dataclasses import dataclass

_FORMATS = {1: "B", 2: "H", 4: "I", 8: "Q"}


@dataclass(frozen=True)
class IntTable:
    """`count` unsigned ints of `size` bytes, `stride` bytes apart, from `offset`."""
    id: str
    offset: int
    count: int
    size: int
    stride: int
    endian: str = "<"
    name_key: str = ""  # locale key of the table's name; defaults to `id`
    limit: int | None = None  # in-game cap; None = whatever the int size holds
    first_number: int = 1  # in-game list number of entry 0 (display only; indexes stay 0-based)

    @property
    def fmt(self) -> str:
        return self.endian + _FORMATS[self.size]

    @property
    def max_value(self) -> int:
        return (1 << 8 * self.size) - 1 if self.limit is None else self.limit

    @property
    def end(self) -> int:
        """One past the last byte of the table."""
        return self.offset + (self.count - 1) * self.stride + self.size

    def offset_of(self, index: int) -> int:
        if not 0 <= index < self.count:
            raise IndexError(f"{self.id}: index {index} out of range 0-{self.count - 1}")
        return self.offset + index * self.stride

    def entry_id(self, index: int) -> str:
        return f"{self.id}.{index}"

    def number(self, index: int) -> int:
        return self.first_number + index


# --- arte usage counts: u16 LE every 12 bytes, one block per character ---
ARTE_STRIDE = 12
ARTE_BLOCK = 0xBD8  # distance between character blocks
ARTE_LIMIT = 9999


def _artes(character: str, offset: int, count: int) -> IntTable:
    return IntTable(f"arte.{character}", offset, count, size=2, stride=ARTE_STRIDE,
                    name_key=f"character.{character}", limit=ARTE_LIMIT)


ARTES = (
    _artes("asbel", 0x0762, 36),
    _artes("sophie", 0x133A, 36),
    _artes("hubert", 0x1F12, 31),
    _artes("cheria", 0x2AEA, 32),
    _artes("malik", 0x36C2, 33),
    _artes("pascal", 0x429A, 32),
    # Richard: not found yet; 0x4E72 (= Pascal + ARTE_BLOCK) is the obvious guess.
    #_artes("richard", 0x4E72, 26),
)


# --- item counts: u8, contiguous, in in-game list order ---
CONSUMABLE_LIMIT = 30
ITEM_LIMIT = 15


def _items(category: str, offset: int, count: int, limit: int = ITEM_LIMIT, first_number: int = 1) -> IntTable:
    return IntTable(f"item.{category}", offset, count, size=1, stride=1, limit=limit, first_number=first_number)


# in-game numbering runs on through materials, sellables and ingredients
MATERIAL_COUNT, SELLABLE_COUNT = 123, 66

ITEMS = (
    _items("consumable", 0xA641, 35, limit=CONSUMABLE_LIMIT),
    _items("dish", 0xA664, 109),  # 0xA6D1-0xA6E0 after it: unmapped
    _items("material", 0xA6E1, MATERIAL_COUNT),
    _items("sellable", 0xA75C, SELLABLE_COUNT, first_number=1 + MATERIAL_COUNT),
    _items("ingredient", 0xA79E, 47, first_number=1 + MATERIAL_COUNT + SELLABLE_COUNT),  # 0xA7CD-0xA7D7 after it: unmapped
)

# --- misc single values (gald, ...): one-entry tables, e.g.
#   IntTable("misc.gald", 0x1234, 1, size=4, stride=4, limit=999999)
# with "misc.gald" / "misc.gald.0" names in the locale files. None mapped yet.
MISC: tuple[IntTable, ...] = ()

TABLES: dict[str, IntTable] = {t.id: t for t in ARTES + ITEMS + MISC}
GROUPS: dict[str, tuple[str, ...]] = {
    "artes": tuple(t.id for t in ARTES),
    "items": tuple(t.id for t in ITEMS),
    "misc": tuple(t.id for t in MISC),
}


# --- shards: 4-byte slots [type, SHARD_MARKER, nature, strength], all zero = empty ---
SHARD_OFFSET = 0x76DC
SHARD_SLOTS = 199
SHARD_SIZE = 4
SHARD_MARKER = 0x02
SHARD_COUNT_OFFSET = 0xA7D8  # u8 count of type t at SHARD_COUNT_OFFSET + t; must match the slots
SHARD_TYPES = 26  # 1-based
SHARD_NATURES = 54  # 1-based
SHARD_MAX_STRENGTH = 10

MIN_SIZE = max([t.end for t in TABLES.values()]
               + [SHARD_OFFSET + SHARD_SLOTS * SHARD_SIZE, SHARD_COUNT_OFFSET + SHARD_TYPES + 1])
