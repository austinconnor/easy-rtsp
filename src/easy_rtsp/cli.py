"""``easy-rtsp`` CLI (thin wrapper over the Python API)."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from easy_rtsp import __version__
from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import EasyRtspError
from easy_rtsp.install_backends import INSTALL_MEDIAMTX_CLI
from easy_rtsp.serve_url import redact_credentials_in_text, redact_url_credentials

if TYPE_CHECKING:
    from easy_rtsp.stream import Stream

# Conventional exit status when Ctrl+C aborts a command before streaming starts (128 + SIGINT).
_EXIT_INTERRUPTED = 130


def _print_play_urls(stream: Stream) -> None:
    """Print viewer URLs to stdout after ``serve()``; hints go to stderr."""
    viewer_url = stream.viewer_url
    if not viewer_url:
        return
    safe_viewer_url = redact_url_credentials(viewer_url)
    if viewer_url.startswith("tcp://"):
        print(f"Play (TCP/MPEG-TS): {safe_viewer_url}", flush=True)
    else:
        print(f"Play: {safe_viewer_url}", flush=True)
    if stream.webrtc_play_url:
        print(f"WebRTC: {stream.webrtc_play_url}", flush=True)
    for url in stream.lan_viewer_urls:
        print(f"LAN: {url}", flush=True)
    for url in stream.lan_webrtc_play_urls:
        print(f"LAN WebRTC: {url}", flush=True)

    if stream.lan_viewer_urls:
        port = urlparse(stream.lan_viewer_urls[0]).port or stream.config.server_port
        _hint(
            "LAN mode has no authentication; use it only on a trusted network. "
            f"Allow inbound TCP {port} in the host firewall if needed."
        )
        if stream.lan_webrtc_play_urls:
            _hint(
                "If WebRTC stays on loading: disable VPN for a test, try another browser, "
                f"and allow TCP {stream.config.webrtc_http_port} plus UDP/TCP "
                f"{stream.config.webrtc_ice_port} for MediaMTX."
            )


def _hint(message: str) -> None:
    print(f"  {message}", file=sys.stderr, flush=True)


def _wait_for_stream(stream: Stream) -> int:
    """Print playback details, block until publishing ends or Ctrl+C, and report failures."""
    _print_play_urls(stream)
    try:
        # Stream.wait() polls, so KeyboardInterrupt is delivered promptly even on Windows.
        stream.wait()
    except KeyboardInterrupt:
        # Ctrl+C is the normal way to end a stream, so it is not reported as a failure.
        print("easy-rtsp: stopping...", file=sys.stderr, flush=True)
    finally:
        stream.stop()

    status = stream.status()
    if status.has_publish_error:
        print(f"error: {status.publish_error}", file=sys.stderr, flush=True)
        return 1
    return 0


def _first_output_line(argv: list[str]) -> str | None:
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = (result.stdout or result.stderr).strip().splitlines()
    return lines[0].split(" Copyright")[0].strip() if lines else None


def cmd_install_backends(args: argparse.Namespace) -> int:
    """Download MediaMTX for this platform and print FFmpeg install hints."""
    from easy_rtsp.install_backends import run_install_backends

    prefix = Path(args.prefix).expanduser() if args.prefix else None
    out = run_install_backends(prefix=prefix, mediamtx=not args.skip_mediamtx, dry_run=args.dry_run)
    mediamtx = out.get("mediamtx")
    if mediamtx is None:
        return 0
    if args.dry_run:
        print(f"Would install MediaMTX to: {mediamtx}", flush=True)
        return 0
    print(f"Installed MediaMTX: {mediamtx}", flush=True)
    if prefix is not None:
        # Only the default location (~/.easy-rtsp/bin) is discovered automatically.
        print(f"Set EASY_RTSP_MEDIAMTX={mediamtx} or add its directory to PATH.", flush=True)
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Print environment diagnostics; exit non-zero when a required dependency is missing."""
    from easy_rtsp.backend import mediamtx_version
    from easy_rtsp.ffmpeg_util import resolve_ffmpeg, resolve_ffprobe, resolve_mediamtx

    print("easy-rtsp doctor")
    print(f"  easy-rtsp: {__version__}")
    print(f"  platform:  {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  python:    {sys.version.split()[0]}")

    ok = True
    for name, resolve in (("ffmpeg", resolve_ffmpeg), ("ffprobe", resolve_ffprobe)):
        try:
            path = resolve()
        except EasyRtspError as e:
            ok = False
            print(f"  {name + ':':<10} MISSING ({e})")
            continue
        version = _first_output_line([path, "-version"]) or "version unknown"
        print(f"  {name + ':':<10} {path} ({version})")

    try:
        mtx = resolve_mediamtx()
    except EasyRtspError as e:
        mtx = None
        print(f"  mediamtx:  MISCONFIGURED ({e})")
    else:
        if mtx:
            version_info = mediamtx_version(mtx)
            version = "v" + ".".join(map(str, version_info)) if version_info else "version unknown"
            print(f"  mediamtx:  {mtx} ({version})")
        else:
            print("  mediamtx:  not found (optional; needed for rtsp:// playback, LAN, and WebRTC)")
    if not mtx:
        print(f"  hint:      install MediaMTX with: {INSTALL_MEDIAMTX_CLI}", flush=True)

    return 0 if ok else 1


def _config_kwargs_from_args(args: argparse.Namespace) -> dict[str, Any]:
    """Map parsed CLI flags onto :class:`StreamConfig` fields; absent flags keep defaults."""
    options = vars(args)
    kwargs: dict[str, Any] = {
        "server_host": args.server_host,
        "server_port": args.server_port,
        "lan_access": args.lan,
        "webrtc_enabled": args.webrtc_enabled,
        "webrtc_http_port": args.webrtc_port,
        "webrtc_ice_port": args.webrtc_ice_port,
        "hls_segment_time": args.hls_segment_time,
        "hls_list_size": args.hls_list_size,
        "preset": args.preset,
    }
    optional = {
        "record": "record_path",
        "hls_dir": "hls_output_dir",
        "video_encoder": "video_encoder",
        "bitrate": "bitrate",
        "fps": "fps",
        # Relay-only flags.
        "transport": "transport",
        "latency_ms": "latency_ms",
        "retry_interval": "retry_interval_sec",
        "max_reconnect_attempts": "max_reconnect_attempts",
        "audio_mode": "audio_mode",
        # File-only flags.
        "file_loop": "file_loop",
    }
    for flag, field_name in optional.items():
        if options.get(flag) is not None:
            kwargs[field_name] = options[flag]
    if options.get("no_reconnect"):
        kwargs["reconnect"] = False
    if args.low_latency_input or options.get("no_realtime"):
        kwargs["input_realtime_pace"] = False
    return kwargs


def _announce(description: str, serve: str) -> None:
    print(
        f"easy-rtsp: {description} -> --serve {redact_url_credentials(serve)!r} (Ctrl+C to stop)",
        file=sys.stderr,
        flush=True,
    )


def cmd_relay(args: argparse.Namespace) -> int:
    """Ingest an RTSP URL and publish to ``--serve``."""
    from easy_rtsp import Stream

    _announce(f"relay {redact_url_credentials(args.url)!r}", args.serve)
    stream = Stream.open(args.url, **_config_kwargs_from_args(args)).serve(args.serve)
    return _wait_for_stream(stream)


def cmd_webcam(args: argparse.Namespace) -> int:
    """Capture a webcam and publish to ``--serve``."""
    from easy_rtsp import Stream

    _announce(f"webcam index {args.index}", args.serve)
    stream = Stream.from_webcam(args.index, **_config_kwargs_from_args(args)).serve(args.serve)
    return _wait_for_stream(stream)


def cmd_file(args: argparse.Namespace) -> int:
    """Decode a file and publish to ``--serve``."""
    from easy_rtsp import Stream

    path = Path(args.path).expanduser()
    if not path.is_file():
        print(f"error: not a file: {path}", file=sys.stderr)
        return 2
    _announce(f"file {path}", args.serve)
    stream = Stream.from_file(path, **_config_kwargs_from_args(args)).serve(args.serve)
    return _wait_for_stream(stream)


def _add_publish_arguments(p: argparse.ArgumentParser) -> None:
    """Flags shared by every publishing command."""
    p.add_argument(
        "--serve",
        default="live",
        metavar="ENDPOINT",
        help='Publish target: shorthand path, rtsp://, rtsps://, or srt:// URL (default: "live")',
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
        "--lan",
        action="store_true",
        help="Expose a locally started RTSP server to this network and print LAN playback URLs",
    )
    p.add_argument(
        "--webrtc",
        action=argparse.BooleanOptionalAction,
        default=StreamConfig.webrtc_enabled,
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
        "--webrtc-ice-port",
        type=int,
        default=StreamConfig.webrtc_ice_port,
        metavar="PORT",
        help="MediaMTX WebRTC UDP/TCP ICE port (default: %(default)s)",
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
        "--hls-list-size",
        type=int,
        default=StreamConfig.hls_list_size,
        metavar="N",
        help="HLS playlist segment count to retain (default: %(default)s; 0 keeps all)",
    )
    p.add_argument(
        "--fps",
        type=float,
        default=None,
        metavar="FPS",
        help="Publish frame rate override (default: probed from the source, else 30)",
    )
    p.add_argument(
        "--video-encoder",
        metavar="NAME",
        default=None,
        help="FFmpeg video encoder (e.g. h264_nvenc, h264_qsv); default is libx264 for H.264",
    )
    p.add_argument(
        "--bitrate",
        metavar="RATE",
        default=None,
        help='Optional video encoder bitrate (e.g. "4M")',
    )
    p.add_argument(
        "--preset",
        choices=["default", "low_latency", "quality"],
        default=StreamConfig.preset,
        help="Encoding quality/latency preset (default: %(default)s)",
    )
    p.add_argument(
        "--low-latency-input",
        action="store_true",
        help="Disable FFmpeg -re pacing on raw input (slightly lower latency; can look jittery)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log debug messages to stderr",
    )


def _add_rtsp_ingest_arguments(p: argparse.ArgumentParser) -> None:
    """Flags that only apply to RTSP input (``relay``)."""
    p.add_argument(
        "--transport",
        choices=["tcp", "udp"],
        default=StreamConfig.transport,
        help="RTSP ingest transport (default: %(default)s)",
    )
    p.add_argument(
        "--latency-ms",
        type=int,
        default=None,
        metavar="MS",
        help="Optional RTSP ingest latency hint in milliseconds",
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
        help="Max RTSP reconnects (default: unlimited)",
    )
    p.add_argument(
        "--no-reconnect",
        action="store_true",
        help="Disable RTSP reconnect",
    )
    p.add_argument(
        "--audio-mode",
        choices=["off", "passthrough"],
        default=StreamConfig.audio_mode,
        help="Audio publishing mode (default: %(default)s); passthrough copies source audio and video",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easy-rtsp",
        description="Ingest video and republish over RTSP (see also the Python API).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
        help="Install directory (default: ~/.easy-rtsp, which easy-rtsp finds automatically)",
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
    _add_publish_arguments(p_relay)
    _add_rtsp_ingest_arguments(p_relay)
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
    _add_publish_arguments(p_webcam)
    p_webcam.set_defaults(func=cmd_webcam)

    p_file = sub.add_parser(
        "file",
        help="Decode a video file and publish",
        description="Example: easy-rtsp file input.mp4 --serve demo",
    )
    p_file.add_argument("path", help="Path to a video file")
    p_file.add_argument(
        "--loop",
        action=argparse.BooleanOptionalAction,
        default=StreamConfig.file_loop,
        dest="file_loop",
        help="Loop the file when it ends (default: on)",
    )
    p_file.add_argument(
        "--no-realtime",
        action="store_true",
        help="Read the file as fast as possible (same as --low-latency-input)",
    )
    _add_publish_arguments(p_file)
    p_file.set_defaults(func=cmd_file)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from easy_rtsp.log import setup_cli_logging

    setup_cli_logging(getattr(args, "verbose", False))
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return _EXIT_INTERRUPTED
    except (EasyRtspError, OSError) as e:
        print(f"error: {redact_credentials_in_text(str(e))}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
