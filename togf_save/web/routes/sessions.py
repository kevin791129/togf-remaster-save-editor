"""Sessions: upload a save, read its summary and slot 1, download the edited save, close."""
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ... import container
from ...codec import find_binary_paths
from ..deps import SessionDep, StoreDep
from ..sessions import Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

MAX_UPLOAD = 4 * 1024 * 1024  # a save is ~1 MB


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


@router.post("", status_code=201)
def upload(store: StoreDep, file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD} bytes; not a save")
    return summary(store.create(Path(file.filename or "SaveDat000.sav").name, data))


@router.get("/{session_id}")
def get_summary(s: SessionDep):
    return summary(s)


@router.delete("/{session_id}", status_code=204)
def close(s: SessionDep, store: StoreDep):
    store.delete(s.id)


@router.get("/{session_id}/download")
def download(s: SessionDep):
    with s.lock:
        data = s.encode()
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{s.filename}"'})


@router.get("/{session_id}/slot1")
def slot1(s: SessionDep):
    """Slot 1 JSON, read only; base64 fields are replaced by their size."""
    data = s.save.slot1.data
    sizes = {".".join(p): len(s.save.slot1.get_binary(p)) for p in find_binary_paths(data)}
    return {"data": {k: (f"<{sizes[k]} bytes>" if k in sizes else v) for k, v in data.items()}}
