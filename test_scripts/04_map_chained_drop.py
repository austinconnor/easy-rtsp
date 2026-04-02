"""Exercise: chained map().map() and dropping frames (callback returns None)."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    def gen():
        for i in range(10):
            yield np.full((16, 16, 3), i, dtype=np.uint8)

    def add_border(f: np.ndarray) -> np.ndarray:
        out = f.copy()
        out[0, :, :] = 200
        out[-1, :, :] = 200
        return out

    def keep_odd_only(f: np.ndarray) -> np.ndarray | None:
        v = int(f[1, 1, 0])
        return f if v % 2 == 1 else None

    s = Stream.from_frames(gen, fps=30.0, size=(16, 16)).map(add_border).map(keep_odd_only)
    kept = list(s.frames())
    print(f"frames kept: {len(kept)} (expected 5)")
    print(f"first kept value at (1,1): {kept[0][1, 1, 0]}")


if __name__ == "__main__":
    main()
