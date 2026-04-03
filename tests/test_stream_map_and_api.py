"""Stream.map(), transforms, composition, and related API behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from easy_rtsp import ConfigurationError, ProcessingError, Stream
from easy_rtsp.types import StreamState


def test_map_applies_function_to_each_frame() -> None:
    def gen():
        yield np.full((10, 10, 3), 100, dtype=np.uint8)

    s = Stream.from_frames(gen, fps=30.0, size=(10, 10)).map(lambda f: f // 2)
    out = list(s.frames())
    assert len(out) == 1
    assert out[0][0, 0, 0] == 50


def test_map_chained_applies_outer_then_inner_order() -> None:
    """First ``.map`` runs on source frames; second ``.map`` runs on the result."""

    def gen():
        yield np.ones((10, 10, 3), dtype=np.uint8) * 10

    s = (
        Stream.from_frames(gen, fps=30.0, size=(10, 10))
        .map(lambda f: f + 1)
        .map(lambda f: f * 2)
    )
    out = list(s.frames())[0]
    assert out[0, 0, 0] == (10 + 1) * 2


def test_map_drop_frame_when_returns_none() -> None:
    def gen():
        for i in range(4):
            yield np.full((10, 10, 3), i, dtype=np.uint8)

    s = Stream.from_frames(gen, fps=30.0, size=(10, 10)).map(
        lambda f: f if f[0, 0, 0] % 2 == 1 else None
    )
    out = list(s.frames())
    assert len(out) == 2
    assert out[0][0, 0, 0] == 1
    assert out[1][0, 0, 0] == 3


def test_map_opencv_draw_rectangle() -> None:
    import cv2

    def gen():
        yield np.zeros((48, 64, 3), dtype=np.uint8)

    def annotate(f: np.ndarray) -> np.ndarray:
        out = f.copy()
        cv2.rectangle(out, (4, 4), (40, 40), (0, 255, 0), thickness=2)
        cv2.putText(out, "easy-rtsp", (4, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        return out

    s = Stream.from_frames(gen, fps=30.0, size=(64, 48)).map(annotate)
    frame = list(s.frames())[0]
    # Border is BGR green (0, 255, 0); interior stays black
    assert frame[5, 5, 1] == 255
    assert np.any(frame[:, :, :] > 0)


def test_map_numpy_grayscale_blend() -> None:
    def gen():
        b = np.zeros((12, 16, 3), dtype=np.uint8)
        b[:, :, 2] = 200
        yield b

    def to_gray_bgr(f: np.ndarray) -> np.ndarray:
        import cv2

        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)

    s = Stream.from_frames(gen, fps=30.0, size=(16, 12)).map(to_gray_bgr)
    out = list(s.frames())[0]
    assert out.shape == (12, 16, 3)
    # Grayscale converted back to BGR should have near-equal channels
    assert abs(int(out[6, 8, 0]) - int(out[6, 8, 1])) < 5


def test_map_raises_processing_error_on_callback_failure() -> None:
    def gen():
        yield np.zeros((10, 10, 3), dtype=np.uint8)

    def bad(_: np.ndarray) -> np.ndarray:
        raise ValueError("boom")

    s = Stream.from_frames(gen, fps=30.0, size=(10, 10)).map(bad)
    with pytest.raises(ProcessingError, match="transform callback failed"):
        list(s.frames())


def test_unknown_stream_kwarg_raises() -> None:
    with pytest.raises(ConfigurationError, match="Unknown stream options"):
        Stream.from_frames((x for x in []), fps=30.0, size=(10, 10), not_a_field=True)  # type: ignore[call-arg]


def test_serve_twice_raises() -> None:
    from unittest.mock import MagicMock, patch

    def gen():
        yield np.zeros((48, 64, 3), dtype=np.uint8)

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
        s = Stream.from_frames(gen, fps=30.0, size=(64, 48)).serve("live")
        with pytest.raises(ConfigurationError, match="already started"):
            s.serve("live")


def test_viewer_url_none_before_serve() -> None:
    def gen():
        yield np.zeros((10, 10, 3), dtype=np.uint8)

    s = Stream.from_frames(gen, fps=30.0, size=(10, 10))
    assert s.viewer_url is None


def test_context_manager_calls_stop() -> None:
    def gen():
        yield np.zeros((10, 10, 3), dtype=np.uint8)

    stream: Stream | None = None
    with Stream.from_frames(gen, fps=30.0, size=(10, 10)) as s:
        stream = s
        assert list(s.frames())
    assert stream is not None
    assert stream.state == StreamState.STOPPED


def test_stop_unblocks_waiters_even_without_publish_thread() -> None:
    s = Stream.from_frames(iter(()), fps=30.0, size=(10, 10))
    s.stop()
    assert s.wait(timeout=0.0)


def test_status_reports_initial_state() -> None:
    s = Stream.from_frames(iter(()), fps=30.0, size=(10, 10))
    status = s.status()

    assert status.state == StreamState.STOPPED
    assert status.reconnect_count == 0
    assert status.serve_started is False
    assert status.latest_frame_available is False
    assert status.viewer_url is None
    assert status.webrtc_play_url is None
    assert status.has_publish_error is False
    assert status.publish_thread_alive is False
    assert status.last_state_change_at >= status.created_at


def test_latest_frame_tracks_transformed_output_and_copies() -> None:
    def gen():
        yield np.full((4, 4, 3), 10, dtype=np.uint8)
        yield np.full((4, 4, 3), 20, dtype=np.uint8)

    s = Stream.from_frames(gen, fps=30.0, size=(4, 4)).map(lambda f: f + 1)
    frames = list(s.frames())

    assert len(frames) == 2
    latest = s.latest_frame()
    assert latest is not None
    assert latest[0, 0, 0] == 21

    latest[0, 0, 0] = 99
    assert s.latest_frame()[0, 0, 0] == 21


def test_latest_frame_updates_through_serve_path() -> None:
    def gen():
        yield np.full((4, 4, 3), 42, dtype=np.uint8)

    def fake_start_publish_thread(frame_iter_factory, **kwargs):
        next(frame_iter_factory())
        return MagicMock()

    with patch("easy_rtsp.stream.start_publish_thread", side_effect=fake_start_publish_thread):
        s = Stream.from_frames(gen, fps=30.0, size=(4, 4)).serve("srt://127.0.0.1:9000")

    latest = s.latest_frame()
    assert latest is not None
    assert latest[0, 0, 0] == 42


def test_status_reports_serve_state_and_latest_frame() -> None:
    def gen():
        yield np.full((4, 4, 3), 42, dtype=np.uint8)

    thread = MagicMock()
    thread.is_alive.return_value = True

    def fake_start_publish_thread(frame_iter_factory, **kwargs):
        next(frame_iter_factory())
        return thread

    with patch("easy_rtsp.stream.start_publish_thread", side_effect=fake_start_publish_thread):
        s = Stream.from_frames(gen, fps=30.0, size=(4, 4)).serve("srt://127.0.0.1:9000")

    status = s.status()
    assert status.state == StreamState.RUNNING
    assert status.serve_started is True
    assert status.latest_frame_available is True
    assert status.viewer_url == "srt://127.0.0.1:9000"
    assert status.publish_thread_alive is True


def test_status_reports_publish_error_flag() -> None:
    s = Stream.from_frames(iter(()), fps=30.0, size=(4, 4))
    s._publish_error = RuntimeError("boom")

    status = s.status()
    assert status.publish_error == "boom"
    assert status.has_publish_error is True


def test_save_snapshot_writes_image_file(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")

    def gen():
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        frame[:, :, 1] = 128
        yield frame

    s = Stream.from_frames(gen, fps=30.0, size=(4, 4))
    next(s.frames())
    dest = s.save_snapshot(tmp_path / "nested" / "snapshot.png")

    assert dest.exists()
    assert dest.parent == tmp_path / "nested"
    saved = cv2.imread(str(dest))
    assert saved is not None
    assert saved.shape == (4, 4, 3)
    assert int(saved[0, 0, 1]) >= 120


def test_save_snapshot_requires_frame() -> None:
    s = Stream.from_frames(iter(()), fps=30.0, size=(4, 4))
    with pytest.raises(ProcessingError, match="No frame available yet"):
        s.save_snapshot(Path("snapshot.png"))
