# Relay and transform

## Relay without touching frames

```console
easy-rtsp relay rtsp://camera.local/live --serve live
```

RTSP input reconnects by default. Configure the retry policy with `--retry-interval`, `--max-reconnect-attempts`, or `--no-reconnect`.

## Transform frames

`map()` receives OpenCV-style BGR `uint8` NumPy arrays shaped `(height, width, 3)`.

```python
import cv2

from easy_rtsp import Stream


def label(frame):
    cv2.putText(
        frame,
        "front gate",
        (24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2,
    )
    return frame


stream = (
    Stream.open("rtsp://camera.local/live")
    .map(label)
    .serve("annotated")
)
stream.wait()
```

Return `None` to drop a frame. Maps can be chained and run in order.

```python
stream = Stream.open(url).map(resize).map(detect).map(draw)
```

## Preserve source audio

For an unmodified RTSP relay, request passthrough audio:

```python
Stream.open(
    "rtsp://camera.local/live",
    audio_mode="passthrough",
).serve("live").wait()
```

Audio passthrough is intentionally rejected when frame transforms are present because the decoded video pipeline and untouched source timeline cannot be safely combined without additional synchronization complexity.

## Custom frame generators

```python
import numpy as np

from easy_rtsp import Stream


def frames():
    while True:
        yield np.zeros((720, 1280, 3), dtype=np.uint8)


Stream.from_frames(
    frames,
    fps=30,
    size=(1280, 720),
).serve("synthetic").wait()
```
