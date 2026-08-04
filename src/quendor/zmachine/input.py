"""Where typed input comes from: the frontend boundary."""

from collections.abc import Sequence
from typing import Protocol

from quendor.zmachine.errors import EndOfInputError


class Keyboard(Protocol):
    """Somewhere typed input comes from (input stream 0, § 15)."""

    def read_line(self, maximum: int) -> str:
        """Read one line of at most `maximum` characters, without its newline.

        Raises:
            EndOfInputError: The input is closed; nobody is there.
        """
        ...


class ScriptedKeyboard:
    """A keyboard that replays a fixed list of lines.

    Used by tests and by anything driving a story without a person present.
    Running out of script raises `EndOfInputError`, which mirrors what a
    real terminal reports when its input is closed.
    """

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines = list(lines)

    def read_line(self, maximum: int) -> str:
        """Replay the next line, trimmed as a real read would trim it."""

        if not self._lines:
            message = "the script has no more input"
            raise EndOfInputError(message)

        return self._lines.pop(0)[:maximum]
