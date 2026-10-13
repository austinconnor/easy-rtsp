"""Decode subprocess cleanup."""

from __future__ import annotations

import threading
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.exceptions import SourceError
from easy_rtsp.sources.decode import iter_raw_bgr_frames


def test_iter_raw_bgr_frames_removes_process_from_holder() -> None:
    frame = bytes(range(12))
    holder: list[object] = []
    proc = MagicMock()
    proc.stdout = BytesIO(frame)
    proc.stderr = BytesIO(b"")
    proc.poll.return_value = 0
    proc.wait.return_value = 0
    proc.returncode = 0

    with (
        patch("easy_rtsp.sources.decode.resolve_ffmpeg", return_value="/bin/ffmpeg"),
        patch("easy_rtsp.sources.decode.subprocess.Popen", return_value=proc),
    ):
        frames = list(iter_raw_bgr_frames(["-i", "input"], 2, 2, proc_holder=holder))

    assert len(frames) == 1
    assert frames[0].flags.writeable is True
    frames[0][0, 0, 0] = 255
    assert holder == []


def test_iter_raw_bgr_frames_redacts_credentials_on_error() -> None:
    proc = MagicMock()
    proc.stdout = BytesIO(b"")
    proc.stderr = BytesIO(b"rtsp://admin:supersecret@camera/live: 401 Unauthorized")
    proc.poll.return_value = 1
    proc.wait.return_value = 1
    proc.returncode = 1

    with (
        patch("easy_rtsp.sources.decode.resolve_ffmpeg", return_value="/bin/ffmpeg"),
        patch("easy_rtsp.sources.decode.subprocess.Popen", return_value=proc),
        pytest.raises(SourceError) as exc,
    ):
        list(iter_raw_bgr_frames(["-i", "rtsp://admin:supersecret@camera/live"], 2, 2))

    assert "supersecret" not in str(exc.value)
    assert "admin:***@camera" in str(exc.value)


def test_iter_raw_bgr_frames_suppresses_error_when_stop_event_set() -> None:
    stop_event = threading.Event()
    stop_event.set()
    proc = MagicMock()
    proc.stdout = BytesIO(b"")
    proc.stderr = BytesIO(b"Exiting normally, received signal 15")
    proc.poll.return_value = 1
    proc.wait.return_value = 1
    proc.returncode = 1

    with (
        patch("easy_rtsp.sources.decode.resolve_ffmpeg", return_value="/bin/ffmpeg"),
        patch("easy_rtsp.sources.decode.subprocess.Popen", return_value=proc),
    ):
        frames = list(iter_raw_bgr_frames(["-i", "input"], 2, 2, stop_event=stop_event))

    assert frames == []
