"""Stream configuration validation."""

from __future__ import annotations

import pytest

from easy_rtsp.config import StreamConfig
from easy_rtsp.exceptions import ConfigurationError


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("transport", "invalid"),
        ("audio_mode", "invalid"),
        ("preset", "invalid"),
        ("server_port", 0),
        ("webrtc_http_port", 65536),
        ("retry_interval_sec", -0.1),
        ("max_reconnect_attempts", -1),
        ("fps", 0),
        ("hls_segment_time", 0),
    ],
)
def test_invalid_config_fails_early(option: str, value: object) -> None:
    with pytest.raises(ConfigurationError):
        StreamConfig(**{option: value})
