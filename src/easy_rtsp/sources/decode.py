"""Shared FFmpeg rawvideo decode loop."""

from __future__ import annotations

import io
import subprocess
import threading
from collections.abc import Iterator
from contextlib import suppress
from typing import cast

import numpy as np

from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import resolve_ffmpeg
from easy_rtsp.process_io import (
    decode_tail_bytes,
    discard_process,
    start_tail_reader,
    terminate_process,
)
from easy_rtsp.serve_url import redact_credentials_in_text

_EOF_EXIT_TIMEOUT_SEC = 5.0


def _ffmpeg_exit_ok(returncode: int | None, stderr: str) -> bool:
    """Whether FFmpeg's exit code is acceptable after we stop reading stdout."""
    if returncode is None:
        return False
    if returncode in (0, -15, 255):
        return True
    # Closing the pipe early makes FFmpeg exit 1 with "Broken pipe" / mux errors — not a decode failure.
    return returncode == 1 and "broken pipe" in stderr.lower()


def iter_raw_bgr_frames(
    ffmpeg_cmd: list[str],
    width: int,
    height: int,
    *,
    proc_holder: list[subprocess.Popen[bytes]] | None = None,
    stop_event: threading.Event | None = None,
) -> Iterator[np.ndarray]:
    """Run FFmpeg and yield writeable BGR frames read from stdout."""
    if width <= 0 or height <= 0:
        raise SourceError("width and height must be positive")
    ffmpeg = resolve_ffmpeg()
    cmd = [ffmpeg, *ffmpeg_cmd, "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as e:
        raise DependencyError("ffmpeg could not be executed.") from e

    if proc_holder is not None:
        proc_holder.append(proc)

    assert proc.stdout is not None
    assert proc.stderr is not None
    stderr_tail, stderr_thread = start_tail_reader(
        proc.stderr,
        name="easy-rtsp-decode-stderr",
    )
    stdout = cast(io.BufferedReader, proc.stdout)
    frame_bytes = width * height * 3
    stopped_early = False
    try:
        while not (stop_event is not None and stop_event.is_set()):
            # Read straight into a fresh array: one copy per frame, and callers may mutate it.
            frame = np.empty((height, width, 3), dtype=np.uint8)
            if stdout.readinto(frame.data) != frame_bytes:
                break
            yield frame
    except GeneratorExit:
        stopped_early = True
        raise
    finally:
        stopped = stopped_early or bool(stop_event is not None and stop_event.is_set())
        with suppress(OSError):
            proc.stdout.close()
        if not stopped:
            # stdout hit EOF, so FFmpeg is exiting on its own; collect its real exit status.
            try:
                proc.wait(timeout=_EOF_EXIT_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                stopped = True
        terminate_process(proc, timeout=10.0)
        stderr_thread.join(timeout=5.0)
        discard_process(proc_holder, proc)
        if not stopped:
            err = redact_credentials_in_text(decode_tail_bytes(stderr_tail))
            if not _ffmpeg_exit_ok(proc.returncode, err):
                raise SourceError(f"ffmpeg exited with code {proc.returncode}: {err[-4000:]}")
