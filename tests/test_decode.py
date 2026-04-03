"""Decode subprocess cleanup."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

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
    assert holder == []
