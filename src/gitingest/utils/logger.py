"""Centralized logging configuration for the application.

This module provides a unified logging setup built on top of Loguru.  It
replaces the previous stdlib ``logging`` based configuration and adds:

* Full timestamps (``YYYY-MM-DD HH:mm:ss.SSS``) on every line, console included.
* Daily rotating file logs with retention and compression.
* Context binding helpers (``request_id``, ``client_ip``, ...) for request tracing.
* A bridge that routes standard library ``logging`` records (uvicorn,
  aiohttp, gitpython, ...) through the same Loguru pipeline.

Usage
-----
    from gitingest.utils.logger import get_logger

    logger = get_logger("ingestion")
    logger.info("Processing started")
    logger.warning("File size limit reached: {}", path)
    logger.error("Failed to process file: {}", exc)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from loguru import logger as _base_logger

# ── Environment defaults ──
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_ROTATION = "00:00"
_DEFAULT_RETENTION = "14 days"
_DEFAULT_COMPRESSION = "gz"

# Optional extra fields rendered in the human-readable output when present
# (bound via ``logger.contextualize(...)`` by the request middleware).
_CONTEXT_LABELS = (
    ("request_id", "rid"),
    ("client_ip", "ip"),
    ("method", "method"),
    ("path", "path"),
)


def _make_formatter(colorize: bool):
    """Build a Loguru formatter callable for the human-readable text output.

    The timestamp always includes the full date (``YYYY-MM-DD HH:mm:ss.SSS``).
    Request context fields are only rendered when bound (e.g. inside a request
    handled by the request logging middleware), keeping background/CLI logs
    clean.
    """

    def _format(record: dict) -> str:
        time_s = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_s = f"{record['level'].name: <8}"
        module_s = record["extra"].get("module", record["name"])

        if colorize:
            parts = [f"<green>{time_s}</green> | <level>{level_s}</level> | {module_s}"]
        else:
            parts = [f"{time_s} | {level_s} | {module_s}"]

        for key, label in _CONTEXT_LABELS:
            value = record["extra"].get(key)
            if value:
                parts.append(f"{label}={value}")

        if colorize:
            parts.append("<level>{message}</level>")
        else:
            parts.append("{message}")

        # Loguru renders the traceback only when `{exception}` is present.
        if record["exception"] is not None:
            parts.append("{exception}")

        return " | ".join(parts) + "\n"

    return _format


def _env(name: str, default: str) -> str:
    """Read an environment variable, returning ``default`` when unset/empty."""
    value = os.getenv(name)
    return value if value else default


class _InterceptHandler(logging.Handler):
    """Route stdlib ``logging`` records into the Loguru pipeline.

    Attach this handler to the root stdlib logger so that third party
    libraries (uvicorn, aiohttp, gitpython, ...) share the same console/file
    sinks, format and rotation as the application logs.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = _base_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        _base_logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            record.getMessage(),
            module=f"stdlib.{record.name}",
        )


def _setup_stdlib_bridge() -> None:
    """Redirect the stdlib ``logging`` root logger into Loguru.

    The uvicorn access logger is disabled because the request logging
    middleware already records every request with richer context (request id,
    client ip, duration).
    """
    handler = _InterceptHandler()
    logging.basicConfig(handlers=[handler], level=0, force=True)
    logging.getLogger("uvicorn.access").disabled = True


# ── Module-level sentinel to ensure setup runs only once ──
_initialized: bool = False


def setup_logging(
    name: str = "repoingest",
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> None:
    """Configure the Loguru logger: colorized console + rotating file sinks.

    Call this **once** at application startup.  Subsequent calls are no-ops
    (the existing sinks are kept) and never duplicate handlers.

    Parameters
    ----------
    name : str
        Root logger namespace.  Kept for API compatibility; every logger
        returned by :func:`get_logger` is namespaced under it.
    log_level : str, optional
        One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``.
        Falls back to the ``REPOINGEST_LOG_LEVEL`` environment variable,
        then to ``INFO``.
    log_file : str, optional
        Path to the log file.  Falls back to the ``REPOINGEST_LOG_FILE``
        environment variable.  When set, logs are written both to the console
        and to a rotating file.
    """
    global _initialized  # noqa: PLW0603

    if _initialized:
        return

    level = (log_level or _env("REPOINGEST_LOG_LEVEL", _DEFAULT_LOG_LEVEL)).upper()

    # Remove Loguru's default handler to avoid duplicate console output
    _base_logger.remove()

    # ── Console sink (colorized when attached to a real terminal) ──
    if _env("REPOINGEST_LOG_TO_STDOUT", "1") == "1":
        _base_logger.add(
            sys.stderr,
            level=level,
            format=_make_formatter(colorize=sys.stderr.isatty()),
            colorize=sys.stderr.isatty(),
            backtrace=True,
            diagnose=False,
        )

    # ── Rotating file sink ──
    file_path = log_file or _env("REPOINGEST_LOG_FILE", "")
    if file_path:
        serialize = _env("REPOINGEST_LOG_JSON", "0") == "1"
        _base_logger.add(
            file_path,
            level="DEBUG",
            format=_make_formatter(colorize=False),
            rotation=_env("REPOINGEST_LOG_ROTATION", _DEFAULT_ROTATION),
            retention=_env("REPOINGEST_LOG_RETENTION", _DEFAULT_RETENTION),
            compression=_env("REPOINGEST_LOG_COMPRESSION", _DEFAULT_COMPRESSION),
            encoding="utf-8",
            enqueue=True,
            backtrace=True,
            diagnose=False,
            serialize=serialize,
        )

    _setup_stdlib_bridge()

    _initialized = True


def get_logger(child_name: str):
    """Return a Loguru logger bound to the ``repoingest.<child_name>`` namespace.

    Parameters
    ----------
    child_name : str
        Sub-namespace for the logger (e.g. ``"server"``, ``"cloning"``).

    Returns
    -------
    loguru.Logger
        A Loguru logger whose records are tagged with the given module.
    """
    return _base_logger.bind(module=f"repoingest.{child_name}")
