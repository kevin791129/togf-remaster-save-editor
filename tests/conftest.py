import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from .helpers import make_save, make_slots

load_dotenv()  # TEST_TOGF_SAVE can be set in .env


@pytest.fixture(autouse=True)
def default_lang(monkeypatch):
    """Tests check names in zh-Hant when no language is given; don't let .env change that."""
    monkeypatch.setenv("DEFAULT_LANG", "zh-Hant")


@pytest.fixture(autouse=True)
def no_log_files(monkeypatch):
    """CLI tests run main(), which sets up logging; don't write log files from tests."""
    monkeypatch.setenv("LOG_ENABLED", "false")


@pytest.fixture
def save_bytes() -> bytes:
    return make_save(*make_slots())


@pytest.fixture
def real_save() -> Path:
    """A real SaveDat*.sav given by the TEST_TOGF_SAVE environment variable (read only)."""
    path = os.environ.get("TEST_TOGF_SAVE")
    if not path:
        pytest.skip("set TEST_TOGF_SAVE (environment or .env) to a real save to run this test")
    return Path(path)
