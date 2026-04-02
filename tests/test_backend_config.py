"""Generated MediaMTX config (WebRTC, RTSP)."""

from __future__ import annotations

from pathlib import Path

from easy_rtsp.backend import write_minimal_mediamtx_config


def test_mediamtx_config_includes_webrtc(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "live", 8554, webrtc_enabled=True, webrtc_http_port=8889)
    text = p.read_text(encoding="utf-8")
    assert "webrtc: true" in text
    assert "webrtcAddress: :8889" in text
    assert "webrtcIPsFromInterfaces: false" in text
    assert "webrtcLocalTCPAddress: :8189" in text
    assert "webrtcAdditionalHosts:" in text
    assert "127.0.0.1" in text
    assert "webrtcICEServers2: []" in text
    assert "paths:" in text
    assert "live:" in text


def test_mediamtx_config_can_disable_webrtc(tmp_path: Path) -> None:
    p = tmp_path / "mtx.yml"
    write_minimal_mediamtx_config(p, "live", 8554, webrtc_enabled=False)
    text = p.read_text(encoding="utf-8")
    assert "webrtc: false" in text
