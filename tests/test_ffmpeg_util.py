"""FFmpeg executable discovery and probing."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import probe_video, resolve_ffmpeg


def test_probe_applies_input_options_before_url() -> None:
    payload = json.dumps({"streams": [{"width": 640, "height": 480, "r_frame_rate": "30/1"}]})
    with patch("easy_rtsp.ffmpeg_util.subprocess.check_output", return_value=payload) as run:
        probe = probe_video(
            "rtsp://camera/live",
            ffprobe_bin="ffprobe",
            input_args=["-rtsp_transport", "udp"],
        )

    cmd = run.call_args[0][0]
    assert cmd.index("-rtsp_transport") < cmd.index("rtsp://camera/live")
    assert probe.fps == 30.0


def test_probe_timeout_redacts_password() -> None:
    error = subprocess.TimeoutExpired(["ffprobe"], 15)
    with patch("easy_rtsp.ffmpeg_util.subprocess.check_output", side_effect=error):
        with pytest.raises(SourceError) as exc:
            probe_video("rtsp://user:secret@camera/live", ffprobe_bin="ffprobe")
    assert "secret" not in str(exc.value)
    assert "user:***@camera" in str(exc.value)


def test_invalid_executable_override_fails_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASY_RTSP_FFMPEG", "definitely-not-an-executable")
    with patch("easy_rtsp.ffmpeg_util._which", return_value=None):
        with pytest.raises(DependencyError, match="EASY_RTSP_FFMPEG"):
            resolve_ffmpeg()
