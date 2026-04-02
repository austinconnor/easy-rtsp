"""Exercise: map() with pure NumPy (crop, channel swap, scale) — no cv2 in the transform."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    def gen():
        yield np.arange(48 * 64 * 3, dtype=np.uint8).reshape(48, 64, 3)

    def crop_and_swap_r_b(f: np.ndarray) -> np.ndarray:
        patch = f[8:40, 8:56, :].copy()
        patch[:, :, [0, 2]] = patch[:, :, [2, 0]]
        out = np.zeros_like(f)
        out[8:40, 8:56, :] = patch
        return out

    s = Stream.from_frames(gen, fps=30.0, size=(64, 48)).map(crop_and_swap_r_b)
    f = next(iter(s.frames()))
    print(f"transformed shape={f.shape} center patch mean={f[24, 32].tolist()}")


if __name__ == "__main__":
    main()
