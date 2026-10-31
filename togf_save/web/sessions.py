"""In-memory editing sessions, one per uploaded save.

Edits go to the session's NativeData; the save is encoded only on download.
Sessions live until deleted or evicted (oldest first) when MAX_SESSIONS is reached.
"""
import secrets
import threading
import time
from dataclasses import dataclass, field

from loguru import logger

from ..codec import SaveData, decode, encode
from ..native import NativeData

MAX_SESSIONS = 16


@dataclass
class Session:
    id: str
    filename: str
    original: bytes  # uploaded file
    save: SaveData
    native: NativeData  # edited copy of slot2.NativeData
    original_native: bytes
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    last_used: float = field(default_factory=time.monotonic)

    @property
    def modified(self) -> bool:
        return self.native.data != self.original_native

    def encode(self) -> bytes:
        self.save.native = self.native.to_bytes()
        return encode(self.save)


class SessionStore:
    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, filename: str, data: bytes) -> Session:
        save = decode(data)  # raises SaveError before anything is stored
        session = Session(secrets.token_urlsafe(12), filename, data, save, NativeData(save.native), save.native)
        with self._lock:
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                del self._sessions[oldest.id]
                logger.info("evicted session {} ({})", oldest.id, oldest.filename)
            self._sessions[session.id] = session
        logger.info("session {}: loaded {} ({} bytes)", session.id, filename, len(data))
        return session

    def get(self, session_id: str) -> Session:
        with self._lock:
            session = self._sessions[session_id]  # KeyError if unknown
            session.last_used = time.monotonic()
            return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
