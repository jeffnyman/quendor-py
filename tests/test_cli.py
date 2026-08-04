import runpy
import sys
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import pytest
from assertpy import assert_that

from quendor.cli import (
    first_instruction_address,
    format_operand,
    format_string,
    format_variable,
    main,
)
from quendor.zmachine.instructions import Operand, OperandType
from quendor.zmachine.interpreter import Interpreter
from quendor.zmachine.story import Story
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
    # Inspection rather than a bare run: running a story is the interpreter's
    # young, still-forming contract, while the banner and exit code of an
    # inspection are settled behavior.
    exit_code = main([str(story_path), "--header"])

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
    monkeypatch.setattr(sys, "argv", ["quendor", str(story_path), "--header"])

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


def test_format_variable_names_all_three_kinds() -> None:
    assert_that(format_variable(0x00)).is_equal_to("sp")
    assert_that(format_variable(0x01)).is_equal_to("L00")
    assert_that(format_variable(0x0F)).is_equal_to("L0e")
    assert_that(format_variable(0x10)).is_equal_to("G00")
    assert_that(format_variable(0xFF)).is_equal_to("Gef")


def test_format_operand_shapes() -> None:
    variable = Operand(OperandType.VARIABLE, 1)
    large = Operand(OperandType.LARGE_CONSTANT, 0x1234)
    small = Operand(OperandType.SMALL_CONSTANT, 5)

    assert_that(format_operand(variable)).is_equal_to("L00")
    assert_that(format_operand(large)).is_equal_to("#1234")
    assert_that(format_operand(small)).is_equal_to("#05")


def test_format_string_escapes_for_one_line() -> None:
    assert_that(format_string('a"b\nc\\d')).is_equal_to('"a\\"b\\nc\\\\d"')


def test_first_instruction_address(story_data: Callable[..., bytes]) -> None:
    v3 = Story(story_data(V3))

    assert_that(first_instruction_address(v3)).is_equal_to(0x0500)

    # The V6 main routine sits at 4P + 8R_O = $0480; one more byte skips
    # its local-count header (§ 5.2).
    v6 = Story(story_data(V6, initial_pc=0x0100, routines_offset=0x10))

    assert_that(first_instruction_address(v6)).is_equal_to(0x0481)


def _with_code(
    story_data: Callable[..., bytes],
    code: bytes,
    version: int = V3,
) -> bytes:
    data = bytearray(story_data(version))
    data[0x0500 : 0x0500 + len(code)] = code

    return bytes(data)


def _disassembly(
    data: bytes,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *arguments: str,
) -> str:
    path = tmp_path / "story.z3"
    path.write_bytes(data)

    exit_code = main([str(path), "--disassemble", *arguments])

    assert_that(exit_code).is_equal_to(0)

    return capsys.readouterr().out


def test_disassembly_lists_instructions(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    program = (
        bytes([0x14, 0x05, 0x0A, 0x00])  # add #05,#0a -> sp
        + bytes([0x90, 0x2A, 0xC5])  # jz #2a [TRUE] $0050a
        + bytes([0xB2, 0xB5, 0xC5])  # print "hi"
        + bytes([0xB0])  # rtrue
    )

    out = _disassembly(_with_code(story_data, program), tmp_path, capsys)

    assert_that(out).contains("$00500:  14 05 0a 00")
    assert_that(out).contains("ADD")
    assert_that(out).contains("#05,#0a")
    assert_that(out).contains("-> sp")
    assert_that(out).contains("[TRUE] $0050a")
    assert_that(out).contains('"hi"')
    assert_that(out).contains("RTRUE")

    # The zeroes after the program are not an opcode; the listing ends
    # with the error inline rather than discarding what decoded.
    assert_that(out).contains("not an opcode")


def test_disassembly_shows_return_branches(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    program = bytes([0x90, 0x00, 0xC0])

    out = _disassembly(
        _with_code(story_data, program), tmp_path, capsys, "--count", "1"
    )

    assert_that(out).contains("[TRUE] RFALSE")


def test_disassembly_flags_early_opcodes(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    program = bytes([0xBF, 0xC0])  # piracy, V5-only, in a V3 story

    out = _disassembly(
        _with_code(story_data, program), tmp_path, capsys, "--count", "1"
    )

    assert_that(out).contains("PIRACY")
    assert_that(out).contains("! opcode postdates this Version (§ 14.2)")


def test_disassembly_start_address_is_hex(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    program = bytes([0x14, 0x05, 0x0A, 0x00, 0xB0])

    out = _disassembly(
        _with_code(story_data, program),
        tmp_path,
        capsys,
        "--start",
        "504",
        "--count",
        "1",
    )

    assert_that(out).contains("$00504")
    assert_that(out).does_not_contain("ADD")


def test_running_a_story_reports_the_frontier(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A bare invocation runs the interpreter. The fixture's program area is
    # zeroes, which is not decodable, and the failure lands on stderr.
    path = tmp_path / "story.z3"
    path.write_bytes(story_data(V3))

    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(1)
    assert_that(capsys.readouterr().err).contains("not an opcode")


def test_running_a_story_reports_unimplemented_opcodes(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Strip rtrue's handler so an unimplemented opcode exists to report,
    # however complete the interpreter becomes. The frontier message names
    # the method to write.
    monkeypatch.delattr(Interpreter, "_op_rtrue")

    data = bytearray(story_data(V3))
    data[0x0500] = 0xB0

    path = tmp_path / "story.z3"
    path.write_bytes(bytes(data))

    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(1)
    assert_that(capsys.readouterr().err).contains("define `Interpreter._op_rtrue`")


def test_a_story_plays_through_to_the_end(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The first complete playthrough: print "hi", then quit. Exit code 0
    # and the story's own words on stdout.
    data = bytearray(story_data(V3))
    data[0x0500:0x0504] = bytes([0x8D, 0x01, 0x80, 0xBA])  # print_paddr; quit
    data[0x0300:0x0302] = bytes([0xB5, 0xC5])  # "hi", packed at $0180

    path = tmp_path / "story.z3"
    path.write_bytes(bytes(data))

    exit_code = main([str(path)])

    assert_that(exit_code).is_equal_to(0)
    assert_that(capsys.readouterr().out).contains("hi")


def test_running_a_story_that_stops_exits_cleanly(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No opcode handler can stop the machine yet, so stop it by decree: the
    # clean-exit contract is worth pinning before quit exists.
    monkeypatch.setattr(Interpreter, "run", lambda _self: None)

    path = tmp_path / "story.z3"
    path.write_bytes(story_data(V3))

    assert_that(main([str(path)])).is_equal_to(0)


def test_header_and_disassembly_combine(
    story_data: Callable[..., bytes],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    program = bytes([0xB0])

    out = _disassembly(
        _with_code(story_data, program), tmp_path, capsys, "--header", "--count", "1"
    )

    assert_that(out).contains("Header Info for:")
    assert_that(out).contains("RTRUE")
