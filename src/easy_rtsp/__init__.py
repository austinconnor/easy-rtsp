"""easy-rtsp — ingest, transform, and re-host video over RTSP."""

from easy_rtsp.exceptions import (
    ConfigurationError,
    DependencyError,
    EasyRtspError,
    ProcessingError,
    PublishError,
    SourceError,
)
from easy_rtsp.log import configure_logging, get_logger, setup_cli_logging
from easy_rtsp.serve_url import PublishDestination, parse_publish_destination
from easy_rtsp.stream import Stream
from easy_rtsp.types import StreamState

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
]

__version__ = "0.1.0"
