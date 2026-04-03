"""Local file ingest."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import SourceError
from easy_rtsp.ffmpeg_util import probe_video
from easy_rtsp.sources.base import ensure_bgr_uint8
from easy_rtsp.sources.decode import iter_raw_bgr_frames


class FileSource:
    """Decode a video file to BGR frames via FFmpeg."""

    def __init__(self, path: str | Path, config: StreamConfig | None = None) -> None:
        self._path = Path(path)
        if not self._path.is_file():
            raise SourceError(f"Not a file or missing: {self._path}")
        self._config = config or StreamConfig()

    @property
    def config(self) -> StreamConfig:
        return self._config

    def frames(self) -> Iterator[np.ndarray]:
        path_str = str(self._path.resolve())
        probe = probe_video(path_str)
        w, h = probe.width, probe.height

        # Loop inside FFmpeg (-stream_loop -1) so one decode process runs continuously; restarting
        # at EOF can fail on some files when FFmpeg exits non-zero at end-of-file.
        loop = ["-stream_loop", "-1"] if self._config.file_loop else []
        input_args = self._config.extra_ffmpeg_input_args + loop + ["-i", path_str, "-an"]
        for frame in iter_raw_bgr_frames(
            input_args, w, h, proc_holder=self._config.ffmpeg_children
        ):
            yield ensure_bgr_uint8(frame, context="FileSource")
