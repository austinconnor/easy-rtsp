"""Encode BGR frames and publish (FFmpeg -> RTSP, SRT, or TCP/MPEG-TS)."""

from __future__ import annotations

import errno
import subprocess
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import PublishError
from easy_rtsp.ffmpeg_util import resolve_ffmpeg
from easy_rtsp.log import get_logger
from easy_rtsp.process_io import discard_process

_plog = get_logger("publish")


def _resolved_input_pace(config: StreamConfig) -> bool:
    """
    Whether to pass FFmpeg ``-re`` so raw input is read at ``-r`` fps (wall clock).

    Default ``True`` when unset: smooth pacing for webcam/relay (avoids bursty pipe reads).
    Set ``input_realtime_pace=False`` to minimize latency at the cost of possible jitter.
    """
    if config.input_realtime_pace is None:
        return True
    return config.input_realtime_pace


def _resolve_video_encoder(config: StreamConfig) -> str:
    if config.video_encoder:
        return config.video_encoder
    c = config.codec.lower()
    if c in ("h264", "avc", "libx264"):
        return "libx264"
    return config.codec


def _preset_libx264_args(preset_name: str) -> list[str]:
    name = (preset_name or "default").lower()
    if name == "low_latency":
        return ["-preset", "ultrafast", "-tune", "zerolatency"]
    if name == "quality":
        return ["-preset", "medium"]
    return ["-preset", "veryfast", "-tune", "zerolatency"]


def _libx264_gop_and_bframes(fps: float) -> list[str]:
    """Short GOP and no B-frames so decoders can show frames sooner."""
    gop = max(1, int(round(fps)))
    kmin = max(1, gop // 2)
    return ["-bf", "0", "-g", str(gop), "-keyint_min", str(kmin)]


def _encoder_quality_args(config: StreamConfig, fps: float) -> list[str]:
    enc = _resolve_video_encoder(config).lower()
    if enc in ("libx264", "h264", "avc"):
        # Baseline profile + no B-frames: required for reliable WebRTC playback in browsers.
        return (
            _preset_libx264_args(config.preset)
            + ["-profile:v", "baseline"]
            + _libx264_gop_and_bframes(fps)
        )
    if enc in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
        return ["-preset", "p4", "-tune", "ll"]
    if enc in ("h264_qsv", "hevc_qsv", "av1_qsv"):
        return ["-preset", "veryfast"]
    if enc in ("h264_amf", "hevc_amf"):
        return ["-quality", "speed"]
    return []


def _norm_fs_path(p: str) -> str:
    return str(Path(p).expanduser().resolve()).replace("\\", "/")


def _build_tee_spec(rtsp_url: str, config: StreamConfig) -> str:
    parts: list[str] = [f"[f=rtsp:rtsp_transport=tcp]{rtsp_url}"]
    if config.record_path:
        parts.append(f"[f=mp4]{_norm_fs_path(config.record_path)}")
    if config.hls_output_dir:
        playlist = Path(config.hls_output_dir).expanduser() / "index.m3u8"
        st = float(config.hls_segment_time)
        parts.append(
            f"[f=hls:hls_time={st}:hls_list_size=0:hls_flags=delete_segments]"
            f"{_norm_fs_path(str(playlist))}"
        )
    return "|".join(parts)


def _raw_input_chain(
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
) -> list[str]:
    vcodec = _resolve_video_encoder(config)
    pace = _resolved_input_pace(config)
    latency_tail = _encoder_quality_args(config, fps)
    out: list[str] = [
        "-loglevel",
        "warning",
        *(["-re"] if pace else []),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        *latency_tail,
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        vcodec,
    ]
    if config.bitrate:
        out += ["-b:v", config.bitrate]
    out += list(config.extra_ffmpeg_output_args)
    return out


def build_raw_publish_ffmpeg_cmd(
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> list[str]:
    """
    FFmpeg argv after the binary.

    Exactly one of *rtsp_push_url*, *srt_push_url*, or *tcp_listen* must be provided.
    """
    if width <= 0 or height <= 0:
        raise PublishError("width and height must be positive for publishing")
    if fps <= 0:
        raise PublishError("fps must be positive for publishing")
    n_dest = sum(
        1 for x in (rtsp_push_url, srt_push_url, tcp_listen) if x is not None
    )
    if n_dest != 1:
        raise PublishError("internal: specify exactly one of rtsp_push_url, srt_push_url, tcp_listen")

    wants_side = bool(config.record_path or config.hls_output_dir)
    if wants_side:
        if tcp_listen is not None or srt_push_url is not None:
            raise PublishError(
                "record_path and hls_output_dir require RTSP push (tee muxer); "
                "not compatible with SRT-only or TCP MPEG-TS listen mode."
            )
        if rtsp_push_url is None:
            raise PublishError("internal: RTSP URL missing for tee outputs")

    base = _raw_input_chain(width=width, height=height, fps=fps, config=config)
    mux = ["-muxdelay", "0", "-muxpreload", "0"]

    if tcp_listen is not None:
        host, port = tcp_listen
        dest = f"tcp://{host}:{port}?listen=1"
        return base + mux + ["-f", "mpegts", dest]

    if srt_push_url is not None:
        # MPEG-TS over SRT is widely supported by FFmpeg.
        return base + mux + ["-f", "mpegts", srt_push_url]

    assert rtsp_push_url is not None
    if wants_side:
        tee_arg = _build_tee_spec(rtsp_push_url, config)
        return base + ["-f", "tee", tee_arg]
    return base + mux + ["-f", "rtsp", "-rtsp_transport", "tcp", rtsp_push_url]


def run_publish_loop(
    frame_iter: Iterator[np.ndarray],
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None = None,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> None:
    """Blocking: encode frames from *frame_iter* and send to RTSP, SRT, or TCP listen."""
    resolve_ffmpeg()
    cmd = build_raw_publish_ffmpeg_cmd(
        width=width,
        height=height,
        fps=fps,
        config=config,
        rtsp_push_url=rtsp_push_url,
        srt_push_url=srt_push_url,
        tcp_listen=tcp_listen,
    )
    ffmpeg = resolve_ffmpeg()
    proc: subprocess.Popen[bytes] | None = None
    try:
        proc = subprocess.Popen(
            [ffmpeg, *cmd],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            # Never PIPE stderr without draining during the loop — FFmpeg can fill the buffer and
            # block forever, leaking RAM and leaving a zombie child after Ctrl+C.
            stderr=subprocess.DEVNULL,
        )
        if proc_holder is not None:
            proc_holder.append(proc)
        assert proc.stdin is not None
        if tcp_listen is not None:
            _plog.info("TCP MPEG-TS listen on tcp://%s:%s (connect a viewer)", tcp_listen[0], tcp_listen[1])
        if srt_push_url is not None:
            _plog.info("Publishing MPEG-TS to SRT %s", srt_push_url)
        for frame in frame_iter:
            if frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                raise PublishError(
                    f"Each frame must be uint8 HWC BGR shaped {(height, width, 3)}, "
                    f"got {frame.dtype} {frame.shape}"
                )
            proc.stdin.write(frame.tobytes())
            proc.stdin.flush()
        proc.stdin.close()
        code = proc.wait(timeout=120)
        if code != 0:
            raise PublishError(f"ffmpeg publisher exited with code {code}")
    except BrokenPipeError:
        pass
    except OSError as e:
        # Encoder stopped (stop() or viewer disconnect): EPIPE, or Windows winerror 232 / 109.
        if e.errno in (errno.EPIPE, errno.ECONNRESET):
            pass
        elif getattr(e, "winerror", None) in (232, 109):
            pass
        elif e.errno == 232:
            pass
        else:
            raise
    except PublishError:
        raise
    finally:
        if proc is not None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass
            discard_process(proc_holder, proc)


def start_publish_thread(
    frame_iter_factory: Callable[[], Iterator[np.ndarray]],
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None,
    on_done: Callable[[BaseException | None], None],
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> threading.Thread:
    """Run :func:`run_publish_loop` in a daemon thread."""

    def _run() -> None:
        err: BaseException | None = None
        try:
            run_publish_loop(
                frame_iter_factory(),
                width=width,
                height=height,
                fps=fps,
                config=config,
                proc_holder=proc_holder,
                rtsp_push_url=rtsp_push_url,
                srt_push_url=srt_push_url,
                tcp_listen=tcp_listen,
            )
        except BaseException as e:
            err = e
        finally:
            on_done(err)

    t = threading.Thread(target=_run, name="easy-rtsp-publish", daemon=True)
    t.start()
    return t
