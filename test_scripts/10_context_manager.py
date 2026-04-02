"""Exercise: ``with Stream(...) as s`` — __exit__ calls stop() after the block."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    def gen():
        yield np.zeros((16, 16, 3), dtype=np.uint8)

    with Stream.from_frames(gen, fps=30.0, size=(16, 16)) as stream:
        n = sum(1 for _ in stream.frames())
        print(f"frames read in context: {n}")
    print("exited context (stream stopped)")


if __name__ == "__main__":
    main()
