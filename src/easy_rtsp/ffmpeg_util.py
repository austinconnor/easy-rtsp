"""FFmpeg / ffprobe discovery and helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.install_backends import default_install_prefix
from easy_rtsp.serve_url import redact_credentials_in_text, redact_url_credentials

_PROBE_TIMEOUT_SEC = 15.0
_MIN_SANE_FPS = 0.1
_MAX_SANE_FPS = 240.0


def _which(name: str) -> str | None:
    return shutil.which(name)


def _resolve_executable(name: str, env_var: str, *, required: bool) -> str | None:
    override = os.environ.get(env_var)
    if override:
        path = _which(os.path.expanduser(override))
        if path:
            return path
        raise DependencyError(
            f"{env_var} is set to {override!r}, but that executable could not be found or run."
        )
    path = _which(name)
    if path or not required:
        return path
    raise DependencyError(
        f"{name} not found on PATH. Install FFmpeg and ensure it is available, "
        f"or set {env_var} to the executable path."
    )


def resolve_ffmpeg() -> str:
    """Return path to ``ffmpeg`` or raise :class:`DependencyError`."""
    path = _resolve_executable("ffmpeg", "EASY_RTSP_FFMPEG", required=True)
    assert path is not None
    return path


def resolve_ffprobe() -> str:
    """Return path to ``ffprobe`` or raise :class:`DependencyError`."""
    path = _resolve_executable("ffprobe", "EASY_RTSP_FFPROBE", required=True)
    assert path is not None
    return path


def _default_mediamtx_binary() -> Path:
    exe = "mediamtx.exe" if os.name == "nt" else "mediamtx"
    return default_install_prefix() / "bin" / exe


def resolve_mediamtx() -> str | None:
    """Return path to ``mediamtx`` if on ``PATH``, ``EASY_RTSP_MEDIAMTX``, or installed via ``install-backends``."""
    found = _resolve_executable("mediamtx", "EASY_RTSP_MEDIAMTX", required=False)
    if found:
        return found
    default_bin = _default_mediamtx_binary()
    if default_bin.is_file():
        return str(default_bin)
    return None


@dataclass(frozen=True)
class VideoProbe:
    """Frame size and nominal frame rate (``None`` when unknown) of a video source."""

    width: int
    height: int
    fps: float | None


def _parse_fps(rate: str | None) -> float | None:
    if not rate or rate == "0/0":
        return None
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            n, d = float(num), float(den)
            if d == 0:
                return None
            return n / d
        except ValueError:
            return None
    try:
        return float(rate)
    except ValueError:
        return None


def is_sane_fps(fps: float | None) -> bool:
    """Whether a probed frame rate is plausible (drivers and containers sometimes report 0 or 90000)."""
    return fps is not None and _MIN_SANE_FPS <= fps <= _MAX_SANE_FPS


def _select_probed_fps(stream_info: dict[str, Any]) -> float | None:
    avg_fps = _parse_fps(stream_info.get("avg_frame_rate"))
    if is_sane_fps(avg_fps):
        return avg_fps
    r_fps = _parse_fps(stream_info.get("r_frame_rate"))
    if is_sane_fps(r_fps):
        return r_fps
    return None


def probe_video(
    path: str,
    ffprobe_bin: str | None = None,
    *,
    input_args: list[str] | None = None,
    timeout_sec: float = _PROBE_TIMEOUT_SEC,
) -> VideoProbe:
    """Probe width/height and nominal FPS for a URL or file path."""
    ffprobe = ffprobe_bin or resolve_ffprobe()
    safe_path = redact_url_credentials(path)
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate",
        "-of",
        "json",
        *(input_args or []),
        path,
    ]
    try:
        out = subprocess.check_output(
            cmd,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError as e:
        raise DependencyError("ffprobe could not be executed.") from e
    except subprocess.TimeoutExpired as e:
        raise SourceError(f"ffprobe timed out after {timeout_sec:g}s for {safe_path!r}") from e
    except subprocess.CalledProcessError as e:
        detail = redact_credentials_in_text(str(e.stderr or e).replace(path, safe_path))
        raise SourceError(f"ffprobe failed for {safe_path!r}: {detail}") from e

    try:
        data: dict[str, Any] = json.loads(out)
    except (json.JSONDecodeError, TypeError) as e:
        raise SourceError(f"ffprobe returned invalid JSON for {safe_path!r}") from e
    streams = data.get("streams") or []
    if not streams:
        raise SourceError(f"No video stream found for {safe_path!r}")
    s0 = streams[0]
    w, h = s0.get("width"), s0.get("height")
    if not isinstance(w, int) or not isinstance(h, int) or w <= 0 or h <= 0:
        raise SourceError(f"ffprobe did not return width/height for {safe_path!r}")
    fps = _select_probed_fps(s0)
    return VideoProbe(width=w, height=h, fps=fps)


def ffmpeg_ingest_rtsp_args(url: str, transport: str, latency_ms: int | None) -> list[str]:
    """Return FFmpeg input arguments (options plus ``-i URL``) for an RTSP source."""
    return [*ffmpeg_rtsp_input_options(transport, latency_ms), "-i", url]


def ffmpeg_rtsp_input_options(transport: str, latency_ms: int | None) -> list[str]:
    """Return FFmpeg/ffprobe RTSP options that must appear before the input URL."""
    args: list[str] = ["-rtsp_transport", transport]
    if latency_ms is not None:
        args += ["-max_delay", str(latency_ms * 1000)]
    return args
