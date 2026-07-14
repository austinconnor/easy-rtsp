# Edge CV integrations

easy-rtsp is most useful at the edges of a computer-vision system: acquiring a stream, making Python frame processing approachable, and exposing the result through a URL that other tools already understand.

The goal is not to replace GStreamer, DeepStream, or Triton. It is to make the handoff to them obvious.

## Choose a pipeline shape

| Shape | Best for | Tradeoff |
| --- | --- | --- |
| **All Python**: source → easy-rtsp → `map()` → RTSP | One stream, lightweight OpenCV/NumPy or local inference | Every transform runs synchronously on the frame path. |
| **Media handoff**: easy-rtsp → RTSP → GStreamer/DeepStream | Native plugins, NVIDIA zero-copy processing, multi-stream analytics | A process and encoded-media boundary is introduced. |
| **Inference service**: easy-rtsp → `map()` → Triton → RTSP | Centralized models, independent model deployment, CPU/GPU inference servers | A synchronous request per frame can become the bottleneck. |

## Start with the simplest thing

For a model or CV function that already accepts NumPy arrays, use `map()`:

```python
from easy_rtsp import Stream


def detect_and_draw(frame):
    detections = model(frame)
    return draw(frame, detections)


Stream.open("rtsp://camera/live").map(detect_and_draw).serve("annotated").wait()
```

Frames are BGR `uint8` arrays with shape `(height, width, 3)`. Returning `None` drops the frame.

## Know when to move the boundary

`map()` is deliberately synchronous. The next source frame is not processed until the callback returns. This is excellent for a small, understandable pipeline, but it means:

- 80 ms inference caps processing near 12.5 frames per second.
- A remote inference timeout pauses the publish path.
- Multiple camera streams do not automatically batch together.
- CPU-side NumPy frames cannot preserve a DeepStream zero-copy GPU path.

Move to GStreamer/DeepStream when native media elements or device-memory pipelines matter. Move to Triton when model deployment, batching, metrics, or independent scaling matter.

## Preserve a useful output rate

Run expensive inference every *N* frames and reuse the last result between requests:

```python
class SampledInference:
    def __init__(self, infer, draw, every: int = 3):
        self.infer = infer
        self.draw = draw
        self.every = every
        self.frame_number = 0
        self.latest = None

    def __call__(self, frame):
        if self.frame_number % self.every == 0:
            self.latest = self.infer(frame)
        self.frame_number += 1
        return self.draw(frame, self.latest)


processor = SampledInference(model, draw, every=3)
stream = Stream.open(camera_url).map(processor).serve("annotated")
```

This keeps every output frame while reducing inference frequency. For asynchronous requests, bounded queues, or batching across cameras, keep that orchestration outside `map()` and feed completed frames through `Stream.from_frames()`.

## Integration guides

- [GStreamer](gstreamer.md) — consume an easy-rtsp URL in a native media pipeline.
- [NVIDIA DeepStream](deepstream.md) — use easy-rtsp as a clean RTSP source boundary for GPU analytics.
- [NVIDIA Triton](triton.md) — send NumPy tensors to a model server from a transform.

!!! tip "A practical rule"
    Keep easy-rtsp in control when Python is the product. Use RTSP as the boundary when a native media graph is the product.
