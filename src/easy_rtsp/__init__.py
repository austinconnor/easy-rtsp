"""easy-rtsp — ingest, transform, and re-host video over RTSP."""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from easy_rtsp.exceptions import (
    ConfigurationError,
    DependencyError,
    EasyRtspError,
    ProcessingError,
    PublishError,
    SourceError,
)

# Heavy symbols (Stream, numpy chain, logging) load on first use so
# ``import easy_rtsp.install_backends`` and lightweight tests stay fast.
_LAZY_ATTRS: dict[str, tuple[str, str]] = {
    "Stream": ("easy_rtsp.stream", "Stream"),
    "StreamState": ("easy_rtsp.types", "StreamState"),
    "StreamStatus": ("easy_rtsp.types", "StreamStatus"),
    "PublishDestination": ("easy_rtsp.serve_url", "PublishDestination"),
    "parse_publish_destination": ("easy_rtsp.serve_url", "parse_publish_destination"),
    "configure_logging": ("easy_rtsp.log", "configure_logging"),
    "get_logger": ("easy_rtsp.log", "get_logger"),
    "setup_cli_logging": ("easy_rtsp.log", "setup_cli_logging"),
}

__all__ = [
    "ConfigurationError",
    "configure_logging",
    "setup_cli_logging",
    "DependencyError",
    "EasyRtspError",
    "get_logger",
    "ProcessingError",
    "PublishError",
    "PublishDestination",
    "parse_publish_destination",
    "SourceError",
    "Stream",
    "StreamState",
    "StreamStatus",
]

try:
    __version__ = version("easy-rtsp")
except PackageNotFoundError:
    __version__ = "0.0.0"


def __getattr__(name: str) -> Any:
    spec = _LAZY_ATTRS.get(name)
    if spec is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    mod_name, attr = spec
    mod = importlib.import_module(mod_name)
    value = getattr(mod, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


if TYPE_CHECKING:
    from easy_rtsp.log import configure_logging, get_logger, setup_cli_logging
    from easy_rtsp.serve_url import PublishDestination, parse_publish_destination
    from easy_rtsp.stream import Stream
    from easy_rtsp.types import StreamState, StreamStatus
