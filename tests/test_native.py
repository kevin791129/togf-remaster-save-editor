import re
import struct

import pytest

from togf_save import ReadOnlyError, SaveError, decode, encode, i18n, read_save
from togf_save.native import NativeData, Shard, layout as L, set_all_indexes

from .helpers import NATIVE_SIZE


@pytest.fixture
def native() -> NativeData:
    return NativeData(bytes(NATIVE_SIZE))


# --- layout ---

def _regions():
    for t in L.TABLES.values():
        yield t.id, {t.offset_of(i) + b for i in range(t.count) for b in range(struct.calcsize(t.fmt_of(i)))}
    yield "shards", set(range(L.SHARD_OFFSET, L.SHARD_OFFSET + L.SHARD_SLOTS * L.SHARD_SIZE))
    yield "shard counts", set(range(L.SHARD_COUNT_OFFSET + 1, L.SHARD_COUNT_OFFSET + 1 + L.SHARD_TYPES))


def test_regions_do_not_overlap():
    seen = {}
    for name, region in _regions():
        for other, used in seen.items():
            assert not region & used, f"{name} overlaps {other}"
        seen[name] = region


def test_regions_fit():
    assert L.MIN_SIZE <= NATIVE_SIZE
    assert all(max(region) < L.MIN_SIZE for _, region in _regions())


def test_char_offset():
    assert L.char_offset("asbel", 0) == 0x84
    assert L.char_offset(1, 0) == 0x84 + 0xBD8
    assert L.char_offset("richard", L.ARTE_REL) == 0x4E72
    with pytest.raises(ValueError):
        L.char_offset("nobody", 0)
    with pytest.raises(IndexError):
        L.char_offset(len(L.CHARACTERS), 0)


def test_arte_offsets():
    """Offsets found by diffing saves, before the character block map existed."""
    found = {"asbel": 0x0762, "sophie": 0x133A, "hubert": 0x1F12, "cheria": 0x2AEA,
             "malik": 0x36C2, "pascal": 0x429A}
    assert {t.id: t.offset for t in L.ARTES} == {f"{c}.arte": o for c, o in found.items()}


def test_active_characters_have_arte_counts():
    assert L.ACTIVE_CHARACTERS == tuple(c for c in L.CHARACTERS if c in L.ARTE_COUNTS)


# --- flags, name ids, hint ids ---

_PROBE = L.FieldTable("probe", (
    L.Field("plain", 0x10, 2),
    L.Field("own", 0x12, 2, flags=L.Flag.READ_ONLY | L.Flag.HIDDEN, name_key="shared.name", hint_key="hint.own"),
    L.Field("no_hint", 0x14, 2, hint_key=""),
), flags=L.Flag.SET_ALL, hint_key="hint.table")


def test_field_table_flags_combine_table_and_field():
    assert _PROBE.flags_of(0) == L.Flag.SET_ALL
    assert _PROBE.flags_of(1) == L.Flag.SET_ALL | L.Flag.READ_ONLY | L.Flag.HIDDEN
    with pytest.raises(IndexError):
        _PROBE.flags_of(3)


def test_field_table_name_id():
    assert _PROBE.name_id(0) == "probe.plain"  # defaults to the entry id
    assert _PROBE.name_id(1) == "shared.name"


def test_field_table_hint_id():
    assert _PROBE.hint_id(0) == "hint.table"  # None: inherits the table's hint
    assert _PROBE.hint_id(1) == "hint.own"
    assert _PROBE.hint_id(2) == ""  # "": explicitly none


def test_int_table_flags_name_hint():
    t = L.TABLES["asbel.arte"]
    assert t.flags_of(0) == L.Flag.SET_ALL
    assert t.name_id(3) == t.entry_id(3) == "asbel.arte.3"
    assert t.hint_id(0) == "hint.usage_count"
    for method in (t.flags_of, t.hint_id):
        with pytest.raises(IndexError):
            method(t.count)
    assert L.TABLES["item.dish"].hint_id(0) == ""


def test_existing_tables_are_set_all():
    for t in L.ARTES + L.ITEMS + (L.MISC,):
        assert all(t.flags_of(i) & L.Flag.SET_ALL for i in range(t.count)), t.id


@pytest.mark.parametrize("lang", ["en", "ja", "zh-Hant"])
def test_hint_keys_exist(lang):
    ui = i18n.load(lang, "ui")
    missing = {t.hint_id(i) for t in L.TABLES.values() for i in range(t.count)} - {""} - ui.keys()
    assert not missing, sorted(missing)


def test_items_are_ordered_and_contiguous_where_known():
    consumable, dish = L.ITEMS[:2]
    assert consumable.end == dish.offset
    assert all(a.end <= b.offset for a, b in zip(L.ITEMS, L.ITEMS[1:]))


# --- int tables ---

def test_get_set(native):
    native.set("item.consumable", 0, 15)
    native.set("asbel.arte", 1, 0x1234)
    assert native.get("item.consumable", 0) == 15
    assert native.data[0xA641] == 15
    assert native.data[0x0762 + 12:0x0762 + 14] == b"\x34\x12"  # u16 little-endian


def test_get_set_misc(native):
    native.set("misc", 0, 1234567)
    assert native.get("misc", 0) == 1234567
    assert native.data[0x76D4:0x76D8] == (1234567).to_bytes(4, "little")  # gald: u32 little-endian
    assert native.rows("misc", "en")[0] == {"index": 0, "number": 1, "id": "misc.gald", "name": "Gald",
                                            "offset": 0x76D4, "max": 9999999, "value": 1234567,
                                            "read_only": False, "hidden": False, "set_all": True, "hint": ""}


@pytest.mark.parametrize("value", [-1, 31, 256, 1.5, "3"])
def test_set_out_of_range(native, value):
    with pytest.raises(ValueError):
        native.set("item.consumable", 0, value)


@pytest.mark.parametrize("table_id,limit", [("asbel.arte", 9999), ("item.consumable", 30),
                                            ("item.dish", 15), ("item.material", 15),
                                            ("item.sellable", 15), ("item.ingredient", 15),
                                            ("misc", 9999999)])
def test_limits(native, table_id, limit):
    native.set(table_id, 0, limit)
    with pytest.raises(ValueError, match=f"0-{limit}"):
        native.set(table_id, 0, limit + 1)


def test_index_out_of_range(native):
    with pytest.raises(IndexError):
        native.get("item.consumable", 35)


def test_unknown_table(native):
    with pytest.raises(KeyError):
        native.get("item.nope", 0)


def test_set_all(native):
    native.set_all("item.ingredient", 15)
    assert native.values("item.ingredient") == [15] * 47
    assert native.data[0xA79E - 1] == 0 and native.data[0xA79E + 47] == 0


def test_set_all_max(native):
    native.set_all_max("item.consumable")
    native.set_all_max("misc")
    assert native.values("item.consumable") == [30] * 35
    assert native.get("misc", 0) == 9999999


def test_rows(native):
    native.set("item.consumable", 4, 3)
    row = native.rows("item.consumable")[4]
    assert row == {"index": 4, "number": 5, "id": "item.consumable.4", "name": "萬靈藥瓶", "offset": 0xA645,
                   "max": 30, "value": 3, "read_only": False, "hidden": False, "set_all": True, "hint": ""}


def test_rows_hint(native):
    assert native.rows("asbel.arte", "zh-Hant")[0]["hint"] == i18n.text("hint.usage_count", "zh-Hant") != ""


# --- flags in the editor (on a stand-in table, until real tables use them) ---

_F = L.Flag
_FLAGGED = L.FieldTable("flagged", (
    L.Field("plain", 0x10, 2, limit=100, flags=_F.SET_ALL),
    L.Field("locked", 0x12, 2, limit=50, flags=_F.READ_ONLY | _F.SET_ALL, hint_key="hint.usage_count"),
    L.Field("secret", 0x14, 2, flags=_F.HIDDEN | _F.SET_ALL),
    L.Field("fixed", 0x16, 2, flags=_F.READ_ONLY | _F.HIDDEN),
    L.Field("bulk_off", 0x18, 2),
))
_NO_BULK = L.FieldTable("no_bulk", (L.Field("a", 0x10, 2), L.Field("b", 0x12, 2, flags=_F.READ_ONLY)))


@pytest.fixture
def flagged(monkeypatch, native) -> NativeData:
    monkeypatch.setitem(L.TABLES, "flagged", _FLAGGED)
    return native


def test_read_only_needs_force(flagged):
    with pytest.raises(ReadOnlyError, match="flagged.locked"):
        flagged.set("flagged", 1, 5)
    assert flagged.get("flagged", 1) == 0
    flagged.set("flagged", 1, 5, force=True)
    assert flagged.get("flagged", 1) == 5
    with pytest.raises(ValueError, match="0-50"):  # force skips the read-only check, not the range
        flagged.set("flagged", 1, 51, force=True)


def test_read_only_error_is_a_value_error():
    assert issubclass(ReadOnlyError, ValueError)  # CLI and web report it like any bad value


def test_set_all_touches_set_all_entries_only(flagged):
    flagged.set_all("flagged", 7)
    assert flagged.values("flagged") == [7, 0, 7, 0, 0]  # locked: read-only, fixed and bulk_off: not SET_ALL
    flagged.set_all("flagged", 9, force=True)
    assert flagged.values("flagged") == [9, 9, 9, 0, 0]


def test_set_all_max_respects_flags(flagged):
    flagged.set_all_max("flagged")
    assert flagged.values("flagged") == [100, 0, 0xFFFF, 0, 0]
    flagged.set_all_max("flagged", force=True)
    assert flagged.values("flagged") == [100, 50, 0xFFFF, 0, 0]


def test_set_all_checks_every_entry_first(flagged):
    with pytest.raises(ValueError, match="0-100"):
        flagged.set_all("flagged", 101)
    assert flagged.values("flagged") == [0] * 5  # nothing written, not even the entry it fits


def test_set_all_needs_a_set_all_entry(monkeypatch, native):
    monkeypatch.setitem(L.TABLES, "no_bulk", _NO_BULK)
    for call in (lambda: native.set_all("no_bulk", 1), lambda: native.set_all_max("no_bulk", force=True)):
        with pytest.raises(ValueError, match="no entries"):
            call()


def test_set_all_indexes(flagged):
    t = L.TABLES["flagged"]
    assert set_all_indexes(t) == [0, 2]
    assert set_all_indexes(t, force=True) == [0, 1, 2]


# --- float fields (stand-in table, until the stat tables use them) ---

_FLOATS = L.FieldTable("floats", (
    L.Field("a", 0x20, 4, limit=1999, kind="float", flags=_F.SET_ALL),
    L.Field("b", 0x24, 4, limit=1999, kind="float", flags=_F.SET_ALL),
))


@pytest.fixture
def floats(monkeypatch, native) -> NativeData:
    monkeypatch.setitem(L.TABLES, "floats", _FLOATS)
    return native


def _put_f32(native, offset, value):
    struct.pack_into("<f", native.data, offset, value)


def _f32(native, offset):
    return struct.unpack_from("<f", native.data, offset)[0]


def test_float_round_trip(floats):
    floats.set("floats", 0, 812)
    assert floats.data[0x20:0x24] == struct.pack("<f", 812.0)
    assert floats.get("floats", 0) == 812 and isinstance(floats.get("floats", 0), int)


@pytest.mark.parametrize("stored,shown", [(812.4, 812), (812.6, 813), (0.2, 0), (1998.9, 1999)])
def test_float_reads_rounded(floats, stored, shown):
    _put_f32(floats, 0x20, stored)
    assert floats.get("floats", 0) == shown


@pytest.mark.parametrize("stored", [float("nan"), float("inf")])
def test_float_not_finite_reads_zero(floats, stored):
    _put_f32(floats, 0x20, stored)
    assert floats.get("floats", 0) == 0


def test_float_keeps_fraction_unless_changed(floats):
    _put_f32(floats, 0x20, 812.6)
    _put_f32(floats, 0x24, 100.25)
    floats.set("floats", 0, 813)  # same whole number: not written
    assert _f32(floats, 0x20) == pytest.approx(812.6)
    floats.set("floats", 0, 900)
    assert _f32(floats, 0x20) == 900.0
    assert _f32(floats, 0x24) == 100.25  # the other cell is untouched


@pytest.mark.parametrize("value", [-1, 2000, 1.5])
def test_float_set_out_of_range(floats, value):
    with pytest.raises(ValueError, match="0-1999"):
        floats.set("floats", 0, value)


def test_float_set_all_max(floats):
    floats.set_all_max("floats")
    assert floats.values("floats") == [1999, 1999]
    assert _f32(floats, 0x20) == 1999.0


def test_float_field_needs_a_limit():
    with pytest.raises(ValueError, match="limit"):
        L.Field("x", 0, 4, kind="float")


@pytest.mark.parametrize("kind,size", [("float", 2), ("float", 8), ("uint", 3)])
def test_field_size_must_match_kind(kind, size):
    with pytest.raises(ValueError, match="bytes"):
        L.Field("x", 0, size, limit=1, kind=kind)


def test_is_float():
    assert L.is_float(_FLOATS.fmt_of(0)) and not L.is_float(L.MISC.fmt_of(0))


def test_rows_hide_hidden(flagged):
    assert [r["id"] for r in flagged.rows("flagged")] == ["flagged.plain", "flagged.locked", "flagged.bulk_off"]
    rows = flagged.rows("flagged", show_hidden=True)
    assert [r["index"] for r in rows] == [0, 1, 2, 3, 4]
    assert [(r["read_only"], r["hidden"], r["set_all"]) for r in rows] == [
        (False, False, True), (True, False, True), (False, True, True), (True, True, False), (False, False, False)]
    assert rows[1]["hint"] == i18n.text("hint.usage_count") and rows[0]["hint"] == ""


def test_numbers_continue_across_material_sellable_ingredient():
    material, sellable, ingredient = (L.TABLES[f"item.{c}"] for c in ("material", "sellable", "ingredient"))
    assert material.number(0) == 1
    assert sellable.number(0) == material.number(material.count - 1) + 1 == 124
    assert ingredient.number(0) == sellable.number(sellable.count - 1) + 1 == 190
    assert L.TABLES["item.dish"].number(0) == 1 and L.TABLES["asbel.arte"].number(0) == 1


def test_too_small():
    with pytest.raises(SaveError):
        NativeData(bytes(L.MIN_SIZE - 1))


# --- shards ---

def test_shard_validation():
    with pytest.raises(ValueError):
        Shard(0, 1, 1)
    with pytest.raises(ValueError):
        Shard(1, L.SHARD_NATURES + 1, 1)
    with pytest.raises(ValueError):
        Shard(1, 1, L.SHARD_MAX_STRENGTH + 1)


def test_set_shard_keeps_counts(native):
    native.set_shard(0, Shard(1, 3, 10))
    native.set_shard(1, Shard(1, 4, 5))
    assert native.shard_raw(0) == bytes([1, 2, 3, 10])
    assert native.shard_count(1) == 2

    native.set_shard(1, Shard(7, 4, 5))  # replace: type 1 -> 7
    assert native.shard_count(1) == 1 and native.shard_count(7) == 1

    native.set_shard(0, None)
    assert native.shard(0) is None and native.shard_count(1) == 0
    assert native.shard_count_mismatches() == {}


def test_set_same_shard_is_noop(native):
    native.set_shard(0, Shard(2, 2, 2))
    native.set_shard(0, Shard(2, 2, 2))
    assert native.shard_count(2) == 1


def test_invalid_slot_data(native):
    native.data[L.SHARD_OFFSET:L.SHARD_OFFSET + 4] = b"\x01\x05\x01\x01"  # wrong marker
    with pytest.raises(ValueError, match="slot 0"):
        native.set_shard(0, Shard(1, 1, 1))
    rows = native.shard_rows()
    assert "error" in rows[0] and rows[1]["shard"] is None


def test_count_already_zero(native):
    native.data[L.SHARD_OFFSET:L.SHARD_OFFSET + 4] = Shard(3, 1, 1).to_bytes()  # count not bumped
    with pytest.raises(SaveError):
        native.set_shard(0, None)
    assert native.shard_count_mismatches() == {3: (0, 1)}
    native.fix_shard_counts()
    assert native.shard_count_mismatches() == {}


def test_clear_shards(native):
    for slot in range(5):
        native.set_shard(slot, Shard(slot + 1, 1, 1))
    native.clear_shards()
    assert native.shards() == [None] * L.SHARD_SLOTS
    assert all(native.shard_count(t) == 0 for t in range(1, L.SHARD_TYPES + 1))


def test_slot_out_of_range(native):
    with pytest.raises(IndexError):
        native.shard(L.SHARD_SLOTS)


def test_shard_rows_names(native):
    native.set_shard(2, Shard(1, 3, 10))
    s = native.shard_rows()[2]["shard"]
    assert (s["type_name"], s["nature_name"], s["strength"]) == ("攻擊碎片", "帥氣", 10)


def test_edit_through_save(save_bytes):
    save = decode(save_bytes)
    native = NativeData(save.native)
    native.set("item.dish", 0, 9)
    save.native = native.to_bytes()
    assert NativeData(decode(encode(save)).native).get("item.dish", 0) == 9


# --- locales ---

def test_default_locale_listed():
    assert i18n.available()[i18n.FALLBACK_LANG] == "日本語"


def test_default_lang_from_env(monkeypatch):
    monkeypatch.delenv("DEFAULT_LANG", raising=False)
    assert i18n.default_lang() == i18n.FALLBACK_LANG
    monkeypatch.setenv("DEFAULT_LANG", "xx")
    assert i18n.default_lang() == "xx"
    with pytest.raises(ValueError):
        i18n.name("item.consumable.0")


def test_locale_keys_within_tables():
    """Catches miscounted tables: no name for an index past the end."""
    for lang in i18n.available():
        for key in i18n.load(lang, "names"):
            m = re.fullmatch(r"(.+)\.(\d+)", key)
            if m and m.group(1) in L.TABLES:
                assert int(m.group(2)) < L.TABLES[m.group(1)].count, f"{lang}: {key}"


def test_every_table_has_a_name():
    for t in L.TABLES.values():
        assert i18n.name(t.name_key or t.id) != (t.name_key or t.id), t.id


def test_every_field_has_a_name():
    for t in L.TABLES.values():
        if isinstance(t, L.FieldTable):
            for i in range(t.count):
                assert i18n.name(t.name_id(i)) != t.name_id(i), t.entry_id(i)


def test_shard_names_complete_where_known():
    names = i18n.load(i18n.FALLBACK_LANG, "names")
    assert all(f"shard.type.{t}" in names for t in range(1, L.SHARD_TYPES + 1))
    assert f"shard.nature.{L.SHARD_NATURES}" in names
    assert f"shard.nature.{L.SHARD_NATURES + 1}" not in names


def test_languages():
    assert i18n.available() == {"en": "English", "ja": "日本語", "zh-Hant": "繁體中文"}


@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_ui_files_have_the_same_keys(lang):
    assert i18n.load(lang, "ui").keys() == i18n.load(i18n.FALLBACK_LANG, "ui").keys()


@pytest.mark.parametrize("kind", ["names", "ui"])
def test_fallback_has_every_key(kind):
    fallback = i18n.load(i18n.FALLBACK_LANG, kind).keys()
    for lang in i18n.available():
        missing = sorted(i18n.load(lang, kind).keys() - fallback)
        assert not missing, f"{len(missing)} {lang} keys missing from {i18n.FALLBACK_LANG}: {missing[:10]}"


@pytest.mark.parametrize("lang", ["en", "ja", "zh-Hant"])
def test_ui_placeholders_match(lang):
    """A translation must use the same {placeholders} as the fallback, or format() breaks."""
    fallback = i18n.load(i18n.FALLBACK_LANG, "ui")
    for key, template in i18n.load(lang, "ui").items():
        assert set(re.findall(r"\{(\w+)\}", template)) == set(re.findall(r"\{(\w+)\}", fallback[key])), key


def test_ui_text():
    assert i18n.text("shards.used", "en", used=3, slots=199) == "3/199 slots used"
    assert i18n.text("shards.used", "zh-Hant", used=3, slots=199) == "已使用 3/199 個欄位"
    assert i18n.text("no.such.key", "en") == "no.such.key"
    assert i18n.ui_strings("en")["group.items"] == "Items"


def test_names_fall_back(tmp_path, monkeypatch):
    """A language without a name (or without names.json) falls back to FALLBACK_LANG, then the id."""
    (tmp_path / "xx").mkdir()
    fallback = tmp_path / i18n.FALLBACK_LANG
    fallback.mkdir()
    (fallback / "names.json").write_text('{"item.consumable.4": "萬靈藥瓶"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
    i18n.load.cache_clear()
    try:
        assert i18n.name("item.consumable.4", "xx") == "萬靈藥瓶"
        assert i18n.name("item.consumable.5", "xx") == "item.consumable.5"
    finally:
        i18n.load.cache_clear()


def test_unknown_language():
    with pytest.raises(ValueError):
        i18n.name("item.consumable.0", "xx")


# --- real save (set TEST_TOGF_SAVE) ---

def test_real_shards_consistent(real_save):
    native = NativeData(read_save(real_save).native)
    assert all("error" not in row for row in native.shard_rows())
    assert native.shard_count_mismatches() == {}
