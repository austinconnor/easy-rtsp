"""Optional download of MediaMTX and install hints for FFmpeg (``install-backends`` command)."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from easy_rtsp.exceptions import DependencyError

GITHUB_API_LATEST = "https://api.github.com/repos/bluenviron/mediamtx/releases/latest"
USER_AGENT = "easy-rtsp-install-backends/1.0"
_CHECKSUMS_ASSET = "checksums.sha256"

# Shown when MediaMTX is missing (stream fallback, doctor hint).
INSTALL_MEDIAMTX_CLI = "easy-rtsp install-backends"


def default_install_prefix() -> Path:
    """Directory ``install-backends`` uses by default (searched automatically for ``mediamtx``)."""
    return Path.home() / ".easy-rtsp"


def print_ffmpeg_install_hints() -> None:
    """Print OS-specific pointers; FFmpeg is not bundled."""
    system = platform.system()
    print("FFmpeg / ffprobe (required)")
    print("  Install a full build that includes ffprobe, and ensure both are on PATH.")
    if system == "Windows":
        print("  Windows: https://www.gyan.dev/ffmpeg/builds/  or  winget install ffmpeg")
    elif system == "Darwin":
        print("  macOS:    brew install ffmpeg")
    else:
        print("  Linux:    use your distro package (e.g. apt install ffmpeg) or a static build.")
    print("  Or set EASY_RTSP_FFMPEG / EASY_RTSP_FFPROBE to executable paths.")
    print()


def _platform_asset_suffix() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    amd64 = {"amd64", "x86_64", "x64"}
    arm64 = {"aarch64", "arm64"}
    if system == "Linux":
        if machine in amd64:
            arch = "amd64"
        elif machine in arm64:
            arch = "arm64"
        elif machine in {"armv7l", "armv7"}:
            arch = "armv7"
        elif machine in {"armv6l", "armv6"}:
            arch = "armv6"
        else:
            raise DependencyError(f"Unsupported Linux architecture: {machine}")
        return f"linux_{arch}.tar.gz"
    if system == "Darwin":
        if machine in amd64:
            arch = "amd64"
        elif machine in arm64:
            arch = "arm64"
        else:
            raise DependencyError(f"Unsupported macOS architecture: {machine}")
        return f"darwin_{arch}.tar.gz"
    if system == "Windows":
        # Windows on ARM runs the amd64 build under emulation; MediaMTX ships no native arm64 zip.
        if machine in amd64 or machine in arm64:
            return "windows_amd64.zip"
        raise DependencyError(f"Unsupported Windows architecture: {machine}")
    raise DependencyError(f"Unsupported platform for bundled MediaMTX download: {system} {machine}")


def _fetch_latest_mediamtx_release() -> dict[str, Any]:
    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pick_asset(release: dict[str, Any]) -> dict[str, Any]:
    suffix = _platform_asset_suffix()
    for asset in release.get("assets") or []:
        if (asset.get("name") or "").endswith(suffix) and asset.get("browser_download_url"):
            return asset
    tag = release.get("tag_name") or ""
    raise DependencyError(
        f"No MediaMTX release asset matching *{suffix} in {tag}. "
        "Install MediaMTX manually from https://github.com/bluenviron/mediamtx/releases"
    )


def _read_url(url: str, *, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_read_url(url, timeout=120))


def _expected_sha256(release: dict[str, Any], asset: dict[str, Any]) -> str | None:
    """SHA-256 published for *asset*: GitHub's asset digest, else the release's checksums file."""
    digest = asset.get("digest") or ""
    if digest.startswith("sha256:"):
        return digest.split(":", 1)[1].lower()
    for candidate in release.get("assets") or []:
        if candidate.get("name") == _CHECKSUMS_ASSET and candidate.get("browser_download_url"):
            listing = _read_url(candidate["browser_download_url"], timeout=60).decode("utf-8")
            for line in listing.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[1].lstrip("*") == asset.get("name"):
                    return parts[0].lower()
    return None


def _verify_sha256(path: Path, expected: str) -> None:
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise DependencyError(
            f"Checksum mismatch for {path.name}: expected {expected}, got {actual}. "
            "The download may be corrupt or tampered with; retry or install MediaMTX manually."
        )


def _extract_mediamtx_binary(archive: Path, dest_bin: Path) -> None:
    """Extract the ``mediamtx`` executable, replacing *dest_bin* atomically."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            exe = next(
                (n for n in zf.namelist() if PurePosixPath(n).name.lower() == "mediamtx.exe"),
                None,
            )
            if not exe:
                raise DependencyError("mediamtx.exe not found in zip")
            data = zf.read(exe)
    else:
        with tarfile.open(archive, "r:*") as tf:
            member = next(
                (
                    m
                    for m in tf.getmembers()
                    if m.isfile() and PurePosixPath(m.name).name == "mediamtx"
                ),
                None,
            )
            if member is None:
                raise DependencyError("mediamtx binary not found in archive")
            f = tf.extractfile(member)
            if f is None:
                raise DependencyError("Could not read mediamtx from archive")
            data = f.read()

    staged = dest_bin.with_name(f".{dest_bin.name}.partial")
    try:
        staged.write_bytes(data)
        staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.replace(staged, dest_bin)
    except OSError as e:
        staged.unlink(missing_ok=True)
        raise DependencyError(
            f"Could not install MediaMTX to {dest_bin}: {e}. "
            "Stop any running MediaMTX process and retry."
        ) from e


def install_mediamtx(prefix: Path | None = None, *, dry_run: bool = False) -> Path | None:
    """
    Download the latest MediaMTX release for this OS/arch into ``prefix/bin``.

    The archive is verified against the release's published SHA-256 before it is extracted.
    Returns the path to the ``mediamtx`` executable (where it would go, if *dry_run*).
    """
    prefix = prefix or default_install_prefix()
    bin_dir = prefix / "bin"
    dest_bin = bin_dir / ("mediamtx.exe" if platform.system() == "Windows" else "mediamtx")

    if dry_run:
        return dest_bin

    release = _fetch_latest_mediamtx_release()
    asset = _pick_asset(release)
    expected = _expected_sha256(release, asset)
    tmp = bin_dir / f".download_{asset['name']}"
    try:
        _download(str(asset["browser_download_url"]), tmp)
        if expected:
            _verify_sha256(tmp, expected)
        else:
            print(f"warning: no published checksum for {asset['name']}; skipping verification")
        _extract_mediamtx_binary(tmp, dest_bin)
    finally:
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

    Returns a dict with key ``mediamtx`` -> installed path, or ``None`` if MediaMTX was skipped.
    """
    print_ffmpeg_install_hints()
    out: dict[str, Path | None] = {"mediamtx": None}
    if not mediamtx:
        return out
    try:
        out["mediamtx"] = install_mediamtx(prefix=prefix, dry_run=dry_run)
    except urllib.error.URLError as e:
        raise DependencyError(f"Download failed: {e}") from e
    return out
