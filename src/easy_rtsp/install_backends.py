"""Optional download of MediaMTX and install hints for FFmpeg (``install-backends`` command)."""

from __future__ import annotations

import json
import platform
import stat
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from easy_rtsp.exceptions import DependencyError

GITHUB_API_LATEST = "https://api.github.com/repos/bluenviron/mediamtx/releases/latest"
USER_AGENT = "easy-rtsp-install-backends/1.0"

# Shown when MediaMTX is missing (stream fallback, doctor hint).
INSTALL_MEDIAMTX_CLI = "easy-rtsp install-backends"


def print_ffmpeg_install_hints() -> None:
    """Print OS-specific pointers; FFmpeg is not bundled."""
    sys = platform.system()
    print("FFmpeg / ffprobe (required)")
    print("  Install a full build that includes ffprobe, and ensure both are on PATH.")
    if sys == "Windows":
        print("  Windows: https://www.gyan.dev/ffmpeg/builds/  or  winget install ffmpeg")
    elif sys == "Darwin":
        print("  macOS:    brew install ffmpeg")
    else:
        print("  Linux:    use your distro package (e.g. apt install ffmpeg) or a static build.")
    print("  Or set EASY_RTSP_FFMPEG / EASY_RTSP_FFPROBE to executable paths.")
    print()


def _platform_asset_suffix() -> str:
    sys = platform.system()
    machine = platform.machine().lower()
    if sys == "Linux":
        arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
        return f"linux_{arch}.tar.gz"
    if sys == "Darwin":
        arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
        return f"darwin_{arch}.tar.gz"
    if sys == "Windows":
        return "windows_amd64.zip"
    raise DependencyError(f"Unsupported platform for bundled MediaMTX download: {sys} {machine}")


def _fetch_latest_mediamtx_release() -> dict[str, Any]:
    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_asset_url(release: dict[str, Any]) -> tuple[str, str]:
    suffix = _platform_asset_suffix()
    tag = release.get("tag_name") or ""
    for a in release.get("assets") or []:
        name = a.get("name") or ""
        if name.endswith(suffix):
            url = a.get("browser_download_url")
            if url:
                return str(url), name
    raise DependencyError(
        f"No MediaMTX release asset matching *{suffix} in {tag}. "
        "Install MediaMTX manually from https://github.com/bluenviron/mediamtx/releases"
    )


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _extract_mediamtx_binary(archive: Path, dest_bin: Path) -> None:
    if archive.suffix == ".zip" or archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            names = zf.namelist()
            exe = next((n for n in names if n.endswith("mediamtx.exe") or n.endswith("/mediamtx.exe")), None)
            if not exe:
                raise DependencyError("mediamtx.exe not found in zip")
            data = zf.read(exe)
            dest_bin.write_bytes(data)
    else:
        with tarfile.open(archive, "r:*") as tf:
            member = next(
                (m for m in tf.getmembers() if m.isfile() and m.name.endswith("/mediamtx")),
                None,
            )
            if member is None:
                # flat layout
                member = next((m for m in tf.getmembers() if m.isfile() and m.name == "mediamtx"), None)
            if member is None:
                raise DependencyError("mediamtx binary not found in archive")
            f = tf.extractfile(member)
            if f is None:
                raise DependencyError("Could not read mediamtx from archive")
            dest_bin.write_bytes(f.read())

    mode = dest_bin.stat().st_mode
    dest_bin.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_mediamtx(prefix: Path | None = None, *, dry_run: bool = False) -> Path | None:
    """
    Download the latest MediaMTX release for this OS/arch into ``prefix/bin``.

    Returns the path to the ``mediamtx`` executable, or ``None`` if *dry_run*.
    """
    prefix = prefix or Path.home() / ".easy-rtsp"
    bin_dir = prefix / "bin"
    dest_bin = bin_dir / ("mediamtx.exe" if platform.system() == "Windows" else "mediamtx")

    if dry_run:
        return dest_bin

    release = _fetch_latest_mediamtx_release()
    url, filename = _pick_asset_url(release)
    tmp = bin_dir / f".download_{filename}"
    try:
        _download(url, tmp)
        _extract_mediamtx_binary(tmp, dest_bin)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return dest_bin


def run_install_backends(
    *,
    prefix: Path | None = None,
    mediamtx: bool = True,
    dry_run: bool = False,
) -> dict[str, Path | None]:
    """
    Print FFmpeg hints and optionally download MediaMTX.

    Returns a dict with key ``mediamtx`` -> path or ``None`` (if *dry_run*).
    """
    print_ffmpeg_install_hints()
    out: dict[str, Path | None] = {"mediamtx": None}
    if not mediamtx:
        return out
    try:
        path = install_mediamtx(prefix=prefix, dry_run=dry_run)
        out["mediamtx"] = path
    except urllib.error.URLError as e:
        raise DependencyError(f"Download failed: {e}") from e
    return out
