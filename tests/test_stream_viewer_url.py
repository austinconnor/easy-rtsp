"""Stream.viewer_url after serve()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from easy_rtsp import Stream


def _infinite_frames():
    while True:
        yield np.zeros((48, 64, 3), dtype=np.uint8)


def test_viewer_url_rtsp_with_local_mediamtx() -> None:
    with (
        patch("easy_rtsp.stream.start_publish_thread"),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value="/bin/mediamtx"),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.MediaMTXProcess.start", return_value=MagicMock()),
        patch("easy_rtsp.stream.write_minimal_mediamtx_config"),
        patch("easy_rtsp.stream.tempfile.mkstemp", return_value=(3, "C:\\tmp\\cfg.yml")),
        patch("easy_rtsp.stream.os.close"),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        s = Stream.from_frames(_infinite_frames(), fps=30, size=(64, 48))
        s.serve("live")
        assert s.viewer_url == "rtsp://127.0.0.1:8554/live"
        assert s.webrtc_play_url is None


def test_webrtc_play_url_when_enabled_with_local_mediamtx() -> None:
    with (
        patch("easy_rtsp.stream.start_publish_thread"),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value="/bin/mediamtx"),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.MediaMTXProcess.start", return_value=MagicMock()),
        patch("easy_rtsp.stream.write_minimal_mediamtx_config"),
        patch("easy_rtsp.stream.tempfile.mkstemp", return_value=(3, "C:\\tmp\\cfg.yml")),
        patch("easy_rtsp.stream.os.close"),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        s = Stream.from_frames(
            _infinite_frames(), fps=30, size=(64, 48), webrtc_enabled=True
        )
        s.serve("live")
        assert s.viewer_url == "rtsp://127.0.0.1:8554/live"
        assert s.webrtc_play_url == "http://127.0.0.1:8889/live"


def test_webrtc_play_url_disabled_when_config_off() -> None:
    with (
        patch("easy_rtsp.stream.start_publish_thread"),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value="/bin/mediamtx"),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.MediaMTXProcess.start", return_value=MagicMock()),
        patch("easy_rtsp.stream.write_minimal_mediamtx_config"),
        patch("easy_rtsp.stream.tempfile.mkstemp", return_value=(3, "C:\\tmp\\cfg.yml")),
        patch("easy_rtsp.stream.os.close"),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        s = Stream.from_frames(_infinite_frames(), fps=30, size=(64, 48), webrtc_enabled=False)
        s.serve("live")
        assert s.webrtc_play_url is None


def test_viewer_url_tcp_without_mediamtx() -> None:
    with (
        patch("easy_rtsp.stream.start_publish_thread"),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        s = Stream.from_frames(_infinite_frames(), fps=30, size=(64, 48))
        s.serve("live")
        assert s.viewer_url == "tcp://127.0.0.1:8554"
