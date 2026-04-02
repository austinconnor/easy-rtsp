"""Webcam / camera ingest (OpenCV)."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.sources.base import ensure_bgr_uint8

_DEFAULT_PROBE_TIMEOUT_SEC = 15.0


def probe_webcam_dimensions(index: int, *, timeout_sec: float = _DEFAULT_PROBE_TIMEOUT_SEC) -> tuple[int, int]:
    """
    Return ``(width, height)`` for a camera index via OpenCV.

    The probe runs in a thread with *timeout_sec* so a stuck driver does not hang forever.
    """
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError as e:
        raise DependencyError(
            "OpenCV (cv2) is required for webcam capture but could not be imported. "
            "Reinstall easy-rtsp or install opencv-python-headless."
        ) from e

    result: list[tuple[int, int]] = []
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
                result.append((max(w, 1), max(h, 1)))
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
        raise SourceError(f"Could not read webcam dimensions for index {index}")
    return result[0]


class WebcamSource:
    """Capture from a camera index using OpenCV when available."""

    def __init__(self, index: int = 0, config: StreamConfig | None = None) -> None:
        self._index = index
        self._config = config or StreamConfig()

    @property
    def config(self) -> StreamConfig:
        return self._config

    def frames(self) -> Iterator[np.ndarray]:
        try:
            import cv2  # type: ignore[import-untyped]
        except ImportError as e:
            raise DependencyError(
                "OpenCV (cv2) is required for webcam capture but could not be imported. "
                "Reinstall easy-rtsp or install opencv-python-headless."
            ) from e

        cap = cv2.VideoCapture(self._index)
        if not cap.isOpened():
            raise SourceError(f"Could not open webcam index {self._index}")
        try:
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                yield ensure_bgr_uint8(frame, context="WebcamSource")
        finally:
            cap.release()
