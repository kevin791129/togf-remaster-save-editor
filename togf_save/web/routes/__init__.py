"""API routes, one module per group; app.py includes ROUTERS.

    meta.py        GET /api/meta
    sessions.py    upload, summary, slot 1, download, close
    tables.py      read and edit tables (characters, items, misc)
    shards.py      shard slots
    native_hex.py  raw NativeData bytes
"""
from . import meta, native_hex, sessions, shards, tables

ROUTERS = (meta.router, sessions.router, tables.router, shards.router, native_hex.router)
