"""Tests for serve URL parsing."""

import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError
from easy_rtsp.serve_url import (
    build_rtsp_url,
    is_loopback_host,
    parse_publish_destination,
    parse_serve_endpoint,
    redact_credentials_in_text,
    redact_url_credentials,
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


def test_full_rtsp_url_uses_protocol_default_port() -> None:
    d = parse_publish_destination("rtsp://192.168.1.10/live", StreamConfig(server_port=8554))
    assert d.port == 554


def test_full_rtsps_url_uses_secure_default_port() -> None:
    d = parse_publish_destination("rtsps://192.168.1.10/live", StreamConfig())
    assert d.port == 322


def test_rtsp_url_preserves_credentials() -> None:
    d = parse_publish_destination("rtsp://user:secret@192.168.1.10:8554/live", StreamConfig())
    assert "user:secret@" in d.url
    assert d.scheme == "rtsp"


def test_build_rtsp_url_encodes_credentials_safely() -> None:
    url = build_rtsp_url(
        "192.168.1.10",
        "cam 1",
        port=8554,
        username="user name",
        password="p@ss:word",
    )
    assert url == "rtsp://user%20name:p%40ss%3Aword@192.168.1.10:8554/cam%201"


def test_build_rtsps_url_uses_secure_scheme() -> None:
    url = build_rtsp_url("example.com", "live", port=322, secure=True)
    assert url == "rtsps://example.com:322/live"


def test_rtsp_url_preserves_multi_segment_path() -> None:
    d = parse_publish_destination("rtsp://192.168.1.10:8554/foo/bar", StreamConfig())
    assert d.url == "rtsp://192.168.1.10:8554/foo/bar"
    assert d.path_name == "foo/bar"


def test_rtsp_url_preserves_query_and_fragment() -> None:
    d = parse_publish_destination("rtsp://camera/live?token=abc#view", StreamConfig())
    assert d.url == "rtsp://camera/live?token=abc#view"


def test_ipv6_hosts_are_bracketed_in_built_urls() -> None:
    assert build_rtsp_url("::1", "live") == "rtsp://[::1]:8554/live"
    d = parse_publish_destination("live", StreamConfig(server_host="::1"))
    assert d.url == "rtsp://[::1]:8554/live"
    assert is_loopback_host("[::1]")


def test_shorthand_path_is_url_encoded() -> None:
    d = parse_publish_destination("camera one/live feed", StreamConfig())
    assert d.url.endswith("/camera%20one/live%20feed")


def test_invalid_url_port_has_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="port"):
        parse_publish_destination("rtsp://camera:not-a-port/live", StreamConfig())


def test_malformed_ipv6_url_has_configuration_error() -> None:
    with pytest.raises(ConfigurationError, match="Invalid publish URL"):
        parse_publish_destination("rtsp://[::1/live", StreamConfig())


def test_password_redaction() -> None:
    assert (
        redact_url_credentials("rtsp://user:secret@camera/live?token=ok")
        == "rtsp://user:***@camera/live?token=ok"
    )


def test_srt_url() -> None:
    d = parse_publish_destination("srt://127.0.0.1:9000?mode=listener", StreamConfig())
    assert d.scheme == "srt"
    assert d.port == 9000
    assert d.url.startswith("srt://")


def test_srt_url_adds_default_port() -> None:
    d = parse_publish_destination("srt://stream.example/live?mode=caller", StreamConfig())
    assert d.port == 9000
    assert d.url == "srt://stream.example:9000/live?mode=caller"


def test_srt_url_requires_host() -> None:
    with pytest.raises(ConfigurationError, match="must include a host"):
        parse_publish_destination("srt:///stream", StreamConfig())


def test_unsupported_scheme() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported"):
        parse_publish_destination("http://example.com/x", StreamConfig())


def test_loopback() -> None:
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("127.0.0.2")
    assert is_loopback_host("localhost")
    assert not is_loopback_host("192.168.0.1")


def test_build_rtsp_url_preserves_query_parameters() -> None:
    url = build_rtsp_url(
        "192.168.1.10",
        "cam/realmonitor?channel=1&subtype=0",
        username="admin",
        password="secret",
    )
    assert url == "rtsp://admin:secret@192.168.1.10:8554/cam/realmonitor?channel=1&subtype=0"


def test_rtsp_url_requires_hostname_even_with_userinfo() -> None:
    with pytest.raises(ConfigurationError, match="must include a host"):
        parse_publish_destination("rtsp://user:pass@/live", StreamConfig())


def test_redact_credentials_in_freeform_text() -> None:
    msg = "Failed to open rtsp://admin:my_secret_pw@10.0.0.5:554/stream1 (401)"
    redacted = redact_credentials_in_text(msg)
    assert "my_secret_pw" not in redacted
    assert "rtsp://admin:***@10.0.0.5:554/stream1" in redacted
