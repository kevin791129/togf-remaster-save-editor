"""Shards: 4-byte slots [type, SHARD_MARKER, nature, strength], all zero = empty."""

SHARD_OFFSET = 0x76DC
SHARD_SLOTS = 199
SHARD_SIZE = 4
SHARD_MARKER = 0x02
SHARD_COUNT_OFFSET = 0xA7D8  # u8 count of type t at SHARD_COUNT_OFFSET + t; must match the slots
SHARD_TYPES = 26  # 1-based
SHARD_NATURES = 54  # 1-based
SHARD_MAX_STRENGTH = 10
