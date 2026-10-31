"""slot2.NativeData: game state written by the native engine (GameNative.prx)."""
from . import layout
from .editor import NativeData, Shard, table

__all__ = ["NativeData", "Shard", "layout", "table"]
