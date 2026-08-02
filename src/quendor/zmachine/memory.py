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


class Memory:
    """The story file's bytes."""

    def __init__(self, data: bytes) -> None:
        if len(data) < HEADER_SIZE:
            message = (
                f"story file is {len(data)} bytes; "
                f"a header alone requires {HEADER_SIZE} (§ 1.1.1.1)"
            )
            raise StoryFileError(message)

        self._data = bytearray(data)

    def __len__(self) -> int:
        return len(self._data)

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

    def _check_readable(self, address: int, length: int) -> None:
        if address < 0 or address + length > len(self._data):
            message = (
                f"address ${address:05x} (+{length}) lies outside the "
                f"{len(self._data)}-byte story file"
            )
            raise MemoryAccessError(message)
