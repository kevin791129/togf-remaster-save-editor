import base64
import json

from togf_save import container, crypto

# sizes and key order mirror a real SaveDat000.sav
NATIVE_SIZE = 79104
NOBLE_SIZE = 1024
CAPTURE_SIZE = 1796
SYS_PARAM_SIZE = 2048
STALE_TAIL_OFFSET = 0x4000  # past the slot 1 record (~0x1800 bytes)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def to_json(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_native() -> bytes:
    return bytes(i * 7 & 0xFF for i in range(NATIVE_SIZE))


def pad(raw: bytes, size: int) -> bytes:
    return raw + bytes(size - len(raw))


def make_slots(native: bytes | None = None) -> tuple[dict, dict]:
    slot1 = {  # NobleAppFileParam
        "version": 0.5,
        "listParam": {
            "saveDate": {"year": 2025, "month": 9, "day": 23, "hour": 22, "minutes": 52, "seconds": 26},
            "playTime": 20789286, "leaderLevel": 154, "to10": 835120010, "sv_sce_no": 4195840,
            "partyLeader": 5, "ending": 1, "listParam0": 1, "sectionClearFlag": 235, "isValid": 1,
            "futer_play": 0,
        },
        "capture": b64(pad(b"\x89PNG\r\n\x1a\n", CAPTURE_SIZE)),
        "captureSize": CAPTURE_SIZE,
        "pNativeSysParam": b64(pad("艾斯貝爾  Lv.154".encode("utf-8"), SYS_PARAM_SIZE)),
    }
    slot2 = {  # NobleAppDataParam
        "NativeData": b64(make_native() if native is None else native),
        "NobleData": b64(pad(b"\x05\x01\x01\x00\x64\x00", NOBLE_SIZE)),
    }
    return slot1, slot2


def make_save(slot1: dict, slot2: dict, stale_tail: bool = True) -> bytes:
    """Build a save like the game would; `stale_tail` leaves junk past the slot 1 record."""
    base = bytearray(container.SLOT1_SIZE)
    if stale_tail:
        base[STALE_TAIL_OFFSET:STALE_TAIL_OFFSET + 0x800] = b"\xAB" * 0x800
    return container.build(crypto.encrypt(to_json(slot1)), crypto.encrypt(to_json(slot2)),
                           slot1_base=bytes(base))
