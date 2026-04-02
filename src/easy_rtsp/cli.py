"""``easy-rtsp`` CLI (thin wrapper over the Python API)."""

from __future__ import annotations

import argparse
import platform
import signal
import sys
from pathlib import Path
from typing import Any

from easy_rtsp.config import StreamConfig
from easy_rtsp.install_backends import INSTALL_MEDIAMTX_CLI


def _install_sigint_stop(stream: object):
    """
    Call :meth:`~easy_rtsp.stream.Stream.stop` on SIGINT so Ctrl+C works even when
    ``KeyboardInterrupt`` is not delivered (common on Windows consoles).

    Returns the previous SIGINT handler to restore in ``finally``, or ``None`` if unchanged.
    """
    if not hasattr(signal, "SIGINT"):
        return None

    def _handler(_signum: int, _frame: object) -> None:
        try:
            stream.stop()
        except Exception:
            pass

    return signal.signal(signal.SIGINT, _handler)


def _print_play_url(stream: object) -> None:
    """Print the viewer URL to stdout after ``serve()`` (RTSP or TCP fallback)."""
    viewer_url = getattr(stream, "viewer_url", None)
    if not viewer_url:
        return
    if str(viewer_url).startswith(("rtsp://", "rtsps://")):
        print(f"Play: {viewer_url}", flush=True)
    else:
        print(f"Play (TCP/MPEG-TS): {viewer_url}", flush=True)
    webrtc = getattr(stream, "webrtc_play_url", None)
    if webrtc:
        print(f"WebRTC: {webrtc}", flush=True)
        if "127.0.0.1" in webrtc or "localhost" in webrtc.lower():
            print(
                "  Open in a browser; on a phone use this machine's LAN IP instead of 127.0.0.1.",
                file=sys.stderr,
                flush=True,
            )
            print(
                "  If WebRTC stays on loading: disable VPN for a test, try another browser, "
                "and use MediaMTX 1.11.2+ (firewall: UDP/TCP 8189 for mediamtx).",
                file=sys.stderr,
                flush=True,
            )


def cmd_install_backends(args: argparse.Namespace) -> int:
    """Download MediaMTX for this platform and print FFmpeg install hints."""
    from easy_rtsp.install_backends import run_install_backends

    prefix = Path(args.prefix).expanduser() if args.prefix else None
    try:
        out = run_install_backends(prefix=prefix, mediamtx=not args.skip_mediamtx, dry_run=args.dry_run)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    m = out.get("mediamtx")
    if m and not args.dry_run:
        print(f"Installed MediaMTX: {m}", flush=True)
        print(f"Set EASY_RTSP_MEDIAMTX={m} or add its directory to PATH.", flush=True)
    elif args.dry_run and m:
        print(f"Would install MediaMTX to: {m}", flush=True)
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Print environment diagnostics (FFmpeg, MediaMTX, OS)."""
    from easy_rtsp.ffmpeg_util import resolve_ffmpeg, resolve_ffprobe, resolve_mediamtx

    print("easy-rtsp doctor")
    print(f"  platform: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  python:   {sys.version.split()[0]}")

    try:
        ff = resolve_ffmpeg()
        print(f"  ffmpeg:   {ff}")
    except Exception as e:
        print(f"  ffmpeg:   MISSING ({e})")

    try:
        fp = resolve_ffprobe()
        print(f"  ffprobe:  {fp}")
    except Exception as e:
        print(f"  ffprobe:  MISSING ({e})")

    mtx = resolve_mediamtx()
    print(f"  mediamtx: {mtx or 'not found on PATH (optional for local publish)'}")
    if not mtx:
        print(f"  warning:  install MediaMTX for rtsp:// and WebRTC: {INSTALL_MEDIAMTX_CLI}", flush=True)

    return 0


def _config_kwargs_from_args(args: argparse.Namespace) -> dict[str, Any]:
    d: dict[str, Any] = dict(
        transport=args.transport,
        reconnect=not args.no_reconnect,
        retry_interval_sec=args.retry_interval,
        max_reconnect_attempts=args.max_reconnect_attempts,
        server_host=args.server_host,
        server_port=args.server_port,
    )
    if getattr(args, "low_latency_input", False):
        d["input_realtime_pace"] = False
    if getattr(args, "record", None):
        d["record_path"] = args.record
    if getattr(args, "hls_dir", None):
        d["hls_output_dir"] = args.hls_dir
    if getattr(args, "hls_segment_time", None) is not None:
        d["hls_segment_time"] = float(args.hls_segment_time)
    if getattr(args, "video_encoder", None):
        d["video_encoder"] = args.video_encoder
    if getattr(args, "webrtc_enabled", None) is not None:
        d["webrtc_enabled"] = bool(args.webrtc_enabled)
    if getattr(args, "webrtc_port", None) is not None:
        d["webrtc_http_port"] = int(args.webrtc_port)
    if getattr(args, "fps", None) is not None:
        d["fps"] = float(args.fps)
    if getattr(args, "file_loop", None) is not None:
        d["file_loop"] = bool(args.file_loop)
    return d


def cmd_relay(args: argparse.Namespace) -> int:
    """Ingest an RTSP URL and publish to ``--serve``."""
    from easy_rtsp import Stream

    print(
        f"easy-rtsp: relay {args.url!r} -> --serve {args.serve!r} (Ctrl+C to stop)",
        file=sys.stderr,
        flush=True,
    )
    kwargs = _config_kwargs_from_args(args)
    stream = Stream.open(args.url, **kwargs).serve(args.serve)
    _print_play_url(stream)
    prev = _install_sigint_stop(stream)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()
    finally:
        if prev is not None:
            signal.signal(signal.SIGINT, prev)
    return 0


def cmd_webcam(args: argparse.Namespace) -> int:
    """Capture a webcam and publish to ``--serve``."""
    from easy_rtsp import Stream

    print(
        f"easy-rtsp: webcam index {args.index} -> --serve {args.serve!r} (Ctrl+C to stop)",
        file=sys.stderr,
        flush=True,
    )
    kwargs = _config_kwargs_from_args(args)
    stream = Stream.from_webcam(args.index, **kwargs).serve(args.serve)
    _print_play_url(stream)
    prev = _install_sigint_stop(stream)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()
    finally:
        if prev is not None:
            signal.signal(signal.SIGINT, prev)
    return 0


def cmd_file(args: argparse.Namespace) -> int:
    """Decode a file and publish to ``--serve``."""
    from easy_rtsp import Stream

    kwargs = _config_kwargs_from_args(args)
    if getattr(args, "no_realtime", False):
        kwargs["input_realtime_pace"] = False
    path = Path(args.path)
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    print(
        f"easy-rtsp: file {path} -> --serve {args.serve!r} (Ctrl+C to stop)",
        file=sys.stderr,
        flush=True,
    )
    stream = Stream.from_file(path, **kwargs).serve(args.serve)
    _print_play_url(stream)
    prev = _install_sigint_stop(stream)
    try:
        stream.wait()
    except KeyboardInterrupt:
        stream.stop()
    finally:
        if prev is not None:
            signal.signal(signal.SIGINT, prev)
    return 0


def _add_serve_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--serve",
        default="live",
        metavar="ENDPOINT",
        help='Publish target: shorthand path, rtsp://, rtsps://, or srt:// URL (default: "live")',
    )
    p.add_argument(
        "--transport",
        choices=["tcp", "udp"],
        default="tcp",
        help="RTSP ingest transport (relay only; default: tcp)",
    )
    p.add_argument(
        "--retry-interval",
        type=float,
        default=StreamConfig.retry_interval_sec,
        metavar="SEC",
        help="Seconds between RTSP reconnect attempts (default: %(default)s)",
    )
    p.add_argument(
        "--max-reconnect-attempts",
        type=int,
        default=None,
        metavar="N",
        help="Max RTSP reconnects (default: unlimited; use 0 to disable reconnect)",
    )
    p.add_argument(
        "--no-reconnect",
        action="store_true",
        help="Disable RTSP reconnect (relay)",
    )
    p.add_argument(
        "--server-host",
        default=StreamConfig.server_host,
        metavar="HOST",
        help="Host for shorthand serve URL (default: %(default)s)",
    )
    p.add_argument(
        "--server-port",
        type=int,
        default=StreamConfig.server_port,
        metavar="PORT",
        help="Port for shorthand serve URL (default: %(default)s)",
    )
    p.add_argument(
        "--low-latency-input",
        action="store_true",
        help="Disable FFmpeg -re pacing on raw input (slightly lower latency; can look jittery)",
    )
    p.add_argument(
        "--record",
        metavar="PATH",
        default=None,
        help="Also write MP4 to PATH (FFmpeg tee; RTSP push only)",
    )
    p.add_argument(
        "--hls-dir",
        metavar="DIR",
        default=None,
        help="Also write HLS (index.m3u8 + segments) under DIR (RTSP push only)",
    )
    p.add_argument(
        "--hls-segment-time",
        type=float,
        default=StreamConfig.hls_segment_time,
        metavar="SEC",
        help="HLS segment duration (default: %(default)s)",
    )
    p.add_argument(
        "--video-encoder",
        metavar="NAME",
        default=None,
        help="FFmpeg video encoder (e.g. h264_nvenc, h264_qsv); default is libx264 for H.264",
    )
    p.add_argument(
        "--webrtc",
        action=argparse.BooleanOptionalAction,
        default=False,
        dest="webrtc_enabled",
        help="Enable MediaMTX WebRTC when starting local MediaMTX (default: off; RTSP only)",
    )
    p.add_argument(
        "--webrtc-port",
        type=int,
        default=StreamConfig.webrtc_http_port,
        metavar="PORT",
        help="MediaMTX WebRTC HTTP port (default: %(default)s)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log easy_rtsp messages to stderr",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easy-rtsp",
        description="Ingest video and republish over RTSP (see also the Python API).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_doc = sub.add_parser("doctor", help="Show FFmpeg/MediaMTX availability and platform info")
    p_doc.set_defaults(func=cmd_doctor)

    p_install = sub.add_parser(
        "install-backends",
        help="Print FFmpeg install hints and optionally download MediaMTX",
        description=(
            "FFmpeg is never bundled; MediaMTX can be downloaded from GitHub releases "
            "into --prefix/bin."
        ),
    )
    p_install.add_argument(
        "--prefix",
        type=str,
        default=None,
        metavar="DIR",
        help="Install directory (default: ~/.easy-rtsp)",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Show where MediaMTX would be installed without downloading",
    )
    p_install.add_argument(
        "--skip-mediamtx",
        action="store_true",
        help="Only print FFmpeg hints; do not download MediaMTX",
    )
    p_install.set_defaults(func=cmd_install_backends)

    p_relay = sub.add_parser(
        "relay",
        help="Ingest an RTSP stream and republish",
        description="Example: easy-rtsp relay rtsp://camera/live --serve live",
    )
    p_relay.add_argument("url", help="RTSP or RTSPS URL")
    _add_serve_arguments(p_relay)
    p_relay.set_defaults(func=cmd_relay)

    p_webcam = sub.add_parser(
        "webcam",
        help="Capture from a webcam index and publish",
        description="Example: easy-rtsp webcam 0 --serve live",
    )
    p_webcam.add_argument(
        "index",
        type=int,
        nargs="?",
        default=0,
        help="Camera device index (default: 0)",
    )
    _add_serve_arguments(p_webcam)
    p_webcam.set_defaults(func=cmd_webcam)

    p_file = sub.add_parser(
        "file",
        help="Decode a video file and publish",
        description="Example: easy-rtsp file input.mp4 --serve demo",
    )
    p_file.add_argument("path", help="Path to a video file")
    p_file.add_argument(
        "--fps",
        type=float,
        default=None,
        metavar="FPS",
        help="Publish frame rate (default: from file metadata via ffprobe, else 30)",
    )
    p_file.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="file_loop",
        help="Loop the file when it ends (default: on)",
    )
    p_file.add_argument(
        "--no-realtime",
        action="store_true",
        help="Read the file as fast as possible (no -re); default paces like live for smoother publish",
    )
    _add_serve_arguments(p_file)
    p_file.set_defaults(func=cmd_file)

    args = parser.parse_args(argv)
    from easy_rtsp.log import setup_cli_logging

    setup_cli_logging(getattr(args, "verbose", False))
    code = args.func(args)
    return int(code) if code is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
