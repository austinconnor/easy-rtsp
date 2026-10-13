"""Publish / FFmpeg command construction."""

from __future__ import annotations

import threading
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import PublishError
from easy_rtsp.publish import (
    build_raw_publish_ffmpeg_cmd,
    build_rtsp_passthrough_ffmpeg_cmd,
    run_publish_loop,
    run_rtsp_passthrough_loop,
)


def test_build_rtsp_push_cmd() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(),
        rtsp_push_url="rtsp://127.0.0.1:8554/live",
    )
    assert "-f" in cmd
    assert "rtsp" in cmd
    assert cmd[-1] == "rtsp://127.0.0.1:8554/live"
    assert "mpegts" not in cmd
    assert "-re" in cmd
    assert "-muxdelay" in cmd
    assert cmd[cmd.index("-bf") + 1] == "0"


def test_build_rtsp_push_cmd_burst_mode_no_re() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(input_realtime_pace=False),
        rtsp_push_url="rtsp://127.0.0.1:8554/live",
    )
    assert "-re" not in cmd


def test_build_tcp_mpegts_listen_cmd() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(),
        tcp_listen=("127.0.0.1", 8554),
    )
    assert "-f" in cmd
    assert "mpegts" in cmd
    assert any("tcp://" in x and "listen=1" in x for x in cmd)


def test_build_rejects_both_destinations() -> None:
    from easy_rtsp.exceptions import PublishError

    with pytest.raises(PublishError, match="exactly one"):
        build_raw_publish_ffmpeg_cmd(
            width=64,
            height=48,
            fps=1.0,
            config=StreamConfig(),
            rtsp_push_url="rtsp://x/x",
            tcp_listen=("127.0.0.1", 9),
        )


def test_build_rejects_no_destination() -> None:
    from easy_rtsp.exceptions import PublishError

    with pytest.raises(PublishError, match="exactly one"):
        build_raw_publish_ffmpeg_cmd(
            width=64,
            height=48,
            fps=1.0,
            config=StreamConfig(),
        )


def test_build_srt_push_cmd() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(),
        srt_push_url="srt://127.0.0.1:9000?mode=listener",
    )
    assert "mpegts" in cmd
    assert cmd[-1].startswith("srt://")


def test_build_tee_record_and_hls(tmp_path) -> None:
    mp4 = tmp_path / "out.mp4"
    hls = tmp_path / "hls"
    hls.mkdir()
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(record_path=str(mp4), hls_output_dir=str(hls)),
        rtsp_push_url="rtsp://127.0.0.1:8554/live",
    )
    assert "-f" in cmd
    assert "tee" in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    joined = "|".join(cmd)
    assert "rtsp://" in joined
    assert "index.m3u8" in joined


def test_build_tee_escapes_special_output_path(tmp_path) -> None:
    output = tmp_path / "record | camera's view.mp4"
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(record_path=str(output)),
        rtsp_push_url="rtsp://127.0.0.1:8554/live",
    )
    tee_spec = cmd[-1]
    assert "record | camera" in tee_spec
    assert "'\\''" in tee_spec


def test_build_rejects_tee_with_tcp_listen(tmp_path) -> None:
    from easy_rtsp.exceptions import PublishError

    with pytest.raises(PublishError, match="tee"):
        build_raw_publish_ffmpeg_cmd(
            width=64,
            height=48,
            fps=1.0,
            config=StreamConfig(record_path=str(tmp_path / "x.mp4")),
            tcp_listen=("127.0.0.1", 9),
        )


def test_build_nvenc_encoder_flag() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=64,
        height=48,
        fps=30.0,
        config=StreamConfig(video_encoder="h264_nvenc"),
        rtsp_push_url="rtsp://127.0.0.1:9/x",
    )
    assert cmd[cmd.index("-c:v") + 1] == "h264_nvenc"
    assert "-bf" not in cmd


def test_build_rtsp_passthrough_cmd() -> None:
    cmd = build_rtsp_passthrough_ffmpeg_cmd(
        source_url="rtsp://camera/live",
        config=StreamConfig(audio_mode="passthrough"),
        rtsp_push_url="rtsp://127.0.0.1:8554/live",
    )
    assert cmd[cmd.index("-i") + 1] == "rtsp://camera/live"
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    assert "pipe:0" not in cmd


def test_build_rtsp_passthrough_tcp_listen_cmd() -> None:
    cmd = build_rtsp_passthrough_ffmpeg_cmd(
        source_url="rtsp://camera/live",
        config=StreamConfig(audio_mode="passthrough"),
        tcp_listen=("127.0.0.1", 8554),
    )
    assert "mpegts" in cmd
    assert any("tcp://" in x and "listen=1" in x for x in cmd)


def test_passthrough_rejects_side_output_with_srt(tmp_path) -> None:
    with pytest.raises(PublishError, match="require RTSP push"):
        build_rtsp_passthrough_ffmpeg_cmd(
            source_url="rtsp://camera/live",
            config=StreamConfig(
                audio_mode="passthrough",
                record_path=str(tmp_path / "out.mp4"),
            ),
            srt_push_url="srt://127.0.0.1:9000",
        )


def test_build_tcp_mpegts_brackets_ipv6() -> None:
    cmd = build_raw_publish_ffmpeg_cmd(
        width=640,
        height=480,
        fps=30.0,
        config=StreamConfig(),
        tcp_listen=("::1", 8554),
    )
    assert cmd[-1] == "tcp://[::1]:8554?listen=1"


def test_run_publish_loop_tcp_listen() -> None:
    holder: list[object] = []
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = BytesIO(b"")
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        p.return_value = mock_proc

        run_publish_loop(
            iter([]),
            width=64,
            height=48,
            fps=1.0,
            config=StreamConfig(),
            proc_holder=holder,
            tcp_listen=("127.0.0.1", 9),
        )
        args = p.call_args[0][0]
        assert "mpegts" in args
        assert any("tcp://" in a and "listen=1" in a for a in args)
    assert holder == []


def test_run_publish_loop_rtsp_push() -> None:
    holder: list[object] = []
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = BytesIO(b"")
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        p.return_value = mock_proc

        run_publish_loop(
            iter([]),
            width=64,
            height=48,
            fps=1.0,
            config=StreamConfig(),
            proc_holder=holder,
            rtsp_push_url="rtsp://127.0.0.1:9/x",
        )
        args = p.call_args[0][0]
        assert "rtsp" in args
        assert args[-1] == "rtsp://127.0.0.1:9/x"
    assert holder == []


def test_run_rtsp_passthrough_loop_rtsp_push() -> None:
    holder: list[object] = []
    stop_event = MagicMock()
    stop_event.is_set.return_value = False
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stderr = BytesIO(b"")
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        p.return_value = mock_proc

        run_rtsp_passthrough_loop(
            "rtsp://camera/live",
            config=StreamConfig(audio_mode="passthrough", reconnect=False),
            proc_holder=holder,
            stop_event=stop_event,
            rtsp_push_url="rtsp://127.0.0.1:9/x",
        )
        args = p.call_args[0][0]
        assert args[-1] == "rtsp://127.0.0.1:9/x"
    assert holder == []


def test_publish_failure_includes_ffmpeg_diagnostics() -> None:
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = BytesIO(b"unknown encoder h264_missing")
        mock_proc.poll.return_value = 1
        mock_proc.wait.return_value = 1
        p.return_value = mock_proc

        with pytest.raises(PublishError, match="unknown encoder h264_missing"):
            run_publish_loop(
                iter([]),
                width=64,
                height=48,
                fps=1.0,
                config=StreamConfig(),
                rtsp_push_url="rtsp://127.0.0.1:9/x",
            )


def test_publish_broken_pipe_after_first_frame_raises_publish_error() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.write.side_effect = [None, BrokenPipeError("broken pipe")]
        mock_proc.stderr = BytesIO(
            b"rtsp://user:secret@127.0.0.1:8554/live: 401 Unauthorized"
        )
        mock_proc.poll.return_value = 1
        mock_proc.wait.return_value = 1
        p.return_value = mock_proc

        with pytest.raises(PublishError) as exc:
            run_publish_loop(
                iter([frame, frame]),
                width=64,
                height=48,
                fps=10.0,
                config=StreamConfig(),
                rtsp_push_url="rtsp://user:secret@127.0.0.1:8554/live",
            )

    assert "401 Unauthorized" in str(exc.value)
    assert "secret" not in str(exc.value)
    assert "user:***@127.0.0.1" in str(exc.value)


def test_publish_broken_pipe_ignored_when_stop_event_is_set() -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    stop_event = threading.Event()
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()

        def write_and_stop(_data: bytes) -> None:
            stop_event.set()
            raise BrokenPipeError("stopped")

        mock_proc.stdin.write.side_effect = write_and_stop
        mock_proc.stderr = BytesIO(b"Exiting")
        mock_proc.poll.return_value = 1
        mock_proc.wait.return_value = 1
        p.return_value = mock_proc

        run_publish_loop(
            iter([frame]),
            width=64,
            height=48,
            fps=10.0,
            config=StreamConfig(),
            stop_event=stop_event,
            rtsp_push_url="rtsp://127.0.0.1:8554/live",
        )


def test_run_publish_loop_adapts_to_resized_first_frame() -> None:
    resized = np.zeros((24, 32, 3), dtype=np.uint8)
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = BytesIO(b"")
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        p.return_value = mock_proc

        run_publish_loop(
            iter([resized]),
            width=64,
            height=48,
            fps=10.0,
            config=StreamConfig(),
            rtsp_push_url="rtsp://127.0.0.1:8554/live",
        )
        args = p.call_args[0][0]
        assert args[args.index("-s") + 1] == "32x24"
