"""RTSP URL ingest."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from urllib.parse import urlparse

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import (
    VideoProbe,
    ffmpeg_ingest_rtsp_args,
    ffmpeg_rtsp_input_options,
    probe_video,
)
from easy_rtsp.log import get_logger
from easy_rtsp.serve_url import redact_url_credentials
from easy_rtsp.sources.base import ensure_bgr_uint8
from easy_rtsp.sources.decode import iter_raw_bgr_frames

_logger = get_logger("ingest.rtsp")


class RtspSource:
    """Decode an RTSP stream to BGR frames via FFmpeg."""

    def __init__(self, url: str, config: StreamConfig | None = None) -> None:
        raw = (url or "").strip()
        parsed = urlparse(raw) if "://" in raw else None
        if parsed is None or parsed.scheme.lower() not in ("rtsp", "rtsps") or not parsed.hostname:
            raise SourceError(f"Not an RTSP URL: {redact_url_credentials(url)!r}")
        self._url = raw
        self._config = config or StreamConfig()
        self._reconnect_count = 0
        self._last_reconnect_reason: str | None = None
        self._cached_probe: VideoProbe | None = None
        self._stop_event: threading.Event | None = None
        self._on_reconnecting_internal: Callable[[int, str], None] | None = None

    @property
    def config(self) -> StreamConfig:
        return self._config

    @property
    def url(self) -> str:
        """Source URL, including any credentials (use ``redact_url_credentials`` before logging)."""
        return self._url

    @property
    def reconnect_count(self) -> int:
        """How many reconnects have been scheduled after a disconnect or probe failure."""
        return self._reconnect_count

    @property
    def last_reconnect_reason(self) -> str | None:
        """Reason recorded for the most recent reconnect attempt or terminal failure."""
        return self._last_reconnect_reason

    def record_reconnect(self, reason: str, *, sleep: bool = True) -> int:
        """Record a reconnect attempt and optionally sleep unless stopped."""
        self._reconnect_count += 1
        self._last_reconnect_reason = reason
        interval = max(0.0, float(self._config.retry_interval_sec))
        _logger.warning(
            "RTSP disconnected or session ended (%s); reconnecting in %.2fs (reconnect #%s)",
            reason,
            interval,
            self._reconnect_count,
        )
        if self._on_reconnecting_internal is not None:
            self._on_reconnecting_internal(self._reconnect_count, reason)
        if self._config.on_reconnecting is not None:
            self._config.on_reconnecting(self._reconnect_count)
        if sleep and interval:
            if self._stop_event is not None:
                self._stop_event.wait(interval)
            else:
                time.sleep(interval)
        return self._reconnect_count

    def frames(self) -> Iterator[np.ndarray]:
        """Yield decoded frames; reconnects according to :class:`~easy_rtsp.config.StreamConfig`."""
        safe_url = redact_url_credentials(self._url)
        while True:
            if self._stop_event is not None and self._stop_event.is_set():
                break
            try:
                if self._cached_probe is not None:
                    probe = self._cached_probe
                    self._cached_probe = None
                else:
                    probe = probe_video(
                        self._url,
                        input_args=ffmpeg_rtsp_input_options(
                            self._config.transport,
                            self._config.latency_ms,
                        ),
                    )
            except DependencyError:
                raise
            except Exception as e:
                if self._stop_event is not None and self._stop_event.is_set():
                    break
                if not self._config.reconnect or self._reconnect_exhausted():
                    raise SourceError(f"RTSP probe failed for {safe_url!r}: {e}") from e
                self.record_reconnect("probe_failed")
                continue

            w, h = probe.width, probe.height
            input_args = ffmpeg_ingest_rtsp_args(
                self._url, self._config.transport, self._config.latency_ms
            )
            input_args = self._config.extra_ffmpeg_input_args + input_args
            decode_args = [
                *input_args,
                "-an",
                "-fflags",
                "nobuffer",
                "-flags",
                "low_delay",
            ]

            try:
                for frame in iter_raw_bgr_frames(
                    decode_args,
                    w,
                    h,
                    proc_holder=self._config.ffmpeg_children,
                    stop_event=self._stop_event,
                ):
                    if self._stop_event is not None and self._stop_event.is_set():
                        return
                    yield ensure_bgr_uint8(frame, context="RtspSource")
            except SourceError as e:
                if self._stop_event is not None and self._stop_event.is_set():
                    break
                if not self._config.reconnect or self._reconnect_exhausted():
                    raise SourceError(
                        f"RTSP decode failed for {safe_url!r} "
                        f"(reconnect_count={self._reconnect_count}): {e}"
                    ) from e
                self.record_reconnect("decode_failed")
                continue

            if self._stop_event is not None and self._stop_event.is_set():
                break
            # FFmpeg exited cleanly (e.g. stream ended).
            if not self._config.reconnect:
                break
            if self._reconnect_exhausted():
                _logger.info(
                    "RTSP stream ended; max reconnect attempts (%s) reached",
                    self._config.max_reconnect_attempts,
                )
                break
            self.record_reconnect("stream_ended")

    def _reconnect_exhausted(self) -> bool:
        m = self._config.max_reconnect_attempts
        if m is None:
            return False
        return self._reconnect_count >= m
