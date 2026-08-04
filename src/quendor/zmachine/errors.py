"""Exceptions raised by the Z-Machine core."""


class QuendorError(Exception):
    """Base class for every error Quendor raises."""


class BlorbError(QuendorError):
    """A resource file that cannot be read."""


class ExecutionError(QuendorError):
    """The running program did something the Z-machine does not allow.

    Distinct from `StoryFileError`, which is about a file that could never
    have run at all.
    """


class IllegalOpcodeError(QuendorError):
    """An opcode that does not exist in the story file's Version.

    § 14.2 makes this a fault an interpreter should normally halt on, rather
    than something to skip past: an opcode Quendor does not recognise means
    it has almost certainly lost its place in the instruction stream.
    """


class IllegalReturnError(ExecutionError):
    """A return from the outermost routine.

    § 5.4 and § 5.5 both say returning from the environment the Z-machine
    starts in is illegal. There is nowhere for it to go.
    """


class MemoryAccessError(QuendorError):
    """A read or write violated the memory map rules of § 1.1.

    Either the address lies outside the story file, or the game attempted to
    write to static memory, which § 1.1.2 forbids.
    """


class StackError(ExecutionError):
    """A stack operation that cannot be satisfied.

    Most often pulling from a stack that nothing has been pushed onto, which
    § 6.3.1 makes illegal.
    """


class StoryFileError(QuendorError):
    """A story file is malformed, truncated, or otherwise unusable.

    Raised while loading, before the interpreter starts. Once a story is
    running, faults become `MemoryAccessError` instead.
    """


class UnimplementedOpcodeError(QuendorError):
    """An opcode Quendor decodes but cannot yet execute."""
