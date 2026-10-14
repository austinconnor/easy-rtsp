"""install_backends helpers (network calls mocked)."""

from __future__ import annotations

import hashlib
import json
import sys
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from easy_rtsp.install_backends import print_ffmpeg_install_hints, run_install_backends


def test_print_ffmpeg_hints_does_not_crash() -> None:
    buf = StringIO()
    with patch.object(sys, "stdout", buf):
        print_ffmpeg_install_hints()
    assert "FFmpeg" in buf.getvalue()


def test_run_install_backends_skip_mediamtx() -> None:
    buf = StringIO()
    with patch.object(sys, "stdout", buf):
        out = run_install_backends(mediamtx=False, dry_run=False)
    assert out["mediamtx"] is None
    assert "FFmpeg" in buf.getvalue()


def test_run_install_backends_dry_run_mediamtx(tmp_path: Path) -> None:
    out = run_install_backends(prefix=tmp_path, mediamtx=True, dry_run=True)
    assert out["mediamtx"] is not None
    assert str(tmp_path) in str(out["mediamtx"])


def test_install_mediamtx_download_mocked(tmp_path: Path) -> None:
    from easy_rtsp.install_backends import install_mediamtx

    release = {
        "tag_name": "v1.0.0",
        "assets": [
            {
                "name": "mediamtx_v1.0.0_linux_amd64.tar.gz",
                "browser_download_url": "https://example.com/mtx.tgz",
            }
        ],
    }
    fake_tar = _minimal_tar_with_mediamtx()

    def fake_urlopen(req, timeout=60):
        url = req.full_url if hasattr(req, "full_url") else getattr(req, "selector", str(req))
        if "api.github.com" in str(url):
            return _FakeResp(json.dumps(release).encode())
        if "example.com" in str(url):
            return _FakeResp(fake_tar)
        raise AssertionError(url)

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="x86_64"),
        patch("easy_rtsp.install_backends.urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        dest = install_mediamtx(prefix=tmp_path, dry_run=False)

    assert dest is not None
    assert dest.exists()
    assert dest.stat().st_size > 0


def _install_with_release(tmp_path: Path, release: dict, files: dict[str, bytes]) -> Path | None:
    from easy_rtsp.install_backends import install_mediamtx

    def fake_urlopen(req, timeout=60):
        url = req.full_url
        if "api.github.com" in url:
            return _FakeResp(json.dumps(release).encode())
        return _FakeResp(files[url])

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="x86_64"),
        patch("easy_rtsp.install_backends.urllib.request.urlopen", side_effect=fake_urlopen),
    ):
        return install_mediamtx(prefix=tmp_path)


def _release(*, digest: str | None = None, checksums: bool = False) -> dict:
    asset = {
        "name": "mediamtx_v1.0.0_linux_amd64.tar.gz",
        "browser_download_url": "https://example.com/mtx.tgz",
    }
    if digest:
        asset["digest"] = digest
    assets = [asset]
    if checksums:
        assets.append(
            {"name": "checksums.sha256", "browser_download_url": "https://example.com/sums"}
        )
    return {"tag_name": "v1.0.0", "assets": assets}


def test_install_verifies_checksums_file(tmp_path: Path) -> None:
    archive = _minimal_tar_with_mediamtx()
    sums = f"{'0' * 64} *other.zip\n{hashlib.sha256(archive).hexdigest()} *mediamtx_v1.0.0_linux_amd64.tar.gz\n"

    dest = _install_with_release(
        tmp_path,
        _release(checksums=True),
        {"https://example.com/mtx.tgz": archive, "https://example.com/sums": sums.encode()},
    )

    assert dest is not None and dest.exists()


def test_install_rejects_checksum_mismatch(tmp_path: Path) -> None:
    from easy_rtsp.exceptions import DependencyError

    with pytest.raises(DependencyError, match="Checksum mismatch"):
        _install_with_release(
            tmp_path,
            _release(digest="sha256:" + "0" * 64),
            {"https://example.com/mtx.tgz": _minimal_tar_with_mediamtx()},
        )

    assert list((tmp_path / "bin").iterdir()) == []


def test_install_prefers_github_asset_digest(tmp_path: Path) -> None:
    archive = _minimal_tar_with_mediamtx()
    dest = _install_with_release(
        tmp_path,
        _release(digest="sha256:" + hashlib.sha256(archive).hexdigest()),
        {"https://example.com/mtx.tgz": archive},
    )
    assert dest is not None and dest.read_bytes().startswith(b"#!/bin/sh")


def test_linux_armv7_asset_is_selected() -> None:
    from easy_rtsp.install_backends import _platform_asset_suffix

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="armv7l"),
    ):
        assert _platform_asset_suffix() == "linux_armv7.tar.gz"


def test_unknown_architecture_is_not_mistaken_for_amd64() -> None:
    from easy_rtsp.exceptions import DependencyError
    from easy_rtsp.install_backends import _platform_asset_suffix

    with (
        patch("platform.system", return_value="Linux"),
        patch("platform.machine", return_value="mips64"),
        pytest.raises(DependencyError, match="Unsupported Linux architecture"),
    ):
        _platform_asset_suffix()


def test_windows_arm64_selects_windows_amd64_zip() -> None:
    from easy_rtsp.install_backends import _platform_asset_suffix

    with (
        patch("platform.system", return_value="Windows"),
        patch("platform.machine", return_value="ARM64"),
    ):
        assert _platform_asset_suffix() == "windows_amd64.zip"


class _FakeResp:
    def __init__(self, data: bytes) -> None:
        self._bio = BytesIO(data)

    def read(self) -> bytes:
        return self._bio.read()

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _minimal_tar_with_mediamtx() -> bytes:
    import io
    import tarfile

    buf = io.BytesIO()
    data = b"#!/bin/sh\necho mediamtx\n"
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="mediamtx_v1_linux_amd64/mediamtx")
        ti.size = len(data)
        ti.mode = 0o755
        tf.addfile(ti, BytesIO(data))
    return buf.getvalue()
