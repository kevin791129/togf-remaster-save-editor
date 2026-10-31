import pytest

from togf_save import SaveError, decode, encode
from togf_save.folder import SLOT1_JSON, SLOT1_RAW, SLOT2_JSON, export_folder, import_folder
from togf_save.native import NativeData


def test_export_files(tmp_path, save_bytes):
    files = export_folder(decode(save_bytes), tmp_path)
    assert sorted(f.name for f in files) == sorted(
        [SLOT1_RAW, SLOT1_JSON, SLOT2_JSON, "slot2.NativeData.bin", "slot2.NobleData.bin"])
    assert (tmp_path / SLOT1_JSON).read_bytes() == decode(save_bytes).slot1.text


def test_edited_slot1_json_is_used(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    path = tmp_path / SLOT1_JSON
    path.write_bytes(path.read_bytes().replace(b'"leaderLevel":154', b'"leaderLevel":200'))
    out = decode(encode(import_folder(tmp_path)))
    assert out.slot1.get("listParam.leaderLevel") == 200
    assert out.slot1.text == path.read_bytes()  # used as written


def test_invalid_slot1_json(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    (tmp_path / SLOT1_JSON).write_text("{broken")
    with pytest.raises(SaveError, match="slot1"):
        import_folder(tmp_path)


def test_missing_slot1_json_uses_raw(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    (tmp_path / SLOT1_JSON).unlink()
    assert encode(import_folder(tmp_path)) == save_bytes


def test_unedited_roundtrip_is_identical(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    save = import_folder(tmp_path)
    assert not save.modified and not save.warnings
    assert encode(save) == save_bytes


def test_edited_bin_is_used(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    native = NativeData((tmp_path / "slot2.NativeData.bin").read_bytes())
    native.set("item.consumable", 0, 7)
    (tmp_path / "slot2.NativeData.bin").write_bytes(native.to_bytes())
    out = encode(import_folder(tmp_path))
    assert NativeData(decode(out).native).get("item.consumable", 0) == 7
    assert decode(out).slot1.text == decode(save_bytes).slot1.text


def test_size_change_warns(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    (tmp_path / "slot2.NobleData.bin").write_bytes(b"\x01" * 16)
    assert import_folder(tmp_path).warnings == ["slot2.NobleData.bin: size changed 1024 -> 16 bytes"]


def test_missing_bin_keeps_json(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    (tmp_path / "slot2.NobleData.bin").unlink()
    assert encode(import_folder(tmp_path)) == save_bytes


def test_not_a_folder(tmp_path):
    with pytest.raises(SaveError, match="missing"):
        import_folder(tmp_path)


def test_damaged_slot1_raw_without_json(tmp_path, save_bytes):
    export_folder(decode(save_bytes), tmp_path)
    (tmp_path / SLOT1_JSON).unlink()
    raw = bytearray((tmp_path / SLOT1_RAW).read_bytes())
    raw[8] ^= 0xFF
    (tmp_path / SLOT1_RAW).write_bytes(bytes(raw))
    with pytest.raises(SaveError, match="crc"):
        import_folder(tmp_path)
