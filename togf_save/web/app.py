"""FastAPI app: upload a save, edit NativeData (artes, items, shards, raw bytes), download.

Run with `togf-save serve`, or `uvicorn togf_save.web.app:app`.
All edits stay in memory until GET /api/sessions/{id}/download.
"""
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__, container, i18n
from ..codec import find_binary_paths
from ..errors import SaveError
from ..native import NativeData, Shard, layout as L, table as get_table
from .sessions import Session, SessionStore

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD = 4 * 1024 * 1024  # a save is ~1 MB
MAX_HEX = 4096

Lang = Annotated[str | None, Query(description="language code for names; default $DEFAULT_LANG")]


class TableEdit(BaseModel):
    set: dict[int, int] = Field(default_factory=dict, description="{index: value}")
    set_all: int | Literal["max"] | None = Field(None, description='a value, or "max" for the table max')


class ShardIn(BaseModel):
    type: int
    nature: int
    strength: int


class HexWrite(BaseModel):
    offset: int = Field(ge=0)
    hex: str = Field(description="bytes as hex, spaces allowed")


def _check_lang(lang: str | None) -> str:
    lang = lang or i18n.default_lang()
    if lang not in i18n.available():
        raise HTTPException(422, f"unknown language {lang!r}")
    return lang


def create_app(store: SessionStore | None = None) -> FastAPI:
    app = FastAPI(title="ToGf Save Editor", version=__version__)
    store = store or SessionStore()
    app.state.store = store

    @app.exception_handler(SaveError)
    @app.exception_handler(ValueError)
    @app.exception_handler(IndexError)
    async def invalid_edit(request: Request, exc: Exception):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(KeyError)  # unknown table id
    async def not_found(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": exc.args[0] if exc.args else "not found"})

    def get_session(session_id: str) -> Session:
        try:
            return store.get(session_id)
        except KeyError:
            raise HTTPException(404, "unknown session (it may have expired); upload the save again") from None

    SessionDep = Annotated[Session, Depends(get_session)]

    # --- views ---

    def summary(s: Session) -> dict:
        return {
            "id": s.id,
            "filename": s.filename,
            "size": len(s.original),
            "info": container.parse(s.original).info(),
            "warnings": s.save.warnings,
            "modified": s.modified,
            "native_size": len(s.native.data),
        }

    def table_view(s: Session, table_id: str, lang: str) -> dict:
        t = get_table(table_id)
        return {"id": t.id, "name": i18n.name(t.name_key or t.id, lang), "max": t.max_value,
                "rows": s.native.rows(table_id, lang)}

    def shards_view(s: Session, lang: str) -> dict:
        rows = s.native.shard_rows(lang)
        return {"rows": rows, "used": sum(1 for r in rows if r["shard"]),
                "mismatches": [{"type": t, "stored": stored, "actual": actual}
                               for t, (stored, actual) in s.native.shard_count_mismatches().items()]}

    # --- metadata ---

    @app.get("/api/meta")
    def meta(lang: Lang = None):
        lang = _check_lang(lang)
        return {
            "version": __version__,
            "languages": i18n.available(),
            "default_lang": i18n.default_lang(),
            "ui": i18n.ui_strings(lang),
            "groups": [{"id": g, "name": i18n.text(f"group.{g}", lang),
                        "tables": [{"id": tid, "name": i18n.name(get_table(tid).name_key or tid, lang),
                                    "count": get_table(tid).count, "max": get_table(tid).max_value}
                                   for tid in ids]}
                       for g, ids in L.GROUPS.items()],
            "shards": {
                "name": i18n.text("group.shards", lang),
                "slots": L.SHARD_SLOTS,
                "types": [{"value": n, "name": i18n.name(f"shard.type.{n}", lang)}
                          for n in range(1, L.SHARD_TYPES + 1)],
                "natures": [{"value": n, "name": i18n.name(f"shard.nature.{n}", lang)}
                            for n in range(1, L.SHARD_NATURES + 1)],
                "max_strength": L.SHARD_MAX_STRENGTH,
            },
        }

    # --- sessions ---

    @app.post("/api/sessions", status_code=201)
    def upload(file: UploadFile = File(...)):
        data = file.file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"file is larger than {MAX_UPLOAD} bytes; not a save")
        return summary(store.create(Path(file.filename or "SaveDat000.sav").name, data))

    @app.get("/api/sessions/{session_id}")
    def get_summary(s: SessionDep):
        return summary(s)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    def close(s: SessionDep):
        store.delete(s.id)

    @app.get("/api/sessions/{session_id}/download")
    def download(s: SessionDep):
        with s.lock:
            data = s.encode()
        return Response(data, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{s.filename}"'})

    @app.get("/api/sessions/{session_id}/slot1")
    def slot1(s: SessionDep):
        """Slot 1 JSON, read only; base64 fields are replaced by their size."""
        data = s.save.slot1.data
        sizes = {".".join(p): len(s.save.slot1.get_binary(p)) for p in find_binary_paths(data)}
        return {"data": {k: (f"<{sizes[k]} bytes>" if k in sizes else v) for k, v in data.items()}}

    # --- tables (artes, items) ---

    @app.get("/api/sessions/{session_id}/tables/{table_id}")
    def read_table(s: SessionDep, table_id: str, lang: Lang = None):
        lang = _check_lang(lang)
        return table_view(s, table_id, lang)

    @app.patch("/api/sessions/{session_id}/tables/{table_id}")
    def edit_table(s: SessionDep, table_id: str, edit: TableEdit, lang: Lang = None):
        lang = _check_lang(lang)
        t = get_table(table_id)
        with s.lock:
            work = NativeData(s.native.to_bytes())  # all-or-nothing: apply to a copy first
            if edit.set_all is not None:
                work.set_all(table_id, t.max_value if edit.set_all == "max" else edit.set_all)
            for index, value in edit.set.items():
                work.set(t.id, index, value)
            s.native = work
        return table_view(s, table_id, lang)

    # --- shards ---

    @app.get("/api/sessions/{session_id}/shards")
    def read_shards(s: SessionDep, lang: Lang = None):
        lang = _check_lang(lang)
        return shards_view(s, lang)

    @app.put("/api/sessions/{session_id}/shards/{slot}")
    def put_shard(s: SessionDep, slot: int, shard: ShardIn, lang: Lang = None):
        lang = _check_lang(lang)
        with s.lock:
            s.native.set_shard(slot, Shard(shard.type, shard.nature, shard.strength))
        return shards_view(s, lang)

    @app.delete("/api/sessions/{session_id}/shards/{slot}")
    def delete_shard(s: SessionDep, slot: int, lang: Lang = None):
        lang = _check_lang(lang)
        with s.lock:
            s.native.set_shard(slot, None)
        return shards_view(s, lang)

    @app.post("/api/sessions/{session_id}/shards/clear")
    def clear_shards(s: SessionDep, lang: Lang = None):
        lang = _check_lang(lang)
        with s.lock:
            s.native.clear_shards()
        return shards_view(s, lang)

    @app.post("/api/sessions/{session_id}/shards/fix-counts")
    def fix_shard_counts(s: SessionDep, lang: Lang = None):
        lang = _check_lang(lang)
        with s.lock:
            s.native.fix_shard_counts()
        return shards_view(s, lang)

    # --- raw bytes ---

    @app.get("/api/sessions/{session_id}/native/hex")
    def read_hex(s: SessionDep, offset: Annotated[int, Query(ge=0)] = 0,
                 length: Annotated[int, Query(ge=1, le=MAX_HEX)] = 256):
        if offset >= len(s.native.data):
            raise HTTPException(422, f"offset {offset:#x} is past the end ({len(s.native.data):#x})")
        chunk = s.native.data[offset:offset + length]
        return {"offset": offset, "length": len(chunk), "hex": chunk.hex(" ")}

    @app.put("/api/sessions/{session_id}/native/hex")
    def write_hex(s: SessionDep, write: HexWrite):
        raw = bytes.fromhex(write.hex)  # ValueError -> 422
        if not raw or len(raw) > MAX_HEX:
            raise HTTPException(422, f"write 1-{MAX_HEX} bytes")
        with s.lock:
            if write.offset + len(raw) > len(s.native.data):
                raise HTTPException(422, "write goes past the end of NativeData")
            s.native.data[write.offset:write.offset + len(raw)] = raw
        return {"offset": write.offset, "length": len(raw), "modified": s.modified}

    # frontend; mounted last so /api routes win
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


load_dotenv()  # DEFAULT_LANG when run directly with uvicorn
app = create_app()
