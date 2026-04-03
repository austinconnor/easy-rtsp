"""Stream status snapshots."""

from __future__ import annotations

import dataclasses
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

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
    assert status.serve_started is False
    assert status.viewer_url is None
    assert status.webrtc_play_url is None
    assert status.publish_error is None
    assert status.has_publish_error is False
    assert status.publish_thread_alive is False
    assert status.created_at <= status.last_state_change_at

    with pytest.raises(dataclasses.FrozenInstanceError):
        status.state = StreamState.RUNNING  # type: ignore[misc]


def test_status_tracks_serve_stop_and_thread_liveness() -> None:
    dummy_thread = _DummyThread()

    with (
        patch("easy_rtsp.stream.start_publish_thread", return_value=dummy_thread),
        patch("easy_rtsp.stream.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.stream.tcp_port_is_available", return_value=True),
        patch("easy_rtsp.stream.time.sleep"),
    ):
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
    assert after_serve.publish_thread_alive is True
    assert after_stop.state == StreamState.STOPPED
    assert after_stop.publish_thread_alive is False
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
