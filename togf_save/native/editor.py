"""Read and edit slot2.NativeData through the field map in the layout package.

    native = NativeData(save.native)
    native.set("item.consumable", 0, 15)
    native.set_shard(0, Shard(type=1, nature=3, strength=10))
    save.native = native.to_bytes()

Field flags (layout.Flag): READ_ONLY fields are only written with force=True, HIDDEN
fields are left out of rows() unless show_hidden=True, and set_all / set_all_max only
touch SET_ALL fields. Shard operations live in shards.py (ShardSlots, mixed in here).
"""
import math
import struct

from .. import i18n
from ..errors import ReadOnlyError, SaveError
from . import layout as L
from .shards import Shard, ShardSlots

__all__ = ["NativeData", "Shard", "table", "set_all_indexes", "has_set_all"]


def table(table_id: str) -> L.IntTable | L.FieldTable:
    try:
        return L.TABLES[table_id]
    except KeyError:
        raise KeyError(f"unknown table {table_id!r}") from None


def set_all_indexes(t: L.IntTable | L.FieldTable, force: bool = False) -> list[int]:
    """Indexes that set_all / set_all_max write: SET_ALL entries, minus READ_ONLY ones unless forced."""
    return [i for i in range(t.count)
            if t.flags_of(i) & L.Flag.SET_ALL and (force or not t.flags_of(i) & L.Flag.READ_ONLY)]


def has_set_all(t: L.IntTable | L.FieldTable) -> bool:
    """Whether to offer "set all" for the table: some visible (not HIDDEN) entry is SET_ALL.
    It may still need force, if those entries are READ_ONLY."""
    return any(t.flags_of(i) & L.Flag.SET_ALL and not t.flags_of(i) & L.Flag.HIDDEN for i in range(t.count))


class NativeData(ShardSlots):
    def __init__(self, data: bytes):
        if len(data) < L.MIN_SIZE:
            raise SaveError(f"NativeData is {len(data):#x} bytes, expected at least {L.MIN_SIZE:#x}")
        self.data = bytearray(data)

    def to_bytes(self) -> bytes:
        return bytes(self.data)

    # --- tables (artes, items, misc, ...) ---

    def get(self, table_id: str, index: int) -> int:
        """The value as an int; float fields are rounded (NaN / infinity read as 0)."""
        t = table(table_id)
        fmt = t.fmt_of(index)
        value = struct.unpack_from(fmt, self.data, t.offset_of(index))[0]
        if L.is_float(fmt):
            return round(value) if math.isfinite(value) else 0
        return value

    def set(self, table_id: str, index: int, value: int, force: bool = False) -> None:
        """Write an int. A float field is stored as float(value), and left untouched when it
        already reads as `value`, so its fractional part survives a no-op edit."""
        t = table(table_id)
        if t.flags_of(index) & L.Flag.READ_ONLY and not force:
            raise ReadOnlyError(f"{t.entry_id(index)} is read-only (force to write it)")
        top = t.max_of(index)
        if not isinstance(value, int) or not 0 <= value <= top:
            raise ValueError(f"{t.entry_id(index)}: value {value!r} out of range 0-{top}")
        fmt = t.fmt_of(index)
        if L.is_float(fmt):
            if self.get(table_id, index) == value:
                return
            value = float(value)
        struct.pack_into(fmt, self.data, t.offset_of(index), value)

    def values(self, table_id: str) -> list[int]:
        return [self.get(table_id, i) for i in range(table(table_id).count)]

    def _bulk_indexes(self, table_id: str, force: bool) -> list[int]:
        indexes = set_all_indexes(table(table_id), force)
        if not indexes:
            raise ValueError(f"{table_id}: no entries can be set all at once"
                             + ("" if force else " (read-only ones need force)"))
        return indexes

    def set_all(self, table_id: str, value: int, force: bool = False) -> None:
        """Every SET_ALL entry to `value` (READ_ONLY ones only with force).
        Checked against every entry first, so a bad value changes nothing."""
        t = table(table_id)
        indexes = self._bulk_indexes(table_id, force)
        for i in indexes:
            top = t.max_of(i)
            if not isinstance(value, int) or not 0 <= value <= top:
                raise ValueError(f"{t.entry_id(i)}: value {value!r} out of range 0-{top}")
        for i in indexes:
            self.set(table_id, i, value, force=True)

    def set_all_max(self, table_id: str, force: bool = False) -> None:
        """Every SET_ALL entry to its own max (READ_ONLY ones only with force)."""
        t = table(table_id)
        for i in self._bulk_indexes(table_id, force):
            self.set(table_id, i, t.max_of(i), force=True)

    def rows(self, table_id: str, lang: str | None = None, show_hidden: bool = False) -> list[dict]:
        """Table entries with in-game number, id, display name, offset, max, current value,
        flags and hint text ("" for none). HIDDEN entries only with show_hidden."""
        t = table(table_id)
        rows = []
        for i in range(t.count):
            flags = t.flags_of(i)
            if flags & L.Flag.HIDDEN and not show_hidden:
                continue
            hint = t.hint_id(i)
            rows.append({"index": i, "number": t.number(i), "id": t.entry_id(i), "name": i18n.name(t.name_id(i), lang),
                         "offset": t.offset_of(i), "max": t.max_of(i), "value": self.get(table_id, i),
                         "read_only": bool(flags & L.Flag.READ_ONLY), "hidden": bool(flags & L.Flag.HIDDEN),
                         "set_all": bool(flags & L.Flag.SET_ALL), "hint": i18n.text(hint, lang) if hint else ""})
        return rows
