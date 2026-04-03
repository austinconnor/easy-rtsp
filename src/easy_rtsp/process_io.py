"""Helpers for bounded subprocess I/O capture and cleanup."""

from __future__ import annotations

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
        except OSError:
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
