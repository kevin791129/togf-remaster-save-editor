# Character blocks in NativeData

`slot2.NativeData` stores one block of `0xBD8` bytes per party member. Every block has the
same layout, so a field's offset is:

```
offset = 0x84 + char_index * 0xBD8 + rel
```

All values are little-endian.

| Index | Character | Block base | Tables built |
|---:|---|---|---|
| 0 | Asbel | `0x0084` | yes |
| 1 | Sophie | `0x0C5C` | yes |
| 2 | Hubert | `0x1834` | yes |
| 3 | Cheria | `0x240C` | yes |
| 4 | Malik | `0x2FE4` | yes |
| 5 | Pascal | `0x3BBC` | yes |
| 6 | Richard | `0x4794` | no, see [Richard](#richard) |

The code for this map is [togf_save/native/layout/characters.py](../togf_save/native/layout/characters.py).

## Tables

Each active character has four tables. Table ids are `<character>.<table>`, and an entry id is
`<table id>.<key>` (for example `asbel.stat.attack`), or `<table id>.<index>` for artes.

| Section | Table id | Kind | Range (rel) |
|---|---|---|---|
| Stats | `<char>.stat` | 11 named fields | `+0x000`–`+0x03B` |
| Artes | `<char>.arte` | u16 every 12 bytes | from `+0x6DE` |
| Combat counters | `<char>.counter` | 32 named fields | `+0xB14`–`+0xB61` |
| Battles together | `<char>.together` | u16 × 7, one per character | `+0xB62`–`+0xB6F` |

Names are shared between characters. A field's display name comes from a shared key
(`stat.attack`, `counter.items_stolen`, `character.pascal`), not from its entry id, so each name
is written once per language.

## Confidence

How sure each mapping is. These levels are documentation only; the editor and the UI don't show
them.

| Level | Meaning |
|---|---|
| CONFIRMED | Seen to change with the in-game action, and matches the in-game display. |
| LIKELY | Changes as expected, but not checked against an in-game number. |
| INFERRED | Not observed directly; follows from neighbouring confirmed fields. |
| GUESS | Position and size fit, but the meaning is a guess. |
| UNKNOWN | Size known, meaning not. |

## Flags

Each field can have these flags (`togf_save.native.layout.Flag`):

| Flag | Effect | Override |
|---|---|---|
| `READ_ONLY` | Writes are refused. | CLI `--force`; web `"force": true` / "Allow editing read-only" |
| `HIDDEN` | Left out of listings. | CLI `--show-hidden`; web `?show_hidden=true` / "Show hidden" |
| `SET_ALL` | Included by "set all" and "set all max". Without it, a field is only edited one at a time. A `READ_ONLY` field with `SET_ALL` is only bulk-written with force. | – |

## Stats

Verified against the in-game Status screen. The whole table is `READ_ONLY`: these values are tied
to each other and to the level curve, and the game recalculates some of them.

| Rel | Type | Key | Name | Confidence | Flags | Cap | Hint |
|---|---|---|---|---|---|---|---|
| `+0x000` | u32 | `exp` | EXP total | CONFIRMED | RO | – | `hint.linked_exp` |
| `+0x004` | u32 | `next` | EXP to next level | CONFIRMED | RO | – | `hint.linked_exp` |
| `+0x008` | u16 | `level` | Level | CONFIRMED | RO | 200 | `hint.linked_exp` |
| `+0x018` | u32 | `hp` | Current HP | CONFIRMED | RO | 9999 | `hint.linked_hp` |
| `+0x020` | f32 | `attack` | Attack (攻擊) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x024` | f32 | `arte_attack` | Arte Attack (術攻) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x028` | f32 | `accuracy` | Accuracy (命中) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x02C` | f32 | `defense` | Defense (防禦) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x030` | f32 | `arte_defense` | Arte Defense (術防) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x034` | f32 | `evasion` | Evasion (迴避) | CONFIRMED | RO, SET_ALL | 1999 | – |
| `+0x038` | f32 | `max_hp` | Max HP | CONFIRMED | RO | 9999 | `hint.linked_hp` |

- **Linked values:** EXP, NEXT and Level move together. Changing one alone leaves them out of step
  with the level curve. Current HP must not exceed Max HP.
- **f32 fields** are shown and edited as whole numbers. Reading rounds to the nearest integer
  (exact halves to the nearest even number, Python's `round`), and NaN or infinity read as 0.
  Writing stores `float(value)`. If the field already reads as the new value, nothing is written,
  so a stored fraction such as 812.6 survives an edit that doesn't change the shown number.
- `+0x00A`–`+0x017` and `+0x03C` onwards (up to the arte table) are unmapped.

## Artes

| Rel | Type | Count | Confidence | Flags | Cap | Hint |
|---|---|---|---|---|---|---|
| `+0x6DE + 12 × k` | u16 | per character | CONFIRMED | SET_ALL | 9999 | `hint.usage_count` (table-wide) |

- Each arte has a 12-byte record. Only its 2-byte usage count is mapped; the other 10 bytes are
  unknown.
- Arte counts: Asbel 36, Sophie 36, Hubert 31, Cheria 32, Malik 33, Pascal 32.
- The A-arte and B-arte totals in the combat counters are roughly the sum of every character's
  arte usage table.

## Combat counters

The layout is the same in every block, whether or not that character has a title that uses the
counter. Every visible counter is `SET_ALL`. Default caps: 9999 for u16, 9999999 for u32.

| Rel | Type | Key | Meaning | Confidence | Flags | Hint |
|---|---|---|---|---|---|---|
| `+0xB14` | u16 | `combo_15` | 15-hit combos | LIKELY | SET_ALL | `hint.combo_tier` |
| `+0xB16` | u16 | `combo_30` | 30-hit combos | LIKELY | SET_ALL | `hint.combo_tier` |
| `+0xB18` | u16 | `combo_50` | 50-hit combos | LIKELY | SET_ALL | `hint.combo_tier` |
| `+0xB1A` | u16 | `combo_100` | 100-hit combos | LIKELY | SET_ALL | `hint.combo_tier` |
| `+0xB1C` | u32 | `enemies_defeated` | Enemies defeated | CONFIRMED | SET_ALL | – |
| `+0xB20` | u32 | `defeated_2_at_once` | Defeated 2 enemies at once | LIKELY | SET_ALL | – |
| `+0xB24` | u32 | `defeated_4_at_once` | Defeated 4 enemies at once | CONFIRMED | SET_ALL | – |
| `+0xB28` | u32 | `unknown_b28` | ? (zero for all characters) | UNKNOWN | RO, HIDDEN | – |
| `+0xB2C` | u32 | `critical_hits` | Critical hits | CONFIRMED | SET_ALL | – |
| `+0xB30` | u32 | `weakness_hits` | Weakness hits | CONFIRMED | SET_ALL | – |
| `+0xB34` | u32 | `damage_received` | Damage received | LIKELY | SET_ALL | – |
| `+0xB38` | u16 | `quick_battles` | Battles ended within 10 s | GUESS | SET_ALL | – |
| `+0xB3A` | u16 | `cc1_artes` | CC1 artes used | INFERRED | SET_ALL | – |
| `+0xB3C` | u16 | `cc2_artes` | CC2 artes used | INFERRED | SET_ALL | – |
| `+0xB3E` | u16 | `cc3_artes` | CC3 artes used | INFERRED | SET_ALL | – |
| `+0xB40` | u16 | `cc4_artes` | CC4 artes used | CONFIRMED | SET_ALL | – |
| `+0xB42` | u16 | `unknown_b42` | ? (likely arte-related) | UNKNOWN | RO, HIDDEN | – |
| `+0xB44` | u16 | `a_artes` | A-arte uses, total | CONFIRMED | SET_ALL | – |
| `+0xB46` | u16 | `b_artes` | B-arte uses, total | CONFIRMED | SET_ALL | – |
| `+0xB48` | u16 | `items_stolen` | Items stolen | CONFIRMED | SET_ALL | – |
| `+0xB4A` | u16 | `items_received` | Items received after battle | CONFIRMED | SET_ALL | – |
| `+0xB4C` | u16 | `battles_controlled` | Battles won as the player-controlled character | LIKELY | SET_ALL | – |
| `+0xB4E` | u16 | `defended_poison` | Status defended: 劇毒 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB50` | u16 | `defended_paralysis` | Status defended: 麻痺 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB52` | u16 | `defended_freeze` | Status defended: 凍結 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB54` | u16 | `defended_burn` | Status defended: 燒傷 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB56` | u16 | `defended_petrify` | Status defended: 石化 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB58` | u16 | `defended_heavy` | Status defended: 笨重 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB5A` | u16 | `defended_seal` | Status defended: 封印 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB5C` | u16 | `defended_curse` | Status defended: 咒殺 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB5E` | u16 | `defended_weaken` | Status defended: 弱化 | GUESS | SET_ALL | `hint.status_defended` |
| `+0xB60` | u16 | `dishes_cooked` | Dishes cooked | GUESS | SET_ALL | – |

- The two UNKNOWN fields are hidden and read-only, so neither "set all" nor a normal edit touches
  them. They can still be seen with "show hidden" and written with force, or through the hex
  editor.
- `+0xAF2`–`+0xB00` hold small values that never changed (12, 1, 50, 40, 32, 80, …). They look
  like settings or fixed data, not counters, and are unmapped.

## Unlocking titles

Many titles are learned when a counter passes a threshold: an arte's usage count, or one of the
combat counters. The game checks the threshold when the counter goes up in play, not when the
save is loaded. To unlock such a title:

1. Set the counter at or above the title's threshold.
2. Load the save and perform that action once in game.

The character then learns the title, if that character has it and hasn't learned it yet. When a
title line has several thresholds, every threshold the counter has passed is learned at once.

Example: Asbel has titles for landing 50, 300 and 1500 critical hits. Set `asbel.counter`
`critical_hits` to 1500, then land one critical hit in battle. Asbel learns all three titles
that he doesn't already have.

## Battles together

| Rel | Type | Key | Confidence | Flags | Hint |
|---|---|---|---|---|---|
| `+0xB62 + 2 × partner_index` | u16 | partner id (`asbel` … `richard`) | CONFIRMED | RO (own slot also HIDDEN) | `hint.pair` (table-wide) |

- One u16 per character, in block order: 0 Asbel, 1 Sophie, 2 Hubert, 3 Cheria, 4 Malik,
  5 Pascal, 6 Richard. Richard's column is shown even though his own block isn't mapped yet.
- Each pair of characters in the active battle party gets +1. Reserve (non-party) characters are
  not counted.
- A character's own slot is always 0, so it's hidden.
- Mostly symmetric (A → B equals B → A), but some pairs are off by one, for example Asbel/Pascal
  477/478 and Hubert/Pascal 371/372. Each direction is its own value.
- The whole table is read-only, because editing one side leaves the pair out of step. To change
  a pair, force-edit both cells: `<a>.together.<b>` and `<b>.together.<a>`.
- No field is `SET_ALL`, so "set all" is refused even with force.

## Richard

- Richard's block (index 6, base `0x4794`) exists, but none of his tables are built yet:
  `ACTIVE_CHARACTERS` holds only the first six characters.
- His arte table would start at `0x4E72` (`0x4794 + 0x6DE`), with 26 artes. The count is
  unconfirmed, so the entry in `ARTE_COUNTS` is commented out.
- To enable him: add `"richard"` to `ACTIVE_CHARACTERS` and uncomment his line in `ARTE_COUNTS`
  in [characters.py](../togf_save/native/layout/characters.py). A test checks that the two stay in
  step. His stats, counters and battles-together tables then follow the same layout as everyone
  else's.
