# Save file format

How a `SaveDat*.sav` file is built, from the outer container down to the game data. The code
is in [container.py](../togf_save/container.py) (layout, CRCs, backups),
[crypto.py](../togf_save/crypto.py) (AES), [codec.py](../togf_save/codec.py) (JSON) and
[folder.py](../togf_save/folder.py) (decoded folder).

```
SaveDat000.sav
├─ slot 1 area ─ [len][crc32][AES body] ─ JSON: load-menu summary, thumbnail
├─ slot 1 backup (identical copy)
├─ slot 2 area ─ [len][crc32][AES body] ─ JSON: NativeData (game state), NobleData
└─ slot 2 backup (identical copy of the record)
```

## Container

All integers are little-endian.

| Range | Size | Content |
|---|---|---|
| `0x00000`–`0x61000` | `0x61000` | Slot 1: a record, then a stale tail, then zero padding |
| `0x61000`–`0xC2000` | `0x61000` | Backup of slot 1 |
| `0xC2000`–`0xDD000` | `0x1B000` | Slot 2: a record, then zero padding |
| `0xDD000`–end of file | record length | Backup of the slot 2 record, not padded |

- The area sizes match the game's `SaveLoadManager.kAppParamSize` (`0x61000`) and
  `kAppNewDataSize` (`0x1B000`).
- The smallest file accepted is `0xDD008` bytes: everything up to the slot 2 backup, plus its
  8-byte header.

### Records

Each slot area starts with one record:

| Offset | Type | Content |
|---|---|---|
| `+0` | u32 | Body length in bytes |
| `+4` | u32 | CRC-32 of the body (zlib / IEEE polynomial) |
| `+8` | bytes | Body: the AES-encrypted JSON |

- The length must be non-zero and the record must fit in its area.
- **Stale tail:** the game reads only `length` bytes. When it writes a shorter record over a
  longer one, the end of the old record stays in slot 1's area. The game ignores it. The editor
  keeps it too, so an unedited save rebuilds byte for byte.
- A record can't be larger than its area: `0x61000` for slot 1 and `0x1B000` for slot 2, header
  included.

### Backups and damaged copies

- When reading, each slot uses its primary copy if the record is readable and its CRC matches.
  Otherwise it uses the backup, and the save gets a warning ("primary copy is damaged, using the
  backup"). If neither copy is valid, the save can't be loaded.
- When writing, both copies are written from the same record, so they are always identical.
- `info` (CLI) and the web Overview show each copy's offset, length, CRC and status, and whether
  the backup matches the primary.

## Encryption

Each record body is encrypted with AES-128-CBC and PKCS7 padding. This is the game's
`Noble.Encryption` scheme.

| Setting | Value |
|---|---|
| Key derivation | PBKDF2-HMAC-SHA1 (.NET `Rfc2898DeriveBytes`), 1000 rounds, 32 bytes |
| Password | `1123581321345589` |
| Salt | `saltString` |
| Key | Derived bytes 0–15 |
| IV | Derived bytes 16–31 |

- The key and IV are the same for every save. Because the IV is fixed, unchanged plaintext
  encrypts to the same bytes again.
- A body whose length isn't a positive multiple of 16, or whose padding is wrong after
  decryption, is rejected.

## Slot contents

Each decrypted body is UTF-8 JSON written by Newtonsoft.Json, sometimes with a UTF-8 BOM.
`byte[]` fields are base64 strings.

| Slot | Game type | Contents |
|---|---|---|
| 1 | `NobleAppFileParam` | Load-menu summary (`listParam`: play time, leader level, ...), the thumbnail (`capture`) and `pNativeSysParam` |
| 2 | `NobleAppDataParam` | `NativeData`: the game state written by the native engine (`GameNative.prx`). `NobleData`: remaster data |

- The editor treats a string as binary data when it is base64 (letters, digits, `+`, `/`, up to
  two `=`), at least 16 characters long, and a multiple of 4 in length. Shorter strings are too
  ambiguous.
- `NativeData` is mapped field by field in [character-block.md](character-block.md),
  [items.md](items.md), [shards.md](shards.md) and [misc.md](misc.md).

### Re-encoding

- An unedited slot is written back from its original JSON text. Together with the kept stale
  tail and the fixed IV, an unedited save re-encodes to exactly the same bytes.
- An edited slot is serialized again as compact JSON (no spaces), with keys in their original
  order, non-ASCII text kept as is, and the original BOM kept if there was one.
- Saving over an existing file first moves it to `<name>.bak`, but only if no `.bak` exists
  yet, so the backup stays the original file.

## Decoded folder

`togf-save decode` writes, and `encode` reads, a folder for editing with other tools:

| File | Content |
|---|---|
| `slot1.raw` | The whole slot 1 area, still encrypted. Keeps the stale tail. |
| `slot1.json` | Slot 1 JSON as stored. |
| `slot2.json` | Slot 2 JSON as stored. |
| `slot2.<field>.bin` | Each binary field of slot 2, decoded: `slot2.NativeData.bin`, `slot2.NobleData.bin`. |

On encode:

- The `.json` files are used as they are. If `slot1.json` is missing, slot 1 comes from the
  record in `slot1.raw`.
- A `.bin` file that differs from the field in `slot2.json` replaces that field. A size change
  is allowed, but gives a warning.
