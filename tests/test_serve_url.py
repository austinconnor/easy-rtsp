"""Tests for serve URL parsing."""

import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError
from easy_rtsp.serve_url import (
    is_loopback_host,
    parse_publish_destination,
    parse_serve_endpoint,
)


def test_shorthand_live() -> None:
    cfg = StreamConfig(server_host="127.0.0.1", server_port=8554)
    url, host, port, path = parse_serve_endpoint("live", cfg)
    assert url == "rtsp://127.0.0.1:8554/live"
    assert host == "127.0.0.1"
    assert port == 8554
    assert path == "live"


def test_full_rtsp_url() -> None:
    cfg = StreamConfig()
    url, host, port, path = parse_serve_endpoint("rtsp://192.168.1.10:8554/cam1", cfg)
    assert url == "rtsp://192.168.1.10:8554/cam1"
    assert host == "192.168.1.10"
    assert port == 8554
    assert path == "cam1"


def test_rtsp_url_preserves_credentials() -> None:
    d = parse_publish_destination("rtsp://user:secret@192.168.1.10:8554/live", StreamConfig())
    assert "user:secret@" in d.url
    assert d.scheme == "rtsp"


def test_rtsp_url_preserves_multi_segment_path() -> None:
    d = parse_publish_destination("rtsp://192.168.1.10:8554/foo/bar", StreamConfig())
    assert d.url == "rtsp://192.168.1.10:8554/foo/bar"
    assert d.path_name == "bar"


def test_srt_url() -> None:
    d = parse_publish_destination("srt://127.0.0.1:9000?mode=listener", StreamConfig())
    assert d.scheme == "srt"
    assert d.port == 9000
    assert d.url.startswith("srt://")


def test_unsupported_scheme() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported"):
        parse_publish_destination("http://example.com/x", StreamConfig())


def test_loopback() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("192.168.0.1")
