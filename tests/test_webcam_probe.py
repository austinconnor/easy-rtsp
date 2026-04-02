"""Webcam probe timeout."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.exceptions import SourceError
from easy_rtsp.sources.webcam import probe_webcam_dimensions


def test_probe_webcam_timeout_message() -> None:
    with patch("easy_rtsp.sources.webcam.threading.Thread") as m:
        t = MagicMock()
        t.is_alive.return_value = True
        m.return_value = t
        with pytest.raises(SourceError, match="Timed out"):
            probe_webcam_dimensions(0, timeout_sec=0.01)
