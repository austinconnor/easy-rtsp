"""Exercise: Stream.from_frames + frames() iterator (no FFmpeg / no publish)."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    def solid_frames():
        for i in range(5):
            yield np.full((48, 64, 3), i * 40, dtype=np.uint8)

    s = Stream.from_frames(solid_frames, fps=30.0, size=(64, 48))
    for n, frame in enumerate(s.frames()):
        print(f"frame {n}: shape={frame.shape} dtype={frame.dtype} mean={frame.mean():.1f}")


if __name__ == "__main__":
    main()
