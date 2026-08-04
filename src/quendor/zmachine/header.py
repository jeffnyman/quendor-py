"""The story file header (§ 11).

The first 64 bytes of every story file describe the shape of everything else:
where the tables live, which Version's rules apply, and how packed addresses
should be unpacked.

This is a *view* over live memory rather than a snapshot. A few header fields
are writable during play -- the transcription bit of Flags 2, for instance
(§ 11.1.2.1) -- and the interpreter itself writes screen dimensions and its
own version number after loading. Reading through to memory keeps those in
step. Fields not marked "Dyn" in the § 11.1 table may not legally change, and
§ 11.1.1 explicitly permits an interpreter to cache those; `Memory` does
exactly that for the static memory base.
"""

from typing import Final

from quendor.zmachine.memory import Memory
from quendor.zmachine.versions import V2, V3, V5, V6, V7

# Offsets into the header, named after the § 11.1 table. (memory.py keeps
# private mirrors of FLAGS_2 and STATIC_MEMORY_BASE; it cannot import them.)
VERSION: Final = 0x00
FLAGS_1: Final = 0x01
RELEASE: Final = 0x02
HIGH_MEMORY_BASE: Final = 0x04
INITIAL_PC: Final = 0x06
DICTIONARY: Final = 0x08
OBJECT_TABLE: Final = 0x0A
GLOBAL_VARIABLES: Final = 0x0C
STATIC_MEMORY_BASE: Final = 0x0E
FLAGS_2: Final = 0x10
SERIAL: Final = 0x12
ABBREVIATIONS: Final = 0x18
FILE_LENGTH: Final = 0x1A
CHECKSUM: Final = 0x1C
ROUTINES_OFFSET: Final = 0x28
STATIC_STRINGS_OFFSET: Final = 0x2A
ALPHABET_TABLE: Final = 0x34
EXTENSION_TABLE: Final = 0x36

"""Word 3 of the header extension holds the Unicode table address (§ 11.1.7.3)."""
UNICODE_TABLE_EXTENSION_WORD: Final = 3

"""Six characters of ASCII; from V3 the compilation date as YYMMDD (§ 11.1)."""
SERIAL_LENGTH: Final = 6

"""Quendor targets the full range the Z-Machine defines (§ 11.1)."""
SUPPORTED_VERSIONS: Final = frozenset(range(1, 9))

"""The stored file length is divided by this to fit a word (§ 11.1.6)."""
_FILE_LENGTH_SCALE: Final = {1: 2, 2: 2, 3: 2, 4: 4, 5: 4, 6: 8, 7: 8, 8: 8}

"""Maximum permitted story file length, by Version (§ 1.1.4)."""
_MAXIMUM_FILE_SIZE: Final = {
    1: 128 * 1024,
    2: 128 * 1024,
    3: 128 * 1024,
    4: 256 * 1024,
    5: 256 * 1024,
    6: 512 * 1024,
    7: 512 * 1024,
    8: 512 * 1024,
}


class Header:
    """Typed access to the header fields of § 11.1."""

    def __init__(self, memory: Memory) -> None:
        self._memory = memory

    @property
    def version(self) -> int:
        """Z-Machine Version, 1 to 8 (§ 11.1).

        ZVERSION in the ZIP Specification.
        """
        return self._memory.read_byte(VERSION)

    @property
    def release(self) -> int:
        """Release number of the story (§ 11.1).

        ZORKID in the ZIP Specification.
        """
        return self._memory.read_word(RELEASE)

    @property
    def serial(self) -> str | None:
        """Serial code: six ASCII characters, or None when the field is blank.

        SERIAL in the ZIP Specification.

        YYMMDD compilation date from V3 (§ 11.1). V1 files officially leave
        the bytes unset, but some real releases carry a serial anyway, so
        presence is judged from the data rather than the Version.
        """
        raw = self._memory.read_bytes(SERIAL, SERIAL_LENGTH)

        if not any(raw):
            return None

        return raw.decode("ascii", errors="replace")

    @property
    def serial_is_official(self) -> bool:
        """Whether the Version officially records a serial (§ 11.1).

        V1 files leave the field unset on paper; `serial` reports what the
        bytes actually hold.
        """
        return self.version >= V2

    @property
    def serial_is_compilation_date(self) -> bool:
        """Whether the serial is a compilation date, as YYMMDD (§ 11.1)."""
        return self.version >= V3

    @property
    def file_length(self) -> int | None:
        """Length of the story file in bytes, or None if not recorded.

        PLENTH in the ZIP Specification.

        Stored divided by a Version-dependent constant so that it fits in a
        word (§ 11.1.6). The field only exists from V3, and § 11.1 notes that
        some early V3 files leave it zero.
        """
        if self.version < V3:
            return None

        stored = self._memory.read_word(FILE_LENGTH)

        if stored == 0:
            return None

        return stored * _FILE_LENGTH_SCALE[self.version]

    @property
    def checksum(self) -> int | None:
        """Checksum of the story file, or None if not recorded (§ 11.1).

        PCHKSM in the ZIP Specification.

        As with `file_length`, absent before V3 and zero in some early V3
        files.
        """
        if self.version < V3:
            return None

        stored = self._memory.read_word(CHECKSUM)

        return stored or None

    @property
    def flags_1(self) -> int:
        """Interpreter capability flags; meaning varies by Version (§ 11.1.4).

        Referred to as the "mode byte" of ZVERSION in the ZIP Specification.
        """
        return self._memory.read_byte(FLAGS_1)

    @property
    def flags_2(self) -> int:
        """Game and interpreter feature flags (§ 11.1.2).

        FLAGS in the ZIP Specification.
        """
        return self._memory.read_word(FLAGS_2)

    @property
    def static_memory_base(self) -> int:
        """Byte address where static memory begins (§ 1.1).

        PURBOT in the ZIP Specification.
        """
        return self._memory.read_word(STATIC_MEMORY_BASE)

    @property
    def high_memory_base(self) -> int:
        """Byte address where high memory begins (§ 1.1).

        ENDLOD in the ZIP Specification.
        """
        return self._memory.read_word(HIGH_MEMORY_BASE)

    @property
    def dictionary_address(self) -> int:
        """Byte address of the dictionary (§ 11.1).

        VOCAB in the ZIP Specification.
        """
        return self._memory.read_word(DICTIONARY)

    @property
    def object_table_address(self) -> int:
        """Byte address of the object table (§ 11.1).

        OBJECT in the ZIP Specification.
        """
        return self._memory.read_word(OBJECT_TABLE)

    @property
    def global_variables_address(self) -> int:
        """Byte address of the global variables table (§ 11.1).

        GLOBALS in the ZIP Specification.
        """
        return self._memory.read_word(GLOBAL_VARIABLES)

    @property
    def abbreviations_address(self) -> int | None:
        """Byte address of the abbreviations table; V2 and later (§ 11.1).

        FWORDS in the ZIP Specification.
        """
        if self.version < V2:
            return None

        return self._memory.read_word(ABBREVIATIONS)

    @property
    def alphabet_table_address(self) -> int:
        """Byte address of a story-specific alphabet table, or 0 (§ 3.5.5).

        Only consulted from V5; earlier Versions always use the built-in
        alphabets of § 3.5.3.
        """
        if self.version < V5:
            return 0

        return self._memory.read_word(ALPHABET_TABLE)

    @property
    def unicode_translation_table_address(self) -> int:
        """Byte address of the Unicode translation table, or 0 (§ 3.8.5.2).

        Word 3 of the header extension. Absent or zero means the default
        table of § 3.8.5.3 applies, which is always the case before V5.
        """
        return self._extension_word(UNICODE_TABLE_EXTENSION_WORD)

    @property
    def extension_table_address(self) -> int:
        """Byte address of the header extension table, or 0 (§ 11.1.7)."""

        if self.version < V5:
            return 0

        return self._memory.read_word(EXTENSION_TABLE)

    @property
    def initial_program_counter(self) -> int:
        """Where execution begins.

        START in the ZIP Specification.

        In V1-5 this is the byte address of the first instruction. In V6 it is
        the packed address of the initial "main" routine instead (§ 11.1), so
        callers must consult `has_main_routine` before using it.
        """
        return self._memory.read_word(INITIAL_PC)

    @property
    def has_main_routine(self) -> bool:
        """Whether execution begins by calling a "main" routine (§ 11.1).

        Only V6 starts this way; every other Version begins executing at a
        byte address held in the same header word.
        """
        return self.version == V6

    @property
    def routines_offset(self) -> int:
        """Routine offset for unpacking addresses; V6 and V7 only (§ 1.2.3)."""
        return self._memory.read_word(ROUTINES_OFFSET)

    @property
    def static_strings_offset(self) -> int:
        """String offset for unpacking addresses; V6 and V7 only (§ 1.2.3)."""
        return self._memory.read_word(STATIC_STRINGS_OFFSET)

    @property
    def unpacks_with_offsets(self) -> bool:
        """Whether packed addresses add the header offsets when unpacked (§ 1.2.3).

        Only V6 and V7 store routine and string offsets.
        """
        return V6 <= self.version <= V7

    @property
    def maximum_file_size(self) -> int:
        """Largest story file this Version permits (§ 1.1.4)."""
        return _MAXIMUM_FILE_SIZE[self.version]

    def unpack_string_address(self, packed: int) -> int:
        """Convert a packed string address to a byte address (§ 1.2.3).

        Identical to `unpack_routine_address` except that V6 and V7 apply the
        strings offset rather than the routines offset.
        """
        return self._unpack(packed, self.static_strings_offset)

    def unpack_routine_address(self, packed: int) -> int:
        """Convert a packed routine address to a byte address (§ 1.2.3).

        The multiplier grows with the Version because later Versions address
        larger story files with the same 2-byte packed value. V6 and V7 add a
        further offset held in the header, which is how they reach beyond what
        4P alone would allow.
        """
        return self._unpack(packed, self.routines_offset)

    def _unpack(self, packed: int, offset: int) -> int:
        version = self.version

        if version <= V3:
            return 2 * packed

        if version <= V5:
            return 4 * packed

        if version <= V7:
            return 4 * packed + 8 * offset

        return 8 * packed

    def _extension_word(self, index: int) -> int:
        """Read a word from the header extension table (§ 11.1.7).

        Word 0 holds the number of words that follow. Reading past the end of
        the table, or from a table that does not exist, gives 0 (§ 11.1.7.1)
        rather than being an error.
        """

        address = self.extension_table_address

        if address == 0 or index < 1:
            return 0

        length = self._memory.read_word(address)

        if index > length:
            return 0

        return self._memory.read_word(address + 2 * index)
