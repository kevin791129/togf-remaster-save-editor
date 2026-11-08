"""Item counts: u8, contiguous, in in-game list order."""
from .types import Flag, IntTable

CONSUMABLE_LIMIT = 30
ITEM_LIMIT = 15


def _items(category: str, offset: int, count: int, limit: int = ITEM_LIMIT, first_number: int = 1) -> IntTable:
    return IntTable(f"item.{category}", offset, count, size=1, stride=1, limit=limit, first_number=first_number,
                    flags=Flag.SET_ALL)


# in-game numbering runs on through materials, sellables and ingredients
MATERIAL_COUNT, SELLABLE_COUNT = 123, 66

ITEMS = (
    _items("consumable", 0xA641, 35, limit=CONSUMABLE_LIMIT),
    _items("dish", 0xA664, 109),  # 0xA6D1-0xA6E0 after it: unmapped
    _items("material", 0xA6E1, MATERIAL_COUNT),
    _items("sellable", 0xA75C, SELLABLE_COUNT, first_number=1 + MATERIAL_COUNT),
    _items("ingredient", 0xA79E, 47, first_number=1 + MATERIAL_COUNT + SELLABLE_COUNT),  # 0xA7CD-0xA7D7 after it: unmapped
)
