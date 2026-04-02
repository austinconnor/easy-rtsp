"""Synthetic or user-provided frame generators."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError
from easy_rtsp.sources.base import ensure_bgr_uint8


class FrameGeneratorSource:
    """Wrap a Python iterable or callable that yields BGR ``uint8`` frames."""

    def __init__(
        self,
        factory: Callable[[], Iterator[np.ndarray]] | Iterator[np.ndarray],
        *,
        fps: float,
        size: tuple[int, int],
        config: StreamConfig | None = None,
    ) -> None:
        self._factory = factory
        self.fps = float(fps)
        self.size = (int(size[0]), int(size[1]))
        if self.fps <= 0:
            raise ConfigurationError("fps must be positive")
        if self.size[0] <= 0 or self.size[1] <= 0:
            raise ConfigurationError("size must be positive (width, height)")
        self._config = config or StreamConfig()

    @property
    def config(self) -> StreamConfig:
        return self._config

    def frames(self) -> Iterator[np.ndarray]:
        it: Iterator[np.ndarray]
        if callable(self._factory):
            it = self._factory()
        else:
            it = iter(self._factory)
        w, h = self.size
        for frame in it:
            f = ensure_bgr_uint8(frame, context="FrameGeneratorSource")
            if f.shape[1] != w or f.shape[0] != h:
                raise ConfigurationError(
                    f"Frame shape {f.shape[:2]} does not match declared size {w}x{h}"
                )
            yield f
