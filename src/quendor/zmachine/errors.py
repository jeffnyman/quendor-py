"""Exceptions raised by the Z-Machine core."""


class QuendorError(Exception):
    """Base class for every error Quendor raises."""


class StoryFileError(QuendorError):
    """A story file is malformed, truncated, or otherwise unusable."""
