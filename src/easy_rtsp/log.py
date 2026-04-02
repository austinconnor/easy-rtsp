"""Logging helpers for easy-rtsp (stdlib ``logging``)."""

from __future__ import annotations

import logging
import sys

_LOG = logging.getLogger("easy_rtsp")
if not _LOG.handlers:
    _LOG.addHandler(logging.NullHandler())
_LOG.setLevel(logging.WARNING)


def setup_cli_logging(verbose: bool = False) -> None:
    """
    Attach a stderr handler for the ``easy_rtsp`` logger (CLI entry points only).

    Library use keeps the default :class:`~logging.NullHandler` until the app
    configures logging; the CLI replaces it so WARNING/INFO are visible.
    """
    _LOG.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    _LOG.addHandler(h)
    _LOG.setLevel(logging.DEBUG if verbose else logging.INFO)


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a child logger under ``easy_rtsp``.

    Attach your own handlers on ``logging.getLogger("easy_rtsp")`` or this logger
    to receive ingest, reconnect, and backend messages.
    """
    if not name:
        return _LOG
    return _LOG.getChild(name)


def configure_logging(level: int = logging.INFO) -> None:
    """
    Ensure a basic stderr handler exists and set the ``easy_rtsp`` logger level.

    Call once from an application entry point for human-readable logs during development.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")
    _LOG.setLevel(level)
    if not _LOG.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        _LOG.addHandler(h)
