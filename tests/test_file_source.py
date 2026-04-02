"""File source: loop, FPS inference for publish."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from easy_rtsp import Stream
from easy_rtsp.config import StreamConfig
from easy_rtsp.ffmpeg_util import VideoProbe
from easy_rtsp.sources.file import FileSource


@pytest.fixture
def dummy_video(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"dummy")
    return p


def test_file_loop_false_single_pass(dummy_video: Path) -> None:
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    with (
        patch("easy_rtsp.sources.file.probe_video", return_value=VideoProbe(4, 4, 30.0)),
        patch("easy_rtsp.sources.file.iter_raw_bgr_frames") as m_iter,
    ):
        m_iter.return_value = iter([frame])
        src = FileSource(dummy_video, config=StreamConfig(file_loop=False))
        frames = list(src.frames())

    assert len(frames) == 1
    assert m_iter.call_count == 1


def test_file_loop_true_uses_ffmpeg_stream_loop(dummy_video: Path) -> None:
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    with (
        patch("easy_rtsp.sources.file.probe_video", return_value=VideoProbe(4, 4, 30.0)),
        patch("easy_rtsp.sources.file.iter_raw_bgr_frames") as m_iter,
    ):
        m_iter.return_value = iter([frame.copy()])
        src = FileSource(dummy_video, config=StreamConfig(file_loop=True))
        assert next(iter(src.frames())).shape == (4, 4, 3)
    assert m_iter.call_count == 1
    argv = m_iter.call_args[0][0]
    i = argv.index("-stream_loop")
    assert argv[i + 1] == "-1"


def test_file_loop_false_has_no_stream_loop(dummy_video: Path) -> None:
    frame = np.zeros((4, 4, 3), dtype=np.uint8)

    with (
        patch("easy_rtsp.sources.file.probe_video", return_value=VideoProbe(4, 4, 30.0)),
        patch("easy_rtsp.sources.file.iter_raw_bgr_frames") as m_iter,
    ):
        m_iter.return_value = iter([frame])
        list(FileSource(dummy_video, config=StreamConfig(file_loop=False)).frames())
    argv = m_iter.call_args[0][0]
    assert "-stream_loop" not in argv


def test_infer_publish_fps_explicit_overrides_probe(dummy_video: Path) -> None:
    with patch("easy_rtsp.stream.probe_video", return_value=VideoProbe(640, 480, 30.0)):
        s = Stream.from_file(dummy_video, fps=24.0)
        w, h, fps = s._infer_publish_params()
        assert (w, h) == (640, 480)
        assert fps == 24.0


def test_infer_publish_fps_from_probe_when_unset(dummy_video: Path) -> None:
    with patch("easy_rtsp.stream.probe_video", return_value=VideoProbe(640, 480, 29.97)):
        s = Stream.from_file(dummy_video)
        _, _, fps = s._infer_publish_params()
        assert abs(fps - 29.97) < 0.01


def test_infer_publish_fps_fallback_when_probe_missing_fps(dummy_video: Path) -> None:
    with patch("easy_rtsp.stream.probe_video", return_value=VideoProbe(640, 480, None)):
        s = Stream.from_file(dummy_video)
        _, _, fps = s._infer_publish_params()
        assert fps == 30.0
