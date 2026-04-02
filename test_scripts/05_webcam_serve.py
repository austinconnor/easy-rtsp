"""Exercise: Stream.from_webcam + serve (requires camera + FFmpeg; MediaMTX for rtsp://)."""

from __future__ import annotations

import argparse
import sys

from easy_rtsp import Stream


def main() -> None:
    p = argparse.ArgumentParser(description="Publish webcam to --serve endpoint.")
    p.add_argument("--index", type=int, default=0, help="OpenCV camera index (default: 0)")
    p.add_argument("--serve", default="live", help='Shorthand path or full rtsp:// URL (default: "live")')
    p.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Output FPS when not implied by source (default: 30)",
    )
    p.add_argument(
        "--preset",
        choices=["default", "low_latency", "quality"],
        default="default",
        help="Encoder preset",
    )
    args = p.parse_args()

    kwargs: dict = {"preset": args.preset}
    if args.fps is not None:
        kwargs["fps"] = args.fps

    print("Starting webcam publish (Ctrl+C to stop)...", file=sys.stderr)
    stream = Stream.from_webcam(args.index, **kwargs).serve(args.serve)
    print(f"Play: {stream.viewer_url}", flush=True)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()


if __name__ == "__main__":
    main()
