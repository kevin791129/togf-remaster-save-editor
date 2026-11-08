"""slot2.NativeData: game state written by the native engine (GameNative.prx)."""
from . import layout
from .editor import NativeData, Shard, has_set_all, set_all_indexes, table

__all__ = ["NativeData", "Shard", "has_set_all", "layout", "set_all_indexes", "table"]
