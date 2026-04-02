"""Source adapter protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Protocol, runtime_checkable

import numpy as np

if TYPE_CHECKING:
    from easy_rtsp.config import StreamConfig


@runtime_checkable
class FrameSource(Protocol):
    """Produces BGR ``uint8`` frames (HWC) and optional metadata."""

    @property
    def config(self) -> StreamConfig:
        ...

    def frames(self) -> Iterator[np.ndarray]:
        """Yield decoded frames; each array has shape ``(H, W, 3)`` and dtype ``uint8``."""
        ...


def ensure_bgr_uint8(frame: np.ndarray, *, context: str) -> np.ndarray:
    """Validate frame layout for the public contract."""
    if frame.dtype != np.uint8:
        raise ValueError(f"{context}: expected uint8 frame, got {frame.dtype}")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"{context}: expected HWC BGR with 3 channels, got shape {frame.shape}")
    return frame
