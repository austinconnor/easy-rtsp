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

For **webcam** capture, add the OpenCV extra (large wheel; skipped by default so installs stay quick):

```bash
pip install "easy-rtsp[webcam]"
```

Development from a clone: `uv sync --extra dev` (includes OpenCV for tests).

## Releases

Releases use Git tags plus GitHub Actions:

- Run the **Cut Release** workflow with a version like `0.2.0`, or push a tag manually with `git tag -a v0.2.0 -m "Release v0.2.0" && git push origin v0.2.0`.
- The **Release** workflow tests the repo, builds `sdist` and wheel, and publishes to PyPI.
- Publishing uses PyPI Trusted Publishing, so configure a trusted publisher for this repository/workflow/environment in PyPI before the first release.
- If this repository does not have a historical release tag yet, create a baseline tag such as `v0.1.0` before relying on tag-derived versions for future releases.

### Dependencies

| Component | Role |
|-----------|------|
| **FFmpeg** / **ffprobe** | Required on `PATH` for decode/encode/publish. |
| **MediaMTX** | Optional. Without it, loopback publish uses **MPEG-TS over TCP** (`tcp://127.0.0.1:PORT` in VLC), not `rtsp://`. |
| **OpenCV** | Optional extra `webcam`: `opencv-python-headless` for `Stream.from_webcam` only. |

Download help (FFmpeg hints + optional MediaMTX binary for your OS):

```bash
easy-rtsp install-backends
```

Set `EASY_RTSP_MEDIAMTX` to the `mediamtx` executable or add it to `PATH` after install.

---

## Features

### Ingest sources

- **`Stream.open(url)`** — RTSP or RTSPS URL (FFmpeg decode; reconnect with backoff).
- **`Stream.from_webcam(index)`** — Camera via OpenCV.
- **`Stream.from_file(path)`** — File decode; **looping** uses FFmpeg `-stream_loop` (continuous by default).
- **`Stream.from_frames(factory, fps, size)`** — Synthetic or custom frame iterators (BGR `uint8`).

### Frame processing

- **`stream.map(fn)`** — Per-frame transform; return **`None`** to drop a frame. Chaining supported.

### Publishing (`serve`)

- **Shorthand path** — e.g. `"live"` → `rtsp://127.0.0.1:8554/live` (host/port from `StreamConfig.server_host` / `server_port`).
- **Full URLs** — `rtsp://`, `rtsps://` (credentials preserved), **`srt://`** (MPEG-TS over SRT; no local MediaMTX RTSP process).
- **Local MediaMTX** — If `mediamtx` is on `PATH` and the RTSP port on loopback is free, easy-rtsp writes a minimal config and starts MediaMTX.
- **No MediaMTX** — FFmpeg listens for **one** MPEG-TS client over TCP (VLC: open `tcp://…`).
- **Existing server** — If something already listens on the port, FFmpeg **pushes** RTSP in client mode.

### Side outputs (RTSP push only)

- **`record_path`** — Duplicate stream to **MP4** (FFmpeg `tee`).
- **`hls_output_dir`** — **HLS** (`index.m3u8` + segments); optional **`hls_segment_time`**.

### Encoder / quality

- **H.264** via **`codec`** / default **`libx264`**; override with **`video_encoder`** (e.g. `h264_nvenc`, `h264_qsv`, `h264_amf`).
- **`preset`** — `default`, `low_latency`, `quality`.
- **`bitrate`** — e.g. `"4M"`.
- **`input_realtime_pace`** — FFmpeg `-re` pacing for raw sources (default on for smoother pacing; off for lower latency).

### RTSP ingest (relay)

- **`transport`** — `tcp` or `udp`.
- **`reconnect`**, **`retry_interval_sec`**, **`max_reconnect_attempts`** — Reconnect policy.
- **`on_reconnecting`** — Optional callback `(attempt_number)`.
- **`latency_ms`** — Optional ingest hint.

### WebRTC (optional, MediaMTX + loopback)

- **`webrtc_enabled`** — Off by default. Enables MediaMTX’s HTTP/WebRTC listener (video only, no audio).
- **`webrtc_http_port`** — Signaling port (default **8889**); browser URL is **`Stream.webrtc_play_url`** or CLI **`WebRTC: http://…`**.
- For phones on the same LAN, use the machine’s **LAN IP** instead of `127.0.0.1`. If the page stays on “loading”, try disabling VPN, another browser, firewall **UDP/TCP 8189**, and MediaMTX **1.11.2+**.

### File-specific

- **`file_loop`** — Loop file continuously (default **true**); **`false`** for a single playthrough.
- **`fps`** — Override publish FPS (default from ffprobe, else 30).

### Control flow

- **`serve()`** — Starts publish in a background thread (non-blocking).
- **`wait()`** / **`wait(timeout=…)`** — Block until publish ends (polling-friendly for **Ctrl+C** on Windows).
- **`stop()`** — Stops encode/decode FFmpeg children and MediaMTX if started.
- **`latest_frame()`** — Read the latest processed frame for snapshots, previews, or monitoring.
- **`save_snapshot(path)`** — Write the latest processed frame to an image file.
- **`status()`** — Get an immutable health snapshot with state, reconnect count, URLs, and error state.
- **Context manager** — `with stream:` calls **`stop()`** on exit.
- **`Stream.state`**, **`reconnect_count`** (RTSP), **`viewer_url`**, **`webrtc_play_url`**.

### CLI

- **`relay`** — Ingest RTSP/RTSPS, republish.
- **`webcam`** — Webcam index (default `0`).
- **`file`** — File path; **`--loop` / `--no-loop`**, **`--fps`**, **`--no-realtime`**.
- **`doctor`** — FFmpeg, ffprobe, MediaMTX, platform.
- **`install-backends`** — FFmpeg hints; optional MediaMTX download (`--prefix`, `--dry-run`, `--skip-mediamtx`).

Shared **`--serve`** flags: endpoint, transport (relay), reconnect options, **`--server-host`** / **`--server-port`**, **`--low-latency-input`**, **`--record`**, **`--hls-dir`**, **`--hls-segment-time`**, **`--video-encoder`**, **`--webrtc`** / **`--no-webrtc`**, **`--webrtc-port`**, **`-v`**.

Logs go to **stderr**; **`Play:`** / **`WebRTC:`** URLs to **stdout**. **SIGINT** is wired so **Ctrl+C** calls **`stop()`** reliably on Windows.

---

## Quick usage (Python API)

```python
from easy_rtsp import Stream

# Ingest RTSP
for frame in Stream.open("rtsp://camera/live").frames():
    ...

# Webcam → transform → publish
Stream.from_webcam(0).map(process_frame).serve("live")

# File with options (see StreamConfig)
Stream.from_file("clip.mp4", file_loop=True).serve("live")

# Wait for shutdown
stream = Stream.from_webcam(0).serve("live")
print(stream.viewer_url)
print(stream.status())
stream.wait()
```

---

## CLI examples

```bash
easy-rtsp relay rtsp://camera/live --serve live
easy-rtsp webcam 0 --serve live --webrtc
easy-rtsp file input.mp4 --serve demo
easy-rtsp file clip.mp4 --serve live --fps 24 --no-loop
easy-rtsp relay rtsp://cam/live --serve live --record out.mp4 --hls-dir ./hls
easy-rtsp doctor
easy-rtsp install-backends
```

**Without MediaMTX**, use **`tcp://127.0.0.1:PORT`** in VLC (MPEG-TS), not `rtsp://…`, unless you install MediaMTX.

---

## License

MIT

## Third-party software

easy-rtsp only ships **Python** code under the license above. At runtime it invokes tools you install yourself; those are separate projects:

| Component | Where to get it | License (summary) |
|-----------|-----------------|-------------------|
| **FFmpeg** / **ffprobe** | [ffmpeg.org](https://ffmpeg.org/download.html), [FFmpeg legal](https://ffmpeg.org/legal.html) | Not MIT — typically **LGPL 2.1+** or **GPL** depending on build and enabled codecs; see upstream and your binary’s `LICENSE` / docs. |
| **MediaMTX** (optional) | [bluenviron/mediamtx](https://github.com/bluenviron/mediamtx) | **MIT** |
| **OpenCV** (Python bindings) | Optional `easy-rtsp[webcam]` → `opencv-python-headless`; [opencv.org](https://opencv.org/) | **Apache 2.0** (see the wheel / PyPI page for the exact package license). |

`easy-rtsp install-backends` may download a **MediaMTX** release from GitHub; it does **not** bundle FFmpeg — use official FFmpeg builds or your OS package manager and keep their license terms alongside any binaries you redistribute.
