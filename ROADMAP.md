# Roadmap

## v0.1.2

Focus: observability and capture ergonomics.

- Snapshot API
  - Add access to the latest processed frame.
  - Add a convenience method for saving a snapshot to disk.
  - Keep snapshot behavior aligned with transformed output, not raw source frames.

- Health and status API
  - Add a public status object that reports stream state, serve state, reconnect count, viewer URLs, and publish error state.
  - Keep the first iteration intentionally small and stable so applications can build against it.

- Reliability follow-through
  - Extend tests around lifecycle transitions and state reporting.
  - Keep CI focused on lightweight, deterministic checks.

## v0.2.0

Focus: audio-aware publishing.

- Smallest shippable audio feature
  - RTSP relay audio passthrough only.
  - Support `Stream.open(...).serve(...)` carrying source audio when the upstream RTSP stream already has audio.
  - Keep `from_webcam`, `from_file`, and `from_frames` video-only until a later release.

- Proposed API shape
  - Add `audio_mode` to `StreamConfig` with values like `off` and `passthrough`.
  - Default to `off` in v0.1.x and `passthrough` opt-in for relay in v0.2.0.
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
  - Phase 1: add config, CLI flags, and validation for relay-only audio mode.
  - Phase 2: add a second FFmpeg publish path for RTSP relay with audio passthrough.
  - Phase 3: add docs and matrix tests for audio-supported versus audio-unsupported source types.

## Later

- ONVIF / discovery helpers
- Built-in overlay helpers
- Multiple outputs per source
- Small web demo or monitoring surface
