"""The screen model (§ 8)."""

from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory
from quendor.zmachine.output import Screen


class ScreenModel:
    """The § 8 screen state, and the operations the opcodes perform on it."""

    def __init__(self, memory: Memory, header: Header, screen: Screen) -> None:
        self._memory = memory
        self._header = header
        self._screen = screen

    # -- Printing ------------------------------------------------------

    def write(self, text: str) -> None:
        """Show text on the screen.

        For now this forwards straight to the frontend; the window and
        cursor bookkeeping of § 8 will land here as opcodes need it.
        """
        self._screen.write(text)
