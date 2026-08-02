"""Exceptions raised by the Z-Machine core."""


class QuendorError(Exception):
    """Base class for every error Quendor raises."""


class StoryFileError(QuendorError):
    """A story file is malformed, truncated, or otherwise unusable."""


class MemoryAccessError(QuendorError):
    """A read or write violated the memory map rules of § 1.1."""


class BlorbError(QuendorError):
    """A resource file that cannot be read."""
