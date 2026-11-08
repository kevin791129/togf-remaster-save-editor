import pytest

from togf_save import i18n, read_save
from togf_save.cli import main
from togf_save.native import NativeData, Shard, layout as L

from .helpers import NATIVE_SIZE, make_save, make_slots


@pytest.fixture
def sav(tmp_path):
    """A save with zeroed NativeData (empty shard slots) on disk."""
    path = tmp_path / "SaveDat000.sav"
    path.write_bytes(make_save(*make_slots(native=bytes(NATIVE_SIZE))))
    return path


@pytest.fixture
def native_bin(tmp_path):
    """A zeroed slot2.NativeData.bin on disk."""
    path = tmp_path / "slot2.NativeData.bin"
    path.write_bytes(bytes(NATIVE_SIZE))
    return path


def native_of(path) -> NativeData:
    return NativeData(path.read_bytes())


# --- info / decode / encode (.sav) ---

def test_info(sav, capsys):
    assert main(["info", str(sav), "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "backup identical: yes" in out
    assert "slot2.NativeData  79104 bytes" in out


def test_info_zh(sav, capsys):
    assert main(["info", str(sav), "--lang", "zh-Hant"]) == 0
    out = capsys.readouterr().out
    assert "備份相同：是" in out and "79104 位元組" in out


def test_decode_encode_roundtrip(sav, tmp_path):
    outdir = tmp_path / "dec"
    assert main(["decode", str(sav), str(outdir)]) == 0
    assert (outdir / "slot2.NativeData.bin").exists() and (outdir / "slot1.json").exists()
    assert main(["encode", str(outdir), str(tmp_path / "new.sav")]) == 0
    assert (tmp_path / "new.sav").read_bytes() == sav.read_bytes()


def test_decode_default_outdir_and_encode_backup(sav):
    original = sav.read_bytes()
    assert main(["decode", str(sav)]) == 0
    folder = sav.with_suffix("")
    assert folder.is_dir()
    assert main(["encode", str(folder)]) == 0  # default OUT is the original save
    assert sav.with_name(sav.name + ".bak").read_bytes() == original


def test_full_workflow(sav, tmp_path):
    """decode -> table/shards on the .bin -> encode."""
    folder = tmp_path / "dec"
    assert main(["decode", str(sav), str(folder)]) == 0
    native = folder / "slot2.NativeData.bin"
    assert main(["table", str(native), "item.consumable", "--set", "0=30"]) == 0
    assert main(["shards", str(native), "--set", "0", "2", "5", "7"]) == 0
    assert main(["encode", str(folder), str(tmp_path / "out.sav")]) == 0

    result = NativeData(read_save(tmp_path / "out.sav").native)
    assert result.get("item.consumable", 0) == 30
    assert result.shard(0) == Shard(2, 5, 7) and result.shard_count(2) == 1


def test_missing_file(tmp_path, capsys):
    assert main(["info", str(tmp_path / "nope.sav"), "--lang", "en"]) == 1
    assert "error:" in capsys.readouterr().err


# --- table (.bin) ---

def test_table_list(native_bin, capsys):
    assert main(["table", str(native_bin), "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "item.consumable" in out and "max 30" in out and "max 9999" in out
    assert "Misc" in out and "(1 entries)" in out  # misc has no table-wide max


def test_table_rows(native_bin, capsys):
    assert main(["table", str(native_bin), "item.consumable"]) == 0
    assert "萬靈藥瓶" in capsys.readouterr().out


def test_table_set_in_place(native_bin, capsys):
    assert main(["table", str(native_bin), "item.consumable", "--set", "0=15", "4=3"]) == 0
    assert "item.consumable.4  萬靈藥瓶: 0 -> 3" in capsys.readouterr().out
    assert native_of(native_bin).values("item.consumable")[:5] == [15, 0, 0, 0, 3]


def test_table_set_all_to_output(native_bin, tmp_path):
    out = tmp_path / "out.bin"
    assert main(["table", str(native_bin), "arte.asbel", "--set-all", "9999", "-o", str(out)]) == 0
    assert native_of(out).values("arte.asbel") == [9999] * 36
    assert native_of(native_bin).values("arte.asbel") == [0] * 36  # source untouched


@pytest.mark.parametrize("table_id,limit", [("arte.asbel", 9999), ("item.consumable", 30), ("item.dish", 15),
                                            ("misc", 9999999)])
def test_table_set_all_max(native_bin, table_id, limit):
    assert main(["table", str(native_bin), table_id, "--set-all", "max"]) == 0
    values = native_of(native_bin).values(table_id)
    assert values == [limit] * len(values)


def test_table_set_all_bad_value(native_bin):
    with pytest.raises(SystemExit):
        main(["table", str(native_bin), "item.dish", "--set-all", "lots"])


def test_table_over_limit(native_bin, capsys):
    before = native_bin.read_bytes()
    assert main(["table", str(native_bin), "item.dish", "--set", "0=16"]) == 1
    assert "0-15" in capsys.readouterr().err
    assert native_bin.read_bytes() == before


def test_table_unknown(native_bin, capsys):
    assert main(["table", str(native_bin), "item.nope"]) == 1
    assert "unknown table" in capsys.readouterr().err


def test_table_bad_set_syntax(native_bin):
    with pytest.raises(SystemExit):
        main(["table", str(native_bin), "item.dish", "--set", "0:5"])


def test_table_rejects_short_file(tmp_path, capsys):
    path = tmp_path / "short.bin"
    path.write_bytes(bytes(100))
    assert main(["table", str(path), "item.dish"]) == 1
    assert "NativeData" in capsys.readouterr().err


# --- shards (.bin) ---

def test_shards(native_bin, capsys):
    assert main(["shards", str(native_bin), "--set", "3", "1", "3", "10"]) == 0
    assert native_of(native_bin).shard(3) == Shard(1, 3, 10)
    capsys.readouterr()

    assert main(["shards", str(native_bin), "--lang", "en"]) == 0
    out = capsys.readouterr().out
    names = f"{i18n.name('shard.type.1', 'en')} (1)  {i18n.name('shard.nature.3', 'en')} (3)  10"
    assert names in out and "1/199 slots used" in out

    assert main(["shards", str(native_bin), "--clear", "3"]) == 0
    native = native_of(native_bin)
    assert native.shard(3) is None and native.shard_count(1) == 0


def test_shards_types(capsys):
    assert main(["shards", "--types", "--lang", "zh-Hant"]) == 0  # no NATIVE needed
    out = capsys.readouterr().out
    assert "種類 (1-26)" in out and "   26  加碼碎片" in out
    assert "性質 (1-54)" in out and "    3  帥氣" in out
    assert "強度 (1-10)" in out


def test_shards_types_en(capsys):
    assert main(["shards", "--types", "--lang", "en"]) == 0
    out = capsys.readouterr().out
    assert "Type (1-26)" in out and "Nature (1-54)" in out and "Strength (1-10)" in out


def test_shards_needs_native(capsys):
    assert main(["shards"]) == 1
    assert "NATIVE" in capsys.readouterr().err


def test_table_list_without_native(capsys):
    assert main(["table"]) == 0
    assert "item.consumable" in capsys.readouterr().out


def test_table_id_without_native(capsys):
    assert main(["table", "item.dish"]) == 1
    assert "NATIVE" in capsys.readouterr().err


def test_shards_invalid_value(native_bin, capsys):
    assert main(["shards", str(native_bin), "--set", "0", "27", "1", "1"]) == 1
    assert "type" in capsys.readouterr().err


def test_shards_fix_counts(native_bin, capsys):
    native = native_of(native_bin)
    native.data[L.SHARD_OFFSET:L.SHARD_OFFSET + 4] = Shard(5, 1, 1).to_bytes()  # count not bumped
    native_bin.write_bytes(native.to_bytes())

    assert main(["shards", str(native_bin)]) == 0
    assert "--fix-counts" in capsys.readouterr().out
    assert main(["shards", str(native_bin), "--fix-counts"]) == 0
    assert native_of(native_bin).shard_count_mismatches() == {}
