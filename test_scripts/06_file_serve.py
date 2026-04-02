"""Exercise: Stream.from_file + serve (needs a video file + FFmpeg; MediaMTX optional)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from easy_rtsp import Stream


def main() -> None:
    p = argparse.ArgumentParser(description="Decode a file and publish to RTSP.")
    p.add_argument("path", type=Path, help="Video file path")
    p.add_argument("--serve", default="demo", help="Publish path or full rtsp:// URL")
    p.add_argument(
        "--no-realtime",
        action="store_true",
        help="Disable -re input pacing (decode as fast as possible)",
    )
    args = p.parse_args()

    if not args.path.is_file():
        print(f"Not a file: {args.path}", file=sys.stderr)
        raise SystemExit(2)

    kwargs: dict = {}
    if args.no_realtime:
        kwargs["input_realtime_pace"] = False

    print(f"Publishing {args.path} (Ctrl+C to stop)...", file=sys.stderr)
    stream = Stream.from_file(args.path, **kwargs).serve(args.serve)
    print(f"Play: {stream.viewer_url}", flush=True)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()


if __name__ == "__main__":
    main()
