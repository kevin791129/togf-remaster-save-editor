# Shards in NativeData

Shards are stored in two places, and both must agree: a list of slots holding the shards
themselves, and a count per shard type. The code is
[togf_save/native/layout/shards.py](../togf_save/native/layout/shards.py) (offsets) and
[togf_save/native/shards.py](../togf_save/native/shards.py) (editing).

## Slots

| Offset | Size | Count | End (excl.) |
|---|---|---:|---|
| `0x76DC` | 4 bytes per slot | 199 slots | `0x79F8` |

Slot `n` is at `0x76DC + 4 × n`. Each slot is:

| Byte | Meaning | Range |
|---:|---|---|
| 0 | Type | 1–26 |
| 1 | Marker, always `0x02` | – |
| 2 | Nature | 1–54 |
| 3 | Strength | 1–10 |

- An empty slot is all zeros.
- A slot that isn't all zeros and doesn't have `0x02` in byte 1 is not a shard. The editor
  reports it as an error for that slot instead of failing the whole list, and refuses to
  overwrite it.
- Type and nature names are `shard.type.<n>` and `shard.nature.<n>` in
  `locales/<lang>/names.json`.

## Per-type counts

| Offset | Type | Entries |
|---|---|---|
| `0xA7D8 + t` | u8 | one per type `t` = 1–26 (`0xA7D9`–`0xA7F2`) |

- The count for type `t` is what the game shows for that type. It must equal the number of slots
  holding a shard of that type.
- `0xA7D8` itself (type 0) is not used.

## Keeping them in step

- **Putting or removing a shard** (`set_shard`) updates the type counts at the same time: the old
  shard's type goes down by one, and the new shard's type goes up by one. It refuses to go below 0
  or above 255, since either means the counts already don't match the slots.
- **Clearing** empties every slot and sets every type count to 0.
- **Mismatches** happen when slots are written another way, for example through the hex editor.
  The CLI (`shards`) and the web Shards tab list each type whose stored count differs from its
  slots.
- **Fixing** (`--fix-counts` in the CLI, "Fix counts" on the web) sets each count to the number of
  slots that hold that type.
