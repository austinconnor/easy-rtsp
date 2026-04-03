"""MediaMTX process lifecycle."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.backend import MediaMTXProcess
from easy_rtsp.exceptions import PublishError


def test_mediamtx_start_cleans_config_on_immediate_exit(tmp_path: Path) -> None:
    config_path = tmp_path / "mediamtx.yml"
    config_path.write_text("paths: {}\n", encoding="utf-8")

    proc = MagicMock()
    proc.stderr = BytesIO(b"startup failed")
    proc.poll.return_value = 1
    proc.returncode = 1

    with (
        patch("easy_rtsp.backend.resolve_mediamtx", return_value="/bin/mediamtx"),
        patch("easy_rtsp.backend.subprocess.Popen", return_value=proc),
        patch("easy_rtsp.backend.time.sleep"),
    ):
        with pytest.raises(PublishError, match="startup failed"):
            MediaMTXProcess.start(config_path)

    assert not config_path.exists()
