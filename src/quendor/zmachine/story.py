"""Loading a story file."""

from pathlib import Path
from typing import Self

from quendor.zmachine.errors import StoryFileError


class Story:
    """A loaded story file."""

    def __init__(self, data: bytes) -> None:
        pass

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Load a story file from disk."""

        try:
            data = path.read_bytes()
        except OSError as error:
            message = f"could not read story file {path}: {error}"
            raise StoryFileError(message) from error

        return cls(data)
