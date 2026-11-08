# Items in NativeData

Item counts are single bytes (u8), stored contiguously in the order of the in-game item list.
The code for this map is [togf_save/native/layout/items.py](../togf_save/native/layout/items.py).
Gald is in [misc.md](misc.md).

## Item tables

| Table id | Category | Start | End (incl.) | Entries | Cap | In-game numbers |
|---|---|---|---|---:|---:|---|
| `item.consumable` | Consumables | `0xA641` | `0xA663` | 35 | 30 | 1–35 |
| `item.dish` | Dishes | `0xA664` | `0xA6D0` | 109 | 15 | 1–109 |
| `item.material` | Materials | `0xA6E1` | `0xA75B` | 123 | 15 | 1–123 |
| `item.sellable` | Sellables | `0xA75C` | `0xA79D` | 66 | 15 | 124–189 |
| `item.ingredient` | Ingredients | `0xA79E` | `0xA7CC` | 47 | 15 | 190–236 |

- Entry `k` of a table is at `start + k`, and its entry id is `item.<category>.<k>` (0-based).
- **Numbering:** the game numbers materials, sellables and ingredients as one list, so sellables
  start at 124 and ingredients at 190. The numbers are for display only; indexes stay 0-based.
- **Caps:** consumables go up to 30 and everything else up to 15, matching the in-game maximum.
- **Bulk edits:** every item entry has the `SET_ALL` flag, so "set all" and "set all max" apply.
  None are read-only or hidden.
- **Names:** `item.<category>.<k>` in `locales/<lang>/names.json`. Entries without a name show
  their id.

## Unmapped gaps

| Range | Notes |
|---|---|
| `0xA6D1`–`0xA6E0` | 16 bytes between dishes and materials. |
| `0xA7CD`–`0xA7D7` | 11 bytes between ingredients and the shard counts (see [shards.md](shards.md)). |
