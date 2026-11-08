"""Logging setup from LOG_* variables (togf_save/logsetup.py)."""
import pytest
from loguru import logger

from togf_save import logsetup
from togf_save.cli import main


@pytest.fixture(autouse=True)
def reset_logger():
    yield
    logger.remove()
    logger.disable("togf_save")


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    monkeypatch.setenv("LOG_ENABLED", "true")
    monkeypatch.setenv("LOG_DIR", str(d))
    monkeypatch.setenv("LOG_ENQUEUE", "false")  # write synchronously so the test can read the file
    return d


def test_file_written_when_enabled(log_dir):
    logsetup.setup()
    logger.info("hello file")
    logger.remove()  # close the file
    text = (log_dir / "togf_save.log").read_text(encoding="utf-8")
    assert "hello file" in text and "| INFO" in text


def test_file_level(log_dir, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    logsetup.setup()
    logger.info("too low")
    logger.warning("high enough")
    logger.remove()
    text = (log_dir / "togf_save.log").read_text(encoding="utf-8")
    assert "high enough" in text and "too low" not in text


def test_custom_file_name_and_json(log_dir, monkeypatch):
    monkeypatch.setenv("LOG_FILE_NAME", "custom.jsonl")
    monkeypatch.setenv("LOG_SERIALIZE", "true")
    logsetup.setup()
    logger.info("as json")
    logger.remove()
    assert '"message": "as json"' in (log_dir / "custom.jsonl").read_text(encoding="utf-8")


def test_no_file_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_ENABLED", "false")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    logsetup.setup()
    assert not (tmp_path / "logs").exists()


def test_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_ENABLED")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    logsetup.setup()
    assert not (tmp_path / "logs").exists()


def test_console_only_with_verbose_or_serve(monkeypatch, capsys):
    monkeypatch.setenv("LOG_ENABLED", "false")
    logsetup.setup()
    logger.info("silent")
    assert "silent" not in capsys.readouterr().err

    logsetup.setup(verbose=1)
    logger.debug("too detailed")
    logger.info("console")
    err = capsys.readouterr().err
    assert "console" in err and "too detailed" not in err

    monkeypatch.setenv("LOG_CONSOLE_LEVEL", "WARNING")
    logsetup.setup(console=True)  # the web server
    logger.info("below serve level")
    logger.warning("serve warning")
    err = capsys.readouterr().err
    assert "serve warning" in err and "below serve level" not in err


@pytest.mark.parametrize("name,value", [("LOG_ENABLED", "maybe"), ("LOG_SERIALIZE", "2")])
def test_bad_bool(log_dir, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        logsetup.setup()


def test_bad_rotation_is_reported(log_dir, monkeypatch, capsys):
    monkeypatch.setenv("LOG_ROTATION", "whenever")
    assert main(["table", "--lang", "en"]) == 1
    assert "LOG_" in capsys.readouterr().err


def test_count_or_text():
    assert logsetup._count_or_text("10") == 10
    assert logsetup._count_or_text("14 days") == "14 days"


def test_blank_uses_default(monkeypatch):
    monkeypatch.setenv("LOG_DIR", "  ")
    assert logsetup.env_str("LOG_DIR") == "logs"
