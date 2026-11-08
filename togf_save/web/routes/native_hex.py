"""Raw NativeData bytes: read and write as hex."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import SessionDep

router = APIRouter(prefix="/api/sessions/{session_id}/native", tags=["hex"])

MAX_HEX = 4096


class HexWrite(BaseModel):
    offset: int = Field(ge=0)
    hex: str = Field(description="bytes as hex, spaces allowed")


@router.get("/hex")
def read_hex(s: SessionDep, offset: Annotated[int, Query(ge=0)] = 0,
             length: Annotated[int, Query(ge=1, le=MAX_HEX)] = 256):
    if offset >= len(s.native.data):
        raise HTTPException(422, f"offset {offset:#x} is past the end ({len(s.native.data):#x})")
    chunk = s.native.data[offset:offset + length]
    return {"offset": offset, "length": len(chunk), "hex": chunk.hex(" ")}


@router.put("/hex")
def write_hex(s: SessionDep, write: HexWrite):
    raw = bytes.fromhex(write.hex)  # ValueError -> 422
    if not raw or len(raw) > MAX_HEX:
        raise HTTPException(422, f"write 1-{MAX_HEX} bytes")
    with s.lock:
        if write.offset + len(raw) > len(s.native.data):
            raise HTTPException(422, "write goes past the end of NativeData")
        s.native.data[write.offset:write.offset + len(raw)] = raw
    return {"offset": write.offset, "length": len(raw), "modified": s.modified}
