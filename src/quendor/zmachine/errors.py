"""Exceptions raised by the Z-Machine core."""


class QuendorError(Exception):
    """Base class for every error Quendor raises."""


class StoryFileError(QuendorError):
    """A story file is malformed, truncated, or otherwise unusable.

    Raised while loading, before the interpreter starts. Once a story is
    running, faults become `MemoryAccessError` instead.
    """


class MemoryAccessError(QuendorError):
    """A read or write violated the memory map rules of § 1.1.

    Either the address lies outside the story file, or the game attempted to
    write to static memory, which § 1.1.2 forbids.
    """


class BlorbError(QuendorError):
    """A resource file that cannot be read."""


class IllegalOpcodeError(QuendorError):
    """An opcode that does not exist in the story file's Version.

    § 14.2 makes this a fault an interpreter should normally halt on, rather
    than something to skip past: an opcode Quendor does not recognise means
    it has almost certainly lost its place in the instruction stream.
    """


class UnimplementedOpcodeError(QuendorError):
    """An opcode Quendor decodes but cannot yet execute."""
