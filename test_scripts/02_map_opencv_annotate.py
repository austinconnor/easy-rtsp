"""Exercise: map() with OpenCV drawing (BGR uint8 frames)."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    import cv2

    def gen():
        yield np.zeros((48, 64, 3), dtype=np.uint8)

    def annotate(frame: np.ndarray) -> np.ndarray:
        out = frame.copy()
        cv2.rectangle(out, (2, 2), (62, 46), (0, 255, 0), 2)
        cv2.putText(
            out,
            "easy-rtsp",
            (4, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        return out

    s = Stream.from_frames(gen, fps=30.0, size=(64, 48)).map(annotate)
    frame = next(iter(s.frames()))
    print(f"annotated frame mean BGR: {frame.mean(axis=(0, 1))}")


if __name__ == "__main__":
    main()
