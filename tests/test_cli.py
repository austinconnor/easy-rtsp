"""CLI smoke tests."""

from __future__ import annotations

import pytest

from easy_rtsp.cli import main


def test_doctor_exits_zero() -> None:
    assert main(["doctor"]) == 0


def test_relay_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["relay", "--help"])
    assert exc.value.code == 0


def test_webcam_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["webcam", "--help"])
    assert exc.value.code == 0


def test_file_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["file", "--help"])
    assert exc.value.code == 0


def test_install_backends_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["install-backends", "--help"])
    assert exc.value.code == 0


def test_file_missing_path_errors(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["file", "nonexistent-file-12345.mp4", "--serve", "live"])
    assert code == 2
    err = capsys.readouterr().err
    assert "not a file" in err
