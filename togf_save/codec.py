"""Decode a save into editable JSON slots and encode it back.

Each slot's plaintext is Newtonsoft JSON; `byte[]` fields are base64 strings
(slot1: thumbnail `capture`, `pNativeSysParam`; slot2: `NativeData`, `NobleData`).
An unedited slot is written back from its original text, so an unedited save
re-encodes byte-identically. An edited slot is re-serialized compactly, in the
same key order.

Paths into the JSON are dotted strings ("listParam.playTime", "a.0.b") or tuples.
"""
import base64
import binascii
import codecs
import copy
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from . import container, crypto
from .errors import SaveError

SLOT_NAMES = ("slot1", "slot2")
NATIVE_PATH = ("NativeData",)

_BASE64 = re.compile(r"[A-Za-z0-9+/]+={0,2}")
_MIN_BASE64_LEN = 16  # shorter strings are too ambiguous to treat as binary

JsonPath = str | tuple[str | int, ...]


def split_path(path: JsonPath) -> tuple[str, ...]:
    if isinstance(path, str):
        return tuple(path.split(".")) if path else ()
    return tuple(str(p) for p in path)


def _child(node: Any, key: str, path: JsonPath) -> Any:
    try:
        if isinstance(node, list):
            return node[int(key)]
        if isinstance(node, dict):
            return node[key]
    except (KeyError, IndexError, ValueError):
        pass
    raise KeyError(f"no {key!r} in path {path!r}")


def get_value(obj: Any, path: JsonPath) -> Any:
    for key in split_path(path):
        obj = _child(obj, key, path)
    return obj


def set_value(obj: Any, path: JsonPath, value: Any) -> None:
    """Replace an existing value; new keys are not created."""
    keys = split_path(path)
    if not keys:
        raise KeyError("empty path")
    parent = get_value(obj, keys[:-1])
    _child(parent, keys[-1], path)  # must already exist
    if isinstance(parent, list):
        parent[int(keys[-1])] = value
    else:
        parent[keys[-1]] = value


def _is_base64(value: Any) -> bool:
    return (isinstance(value, str) and len(value) >= _MIN_BASE64_LEN and len(value) % 4 == 0
            and _BASE64.fullmatch(value) is not None)


def find_binary_paths(obj: Any, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Paths of all string values that look like base64 byte arrays."""
    if isinstance(obj, dict):
        items = obj.items()
    elif isinstance(obj, list):
        items = ((str(i), v) for i, v in enumerate(obj))
    else:
        return [prefix] if _is_base64(obj) else []
    return [p for k, v in items for p in find_binary_paths(v, prefix + (k,))]


@dataclass
class SlotData:
    """Decrypted JSON of one slot.

    `data` is the editable object. Binary fields stay base64 strings inside it and are
    read/written as bytes with get_binary/set_binary.
    """
    name: str
    text: bytes  # decrypted JSON exactly as stored
    data: Any = field(init=False)
    _original: Any = field(init=False, repr=False)
    _bom: bytes = field(init=False, repr=False)

    def __post_init__(self):
        self._bom = codecs.BOM_UTF8 if self.text.startswith(codecs.BOM_UTF8) else b""
        try:
            self._original = json.loads(self.text[len(self._bom):].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise SaveError(f"{self.name}: decrypted data is not JSON ({e})") from None
        self.data = copy.deepcopy(self._original)

    @property
    def modified(self) -> bool:
        return self.data != self._original

    @property
    def binary_paths(self) -> list[tuple[str, ...]]:
        return find_binary_paths(self.data)

    def get(self, path: JsonPath) -> Any:
        return get_value(self.data, path)

    def set(self, path: JsonPath, value: Any) -> None:
        set_value(self.data, path, value)

    def get_binary(self, path: JsonPath) -> bytes:
        value = self.get(path)
        if not isinstance(value, str):
            raise SaveError(f"{self.name}.{'.'.join(split_path(path))} is not a base64 string")
        try:
            return base64.b64decode(value, validate=True)
        except binascii.Error as e:
            raise SaveError(f"{self.name}.{'.'.join(split_path(path))} is not valid base64 ({e})") from None

    def set_binary(self, path: JsonPath, raw: bytes) -> None:
        self.set(path, base64.b64encode(raw).decode("ascii"))

    def to_json(self) -> bytes:
        if not self.modified:
            return self.text
        return self._bom + json.dumps(self.data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


@dataclass
class SaveData:
    slot1: SlotData  # NobleAppFileParam: load-menu summary, thumbnail
    slot2: SlotData  # NobleAppDataParam: NativeData (game state), NobleData
    slot1_area: bytes  # slot 1 area the record was read from; its stale tail is kept on encode
    warnings: list[str] = field(default_factory=list)

    def slot(self, name: str) -> SlotData:
        if name not in SLOT_NAMES:
            raise KeyError(f"unknown slot {name!r}, expected one of {SLOT_NAMES}")
        return getattr(self, name)

    @property
    def slots(self) -> tuple[SlotData, SlotData]:
        return self.slot1, self.slot2

    @property
    def modified(self) -> bool:
        return any(s.modified for s in self.slots)

    @property
    def native(self) -> bytes:
        """slot2.NativeData: game state from GameNative.prx."""
        return self.slot2.get_binary(NATIVE_PATH)

    @native.setter
    def native(self, raw: bytes) -> None:
        self.slot2.set_binary(NATIVE_PATH, raw)


def decode(data: bytes) -> SaveData:
    c = container.parse(data)
    slots, warnings = [], []
    for n, name in enumerate(SLOT_NAMES, 1):
        found = c.valid_record(n)
        if found.from_backup:
            warnings.append(f"{name}: primary copy is damaged, using the backup")
            logger.warning(warnings[-1])
        slots.append(SlotData(name, crypto.decrypt(found.record.body)))
        logger.debug("{}: record {:#x} bytes, json {:#x} bytes", name, found.record.length,
                     len(slots[-1].text))
    return SaveData(*slots, slot1_area=c.valid_record(1).area, warnings=warnings)


def encode(save: SaveData) -> bytes:
    for s in save.slots:
        logger.debug("{}: {}", s.name, "re-serialized (edited)" if s.modified else "original text")
    body1, body2 = (crypto.encrypt(s.to_json()) for s in save.slots)
    return container.build(body1, body2, slot1_base=save.slot1_area)


def read_save(path: str | os.PathLike) -> SaveData:
    logger.info("reading {}", path)
    return decode(Path(path).read_bytes())


def write_save(save: SaveData, path: str | os.PathLike, backup: bool = True) -> Path | None:
    """Encode `save` to `path`.

    With `backup`, an existing file is first moved to `<path>.bak`, but only if no
    `.bak` exists yet, so the backup stays the original. Returns the backup path if made.
    """
    path = Path(path)
    data = encode(save)  # before touching any file, so a failed encode changes nothing
    bak = path.with_name(path.name + ".bak")
    made = None
    if backup and path.exists() and not bak.exists():
        os.replace(path, bak)
        made = bak
        logger.info("backed up {} -> {}", path, bak)
    path.write_bytes(data)
    logger.info("wrote {} ({:#x} bytes)", path, len(data))
    return made
