"""Stream.viewer_url and related playback URLs after serve()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from easy_rtsp import ConfigurationError, DependencyError, Stream


def _infinite_frames():
    while True:
        yield np.zeros((48, 64, 3), dtype=np.uint8)


def _stream(**options) -> Stream:
    return Stream.from_frames(_infinite_frames(), fps=30, size=(64, 48), **options)


@pytest.mark.usefixtures("publish_thread")
def test_viewer_url_rtsp_with_local_mediamtx(local_mediamtx: MagicMock) -> None:
    s = _stream().serve("live")

    assert s.viewer_url == "rtsp://127.0.0.1:8554/live"
    assert s.webrtc_play_url is None
    kwargs = local_mediamtx.call_args.kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["path_name"]) == ("127.0.0.1", 8554, "live")
    assert kwargs["webrtc_enabled"] is False


@pytest.mark.usefixtures("publish_thread")
def test_webrtc_play_url_when_enabled_with_local_mediamtx(local_mediamtx: MagicMock) -> None:
    s = _stream(webrtc_enabled=True, webrtc_ice_port=9189).serve("live")

    assert s.viewer_url == "rtsp://127.0.0.1:8554/live"
    assert s.webrtc_play_url == "http://127.0.0.1:8889/live"
    assert local_mediamtx.call_args.kwargs["webrtc_ice_port"] == 9189


@pytest.mark.usefixtures("publish_thread", "local_mediamtx")
def test_webrtc_play_url_disabled_when_config_off() -> None:
    s = _stream(webrtc_enabled=False).serve("live")
    assert s.webrtc_play_url is None


@pytest.mark.usefixtures("publish_thread", "no_mediamtx")
def test_viewer_url_tcp_without_mediamtx() -> None:
    s = _stream().serve("live")
    assert s.viewer_url == "tcp://127.0.0.1:8554"


@pytest.mark.usefixtures("publish_thread")
def test_existing_local_server_is_used_as_push_target(monkeypatch: pytest.MonkeyPatch) -> None:
    launch = MagicMock()
    monkeypatch.setattr("easy_rtsp.stream.tcp_port_is_available", lambda *a, **k: False)
    monkeypatch.setattr("easy_rtsp.stream.MediaMTXProcess.launch", launch)

    s = _stream().serve("live")

    assert s.viewer_url == "rtsp://127.0.0.1:8554/live"
    launch.assert_not_called()


@pytest.mark.usefixtures("publish_thread")
def test_lan_mode_reports_ready_to_use_urls(local_mediamtx: MagicMock) -> None:
    with patch("easy_rtsp.stream.discover_lan_hosts", return_value=["192.168.1.42"]):
        stream = _stream(lan_access=True, webrtc_enabled=True).serve("live")

    assert stream.lan_viewer_urls == ("rtsp://192.168.1.42:8554/live",)
    assert stream.lan_webrtc_play_urls == ("http://192.168.1.42:8889/live",)
    assert local_mediamtx.call_args.kwargs["lan_access"] is True


def test_lan_mode_checks_wildcard_port_availability(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_available(host: str, port: int, **kwargs) -> bool:
        calls.append({"host": host, "port": port, **kwargs})
        return True

    monkeypatch.setattr("easy_rtsp.stream.tcp_port_is_available", fake_available)
    monkeypatch.setattr("easy_rtsp.stream.resolve_mediamtx", lambda: "/bin/mediamtx")
    monkeypatch.setattr("easy_rtsp.stream.MediaMTXProcess.launch", MagicMock())
    monkeypatch.setattr("easy_rtsp.stream.start_publish_thread", MagicMock())
    monkeypatch.setattr("easy_rtsp.stream.discover_lan_hosts", lambda: [])

    _stream(lan_access=True).serve("live")

    assert calls == [{"host": "127.0.0.1", "port": 8554, "lan_access": True}]


@pytest.mark.usefixtures("no_mediamtx")
def test_lan_mode_requires_mediamtx() -> None:
    with pytest.raises(DependencyError, match="LAN RTSP requires MediaMTX"):
        _stream(lan_access=True).serve("live")


@pytest.mark.usefixtures("publish_thread", "local_mediamtx")
def test_local_rtsps_without_existing_server_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="RTSPS server"):
        _stream().serve("rtsps://127.0.0.1:8322/live")
