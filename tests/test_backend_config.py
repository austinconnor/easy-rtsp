"""Generated MediaMTX config (WebRTC, RTSP)."""

from __future__ import annotations

import socket
from pathlib import Path

from easy_rtsp.backend import (
    discover_lan_hosts,
    tcp_port_is_available,
    wait_for_tcp_listener,
    write_minimal_mediamtx_config,
)


def test_mediamtx_config_includes_webrtc(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "live", 8554, webrtc_enabled=True, webrtc_http_port=8889)
    text = p.read_text(encoding="utf-8")
    assert "webrtc: true" in text
    assert "webrtcAddress: 127.0.0.1:8889" in text
    assert "webrtcIPsFromInterfaces: false" in text
    assert "webrtcLocalTCPAddress: 127.0.0.1:8189" in text
    assert "webrtcAdditionalHosts:" in text
    assert "127.0.0.1" in text
    assert "webrtcICEServers2: []" in text
    assert "paths:" in text
    assert '"live":' in text


def test_mediamtx_config_can_disable_webrtc(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "live", 8554, webrtc_enabled=False)
    text = p.read_text(encoding="utf-8")
    assert "webrtc: false" in text


def test_mediamtx_path_is_quoted_as_yaml(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "folder/camera: one", 8554)
    text = p.read_text(encoding="utf-8")
    assert '  "folder/camera: one":' in text


def test_mediamtx_config_is_loopback_only_and_disables_unused_protocols(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "live", 8554)
    text = p.read_text(encoding="utf-8")
    assert "rtspAddress: 127.0.0.1:8554" in text
    assert "rtspTransports: [tcp]" in text
    assert "rtmp: false" in text
    assert "hls: false" in text
    assert "srt: false" in text


def test_mediamtx_lan_config_binds_all_interfaces(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(
        p, "live", 8554, lan_access=True, webrtc_enabled=True
    )
    text = p.read_text(encoding="utf-8")
    assert "rtspAddress: :8554" in text
    assert "webrtcAddress: :8889" in text


def test_discover_lan_hosts_filters_unusable_addresses(monkeypatch) -> None:
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _timeout):
            return None

        def connect(self, _address):
            return None

        def getsockname(self):
            return ("192.168.1.20", 12345)

    monkeypatch.setattr(socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(socket, "gethostname", lambda: "host")
    monkeypatch.setattr(
        socket,
        "gethostbyname_ex",
        lambda _host: ("host", [], ["127.0.0.1", "169.254.1.2", "10.0.0.4"]),
    )
    assert discover_lan_hosts() == ["192.168.1.20", "10.0.0.4"]


def test_wait_for_tcp_listener_checks_real_readiness() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert wait_for_tcp_listener("127.0.0.1", port, timeout=0.1)

    assert not wait_for_tcp_listener("127.0.0.1", port, timeout=0.0)


def test_tcp_port_is_available_detects_wildcard_listener() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("0.0.0.0", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert not tcp_port_is_available("127.0.0.1", port)


def test_mediamtx_config_quotes_ipv6_and_uses_custom_ice_port(tmp_path: Path) -> None:
    p = tmp_path / "mtx_ipv6.yml"
    write_minimal_mediamtx_config(
        p,
        "live",
        8554,
        listen_host="::1",
        webrtc_enabled=True,
        webrtc_http_port=8889,
        webrtc_ice_port=8190,
    )
    text = p.read_text(encoding="utf-8")
    assert 'rtspAddress: "[::1]:8554"' in text
    assert 'webrtcAddress: "[::1]:8889"' in text
    assert 'webrtcLocalUDPAddress: "[::1]:8190"' in text
    assert 'webrtcLocalTCPAddress: "[::1]:8190"' in text
    assert '"::1"' in text
