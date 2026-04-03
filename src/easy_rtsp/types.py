"""Public types and stream state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StreamState(str, Enum):
    """High-level lifecycle state for a :class:`~easy_rtsp.Stream`."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class StreamStatus:
    """Immutable snapshot of a stream's current health and lifecycle state."""

    state: StreamState
    reconnect_count: int
    serve_started: bool
    latest_frame_available: bool
    viewer_url: str | None
    webrtc_play_url: str | None
    publish_error: str | None
    created_at: float
    last_state_change_at: float
    publish_thread_alive: bool
    last_reconnect_reason: str | None
    dropped_frame_count: int
    last_frame_at: float | None
    publish_started_at: float | None
    publish_uptime_sec: float | None
    alive_child_process_count: int

    @property
    def has_publish_error(self) -> bool:
        """Whether the stream has seen a publish failure."""
        return self.publish_error is not None
