"""Parse ``serve()`` endpoint strings into publish destinations (RTSP, RTSPS, SRT)."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
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
    """Full path without the leading slash, used for generated MediaMTX config on loopback."""

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
    host = host.strip()
    if not host:
        raise ConfigurationError("RTSP host must be non-empty")
    if any(char in host for char in ("/", "?", "#", "@")):
        raise ConfigurationError("RTSP host must be a hostname or IP address, not a URL")
    if password is not None and username is None:
        raise ConfigurationError("password requires username")
    port = _validate_port(port, context="RTSP port")
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
    netloc = f"{userinfo}{_format_url_host(host)}:{port}"
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
        port = _validate_port(config.server_port, context="server_port")
        path = quote(path, safe="/%")
        url = f"rtsp://{_format_url_host(host)}:{port}/{path}"
        return PublishDestination(url=url, host=host, port=port, path_name=path, scheme="rtsp")

    try:
        u = urlparse(raw)
    except ValueError as e:
        raise ConfigurationError(f"Invalid publish URL: {redact_url_credentials(raw)!r}") from e
    scheme = (u.scheme or "").lower()
    if scheme in ("rtsp", "rtsps"):
        host = u.hostname or config.server_host
        if not host:
            raise ConfigurationError("RTSP URL must include a host or use a shorthand like 'live'")
        try:
            parsed_port = u.port
        except ValueError as e:
            raise ConfigurationError(f"Invalid RTSP port in {redact_url_credentials(raw)!r}") from e
        port = _validate_port(
            parsed_port if parsed_port is not None else (322 if scheme == "rtsps" else 554),
            context="RTSP port",
        )
        path_clean = (u.path or "").strip()
        if not path_clean or path_clean == "/":
            path_clean = "/live"
        if not path_clean.startswith("/"):
            path_clean = "/" + path_clean
        path_name = path_clean.strip("/") or "live"
        netloc = u.netloc
        if not netloc:
            raise ConfigurationError("RTSP URL must include a host (netloc)")
        full = urlunparse((scheme, netloc, path_clean, u.params, u.query, u.fragment))
        return PublishDestination(url=full, host=host, port=port, path_name=path_name, scheme=scheme)

    if scheme == "srt":
        host = u.hostname
        if not host:
            raise ConfigurationError("SRT URL must include a host")
        try:
            parsed_port = u.port
        except ValueError as e:
            raise ConfigurationError("Invalid SRT port") from e
        port = _validate_port(parsed_port if parsed_port is not None else 9000, context="SRT port")
        if parsed_port is None:
            userinfo, separator, _hostinfo = u.netloc.rpartition("@")
            prefix = f"{userinfo}@" if separator else ""
            netloc = f"{prefix}{_format_url_host(host)}:{port}"
            raw = urlunparse((scheme, netloc, u.path, u.params, u.query, u.fragment))
        return PublishDestination(url=raw, host=host, port=port, path_name="", scheme="srt")

    raise ConfigurationError(
        f"Unsupported URL scheme for serve(): {scheme!r} (use rtsp://, rtsps://, or srt://)"
    )


def parse_serve_endpoint(spec: str, config: StreamConfig) -> tuple[str, str, int, str]:
    """Backward-compatible wrapper returning ``(url, host, port, path_name)``."""
    d = parse_publish_destination(spec, config)
    return d.url, d.host, d.port, d.path_name


def is_loopback_host(host: str) -> bool:
    h = host.strip("[]").lower().rstrip(".")
    if h == "localhost":
        return True
    try:
        return ip_address(h).is_loopback
    except ValueError:
        return False


def redact_url_credentials(value: str) -> str:
    """Hide a URL password while preserving enough context for useful diagnostics."""
    try:
        parsed = urlparse(value)
    except ValueError:
        return value
    userinfo, separator, hostinfo = parsed.netloc.rpartition("@")
    if not separator or ":" not in userinfo:
        return value
    username, _password = userinfo.split(":", 1)
    safe_netloc = f"{username}:***@{hostinfo}"
    return urlunparse(parsed._replace(netloc=safe_netloc))


def format_url_host(host: str) -> str:
    """Return a hostname suitable for an URL authority, bracketing IPv6 literals."""
    return _format_url_host(host)


def _format_url_host(host: str) -> str:
    clean = host.strip().strip("[]")
    return f"[{clean}]" if ":" in clean else clean


def _validate_port(value: int, *, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise ConfigurationError(f"{context} must be an integer between 1 and 65535")
    return value
