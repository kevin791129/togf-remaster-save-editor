"""Misc single values: one field each, named "misc.<key>" in the locale files."""
from .types import Field, FieldTable, Flag

GALD_LIMIT = 9999999

MISC = FieldTable("misc", (
    Field("gald", 0x76D4, 4, limit=GALD_LIMIT, flags=Flag.SET_ALL),
))
