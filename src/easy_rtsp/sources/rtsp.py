"""RTSP URL ingest."""

from __future__ import annotations

import time
from collections.abc import Iterator

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import ffmpeg_ingest_rtsp_args, probe_video
from easy_rtsp.log import get_logger
from easy_rtsp.sources.base import ensure_bgr_uint8
from easy_rtsp.sources.decode import iter_raw_bgr_frames

_logger = get_logger("ingest.rtsp")


class RtspSource:
    """Decode an RTSP stream to BGR frames via FFmpeg."""

    def __init__(self, url: str, config: StreamConfig | None = None) -> None:
        if not url or not (url.startswith("rtsp://") or url.startswith("rtsps://")):
            raise SourceError(f"Not an RTSP URL: {url!r}")
        self._url = url
        self._config = config or StreamConfig()
        self._reconnect_count = 0
        self._last_reconnect_reason: str | None = None

    @property
    def config(self) -> StreamConfig:
        return self._config

    @property
    def reconnect_count(self) -> int:
        """How many reconnects have been scheduled after a disconnect or probe failure."""
        return self._reconnect_count

    @property
    def last_reconnect_reason(self) -> str | None:
        """Reason recorded for the most recent reconnect attempt or terminal failure."""
        return self._last_reconnect_reason

    def frames(self) -> Iterator[np.ndarray]:
        """Yield decoded frames; reconnects according to :class:`~easy_rtsp.config.StreamConfig`."""
        while True:
            try:
                probe = probe_video(self._url)
            except DependencyError:
                raise
            except Exception as e:
                if not self._config.reconnect or self._reconnect_exhausted():
                    raise SourceError(f"RTSP probe failed for {self._url!r}: {e}") from e
                self._notify_reconnect("probe_failed")
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
                    decode_args, w, h, proc_holder=self._config.ffmpeg_children
                ):
                    yield ensure_bgr_uint8(frame, context="RtspSource")
            except SourceError as e:
                if not self._config.reconnect or self._reconnect_exhausted():
                    raise SourceError(
                        f"RTSP decode failed for {self._url!r} (reconnect_count={self._reconnect_count}): {e}"
                    ) from e
                self._notify_reconnect("decode_failed")
                continue

            # FFmpeg exited cleanly (e.g. stream ended).
            if not self._config.reconnect:
                break
            if self._reconnect_exhausted():
                _logger.info(
                    "RTSP stream ended; max reconnect attempts (%s) reached",
                    self._config.max_reconnect_attempts,
                )
                break
            self._notify_reconnect("stream_ended")

    def _reconnect_exhausted(self) -> bool:
        m = self._config.max_reconnect_attempts
        if m is None:
            return False
        return self._reconnect_count >= m

    def _notify_reconnect(self, reason: str) -> None:
        self._reconnect_count += 1
        self._last_reconnect_reason = reason
        interval = max(0.0, float(self._config.retry_interval_sec))
        _logger.warning(
            "RTSP disconnected or session ended (%s); reconnecting in %.2fs (reconnect #%s)",
            reason,
            interval,
            self._reconnect_count,
        )
        if self._config.on_reconnecting is not None:
            self._config.on_reconnecting(self._reconnect_count)
        if interval:
            time.sleep(interval)
