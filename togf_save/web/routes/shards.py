"""Shards: list slots, put / remove a shard, clear all, fix the per-type counts."""
from fastapi import APIRouter
from pydantic import BaseModel

from ...native import Shard
from ..deps import Lang, SessionDep, check_lang
from ..sessions import Session

router = APIRouter(prefix="/api/sessions/{session_id}/shards", tags=["shards"])


class ShardIn(BaseModel):
    type: int
    nature: int
    strength: int


def shards_view(s: Session, lang: str) -> dict:
    rows = s.native.shard_rows(lang)
    return {"rows": rows, "used": sum(1 for r in rows if r["shard"]),
            "mismatches": [{"type": t, "stored": stored, "actual": actual}
                           for t, (stored, actual) in s.native.shard_count_mismatches().items()]}


@router.get("")
def read_shards(s: SessionDep, lang: Lang = None):
    lang = check_lang(lang)
    return shards_view(s, lang)


@router.put("/{slot}")
def put_shard(s: SessionDep, slot: int, shard: ShardIn, lang: Lang = None):
    lang = check_lang(lang)
    with s.lock:
        s.native.set_shard(slot, Shard(shard.type, shard.nature, shard.strength))
    return shards_view(s, lang)


@router.delete("/{slot}")
def delete_shard(s: SessionDep, slot: int, lang: Lang = None):
    lang = check_lang(lang)
    with s.lock:
        s.native.set_shard(slot, None)
    return shards_view(s, lang)


@router.post("/clear")
def clear_shards(s: SessionDep, lang: Lang = None):
    lang = check_lang(lang)
    with s.lock:
        s.native.clear_shards()
    return shards_view(s, lang)


@router.post("/fix-counts")
def fix_shard_counts(s: SessionDep, lang: Lang = None):
    lang = check_lang(lang)
    with s.lock:
        s.native.fix_shard_counts()
    return shards_view(s, lang)
