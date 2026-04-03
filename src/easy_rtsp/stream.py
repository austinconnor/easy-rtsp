"""Primary :class:`Stream` API."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np

from easy_rtsp.backend import MediaMTXProcess, tcp_port_is_available, write_minimal_mediamtx_config
from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError, DependencyError, ProcessingError
from easy_rtsp.ffmpeg_util import probe_video, resolve_mediamtx
from easy_rtsp.install_backends import INSTALL_MEDIAMTX_CLI
from easy_rtsp.publish import start_publish_thread
from easy_rtsp.serve_url import is_loopback_host, parse_publish_destination
from easy_rtsp.sources.file import FileSource
from easy_rtsp.sources.frames import FrameGeneratorSource
from easy_rtsp.sources.rtsp import RtspSource
from easy_rtsp.sources.webcam import WebcamSource, probe_webcam_dimensions
from easy_rtsp.log import get_logger
from easy_rtsp.types import StreamState, StreamStatus

_logger = get_logger("stream")

# Main-thread ``threading.Event.wait(None)`` can block delivery of ``KeyboardInterrupt`` on Windows;
# polling with a short timeout keeps Ctrl+C responsive while ``wait()`` runs.
_WAIT_POLL_SEC = 0.3


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
        self._publish_thread: threading.Thread | None = None
        self._backend: MediaMTXProcess | None = None
        self._publish_error: BaseException | None = None
        self._wait_event = threading.Event()
        self._latest_frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._serve_started = False
        self._viewer_url: str | None = None
        self._webrtc_play_url: str | None = None

        if isinstance(self._source, RtspSource):
            user_hook = self._config.on_reconnecting

            def _reconnect_hook(attempt: int) -> None:
                self._set_state(StreamState.RECONNECTING)
                _logger.info("stream state -> reconnecting (attempt %s)", attempt)
                if user_hook is not None:
                    user_hook(attempt)

            # Mutate shared StreamConfig so RtspSource and all Stream wrappers stay in sync.
            self._config.on_reconnecting = _reconnect_hook

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
        network, replace the host with this machine's LAN IP. ``None`` if WebRTC was not enabled.
        """
        return self._webrtc_play_url

    def status(self) -> StreamStatus:
        """Return an immutable snapshot of the stream's current health and lifecycle state."""
        with self._latest_frame_lock:
            latest_frame_available = self._latest_frame is not None
        return StreamStatus(
            state=self._state,
            reconnect_count=self.reconnect_count,
            serve_started=self._serve_started,
            latest_frame_available=latest_frame_available,
            viewer_url=self._viewer_url,
            webrtc_play_url=self._webrtc_play_url,
            publish_error=None if self._publish_error is None else str(self._publish_error),
            created_at=self._created_at,
            last_state_change_at=self._last_state_change_at,
            publish_thread_alive=bool(
                self._publish_thread is not None and self._publish_thread.is_alive()
            ),
        )

    @classmethod
    def open(cls, url: str, **kwargs: Any) -> Stream:
        """Open an RTSP URL (``rtsp://`` or ``rtsps://``)."""
        cfg = _stream_config_from_kwargs(**kwargs)
        return cls(RtspSource(url, cfg), config=cfg)

    @classmethod
    def from_webcam(cls, index: int = 0, **kwargs: Any) -> Stream:
        """Open a webcam by index (uses OpenCV, bundled as a dependency)."""
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

    def map(self, fn: Callable[[np.ndarray], np.ndarray | None]) -> Stream:
        """Return a new stream that applies *fn* to each frame (``None`` drops a frame)."""

        def composed(frame: np.ndarray) -> np.ndarray | None:
            if self._transform is None:
                return fn(frame)
            mid = self._transform(frame)
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

        Uses OpenCV for image encoding when available. Raises a helpful error if no frame is
        available yet or if OpenCV is not installed.
        """
        frame = self.latest_frame(copy=True)
        if frame is None:
            raise ProcessingError("No frame available yet to save a snapshot")

        try:
            import cv2  # type: ignore[import-untyped]
        except ImportError as e:
            raise DependencyError(
                "OpenCV (cv2) is required to save snapshots. "
                'Install with: pip install "easy-rtsp[webcam]" (or pip install opencv-python-headless).'
            ) from e

        dest = Path(path).expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(dest), frame)
        if not ok:
            raise ProcessingError(f"Could not write snapshot to {dest}")
        return dest

    def frames(self) -> Iterator[np.ndarray]:
        """Iterate decoded or generated frames (BGR ``uint8``)."""
        for frame in self._source.frames():
            if self._state in (StreamState.STOPPED, StreamState.RECONNECTING):
                self._set_state(StreamState.RUNNING)
            if self._transform is None:
                out = frame
            else:
                try:
                    out = self._transform(frame)
                except Exception as e:
                    raise ProcessingError("transform callback failed") from e
                if out is None:
                    continue
            with self._latest_frame_lock:
                self._latest_frame = out.copy()
            yield out

    def serve(self, endpoint: str = "live", **kwargs: Any) -> Stream:
        """
        Start publishing (non-blocking).

        *endpoint* may be:

        * a shorthand path (e.g. ``\"live\"`` -> ``rtsp://127.0.0.1:8554/live``)
        * a full ``rtsp://`` or ``rtsps://`` URL (userinfo is preserved for authenticated cameras)
        * an ``srt://`` URL (FFmpeg publishes MPEG-TS over SRT; no local MediaMTX RTSP startup)

        On loopback RTSP, if the port is free: **MediaMTX** is started when ``mediamtx`` is on ``PATH``.
        If MediaMTX is missing, **FFmpeg** listens for **one** MPEG-TS client over **TCP** on the same
        host/port (open ``tcp://HOST:PORT`` in VLC). FFmpeg's RTSP muxer cannot reliably act as an RTSP
        server; use MediaMTX for ``rtsp://`` playback.
        If something is already listening on the port, FFmpeg pushes RTSP to that server (client mode).

        Optional :class:`~easy_rtsp.config.StreamConfig` fields ``record_path`` and ``hls_output_dir``
        duplicate the encoded stream to MP4 / HLS via FFmpeg's ``tee`` muxer (RTSP push only).

        When MediaMTX is started on loopback, set ``webrtc_enabled`` (default False) to turn on
        MediaMTX's WebRTC server; use :attr:`webrtc_play_url` for browser/mobile playback (no audio).
        """
        if kwargs:
            self._config = dataclasses.replace(self._config, **_stream_config_from_kwargs(**kwargs))
        if self._serve_started:
            raise ConfigurationError("serve() was already started on this Stream")

        self._webrtc_play_url = None
        dest = parse_publish_destination(endpoint, self._config)
        w, h, fps = self._infer_publish_params()

        if self._config.hls_output_dir:
            Path(self._config.hls_output_dir).mkdir(parents=True, exist_ok=True)
        if self._config.record_path:
            Path(self._config.record_path).parent.mkdir(parents=True, exist_ok=True)

        self._config.ffmpeg_children.clear()
        self._publish_error = None
        self._wait_event.clear()

        tcp_mpegts_listen = False
        rtsp_push_url: str | None = None
        srt_push_url: str | None = None

        if dest.scheme == "srt":
            srt_push_url = dest.url
        elif dest.scheme in ("rtsp", "rtsps"):
            host, port, _path_name = dest.host, dest.port, dest.path_name
            full_url = dest.url
            if is_loopback_host(host):
                if tcp_port_is_available(host, port):
                    mtx = resolve_mediamtx()
                    if mtx:
                        fd, tmp = tempfile.mkstemp(suffix=".yml", prefix="easy-rtsp-mediamtx-")
                        os.close(fd)
                        cfg_path = Path(tmp)
                        write_minimal_mediamtx_config(
                            cfg_path,
                            _path_name,
                            port,
                            webrtc_enabled=self._config.webrtc_enabled,
                            webrtc_http_port=self._config.webrtc_http_port,
                        )
                        self._backend = MediaMTXProcess.start(cfg_path)
                        time.sleep(0.25)
                    else:
                        tcp_mpegts_listen = True
                        _logger.warning(
                            "MediaMTX is not installed or not on PATH. "
                            "Using MPEG-TS over TCP at tcp://%s:%s (VLC: Media → Open Network Stream) "
                            "instead of rtsp:// on this port. "
                            "To install MediaMTX: %s",
                            host,
                            port,
                            INSTALL_MEDIAMTX_CLI,
                        )
                # else: assume an RTSP server is already bound on that port (client push mode)
            if not tcp_mpegts_listen:
                rtsp_push_url = full_url
        else:
            raise ConfigurationError(f"Unsupported serve() scheme: {dest.scheme!r}")

        self._set_state(StreamState.RUNNING)
        self._serve_started = True

        def factory() -> Iterator[np.ndarray]:
            return iter(self.frames())

        def on_done(err: BaseException | None) -> None:
            self._publish_error = err
            if err is not None:
                self._set_state(StreamState.ERROR)
            else:
                self._set_state(StreamState.STOPPED)
            self._wait_event.set()
            backend = self._backend
            self._backend = None
            if backend is not None:
                backend.stop()

        self._publish_thread = start_publish_thread(
            factory,
            width=w,
            height=h,
            fps=fps,
            config=self._config,
            proc_holder=self._config.ffmpeg_children,
            on_done=on_done,
            rtsp_push_url=None if tcp_mpegts_listen else rtsp_push_url,
            srt_push_url=srt_push_url,
            tcp_listen=(dest.host, dest.port) if tcp_mpegts_listen else None,
        )
        if tcp_mpegts_listen:
            self._viewer_url = f"tcp://{dest.host}:{dest.port}"
        else:
            self._viewer_url = dest.url

        if (
            self._backend is not None
            and dest.scheme in ("rtsp", "rtsps")
            and self._config.webrtc_enabled
        ):
            self._webrtc_play_url = (
                f"http://{dest.host}:{self._config.webrtc_http_port}/{dest.path_name}"
            )
        return self

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

    def stop(self) -> None:
        """Stop publishing and any MediaMTX instance started by this stream."""
        children = list(self._config.ffmpeg_children)
        for proc in children:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        # Give FFmpeg a moment to exit, then hard-kill anything still running (orphan/zombie guard).
        time.sleep(0.25)
        for proc in children:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
        if self._backend is not None:
            self._backend.stop()
            self._backend = None
        self._set_state(StreamState.STOPPING)
        if self._publish_thread and self._publish_thread.is_alive():
            self._publish_thread.join(timeout=20.0)
        self._set_state(StreamState.STOPPED)
        self._wait_event.set()
        self._config.ffmpeg_children.clear()

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()

    def _infer_publish_params(self) -> tuple[int, int, float]:
        fps_default = self._config.fps if self._config.fps is not None else 30.0
        s = self._source
        if isinstance(s, FrameGeneratorSource):
            w, h = s.size
            return w, h, s.fps
        if isinstance(s, FileSource):
            p = probe_video(str(s._path.resolve()))
            if self._config.fps is not None:
                fps = float(self._config.fps)
            else:
                fps = p.fps if p.fps and p.fps > 0 else 30.0
            return p.width, p.height, fps
        if isinstance(s, RtspSource):
            p = probe_video(s._url)
            fps = p.fps if p.fps and p.fps > 0 else fps_default
            return p.width, p.height, fps
        if isinstance(s, WebcamSource):
            w, h = probe_webcam_dimensions(s._index)
            return w, h, fps_default
        raise ConfigurationError(f"Unsupported source type for publish: {type(s)!r}")

    def _set_state(self, state: StreamState) -> None:
        self._state = state
        self._last_state_change_at = time.monotonic()


def _stream_config_from_kwargs(**kwargs: Any) -> StreamConfig:
    fields = {f.name for f in dataclasses.fields(StreamConfig)}
    unknown = set(kwargs) - fields
    if unknown:
        raise ConfigurationError(f"Unknown stream options: {sorted(unknown)}")
    return StreamConfig(**kwargs)
