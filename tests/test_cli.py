"""CLI smoke tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.cli import (
    _config_kwargs_from_args,
    _print_play_urls,
    _wait_for_stream,
    build_parser,
    main,
)
from easy_rtsp.exceptions import DependencyError


def _fake_stream(**overrides) -> SimpleNamespace:
    values = dict(
        viewer_url="rtsp://127.0.0.1:8554/live",
        webrtc_play_url=None,
        lan_viewer_urls=(),
        lan_webrtc_play_urls=(),
        config=SimpleNamespace(server_port=8554, webrtc_http_port=8889, webrtc_ice_port=8189),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_doctor_exits_zero_when_ffmpeg_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("easy_rtsp.ffmpeg_util.resolve_ffmpeg", return_value="/bin/ffmpeg"),
        patch("easy_rtsp.ffmpeg_util.resolve_ffprobe", return_value="/bin/ffprobe"),
        patch("easy_rtsp.ffmpeg_util.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.cli._first_output_line", return_value="ffmpeg version 7.1"),
    ):
        assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "/bin/ffmpeg (ffmpeg version 7.1)" in out
    assert "install-backends" in out


def test_doctor_exits_nonzero_when_ffmpeg_is_missing(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("easy_rtsp.ffmpeg_util.resolve_ffmpeg", side_effect=DependencyError("no ffmpeg")),
        patch("easy_rtsp.ffmpeg_util.resolve_ffprobe", return_value="/bin/ffprobe"),
        patch("easy_rtsp.ffmpeg_util.resolve_mediamtx", return_value=None),
        patch("easy_rtsp.cli._first_output_line", return_value=None),
    ):
        assert main(["doctor"]) == 1
    assert "MISSING (no ffmpeg)" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["relay", "webcam", "file", "install-backends"])
def test_subcommand_help_exits_zero(command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "easy-rtsp" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--transport=udp", "--no-reconnect", "--audio-mode=passthrough"])
def test_relay_only_flags_are_rejected_for_other_sources(flag: str) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["webcam", "0", flag])
    assert exc.value.code == 2


def test_relay_flags_map_to_stream_config() -> None:
    args = build_parser().parse_args(
        [
            "relay",
            "rtsp://cam/live",
            "--transport=udp",
            "--latency-ms=200",
            "--max-reconnect-attempts=3",
            "--no-reconnect",
            "--audio-mode=passthrough",
            "--record=out.mp4",
            "--fps=12.5",
            "--lan",
            "--webrtc",
        ]
    )
    kwargs = _config_kwargs_from_args(args)

    assert kwargs["transport"] == "udp"
    assert kwargs["latency_ms"] == 200
    assert kwargs["max_reconnect_attempts"] == 3
    assert kwargs["reconnect"] is False
    assert kwargs["audio_mode"] == "passthrough"
    assert kwargs["record_path"] == "out.mp4"
    assert kwargs["fps"] == 12.5
    assert kwargs["lan_access"] is True
    assert kwargs["webrtc_enabled"] is True
    assert "input_realtime_pace" not in kwargs


def test_file_flags_map_to_stream_config() -> None:
    args = build_parser().parse_args(["file", "clip.mp4", "--no-loop", "--no-realtime"])
    kwargs = _config_kwargs_from_args(args)

    assert kwargs["file_loop"] is False
    assert kwargs["input_realtime_pace"] is False
    assert "transport" not in kwargs


def test_cli_prints_clean_error_without_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["relay", "http://not-rtsp"]) == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err


def test_cli_redacts_credentials_in_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["relay", "rtsp://user:hunter2@"]) == 1
    err = capsys.readouterr().err
    assert "hunter2" not in err


def test_file_missing_path_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["file", "nonexistent-file-12345.mp4", "--serve", "live"])
    assert code == 2
    assert "not a file" in capsys.readouterr().err


def test_ctrl_c_during_startup_exits_130() -> None:
    with patch("easy_rtsp.cli.cmd_doctor", side_effect=KeyboardInterrupt):
        assert main(["doctor"]) == 130


def test_wait_for_stream_stops_on_ctrl_c(capsys: pytest.CaptureFixture[str]) -> None:
    stream = MagicMock(**{"wait.side_effect": KeyboardInterrupt})
    stream.viewer_url = None
    stream.status.return_value = SimpleNamespace(has_publish_error=False, publish_error=None)

    assert _wait_for_stream(stream) == 0
    stream.stop.assert_called_once()
    assert "stopping" in capsys.readouterr().err


def test_wait_for_stream_reports_publish_errors(capsys: pytest.CaptureFixture[str]) -> None:
    stream = MagicMock()
    stream.viewer_url = None
    stream.status.return_value = SimpleNamespace(has_publish_error=True, publish_error="boom")

    assert _wait_for_stream(stream) == 1
    stream.stop.assert_called_once()
    assert "error: boom" in capsys.readouterr().err


def test_print_play_urls_includes_lan_urls_and_firewall_ports(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = _fake_stream(
        viewer_url="rtsp://127.0.0.1:9554/live",
        webrtc_play_url="http://127.0.0.1:9999/live",
        lan_viewer_urls=("rtsp://192.168.1.42:9554/live",),
        lan_webrtc_play_urls=("http://192.168.1.42:9999/live",),
        config=SimpleNamespace(server_port=9554, webrtc_http_port=9999, webrtc_ice_port=9189),
    )
    _print_play_urls(stream)  # type: ignore[arg-type]
    captured = capsys.readouterr()
    assert "WebRTC: http://127.0.0.1:9999/live" in captured.out
    assert "LAN: rtsp://192.168.1.42:9554/live" in captured.out
    assert "LAN WebRTC: http://192.168.1.42:9999/live" in captured.out
    assert "TCP 9554" in captured.err
    assert "TCP 9999" in captured.err
    assert "UDP/TCP 9189" in captured.err


def test_print_play_urls_labels_tcp_fallback(capsys: pytest.CaptureFixture[str]) -> None:
    _print_play_urls(_fake_stream(viewer_url="tcp://127.0.0.1:8554"))  # type: ignore[arg-type]
    assert "Play (TCP/MPEG-TS): tcp://127.0.0.1:8554" in capsys.readouterr().out


def test_print_play_urls_redacts_publish_credentials(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stream = _fake_stream(viewer_url="rtsp://publisher:topsecret@192.168.1.50:8554/live")
    _print_play_urls(stream)  # type: ignore[arg-type]
    captured = capsys.readouterr()
    assert "topsecret" not in captured.out
    assert "Play: rtsp://publisher:***@192.168.1.50:8554/live" in captured.out
