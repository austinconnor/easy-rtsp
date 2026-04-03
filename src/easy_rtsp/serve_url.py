"""Parse ``serve()`` endpoint strings into publish destinations (RTSP, RTSPS, SRT)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlparse, urlunparse

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError


@dataclass(frozen=True)
class PublishDestination:
    """Resolved ``serve()`` target for FFmpeg."""

    url: str
    """Full URL passed to FFmpeg (preserves RTSP userinfo when present)."""

    host: str
    port: int
    path_name: str
    """Last path segment, used for generated MediaMTX config on loopback."""

    scheme: str
    """``rtsp``, ``rtsps``, or ``srt``."""


def build_rtsp_url(
    host: str,
    path: str = "live",
    *,
    port: int = 8554,
    username: str | None = None,
    password: str | None = None,
    secure: bool = False,
) -> str:
    """
    Build an RTSP or RTSPS URL without requiring callers to hand-assemble userinfo.

    Username and password are percent-encoded safely so special characters remain valid in the URL.
    """
    if not host:
        raise ConfigurationError("RTSP host must be non-empty")
    if not path:
        path = "live"
    scheme = "rtsps" if secure else "rtsp"
    path_clean = path if path.startswith("/") else f"/{path.lstrip('/')}"
    path_clean = quote(path_clean, safe="/")
    userinfo = ""
    if username is not None:
        userinfo = quote(username, safe="")
        if password is not None:
            userinfo += f":{quote(password, safe='')}"
        userinfo += "@"
    netloc = f"{userinfo}{host}:{int(port)}"
    return urlunparse((scheme, netloc, path_clean, "", "", ""))


def parse_publish_destination(spec: str, config: StreamConfig) -> PublishDestination:
    """
    Parse a *spec* for :meth:`~easy_rtsp.stream.Stream.serve`.

    * ``\"live\"`` -> ``rtsp://{server_host}:{server_port}/live``
    * ``rtsp://user:pass@host:8554/path`` -> URL preserved (credentials kept)
    * ``srt://host:9000?mode=listener`` -> SRT push (no local MediaMTX RTSP startup)
    """
    raw = spec.strip()
    if not raw:
        raise ConfigurationError("serve() endpoint must be non-empty")

    if "://" not in raw:
        path = raw.lstrip("/")
        if not path:
            path = "live"
        host = config.server_host
        port = config.server_port
        url = f"rtsp://{host}:{port}/{path}"
        return PublishDestination(url=url, host=host, port=port, path_name=path, scheme="rtsp")

    u = urlparse(raw)
    scheme = (u.scheme or "").lower()
    if scheme in ("rtsp", "rtsps"):
        host = u.hostname or config.server_host
        if not host:
            raise ConfigurationError("RTSP URL must include a host or use a shorthand like 'live'")
        port = u.port if u.port is not None else config.server_port
        path_clean = (u.path or "").strip()
        if not path_clean or path_clean == "/":
            path_clean = "/live"
        if not path_clean.startswith("/"):
            path_clean = "/" + path_clean
        path_name = path_clean.strip("/").split("/")[-1] or "live"
        netloc = u.netloc
        if not netloc:
            raise ConfigurationError("RTSP URL must include a host (netloc)")
        full = urlunparse((u.scheme, netloc, path_clean, "", "", ""))
        return PublishDestination(url=full, host=host, port=port, path_name=path_name, scheme=scheme)

    if scheme == "srt":
        host = u.hostname or "127.0.0.1"
        port = u.port if u.port is not None else 9000
        return PublishDestination(url=raw, host=host, port=port, path_name="", scheme="srt")

    raise ConfigurationError(
        f"Unsupported URL scheme for serve(): {scheme!r} (use rtsp://, rtsps://, or srt://)"
    )


def parse_serve_endpoint(spec: str, config: StreamConfig) -> tuple[str, str, int, str]:
    """Backward-compatible wrapper returning ``(url, host, port, path_name)``."""
    d = parse_publish_destination(spec, config)
    return d.url, d.host, d.port, d.path_name


def is_loopback_host(host: str) -> bool:
    h = host.lower()
    return h in ("127.0.0.1", "localhost", "::1")
