"""Command-line interface for Quendor."""

import argparse
from collections.abc import Sequence
from importlib.metadata import version

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Quendor command line.

    Args:
        argv: Argument list to parse. Defaults to ``sys.argv[1:]``.

    Returns:
        A process exit code, where zero indicates success.
    """
    build_parser().parse_args(argv)

    print("Quendor Z-Machine Interpreter")

    return 0
