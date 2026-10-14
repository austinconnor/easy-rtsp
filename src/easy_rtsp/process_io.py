"""Helpers for bounded subprocess I/O capture and cleanup."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterable
from contextlib import suppress
from threading import Thread
from typing import IO, Any

_TAIL_MAX_BYTES = 16 * 1024
_READ_CHUNK_BYTES = 4096


def start_tail_reader(stream: IO[bytes], *, name: str) -> tuple[bytearray, Thread]:
    """Drain a byte stream in the background while keeping only a bounded tail."""
    tail = bytearray()

    def _drain() -> None:
        try:
            while True:
                chunk = stream.read(_READ_CHUNK_BYTES)
                if not chunk:
                    break
                tail.extend(chunk)
                overflow = len(tail) - _TAIL_MAX_BYTES
                if overflow > 0:
                    del tail[:overflow]
        except (OSError, ValueError):
            pass
        finally:
            with suppress(OSError):
                stream.close()

    thread = Thread(target=_drain, name=name, daemon=True)
    thread.start()
    return tail, thread


def decode_tail_bytes(tail: bytearray) -> str:
    """Decode a bounded stderr tail to text."""
    return bytes(tail).decode("utf-8", errors="replace")


def discard_process(proc_holder: list[Any] | None, proc: Any) -> None:
    """Remove a subprocess handle from a shared holder if it is still present."""
    if proc_holder is None:
        return
    with suppress(ValueError):
        proc_holder.remove(proc)


def terminate_process(proc: subprocess.Popen[bytes], *, timeout: float = 5.0) -> None:
    """Terminate *proc* if it is still running, escalating to ``kill()`` after *timeout*."""
    terminate_processes([proc], timeout=timeout)


def terminate_processes(procs: Iterable[subprocess.Popen[bytes] | None], *, timeout: float) -> None:
    """Terminate every running process, then kill whichever ones outlive a shared *timeout*."""
    running = [p for p in procs if p is not None and p.poll() is None]
    for proc in running:
        with suppress(OSError):
            proc.terminate()
    deadline = time.monotonic() + timeout
    for proc in running:
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            with suppress(OSError):
                proc.kill()
            with suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=timeout)
