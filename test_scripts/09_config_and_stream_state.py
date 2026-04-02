"""Exercise: StreamConfig knobs, stream.state, reconnect_count (non-RTSP is 0)."""

from __future__ import annotations

import numpy as np

from easy_rtsp import Stream, StreamState
from easy_rtsp.config import StreamConfig


def main() -> None:
    cfg = StreamConfig(
        preset="default",
        fps=15.0,
        input_realtime_pace=None,
        server_host="127.0.0.1",
        server_port=8554,
    )

    def gen():
        yield np.zeros((24, 32, 3), dtype=np.uint8)

    s = Stream.from_frames(gen, fps=30.0, size=(32, 24), config=cfg)
    print(f"state before frames: {s.state}")
    print(f"reconnect_count (non-RTSP): {s.reconnect_count}")
    next(iter(s.frames()))
    print(f"state after first frame: {s.state}")
    assert s.state == StreamState.RUNNING
    print("config.preset:", s.config.preset)
    print("viewer_url before serve:", s.viewer_url)


if __name__ == "__main__":
    main()
