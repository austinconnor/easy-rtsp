"""Stream and ingest configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

Transport = Literal["tcp", "udp"]
Backend = Literal["auto", "ffmpeg"]


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

    reconnect: bool = True
    """Whether to retry RTSP ingest after disconnect."""

    retry_interval_sec: float = 2.0
    """Delay between reconnect attempts."""

    max_reconnect_attempts: int | None = None
    """Maximum RTSP ingest reconnect attempts (``None`` = unlimited)."""

    queue_size: int = 8
    """Bounded queue depth between decode and publish when applicable."""

    server_host: str = "127.0.0.1"
    """Default host for shorthand ``serve(\"path\")`` URLs."""

    server_port: int = 8554
    """Default RTSP port for shorthand ``serve(\"path\")`` URLs."""

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
