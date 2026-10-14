"""Primary :class:`Stream` API."""

from __future__ import annotations

import asyncio
import dataclasses
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from easy_rtsp.backend import MediaMTXProcess, discover_lan_hosts, tcp_port_is_available
from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError, DependencyError, ProcessingError
from easy_rtsp.ffmpeg_util import ffmpeg_rtsp_input_options, probe_video, resolve_mediamtx
from easy_rtsp.install_backends import INSTALL_MEDIAMTX_CLI
from easy_rtsp.log import get_logger
from easy_rtsp.process_io import terminate_processes
from easy_rtsp.publish import start_publish_thread, start_rtsp_passthrough_thread
from easy_rtsp.serve_url import (
    PublishDestination,
    build_rtsp_url,
    format_url_host,
    is_loopback_host,
    parse_publish_destination,
)
from easy_rtsp.sources.base import ensure_bgr_uint8
from easy_rtsp.sources.file import FileSource
from easy_rtsp.sources.frames import FrameGeneratorSource
from easy_rtsp.sources.rtsp import RtspSource
from easy_rtsp.sources.webcam import WebcamSource, probe_webcam
from easy_rtsp.types import StreamState, StreamStatus

_logger = get_logger("stream")

# Main-thread ``threading.Event.wait(None)`` can block delivery of ``KeyboardInterrupt`` on Windows;
# polling with a short timeout keeps Ctrl+C responsive while ``wait()`` runs.
_WAIT_POLL_SEC = 0.3
# How long stop() lets the publish thread close FFmpeg's input (finalizing MP4/HLS side outputs)
# before terminating whatever is still running, e.g. a decoder blocked on a stalled camera.
_STOP_GRACE_SEC = 2.0
_STOP_KILL_TIMEOUT_SEC = 2.0
_STOP_JOIN_TIMEOUT_SEC = 10.0
_DEFAULT_FPS = 30.0


@dataclasses.dataclass(frozen=True)
class _PublishTarget:
    """Where the publish thread sends encoded output; exactly one field is set."""

    rtsp_push_url: str | None = None
    srt_push_url: str | None = None
    tcp_listen: tuple[str, int] | None = None


class Stream:
    """
    Ingest video, optionally transform frames, and publish (RTSP, RTSPS, or SRT).

    Frames are **BGR** ``uint8`` arrays with shape ``(height, width, 3)`` (OpenCV-style).
    """

    def __init__(
        self,
        source: Any,
        *,
        config: StreamConfig | None = None,
        transform: Callable[[np.ndarray], np.ndarray | None] | None = None,
    ) -> None:
        self._source = source
        self._config = config if config is not None else source.config
        self._transform = transform
        self._state = StreamState.STOPPED
        self._created_at = time.monotonic()
        self._last_state_change_at = self._created_at
        self._publish_started_at: float | None = None
        self._publish_ended_at: float | None = None
        self._publish_thread: threading.Thread | None = None
        self._backend: MediaMTXProcess | None = None
        self._backend_lock = threading.Lock()
        self._publish_error: BaseException | None = None
        self._wait_event = threading.Event()
        self._stop_event = threading.Event()
        self._latest_frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._last_frame_at: float | None = None
        self._dropped_frame_count = 0
        self._serve_started = False
        self._viewer_url: str | None = None
        self._webrtc_play_url: str | None = None
        self._lan_viewer_urls: tuple[str, ...] = ()
        self._lan_webrtc_play_urls: tuple[str, ...] = ()
        self._bind_source()

    def __repr__(self) -> str:
        source = type(self._source).__name__
        return f"<Stream source={source} state={self._state.value} viewer_url={self._viewer_url!r}>"

    # ------------------------------------------------------------------ properties

    @property
    def reconnect_count(self) -> int:
        """RTSP ingest reconnect counter (0 if the source is not RTSP)."""
        if isinstance(self._source, RtspSource):
            return self._source.reconnect_count
        return 0

    @property
    def state(self) -> StreamState:
        return self._state

    @property
    def serve_started(self) -> bool:
        """Whether :meth:`serve` has been called successfully on this stream."""
        return self._serve_started

    @property
    def config(self) -> StreamConfig:
        return self._config

    @property
    def viewer_url(self) -> str | None:
        """
        URL to open in a player after :meth:`serve` returns.

        Typically ``rtsp://...``, ``rtsps://...``, ``srt://...``, or ``tcp://...`` (MPEG-TS
        listen fallback without MediaMTX). ``None`` if :meth:`serve` has not been called yet.
        """
        return self._viewer_url

    @property
    def webrtc_play_url(self) -> str | None:
        """
        When easy-rtsp started **MediaMTX** locally with ``webrtc_enabled`` set, HTTP URL for **browser**
        playback (video only). Typically ``http://127.0.0.1:8889/<path>``. For phones on the same
        network, use :attr:`lan_webrtc_play_urls`. ``None`` if WebRTC was not enabled.
        """
        return self._webrtc_play_url

    @property
    def lan_viewer_urls(self) -> tuple[str, ...]:
        """Ready-to-use RTSP URLs for other devices when ``lan_access`` is enabled."""
        return self._lan_viewer_urls

    @property
    def lan_webrtc_play_urls(self) -> tuple[str, ...]:
        """Ready-to-use browser playback URLs for other devices on the LAN."""
        return self._lan_webrtc_play_urls

    def status(self) -> StreamStatus:
        """Return an immutable snapshot of the stream's current health and lifecycle state."""
        with self._latest_frame_lock:
            latest_frame_available = self._latest_frame is not None
            last_frame_at = self._last_frame_at
        last_reconnect_reason = (
            self._source.last_reconnect_reason if isinstance(self._source, RtspSource) else None
        )
        alive_child_process_count = sum(
            1
            for proc in list(self._config.ffmpeg_children)
            if proc is not None and proc.poll() is None
        )
        if self._publish_started_at is None:
            publish_uptime_sec = None
        else:
            end_at = self._publish_ended_at or time.monotonic()
            publish_uptime_sec = max(0.0, end_at - self._publish_started_at)
        if self._publish_error is None:
            publish_error = None
        else:
            publish_error = str(self._publish_error) or type(self._publish_error).__name__
        return StreamStatus(
            state=self._state,
            reconnect_count=self.reconnect_count,
            last_reconnect_reason=last_reconnect_reason,
            serve_started=self._serve_started,
            latest_frame_available=latest_frame_available,
            dropped_frame_count=self._dropped_frame_count,
            last_frame_at=last_frame_at,
            publish_started_at=self._publish_started_at,
            publish_uptime_sec=publish_uptime_sec,
            alive_child_process_count=alive_child_process_count,
            viewer_url=self._viewer_url,
            webrtc_play_url=self._webrtc_play_url,
            lan_viewer_urls=self._lan_viewer_urls,
            lan_webrtc_play_urls=self._lan_webrtc_play_urls,
            publish_error=publish_error,
            created_at=self._created_at,
            last_state_change_at=self._last_state_change_at,
            publish_thread_alive=bool(
                self._publish_thread is not None and self._publish_thread.is_alive()
            ),
        )

    # ------------------------------------------------------------------ constructors

    @classmethod
    def open(cls, url: str, **kwargs: Any) -> Stream:
        """Open an RTSP URL (``rtsp://`` or ``rtsps://``)."""
        cfg = _stream_config_from_kwargs(**kwargs)
        return cls(RtspSource(url, cfg), config=cfg)

    @classmethod
    def open_rtsp(
        cls,
        host: str,
        path: str = "live",
        *,
        port: int = 554,
        username: str | None = None,
        password: str | None = None,
        secure: bool = False,
        **kwargs: Any,
    ) -> Stream:
        """Open an RTSP or RTSPS URL from parts without manual URL assembly."""
        url = build_rtsp_url(
            host,
            path,
            port=port,
            username=username,
            password=password,
            secure=secure,
        )
        return cls.open(url, **kwargs)

    @classmethod
    def from_webcam(cls, index: int = 0, **kwargs: Any) -> Stream:
        """Open a webcam by index (requires the optional OpenCV ``webcam`` extra)."""
        cfg = _stream_config_from_kwargs(**kwargs)
        return cls(WebcamSource(index, cfg), config=cfg)

    @classmethod
    def from_file(cls, path: str | Path, **kwargs: Any) -> Stream:
        """Decode frames from a video file on disk.

        Use ``fps`` in :class:`~easy_rtsp.config.StreamConfig` to override publish FPS; otherwise
        FPS is inferred from the file via ffprobe (fallback 30). Set ``file_loop=False`` to stop
        after one playthrough (default ``file_loop=True`` loops the file for continuous streaming).
        """
        cfg = _stream_config_from_kwargs(**kwargs)
        return cls(FileSource(path, cfg), config=cfg)

    @classmethod
    def from_frames(
        cls,
        factory: Callable[[], Iterator[np.ndarray]] | Iterator[np.ndarray],
        *,
        fps: float,
        size: tuple[int, int],
        **kwargs: Any,
    ) -> Stream:
        """Use a Python frame generator or iterator (see :class:`~easy_rtsp.sources.frames.FrameGeneratorSource`)."""
        cfg = _stream_config_from_kwargs(**kwargs)
        return cls(FrameGeneratorSource(factory, fps=fps, size=size, config=cfg), config=cfg)

    # ------------------------------------------------------------------ processing

    def map(self, fn: Callable[[np.ndarray], np.ndarray | None]) -> Stream:
        """Return a new stream that applies *fn* to each frame (``None`` drops a frame)."""
        inner = self._transform

        def composed(frame: np.ndarray) -> np.ndarray | None:
            if inner is None:
                return fn(frame)
            mid = inner(frame)
            if mid is None:
                return None
            return fn(mid)

        return Stream(self._source, config=self._config, transform=composed)

    def latest_frame(self, copy: bool = True) -> np.ndarray | None:
        """
        Return the most recent processed frame, or ``None`` if no frame has been produced yet.

        When ``copy`` is true, return a defensive copy so callers can inspect or mutate the result
        without affecting the cached frame.
        """
        with self._latest_frame_lock:
            frame = self._latest_frame
            if frame is None:
                return None
            return frame.copy() if copy else frame

    def save_snapshot(self, path: str | Path) -> Path:
        """
        Save the latest processed frame to *path* and return the resolved destination path.

        The image format follows the file extension (``.jpg``, ``.png``, ...). Requires OpenCV;
        raises :class:`ProcessingError` if no frame is available yet.
        """
        frame = self.latest_frame(copy=False)
        if frame is None:
            raise ProcessingError("No frame available yet to save a snapshot")

        try:
            import cv2
        except ImportError as e:
            raise DependencyError(
                "OpenCV (cv2) is required to save snapshots. "
                'Install with: pip install "easy-rtsp[webcam]" (or pip install opencv-python-headless).'
            ) from e

        dest = Path(path).expanduser().resolve()
        # cv2.imencode + write_bytes (instead of cv2.imwrite) handles non-ASCII paths on Windows.
        try:
            ok, encoded = cv2.imencode(dest.suffix or ".png", frame)
        except cv2.error as e:
            raise ProcessingError(f"Could not encode snapshot for {dest}: {e}") from e
        if not ok:
            raise ProcessingError(f"Could not encode snapshot for {dest}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(encoded.tobytes())
        return dest

    def frames(self) -> Iterator[np.ndarray]:
        """Iterate decoded or generated frames (BGR ``uint8``) after any :meth:`map` transforms."""
        self._bind_source()
        try:
            for frame in self._source.frames():
                if self._stop_event.is_set():
                    break
                if self._state in (
                    StreamState.STOPPED,
                    StreamState.STARTING,
                    StreamState.RECONNECTING,
                ):
                    self._set_state(StreamState.RUNNING)
                if self._transform is None:
                    out = frame
                else:
                    try:
                        out = self._transform(frame)
                    except Exception as e:
                        raise ProcessingError("transform callback failed") from e
                    if out is None:
                        self._dropped_frame_count += 1
                        continue
                try:
                    out = ensure_bgr_uint8(out, context="Stream frame")
                except (AttributeError, ValueError) as e:
                    raise ProcessingError(
                        f"invalid frame returned by source or transform: {e}"
                    ) from e
                with self._latest_frame_lock:
                    self._latest_frame = out.copy()
                    self._last_frame_at = time.monotonic()
                yield out
        finally:
            if not self._serve_started and self._state is not StreamState.ERROR:
                self._set_state(StreamState.STOPPED)

    # ------------------------------------------------------------------ publishing

    def serve(self, endpoint: str = "live", **kwargs: Any) -> Stream:
        """
        Start publishing (non-blocking).

        *endpoint* may be:

        * a shorthand path (e.g. ``\"live\"`` -> ``rtsp://127.0.0.1:8554/live``)
        * a full ``rtsp://`` or ``rtsps://`` URL (userinfo is preserved for authenticated cameras)
        * an ``srt://`` URL (FFmpeg publishes MPEG-TS over SRT; no local MediaMTX RTSP startup)

        On loopback RTSP, if the port is free: **MediaMTX** is started when it is installed.
        If MediaMTX is missing, **FFmpeg** listens for **one** MPEG-TS client over **TCP** on the same
        host/port (open ``tcp://HOST:PORT`` in VLC). FFmpeg's RTSP muxer cannot reliably act as an RTSP
        server; use MediaMTX for ``rtsp://`` playback.
        If something is already listening on the port, FFmpeg pushes RTSP to that server (client mode).

        Optional :class:`~easy_rtsp.config.StreamConfig` fields ``record_path`` and ``hls_output_dir``
        duplicate the encoded stream to MP4 / HLS via FFmpeg's ``tee`` muxer (RTSP push only).

        When MediaMTX is started on loopback, set ``webrtc_enabled`` (default False) to turn on
        MediaMTX's WebRTC server; use :attr:`webrtc_play_url` for browser/mobile playback (no audio).

        Keyword arguments override :class:`~easy_rtsp.config.StreamConfig` fields for this stream.
        """
        if self._serve_started:
            raise ConfigurationError("serve() was already started on this Stream")
        if kwargs:
            self._apply_config_overrides(kwargs)
        config = self._config
        use_audio_passthrough = config.audio_mode == "passthrough"
        if use_audio_passthrough:
            self._validate_audio_passthrough()
        dest = parse_publish_destination(endpoint, config)
        if config.lan_access and not (dest.scheme == "rtsp" and is_loopback_host(dest.host)):
            raise ConfigurationError(
                "lan_access only applies to a local RTSP shorthand or loopback rtsp:// URL"
            )
        wants_side_outputs = bool(config.record_path or config.hls_output_dir)
        if wants_side_outputs and dest.scheme == "srt":
            raise ConfigurationError(
                "record_path and hls_output_dir require an RTSP publish destination"
            )

        self._bind_source()
        self._stop_event.clear()
        self._wait_event.clear()
        self._publish_error = None
        config.ffmpeg_children.clear()
        self._viewer_url = None
        self._webrtc_play_url = None
        self._lan_viewer_urls = ()
        self._lan_webrtc_play_urls = ()
        self._set_state(StreamState.STARTING)
        try:
            if use_audio_passthrough:
                width, height, fps = 0, 0, 0.0
            else:
                width, height, fps = self._infer_publish_params()
            target = self._prepare_publish_target(dest)
            if wants_side_outputs and target.tcp_listen is not None:
                raise ConfigurationError(
                    "record_path and hls_output_dir need MediaMTX or an existing RTSP server; "
                    "the TCP fallback cannot create side outputs. Install MediaMTX with: "
                    f"{INSTALL_MEDIAMTX_CLI}"
                )
            self._create_side_output_dirs()

            self._publish_started_at = time.monotonic()
            self._publish_ended_at = None
            self._serve_started = True
            self._set_state(StreamState.RUNNING)
            if use_audio_passthrough:
                self._publish_thread = self._start_passthrough(target)
            else:
                self._publish_thread = self._start_publish(target, width, height, fps)
        except BaseException:
            self._serve_started = False
            self._publish_started_at = None
            self._stop_backend()
            self._set_state(StreamState.STOPPED)
            raise

        self._record_viewer_urls(dest, target)
        return self

    def serve_rtsp(
        self,
        host: str,
        path: str = "live",
        *,
        port: int = 8554,
        username: str | None = None,
        password: str | None = None,
        secure: bool = False,
        **kwargs: Any,
    ) -> Stream:
        """
        Publish to an RTSP or RTSPS destination built from discrete connection parts.

        This is a convenience wrapper around :meth:`serve` that avoids manual URL assembly,
        especially when credentials need percent-encoding.
        """
        url = build_rtsp_url(
            host,
            path,
            port=port,
            username=username,
            password=password,
            secure=secure,
        )
        return self.serve(url, **kwargs)

    def wait(self, timeout: float | None = None) -> bool:
        """
        Block until publishing finishes or *timeout* seconds elapse.

        Returns whether the wait ended because publishing finished (event set), not because of a
        timeout. Uses short internal sleeps so the CLI can handle **Ctrl+C** (``KeyboardInterrupt``)
        on Windows, where an unbounded ``Event.wait()`` often never raises it.
        """
        if timeout is None:
            while not self._wait_event.wait(timeout=_WAIT_POLL_SEC):
                pass
            return True
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self._wait_event.is_set()
            if self._wait_event.wait(timeout=min(_WAIT_POLL_SEC, remaining)):
                return True

    async def wait_async(self, timeout: float | None = None) -> bool:
        """Async wrapper for :meth:`wait` that avoids blocking the event loop."""
        return await asyncio.to_thread(self.wait, timeout)

    def stop(self) -> None:
        """
        Stop publishing and any MediaMTX instance started by this stream.

        The publish thread first gets a short grace period to close FFmpeg's input so MP4 and HLS
        side outputs are finalized; FFmpeg processes still running afterwards are terminated.
        Safe to call more than once.
        """
        self._stop_event.set()
        if self._state is not StreamState.STOPPED:
            self._set_state(StreamState.STOPPING)
        thread = self._publish_thread
        # stop() may be called from a transform running on the publish thread itself.
        joinable = thread is not None and thread is not threading.current_thread()
        if joinable:
            assert thread is not None
            thread.join(timeout=_STOP_GRACE_SEC)
        terminate_processes(list(self._config.ffmpeg_children), timeout=_STOP_KILL_TIMEOUT_SEC)
        if joinable:
            assert thread is not None
            thread.join(timeout=_STOP_JOIN_TIMEOUT_SEC)
        self._stop_backend()
        if self._publish_started_at is not None and self._publish_ended_at is None:
            self._publish_ended_at = time.monotonic()
        self._config.ffmpeg_children.clear()
        self._set_state(StreamState.STOPPED)
        self._wait_event.set()

    async def stop_async(self) -> None:
        """Async wrapper for :meth:`stop` that avoids blocking the event loop."""
        await asyncio.to_thread(self.stop)

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    # ------------------------------------------------------------------ internals

    def _bind_source(self) -> None:
        """Point built-in sources at this stream's stop event and reconnect hook."""
        if hasattr(self._source, "_stop_event"):
            self._source._stop_event = self._stop_event
        if isinstance(self._source, RtspSource):
            self._source._on_reconnecting_internal = self._handle_reconnect_attempt

    def _apply_config_overrides(self, overrides: dict[str, Any]) -> None:
        old_config = self._config
        self._config = dataclasses.replace(old_config, **_stream_options_from_kwargs(**overrides))
        # Built-in sources read ingest/file behavior from their own config reference; keep it aligned.
        if getattr(self._source, "config", None) is old_config and hasattr(self._source, "_config"):
            self._source._config = self._config

    def _handle_reconnect_attempt(self, attempt: int, _reason: str = "") -> None:
        self._set_state(StreamState.RECONNECTING)
        _logger.info("stream state -> reconnecting (attempt %s)", attempt)

    def _prepare_publish_target(self, dest: PublishDestination) -> _PublishTarget:
        """Decide how FFmpeg publishes, starting a local MediaMTX server when appropriate."""
        if dest.scheme == "srt":
            return _PublishTarget(srt_push_url=dest.url)
        local_port_free = is_loopback_host(dest.host) and tcp_port_is_available(
            dest.host, dest.port, lan_access=self._config.lan_access
        )
        if not local_port_free:
            # Remote server, or a server already listening locally: push to it as an RTSP client.
            return _PublishTarget(rtsp_push_url=dest.url)
        if dest.scheme == "rtsps":
            raise ConfigurationError(
                "rtsps:// on loopback needs an RTSPS server already listening on "
                f"{dest.host}:{dest.port}; the MediaMTX instance easy-rtsp starts serves plain rtsp://"
            )

        mediamtx = resolve_mediamtx()
        if mediamtx:
            self._backend = MediaMTXProcess.launch(
                path_name=dest.path_name,
                host=dest.host,
                port=dest.port,
                lan_access=self._config.lan_access,
                webrtc_enabled=self._config.webrtc_enabled,
                webrtc_http_port=self._config.webrtc_http_port,
                webrtc_ice_port=self._config.webrtc_ice_port,
                binary=mediamtx,
            )
            return _PublishTarget(rtsp_push_url=dest.url)

        if self._config.lan_access:
            raise DependencyError(
                "LAN RTSP requires MediaMTX; the built-in fallback is not an RTSP "
                f"server. Install it with: {INSTALL_MEDIAMTX_CLI}"
            )
        _logger.warning(
            "MediaMTX is not installed. Using MPEG-TS over TCP at tcp://%s:%s "
            "(VLC: Media > Open Network Stream) instead of rtsp:// on this port. "
            "To install MediaMTX: %s",
            format_url_host(dest.host),
            dest.port,
            INSTALL_MEDIAMTX_CLI,
        )
        return _PublishTarget(tcp_listen=(dest.host, dest.port))

    def _create_side_output_dirs(self) -> None:
        if self._config.hls_output_dir:
            Path(self._config.hls_output_dir).expanduser().mkdir(parents=True, exist_ok=True)
        if self._config.record_path:
            Path(self._config.record_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

    def _start_publish(
        self, target: _PublishTarget, width: int, height: int, fps: float
    ) -> threading.Thread:
        return start_publish_thread(
            self.frames,
            width=width,
            height=height,
            fps=fps,
            config=self._config,
            proc_holder=self._config.ffmpeg_children,
            stop_event=self._stop_event,
            on_done=self._on_publish_done,
            rtsp_push_url=target.rtsp_push_url,
            srt_push_url=target.srt_push_url,
            tcp_listen=target.tcp_listen,
        )

    def _start_passthrough(self, target: _PublishTarget) -> threading.Thread:
        assert isinstance(self._source, RtspSource)
        return start_rtsp_passthrough_thread(
            self._source.url,
            config=self._config,
            proc_holder=self._config.ffmpeg_children,
            stop_event=self._stop_event,
            on_done=self._on_publish_done,
            on_reconnecting_attempt=self._on_passthrough_reconnect,
            on_running=self._on_passthrough_running,
            rtsp_push_url=target.rtsp_push_url,
            srt_push_url=target.srt_push_url,
            tcp_listen=target.tcp_listen,
        )

    def _on_passthrough_reconnect(self, _attempt: int, reason: str) -> None:
        assert isinstance(self._source, RtspSource)
        self._source.record_reconnect(reason, sleep=True)

    def _on_passthrough_running(self) -> None:
        if not self._stop_event.is_set() and self._state in (
            StreamState.STARTING,
            StreamState.RECONNECTING,
        ):
            self._set_state(StreamState.RUNNING)

    def _on_publish_done(self, err: BaseException | None) -> None:
        self._publish_ended_at = time.monotonic()
        if self._stop_event.is_set():
            err = None
        self._publish_error = err
        if err is not None:
            _logger.error("publishing stopped with an error: %s", err)
            self._set_state(StreamState.ERROR)
        else:
            self._set_state(StreamState.STOPPED)
        self._wait_event.set()
        self._stop_backend()

    def _record_viewer_urls(self, dest: PublishDestination, target: _PublishTarget) -> None:
        if target.tcp_listen is not None:
            self._viewer_url = f"tcp://{format_url_host(dest.host)}:{dest.port}"
        else:
            self._viewer_url = dest.url
        if self._backend is None:
            return
        webrtc_port = self._config.webrtc_http_port
        if self._config.webrtc_enabled:
            self._webrtc_play_url = (
                f"http://{format_url_host(dest.host)}:{webrtc_port}/{dest.path_name}"
            )
        if self._config.lan_access:
            lan_hosts = [format_url_host(host) for host in discover_lan_hosts()]
            self._lan_viewer_urls = tuple(
                f"rtsp://{host}:{dest.port}/{dest.path_name}" for host in lan_hosts
            )
            if self._config.webrtc_enabled:
                self._lan_webrtc_play_urls = tuple(
                    f"http://{host}:{webrtc_port}/{dest.path_name}" for host in lan_hosts
                )

    def _stop_backend(self) -> None:
        with self._backend_lock:
            backend = self._backend
            self._backend = None
        if backend is not None:
            backend.stop()

    def _infer_publish_params(self) -> tuple[int, int, float]:
        """Return ``(width, height, fps)`` for the encoder, probing the source when needed."""
        configured_fps = float(self._config.fps) if self._config.fps is not None else None
        s = self._source
        if isinstance(s, FrameGeneratorSource):
            w, h = s.size
            return w, h, configured_fps or s.fps
        if isinstance(s, FileSource):
            probe = probe_video(str(s.path.resolve()))
            s._cached_probe = probe
        elif isinstance(s, RtspSource):
            probe = probe_video(
                s.url,
                input_args=ffmpeg_rtsp_input_options(
                    self._config.transport, self._config.latency_ms
                ),
            )
            s._cached_probe = probe
        elif isinstance(s, WebcamSource):
            probe = probe_webcam(s.index)
        else:
            # Custom FrameSource: run_publish_loop takes the real size from the first frame.
            size = getattr(s, "size", None)
            if isinstance(size, tuple) and len(size) == 2:
                return int(size[0]), int(size[1]), configured_fps or _DEFAULT_FPS
            return 1, 1, configured_fps or _DEFAULT_FPS
        return probe.width, probe.height, configured_fps or probe.fps or _DEFAULT_FPS

    def _set_state(self, state: StreamState) -> None:
        self._state = state
        self._last_state_change_at = time.monotonic()

    def _validate_audio_passthrough(self) -> None:
        if not isinstance(self._source, RtspSource):
            raise ConfigurationError(
                "audio_mode='passthrough' is currently supported only for Stream.open()/open_rtsp() RTSP sources"
            )
        if self._transform is not None:
            raise ConfigurationError(
                "audio_mode='passthrough' is not compatible with frame transforms in this release"
            )


def _stream_config_from_kwargs(**kwargs: Any) -> StreamConfig:
    return StreamConfig(**_stream_options_from_kwargs(**kwargs))


def _stream_options_from_kwargs(**kwargs: Any) -> dict[str, Any]:
    fields = {f.name for f in dataclasses.fields(StreamConfig)}
    unknown = set(kwargs) - fields
    if unknown:
        raise ConfigurationError(f"Unknown stream options: {sorted(unknown)}")
    return kwargs
