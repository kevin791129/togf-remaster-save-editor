"""Tables (characters, items, misc): read rows, edit values.

Rows carry read_only / hidden / set_all flags and a hint. A hint shared by the whole
table is returned once as the table's "hint"; a row's "hint" is only filled when it
differs from that.
"""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ... import i18n
from ...native import NativeData, has_set_all, table as get_table
from ..deps import Lang, SessionDep, check_lang
from ..sessions import Session

router = APIRouter(prefix="/api/sessions/{session_id}/tables", tags=["tables"])


class TableEdit(BaseModel):
    set: dict[int, int] = Field(default_factory=dict, description="{index: value}")
    set_all: int | Literal["max"] | None = Field(
        None, description='a value, or "max" for each entry\'s max; only entries that allow it')
    force: bool = Field(False, description="also write read-only entries")


def table_view(s: Session, table_id: str, lang: str, show_hidden: bool) -> dict:
    t = get_table(table_id)
    rows = s.native.rows(table_id, lang, show_hidden=show_hidden)
    for row in rows:
        if t.hint_id(row["index"]) == t.hint_key:
            row["hint"] = ""
    return {"id": t.id, "name": i18n.name(t.name_key or t.id, lang), "max": t.max_value,
            "hint": i18n.text(t.hint_key, lang) if t.hint_key else "", "set_all": has_set_all(t),
            "rows": rows}


@router.get("/{table_id}")
def read_table(s: SessionDep, table_id: str, lang: Lang = None, show_hidden: bool = Query(False)):
    lang = check_lang(lang)
    return table_view(s, table_id, lang, show_hidden)


@router.patch("/{table_id}")
def edit_table(s: SessionDep, table_id: str, edit: TableEdit, lang: Lang = None, show_hidden: bool = Query(False)):
    lang = check_lang(lang)
    t = get_table(table_id)
    with s.lock:
        work = NativeData(s.native.to_bytes())  # all-or-nothing: apply to a copy first
        if edit.set_all == "max":
            work.set_all_max(table_id, force=edit.force)
        elif edit.set_all is not None:
            work.set_all(table_id, edit.set_all, force=edit.force)
        for index, value in edit.set.items():
            work.set(t.id, index, value, force=edit.force)
        s.native = work
    return table_view(s, table_id, lang, show_hidden)
