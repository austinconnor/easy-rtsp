"""Public types and stream state."""

from __future__ import annotations

from enum import Enum


class StreamState(str, Enum):
    """High-level lifecycle state for a :class:`~easy_rtsp.Stream`."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    ERROR = "error"
