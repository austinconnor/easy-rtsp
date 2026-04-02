"""FFmpeg / ffprobe discovery and helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from easy_rtsp.exceptions import DependencyError


def _which(name: str) -> str | None:
    return shutil.which(name)

def resolve_ffmpeg() -> str:
    """Return path to ``ffmpeg`` or raise :class:`DependencyError`."""
    path = os.environ.get("EASY_RTSP_FFMPEG") or _which("ffmpeg")
    if not path:
        raise DependencyError(
            "ffmpeg not found on PATH. Install FFmpeg and ensure it is available, "
            "or set EASY_RTSP_FFMPEG to the FFmpeg executable path."
        )
    return path


def resolve_ffprobe() -> str:
    """Return path to ``ffprobe`` or raise :class:`DependencyError`."""
    path = os.environ.get("EASY_RTSP_FFPROBE") or _which("ffprobe")
    if not path:
        raise DependencyError(
            "ffprobe not found on PATH. Install FFmpeg (includes ffprobe) "
            "or set EASY_RTSP_FFPROBE to the ffprobe executable path."
        )
    return path


def resolve_mediamtx() -> str | None:
    """Return path to ``mediamtx`` if ``PATH`` or ``EASY_RTSP_MEDIAMTX`` is set."""
    return os.environ.get("EASY_RTSP_MEDIAMTX") or _which("mediamtx")


@dataclass(frozen=True)
class VideoProbe:
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


def probe_video(path: str, ffprobe_bin: str | None = None) -> VideoProbe:
    """Probe width/height and nominal FPS for a URL or file path."""
    ffprobe = ffprobe_bin or resolve_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "json",
        path,
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError as e:
        raise DependencyError("ffprobe could not be executed.") from e
    except subprocess.CalledProcessError as e:
        raise DependencyError(f"ffprobe failed for {path!r}: {e.stderr or e}") from e

    data: dict[str, Any] = json.loads(out)
    streams = data.get("streams") or []
    if not streams:
        raise DependencyError(f"No video stream found for {path!r}")
    s0 = streams[0]
    w, h = s0.get("width"), s0.get("height")
    if not isinstance(w, int) or not isinstance(h, int):
        raise DependencyError(f"ffprobe did not return width/height for {path!r}")
    fps = _parse_fps(s0.get("r_frame_rate"))
    return VideoProbe(width=w, height=h, fps=fps)


def ffmpeg_ingest_rtsp_args(url: str, transport: str, latency_ms: int | None) -> list[str]:
    args: list[str] = ["-rtsp_transport", transport]
    if latency_ms is not None:
        args += ["-max_delay", str(latency_ms * 1000)]
    args += ["-i", url]
    return args
