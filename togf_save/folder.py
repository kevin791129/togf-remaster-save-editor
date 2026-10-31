"""Decoded-folder form of a save, for editing slot 2 with other tools (hex editor, ...).

    slot1.raw           whole slot 1 area, still encrypted (keeps the stale tail)
    slot1.json          slot 1 JSON as stored
    slot2.json          slot 2 JSON as stored
    slot2.<field>.bin   each binary field of slot 2 (NativeData, NobleData)

On import, the .json files are used as they are (slot1.json falls back to the record
in slot1.raw if missing), and a .bin that differs from the JSON replaces that field.
"""
import os
from pathlib import Path

from loguru import logger

from . import container, crypto
from .codec import SaveData, SlotData
from .errors import SaveError

SLOT1_RAW = "slot1.raw"
SLOT1_JSON = "slot1.json"
SLOT2_JSON = "slot2.json"


def bin_name(path: tuple[str, ...]) -> str:
    return f"slot2.{'.'.join(path)}.bin"


def export_folder(save: SaveData, outdir: str | os.PathLike) -> list[Path]:
    """Write the folder; returns the files written."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    files = {SLOT1_RAW: save.slot1_area, SLOT1_JSON: save.slot1.text, SLOT2_JSON: save.slot2.text}
    files |= {bin_name(p): save.slot2.get_binary(p) for p in save.slot2.binary_paths}
    written = []
    for name, data in files.items():
        (outdir / name).write_bytes(data)
        written.append(outdir / name)
        logger.debug("wrote {} ({} bytes)", outdir / name, len(data))
    return written


def import_folder(srcdir: str | os.PathLike) -> SaveData:
    srcdir = Path(srcdir)
    for name in (SLOT1_RAW, SLOT2_JSON):
        if not (srcdir / name).is_file():
            raise SaveError(f"{srcdir}: missing {name}; not a decoded save folder")

    area = (srcdir / SLOT1_RAW).read_bytes()
    if len(area) != container.SLOT1_SIZE:
        raise SaveError(f"{SLOT1_RAW} is {len(area):#x} bytes, expected {container.SLOT1_SIZE:#x}")
    if (srcdir / SLOT1_JSON).is_file():
        slot1 = SlotData("slot1", (srcdir / SLOT1_JSON).read_bytes())
    else:
        rec = container.read_record(area)
        if not rec.crc_ok:
            raise SaveError(f"{SLOT1_RAW}: crc mismatch")
        slot1 = SlotData("slot1", crypto.decrypt(rec.body))

    slot2 = SlotData("slot2", (srcdir / SLOT2_JSON).read_bytes())
    warnings = []
    for path in slot2.binary_paths:
        f = srcdir / bin_name(path)
        if not f.is_file():
            continue
        raw, old = f.read_bytes(), slot2.get_binary(path)
        if raw == old:
            continue
        logger.info("using edited {}", f.name)
        if len(raw) != len(old):
            warnings.append(f"{f.name}: size changed {len(old)} -> {len(raw)} bytes")
            logger.warning(warnings[-1])
        slot2.set_binary(path, raw)
    return SaveData(slot1, slot2, slot1_area=area, warnings=warnings)
