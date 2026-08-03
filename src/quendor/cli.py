"""Command-line interface for Quendor."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from quendor.zmachine.errors import QuendorError
from quendor.zmachine.flags import describe_flags_1, describe_flags_2
from quendor.zmachine.header import Header
from quendor.zmachine.instructions import Decoder, Instruction, Operand, OperandType
from quendor.zmachine.story import Story
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V6

PROGRAM_NAME = "quendor"
DESCRIPTION = "A Z-Machine emulator and interpreter."

# Variable numbers partition at $0f: $00 is the stack, $01 to $0f the
# current routine's locals, and $10 to $ff the globals (§ 4.2.2).
LAST_LOCAL_VARIABLE = 0x0F
FIRST_GLOBAL_VARIABLE = 0x10


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
    parser.add_argument(
        "--disassemble", action="store_true", help="decode instructions from story file"
    )
    parser.add_argument(
        "--start",
        type=lambda value: int(value, 16),
        metavar="ADDR",
        help="hex byte address to disassemble from",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=16,
        metavar="N",
        help="number of instructions to disassemble (default: 16)",
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

    if arguments.disassemble:
        if arguments.header:
            print()

        start = arguments.start

        if start is None:
            start = first_instruction_address(story)

        print(format_disassembly(story, start, arguments.count))

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


def first_instruction_address(story: Story) -> int:
    """Where execution begins (§ 11.1).

    In most Versions the header holds a byte address pointing straight at an
    instruction. Version 6 instead holds the packed address of a "main"
    routine, and a routine begins with a header rather than with code: one
    byte giving the local variable count, followed in V1-4 by two bytes of
    initial value per local (§ 5.2). V6 is past that, so one byte is enough.
    """

    header = story.header

    if header.version != V6:
        return header.initial_program_counter

    routine = header.unpack_routine_address(header.initial_program_counter)

    return routine + 1


def format_disassembly(story: Story, start: int, count: int) -> str:
    """Disassemble `count` instructions starting at `start`, one per line.

    Each line shows the address, the raw bytes, and the decoded instruction,
    in roughly txd's layout. A decoding failure ends the listing with the
    error inline, keeping everything already decoded on screen.
    """

    lines = []
    address = start

    decoder = Decoder(story.memory, story.header.version)
    text = TextCodec(story.memory, story.header)

    for _ in range(count):
        try:
            instruction = decoder.decode(address)
        except QuendorError as error:
            lines.append(f"${address:05x}:  <{error}>")
            break

        raw = story.memory.read_bytes(instruction.address, instruction.length)

        lines.append(
            f"${address:05x}:  {raw.hex(' '):<24}"
            f"  {format_instruction(instruction, text)}"
        )

        address = instruction.next_address

    return "\n".join(lines)


def format_instruction(instruction: Instruction, text: TextCodec) -> str:
    """One line of disassembly: mnemonic, operands, store, branch, text."""

    parts = [instruction.name.upper().ljust(16)]

    if instruction.operands:
        parts.append(",".join(format_operand(o) for o in instruction.operands))

    if instruction.store is not None:
        parts.append(f"-> {format_variable(instruction.store)}")

    if instruction.branch is not None:
        condition = "TRUE" if instruction.branch.on_true else "FALSE"
        target = instruction.branch_target

        if target is None:
            # Offsets 0 and 1 return instead of jumping (§ 4.7.1).
            destination = "RFALSE" if instruction.branch.returns_false else "RTRUE"
        else:
            destination = f"${target:05x}"

        parts.append(f"[{condition}] {destination}")

    if instruction.text is not None:
        # § 4.8 inline text, decoded through § 3.
        parts.append(format_string(text.decode_bytes(instruction.text)))

    if instruction.out_of_version:
        parts.append("  ! opcode postdates this Version (§ 14.2)")

    return " ".join(parts).rstrip()


def format_string(text: str) -> str:
    """Render decoded text on one line, so a disassembly stays scannable."""

    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def format_operand(operand: Operand) -> str:
    """Render an operand: constants as `#hex`, variables by name."""

    if operand.type is OperandType.VARIABLE:
        return format_variable(operand.value)
    if operand.type is OperandType.LARGE_CONSTANT:
        return f"#{operand.value:04x}"

    return f"#{operand.value:02x}"


def format_variable(number: int) -> str:
    """Name a variable by number (§ 4.2.2).

    Locals and globals are numbered from 0 here, matching txd's output, so
    that disassemblies can be compared side by side (§ 14, Remarks).
    """

    if number == 0:
        return "sp"
    if number <= LAST_LOCAL_VARIABLE:
        return f"L{number - 1:02x}"

    return f"G{number - FIRST_GLOBAL_VARIABLE:02x}"


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
