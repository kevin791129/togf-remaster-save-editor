"""Shared FastAPI dependencies: the session of a request, and the language of its names."""
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from .. import i18n
from .sessions import Session, SessionStore

Lang = Annotated[str | None, Query(description="language code for names; default $DEFAULT_LANG")]


def check_lang(lang: str | None) -> str:
    lang = lang or i18n.default_lang()
    if lang not in i18n.available():
        raise HTTPException(422, f"unknown language {lang!r}")
    return lang


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_session(session_id: str, store: Annotated[SessionStore, Depends(get_store)]) -> Session:
    try:
        return store.get(session_id)
    except KeyError:
        raise HTTPException(404, "unknown session (it may have expired); upload the save again") from None


StoreDep = Annotated[SessionStore, Depends(get_store)]
SessionDep = Annotated[Session, Depends(get_session)]
