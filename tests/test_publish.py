"""Publish / FFmpeg command construction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.publish import build_raw_publish_ffmpeg_cmd, run_publish_loop


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
    joined = "|".join(cmd)
    assert "rtsp://" in joined
    assert "index.m3u8" in joined


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


def test_run_publish_loop_tcp_listen() -> None:
    holder: list[object] = []
    with (
        patch("easy_rtsp.publish.subprocess.Popen") as p,
        patch("easy_rtsp.publish.resolve_ffmpeg", return_value="/bin/ffmpeg"),
    ):
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = None
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
        mock_proc.stderr = None
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
