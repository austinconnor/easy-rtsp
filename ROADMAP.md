# Roadmap

## v0.1.2

Focus: observability, capture ergonomics, and scoped RTSP relay improvements.

- Snapshot API
  - Add access to the latest processed frame.
  - Add a convenience method for saving a snapshot to disk.
  - Keep snapshot behavior aligned with transformed output, not raw source frames.

- Health and status API
  - Add a public status object that reports stream state, serve state, reconnect count, viewer URLs, and publish error state.
  - Expand the first iteration with practical metrics like dropped frames, last-frame timing, publish uptime, child-process health, and reconnect reason.

- Auth/config ergonomics
  - Add helpers for building authenticated RTSP ingest and publish URLs safely.
  - Preserve the existing URL-first API for advanced use cases.

- Async-friendly wrappers
  - Add thin async wrappers around blocking lifecycle calls so services can integrate without blocking an event loop.

- Scoped audio support
  - Add `audio_mode="passthrough"` for RTSP relay when no frame transform is applied.
  - Keep unsupported combinations explicit rather than silently pretending audio works.

- Reliability follow-through
  - Extend tests around lifecycle transitions and state reporting.
  - Keep CI focused on lightweight, deterministic checks.

## v0.2.0

Focus: broader audio-aware publishing.

- Build on the scoped relay-audio path from v0.1.2.
- Extend beyond relay passthrough only where the pipeline can support it honestly.

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
  - Phase 1: broaden the relay audio path and codec handling.
  - Phase 2: evaluate support for additional source types without hiding limitations.
  - Phase 3: add docs and matrix tests for audio-supported versus audio-unsupported source types.

## Later

- ONVIF / discovery helpers
- Built-in overlay helpers
- Multiple outputs per source
- Small web demo or monitoring surface
