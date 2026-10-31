import struct
import zlib

import pytest

from togf_save import container as c

from .helpers import STALE_TAIL_OFFSET


def test_layout(save_bytes):
    rec1_len, crc1 = struct.unpack_from("<II", save_bytes, c.SLOT1_OFFSET)
    rec2_len, crc2 = struct.unpack_from("<II", save_bytes, c.SLOT2_OFFSET)
    body1 = save_bytes[8:8 + rec1_len]
    body2 = save_bytes[c.SLOT2_OFFSET + 8:c.SLOT2_OFFSET + 8 + rec2_len]
    assert zlib.crc32(body1) == crc1 and zlib.crc32(body2) == crc2
    assert save_bytes[:c.SLOT1_SIZE] == save_bytes[c.SLOT1_BACKUP_OFFSET:c.SLOT2_OFFSET]
    # slot 2: record + zero pad, backup is the record only
    assert len(save_bytes) == c.SLOT2_BACKUP_OFFSET + 8 + rec2_len
    assert not any(save_bytes[c.SLOT2_OFFSET + 8 + rec2_len:c.SLOT2_BACKUP_OFFSET])
    assert save_bytes[c.SLOT2_BACKUP_OFFSET:] == save_bytes[c.SLOT2_OFFSET:c.SLOT2_OFFSET + 8 + rec2_len]


def test_info(save_bytes):
    info = c.parse(save_bytes).info()
    assert info["file_size"] == len(save_bytes)
    for slot in info["slots"]:
        assert slot["backup_identical"]
        assert all(copy["crc_ok"] for copy in slot["copies"])


def test_stale_tail_kept(save_bytes):
    p = c.parse(save_bytes)
    found = p.valid_record(1)
    rebuilt = c.build(found.record.body, p.valid_record(2).record.body, slot1_base=found.area)
    assert rebuilt == save_bytes
    assert rebuilt[STALE_TAIL_OFFSET] == 0xAB


def test_no_base_zero_fills(save_bytes):
    p = c.parse(save_bytes)
    rebuilt = c.build(p.valid_record(1).record.body, p.valid_record(2).record.body)
    assert rebuilt[STALE_TAIL_OFFSET] == 0
    assert len(rebuilt) == len(save_bytes)


@pytest.mark.parametrize("slot,offset", [(1, c.SLOT1_OFFSET), (2, c.SLOT2_OFFSET)])
def test_damaged_primary_uses_backup(save_bytes, slot, offset):
    data = bytearray(save_bytes)
    data[offset + 8] ^= 0xFF  # first body byte -> crc mismatch
    p = c.parse(bytes(data))
    found = p.valid_record(slot)
    assert found.from_backup
    assert found.record.crc_ok
    assert not p.info()["slots"][slot - 1]["backup_identical"]


def test_both_copies_damaged(save_bytes):
    data = bytearray(save_bytes)
    data[c.SLOT1_OFFSET + 8] ^= 0xFF
    data[c.SLOT1_BACKUP_OFFSET + 8] ^= 0xFF
    with pytest.raises(c.ContainerError, match="slot 1 has no valid record"):
        c.parse(bytes(data)).valid_record(1)


def test_bad_length_field(save_bytes):
    data = bytearray(save_bytes)
    struct.pack_into("<I", data, c.SLOT1_OFFSET, c.SLOT1_SIZE)  # larger than the area
    found = c.parse(bytes(data)).valid_record(1)
    assert found.from_backup


def test_too_small():
    with pytest.raises(c.ContainerError, match="too small"):
        c.parse(bytes(100))


def test_record_too_large():
    with pytest.raises(c.ContainerError, match="slot 2 record"):
        c.build(b"x" * 16, b"x" * c.SLOT2_SIZE)
