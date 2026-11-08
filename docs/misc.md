# Misc values in NativeData

Single values that don't belong to a character, an item list or the shards. They make up the
`misc` table: each field has its own offset, size and cap, and its entry id is `misc.<key>`.
The code is [togf_save/native/layout/misc.py](../togf_save/native/layout/misc.py).

## Mapped

| Key | Offset | Type | Cap | Flags |
|---|---|---|---:|---|
| `gald` | `0x76D4` | u32 | 9999999 | SET_ALL |

- Gald sits just before the shard slots (see [shards.md](shards.md)). `0x76D8`–`0x76DB`, between
  gald and the first shard slot, is unmapped.

## Coming soon

More values have been found but not confirmed. They are not in the editor yet; once each is
checked in game, it will be added to the `misc` table.

| Offset | Type | Guess |
|---|---|---|
| `0xB9B0` | u32 | Battle count |
| `0xB9C4` | u32 | Gald earned (or spent) |
| `0xB9C8` | u32 | Gald spent (or earned) |

- Which of `0xB9C4` and `0xB9C8` is gald earned and which is gald spent is not known yet.
- Until they are mapped, these can be read and written through the web editor's raw hex access
  (`/api/sessions/{id}/native/hex`).
