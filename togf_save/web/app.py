"""FastAPI app: upload a save, edit NativeData (characters, items, shards, raw bytes), download.

Run with `togf-save serve`, or `uvicorn togf_save.web.app:app`.
All edits stay in memory until GET /api/sessions/{id}/download.

Routes live in routes/ (one module per group), shared dependencies in deps.py.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, logsetup
from ..errors import SaveError
from .routes import ROUTERS
from .sessions import SessionStore

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _setup_logging(app: FastAPI):
    logsetup.setup(console=True)  # on server start, not on import (tests import this module)
    yield


def create_app(store: SessionStore | None = None, setup_logging: bool = False) -> FastAPI:
    """setup_logging: configure loguru from LOG_* when the server starts (for running this module
    directly with uvicorn; `togf-save serve` sets up logging itself)."""
    app = FastAPI(title="ToGf Save Editor", version=__version__,
                  lifespan=_setup_logging if setup_logging else None)
    app.state.store = store or SessionStore()

    @app.exception_handler(SaveError)
    @app.exception_handler(ValueError)  # includes ReadOnlyError
    @app.exception_handler(IndexError)
    async def invalid_edit(request: Request, exc: Exception):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(KeyError)  # unknown table id
    async def not_found(request: Request, exc: KeyError):
        return JSONResponse(status_code=404, content={"detail": exc.args[0] if exc.args else "not found"})

    for router in ROUTERS:
        app.include_router(router)

    # frontend; mounted last so /api routes win
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


load_dotenv()  # DEFAULT_LANG and LOG_* when run directly with uvicorn
app = create_app(setup_logging=True)
