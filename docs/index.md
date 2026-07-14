---
hide:
  - navigation
  - toc
---

<div class="ertsp-hero" markdown>

# Video streams without the ceremony.

Ingest RTSP, webcams, files, or generated frames. Transform them in Python. Publish locally, across your LAN, or to an existing RTSP/SRT server.

<div class="ertsp-actions" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[Edge CV integrations](integrations/index.md){ .md-button }
[View on GitHub](https://github.com/austinconnor/easy-rtsp){ .md-button }
</div>

</div>

```python
from easy_rtsp import Stream

stream = Stream.from_webcam(0, lan_access=True).serve("live")
print(stream.lan_viewer_urls)
stream.wait()
```

<div class="ertsp-grid" markdown>

<div class="ertsp-card" markdown>
### Start anywhere
Open an RTSP camera, webcam, video file, or your own NumPy frame generator.
</div>

<div class="ertsp-card" markdown>
### Transform in Python
Chain frame callbacks with `map()`. Return a BGR `uint8` frame or `None` to drop it.
</div>

<div class="ertsp-card" markdown>
### Publish everywhere
Serve RTSP locally, expose it explicitly to your LAN, relay to another server, or publish SRT.
</div>

<div class="ertsp-card" markdown>
### Connect edge CV
Hand streams to GStreamer or DeepStream, or call Triton from a Python frame processor.
</div>

</div>

## Pick a path

=== "CLI"

    ```console
    easy-rtsp webcam 0 --serve live --lan
    ```

=== "Python"

    ```python
    from easy_rtsp import Stream

    Stream.from_file("clip.mp4").serve("live").wait()
    ```

=== "Relay"

    ```console
    easy-rtsp relay rtsp://camera/live --serve live
    ```

## What easy-rtsp handles

- FFmpeg command construction, process lifecycle, error tails, and cleanup.
- MediaMTX startup for proper local RTSP and optional WebRTC playback.
- Reconnect behavior for unstable RTSP inputs.
- Local recording and HLS side outputs.
- Cross-platform paths, URL escaping, IPv6 formatting, and Ctrl+C handling.

!!! info "Designed to stay small"
    NumPy is the only required Python runtime dependency. FFmpeg performs the media work, while MediaMTX is optional unless you want a proper local or LAN RTSP server.
