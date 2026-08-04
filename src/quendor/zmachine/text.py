"""Decoding text (§ 3)."""

from typing import Final

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory
from quendor.zmachine.versions import V2, V3, V6

A0 = 0
A1 = 1
A2 = 2

"""§ 3.3.1: an abbreviation may not itself use abbreviations."""
MAXIMUM_ABBREVIATION_DEPTH: Final = 1

"""Z-character 6 from A2 introduces a ten-bit ZSCII code (§ 3.4)."""
ESCAPE_ZCHAR: Final = 6

"""Z-characters 1 to 3 select an abbreviation bank from V3 (§ 3.3)."""
LAST_ABBREVIATION_ZCHAR: Final = 3

"""Z-characters 4 and 5 shift to A1 or A2 for one character (§ 3.2.3)."""
SHIFT_TO_A1: Final = 4
SHIFT_TO_A2: Final = 5

"""ZSCII agrees with ASCII from space up to tilde (§ 3.8.3)."""
LAST_ASCII_MATCHING_ZSCII: Final = 126

FIRST_ALPHABET_ZCHAR: Final = 6
FIRST_EXTRA_CHARACTER: Final = 155
LAST_EXTRA_CHARACTER: Final = 251
ZSCII_SPACE: Final = 32
ZSCII_NEWLINE: Final = 13
ZSCII_TAB: Final = 9
ZSCII_SENTENCE_SPACE: Final = 11

"""Set on the last word of a string (§ 3.2)."""
END_BIT: Final = 0x8000

# § 3.5.4: Version 1 needs no newline in A2, which frees a slot for '<'.
V1_A2: Final = "\x00" + "0123456789.,!?_#'\"/\\<-:()"

"""EM QUAD: the closest Unicode has to a typographic sentence gap."""
SENTENCE_SPACE_CHARACTER: Final = chr(0x2001)

"""Entry 32(z-1)+x of the abbreviations table (§ 3.3)."""
ABBREVIATIONS_PER_BANK: Final = 32

"""Each alphabet covers Z-characters 6 to 31 (§ 3.5.3)."""
ALPHABET_SIZE: Final = 26

"""78 bytes: three blocks of 26 ZSCII values (§ 3.5.5.1)."""
CUSTOM_ALPHABET_SIZE: Final = 3 * ALPHABET_SIZE

# § 3.5.3. Position 0 of each row is Z-character 6. In A2 that slot is the
# ZSCII escape and is never looked up here, so it holds a null placeholder.
DEFAULT_A0: Final = "abcdefghijklmnopqrstuvwxyz"
DEFAULT_A1: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DEFAULT_A2: Final = "\x00\r0123456789.,!?_#'\"/\\-:()"

# § 3.8.5.3, Table 1: the default Unicode translation table. Verified
# character for character against Viola, which agrees exactly.
DEFAULT_UNICODE_TABLE: Final[dict[int, int]] = {
    155: 0x00E4, 156: 0x00F6, 157: 0x00FC, 158: 0x00C4, 159: 0x00D6,
    160: 0x00DC, 161: 0x00DF, 162: 0x00BB, 163: 0x00AB, 164: 0x00EB,
    165: 0x00EF, 166: 0x00FF, 167: 0x00CB, 168: 0x00CF, 169: 0x00E1,
    170: 0x00E9, 171: 0x00ED, 172: 0x00F3, 173: 0x00FA, 174: 0x00FD,
    175: 0x00C1, 176: 0x00C9, 177: 0x00CD, 178: 0x00D3, 179: 0x00DA,
    180: 0x00DD, 181: 0x00E0, 182: 0x00E8, 183: 0x00EC, 184: 0x00F2,
    185: 0x00F9, 186: 0x00C0, 187: 0x00C8, 188: 0x00CC, 189: 0x00D2,
    190: 0x00D9, 191: 0x00E2, 192: 0x00EA, 193: 0x00EE, 194: 0x00F4,
    195: 0x00FB, 196: 0x00C2, 197: 0x00CA, 198: 0x00CE, 199: 0x00D4,
    200: 0x00DB, 201: 0x00E5, 202: 0x00C5, 203: 0x00F8, 204: 0x00D8,
    205: 0x00E3, 206: 0x00F1, 207: 0x00F5, 208: 0x00C3, 209: 0x00D1,
    210: 0x00D5, 211: 0x00E6, 212: 0x00C6, 213: 0x00E7, 214: 0x00C7,
    215: 0x00FE, 216: 0x00F0, 217: 0x00DE, 218: 0x00D0, 219: 0x00A3,
    220: 0x0153, 221: 0x0152, 222: 0x00A1, 223: 0x00BF,
}  # fmt: skip


class TextCodec:
    """Turns encoded Z-machine strings into Python text."""

    def __init__(self, memory: Memory, header: Header) -> None:
        self._memory = memory
        self._header = header
        self._version = header.version
        self._alphabets = self._build_alphabets()
        self._unicode = self._build_unicode_table()

    # -- Setup ---------------------------------------------------------

    def _build_alphabets(self) -> tuple[tuple[int, ...], ...]:
        address = self._header.alphabet_table_address

        if address == 0:
            return self._default_alphabets(self._version)

        # § 3.5.5.1: 78 bytes, three blocks of 26 ZSCII values.
        raw = self._memory.read_bytes(address, CUSTOM_ALPHABET_SIZE)
        rows = [
            list(raw[block * ALPHABET_SIZE : (block + 1) * ALPHABET_SIZE])
            for block in range(3)
        ]

        # "Z-characters 6 and 7 of A2, however, are still translated as ZSCII
        # escape and new-line codes" -- overridden by position, not by value.
        # Viola replaces every byte matching the one at slot 7, which would
        # also rewrite any later slot holding the same character.
        rows[A2][0] = 0
        rows[A2][1] = ZSCII_NEWLINE

        return tuple(tuple(row) for row in rows)

    def _build_unicode_table(self) -> dict[int, int]:
        address = self._header.unicode_translation_table_address

        if address == 0:
            return dict(DEFAULT_UNICODE_TABLE)

        # § 3.8.5.2.1: one byte giving N, then N words. This *replaces* the
        # default table rather than extending it, so codes past 155+N-1 are
        # left undefined (§ 3.8.5.2.2).
        count = self._memory.read_byte(address)

        return {
            FIRST_EXTRA_CHARACTER + index: self._memory.read_word(
                address + 1 + 2 * index
            )
            for index in range(count)
        }

    def _default_alphabets(self, version: int) -> tuple[tuple[int, ...], ...]:
        """The built-in alphabet table for a Version (§ 3.5.3, § 3.5.4)."""

        a2 = V1_A2 if version == 1 else DEFAULT_A2

        return tuple(
            tuple(ord(character) for character in row)
            for row in (DEFAULT_A0, DEFAULT_A1, a2)
        )

    # -- Whole strings -------------------------------------------------

    def decode(self, address: int) -> str:
        """Decode the string beginning at a byte address."""
        return self.decode_with_length(address)[0]

    def decode_with_length(self, address: int) -> tuple[str, int]:
        """Decode a string, also reporting how many bytes it occupied."""
        zchars, next_address = self._read_zchars(address)
        text = self._zscii_to_text(self._zchars_to_zscii(zchars))
        return text, next_address - address

    def decode_bytes(self, encoded: bytes) -> str:
        """Decode a string already lifted out of memory, as § 4.8 text is."""

        zchars: list[int] = []

        for offset in range(0, len(encoded), 2):
            word = (encoded[offset] << 8) | encoded[offset + 1]

            zchars += [
                (word >> 10) & 0b11111,
                (word >> 5) & 0b11111,
                word & 0b11111,
            ]

        return self._zscii_to_text(self._zchars_to_zscii(zchars))

    # -- Stage one: Z-characters ---------------------------------------

    def _read_zchars(
        self, address: int, max_bytes: int | None = None
    ) -> tuple[list[int], int]:
        """Read the Z-characters of a string, and the address after it.

        Three per word, most significant first, ending with the word whose
        top bit is set (§ 3.2).

        `max_bytes` caps the read for text of a known fixed extent. Ordinary
        strings never need it, but dictionary entries do: their length comes
        from the dictionary's resolution rather than from an end bit (§ 3.7),
        and some genuinely omit the bit. Two entries in the 1981 Version 1
        Zork I do exactly that, and reading them to an end bit runs on
        through whatever follows.
        """
        zchars: list[int] = []
        read = 0

        while True:
            word = self._memory.read_word(address)
            address += 2
            read += 2

            zchars += [
                (word >> 10) & 0b11111,
                (word >> 5) & 0b11111,
                word & 0b11111,
            ]

            if word & END_BIT:
                return zchars, address

            if max_bytes is not None and read >= max_bytes:
                return zchars, address

    def _abbreviation(self, bank: int, index: int, depth: int) -> list[int]:
        """Expand abbreviation 32(z-1)+x (§ 3.3)."""

        # `_is_abbreviation` admits no z-character in V1, the only Version
        # without a table, so a missing table here means a broken story.
        base = self._header.abbreviations_address

        if base is None:
            message = "abbreviation used but this Version has no table (§ 3.3)"
            raise StoryFileError(message)

        entry = ABBREVIATIONS_PER_BANK * (bank - 1) + index
        address = base + 2 * entry

        # The table holds word addresses, the only place they are used
        # (§ 1.2.2).
        target = self._memory.read_word(address) * 2
        zchars, _ = self._read_zchars(target)

        return self._zchars_to_zscii(zchars, depth + 1)

    def _is_abbreviation(self, zchar: int) -> bool:
        """§ 3.3: banks 1-3 from V3, bank 1 only in V2, none in V1."""

        if self._version >= V3:
            return 1 <= zchar <= LAST_ABBREVIATION_ZCHAR

        return self._version == V2 and zchar == 1

    def _shift(self, zchar: int, current: int, locked: int) -> tuple[int, int] | None:
        """Apply a shift Z-character, returning the new (current, locked).

        Returns None if this Z-character is not a shift at all.
        """
        if self._version >= V3:
            # § 3.2.3: 4 and 5 shift the next character only; no locks.
            if zchar == SHIFT_TO_A1:
                return A1, locked
            if zchar == SHIFT_TO_A2:
                return A2, locked
            return None

        # § 3.2.2: in V1 and V2 the alphabets rotate. Z-characters 2 and 4
        # move one step forward, 3 and 5 two steps; 2 and 3 last for a single
        # character, 4 and 5 lock.
        if zchar in (2, 3):
            return (current + zchar - 1) % 3, locked

        if zchar in (4, 5):
            target = (current + zchar - 3) % 3
            return target, target

        return None

    # -- Stage two: ZSCII ----------------------------------------------

    def _zscii_to_text(self, codes: list[int]) -> str:
        """Convert ZSCII codes to Unicode text (§ 3.8)."""

        return "".join(self._character(code) for code in codes)

    def _zchars_to_zscii(self, zchars: list[int], depth: int = 0) -> list[int]:
        """Convert Z-characters to ZSCII codes (§ 3.2 to § 3.6)."""

        codes: list[int] = []
        current = A0
        locked = A0
        pending = iter(zchars)

        for zchar in pending:
            # Abbreviations consume the following Z-character (§ 3.3).
            if self._is_abbreviation(zchar):
                index = next(pending, None)
                # § 3.6.1: a string may end mid-construction; ignore it.
                if index is None:
                    break
                if depth < MAXIMUM_ABBREVIATION_DEPTH:
                    codes += self._abbreviation(zchar, index, depth)
                continue

            if self._version == 1 and zchar == 1:
                # § 3.5.2: Z-character 1 is a newline in Version 1 alone.
                codes.append(ZSCII_NEWLINE)
                current = locked
                continue

            shifted = self._shift(zchar, current, locked)
            if shifted is not None:
                current, locked = shifted
                continue

            if zchar == 0:
                # § 3.5.1: Z-character 0 is always a space.
                codes.append(ZSCII_SPACE)
                current = locked
                continue

            if current == A2 and zchar == ESCAPE_ZCHAR:
                # § 3.4: the next two Z-characters give a ten-bit code.
                top = next(pending, None)
                bottom = next(pending, None)

                if top is None or bottom is None:
                    break  # § 3.6.1 again

                codes.append((top << 5) | bottom)
                current = locked

                continue

            codes.append(self._alphabets[current][zchar - FIRST_ALPHABET_ZCHAR])
            current = locked

        return codes

    def _character(self, code: int) -> str:
        # § 3.8.2.1: null is defined for output but has no effect.
        if code == 0:
            return ""

        if code == ZSCII_NEWLINE:
            return "\n"

        if code == ZSCII_TAB and self._version == V6:
            # § 3.8.2.3: defined for output in V6 only.
            return "\t"

        if code == ZSCII_SENTENCE_SPACE and self._version == V6:
            # § 3.8.2.4: a typographic gap between sentences, wider than a
            # word space. EM QUAD is the closest thing Unicode offers.
            return SENTENCE_SPACE_CHARACTER

        if ZSCII_SPACE <= code <= LAST_ASCII_MATCHING_ZSCII:
            # § 3.8.3: agrees with ASCII throughout this range.
            return chr(code)

        if FIRST_EXTRA_CHARACTER <= code <= LAST_EXTRA_CHARACTER:
            unicode_code = self._unicode.get(code)
            return "" if unicode_code is None else chr(unicode_code)

        # Everything else is undefined for output (§ 3.8). Dropping it keeps
        # decoding total, which matters when walking data that may not be
        # text at all.
        return ""

    # -- Encoding, for dictionary lookup (§ 3.7) -----------------------

    def zscii_for(self, character: str) -> int:
        """The ZSCII code for a character (§ 3.8), or 0 if undefined.

        "Undefined" covers anything that is not one character. A keyboard has
        to answer `read_char` with something, and a terminal reports an arrow
        key as an escape sequence three bytes long; § 3.8 gives that no code,
        which is an answer rather than an error.
        """

        if len(character) != 1:
            return 0

        code = ord(character)

        if ZSCII_SPACE <= code <= LAST_ASCII_MATCHING_ZSCII:
            return code

        if character == "\n":
            return ZSCII_NEWLINE

        for zscii, unicode_code in self._unicode.items():
            if unicode_code == code:
                return zscii

        return 0
