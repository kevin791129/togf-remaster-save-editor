"""Per-character tables: stats, combat counters, battles fought together (layout/characters.py)."""
import struct

import pytest

from togf_save import ReadOnlyError, i18n
from togf_save.native import NativeData, layout as L, set_all_indexes

from .helpers import NATIVE_SIZE

F = L.Flag
BLOCK = {c: 0x84 + i * 0xBD8 for i, c in enumerate(L.CHARACTERS)}


@pytest.fixture
def native() -> NativeData:
    return NativeData(bytes(NATIVE_SIZE))


def _index(table_id: str, key: str) -> int:
    t = L.TABLES[table_id]
    return next(i for i in range(t.count) if t.entry_id(i) == f"{table_id}.{key}")


# --- layout ---

def test_sections():
    assert tuple(L.CHARACTER_SECTIONS) == L.ACTIVE_CHARACTERS
    for c, sections in L.CHARACTER_SECTIONS.items():
        assert tuple(sections) == L.SECTIONS
        assert all(tid in L.TABLES for tid in sections.values()), c


@pytest.mark.parametrize("character", ["asbel", "pascal"])
def test_tables_stay_in_their_block(character):
    lo, hi = BLOCK[character], BLOCK[character] + L.CHAR_STRIDE
    for tid in L.CHARACTER_SECTIONS[character].values():
        t = L.TABLES[tid]
        assert all(lo <= t.offset_of(i) and t.offset_of(i) + struct.calcsize(t.fmt_of(i)) <= hi
                   for i in range(t.count)), tid


@pytest.mark.parametrize("table_id,key,offset,fmt", [
    ("asbel.stat", "exp", 0x84, "<I"),
    ("asbel.stat", "next", 0x88, "<I"),
    ("asbel.stat", "level", 0x8C, "<H"),
    ("asbel.stat", "hp", 0x9C, "<I"),
    ("asbel.stat", "attack", 0xA4, "<f"),
    ("asbel.stat", "evasion", 0xB8, "<f"),
    ("asbel.stat", "max_hp", 0xBC, "<f"),
    ("sophie.stat", "attack", 0x84 + 0xBD8 + 0x20, "<f"),
    ("pascal.counter", "combo_15", 0x84 + 5 * 0xBD8 + 0xB14, "<H"),
    ("pascal.counter", "enemies_defeated", 0x84 + 5 * 0xBD8 + 0xB1C, "<I"),
    ("pascal.counter", "damage_received", 0x84 + 5 * 0xBD8 + 0xB34, "<I"),
    ("pascal.counter", "quick_battles", 0x84 + 5 * 0xBD8 + 0xB38, "<H"),
    ("pascal.counter", "dishes_cooked", 0x84 + 5 * 0xBD8 + 0xB60, "<H"),
    ("asbel.together", "asbel", 0x84 + 0xB62, "<H"),
    ("pascal.together", "richard", 0x84 + 5 * 0xBD8 + 0xB62 + 12, "<H"),
])
def test_offsets(table_id, key, offset, fmt):
    t = L.TABLES[table_id]
    i = _index(table_id, key)
    assert (t.offset_of(i), t.fmt_of(i)) == (offset, fmt)


def test_counters_are_contiguous():
    t = L.TABLES["asbel.counter"]
    ends = [t.offset_of(i) + struct.calcsize(t.fmt_of(i)) for i in range(t.count)]
    assert [t.offset_of(i) for i in range(1, t.count)] == ends[:-1]
    assert t.offset_of(0) == BLOCK["asbel"] + 0xB14 and t.end == BLOCK["asbel"] + 0xB62
    assert t.end == L.TABLES["asbel.together"].offset_of(0)


@pytest.mark.parametrize("key,limit", [("level", 200), ("hp", 9999), ("max_hp", 9999), ("attack", 1999),
                                       ("arte_attack", 1999), ("accuracy", 1999), ("defense", 1999),
                                       ("arte_defense", 1999), ("evasion", 1999)])
def test_stat_limits(key, limit):
    assert L.TABLES["cheria.stat"].max_of(_index("cheria.stat", key)) == limit


def test_stat_flags():
    t = L.TABLES["asbel.stat"]
    flags = {t.field(i).key: t.flags_of(i) for i in range(t.count)}
    assert all(f & F.READ_ONLY for f in flags.values())
    assert {k for k, f in flags.items() if f & F.SET_ALL} == {
        "attack", "arte_attack", "accuracy", "defense", "arte_defense", "evasion"}
    assert not any(f & F.HIDDEN for f in flags.values())
    assert set_all_indexes(t) == []


def test_counter_flags():
    t = L.TABLES["malik.counter"]
    flags = {t.field(i).key: t.flags_of(i) for i in range(t.count)}
    hidden = {k for k, f in flags.items() if f & F.HIDDEN}
    assert hidden == {"unknown_b28", "unknown_b42"}
    assert all(flags[k] & F.READ_ONLY and not flags[k] & F.SET_ALL for k in hidden)
    assert all(f == F.SET_ALL for k, f in flags.items() if k not in hidden)


def test_counter_limits():
    t = L.TABLES["asbel.counter"]
    for i in range(t.count):
        assert t.max_of(i) == {2: 9999, 4: 9999999}[t.field(i).size], t.entry_id(i)


def test_counter_set_all_max(native):
    native.set_all_max("asbel.counter")
    assert native.get("asbel.counter", _index("asbel.counter", "enemies_defeated")) == 9999999
    assert native.get("asbel.counter", _index("asbel.counter", "items_stolen")) == 9999
    assert native.get("asbel.counter", _index("asbel.counter", "unknown_b28")) == 0


def test_together_flags():
    t = L.TABLES["hubert.together"]
    assert t.count == len(L.CHARACTERS)  # Richard's column included
    assert all(t.flags_of(i) & F.READ_ONLY and not t.flags_of(i) & F.SET_ALL for i in range(t.count))
    assert [t.field(i).key for i in range(t.count) if t.flags_of(i) & F.HIDDEN] == ["hubert"]
    assert set_all_indexes(t) == set_all_indexes(t, force=True) == []


@pytest.mark.parametrize("table_id,key,hint", [
    ("asbel.stat", "exp", "hint.linked_exp"),
    ("asbel.stat", "level", "hint.linked_exp"),
    ("asbel.stat", "hp", "hint.linked_hp"),
    ("asbel.stat", "max_hp", "hint.linked_hp"),
    ("asbel.stat", "attack", ""),
    ("asbel.counter", "combo_100", "hint.perform_count"),  # the table's hint
    ("asbel.counter", "defended_seal", "hint.perform_count"),
    ("asbel.counter", "critical_hits", "hint.perform_count"),
    ("asbel.counter", "dishes_cooked", "hint.dishes_cooked"),  # its own hint overrides the table's
    ("asbel.together", "sophie", "hint.pair"),
])
def test_hints(table_id, key, hint):
    assert L.TABLES[table_id].hint_id(_index(table_id, key)) == hint


def test_names_are_shared_between_characters():
    for section, key, name_key in (("stat", "attack", "stat.attack"), ("counter", "items_stolen", "counter.items_stolen"),
                                   ("together", "richard", "character.richard")):
        ids = {L.TABLES[f"{c}.{section}"].name_id(_index(f"{c}.{section}", key)) for c in L.ACTIVE_CHARACTERS}
        assert ids == {name_key}


def test_every_name_and_hint_is_translated():
    for lang in i18n.available():
        names, ui = i18n.load(lang, "names"), i18n.load(lang, "ui")
        for c in L.ACTIVE_CHARACTERS:
            for tid in L.CHARACTER_SECTIONS[c].values():
                t = L.TABLES[tid]
                assert t.name_key in names, (lang, tid)
                for i in range(t.count):
                    if isinstance(t, L.FieldTable):
                        assert t.name_id(i) in names, (lang, t.entry_id(i))
                    assert t.hint_id(i) == "" or t.hint_id(i) in ui, (lang, t.entry_id(i))
        assert all(f"section.{s}" in names for s in L.SECTIONS), lang


# --- editing ---

def test_stat_set_all_max_touches_the_six_stats(native):
    with pytest.raises(ValueError, match="no entries"):
        native.set_all_max("asbel.stat")  # all read-only: needs force
    native.set_all_max("asbel.stat", force=True)
    t = L.TABLES["asbel.stat"]
    values = {t.field(i).key: native.get("asbel.stat", i) for i in range(t.count)}
    assert values == {"exp": 0, "next": 0, "level": 0, "hp": 0, "attack": 1999, "arte_attack": 1999,
                      "accuracy": 1999, "defense": 1999, "arte_defense": 1999, "evasion": 1999, "max_hp": 0}
    assert native.data[0xA4:0xA8] == struct.pack("<f", 1999.0)


def test_stat_read_only_needs_force(native):
    level = _index("asbel.stat", "level")
    for key in ("level", "attack"):
        with pytest.raises(ReadOnlyError):
            native.set("asbel.stat", _index("asbel.stat", key), 50)
    native.set("asbel.stat", level, 200, force=True)
    assert native.data[0x8C:0x8E] == (200).to_bytes(2, "little")
    with pytest.raises(ValueError, match="0-200"):
        native.set("asbel.stat", level, 201, force=True)


def test_counter_set_all_skips_unknowns(native):
    native.set_all("sophie.counter", 7)
    t = L.TABLES["sophie.counter"]
    for i in range(t.count):
        assert native.get("sophie.counter", i) == (0 if t.field(i).key.startswith("unknown") else 7)


def test_counter_rows_hide_unknowns(native):
    keys = [r["id"] for r in native.rows("asbel.counter")]
    assert "asbel.counter.unknown_b28" not in keys and len(keys) == L.TABLES["asbel.counter"].count - 2
    assert len(native.rows("asbel.counter", show_hidden=True)) == L.TABLES["asbel.counter"].count


def test_together_rows(native):
    native.set("asbel.together", _index("asbel.together", "pascal"), 477, force=True)
    rows = native.rows("asbel.together", "en")
    assert [r["name"] for r in rows] == [i18n.name(f"character.{c}", "en") for c in L.CHARACTERS if c != "asbel"]
    assert all(r["read_only"] and r["hint"] for r in rows)
    assert next(r for r in rows if r["id"] == "asbel.together.pascal")["value"] == 477
    with pytest.raises(ValueError, match="no entries"):
        native.set_all_max("asbel.together", force=True)
