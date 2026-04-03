<p align="center">
  <img src="assets/banner.png" alt="easy-rtsp banner" width="800" />
</p>

# easy-rtsp

Python library for ingesting video, transforming frames with NumPy/OpenCV, and republishing over **RTSP**, **RTSPS**, or **SRT** using FFmpeg, with optional **MediaMTX** for a proper RTSP server and **WebRTC** browser playback.

**Status:** early development. See `ROADMAP.md` for scope and roadmap.

## Install

```bash
pip install easy-rtsp
```

For **webcam** capture, add the OpenCV extra:

```bash
pip install "easy-rtsp[webcam]"
```

Development from a clone:

```bash
uv sync --extra dev
```

## Quick usage (Python API)

```python
from easy_rtsp import Stream

# Ingest RTSP
for frame in Stream.open("rtsp://camera/live").frames():
    ...

# Ingest RTSP from connection parts
relay = Stream.open_rtsp(
    "camera.local",
    "cam/main",
    username="user",
    password="secret",
)

# Webcam -> transform -> publish
Stream.from_webcam(0).map(process_frame).serve("live")

# File with options
Stream.from_file("clip.mp4", file_loop=True).serve("live")

# RTSP relay with audio passthrough
relay.serve_rtsp("127.0.0.1", "live", audio_mode="passthrough")

# Wait for shutdown
stream = Stream.from_webcam(0).serve("live")
print(stream.viewer_url)
print(stream.status())
stream.wait()
```

## CLI

Commands:

- `relay` - ingest RTSP/RTSPS and republish
- `webcam` - capture from webcam index (default `0`)
- `file` - publish from a file source
- `doctor` - print FFmpeg, ffprobe, MediaMTX, and platform status
- `install-backends` - show FFmpeg hints and optionally download MediaMTX

Examples:

```bash
easy-rtsp relay rtsp://camera/live --serve live
easy-rtsp webcam 0 --serve live --webrtc
easy-rtsp file input.mp4 --serve demo
easy-rtsp file clip.mp4 --serve live --fps 24 --no-loop
easy-rtsp relay rtsp://cam/live --serve live --record out.mp4 --hls-dir ./hls
easy-rtsp doctor
easy-rtsp install-backends
```

Shared `--serve` flags include endpoint, transport (relay), reconnect options, `--server-host` / `--server-port`, `--low-latency-input`, `--record`, `--hls-dir`, `--hls-segment-time`, `--video-encoder`, `--audio-mode`, `--webrtc` / `--no-webrtc`, `--webrtc-port`, and `-v`.

Logs go to **stderr**. `Play:` and `WebRTC:` URLs go to **stdout**. `SIGINT` is wired so `Ctrl+C` calls `stop()` reliably on Windows.

## Dependencies

| Component | Role |
|-----------|------|
| **FFmpeg** / **ffprobe** | Required on `PATH` for decode, encode, and publish. |
| **MediaMTX** | Optional. Without it, loopback publish uses **MPEG-TS over TCP** (`tcp://127.0.0.1:PORT` in VLC), not `rtsp://`. |
| **OpenCV** | Optional extra `webcam`: `opencv-python-headless` for `Stream.from_webcam` only. |

Download help:

```bash
easy-rtsp install-backends
```

Set `EASY_RTSP_MEDIAMTX` to the `mediamtx` executable or add it to `PATH` after install.

## Features

### Ingest sources

- **`Stream.open(url)`** - RTSP or RTSPS URL with reconnect and backoff.
- **`Stream.open_rtsp(host, path=..., username=..., password=...)`** - helper that builds a safe RTSP/RTSPS URL.
- **`Stream.from_webcam(index)`** - camera via OpenCV.
- **`Stream.from_file(path)`** - file decode; looping uses FFmpeg `-stream_loop`.
- **`Stream.from_frames(factory, fps, size)`** - synthetic or custom frame iterators (BGR `uint8`).

### Frame processing

- **`stream.map(fn)`** - per-frame transform; return `None` to drop a frame. Chaining is supported.

### Publishing (`serve`)

- **Shorthand path** - `"live"` maps to `rtsp://127.0.0.1:8554/live` using `StreamConfig.server_host` / `server_port`.
- **Full URLs** - `rtsp://`, `rtsps://`, and `srt://`.
- **`audio_mode="passthrough"`** - relay source audio for RTSP ingest when using `Stream.open(...)` / `Stream.open_rtsp(...)` without frame transforms.
- **Local MediaMTX** - easy-rtsp writes a minimal config and starts MediaMTX when possible.
- **No MediaMTX** - FFmpeg listens for one MPEG-TS client over TCP.
- **Existing server** - FFmpeg pushes RTSP in client mode when something is already listening.

### Side outputs

- **`record_path`** - duplicate stream to MP4.
- **`hls_output_dir`** - HLS output with `index.m3u8` and segments.
- **`hls_segment_time`** - optional HLS segment duration.

### Encoder / quality

- **`codec`** / **`video_encoder`** - choose H.264 encoder, including hardware encoders.
- **`preset`** - `default`, `low_latency`, or `quality`.
- **`bitrate`** - for example `"4M"`.
- **`input_realtime_pace`** - FFmpeg `-re` pacing for raw sources.

### RTSP ingest (relay)

- **`transport`** - `tcp` or `udp`.
- **`reconnect`**, **`retry_interval_sec`**, **`max_reconnect_attempts`** - reconnect policy.
- **`on_reconnecting`** - optional callback `(attempt_number)`.
- **`latency_ms`** - optional ingest hint.

### WebRTC (optional, MediaMTX + loopback)

- **`webrtc_enabled`** - off by default.
- **`webrtc_http_port`** - signaling port, default `8889`.
- Use the machine's LAN IP instead of `127.0.0.1` when testing from another device on the same network.

### File-specific

- **`file_loop`** - loop file continuously, default `true`.
- **`fps`** - override publish FPS.

### Control flow

- **`serve()`** - starts publish in a background thread.
- **`serve_rtsp(host, path=..., username=..., password=...)`** - convenience wrapper for authenticated RTSP/RTSPS publish URLs.
- **`wait()`** / **`wait(timeout=...)`** - block until publish ends.
- **`stop()`** - stop encode/decode FFmpeg children and MediaMTX if started.
- **`wait_async()`** / **`stop_async()`** - async wrappers for service environments.
- **`latest_frame()`** - read the latest processed frame.
- **`save_snapshot(path)`** - write the latest processed frame to an image file.
- **`status()`** - get an immutable health snapshot with state, reconnect count, URLs, and error state.
- **Context manager** - `with stream:` calls `stop()` on exit.
- **`Stream.state`**, **`reconnect_count`**, **`viewer_url`**, **`webrtc_play_url`**.

## Releases

Releases use Git tags plus GitHub Actions:

- Run the **Cut Release** workflow with a version like `0.2.0`, or push a tag manually with `git tag -a v0.2.0 -m "Release v0.2.0" && git push origin v0.2.0`.
- The **Release** workflow tests the repo, builds `sdist` and wheel, and publishes to PyPI.
- Publishing uses PyPI Trusted Publishing, so configure a trusted publisher for this repository, workflow, and environment in PyPI before the first release.
- If this repository does not have a historical release tag yet, create a baseline tag such as `v0.1.0` before relying on tag-derived versions for future releases.

## Third-party software

easy-rtsp only ships **Python** code under the license below. At runtime it invokes tools you install yourself; those are separate projects:

| Component | Where to get it | License (summary) |
|-----------|-----------------|-------------------|
| **FFmpeg** / **ffprobe** | [ffmpeg.org](https://ffmpeg.org/download.html), [FFmpeg legal](https://ffmpeg.org/legal.html) | Not MIT - typically **LGPL 2.1+** or **GPL** depending on build and enabled codecs; see upstream and your binary's `LICENSE` / docs. |
| **MediaMTX** (optional) | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) | **MIT** |
| **OpenCV** (Python bindings) | Optional `easy-rtsp[webcam]` -> `opencv-python-headless`; [opencv.org](https://opencv.org/) | **Apache 2.0** |

`easy-rtsp install-backends` may download a **MediaMTX** release from GitHub; it does not bundle FFmpeg. Use official FFmpeg builds or your OS package manager and keep their license terms alongside any binaries you redistribute.

## License

MIT
