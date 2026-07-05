"""Centralized logging configuration for the application.

This module provides a unified logging setup with colorized console output,
optional file logging, and environment-based configuration.

Usage
-----
    from gitingest.utils.logger import get_logger

    logger = get_logger("ingestion")
    logger.info("Processing started")
    logger.warning("File size limit reached")
    logger.error("Failed to process file")
"""

import logging
import os
import sys
from typing import Optional


class _LogColors:
    """ANSI color codes for terminal output."""

    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BROWN = "\033[0;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    LIGHT_GRAY = "\033[0;37m"
    DARK_GRAY = "\033[1;30m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    WHITE = "\033[1;37m"
    BOLD = "\033[1m"
    FAINT = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    NEGATIVE = "\033[7m"
    CROSSED = "\033[9m"
    END = "\033[0m"


_LEVEL_COLORS = {
    "DEBUG": _LogColors.FAINT,
    "INFO": _LogColors.GREEN,
    "WARNING": _LogColors.YELLOW,
    "ERROR": _LogColors.RED,
    "CRITICAL": _LogColors.LIGHT_RED + _LogColors.BOLD,
}


class _ColoredFormatter(logging.Formatter):
    """Custom formatter that adds ANSI color codes to log level names.

    .. important::

       This formatter **restores** ``record.levelname`` after formatting so that
       other handlers attached to the same logger (e.g. a file handler) do **not**
       see ANSI-escaped level names in their output.
    """

    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = _LEVEL_COLORS.get(original_levelname, "")
        record.levelname = f"{color}{original_levelname}{_LogColors.END}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


# ── Module-level sentinel to ensure setup runs only once ──
_initialized: bool = False


def setup_logging(
    name: str = "repoingest",
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """Set up and return a configured root logger instance.

    Call this **once** at application startup.  Subsequent calls return the
    already-configured logger without adding duplicate handlers.

    Parameters
    ----------
    name : str
        Root logger name, defaults to ``"repoingest"``.
    log_level : str, optional
        One of ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``.
        Falls back to the ``REPOINGEST_LOG_LEVEL`` environment variable,
        then to ``INFO``.
    log_file : str, optional
        Path to a log file.  Falls back to the ``REPOINGEST_LOG_FILE``
        environment variable.  When set, logs are written both to the
        console and to the file.

    Returns
    -------
    logging.Logger
        The configured root logger.
    """
    global _initialized  # noqa: PLW0603

    level = (log_level or os.getenv("REPOINGEST_LOG_LEVEL") or "INFO").upper()

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Prevent duplicate handlers if setup_logging is called more than once
    if _initialized:
        return logger

    # ── Console handler (colorized when attached to a real terminal) ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    if sys.stdout.isatty():
        formatter = _ColoredFormatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ── Optional file handler ──
    file_path = log_file or os.getenv("REPOINGEST_LOG_FILE")
    if file_path:
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    _initialized = True
    return logger


def get_logger(child_name: str) -> logging.Logger:
    """Return a child logger under the ``repoingest`` namespace.

    Parameters
    ----------
    child_name : str
        Sub-namespace for the logger (e.g. ``"server"``, ``"cloning"``).

    Returns
    -------
    logging.Logger
        A child logger whose output flows through the root ``repoingest``
        logger's handlers (set up once via :func:`setup_logging`).
    """
    return logging.getLogger(f"repoingest.{child_name}")
