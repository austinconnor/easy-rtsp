"""Frame generator source."""

import numpy as np

from easy_rtsp import Stream


def _solid_frames() -> np.ndarray:
    for _ in range(3):
        yield np.zeros((480, 640, 3), dtype=np.uint8)


def test_from_frames_iteration() -> None:
    s = Stream.from_frames(_solid_frames(), fps=30.0, size=(640, 480))
    frames = list(s.frames())
    assert len(frames) == 3
    assert frames[0].shape == (480, 640, 3)
