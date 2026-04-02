# Manual API examples

Run from the **repository root** with `uv run python test_scripts/<script>.py`.

This folder is listed in `.gitignore` (entire directory). Remove the `test_scripts/` line from `.gitignore` if you want these examples in version control.

| Script | What it exercises |
|--------|-------------------|
| `01_iterate_synthetic_frames.py` | `Stream.from_frames`, `frames()` without publishing |
| `02_map_opencv_annotate.py` | `map()` with `cv2.rectangle`, `putText` |
| `03_map_numpy_transforms.py` | `map()` with NumPy slice / channel ops (no OpenCV in callback) |
| `04_map_chained_drop.py` | Chained `map().map()`, dropping frames with `None` |
| `05_webcam_serve.py` | `from_webcam`, `serve`, `wait` / Ctrl+C (needs a camera) |
| `06_file_serve.py` | `from_file`, `serve` (needs a video file path) |
| `07_relay_serve.py` | `open` RTSP ingest, `serve` (needs a reachable RTSP URL) |
| `08_serve_full_rtsp_url.py` | Shorthand path vs full `rtsp://` endpoint |
| `09_config_and_stream_state.py` | `StreamConfig` fields, `state`, `config`, `viewer_url` |
| `10_context_manager.py` | `with Stream(...) as s` and cleanup |
| `11_synthetic_publish_timed.py` | `from_frames` + `map` + `serve` + auto-stop (needs FFmpeg; MediaMTX optional) |

Automated coverage for `map`, OpenCV-style drawing, chained maps, frame drops, and API edge cases lives in `tests/test_stream_map_and_api.py`.
