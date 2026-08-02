"""Loading a story file.

A story file is the program the Z-Machine runs: a header followed by the
tables and code it describes (§ 1.1). This module turns a file on disk into
`Memory` plus a `Header` view over it, refusing anything the standard says
cannot be valid.
"""

from pathlib import Path
from typing import Self

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.header import SUPPORTED_VERSIONS, Header
from quendor.zmachine.memory import HEADER_SIZE, Memory


class Story:
    """A loaded story file: its memory and a header view over it."""

    def __init__(self, data: bytes) -> None:
        self.memory = Memory(data)
        self.header = Header(self.memory)
        self._validate()

    @classmethod
    def from_path(cls, path: Path) -> Self:
        """Load a story file from disk."""

        try:
            data = path.read_bytes()
        except OSError as error:
            message = f"could not read story file {path}: {error}"
            raise StoryFileError(message) from error

        return cls(data)

    def _validate(self) -> None:
        # Version first: the checks below consult Version-keyed tables, which
        # would raise a bare KeyError for an undefined Version.
        version = self.header.version

        if version not in SUPPORTED_VERSIONS:
            message = (
                f"story file declares Version {version}; "
                f"the Z-Machine defines Versions 1 to 8 (§ 11.1)"
            )
            raise StoryFileError(message)

        size = len(self.memory)
        maximum = self.header.maximum_file_size

        if size > maximum:
            message = (
                f"story file is {size} bytes; Version {version} permits "
                f"at most {maximum} (§ 1.1.4)"
            )
            raise StoryFileError(message)

        # A recorded length longer than the file itself means truncation. The
        # reverse is fine and common: files are padded to a block boundary,
        # and Blorb-extracted story data may carry a tail.
        file_length = self.header.file_length

        if file_length is not None and file_length > size:
            message = (
                f"header records a length of {file_length} bytes but the file "
                f"holds {size}; it looks truncated (§ 11.1.6)"
            )
            raise StoryFileError(message)

        # Dynamic memory runs from 0 to the byte before static memory, holds
        # the header, and must physically exist in the file (§ 1.1). Its base
        # is the only free variable in the famous 64K dynamic-plus-static
        # ceiling, which is otherwise capped by definition.
        static_base = self.header.static_memory_base

        if static_base < HEADER_SIZE:
            message = (
                f"static memory begins at ${static_base:05x}, inside the "
                f"{HEADER_SIZE}-byte header; dynamic memory must contain "
                f"at least {HEADER_SIZE} bytes (§ 1.1)"
            )
            raise StoryFileError(message)

        if static_base > size:
            message = (
                f"static memory begins at ${static_base:05x} but the file "
                f"ends at ${size - 1:05x}; dynamic memory cannot extend "
                f"past the end of the file (§ 1.1)"
            )
            raise StoryFileError(message)
