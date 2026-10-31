"""Container layout of SaveDat*.sav (all little-endian).

| Range           | Content                                                            |
|-----------------|--------------------------------------------------------------------|
| 0x00000-0x61000 | slot 1: [u32 len][u32 crc32(body)][body] + stale tail + zero pad   |
| 0x61000-0xC2000 | identical backup of slot 1                                         |
| 0xC2000-0xDD000 | slot 2: [u32 len][u32 crc32(body)][body] + zero pad                |
| 0xDD000-EOF     | identical backup of slot 2 record (not padded)                     |

The game reads only `len` bytes of a slot. Writing a shorter record leaves the end of
the older, longer one in place (the "stale tail"); it is ignored, but kept so an
unedited save rebuilds byte-for-byte.
"""
import struct
import zlib
from dataclasses import dataclass

from .errors import SaveError

SLOT1_SIZE = 0x61000  # SaveLoadManager.kAppParamSize
SLOT2_SIZE = 0x1B000  # SaveLoadManager.kAppNewDataSize
SLOT1_OFFSET = 0
SLOT1_BACKUP_OFFSET = SLOT1_OFFSET + SLOT1_SIZE
SLOT2_OFFSET = SLOT1_BACKUP_OFFSET + SLOT1_SIZE
SLOT2_BACKUP_OFFSET = SLOT2_OFFSET + SLOT2_SIZE

HEADER = struct.Struct("<II")  # body length, crc32(body)
MIN_FILE_SIZE = SLOT2_BACKUP_OFFSET + HEADER.size


class ContainerError(SaveError):
    """The file is not a valid save container."""


@dataclass(frozen=True)
class Record:
    """One `[len][crc][body]` record read from the start of a slot area."""
    length: int
    crc: int
    body: bytes

    @property
    def crc_ok(self) -> bool:
        return zlib.crc32(self.body) == self.crc


@dataclass(frozen=True)
class SlotRecord:
    """The valid record of a slot and the area (copy) it was read from."""
    record: Record
    area: bytes
    from_backup: bool


def read_record(area: bytes) -> Record:
    if len(area) < HEADER.size:
        raise ContainerError(f"slot area of {len(area):#x} bytes is too small for a record header")
    length, crc = HEADER.unpack_from(area)
    if length == 0 or HEADER.size + length > len(area):
        raise ContainerError(f"record length {length:#x} does not fit in slot area of {len(area):#x} bytes")
    return Record(length, crc, area[HEADER.size:HEADER.size + length])


def pack_record(body: bytes) -> bytes:
    return HEADER.pack(len(body), zlib.crc32(body)) + body


@dataclass(frozen=True)
class Container:
    file_size: int
    slot1: bytes
    slot1_backup: bytes
    slot2: bytes
    slot2_backup: bytes

    def areas(self, slot: int) -> tuple[bytes, bytes]:
        """(primary, backup) areas of slot 1 or 2."""
        if slot == 1:
            return self.slot1, self.slot1_backup
        if slot == 2:
            return self.slot2, self.slot2_backup
        raise ValueError(f"slot must be 1 or 2, not {slot!r}")

    def valid_record(self, slot: int) -> SlotRecord:
        """The primary copy's record, or the backup's if the primary is damaged."""
        errors = []
        for from_backup, area in zip((False, True), self.areas(slot)):
            label = "backup" if from_backup else "primary"
            try:
                rec = read_record(area)
            except ContainerError as e:
                errors.append(f"{label}: {e}")
                continue
            if rec.crc_ok:
                return SlotRecord(rec, area, from_backup)
            errors.append(f"{label}: crc mismatch")
        raise ContainerError(f"slot {slot} has no valid record ({'; '.join(errors)})")

    def info(self) -> dict:
        """Layout and integrity summary, JSON-serializable."""
        slots = []
        offsets = {1: (SLOT1_OFFSET, SLOT1_BACKUP_OFFSET), 2: (SLOT2_OFFSET, SLOT2_BACKUP_OFFSET)}
        for slot in (1, 2):
            primary, backup = self.areas(slot)
            copies = []
            for label, offset, area in zip(("primary", "backup"), offsets[slot], (primary, backup)):
                try:
                    rec = read_record(area)
                    copies.append({"copy": label, "offset": offset, "length": rec.length,
                                   "crc": rec.crc, "crc_ok": rec.crc_ok})
                except ContainerError as e:
                    copies.append({"copy": label, "offset": offset, "error": str(e)})
            slots.append({"slot": slot, "copies": copies,
                          "backup_identical": primary[:len(backup)] == backup})
        return {"file_size": self.file_size, "slots": slots}


def parse(data: bytes) -> Container:
    if len(data) < MIN_FILE_SIZE:
        raise ContainerError(f"file is {len(data):#x} bytes, too small for a save (min {MIN_FILE_SIZE:#x})")
    return Container(
        file_size=len(data),
        slot1=data[SLOT1_OFFSET:SLOT1_BACKUP_OFFSET],
        slot1_backup=data[SLOT1_BACKUP_OFFSET:SLOT2_OFFSET],
        slot2=data[SLOT2_OFFSET:SLOT2_BACKUP_OFFSET],
        slot2_backup=data[SLOT2_BACKUP_OFFSET:],
    )


def build(body1: bytes, body2: bytes, slot1_base: bytes | None = None) -> bytes:
    """Assemble a save file from the two encrypted record bodies.

    `slot1_base` is the previous slot 1 area: the bytes past the new record are kept,
    as the game does. None zero-fills them (valid, but not byte-identical to the original).
    """
    rec1, rec2 = pack_record(body1), pack_record(body2)
    if len(rec1) > SLOT1_SIZE:
        raise ContainerError(f"slot 1 record is {len(rec1):#x} bytes, max {SLOT1_SIZE:#x}")
    if len(rec2) > SLOT2_SIZE:
        raise ContainerError(f"slot 2 record is {len(rec2):#x} bytes, max {SLOT2_SIZE:#x}")
    base = bytes(SLOT1_SIZE) if slot1_base is None else slot1_base
    if len(base) != SLOT1_SIZE:
        raise ContainerError(f"slot 1 base is {len(base):#x} bytes, expected {SLOT1_SIZE:#x}")
    slot1 = rec1 + base[len(rec1):]
    return slot1 + slot1 + rec2 + bytes(SLOT2_SIZE - len(rec2)) + rec2
