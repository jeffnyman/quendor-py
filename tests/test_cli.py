import runpy
from importlib.metadata import version

import pytest
from assertpy import assert_that

from quendor.cli import main


def test_main_reports_success(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Quendor Z-Machine Interpreter")


def test_version_flag_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert_that(exit_info.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains(version("quendor"))


def test_module_execution_runs_main(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("quendor", run_name="__main__")

    assert_that(exit_info.value.code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("Quendor Z-Machine Interpreter")


def test_unknown_argument_is_rejected() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--not-a-real-option"])

    assert_that(exit_info.value.code).is_equal_to(2)
