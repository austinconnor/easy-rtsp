"""MediaMTX RTSP server process management and local network helpers."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from pathlib import Path

from easy_rtsp.exceptions import DependencyError, PublishError
from easy_rtsp.ffmpeg_util import resolve_mediamtx
from easy_rtsp.process_io import decode_tail_bytes, start_tail_reader, terminate_process

_READY_TIMEOUT_SEC = 5.0
# MediaMTX 1.19 added a MoQ server that is enabled by default; it binds extra ports (so a second
# local stream fails to start) and writes auto-generated TLS files into the working directory.
_MOQ_MIN_VERSION = (1, 19, 0)


def discover_lan_hosts() -> list[str]:
    """Return usable IPv4 addresses for reaching this machine from the local network."""
    out: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return
        if (
            ip.version != 4
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_multicast
            or candidate in seen
        ):
            return
        seen.add(candidate)
        out.append(candidate)

    # Ask the routing table first. No packets need to be sent for a UDP connect.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("8.8.8.8", 80))
            add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        _hostname, _aliases, addresses = socket.gethostbyname_ex(socket.gethostname())
        for address in addresses:
            add(address)
    except OSError:
        pass
    return out


def discover_webrtc_additional_hosts(
    *,
    lan_access: bool = False,
    listen_host: str = "127.0.0.1",
) -> list[str]:
    """
    IPs to advertise in ICE for local MediaMTX WebRTC.

    Browsers need candidates that match how they reach the server (e.g. ``127.0.0.1`` for the
    same machine, LAN IP for phones). MediaMTX also recommends ``webrtcAdditionalHosts`` when
    connectivity fails behind NAT or strict firewalls.
    """
    local_host = _local_bind_host(listen_host) or "127.0.0.1"
    return [local_host, *discover_lan_hosts()] if lan_access else [local_host]


def tcp_port_is_available(host: str, port: int, *, lan_access: bool = False) -> bool:
    """Return True if nothing is listening on ``host:port`` and we can bind to it."""
    clean_host = _local_bind_host(host)
    probe_host = "127.0.0.1" if not clean_host or clean_host == "0.0.0.0" else clean_host
    with suppress(OSError), socket.create_connection((probe_host, port), timeout=0.1):
        return False

    family = socket.AF_INET6 if ":" in clean_host else socket.AF_INET
    bind_hosts = [clean_host]
    if lan_access and family == socket.AF_INET and clean_host != "0.0.0.0":
        bind_hosts.append("0.0.0.0")
    for bind_host in bind_hosts:
        with socket.socket(family, socket.SOCK_STREAM) as s:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                with suppress(OSError):
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                s.bind((bind_host, port))
            except OSError:
                return False
    return True


def wait_for_tcp_listener(host: str, port: int, *, timeout: float = 5.0) -> bool:
    """Wait until a TCP listener accepts connections instead of guessing with a fixed sleep."""
    deadline = time.monotonic() + max(0.0, timeout)
    clean_host = _local_bind_host(host)
    while True:
        try:
            with socket.create_connection((clean_host, port), timeout=0.2):
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def write_minimal_mediamtx_config(
    path: Path,
    rtsp_path: str,
    listen_port: int,
    *,
    lan_access: bool = False,
    listen_host: str = "127.0.0.1",
    webrtc_enabled: bool = False,
    webrtc_http_port: int = 8889,
    webrtc_ice_port: int = 8189,
    disable_moq: bool = False,
) -> None:
    """
    Write a minimal MediaMTX config: RTSP publisher path and optional WebRTC (browser) playback.

    Set *disable_moq* for MediaMTX 1.19+, which otherwise starts a MoQ server by default.
    """
    if webrtc_enabled:
        hosts = discover_webrtc_additional_hosts(lan_access=lan_access, listen_host=listen_host)
        hosts_yaml = ", ".join(json.dumps(h) if ":" in h else h for h in hosts)
        webrtc_host = "" if lan_access else _local_bind_host(listen_host)
        # - webrtcIPsFromInterfaces: false — on Windows, auto-discovered IPs often include VPN /
        #   virtual adapters; the browser then negotiates ICE candidates that never reach 127.0.0.1.
        # - webrtcICEServers2: [] — STUN is for NAT hole-punching; for same-machine / LAN it can
        #   make browsers prefer srflx candidates and stay stuck on "loading". Static UDP :8189
        #   + host candidates in webrtcAdditionalHosts is enough for typical local playback.
        webrtc_block = f"""
webrtc: true
webrtcAddress: {_yaml_listener_address(webrtc_host, webrtc_http_port)}
webrtcIPsFromInterfaces: false
webrtcLocalUDPAddress: {_yaml_listener_address(webrtc_host, webrtc_ice_port)}
webrtcLocalTCPAddress: {_yaml_listener_address(webrtc_host, webrtc_ice_port)}
webrtcAdditionalHosts: [{hosts_yaml}]
webrtcICEServers2: []
"""
    else:
        webrtc_block = "\nwebrtc: false\n"

    moq_block = "moq: false\n" if disable_moq else ""
    path_key = json.dumps(rtsp_path)
    rtsp_host = "" if lan_access else _local_bind_host(listen_host)
    content = f"""# Generated by easy-rtsp
logLevel: warn
logDestinations: [stdout]
rtspAddress: {_yaml_listener_address(rtsp_host, listen_port)}
rtspTransports: [tcp]
rtmp: false
hls: false
srt: false
{moq_block}{webrtc_block}
paths:
  {path_key}:
    source: publisher
"""
    path.write_text(content, encoding="utf-8")


def _local_bind_host(host: str) -> str:
    clean = host.strip().strip("[]")
    return "127.0.0.1" if clean.lower().rstrip(".") == "localhost" else clean


def _listener_address(host: str, port: int) -> str:
    if not host:
        return f":{port}"
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _yaml_listener_address(host: str, port: int) -> str:
    addr = _listener_address(host, port)
    return json.dumps(addr) if addr.startswith("[") else addr


def mediamtx_version(binary: str) -> tuple[int, int, int] | None:
    """Return the ``(major, minor, patch)`` reported by ``mediamtx --version``, if available."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", f"{result.stdout} {result.stderr}")
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def _mediamtx_supports_moq(version: tuple[int, int, int] | None) -> bool:
    # MediaMTX rejects unknown config keys, so ``moq`` may only be written for releases that know
    # it. An unparseable version is treated as current rather than as an unsupported legacy build.
    return version is None or version >= _MOQ_MIN_VERSION


class MediaMTXProcess:
    """Started ``mediamtx`` subprocess with a generated config file."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        config_path: Path,
        output_tail: bytearray,
        output_thread: threading.Thread,
    ) -> None:
        self._process = process
        self._config_path = config_path
        self._output_tail = output_tail
        self._output_thread = output_thread

    @property
    def pid(self) -> int | None:
        return self._process.pid

    @classmethod
    def launch(
        cls,
        *,
        path_name: str,
        host: str,
        port: int,
        lan_access: bool = False,
        webrtc_enabled: bool = False,
        webrtc_http_port: int = 8889,
        webrtc_ice_port: int = 8189,
        binary: str | None = None,
        ready_timeout: float = _READY_TIMEOUT_SEC,
    ) -> MediaMTXProcess:
        """
        Write a temporary config, start MediaMTX, and wait until its RTSP listener is ready.

        The config file is removed when the process stops or if startup fails.
        """
        binary = binary or _require_mediamtx()
        fd, tmp = tempfile.mkstemp(suffix=".yml", prefix="easy-rtsp-mediamtx-")
        os.close(fd)
        config_path = Path(tmp)
        try:
            write_minimal_mediamtx_config(
                config_path,
                path_name,
                port,
                lan_access=lan_access,
                listen_host=host,
                webrtc_enabled=webrtc_enabled,
                webrtc_http_port=webrtc_http_port,
                webrtc_ice_port=webrtc_ice_port,
                disable_moq=_mediamtx_supports_moq(mediamtx_version(binary)),
            )
        except BaseException:
            with suppress(OSError):
                config_path.unlink()
            raise
        backend = cls.start(config_path, binary=binary)
        try:
            backend.wait_until_ready(host, port, timeout=ready_timeout)
        except BaseException:
            backend.stop()
            raise
        return backend

    @classmethod
    def start(cls, config_path: Path, *, binary: str | None = None) -> MediaMTXProcess:
        """Spawn MediaMTX with *config_path*; the file is deleted if the process cannot start."""
        binary = binary or _require_mediamtx()
        try:
            proc = subprocess.Popen(
                [binary, str(config_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                # Anything MediaMTX writes relative to its working directory stays out of the caller's.
                cwd=str(config_path.parent),
            )
        except OSError as e:
            with suppress(OSError):
                config_path.unlink()
            raise DependencyError(f"mediamtx could not be executed: {e}") from e
        assert proc.stdout is not None
        output_tail, output_thread = start_tail_reader(
            proc.stdout,
            name="easy-rtsp-mediamtx-output",
        )
        return cls(proc, config_path, output_tail, output_thread)

    def wait_until_ready(
        self, host: str, port: int, *, timeout: float = _READY_TIMEOUT_SEC
    ) -> None:
        """
        Block until MediaMTX accepts TCP connections on ``host:port``.

        Raises :class:`PublishError` with MediaMTX's own output if it exits or never listens.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._process.poll() is not None:
                raise PublishError(
                    f"mediamtx exited during startup (code {self._process.returncode})"
                    f"{self._output_suffix()}"
                )
            if wait_for_tcp_listener(host, port, timeout=0.0):
                return
            if time.monotonic() >= deadline:
                raise PublishError(
                    f"mediamtx did not listen on {host}:{port} within {timeout:g}s"
                    f"{self._output_suffix()}"
                )
            time.sleep(0.05)

    def stop(self, *, timeout: float = 10.0) -> None:
        terminate_process(self._process, timeout=timeout)
        self._output_thread.join(timeout=5.0)
        with suppress(OSError):
            self._config_path.unlink(missing_ok=True)

    def _output_suffix(self) -> str:
        # The reader thread exits once the process closes stdout; give it a moment to catch up.
        if self._process.poll() is not None:
            self._output_thread.join(timeout=2.0)
        output = decode_tail_bytes(self._output_tail).strip()
        return f": {output[-2000:]}" if output else ""


def _require_mediamtx() -> str:
    binary = resolve_mediamtx()
    if not binary:
        raise DependencyError(
            "mediamtx not found. Install it with `easy-rtsp install-backends`, add it to PATH, "
            "or set EASY_RTSP_MEDIAMTX to the mediamtx executable."
        )
    return binary
