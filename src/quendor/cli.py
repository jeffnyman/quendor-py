"""Command-line interface for Quendor."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from quendor.zmachine.errors import QuendorError
from quendor.zmachine.flags import describe_flags_1, describe_flags_2
from quendor.zmachine.header import Header
from quendor.zmachine.story import Story

PROGRAM_NAME = "quendor"
DESCRIPTION = "A Z-Machine emulator and interpreter."


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser for the ``quendor`` command."""
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME, description=DESCRIPTION)
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('quendor')}",
    )
    parser.add_argument("story", type=Path, help="path to a Z-Machine story file")
    parser.add_argument(
        "--header", action="store_true", help="display the story file's header and exit"
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Quendor command line.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code, where zero indicates success.
    """
    print("Quendor Z-Machine Interpreter")

    arguments = build_parser().parse_args(argv)

    try:
        story = Story.from_path(arguments.story)
    except QuendorError as error:
        _fail(str(error))
        return 1

    if arguments.header:
        print(display_header(story, arguments.story))

    return 0


def display_header(story: Story, path: Path) -> str:
    """Render the header of a loaded story as a human-readable report.

    Laid out to be compared against `infodump` from the ztools suite.

    Numbers follow the notation of the Standard's preface: hexadecimal
    values are written with an initial dollar ($ff) and binary values
    with a double dollar ($$11011).
    """

    header = story.header
    size = len(story.memory)

    lines = ["", f"Header Info for: {path.name}"]
    lines += _story_section(header, size)
    lines += _memory_map_section(header, size)
    lines += _tables_section(header)
    lines += _execution_section(header)

    return "\n".join(lines)


def _story_section(header: Header, size: int) -> list[str]:
    lines = [
        "",
        "Story",
        f"  Version           {header.version}",
        f"  Release           {header.release}",
    ]

    serial = header.serial

    if serial is not None:
        if header.serial_is_compilation_date:
            lines.append(f"  Serial            {serial} (YYMMDD)")
        elif header.serial_is_official:
            lines.append(f"  Serial            {serial}")
        else:
            lines.append(
                f"  Serial            {serial} (V1: field officially unset; § 11.1)"
            )

    file_length = header.file_length

    if file_length is None:
        # Absent before V3, and zero in some early V3 files (§ 11.1, § 11.1.6).
        lines.append(f"  File length       not recorded (file is {size} bytes)")
    else:
        padding = size - file_length
        note = f", {padding} bytes of padding" if padding else ""
        lines.append(f"  File length       {file_length} bytes{note}")

    checksum = header.checksum

    if checksum is not None:
        lines.append(f"  Checksum          ${checksum:04x}")

    flags_1 = header.flags_1
    lines.append(f"  Flags 1           ${flags_1:02x}  $${flags_1:08b}")
    lines.extend(
        f"                    {label}"
        for label in describe_flags_1(header.version, flags_1)
    )

    flags_2 = header.flags_2
    lines.append(f"  Flags 2           ${flags_2:04x}  $${flags_2:016b}")
    lines.extend(
        f"                    {label}"
        for label in describe_flags_2(header.version, flags_2)
    )

    return lines


def _memory_map_section(header: Header, size: int) -> list[str]:
    # Static memory ends at $ffff or the end of the file, whichever is
    # lower (§ 1.1); the end address here is exclusive.
    static_end = min(size, 0x10000)

    lines = [
        "",
        "Memory map (§ 1.1)",
        f"  Dynamic           ${0:05x} - ${header.static_memory_base - 1:05x}",
        f"  Static            ${header.static_memory_base:05x} - ${static_end - 1:05x}",
        f"  High              ${header.high_memory_base:05x} - ${size - 1:05x}",
    ]

    # The bottom of high memory may overlap the top of static memory, and
    # many Infocom games rely on it, but must not reach dynamic memory
    # (§ 1.1). Note either arrangement so neither reads as a display bug.
    if header.high_memory_base < header.static_memory_base:
        lines.append(
            "  note: high memory overlaps dynamic memory, which is illegal (§ 1.1)"
        )
    elif header.high_memory_base < static_end:
        lines.append(
            "  note: high memory overlaps static memory, which is legal (§ 1.1)"
        )

    return lines


def _tables_section(header: Header) -> list[str]:
    lines = [
        "",
        "Tables (§ 11.1)",
        f"  Dictionary        ${header.dictionary_address:05x}",
        f"  Object table      ${header.object_table_address:05x}",
        f"  Global variables  ${header.global_variables_address:05x}",
    ]

    abbreviations = header.abbreviations_address

    if abbreviations is not None:
        lines.append(f"  Abbreviations     ${abbreviations:05x}")

    return lines


def _execution_section(header: Header) -> list[str]:
    lines = ["", "Execution"]

    if header.has_main_routine:
        packed = header.initial_program_counter
        unpacked = header.unpack_routine_address(packed)
        lines.append(f"  Initial routine   ${packed:04x} packed -> ${unpacked:05x}")
    else:
        lines.append(f"  Initial PC        ${header.initial_program_counter:05x}")

    if header.unpacks_with_offsets:
        lines += [
            f"  Routines offset   ${header.routines_offset:04x}",
            f"  Strings offset    ${header.static_strings_offset:04x}",
        ]

    return lines


def _fail(message: str) -> None:
    print(f"{PROGRAM_NAME}: {message}", file=sys.stderr)
