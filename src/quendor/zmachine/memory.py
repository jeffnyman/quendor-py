"""The Z-Machine memory map (§ 1).

Memory is a flat array of bytes with addresses running from 0 upward, divided
into three regions (§ 1.1):

    dynamic    $0000 .. static_memory_base - 1    the game may read and write
    static     static_memory_base .. end of file  the game may only read
    high       high_memory_base .. end of file    not directly addressable

High memory holds routines and strings. It may overlap the top of static
memory but never dynamic memory (§ 1.1), and because that overlap is legal --
some Infocom games interleave data among their routines -- there is no
boundary to enforce at the high memory mark. The only access rule this class
polices is the dynamic/static one.
"""

from typing import Final

from quendor.zmachine.errors import MemoryAccessError, StoryFileError

"""By tradition the first 64 bytes of dynamic memory are the header (§ 1.1.1.1)."""
HEADER_SIZE: Final = 0x40

"""Words hold any value in the range $0000 to $ffff (§ 2.1)."""
MAXIMUM_WORD: Final = 0xFFFF

# These two offsets mirror header.py's § 11.1 table. Memory sits beneath
# Header -- header.py imports this module -- so importing them back would
# be circular, and Memory needs both before any Header can exist: the
# static base to enforce the § 1.1 write rules, and Flags 2 to preserve
# it across a restart (§ 6.1.3).
FLAGS_2_FIELD: Final = 0x10
STATIC_MEMORY_BASE_FIELD: Final = 0x0E


class Memory:
    """The story file's bytes, with the access rules of § 1.1 applied."""

    def __init__(self, data: bytes) -> None:
        if len(data) < HEADER_SIZE:
            message = (
                f"story file is {len(data)} bytes; "
                f"a header alone requires {HEADER_SIZE} (§ 1.1.1.1)"
            )
            raise StoryFileError(message)

        self._data = bytearray(data)

        # Keep the story file exactly as it was loaded. The game rewrites
        # dynamic memory as it runs, but two operations need the original
        # bytes: `restart` restores the state "from the original story file"
        # (§ 6.1.3), and `verify` checksums the file as shipped (§ 15). Both
        # would be wrong if computed against memory the game had touched.
        self._original = bytes(data)

        # The static memory base is not marked "Dyn" in the header table, so
        # the game may not legally change it and an interpreter is free to
        # keep its own copy (§ 11.1.1).
        self._static_memory_base = int.from_bytes(
            self._data[STATIC_MEMORY_BASE_FIELD : STATIC_MEMORY_BASE_FIELD + 2],
            "big",
        )

        # The base is consulted on every write and on restart, so a nonsense
        # value is rejected at construction rather than trusted. Dynamic
        # memory holds the header and must physically exist in the file
        # (§ 1.1); its base is also the only free variable in the famous 64K
        # dynamic-plus-static ceiling, which is otherwise capped by
        # definition.
        if self._static_memory_base < HEADER_SIZE:
            message = (
                f"static memory begins at ${self._static_memory_base:05x}, "
                f"inside the {HEADER_SIZE}-byte header; dynamic memory must "
                f"contain at least {HEADER_SIZE} bytes (§ 1.1)"
            )
            raise StoryFileError(message)

        if self._static_memory_base > len(data):
            message = (
                f"static memory begins at ${self._static_memory_base:05x} "
                f"but the file ends at ${len(data) - 1:05x}; dynamic memory "
                f"cannot extend past the end of the file (§ 1.1)"
            )
            raise StoryFileError(message)

    def __len__(self) -> int:
        return len(self._data)

    @property
    def static_memory_base(self) -> int:
        """First address the game may not write to (§ 1.1)."""
        return self._static_memory_base

    def read_bytes(self, address: int, length: int) -> bytes:
        """Read a run of bytes starting at a byte address."""

        if length < 0:
            message = f"cannot read {length} bytes"
            raise MemoryAccessError(message)

        self._check_readable(address, length)
        return bytes(self._data[address : address + length])

    def read_byte(self, address: int) -> int:
        """Read the byte at a byte address."""
        self._check_readable(address, 1)
        return self._data[address]

    def read_word(self, address: int) -> int:
        """Read the 2-byte word at a byte address.

        Words are stored most-significant byte first (§ 2.1).
        """
        self._check_readable(address, 2)
        return (self._data[address] << 8) | self._data[address + 1]

    def write_word(self, address: int, value: int) -> None:
        """Write a 2-byte word to dynamic memory, high byte first (§ 2.1)."""

        self._check_writable(address, 2)

        if not 0 <= value <= MAXIMUM_WORD:
            message = f"${value:x} does not fit in a word"
            raise MemoryAccessError(message)

        self._data[address] = value >> 8
        self._data[address + 1] = value & 0xFF

    def restore_dynamic_memory(self) -> None:
        """Reset dynamic memory to its state on loading (§ 6.1.3).

        `restart` restores everything from the original story file, but
        'Flags 2' survives it: the transcription and fixed-pitch bits reflect
        what the *interpreter* is doing, not what the story was shipped with.
        """

        preserved = self.read_word(FLAGS_2_FIELD)

        self._data[: self._static_memory_base] = self._original[
            : self._static_memory_base
        ]

        self.write_word(FLAGS_2_FIELD, preserved)

    def _check_readable(self, address: int, length: int) -> None:
        if address < 0 or address + length > len(self._data):
            message = (
                f"address ${address:05x} (+{length}) lies outside the "
                f"{len(self._data)}-byte story file"
            )
            raise MemoryAccessError(message)

    def _check_writable(self, address: int, length: int) -> None:
        self._check_readable(address, length)

        if address + length > self._static_memory_base:
            message = (
                f"address ${address:04x} (+{length}) is in static memory, "
                f"which begins at ${self._static_memory_base:05x} "
                f"and is read-only (§ 1.1.2)"
            )
            raise MemoryAccessError(message)
