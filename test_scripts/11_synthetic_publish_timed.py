"""
Exercise: from_frames + map + serve, then stop after a few seconds.

Requires FFmpeg on PATH. If MediaMTX is on PATH and port 8554 is free, you get rtsp://...
Otherwise MPEG-TS over tcp:// (see stderr warning).

Run: uv run python test_scripts/11_synthetic_publish_timed.py
"""

from __future__ import annotations

import threading
import time

import numpy as np

from easy_rtsp import Stream


def main() -> None:
    import cv2

    def frame_factory():
        t0 = time.monotonic()
        while True:
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            cv2.putText(
                frame,
                time.strftime("%H:%M:%S"),
                (4, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
            # subtle motion so you can see time advance in a player
            x = int((time.monotonic() - t0) * 20) % 50
            cv2.circle(frame, (10 + x, 40), 3, (255, 0, 0), -1)
            yield frame

    stream = Stream.from_frames(
        frame_factory, fps=30.0, size=(64, 48), preset="low_latency"
    ).serve("live")
    print(f"Play: {stream.viewer_url}", flush=True)

    def stop_soon() -> None:
        time.sleep(8.0)
        stream.stop()

    threading.Thread(target=stop_soon, daemon=True).start()
    stream.wait()


if __name__ == "__main__":
    main()
