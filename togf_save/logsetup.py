"""Logging setup for the CLI and the web server, from environment variables (.env works too).

Console output:
    CLI: -v (INFO) / -vv (DEBUG). `serve`: always on, at LOG_CONSOLE_LEVEL (default INFO).
Log file (only when LOG_ENABLED is true):
    LOG_DIR/LOG_FILE_NAME, rotated by LOG_ROTATION, old files deleted by LOG_RETENTION.

Library use is unaffected: nothing is logged unless the caller enables "togf_save".
"""
import os
import sys
from pathlib import Path

from loguru import logger

CONSOLE_FORMAT = "<level>{level: <7}</level> {message}"
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}"

DEFAULTS = {
    "LOG_ENABLED": "false",
    "LOG_DIR": "logs",
    "LOG_FILE_NAME": "togf_save.log",
    "LOG_LEVEL": "DEBUG",
    "LOG_CONSOLE_LEVEL": "INFO",
    "LOG_ROTATION": "10 MB",
    "LOG_RETENTION": "14 days",
    "LOG_COMPRESSION": "",
    "LOG_FORMAT": FILE_FORMAT,
    "LOG_SERIALIZE": "false",
    "LOG_BACKTRACE": "true",
    "LOG_DIAGNOSE": "false",
    "LOG_ENQUEUE": "true",
}

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def env_str(name: str) -> str:
    """The variable, or its default when unset or blank."""
    return os.environ.get(name, "").strip() or DEFAULTS[name]


def env_bool(name: str) -> bool:
    value = env_str(name).lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name}={value!r}: expected true or false")


def _count_or_text(value: str) -> int | str:
    """loguru takes a plain number as a file count ("10") and text as a duration or size."""
    return int(value) if value.isdigit() else value


def setup(verbose: int = 0, console: bool = False) -> None:
    """Replace every loguru sink with the configured ones.

    verbose: the CLI's -v count; 1 = INFO and 2+ = DEBUG on the console, regardless of LOG_*.
    console: log to the console at LOG_CONSOLE_LEVEL even without -v (the web server).
    """
    logger.remove()
    sinks = 0
    if verbose or console:
        level = ("DEBUG" if verbose > 1 else "INFO") if verbose else env_str("LOG_CONSOLE_LEVEL").upper()
        logger.add(sys.stderr, level=level, format=CONSOLE_FORMAT)
        sinks += 1
    if env_bool("LOG_ENABLED"):
        directory = Path(env_str("LOG_DIR"))
        directory.mkdir(parents=True, exist_ok=True)
        compression = env_str("LOG_COMPRESSION")
        try:
            logger.add(directory / env_str("LOG_FILE_NAME"),
                       level=env_str("LOG_LEVEL").upper(),
                       format=env_str("LOG_FORMAT"),
                       rotation=_count_or_text(env_str("LOG_ROTATION")),
                       retention=_count_or_text(env_str("LOG_RETENTION")),
                       compression=compression or None,
                       serialize=env_bool("LOG_SERIALIZE"),
                       backtrace=env_bool("LOG_BACKTRACE"),
                       diagnose=env_bool("LOG_DIAGNOSE"),
                       enqueue=env_bool("LOG_ENQUEUE"),
                       encoding="utf-8")
        except (ValueError, TypeError) as e:
            raise ValueError(f"log file settings (LOG_*): {e}") from None
        sinks += 1
    if sinks:
        logger.enable("togf_save")
    else:
        logger.disable("togf_save")
