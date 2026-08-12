"""
Shared structured logging setup, used by both the CLI (src/main.py) and the
Streamlit app (app/common.py) so file and console output are always
JSON-formatted and stamped with a correlation id - a CLI run_id for main.py,
a per-browser-session id for Streamlit - the same way, regardless of which
surface produced them.

Previously this lived only in src/main.py (file handler JSON, console
handler plain-text) - moved here unchanged in behavior for the CLI, plus
generalized so the console handler is JSON too and so a caller that reruns
its entry script repeatedly (Streamlit) doesn't have to reconfigure logging
or open a new log file on every rerun.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from pathlib import Path

from config.app_config import AppConfig

LOGGER_NAME = "kg_local"

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "kg_local_correlation_id", default=None
)


def set_correlation_id(correlation_id: str) -> None:
    """Associates every subsequent log record on this thread with
    correlation_id, until changed again. Used by Streamlit pages to stamp
    each rerun with the current browser session's id without having to pass
    a logger instance around."""
    _correlation_id_var.set(correlation_id)


class RunIdFilter(logging.Filter):
    """Stamps every log record with the active correlation id: whatever
    set_correlation_id() last set on this thread, falling back to the id
    this filter was constructed with (main.py's one-run-per-process id)."""

    def __init__(self, default_correlation_id: str | None = None) -> None:
        super().__init__()
        self.default_correlation_id = default_correlation_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _correlation_id_var.get() or self.default_correlation_id
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", None),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(config: AppConfig, run_id: str) -> Path:
    """CLI entry point: one JSON log file per invocation plus a JSON
    console stream, both stamped with run_id. Behavior-preserving move from
    src/main.py, except the console handler is now JSON (was plain-text) for
    consistency with the file handler."""
    log_dir = config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"ingest_{time.strftime('%Y%m%d_%H%M%S')}.log"

    set_correlation_id(run_id)
    run_id_filter = RunIdFilter(default_correlation_id=run_id)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(run_id_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    console_handler.addFilter(run_id_filter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler], force=True)
    return log_path


def configure_streamlit_logging(config: AppConfig) -> Path | None:
    """Process-wide, one-time logging setup for the Streamlit app: same JSON
    file+console handlers as the CLI, but guarded so re-running the
    Streamlit entry script (which happens on every user interaction) does
    not reopen a new log file or duplicate handlers. Returns the log file
    path on the call that actually configured logging, None on later calls
    that were no-ops."""
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return None

    log_dir = config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"streamlit_{time.strftime('%Y%m%d_%H%M%S')}.log"

    run_id_filter = RunIdFilter()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(run_id_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    console_handler.addFilter(run_id_filter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    return log_path
