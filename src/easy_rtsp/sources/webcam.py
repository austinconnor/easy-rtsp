"""Webcam / camera ingest (OpenCV)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import VideoProbe, is_sane_fps
from easy_rtsp.sources.base import ensure_bgr_uint8

_DEFAULT_PROBE_TIMEOUT_SEC = 15.0


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as e:
        raise DependencyError(
            "OpenCV (cv2) is required for webcam capture but could not be imported. "
            'Install with: pip install "easy-rtsp[webcam]" (or pip install opencv-python-headless).'
        ) from e
    return cv2


def probe_webcam(index: int, *, timeout_sec: float = _DEFAULT_PROBE_TIMEOUT_SEC) -> VideoProbe:
    """
    Return the frame size and driver-reported FPS (``None`` if unknown) for a camera index.

    The probe runs in a thread with *timeout_sec* so a stuck driver does not hang forever.
    """
    cv2 = _import_cv2()
    result: list[VideoProbe] = []
    errors: list[BaseException] = []

    def _run() -> None:
        try:
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                errors.append(SourceError(f"Could not open webcam index {index}"))
                return
            try:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if w <= 0 or h <= 0:
                    ok, sample = cap.read()
                    if ok and sample is not None and getattr(sample, "ndim", 0) >= 2:
                        h, w = int(sample.shape[0]), int(sample.shape[1])
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                result.append(
                    VideoProbe(
                        width=max(w, 1), height=max(h, 1), fps=fps if is_sane_fps(fps) else None
                    )
                )
            finally:
                cap.release()
        except Exception as e:
            errors.append(e)

    th = threading.Thread(target=_run, name="easy-rtsp-webcam-probe", daemon=True)
    th.start()
    th.join(timeout=timeout_sec)
    if th.is_alive():
        raise SourceError(
            f"Timed out opening webcam index {index} after {timeout_sec}s. "
            "Check the device index, close other apps using the camera, and retry."
        )
    if errors:
        raise errors[0]
    if not result:
        raise SourceError(f"Could not read webcam properties for index {index}")
    return result[0]


def probe_webcam_dimensions(
    index: int, *, timeout_sec: float = _DEFAULT_PROBE_TIMEOUT_SEC
) -> tuple[int, int]:
    """Return ``(width, height)`` for a camera index (see :func:`probe_webcam`)."""
    probe = probe_webcam(index, timeout_sec=timeout_sec)
    return probe.width, probe.height


class WebcamSource:
    """Capture from a camera index using OpenCV when available."""

    def __init__(self, index: int = 0, config: StreamConfig | None = None) -> None:
        self._index = index
        self._config = config or StreamConfig()
        self._stop_event: threading.Event | None = None

    @property
    def config(self) -> StreamConfig:
        return self._config

    @property
    def index(self) -> int:
        """OpenCV camera device index."""
        return self._index

    def frames(self) -> Iterator[np.ndarray]:
        cv2 = _import_cv2()
        cap = cv2.VideoCapture(self._index)
        if not cap.isOpened():
            raise SourceError(f"Could not open webcam index {self._index}")
        try:
            while True:
                if self._stop_event is not None and self._stop_event.is_set():
                    break
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                yield ensure_bgr_uint8(frame, context="WebcamSource")
        finally:
            cap.release()
