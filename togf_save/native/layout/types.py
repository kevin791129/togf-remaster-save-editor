"""Building blocks of the field map: tables of ints and single fields at fixed offsets.

Every table has the same interface (count, end, offset_of, fmt_of, max_of, flags_of,
entry_id, name_id, hint_id, number), so the editor, CLI and web treat them alike.
"""
from dataclasses import dataclass
from enum import IntFlag
from typing import Literal

_FORMATS = {1: "B", 2: "H", 4: "I", 8: "Q"}
_FLOAT_FORMATS = {4: "f"}  # f32; edited as whole numbers (see is_float)

Kind = Literal["uint", "float"]


def is_float(fmt: str) -> bool:
    """True for a struct format of a float field: read rounded, written as float(int)."""
    return fmt[-1] in _FLOAT_FORMATS.values()


class Flag(IntFlag):
    """Per-field behaviour. A FieldTable's flags apply to every field, on top of the field's own."""
    NONE = 0
    READ_ONLY = 1  # not written unless forced
    HIDDEN = 2  # left out of listings unless asked for
    SET_ALL = 4  # included by "set all" / "set all max"


def _int_max(size: int, limit: int | None) -> int:
    return (1 << 8 * size) - 1 if limit is None else limit


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
    flags: Flag = Flag.NONE  # applies to every entry
    hint_key: str = ""  # ui locale key of a hint for every entry; "" = none

    @property
    def fmt(self) -> str:
        return self.endian + _FORMATS[self.size]

    @property
    def max_value(self) -> int:
        return _int_max(self.size, self.limit)

    @property
    def end(self) -> int:
        """One past the last byte of the table."""
        return self.offset + (self.count - 1) * self.stride + self.size

    def _check(self, index: int) -> None:
        if not 0 <= index < self.count:
            raise IndexError(f"{self.id}: index {index} out of range 0-{self.count - 1}")

    def offset_of(self, index: int) -> int:
        self._check(index)
        return self.offset + index * self.stride

    def fmt_of(self, index: int) -> str:
        return self.fmt

    def max_of(self, index: int) -> int:
        return self.max_value

    def flags_of(self, index: int) -> Flag:
        self._check(index)
        return self.flags

    def entry_id(self, index: int) -> str:
        return f"{self.id}.{index}"

    def name_id(self, index: int) -> str:
        """Locale key of the entry's display name."""
        return self.entry_id(index)

    def hint_id(self, index: int) -> str:
        """ui locale key of the entry's hint; "" = no hint."""
        self._check(index)
        return self.hint_key

    def number(self, index: int) -> int:
        return self.first_number + index


@dataclass(frozen=True)
class Field:
    """One value of `size` bytes at `offset`; its entry id is `<table id>.<key>`.
    kind "uint": unsigned int. kind "float": f32, shown and edited as a whole number 0-limit."""
    key: str
    offset: int
    size: int
    limit: int | None = None  # in-game cap; None = whatever the int size holds (required for floats)
    endian: str = "<"
    flags: Flag = Flag.NONE  # added to the table's flags
    name_key: str = ""  # locale key of the display name, shareable between fields; defaults to the entry id
    hint_key: str | None = None  # ui locale key of a hint; None = the table's hint, "" = no hint
    kind: Kind = "uint"

    def __post_init__(self):
        formats = _FLOAT_FORMATS if self.kind == "float" else _FORMATS
        if self.size not in formats:
            raise ValueError(f"{self.key}: no {self.kind} of {self.size} bytes")
        if self.kind == "float" and self.limit is None:
            raise ValueError(f"{self.key}: a float field needs a limit")

    @property
    def fmt(self) -> str:
        return self.endian + (_FLOAT_FORMATS if self.kind == "float" else _FORMATS)[self.size]

    @property
    def max_value(self) -> int:
        return _int_max(self.size, self.limit)


@dataclass(frozen=True)
class FieldTable:
    """Unrelated single values, each with its own offset, size and cap.
    Same interface as IntTable, except there is no table-wide max (max_value is None)."""
    id: str
    fields: tuple[Field, ...]
    name_key: str = ""  # locale key of the table's name; defaults to `id`
    flags: Flag = Flag.NONE  # applies to every field, on top of the field's own
    hint_key: str = ""  # ui locale key of a hint for fields without their own; "" = none
    max_value = None

    @property
    def count(self) -> int:
        return len(self.fields)

    @property
    def end(self) -> int:
        """One past the last byte of any field."""
        return max(f.offset + f.size for f in self.fields)

    def field(self, index: int) -> Field:
        if not 0 <= index < self.count:
            raise IndexError(f"{self.id}: index {index} out of range 0-{self.count - 1}")
        return self.fields[index]

    def offset_of(self, index: int) -> int:
        return self.field(index).offset

    def fmt_of(self, index: int) -> str:
        return self.field(index).fmt

    def max_of(self, index: int) -> int:
        return self.field(index).max_value

    def flags_of(self, index: int) -> Flag:
        return self.flags | self.field(index).flags

    def entry_id(self, index: int) -> str:
        return f"{self.id}.{self.field(index).key}"

    def name_id(self, index: int) -> str:
        """Locale key of the field's display name."""
        return self.field(index).name_key or self.entry_id(index)

    def hint_id(self, index: int) -> str:
        """ui locale key of the field's hint; "" = no hint."""
        own = self.field(index).hint_key
        return self.hint_key if own is None else own

    def number(self, index: int) -> int:
        return index + 1
