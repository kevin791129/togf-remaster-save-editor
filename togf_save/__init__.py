"""Save editor for Tales of Graces f Remastered (PS5).

Logging uses loguru and is off by default for library use; turn it on with
`from loguru import logger; logger.enable("togf_save")` (the CLI and web app do this).
"""
from loguru import logger

from .codec import SaveData, SlotData, decode, encode, read_save, write_save
from .errors import ReadOnlyError, SaveError

__version__ = "0.1.0"

logger.disable("togf_save")

__all__ = ["ReadOnlyError", "SaveData", "SaveError", "SlotData", "decode", "encode", "read_save", "write_save"]
