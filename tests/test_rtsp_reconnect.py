"""RTSP reconnect behaviour (mocked FFmpeg)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import SourceError
from easy_rtsp.ffmpeg_util import VideoProbe
from easy_rtsp.sources.rtsp import RtspSource


@patch("easy_rtsp.sources.rtsp.iter_raw_bgr_frames")
@patch("easy_rtsp.sources.rtsp.probe_video")
def test_rtsp_decode_error_no_reconnect(mock_probe: object, mock_iter: object) -> None:
    mock_probe.return_value = VideoProbe(640, 480, 30.0)
    mock_iter.side_effect = SourceError("decode failed")

    cfg = StreamConfig(reconnect=False)
    src = RtspSource("rtsp://127.0.0.1:9/x", cfg)
    with pytest.raises(SourceError, match="decode failed"):
        list(src.frames())
    assert src.reconnect_count == 0


@patch("easy_rtsp.sources.rtsp.iter_raw_bgr_frames")
@patch("easy_rtsp.sources.rtsp.probe_video")
def test_rtsp_max_reconnect_attempts(mock_probe: object, mock_iter: object) -> None:
    mock_probe.return_value = VideoProbe(640, 480, 30.0)
    mock_iter.side_effect = SourceError("decode failed")

    cfg = StreamConfig(
        reconnect=True,
        max_reconnect_attempts=2,
        retry_interval_sec=0.0,
    )
    src = RtspSource("rtsp://127.0.0.1:9/x", cfg)
    with pytest.raises(SourceError):
        list(src.frames())
    assert src.reconnect_count == 2


@patch("easy_rtsp.sources.rtsp.iter_raw_bgr_frames")
@patch("easy_rtsp.sources.rtsp.probe_video")
def test_rtsp_zero_reconnect_attempts(mock_probe: object, mock_iter: object) -> None:
    mock_probe.return_value = VideoProbe(640, 480, 30.0)
    mock_iter.side_effect = SourceError("decode failed")

    cfg = StreamConfig(reconnect=True, max_reconnect_attempts=0, retry_interval_sec=0.0)
    src = RtspSource("rtsp://127.0.0.1:9/x", cfg)
    with pytest.raises(SourceError):
        list(src.frames())
    assert src.reconnect_count == 0


@patch("easy_rtsp.sources.rtsp.iter_raw_bgr_frames")
@patch("easy_rtsp.sources.rtsp.probe_video")
def test_rtsp_probe_retries(mock_probe: object, mock_iter: object) -> None:
    mock_probe.side_effect = [OSError("down"), VideoProbe(640, 480, 30.0)]
    mock_iter.return_value = iter(())

    cfg = StreamConfig(reconnect=True, max_reconnect_attempts=1, retry_interval_sec=0.0)
    src = RtspSource("rtsp://127.0.0.1:9/x", cfg)
    list(src.frames())
    assert src.reconnect_count == 1
