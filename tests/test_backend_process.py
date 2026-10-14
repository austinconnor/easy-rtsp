"""MediaMTX process lifecycle."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from easy_rtsp.backend import MediaMTXProcess, mediamtx_version
from easy_rtsp.exceptions import PublishError


def _fake_proc(*, exit_code: int | None, output: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.stdout = BytesIO(output)
    proc.poll.return_value = exit_code
    proc.returncode = exit_code
    return proc


def _launch(
    proc: MagicMock,
    tmp_path: Path,
    *,
    version: str = "v1.21.2\n",
    configs: list[str] | None = None,
    **kwargs,
) -> MediaMTXProcess:
    """Run MediaMTXProcess.launch against fake processes, capturing each written config."""

    def fake_mkstemp(suffix: str, prefix: str) -> tuple[int, str]:
        path = tmp_path / f"{prefix}{suffix}"
        path.write_text("", encoding="utf-8")
        return 0, str(path)

    def fake_popen(argv: list[str], **_kwargs) -> MagicMock:
        if configs is not None:
            configs.append(Path(argv[1]).read_text(encoding="utf-8"))
        return proc

    with (
        patch("easy_rtsp.backend.tempfile.mkstemp", side_effect=fake_mkstemp),
        patch("easy_rtsp.backend.os.close"),
        patch(
            "easy_rtsp.backend.subprocess.run",
            return_value=MagicMock(stdout=version, stderr=""),
        ),
        patch("easy_rtsp.backend.subprocess.Popen", side_effect=fake_popen),
        patch("easy_rtsp.backend.time.sleep"),
    ):
        return MediaMTXProcess.launch(
            path_name="live", host="127.0.0.1", port=1, binary="/bin/mediamtx", **kwargs
        )


def test_launch_reports_output_and_cleans_config_on_immediate_exit(tmp_path: Path) -> None:
    proc = _fake_proc(exit_code=1, output=b"ERR listen tcp :8554: bind: address already in use")

    with pytest.raises(PublishError, match="address already in use"):
        _launch(proc, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_launch_times_out_when_listener_never_appears(tmp_path: Path) -> None:
    proc = _fake_proc(exit_code=None)

    with (
        patch("easy_rtsp.backend.wait_for_tcp_listener", return_value=False),
        pytest.raises(PublishError, match="did not listen"),
    ):
        _launch(proc, tmp_path, ready_timeout=0.0)

    proc.terminate.assert_called_once()
    assert list(tmp_path.iterdir()) == []


def test_launch_disables_moq_for_mediamtx_1_19_and_newer(tmp_path: Path) -> None:
    configs: list[str] = []
    with patch("easy_rtsp.backend.wait_for_tcp_listener", return_value=True):
        _launch(_fake_proc(exit_code=None), tmp_path, version="v1.19.0", configs=configs)

    assert "moq: false" in configs[0]


def test_launch_omits_moq_key_for_older_mediamtx(tmp_path: Path) -> None:
    configs: list[str] = []
    with patch("easy_rtsp.backend.wait_for_tcp_listener", return_value=True):
        _launch(_fake_proc(exit_code=None), tmp_path, version="v1.18.1", configs=configs)

    assert "moq" not in configs[0]


def test_stop_removes_generated_config(tmp_path: Path) -> None:
    with patch("easy_rtsp.backend.wait_for_tcp_listener", return_value=True):
        backend = _launch(_fake_proc(exit_code=None), tmp_path)
    assert len(list(tmp_path.iterdir())) == 1

    backend.stop()

    assert list(tmp_path.iterdir()) == []


def test_mediamtx_runs_in_config_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "mediamtx.yml"
    config_path.write_text("paths: {}\n", encoding="utf-8")

    with patch(
        "easy_rtsp.backend.subprocess.Popen", return_value=_fake_proc(exit_code=None)
    ) as popen:
        MediaMTXProcess.start(config_path, binary="/bin/mediamtx")

    assert popen.call_args.kwargs["cwd"] == str(tmp_path)


@pytest.mark.parametrize(
    ("output", "expected"),
    [("v1.21.2\n", (1, 21, 2)), ("1.9.0", (1, 9, 0)), ("garbage", None)],
)
def test_mediamtx_version_parsing(output: str, expected: tuple[int, int, int] | None) -> None:
    with patch(
        "easy_rtsp.backend.subprocess.run", return_value=MagicMock(stdout=output, stderr="")
    ):
        assert mediamtx_version("/bin/mediamtx") == expected


def test_mediamtx_version_is_none_when_binary_fails() -> None:
    with patch("easy_rtsp.backend.subprocess.run", side_effect=OSError("nope")):
        assert mediamtx_version("/bin/mediamtx") is None
