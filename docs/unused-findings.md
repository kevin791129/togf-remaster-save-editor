# Findings not used by the editor yet

Things found in the save that the editor doesn't map or edit yet. Offsets are into the decoded
`slot2.NativeData`. They are kept here so they aren't lost, and so they can become tables once
there is enough to map them reliably.

## Monster kill counts (bestiary)

`0xB0F0`–`0xB240` is a long array of small u16 counts. It looks like a bestiary or kill-tracking
table.

Single offsets confirmed in game, by defeating the monster and seeing the value change:

| Offset | Type | Counts kills of |
|---|---|---|
| `0xB14E` | u16 | No. 178 |
| `0xB15A` | u16 | No. 225 |
| `0xB15C` | u16 | No. 220 |
| `0xB17E` | u16 | No. 210 |

- "No." is the monster's number in the in-game monster book.
- The array is not in monster-number order: No. 225 comes before No. 220, and No. 178 and No. 210
  are 0x30 bytes apart. A mapping from offset to monster number needs more data points before it
  can become a table.
- The start and end of the array are approximate.
