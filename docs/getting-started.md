# Installation

## Install the library

```console
pip install easy-rtsp
```

Webcam capture and snapshot encoding require the optional OpenCV extra:

```console
pip install "easy-rtsp[webcam]"
```

## Check the media tools

easy-rtsp orchestrates external media tools rather than bundling large binaries. Run:

```console
easy-rtsp doctor
```

You need FFmpeg and ffprobe for decoding and publishing. MediaMTX is required for a proper locally hosted RTSP stream and for LAN/WebRTC access.

```console
easy-rtsp install-backends
```

This command can download MediaMTX and prints platform-specific FFmpeg guidance. See [Dependencies](operations/dependencies.md) for environment-variable overrides.

## Publish your first stream

=== "Webcam"

    ```console
    easy-rtsp webcam 0 --serve live
    ```

=== "Video file"

    ```console
    easy-rtsp file clip.mp4 --serve live
    ```

=== "RTSP relay"

    ```console
    easy-rtsp relay rtsp://camera/live --serve live
    ```

With MediaMTX installed, the CLI prints:

```text
Play: rtsp://127.0.0.1:8554/live
```

Open that URL in VLC, ffplay, OBS, or another RTSP client. Press ++ctrl+c++ to stop the stream cleanly.

## Use the Python API

```python
from easy_rtsp import Stream

stream = Stream.from_file("clip.mp4").serve("live")
print(stream.viewer_url)

try:
    stream.wait()
finally:
    stream.stop()
```

`serve()` is non-blocking. Call `wait()`, keep your own application loop alive, or use the stream as a context manager.

## Develop from a clone

This project uses uv:

```console
uv sync --extra dev --group docs
uv run pytest
uv run ruff check src tests
uv run --group docs mkdocs serve
```

The documentation preview is available at `http://127.0.0.1:8000` while MkDocs is running.
