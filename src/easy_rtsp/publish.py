"""Encode BGR frames and publish (FFmpeg -> RTSP, SRT, or TCP/MPEG-TS)."""

from __future__ import annotations

import errno
import itertools
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import PublishError
from easy_rtsp.ffmpeg_util import ffmpeg_ingest_rtsp_args, resolve_ffmpeg
from easy_rtsp.log import get_logger
from easy_rtsp.process_io import (
    decode_tail_bytes,
    discard_process,
    start_tail_reader,
    terminate_process,
)
from easy_rtsp.serve_url import format_url_host, redact_credentials_in_text, redact_url_credentials

_plog = get_logger("publish")

_ENCODER_DRAIN_TIMEOUT_SEC = 120.0
# Exit codes after the encoder was stopped from outside: clean, SIGTERM, or FFmpeg's "interrupted".
_ENCODER_STOPPED_CODES = (0, -15, 255)
_STOP_POLL_SEC = 0.2
_QUIT_GRACE_SEC = 1.5


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
    gop = max(1, round(fps))
    kmin = max(1, gop // 2)
    return ["-bf", "0", "-g", str(gop), "-keyint_min", str(kmin)]


def _encoder_quality_args(config: StreamConfig, fps: float) -> list[str]:
    enc = _resolve_video_encoder(config).lower()
    if enc in ("libx264", "h264", "avc"):
        # Baseline profile + no B-frames: required for reliable WebRTC playback in browsers.
        return [
            *_preset_libx264_args(config.preset),
            "-profile:v",
            "baseline",
            *_libx264_gop_and_bframes(fps),
        ]
    if enc in ("h264_nvenc", "hevc_nvenc", "av1_nvenc"):
        return ["-preset", "p4", "-tune", "ll"]
    if enc in ("h264_qsv", "hevc_qsv", "av1_qsv"):
        return ["-preset", "veryfast"]
    if enc in ("h264_amf", "hevc_amf"):
        return ["-quality", "speed"]
    return []


def _norm_fs_path(p: str) -> str:
    return str(Path(p).expanduser().resolve()).replace("\\", "/")


def _escape_tee_slave(value: str) -> str:
    """Escape a tee slave name for FFmpeg's own parser (the command does not use a shell)."""
    return "'" + value.replace("'", "'\\''") + "'"


def _build_tee_spec(rtsp_url: str, config: StreamConfig) -> str:
    parts: list[str] = [f"[f=rtsp:rtsp_transport=tcp]{_escape_tee_slave(rtsp_url)}"]
    if config.record_path:
        parts.append(
            f"[f=mp4:movflags=+frag_keyframe+empty_moov+default_base_moof:flush_packets=1]"
            f"{_escape_tee_slave(_norm_fs_path(config.record_path))}"
        )
    if config.hls_output_dir:
        playlist = Path(config.hls_output_dir).expanduser() / "index.m3u8"
        st = float(config.hls_segment_time)
        list_size = int(config.hls_list_size)
        hls_opts = f"f=hls:hls_time={st}:hls_list_size={list_size}"
        if list_size > 0:
            hls_opts += ":hls_flags=delete_segments"
        parts.append(f"[{hls_opts}]{_escape_tee_slave(_norm_fs_path(str(playlist)))}")
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
    n_dest = sum(1 for x in (rtsp_push_url, srt_push_url, tcp_listen) if x is not None)
    if n_dest != 1:
        raise PublishError(
            "internal: specify exactly one of rtsp_push_url, srt_push_url, tcp_listen"
        )

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
        dest = f"tcp://{format_url_host(host)}:{port}?listen=1"
        return base + mux + ["-f", "mpegts", dest]

    if srt_push_url is not None:
        # MPEG-TS over SRT is widely supported by FFmpeg.
        return base + mux + ["-f", "mpegts", srt_push_url]

    assert rtsp_push_url is not None
    if wants_side:
        tee_arg = _build_tee_spec(rtsp_push_url, config)
        return [*base, "-flags", "+global_header", "-map", "0:v:0", "-f", "tee", tee_arg]
    return base + mux + ["-f", "rtsp", "-rtsp_transport", "tcp", rtsp_push_url]


def build_rtsp_passthrough_ffmpeg_cmd(
    *,
    source_url: str,
    config: StreamConfig,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> list[str]:
    """
    FFmpeg argv after the binary for RTSP relay with video/audio passthrough.

    Exactly one of *rtsp_push_url*, *srt_push_url*, or *tcp_listen* must be provided.
    """
    n_dest = sum(1 for x in (rtsp_push_url, srt_push_url, tcp_listen) if x is not None)
    if n_dest != 1:
        raise PublishError(
            "internal: specify exactly one of rtsp_push_url, srt_push_url, tcp_listen"
        )

    if (config.record_path or config.hls_output_dir) and (
        tcp_listen is not None or srt_push_url is not None
    ):
        raise PublishError(
            "record_path and hls_output_dir require RTSP push (tee muxer); "
            "not compatible with SRT-only or TCP MPEG-TS listen mode."
        )

    input_args = config.extra_ffmpeg_input_args + ffmpeg_ingest_rtsp_args(
        source_url,
        config.transport,
        config.latency_ms,
    )
    base = [
        "-loglevel",
        "warning",
        *input_args,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        *config.extra_ffmpeg_output_args,
    ]
    mux = ["-muxdelay", "0", "-muxpreload", "0"]

    if tcp_listen is not None:
        host, port = tcp_listen
        dest = f"tcp://{format_url_host(host)}:{port}?listen=1"
        return base + mux + ["-f", "mpegts", dest]

    if srt_push_url is not None:
        return base + mux + ["-f", "mpegts", srt_push_url]

    assert rtsp_push_url is not None
    if config.record_path or config.hls_output_dir:
        tee_arg = _build_tee_spec(rtsp_push_url, config)
        return [*base, "-f", "tee", tee_arg]
    return base + mux + ["-f", "rtsp", "-rtsp_transport", "tcp", rtsp_push_url]


def run_publish_loop(
    frame_iter: Iterator[np.ndarray],
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None = None,
    stop_event: threading.Event | None = None,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> None:
    """
    Blocking: encode frames from *frame_iter* and send to RTSP, SRT, or TCP listen.

    The encoder is sized from the first frame, so *width* and *height* only matter when the
    iterator is empty.
    """
    first_frame: np.ndarray | None = None
    if not _is_set(stop_event):
        first_frame = next(frame_iter, None)
        if first_frame is not None:
            _check_frame_layout(first_frame)
            height, width = int(first_frame.shape[0]), int(first_frame.shape[1])

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
    stderr_tail = bytearray()
    stderr_thread: threading.Thread | None = None

    def _exit_error(code: int | None) -> PublishError:
        if stderr_thread is not None:
            stderr_thread.join(timeout=1.0)
        return _publisher_exit_error(code, stderr_tail)

    try:
        proc = subprocess.Popen(
            [ffmpeg, *cmd],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            # A background reader keeps diagnostics bounded without letting FFmpeg block on stderr.
            stderr=subprocess.PIPE,
        )
        if proc_holder is not None:
            proc_holder.append(proc)
        assert proc.stdin is not None
        assert proc.stderr is not None
        stderr_tail, stderr_thread = start_tail_reader(
            proc.stderr,
            name="easy-rtsp-publish-stderr",
        )
        if tcp_listen is not None:
            _plog.info(
                "TCP MPEG-TS listen on tcp://%s:%s (connect a viewer)",
                format_url_host(tcp_listen[0]),
                tcp_listen[1],
            )
        if srt_push_url is not None:
            _plog.info("Publishing MPEG-TS to SRT %s", redact_url_credentials(srt_push_url))

        frames = frame_iter if first_frame is None else itertools.chain((first_frame,), frame_iter)
        expected_shape = (height, width, 3)
        for frame in frames:
            if _is_set(stop_event):
                break
            if frame.shape != expected_shape or frame.dtype != np.uint8:
                raise PublishError(
                    f"Each frame must be uint8 HWC BGR shaped {expected_shape}, "
                    f"got {frame.dtype} {frame.shape}"
                )
            # Writing the array's buffer directly avoids a tobytes() copy per frame.
            proc.stdin.write(np.ascontiguousarray(frame).data)
            proc.stdin.flush()
        # EOF on stdin lets FFmpeg flush the encoder and finalize MP4/HLS side outputs.
        proc.stdin.close()
        try:
            code = proc.wait(timeout=_ENCODER_DRAIN_TIMEOUT_SEC)
        except subprocess.TimeoutExpired as e:
            raise PublishError("ffmpeg publisher did not exit after the input stream ended") from e
        if code != 0 and not _is_set(stop_event):
            raise _exit_error(code)
    except (OSError, ValueError) as e:
        # Writing to an encoder that already exited (viewer disconnect, server gone, or stop())
        # fails with EPIPE/EINVAL, Windows error 232/109, or ValueError once stdin is closed.
        if _is_set(stop_event):
            return
        if proc is None or not _is_closed_pipe_error(e):
            raise
        try:
            code = proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            code = None
        if code not in _ENCODER_STOPPED_CODES:
            raise _exit_error(code) from e
    finally:
        if proc is not None:
            with suppress(OSError, ValueError):
                if proc.stdin:
                    proc.stdin.close()
            terminate_process(proc)
            if stderr_thread is not None:
                stderr_thread.join(timeout=5.0)
            discard_process(proc_holder, proc)


def _check_frame_layout(frame: np.ndarray) -> None:
    if (
        getattr(frame, "dtype", None) != np.uint8
        or getattr(frame, "ndim", 0) != 3
        or frame.shape[2] != 3
    ):
        raise PublishError(
            "Each frame must be uint8 HWC BGR shaped (H, W, 3), "
            f"got {getattr(frame, 'dtype', None)} {getattr(frame, 'shape', None)}"
        )


def _is_set(event: threading.Event | None) -> bool:
    return event is not None and event.is_set()


def _is_closed_pipe_error(e: BaseException) -> bool:
    if isinstance(e, (ValueError, BrokenPipeError)):
        return True  # ValueError: "write to closed file"
    if isinstance(e, OSError):
        return e.errno in (errno.EPIPE, errno.ECONNRESET, errno.EINVAL) or getattr(
            e, "winerror", None
        ) in (232, 109)
    return False


def _publisher_exit_error(code: int | None, stderr_tail: bytearray) -> PublishError:
    detail = redact_credentials_in_text(decode_tail_bytes(stderr_tail).strip())
    suffix = f": {detail[-4000:]}" if detail else ""
    status = "did not exit" if code is None else f"exited with code {code}"
    return PublishError(f"ffmpeg publisher {status}{suffix}")


def _wait_for_relay_exit(
    proc: subprocess.Popen[bytes], stop_event: threading.Event | None
) -> int | None:
    """
    Wait for a passthrough relay to exit; on *stop_event*, ask FFmpeg to quit gracefully.

    Returns the exit code, or ``None`` if FFmpeg ignored the quit request (the caller terminates it).
    """
    if stop_event is None:
        return proc.wait()
    while True:
        try:
            return proc.wait(timeout=_STOP_POLL_SEC)
        except subprocess.TimeoutExpired:
            if stop_event.is_set():
                break
    # FFmpeg reads interactive commands from stdin when stdin is not an input; "q" finalizes outputs.
    if proc.stdin is not None:
        with suppress(OSError, ValueError):
            proc.stdin.write(b"q")
            proc.stdin.flush()
    try:
        return proc.wait(timeout=_QUIT_GRACE_SEC)
    except subprocess.TimeoutExpired:
        return None


def run_rtsp_passthrough_loop(
    source_url: str,
    *,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None = None,
    stop_event: threading.Event | None = None,
    on_reconnecting_attempt: Callable[[int, str], None] | None = None,
    on_running: Callable[[], None] | None = None,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> None:
    """Blocking: relay RTSP video and audio directly to RTSP, SRT, or TCP listen."""
    ffmpeg = resolve_ffmpeg()
    cmd = build_rtsp_passthrough_ffmpeg_cmd(
        source_url=source_url,
        config=config,
        rtsp_push_url=rtsp_push_url,
        srt_push_url=srt_push_url,
        tcp_listen=tcp_listen,
    )
    attempt = 0

    while not _is_set(stop_event):
        proc: subprocess.Popen[bytes] | None = None
        stderr_tail = bytearray()
        stderr_thread: threading.Thread | None = None
        try:
            proc = subprocess.Popen(
                [ffmpeg, *cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if proc_holder is not None:
                proc_holder.append(proc)
            if on_running is not None:
                on_running()
            assert proc.stderr is not None
            stderr_tail, stderr_thread = start_tail_reader(
                proc.stderr,
                name="easy-rtsp-passthrough-stderr",
            )
            code = _wait_for_relay_exit(proc, stop_event)
            stderr_thread.join(timeout=1.0)
        finally:
            if proc is not None:
                with suppress(OSError):
                    if proc.stdin:
                        proc.stdin.close()
                terminate_process(proc)
                if stderr_thread is not None:
                    stderr_thread.join(timeout=5.0)
                discard_process(proc_holder, proc)

        if _is_set(stop_event):
            return
        if not config.reconnect:
            if code != 0:
                raise _publisher_exit_error(code, stderr_tail)
            return
        if config.max_reconnect_attempts is not None and attempt >= config.max_reconnect_attempts:
            if code != 0:
                detail = redact_credentials_in_text(decode_tail_bytes(stderr_tail).strip())
                suffix = f": {detail[-4000:]}" if detail else ""
                raise PublishError(
                    f"ffmpeg passthrough publisher exhausted reconnect attempts{suffix}"
                )
            return

        attempt += 1
        reconnect_reason = "stream_ended" if code == 0 else "publish_exited"
        if on_reconnecting_attempt is not None:
            on_reconnecting_attempt(attempt, reconnect_reason)
            continue
        if config.on_reconnecting is not None:
            config.on_reconnecting(attempt)
        interval = max(0.0, float(config.retry_interval_sec))
        if stop_event is not None:
            if stop_event.wait(interval):
                return
        elif interval:
            time.sleep(interval)


def start_rtsp_passthrough_thread(
    source_url: str,
    *,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None,
    stop_event: threading.Event | None,
    on_done: Callable[[BaseException | None], None],
    on_reconnecting_attempt: Callable[[int, str], None] | None = None,
    on_running: Callable[[], None] | None = None,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> threading.Thread:
    """Run :func:`run_rtsp_passthrough_loop` in a daemon thread."""

    def _run() -> None:
        err: BaseException | None = None
        try:
            run_rtsp_passthrough_loop(
                source_url,
                config=config,
                proc_holder=proc_holder,
                stop_event=stop_event,
                on_reconnecting_attempt=on_reconnecting_attempt,
                on_running=on_running,
                rtsp_push_url=rtsp_push_url,
                srt_push_url=srt_push_url,
                tcp_listen=tcp_listen,
            )
        except BaseException as e:
            err = e
        finally:
            on_done(err)

    t = threading.Thread(target=_run, name="easy-rtsp-publish-audio", daemon=True)
    t.start()
    return t


def start_publish_thread(
    frame_iter_factory: Callable[[], Iterator[np.ndarray]],
    *,
    width: int,
    height: int,
    fps: float,
    config: StreamConfig,
    proc_holder: list[subprocess.Popen[bytes] | None] | None,
    stop_event: threading.Event | None = None,
    on_done: Callable[[BaseException | None], None],
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> threading.Thread:
    """Run :func:`run_publish_loop` in a daemon thread."""

    def _run() -> None:
        err: BaseException | None = None
        frames: Iterator[np.ndarray] | None = None
        try:
            frames = frame_iter_factory()
            run_publish_loop(
                frames,
                width=width,
                height=height,
                fps=fps,
                config=config,
                proc_holder=proc_holder,
                stop_event=stop_event,
                rtsp_push_url=rtsp_push_url,
                srt_push_url=srt_push_url,
                tcp_listen=tcp_listen,
            )
        except BaseException as e:
            err = e
        finally:
            # Close generator sources now (stopping their decoder processes) rather than at GC time.
            close = getattr(frames, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as e:
                    err = err or e
            on_done(err)

    t = threading.Thread(target=_run, name="easy-rtsp-publish", daemon=True)
    t.start()
    return t
