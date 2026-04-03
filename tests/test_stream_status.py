"""Stream status snapshots."""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from easy_rtsp.exceptions import SourceError
from easy_rtsp import Stream, StreamStatus
from easy_rtsp.types import StreamState


class _DummyThread:
    def __init__(self) -> None:
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        self.alive = False


def _frame_gen():
    yield np.zeros((8, 12, 3), dtype=np.uint8)


def test_status_before_serve_is_minimal_and_stable() -> None:
    stream = Stream.from_frames(_frame_gen, fps=30.0, size=(12, 8))
    status = stream.status()

    assert isinstance(status, StreamStatus)
    assert status.state == StreamState.STOPPED
    assert status.reconnect_count == 0
    assert status.last_reconnect_reason is None
    assert status.serve_started is False
    assert status.viewer_url is None
    assert status.webrtc_play_url is None
    assert status.publish_error is None
    assert status.has_publish_error is False
    assert status.dropped_frame_count == 0
    assert status.last_frame_at is None
    assert status.publish_started_at is None
    assert status.publish_uptime_sec is None
    assert status.alive_child_process_count == 0
    assert status.publish_thread_alive is False
    assert status.created_at <= status.last_state_change_at

    with pytest.raises(dataclasses.FrozenInstanceError):
        status.state = StreamState.RUNNING  # type: ignore[misc]


def test_status_tracks_serve_stop_and_thread_liveness() -> None:
    dummy_thread = _DummyThread()
    alive_child = MagicMock()
    alive_child.poll.return_value = None
    dead_child = MagicMock()
    dead_child.poll.return_value = 0

    with (
        patch("easy_rtsp.stream.start_publish_thread") as start_publish_thread,
        patch("easy_rtsp.stream.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        def fake_start_publish_thread(*args: Any, **kwargs: Any) -> _DummyThread:
            kwargs["proc_holder"].extend([alive_child, dead_child])
            return dummy_thread

        start_publish_thread.side_effect = fake_start_publish_thread
        stream = Stream.from_frames(_frame_gen, fps=30.0, size=(12, 8))
        before = stream.status()
        stream.serve("live")
        after_serve = stream.status()
        stream.stop()
        after_stop = stream.status()

    assert before.state == StreamState.STOPPED
    assert after_serve.state == StreamState.RUNNING
    assert after_serve.serve_started is True
    assert after_serve.viewer_url == "tcp://127.0.0.1:8554"
    assert after_serve.publish_started_at is not None
    assert after_serve.publish_uptime_sec is not None
    assert after_serve.publish_uptime_sec >= 0.0
    assert after_serve.alive_child_process_count == 1
    assert after_serve.publish_thread_alive is True
    assert after_stop.state == StreamState.STOPPED
    assert after_stop.publish_thread_alive is False
    assert after_stop.publish_uptime_sec is not None
    assert after_stop.last_state_change_at >= after_serve.last_state_change_at


def test_status_reports_publish_error_after_failure() -> None:
    dummy_thread = _DummyThread()
    captured: dict[str, Any] = {}

    def fake_start_publish_thread(*args: Any, **kwargs: Any) -> _DummyThread:
        captured["on_done"] = kwargs["on_done"]
        return dummy_thread

    with (
        patch("easy_rtsp.stream.start_publish_thread", side_effect=fake_start_publish_thread),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.time.sleep"),
    ):
        stream = Stream.from_frames(_frame_gen, fps=30.0, size=(12, 8))
        stream.serve("live")
        dummy_thread.alive = False
        captured["on_done"](RuntimeError("boom"))

    status = stream.status()
    assert status.state == StreamState.ERROR
    assert status.has_publish_error is True
    assert status.publish_error == "boom"
    assert status.publish_thread_alive is False


def test_status_tracks_frame_timestamps_and_drop_count() -> None:
    def gen():
        for i in range(1, 4):
            yield np.full((6, 6, 3), i, dtype=np.uint8)

    stream = Stream.from_frames(gen, fps=30.0, size=(6, 6)).map(
        lambda frame: frame if int(frame[0, 0, 0]) != 2 else None
    )
    list(stream.frames())
    status = stream.status()

    assert status.latest_frame_available is True
    assert status.dropped_frame_count == 1
    assert status.last_frame_at is not None


def test_status_reports_last_reconnect_reason_for_rtsp() -> None:
    with (
        patch("easy_rtsp.sources.rtsp.probe_video", side_effect=[OSError("down"), OSError("down")]),
        patch("easy_rtsp.sources.rtsp.iter_raw_bgr_frames"),
    ):
        stream = Stream.open(
            "rtsp://127.0.0.1:8554/live",
            reconnect=True,
            max_reconnect_attempts=1,
            retry_interval_sec=0.0,
        )
        with pytest.raises(SourceError):
            list(stream.frames())

    status = stream.status()
    assert status.reconnect_count == 1
    assert status.last_reconnect_reason == "probe_failed"
