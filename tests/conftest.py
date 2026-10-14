"""Shared fixtures."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def local_mediamtx(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """
    Pretend MediaMTX is installed and the local RTSP port is free.

    Returns the mock standing in for :meth:`MediaMTXProcess.launch`; its ``return_value`` is the
    fake backend whose ``stop()`` calls can be asserted.
    """
    launch = MagicMock(name="MediaMTXProcess.launch")
    monkeypatch.setattr("easy_rtsp.stream.resolve_mediamtx", lambda: "/bin/mediamtx")
    monkeypatch.setattr("easy_rtsp.stream.tcp_port_is_available", lambda *a, **k: True)
    monkeypatch.setattr("easy_rtsp.stream.MediaMTXProcess.launch", launch)
    return launch


@pytest.fixture
def no_mediamtx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend MediaMTX is not installed and the local RTSP port is free (TCP fallback)."""
    monkeypatch.setattr("easy_rtsp.stream.resolve_mediamtx", lambda: None)
    monkeypatch.setattr("easy_rtsp.stream.tcp_port_is_available", lambda *a, **k: True)


@pytest.fixture
def publish_thread(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the background publish thread so serve() returns without running FFmpeg."""
    start = MagicMock(name="start_publish_thread")
    monkeypatch.setattr("easy_rtsp.stream.start_publish_thread", start)
    return start
