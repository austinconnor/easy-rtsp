"""Encode BGR frames and publish (FFmpeg -> RTSP, SRT, or TCP/MPEG-TS)."""

from __future__ import annotations

import errno
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import PublishError
from easy_rtsp.ffmpeg_util import ffmpeg_ingest_rtsp_args, resolve_ffmpeg
from easy_rtsp.log import get_logger
from easy_rtsp.process_io import decode_tail_bytes, discard_process, start_tail_reader
from easy_rtsp.serve_url import format_url_host, redact_credentials_in_text, redact_url_credentials

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
        dest = f"tcp://{format_url_host(host)}:{port}?listen=1"
        return base + mux + ["-f", "mpegts", dest]

    if srt_push_url is not None:
        # MPEG-TS over SRT is widely supported by FFmpeg.
        return base + mux + ["-f", "mpegts", srt_push_url]

    assert rtsp_push_url is not None
    if wants_side:
        tee_arg = _build_tee_spec(rtsp_push_url, config)
        return base + ["-flags", "+global_header", "-map", "0:v:0", "-f", "tee", tee_arg]
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
        raise PublishError("internal: specify exactly one of rtsp_push_url, srt_push_url, tcp_listen")

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
    stop_event: threading.Event | None = None,
    rtsp_push_url: str | None = None,
    srt_push_url: str | None = None,
    tcp_listen: tuple[str, int] | None = None,
) -> None:
    """Blocking: encode frames from *frame_iter* and send to RTSP, SRT, or TCP listen."""
    first_frame: np.ndarray | None = None
    if stop_event is None or not stop_event.is_set():
        first_frame = next(frame_iter, None)
        if first_frame is not None:
            if (
                getattr(first_frame, "dtype", None) != np.uint8
                or getattr(first_frame, "ndim", 0) != 3
                or first_frame.shape[2] != 3
            ):
                raise PublishError(
                    f"Each frame must be uint8 HWC BGR shaped (H, W, 3), "
                    f"got {getattr(first_frame, 'dtype', None)} {getattr(first_frame, 'shape', None)}"
                )
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
            _plog.info("TCP MPEG-TS listen on tcp://%s:%s (connect a viewer)", tcp_listen[0], tcp_listen[1])
        if srt_push_url is not None:
            _plog.info("Publishing MPEG-TS to SRT %s", redact_url_credentials(srt_push_url))

        def _all_frames() -> Iterator[np.ndarray]:
            if first_frame is not None:
                yield first_frame
            yield from frame_iter

        for frame in _all_frames():
            if stop_event is not None and stop_event.is_set():
                break
            if frame.shape != (height, width, 3) or frame.dtype != np.uint8:
                raise PublishError(
                    f"Each frame must be uint8 HWC BGR shaped {(height, width, 3)}, "
                    f"got {frame.dtype} {frame.shape}"
                )
            proc.stdin.write(frame.tobytes())
            proc.stdin.flush()
        proc.stdin.close()
        try:
            code = proc.wait(timeout=120)
        except subprocess.TimeoutExpired as e:
            raise PublishError("ffmpeg publisher did not exit after the input stream ended") from e
        if stop_event is not None and stop_event.is_set():
            return
        if code != 0:
            if stderr_thread is not None:
                stderr_thread.join(timeout=1.0)
            raise _publisher_exit_error(code, stderr_tail)
    except BrokenPipeError as e:
        if stop_event is not None and stop_event.is_set():
            return
        if proc is not None:
            try:
                code = proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                code = proc.poll()
            if code not in (0, -15, 255):
                if stderr_thread is not None:
                    stderr_thread.join(timeout=1.0)
                raise _publisher_exit_error(code if code is not None else 1, stderr_tail) from e
    except OSError as e:
        # Encoder stopped (stop() or viewer disconnect): EPIPE, EINVAL, or Windows winerror 232 / 109.
        if e.errno in (errno.EPIPE, errno.ECONNRESET, errno.EINVAL) or getattr(
            e, "winerror", None
        ) in (
            232,
            109,
        ):
            if stop_event is not None and stop_event.is_set():
                return
            if proc is not None:
                try:
                    code = proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    code = proc.poll()
                if code not in (0, -15, 255):
                    if stderr_thread is not None:
                        stderr_thread.join(timeout=1.0)
                    raise _publisher_exit_error(code if code is not None else 1, stderr_tail) from e
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
            if stderr_thread is not None:
                stderr_thread.join(timeout=5.0)
            discard_process(proc_holder, proc)


def _publisher_exit_error(code: int, stderr_tail: bytearray) -> PublishError:
    detail = redact_credentials_in_text(decode_tail_bytes(stderr_tail).strip())
    suffix = f": {detail[-4000:]}" if detail else ""
    return PublishError(f"ffmpeg publisher exited with code {code}{suffix}")


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
    attempt = 0
    last_error_detail = ""

    while True:
        proc: subprocess.Popen[bytes] | None = None
        stderr_tail = bytearray()
        stderr_thread: threading.Thread | None = None
        reconnect_reason: str | None = None
        try:
            cmd = build_rtsp_passthrough_ffmpeg_cmd(
                source_url=source_url,
                config=config,
                rtsp_push_url=rtsp_push_url,
                srt_push_url=srt_push_url,
                tcp_listen=tcp_listen,
            )
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
            code = proc.wait()
            stderr_thread.join(timeout=1.0)
            last_error_detail = redact_credentials_in_text(decode_tail_bytes(stderr_tail).strip())
            if stop_event is not None and stop_event.is_set():
                return
            if code == 0:
                reconnect_reason = "stream_ended"
            else:
                reconnect_reason = "publish_exited"
                if not config.reconnect:
                    raise _publisher_exit_error(code, stderr_tail)
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
                if stderr_thread is not None:
                    stderr_thread.join(timeout=5.0)
                discard_process(proc_holder, proc)

        if stop_event is not None and stop_event.is_set():
            return
        if not config.reconnect:
            return
        if config.max_reconnect_attempts is not None and attempt >= config.max_reconnect_attempts:
            if reconnect_reason == "publish_exited":
                suffix = f": {last_error_detail[-4000:]}" if last_error_detail else ""
                raise PublishError(
                    f"ffmpeg passthrough publisher exhausted reconnect attempts{suffix}"
                )
            return

        attempt += 1
        if on_reconnecting_attempt is not None:
            on_reconnecting_attempt(attempt, reconnect_reason or "publish_exited")
        else:
            if config.on_reconnecting is not None:
                config.on_reconnecting(attempt)
            interval = max(0.0, float(config.retry_interval_sec))
            if interval:
                if stop_event is not None:
                    if stop_event.wait(interval):
                        return
                else:
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
        try:
            run_publish_loop(
                frame_iter_factory(),
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
            on_done(err)

    t = threading.Thread(target=_run, name="easy-rtsp-publish", daemon=True)
    t.start()
    return t
