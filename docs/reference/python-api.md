# Python API

The primary public surface is `easy_rtsp.Stream`.

## Constructors

| Call | Purpose |
| --- | --- |
| `Stream.open(url, **options)` | Open an RTSP or RTSPS input URL. |
| `Stream.open_rtsp(host, path="live", ...)` | Build an authenticated RTSP/RTSPS input safely. |
| `Stream.from_webcam(index=0, **options)` | Capture an OpenCV camera device. |
| `Stream.from_file(path, **options)` | Decode and optionally loop a video file. |
| `Stream.from_frames(factory, fps=..., size=..., **options)` | Consume BGR NumPy frames from Python. |

All `**options` are validated against [`StreamConfig`](configuration.md). Unknown fields fail immediately.

## Processing

### `map(fn) -> Stream`

Returns a stream wrapper that applies `fn(frame)` to every frame. The callback must return a BGR `uint8` array or `None`.

### `frames() -> Iterator[np.ndarray]`

Iterates processed frames without publishing.

### `latest_frame(copy=True) -> np.ndarray | None`

Returns the latest processed frame. The default defensive copy is safe to mutate.

### `save_snapshot(path) -> Path`

Encodes the latest frame with OpenCV and returns the resolved path. Raises `ProcessingError` until a frame is available.

## Publishing

### `serve(endpoint="live", **options) -> Stream`

Starts publishing in a background thread. The endpoint may be a shorthand path, an RTSP/RTSPS URL, or an SRT URL.

### `serve_rtsp(host, path="live", ...) -> Stream`

Builds a destination URL from connection parts and safely encodes credentials.

### `wait(timeout=None) -> bool`

Waits for publishing to finish. Returns `False` when a finite timeout expires first.

### `stop() -> None`

Stops FFmpeg children and the locally managed MediaMTX process.

Streams are context managers:

```python
with Stream.from_file("clip.mp4").serve("live") as stream:
    stream.wait()
```

## Runtime properties

| Property | Value |
| --- | --- |
| `state` | Current `StreamState`. |
| `serve_started` | Whether `serve()` started successfully. |
| `viewer_url` | Local/player destination after serving. |
| `webrtc_play_url` | Local browser URL when WebRTC is enabled. |
| `lan_viewer_urls` | Discovered RTSP URLs when LAN mode is enabled. |
| `lan_webrtc_play_urls` | Discovered browser URLs for LAN WebRTC. |
| `reconnect_count` | Number of RTSP input reconnects. |
| `config` | Active `StreamConfig`. |

## Health snapshots

`status()` returns an immutable `StreamStatus` containing lifecycle state, reconnect information, URLs, background errors, frame timing, uptime, drop count, and child-process health.

```python
status = stream.status()
if status.has_publish_error:
    raise RuntimeError(status.publish_error)
```

## Exceptions

All library-specific exceptions inherit from `EasyRtspError`:

- `ConfigurationError`
- `DependencyError`
- `ProcessingError`
- `PublishError`
- `SourceError`
