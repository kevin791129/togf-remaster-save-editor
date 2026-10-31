"""Read and edit slot2.NativeData through the field map in layout.py.

    native = NativeData(save.native)
    native.set("item.consumable", 0, 15)
    native.set_shard(0, Shard(type=1, nature=3, strength=10))
    save.native = native.to_bytes()
"""
import struct
from dataclasses import dataclass

from .. import i18n
from ..errors import SaveError
from . import layout as L


@dataclass(frozen=True)
class Shard:
    type: int  # 1-SHARD_TYPES
    nature: int  # 1-SHARD_NATURES
    strength: int  # 1-SHARD_MAX_STRENGTH

    def __post_init__(self):
        for field, value, top in (("type", self.type, L.SHARD_TYPES),
                                  ("nature", self.nature, L.SHARD_NATURES),
                                  ("strength", self.strength, L.SHARD_MAX_STRENGTH)):
            if not isinstance(value, int) or not 1 <= value <= top:
                raise ValueError(f"shard {field} {value!r} out of range 1-{top}")

    def to_bytes(self) -> bytes:
        return bytes([self.type, L.SHARD_MARKER, self.nature, self.strength])

    @classmethod
    def from_bytes(cls, raw: bytes) -> "Shard | None":
        """None for an empty (all-zero) slot; ValueError if the bytes are not a shard."""
        if not any(raw):
            return None
        if len(raw) != L.SHARD_SIZE or raw[1] != L.SHARD_MARKER:
            raise ValueError(f"not a shard: {raw.hex(' ')}")
        return cls(raw[0], raw[2], raw[3])


def table(table_id: str) -> L.IntTable:
    try:
        return L.TABLES[table_id]
    except KeyError:
        raise KeyError(f"unknown table {table_id!r}") from None


class NativeData:
    def __init__(self, data: bytes):
        if len(data) < L.MIN_SIZE:
            raise SaveError(f"NativeData is {len(data):#x} bytes, expected at least {L.MIN_SIZE:#x}")
        self.data = bytearray(data)

    def to_bytes(self) -> bytes:
        return bytes(self.data)

    # --- int tables (artes, items) ---

    def get(self, table_id: str, index: int) -> int:
        t = table(table_id)
        return struct.unpack_from(t.fmt, self.data, t.offset_of(index))[0]

    def set(self, table_id: str, index: int, value: int) -> None:
        t = table(table_id)
        if not isinstance(value, int) or not 0 <= value <= t.max_value:
            raise ValueError(f"{t.entry_id(index)}: value {value!r} out of range 0-{t.max_value}")
        struct.pack_into(t.fmt, self.data, t.offset_of(index), value)

    def values(self, table_id: str) -> list[int]:
        return [self.get(table_id, i) for i in range(table(table_id).count)]

    def set_all(self, table_id: str, value: int) -> None:
        for i in range(table(table_id).count):
            self.set(table_id, i, value)

    def rows(self, table_id: str, lang: str | None = None) -> list[dict]:
        """Table entries with in-game number, id, display name, offset and current value."""
        t = table(table_id)
        return [{"index": i, "number": t.number(i), "id": t.entry_id(i), "name": i18n.name(t.entry_id(i), lang),
                 "offset": t.offset_of(i), "value": self.get(table_id, i)} for i in range(t.count)]

    # --- shards ---

    @staticmethod
    def _shard_offset(slot: int) -> int:
        if not 0 <= slot < L.SHARD_SLOTS:
            raise IndexError(f"shard slot {slot} out of range 0-{L.SHARD_SLOTS - 1}")
        return L.SHARD_OFFSET + slot * L.SHARD_SIZE

    def shard_raw(self, slot: int) -> bytes:
        pos = self._shard_offset(slot)
        return bytes(self.data[pos:pos + L.SHARD_SIZE])

    def shard(self, slot: int) -> Shard | None:
        try:
            return Shard.from_bytes(self.shard_raw(slot))
        except ValueError as e:
            raise ValueError(f"shard slot {slot}: {e}") from None

    def shards(self) -> list[Shard | None]:
        return [self.shard(s) for s in range(L.SHARD_SLOTS)]

    def shard_count(self, shard_type: int) -> int:
        """Stored per-type count byte (what the game shows), not a count of the slots."""
        return self.data[L.SHARD_COUNT_OFFSET + shard_type]

    def set_shard(self, slot: int, shard: Shard | None) -> None:
        """Put `shard` in `slot` (None empties it), keeping the per-type counts in step."""
        old = self.shard(slot)  # raises if the slot holds something that is not a shard
        if old == shard:
            return
        if old is not None:
            if self.shard_count(old.type) == 0:
                raise SaveError(f"count of shard type {old.type} is already 0; counts don't match the slots")
            self.data[L.SHARD_COUNT_OFFSET + old.type] -= 1
        if shard is not None:
            if self.shard_count(shard.type) == 0xFF:
                raise SaveError(f"count of shard type {shard.type} is already 255")
            self.data[L.SHARD_COUNT_OFFSET + shard.type] += 1
        pos = self._shard_offset(slot)
        self.data[pos:pos + L.SHARD_SIZE] = shard.to_bytes() if shard else bytes(L.SHARD_SIZE)

    def clear_shards(self) -> None:
        """Empty every slot and zero every per-type count."""
        self.data[L.SHARD_OFFSET:L.SHARD_OFFSET + L.SHARD_SLOTS * L.SHARD_SIZE] = \
            bytes(L.SHARD_SLOTS * L.SHARD_SIZE)
        self.data[L.SHARD_COUNT_OFFSET + 1:L.SHARD_COUNT_OFFSET + 1 + L.SHARD_TYPES] = bytes(L.SHARD_TYPES)

    def shard_count_mismatches(self) -> dict[int, tuple[int, int]]:
        """{type: (stored count, slots holding that type)} for every type that disagrees."""
        actual = [0] * (L.SHARD_TYPES + 1)
        for s in self.shards():
            if s is not None:
                actual[s.type] += 1
        return {t: (self.shard_count(t), actual[t]) for t in range(1, L.SHARD_TYPES + 1)
                if self.shard_count(t) != actual[t]}

    def fix_shard_counts(self) -> None:
        for t, (_, actual) in self.shard_count_mismatches().items():
            self.data[L.SHARD_COUNT_OFFSET + t] = actual

    def shard_rows(self, lang: str | None = None) -> list[dict]:
        """Every slot with its raw bytes and, if it holds a shard, values and names.
        A slot with unrecognised bytes gets an "error" instead of failing the whole list."""
        rows = []
        for slot in range(L.SHARD_SLOTS):
            row = {"slot": slot, "offset": self._shard_offset(slot), "raw": self.shard_raw(slot).hex(" "),
                   "shard": None}
            try:
                s = self.shard(slot)
            except ValueError as e:
                row["error"] = str(e)
            else:
                if s is not None:
                    row["shard"] = {"type": s.type, "nature": s.nature, "strength": s.strength,
                                    "type_name": i18n.name(f"shard.type.{s.type}", lang),
                                    "nature_name": i18n.name(f"shard.nature.{s.nature}", lang)}
            rows.append(row)
        return rows
