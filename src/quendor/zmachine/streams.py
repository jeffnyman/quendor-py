"""Output streams (§ 7)."""

from dataclasses import dataclass, field
from typing import Final

from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory
from quendor.zmachine.screen import ScreenModel
from quendor.zmachine.text import TextCodec

"""§ 7.1.2.2.1: newlines reach stream 3 as ZSCII 13, never 10."""
ZSCII_NEWLINE: Final = 13

"""§ 7.5.3: anything with no ZSCII code becomes a question mark."""
UNPRINTABLE: Final = ord("?")


@dataclass
class MemoryStream:
    """One selection of stream 3: a table being filled (§ 7.1.2.1)."""

    table: int
    characters: list[int] = field(default_factory=list)

    """§ 15's Version 6 operand. None means the table holds plain text; a
        number means it holds *formatted* text, laid out to that width."""
    width: int | None = None


class OutputStreams:
    """Routes printed text to whichever streams are selected (§ 7)."""

    def __init__(
        self, memory: Memory, header: Header, display: ScreenModel, text: TextCodec
    ) -> None:
        self._memory = memory
        self._header = header
        self._display = display
        self._text = text

        #: Whether anything has been printed since this was last cleared.
        #: § 15 uses it to tell whether an interrupt routine printed, so
        #: the input line can be redrawn. Viola keeps the same flag.
        self.printed = False

        self._tables: list[MemoryStream] = []

    # -- Selection (§ 7.3, § 7.4) --------------------------------------

    @property
    def redirected(self) -> bool:
        """Whether stream 3 is swallowing everything (§ 7.1.2.2)."""
        return bool(self._tables)

    # -- Printing ------------------------------------------------------

    def write(self, text: str) -> None:
        """Send text to every selected stream (§ 7.1).

        Stream 3 takes precedence over everything: while it is selected the
        other streams see nothing at all (§ 7.1.2.2).
        """

        if text:
            self.printed = True

        if self.redirected:
            self._tables[-1].characters.extend(self._to_zscii(text))
            return

        self._display.write(text)

    def _to_zscii(self, text: str) -> list[int]:
        codes = []

        for character in text:
            if character == "\n":
                # § 7.1.2.2.1: never ZSCII 10.
                codes.append(ZSCII_NEWLINE)
                continue

            code = self._text.zscii_for(character)

            # § 7.5.3: a character with no ZSCII code becomes '?'.
            codes.append(code if code else UNPRINTABLE)

        return codes
