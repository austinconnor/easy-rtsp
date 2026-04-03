"""Shared FFmpeg rawvideo decode loop."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from typing import Callable

import numpy as np

from easy_rtsp.exceptions import DependencyError, SourceError
from easy_rtsp.ffmpeg_util import resolve_ffmpeg
from easy_rtsp.process_io import decode_tail_bytes, discard_process, start_tail_reader


def _ffmpeg_exit_ok(returncode: int | None, stderr: str) -> bool:
    """Whether FFmpeg's exit code is acceptable after we stop reading stdout."""
    if returncode is None:
        return False
    if returncode in (0, -15, 255):
        return True
    err = stderr.lower()
    # Closing the pipe early makes FFmpeg exit 1 with "Broken pipe" / mux errors — not a decode failure.
    if returncode == 1 and "broken pipe" in err:
        return True
    return False


def iter_raw_bgr_frames(
    ffmpeg_cmd: list[str],
    width: int,
    height: int,
    *,
    stderr_filter: Callable[[str], None] | None = None,
    proc_holder: list[subprocess.Popen[bytes]] | None = None,
) -> Iterator[np.ndarray]:
    """Run FFmpeg and yield BGR frames read from stdout."""
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
    frame_bytes = width * height * 3
    try:
        while True:
            buf = proc.stdout.read(frame_bytes)
            if not buf or len(buf) < frame_bytes:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 3))
    finally:
        killed_by_us = False
        try:
            proc.stdout.close()
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            killed_by_us = True
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
            killed_by_us = True
        stderr_thread.join(timeout=5.0)
        discard_process(proc_holder, proc)
        err = decode_tail_bytes(stderr_tail)
        if not killed_by_us and not _ffmpeg_exit_ok(proc.returncode, err):
            if stderr_filter:
                stderr_filter(err)
            raise SourceError(f"ffmpeg exited with code {proc.returncode}: {err[-4000:]}")
