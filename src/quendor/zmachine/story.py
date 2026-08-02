"""Loading a story file."""

from pathlib import Path
from typing import Self

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory


class Story:
    """A loaded story file: its memory and a header view over it."""

    def __init__(self, data: bytes) -> None:
        self.memory = Memory(data)
        self.header = Header(self.memory)

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Load a story file from disk."""

        try:
            data = path.read_bytes()
        except OSError as error:
            message = f"could not read story file {path}: {error}"
            raise StoryFileError(message) from error

        return cls(data)
