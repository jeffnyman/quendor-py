import runpy
import sys
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import pytest
from assertpy import assert_that

from quendor.cli import main
from quendor.zmachine.versions import V1, V2, V3, V6


@pytest.fixture
def story_path(tmp_path: Path, story_data: Callable[..., bytes]) -> Path:
    path = tmp_path / "sample.z3"
    path.write_bytes(story_data(V3))
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


def _header_report(
    data: bytes,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> str:
    path = tmp_path / "story.z"
    path.write_bytes(data)

    exit_code = main([str(path), "--header"])

    assert_that(exit_code).is_equal_to(0)

    return capsys.readouterr().out


def test_header_report_for_a_v3_story(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _header_report(
        story_data(
            V3,
            serial=b"840809",
            flags_1=0b10,
            file_length_words=760,
            checksum=0xA5A0,
            high_memory_base=0x0300,
        ),
        tmp_path,
        capsys,
    )

    assert_that(report).contains("  Version           3")
    assert_that(report).contains("  Serial            840809 (YYMMDD)")
    assert_that(report).contains("  File length       1520 bytes, 16 bytes of padding")
    assert_that(report).contains("  Checksum          $a5a0")
    assert_that(report).contains("status line shows hours:mins")
    assert_that(report).contains("high memory overlaps static memory, which is legal")
    assert_that(report).contains("  Abbreviations     $001c0")
    assert_that(report).contains("  Initial PC        $00500")


def test_header_report_for_a_v1_story(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _header_report(story_data(V1, serial=b"AS000C"), tmp_path, capsys)

    assert_that(report).contains(
        "  Serial            AS000C (V1: field officially unset; § 11.1)"
    )
    assert_that(report).contains(
        "  File length       not recorded (file is 1536 bytes)"
    )
    assert_that(report).does_not_contain("Checksum")
    assert_that(report).does_not_contain("Abbreviations")


def test_header_report_for_a_v2_story(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _header_report(story_data(V2, serial=b"UG3AU5"), tmp_path, capsys)

    assert_that(report).contains("  Serial            UG3AU5\n")


def test_header_report_for_a_v6_story(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _header_report(
        story_data(
            V6,
            initial_pc=0x0100,
            routines_offset=0x0010,
            static_strings_offset=0x0020,
            file_length_words=192,
            checksum=0x1234,
            flags_2=0b1000,
            high_memory_base=0x0600,
        ),
        tmp_path,
        capsys,
    )

    assert_that(report).contains("  File length       1536 bytes\n")
    assert_that(report).contains("game wants to use pictures")
    assert_that(report).does_not_contain("Serial")
    assert_that(report).does_not_contain("overlaps")
    assert_that(report).contains("  Initial routine   $0100 packed -> $00480")
    assert_that(report).contains("  Routines offset   $0010")
    assert_that(report).contains("  Strings offset    $0020")


def test_header_report_flags_an_illegal_memory_layout(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _header_report(story_data(V3, high_memory_base=0x0100), tmp_path, capsys)

    assert_that(report).contains(
        "high memory overlaps dynamic memory, which is illegal"
    )
