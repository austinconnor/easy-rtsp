# Changelog

All notable changes to this project are documented here. Earlier releases are summarized in the
[GitHub release notes](https://github.com/austinconnor/easy-rtsp/releases).

## 0.1.6

### Breaking

- CLI: relay-only flags (`--transport`, `--retry-interval`, `--max-reconnect-attempts`,
  `--no-reconnect`, `--audio-mode`) are now accepted only by `easy-rtsp relay`. `webcam` and `file`
  used to accept and silently ignore them; they now exit with a usage error.

### Added

- `easy-rtsp doctor` reports the easy-rtsp, FFmpeg, ffprobe, and MediaMTX versions and exits
  non-zero when FFmpeg or ffprobe is missing.
- `install-backends` verifies the SHA-256 checksum of the downloaded MediaMTX archive and installs
  the binary atomically.
- Webcam publishing uses the frame rate reported by the camera driver when `fps` is not set
  (previously always 30).
- Public `FileSource.path`, `RtspSource.url`, and `WebcamSource.index` properties.
- Type checking with mypy and `ruff format` checks in CI.

### Fixed

- Several locally started streams can run at once with MediaMTX 1.19+. Its new MoQ server is now
  disabled, so it no longer claims extra ports or writes `auto.key` / `auto.crt` into the current
  directory.
- MediaMTX startup waits for the RTSP listener and reports MediaMTX's own output when it fails,
  instead of using a fixed delay. Its temporary config file is always removed.
- A failure partway through `serve()` (for example, a bad recording path) now stops the MediaMTX
  process that had already started, instead of leaving it running.
- `serve()` with an `rtsps://` destination and no existing server fails fast instead of starting an
  unencrypted server.
- `--lan` with an existing server on the port publishes to it rather than failing the port check.
- `stop()` gives the publisher a grace period to finalize MP4 recordings before terminating
  processes, and it is safe to call from inside a `map()` transform.
- Ctrl+C during CLI startup exits with code 130 instead of printing a traceback.
- Decoder failures (for example, a corrupt file) are reported reliably. FFmpeg used to be
  terminated as soon as its output ended, often before its exit status showed the error.
- `save_snapshot()` writes to paths that contain non-ASCII characters on Windows.
- Lower per-frame overhead in the decode and publish loops (one fewer copy per frame).
- Credentials are redacted from all CLI error messages.
