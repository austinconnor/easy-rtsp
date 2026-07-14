# Local publishing

The shortest endpoint is a path name:

```python
from easy_rtsp import Stream

stream = Stream.from_webcam(0).serve("live")
print(stream.viewer_url)
stream.wait()
```

`"live"` resolves to `rtsp://127.0.0.1:8554/live` by default.

## What starts behind the scenes

When the destination is loopback and the port is free:

1. easy-rtsp starts MediaMTX if it is installed.
2. FFmpeg publishes encoded H.264 to MediaMTX.
3. Players connect to the printed RTSP URL.

If MediaMTX is unavailable, easy-rtsp falls back to a single MPEG-TS listener and prints a `tcp://` URL instead. That fallback is useful for a quick VLC preview, but it is not an RTSP server and cannot power LAN mode, recording/HLS tee outputs, or WebRTC.

## Change the endpoint

```console
easy-rtsp webcam 0 --serve camera/front --server-port 9554
```

```python
stream = Stream.from_webcam(
    0,
    server_port=9554,
).serve("camera/front")
```

The resulting local URL is `rtsp://127.0.0.1:9554/camera/front`.

## Publish to an existing server

Pass a full destination URL:

```python
stream.serve("rtsp://media-server.local:8554/live")
```

For credentials, avoid manual string assembly:

```python
stream.serve_rtsp(
    "media-server.local",
    "live",
    port=8554,
    username="publisher",
    password="secret",
)
```

Credentials are safely percent-encoded and redacted from CLI diagnostics.
