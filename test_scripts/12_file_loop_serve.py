"""
Exercise: Stream.from_file with looping (FFmpeg -stream_loop) + serve.

Default is continuous loop; pass --no-loop for a single playthrough.

Requires FFmpeg on PATH. If MediaMTX is on PATH and the RTSP port is free, you get rtsp://...
Otherwise MPEG-TS over tcp:// (see stderr warning).

Run:
  uv run python test_scripts/12_file_loop_serve.py path/to/video.mp4
  uv run python test_scripts/12_file_loop_serve.py path/to/video.mp4 --serve live --webrtc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from easy_rtsp import Stream


def main() -> None:
    p = argparse.ArgumentParser(description="Loop a video file and publish to RTSP.")
    p.add_argument("path", type=Path, help="Video file path")
    p.add_argument("--serve", default="live", help="Publish path or full rtsp:// URL")
    p.add_argument(
        "--no-loop",
        action="store_true",
        help="Play the file once then stop (default: loop forever)",
    )
    p.add_argument(
        "--no-realtime",
        action="store_true",
        help="Disable -re input pacing on the encoder (lower latency; can look jittery)",
    )
    p.add_argument(
        "--webrtc",
        action="store_true",
        help="Enable MediaMTX WebRTC in addition to RTSP (local MediaMTX only)",
    )
    args = p.parse_args()

    if not args.path.is_file():
        print(f"Not a file: {args.path}", file=sys.stderr)
        raise SystemExit(2)

    kwargs: dict = {}
    if args.no_realtime:
        kwargs["input_realtime_pace"] = False
    if args.no_loop:
        kwargs["file_loop"] = False
    if args.webrtc:
        kwargs["webrtc_enabled"] = True

    mode = "once" if args.no_loop else "loop"
    print(f"Publishing {args.path} ({mode}; Ctrl+C to stop)...", file=sys.stderr)
    stream = Stream.from_file(args.path, **kwargs).serve(args.serve)
    print(f"Play: {stream.viewer_url}", flush=True)
    w = getattr(stream, "webrtc_play_url", None)
    if w:
        print(f"WebRTC: {w}", flush=True)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()


if __name__ == "__main__":
    main()
