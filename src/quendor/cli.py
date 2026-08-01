"""Command-line interface for Quendor."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from quendor.zmachine.errors import QuendorError
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Quendor command line.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code, where zero indicates success.
    """
    arguments = build_parser().parse_args(argv)

    try:
        Story.from_path(arguments.story)
    except QuendorError as error:
        _fail(str(error))
        return 1

    print("Quendor Z-Machine Interpreter")

    return 0


def _fail(message: str) -> None:
    print(f"{PROGRAM_NAME}: {message}", file=sys.stderr)
