import runpy
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from assertpy import assert_that

from quendor.cli import main


@pytest.fixture
def story_path(tmp_path: Path) -> Path:
    path = tmp_path / "sample.z3"
    path.write_bytes(b"\x03" + b"\x00" * 63)
    return path


def test_main_reports_success(
    story_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([str(story_path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Quendor Z-Machine Interpreter")


def test_version_flag_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert_that(exit_info.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains(version("quendor"))


def test_module_execution_runs_main(
    story_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["quendor", str(story_path)])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("quendor", run_name="__main__")

    assert_that(exit_info.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Quendor Z-Machine Interpreter")


def test_missing_story_file_is_reported(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([str(tmp_path / "no-such-story.z5")])

    assert_that(exit_code).is_equal_to(1)

    stderr = capsys.readouterr().err
    assert_that(stderr).starts_with("quendor:")
    assert_that(stderr).contains("could not read story file")


def test_unknown_argument_is_rejected() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--not-a-real-option"])

    assert_that(exit_info.value.code).is_equal_to(2)
