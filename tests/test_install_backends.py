"""install_backends helpers (network calls mocked)."""

from __future__ import annotations

import json
import sys
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

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

    with patch("platform.system", return_value="Linux"), patch(
        "platform.machine", return_value="x86_64"
    ), patch("easy_rtsp.install_backends.urllib.request.urlopen", side_effect=fake_urlopen):
        dest = install_mediamtx(prefix=tmp_path, dry_run=False)

    assert dest is not None
    assert dest.exists()
    assert dest.stat().st_size > 0


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
