"""Stream and ingest configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from numbers import Real
from typing import Any, Literal

from easy_rtsp.exceptions import ConfigurationError

Transport = Literal["tcp", "udp"]
Backend = Literal["auto", "ffmpeg"]
AudioMode = Literal["off", "passthrough"]


@dataclass
class StreamConfig:
    """Options for ingest, transforms, and publish paths."""

    transport: Transport = "tcp"
    """RTSP ingest transport when applicable."""

    latency_ms: int | None = None
    """Optional latency hint for RTSP ingest (milliseconds)."""

    codec: str = "h264"
    """Encoder output codec name for publish (v1: primarily H.264)."""

    video_encoder: str | None = None
    """If set, used as FFmpeg ``-c:v`` (e.g. ``h264_nvenc``, ``h264_qsv``). Overrides ``codec`` for encoding."""

    bitrate: str | None = None
    """Optional encoder bitrate, e.g. ``\"4M\"``."""

    audio_mode: AudioMode = "off"
    """Audio publishing mode. ``off`` disables audio, ``passthrough`` relays source audio when supported."""

    reconnect: bool = True
    """Whether to retry RTSP ingest after disconnect."""

    retry_interval_sec: float = 2.0
    """Delay between reconnect attempts."""

    max_reconnect_attempts: int | None = None
    """Maximum RTSP ingest reconnect attempts (``None`` = unlimited)."""

    queue_size: int = 8
    """Reserved queue depth for buffered pipelines; the current raw pipe path writes directly."""

    server_host: str = "127.0.0.1"
    """Default host for shorthand ``serve(\"path\")`` URLs."""

    server_port: int = 8554
    """Default RTSP port for shorthand ``serve(\"path\")`` URLs."""

    lan_access: bool = False
    """Expose a locally started MediaMTX server to other devices on the same network."""

    backend: Backend = "auto"
    """Media backend selection (v1 focuses on FFmpeg orchestration)."""

    preset: str = "default"
    """Named preset: ``default``, ``low_latency``, ``quality``."""

    input_realtime_pace: bool | None = None
    """If true, FFmpeg ``-re`` reads raw input at ``-r`` fps (steady pacing). If ``None``, default is on (smoother playback). Set ``False`` for lowest latency (may look jittery)."""

    fps: float | None = None
    """Output / publish frame rate. For files, if unset, FPS is taken from probe metadata (fallback 30)."""

    file_loop: bool = True
    """For :class:`~easy_rtsp.sources.file.FileSource`, restart decoding from the beginning after EOF."""

    extra_ffmpeg_input_args: list[str] = field(default_factory=list)
    """Additional FFmpeg arguments inserted before inputs (advanced)."""

    extra_ffmpeg_output_args: list[str] = field(default_factory=list)
    """Additional FFmpeg arguments before outputs (advanced)."""

    record_path: str | None = None
    """If set, duplicate the encoded stream to this MP4 path (FFmpeg ``tee``; requires RTSP push)."""

    hls_output_dir: str | None = None
    """If set, write HLS (``index.m3u8`` + segments) under this directory (FFmpeg ``tee``; requires RTSP push)."""

    hls_segment_time: float = 2.0
    """HLS segment duration in seconds when ``hls_output_dir`` is set."""

    webrtc_enabled: bool = False
    """When easy-rtsp starts MediaMTX locally, enable its WebRTC HTTP server (default off; RTSP remains available)."""

    webrtc_http_port: int = 8889
    """Port for MediaMTX WebRTC signaling HTTP listener (``webrtcAddress``)."""

    on_reconnecting: Callable[[int], None] | None = None
    """Optional callback ``(attempt_number)`` before each RTSP reconnect (after the first session ends)."""

    ffmpeg_children: list[Any] = field(default_factory=list, repr=False)
    """Internal: FFmpeg subprocesses (decode + encode) to terminate on :meth:`~easy_rtsp.stream.Stream.stop`."""

    def __post_init__(self) -> None:
        """Reject invalid values before they become obscure FFmpeg or socket errors."""
        if self.transport not in ("tcp", "udp"):
            raise ConfigurationError("transport must be 'tcp' or 'udp'")
        if self.backend not in ("auto", "ffmpeg"):
            raise ConfigurationError("backend must be 'auto' or 'ffmpeg'")
        if self.audio_mode not in ("off", "passthrough"):
            raise ConfigurationError("audio_mode must be 'off' or 'passthrough'")
        if self.preset not in ("default", "low_latency", "quality"):
            raise ConfigurationError("preset must be 'default', 'low_latency', or 'quality'")
        if not isinstance(self.codec, str) or not self.codec.strip():
            raise ConfigurationError("codec must be non-empty")
        if self.video_encoder is not None and (
            not isinstance(self.video_encoder, str) or not self.video_encoder.strip()
        ):
            raise ConfigurationError("video_encoder must be non-empty when provided")
        if self.bitrate is not None and (
            not isinstance(self.bitrate, str) or not self.bitrate.strip()
        ):
            raise ConfigurationError("bitrate must be non-empty when provided")
        if self.latency_ms is not None and (
            not isinstance(self.latency_ms, int)
            or isinstance(self.latency_ms, bool)
            or self.latency_ms < 0
        ):
            raise ConfigurationError("latency_ms must be zero or positive")
        if not _is_nonnegative_number(self.retry_interval_sec):
            raise ConfigurationError("retry_interval_sec must be zero or positive")
        if self.max_reconnect_attempts is not None and (
            not isinstance(self.max_reconnect_attempts, int)
            or isinstance(self.max_reconnect_attempts, bool)
            or self.max_reconnect_attempts < 0
        ):
            raise ConfigurationError("max_reconnect_attempts must be zero or positive")
        if (
            not isinstance(self.queue_size, int)
            or isinstance(self.queue_size, bool)
            or self.queue_size <= 0
        ):
            raise ConfigurationError("queue_size must be positive")
        if not isinstance(self.server_host, str) or not self.server_host.strip():
            raise ConfigurationError("server_host must be non-empty")
        if not isinstance(self.lan_access, bool):
            raise ConfigurationError("lan_access must be a boolean")
        _validate_port("server_port", self.server_port)
        _validate_port("webrtc_http_port", self.webrtc_http_port)
        if self.fps is not None and not _is_positive_number(self.fps):
            raise ConfigurationError("fps must be positive")
        if not _is_positive_number(self.hls_segment_time):
            raise ConfigurationError("hls_segment_time must be positive")


def _validate_port(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise ConfigurationError(f"{name} must be an integer between 1 and 65535")


def _is_nonnegative_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and value >= 0


def _is_positive_number(value: object) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and value > 0
