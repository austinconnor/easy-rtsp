# Roadmap

## Shipped in v0.1.x

- Snapshot API (`latest_frame()`, `save_snapshot()`) aligned with transformed output.
- Health and status API (`status()`) with reconnect, frame timing, and publish error details.
- Authenticated URL helpers (`build_rtsp_url`, `serve_rtsp`) with credential redaction in logs and errors.
- Async wrappers for blocking lifecycle calls.
- `audio_mode="passthrough"` for untransformed RTSP relay.
- Checksum-verified `install-backends`, typed codebase (mypy), and lifecycle tests.

## v0.2.0

Focus: broader audio-aware publishing.

- Build on the scoped relay-audio path shipped in v0.1.x.
- Extend beyond relay passthrough only where the pipeline can support it honestly.

- Proposed API shape
  - Keep `audio_mode` on `StreamConfig` (`off` by default, `passthrough` opt-in) and extend it only where supported.
  - Raise a clear configuration error when audio is requested for sources that do not support it yet.

- Files likely to change
  - `src/easy_rtsp/config.py`
  - `src/easy_rtsp/stream.py`
  - `src/easy_rtsp/publish.py`
  - `src/easy_rtsp/sources/rtsp.py`
  - `src/easy_rtsp/cli.py`
  - publish/relay-focused tests

- Main constraint
  - The current architecture decodes video to NumPy and republishes rawvideo through FFmpeg. That path has no audio channel.
  - The first audio feature therefore needs a relay-specific publish path that keeps FFmpeg in charge of copying or transcoding audio from the original RTSP source while still using the existing video pipeline.
  - This is a different path from webcam/file/frame-generator publishing and should stay explicitly scoped.

- Risks
  - A/V sync and mux timing when transformed video is paired with source audio.
  - Source streams with unsupported or unstable audio codecs.
  - Confusion if audio appears to be available for some source types but not others.

- Recommended implementation sequence
  - Phase 1: broaden the relay audio path and codec handling.
  - Phase 2: evaluate support for additional source types without hiding limitations.
  - Phase 3: add docs and matrix tests for audio-supported versus audio-unsupported source types.

## Later

- ONVIF / discovery helpers
- Built-in overlay helpers
- Multiple outputs per source
- Small web demo or monitoring surface
