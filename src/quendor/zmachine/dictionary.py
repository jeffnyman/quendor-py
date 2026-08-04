"""The dictionary and lexical analysis (§ 13).

The dictionary is the game's vocabulary, not the interpreter's: the
interpreter only breaks a command into words and reports where each word is
defined. Understanding them is the story file's problem (§ 13.6).
"""

from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V3


class Dictionary:
    """The standard dictionary table (§ 13.1, § 13.2)."""

    def __init__(self, memory: Memory, header: Header, text: TextCodec) -> None:
        self._memory = memory
        self._text = text

        # § 13.2: n, then n word-separator ZSCII codes, then the entry
        # length, then a 2-byte entry count. Entries follow immediately.
        address = header.dictionary_address
        count = memory.read_byte(address)

        self.separators = frozenset(memory.read_bytes(address + 1, count))

        self._entry_length = memory.read_byte(address + 1 + count)
        self._count = memory.read_word(address + 2 + count)
        self._entries = address + 4 + count

        # § 13.3, § 13.4: 6 Z-characters in 4 bytes, or 9 in 6 from V4.
        self._encoded_length = 4 if header.version <= V3 else 6

    def __len__(self) -> int:
        return self._count

    def entry_address(self, index: int) -> int:
        """Byte address of entry `index`, counted from 0."""
        return self._entries + index * self._entry_length

    def word(self, index: int) -> str:
        """Decode entry `index` back into text, for display and tests."""

        encoded = self._memory.read_bytes(
            self.entry_address(index), self._encoded_length
        )

        return self._text.decode_bytes(encoded)

    def lookup(self, word: str) -> int:
        """The entry address for a word, or 0 when it is absent.

        § 13.5 stores entries "in numerical order of the encoded text
        (when the encoded text is regarded as a 32 or 48-bit binary number
        with most-significant byte first)" -- which is exactly bytewise
        order, so encoded text can be binary searched as bytes.
        """

        target = self._text.encode_word(word)
        low, high = 0, self._count - 1

        while low <= high:
            middle = (low + high) // 2
            address = self.entry_address(middle)
            candidate = self._memory.read_bytes(address, self._encoded_length)

            if candidate == target:
                return address

            if candidate < target:
                low = middle + 1
            else:
                high = middle - 1

        return 0


def tokenize(line: str, separators: frozenset[int]) -> list[tuple[str, int]]:
    """Break a command into (word, position) pairs (§ 13.6.1).

    Spaces divide words and are otherwise ignored; separators divide words
    and are words in their own right. Positions count from the start of the
    typed text.
    """

    tokens: list[tuple[str, int]] = []
    word_start: int | None = None

    for index, character in enumerate(line):
        dividing = character == " " or ord(character) in separators

        if not dividing:
            if word_start is None:
                word_start = index
            continue

        if word_start is not None:
            tokens.append((line[word_start:index], word_start))
            word_start = None

        if ord(character) in separators:
            tokens.append((character, index))

    if word_start is not None:
        tokens.append((line[word_start:], word_start))

    return tokens
