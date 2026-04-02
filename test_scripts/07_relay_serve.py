"""Exercise: Stream.open (RTSP ingest) + serve — republish a remote RTSP stream."""

from __future__ import annotations

import argparse
import sys

from easy_rtsp import Stream


def main() -> None:
    p = argparse.ArgumentParser(description="Relay an RTSP URL to --serve.")
    p.add_argument("url", help="rtsp:// or rtsps:// source URL")
    p.add_argument("--serve", default="live", help="Publish path or full rtsp:// URL")
    p.add_argument(
        "--transport",
        choices=["tcp", "udp"],
        default="tcp",
        help="RTSP ingest transport (default: tcp)",
    )
    args = p.parse_args()

    print(f"Relay {args.url!r} -> {args.serve!r} (Ctrl+C to stop)...", file=sys.stderr)
    stream = Stream.open(args.url, transport=args.transport).serve(args.serve)
    print(f"Play: {stream.viewer_url}", flush=True)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()


if __name__ == "__main__":
    main()
