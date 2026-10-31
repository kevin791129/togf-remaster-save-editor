import json

import pytest

from togf_save import SaveError, codec, container, crypto, decode, encode, read_save, write_save

from .helpers import make_native, make_save, make_slots, to_json


def test_unmodified_roundtrip_is_identical(save_bytes):
    save = decode(save_bytes)
    assert not save.modified
    assert not save.warnings
    assert encode(save) == save_bytes


def test_decoded_values(save_bytes):
    save = decode(save_bytes)
    assert save.slot1.get("listParam.playTime") == 20789286
    assert save.slot1.get(("listParam", "saveDate", "year")) == 2025
    assert save.native == make_native()


def test_binary_paths(save_bytes):
    save = decode(save_bytes)
    assert save.slot1.binary_paths == [("capture",), ("pNativeSysParam",)]
    assert save.slot2.binary_paths == [("NativeData",), ("NobleData",)]


def test_edit_json_value(save_bytes):
    save = decode(save_bytes)
    save.slot1.set("listParam.leaderLevel", 99)
    assert save.modified
    again = decode(encode(save))
    assert again.slot1.get("listParam.leaderLevel") == 99
    assert again.slot1.data == save.slot1.data
    # untouched slot 2 is written from its original text
    assert again.slot2.text == save.slot2.text


def test_edit_native(save_bytes):
    save = decode(save_bytes)
    native = bytearray(save.native)
    native[0x100:0x104] = b"\xDE\xAD\xBE\xEF"
    save.native = bytes(native)
    out = encode(save)
    assert decode(out).native == bytes(native)
    # stale tail of slot 1 survives an edit of slot 2
    assert out[:container.SLOT1_SIZE] == save_bytes[:container.SLOT1_SIZE]


def test_edited_json_is_compact_and_keeps_key_order(save_bytes):
    slot1, _ = make_slots()
    save = decode(save_bytes)
    save.slot1.set("version", 0.5)  # same value: still unmodified
    assert not save.slot1.modified
    save.slot1.set("captureSize", 65)
    slot1["captureSize"] = 65
    assert save.slot1.to_json() == to_json(slot1)


def test_list_paths():
    slot = codec.SlotData("t", json.dumps({"a": [{"b": 1}, {"b": 2}]}).encode())
    assert slot.get("a.1.b") == 2
    slot.set(("a", 0, "b"), 5)
    assert slot.data == {"a": [{"b": 5}, {"b": 2}]}


@pytest.mark.parametrize("path", ["listParam.nope", "nope", "listParam.playTime.x", ""])
def test_set_missing_path(save_bytes, path):
    with pytest.raises(KeyError):
        decode(save_bytes).slot1.set(path, 1)


def test_get_binary_of_non_string(save_bytes):
    with pytest.raises(SaveError):
        decode(save_bytes).slot1.get_binary("captureSize")


def test_bom_is_kept():
    slot = codec.SlotData("t", b"\xef\xbb\xbf" + b'{"a":1}')
    slot.set("a", 2)
    assert slot.to_json() == b'\xef\xbb\xbf{"a":2}'


def test_not_json():
    data = container.build(crypto.encrypt(b"not json"), crypto.encrypt(b"{}"))
    with pytest.raises(SaveError, match="slot1"):
        decode(data)


def test_damaged_primary_warns(save_bytes):
    data = bytearray(save_bytes)
    data[container.SLOT2_OFFSET + 8] ^= 0xFF
    save = decode(bytes(data))
    assert save.warnings == ["slot2: primary copy is damaged, using the backup"]
    assert save.native == make_native()


def test_slot_lookup(save_bytes):
    save = decode(save_bytes)
    assert save.slot("slot2") is save.slot2
    with pytest.raises(KeyError):
        save.slot("slot3")


def test_write_save_backup(tmp_path, save_bytes):
    path = tmp_path / "SaveDat000.sav"
    path.write_bytes(save_bytes)
    save = read_save(path)
    save.slot1.set("listParam.leaderLevel", 1)

    assert write_save(save, path) == tmp_path / "SaveDat000.sav.bak"
    assert (tmp_path / "SaveDat000.sav.bak").read_bytes() == save_bytes
    assert read_save(path).slot1.get("listParam.leaderLevel") == 1

    save.slot1.set("listParam.leaderLevel", 2)
    assert write_save(save, path) is None  # .bak already exists: keep the original
    assert (tmp_path / "SaveDat000.sav.bak").read_bytes() == save_bytes


def test_failed_encode_leaves_file_alone(tmp_path, save_bytes):
    path = tmp_path / "SaveDat000.sav"
    path.write_bytes(save_bytes)
    save = read_save(path)
    save.native = bytes(container.SLOT2_SIZE)  # base64 + encryption overflow slot 2
    with pytest.raises(container.ContainerError):
        write_save(save, path)
    assert path.read_bytes() == save_bytes
    assert not (tmp_path / "SaveDat000.sav.bak").exists()


def test_no_stale_tail_roundtrip():
    data = make_save(*make_slots(), stale_tail=False)
    assert encode(decode(data)) == data


# --- real save (set TEST_TOGF_SAVE) ---

def test_real_roundtrip_is_identical(real_save):
    data = real_save.read_bytes()
    assert encode(decode(data)) == data


def test_real_reserialization_matches(real_save):
    """Edited slots are re-serialized; this checks that matches the game's JSON formatting."""
    save = read_save(real_save)
    for slot in save.slots:
        reserialized = json.dumps(slot.data, ensure_ascii=False, separators=(",", ":")).encode()
        assert reserialized == slot.text.removeprefix(b"\xef\xbb\xbf"), slot.name
