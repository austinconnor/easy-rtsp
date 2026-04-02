"""Stream.map(), transforms, composition, and related API behavior."""

from __future__ import annotations

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
