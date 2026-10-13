"""CLI smoke tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from easy_rtsp.cli import _print_play_url, main


def test_doctor_exits_zero() -> None:
    assert main(["doctor"]) == 0


def test_relay_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["relay", "--help"])
    assert exc.value.code == 0


def test_webcam_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["webcam", "--help"])
    assert exc.value.code == 0


def test_file_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["file", "--help"])
    assert exc.value.code == 0


def test_install_backends_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["install-backends", "--help"])
    assert exc.value.code == 0


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "easy-rtsp" in capsys.readouterr().out


def test_cli_prints_clean_error_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["relay", "http://not-rtsp"]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_print_play_url_includes_lan_urls_and_firewall_ports(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = SimpleNamespace(
        viewer_url="rtsp://127.0.0.1:9554/live",
        webrtc_play_url="http://127.0.0.1:9999/live",
        lan_viewer_urls=("rtsp://192.168.1.42:9554/live",),
        lan_webrtc_play_urls=("http://192.168.1.42:9999/live",),
        config=SimpleNamespace(webrtc_http_port=9999),
    )
    _print_play_url(stream)
    captured = capsys.readouterr()
    assert "LAN: rtsp://192.168.1.42:9554/live" in captured.out
    assert "LAN WebRTC: http://192.168.1.42:9999/live" in captured.out
    assert "TCP 9554" in captured.err
    assert "TCP 9999" in captured.err


def test_file_missing_path_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["file", "nonexistent-file-12345.mp4", "--serve", "live"])
    assert code == 2
    err = capsys.readouterr().err
    assert "not a file" in err


def test_print_play_url_redacts_publish_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = SimpleNamespace(
        viewer_url="rtsp://publisher:topsecret@192.168.1.50:8554/live",
        webrtc_play_url=None,
        lan_viewer_urls=(),
        lan_webrtc_play_urls=(),
    )
    _print_play_url(stream)
    captured = capsys.readouterr()
    assert "topsecret" not in captured.out
    assert "Play: rtsp://publisher:***@192.168.1.50:8554/live" in captured.out
