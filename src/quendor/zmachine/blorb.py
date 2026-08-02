"""Blorb resource files (Blorb 2.0.5)."""

from pathlib import Path
from typing import Final

from quendor.zmachine.errors import BlorbError, StoryFileError

FORM: Final = b"FORM"
IFRS: Final = b"IFRS"
RIDX: Final = b"RIdx"
ZCODE: Final = b"ZCOD"
GLULX: Final = b"GLUL"

PICTURE: Final = b"Pict"
SOUND: Final = b"Snd "
EXECUTABLE: Final = b"Exec"

"""Usage, number and offset, four bytes each (Blorb § 1)."""
_INDEX_ENTRY_SIZE: Final = 12

"""Extensions story files conventionally use, named for the Versions of
§ 11.1. Only for recognising a file by name, never for deciding what is
in it."""
_STORY_SUFFIXES: Final = tuple(f".z{version}" for version in range(1, 9))


class Blorb:
    """A bundled up collection of resources."""

    def __init__(self, data: bytes) -> None:
        if data[:4] != FORM or data[8:12] != IFRS:
            message = "not a Blorb file (no IFRS form)"
            raise BlorbError(message)

        self._data = data

        # Lookups are by chunk identifier, so duplicate identifiers collapse
        # to the last one. Fine while only the singleton RIdx is consulted;
        # revisit before reading resources by chunk rather than by index
        # offset.
        self._chunks = dict(self._scan(data))

        self._executables: dict[int, int] = {}
        self.picture_count = 0
        self.sound_count = 0

        self._read_index()

    def executable(self) -> bytes | None:
        """The story inside, or None if none is indexed (Blorb § 5).

        A `.zblorb` packages code and resources in one file: the story is a
        `ZCOD` chunk indexed with a usage of `Exec`. The lowest-numbered
        executable is the one to run, and no system in the wild ships more
        than one (Blorb § 5.1).

        Raises:
            BlorbError: The Blorb carries an executable quendor cannot run,
                such as a Glulx game.
        """

        kinds = []

        for _number, offset in sorted(self._executables.items()):
            kind = self._data[offset : offset + 4]

            if kind == ZCODE:
                length = int.from_bytes(self._data[offset + 4 : offset + 8], "big")
                return self._data[offset + 8 : offset + 8 + length]

            kinds.append(kind)

        if kinds:
            label = kinds[0].decode("ascii", errors="replace").strip()
            glulx = " (a Glulx game)" if kinds[0] == GLULX else ""
            message = (
                f"its executable is {label}{glulx} rather than Z-code, "
                f"which quendor cannot run (Blorb § 5)"
            )
            raise BlorbError(message)

        return None

    @staticmethod
    def _scan(data: bytes) -> list[tuple[bytes, tuple[int, int]]]:
        """Walk the top-level chunks, recording where each body begins."""

        found = []
        position = 12

        while position + 8 <= len(data):
            identifier = data[position : position + 4]
            length = int.from_bytes(data[position + 4 : position + 8], "big")

            found.append((identifier, (position + 8, length)))

            # Chunks are padded to an even length (Blorb § 15).
            position += 8 + length + (length % 2)

        return found

    def _read_index(self) -> None:
        """Read the resource index (Blorb § 1)."""

        if RIDX not in self._chunks:
            message = "it has no resource index (Blorb § 1)"
            raise BlorbError(message)

        start, _length = self._chunks[RIDX]
        count = int.from_bytes(self._data[start : start + 4], "big")

        for index in range(count):
            entry = start + 4 + _INDEX_ENTRY_SIZE * index
            usage = self._data[entry : entry + 4]

            if usage == PICTURE:
                self.picture_count += 1
            elif usage == SOUND:
                self.sound_count += 1
            elif usage == EXECUTABLE:
                number = int.from_bytes(self._data[entry + 4 : entry + 8], "big")

                # The offset is from the start of the file, and points at a
                # chunk header rather than at its body (Blorb § 1).
                offset = int.from_bytes(self._data[entry + 8 : entry + 12], "big")

                self._executables[number] = offset


def story_beside(blorb: Path) -> Path | None:
    """The story file a resource Blorb belongs to, if there is an obvious one."""

    for suffix in _STORY_SUFFIXES:
        candidate = blorb.with_suffix(suffix)

        if candidate.is_file():
            return candidate

    siblings = sorted(
        path
        for suffix in _STORY_SUFFIXES
        for path in blorb.parent.glob(f"*{suffix}")
        if path.stem.startswith(blorb.stem) or blorb.stem.startswith(path.stem)
    )

    return siblings[0] if siblings else None


def story_bytes(path: Path) -> bytes:
    """The story file at `path`, unwrapping a Blorb package if it is one.

    A bare story file is returned as it stands, and a `.zblorb` is unwrapped
    (Blorb § 5). A Blorb with no executable chunk is a *resource* file, and
    saying so is the whole point of looking: read as a story it yields a
    header full of picture data, and the complaint that comes back is about
    the memory map rather than about the file being the wrong one. Beyond
    Zork ships its cover art in exactly such a file, next to the story.
    """

    data = path.read_bytes()

    if data[:4] != FORM or data[8:12] != IFRS:
        return data

    # From here the file has declared itself a Blorb, so any trouble with it
    # is reported in those terms rather than letting the raw bytes fall
    # through to be misread as a story.
    try:
        blorb = Blorb(data)
        packaged = blorb.executable()
    except BlorbError as error:
        message = f"{path.name} is a Blorb that cannot be used: {error}"
        raise StoryFileError(message) from error

    if packaged is not None:
        return packaged

    beside = story_beside(path)
    hint = f"; the story file beside it is {beside.name}" if beside else ""

    message = (
        f"{path.name} is a Blorb resource file rather than a story: it "
        f"holds {_contents(blorb)} and no executable chunk (Blorb § 5){hint}"
    )

    raise StoryFileError(message)


def _contents(blorb: Blorb) -> str:
    parts = []

    if blorb.picture_count:
        parts.append(_count(blorb.picture_count, "picture"))

    if blorb.sound_count:
        parts.append(_count(blorb.sound_count, "sound"))

    return " and ".join(parts) if parts else "no indexed resources"


def _count(number: int, noun: str) -> str:
    suffix = "" if number == 1 else "s"
    return f"{number} {noun}{suffix}"
