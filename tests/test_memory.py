from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import MemoryAccessError, StoryFileError
from quendor.zmachine.memory import Memory
from quendor.zmachine.versions import V3


def blank_story(size: int = 64) -> bytes:
    """Zeroed bytes with static memory opening right after the header.

    The smallest data Memory accepts now that it validates its own static
    base at construction.
    """

    data = bytearray(size)
    data[0x0E:0x10] = (0x40).to_bytes(2, "big")

    return bytes(data)


def test_data_shorter_than_a_header_is_rejected() -> None:
    with pytest.raises(StoryFileError) as error_info:
        Memory(b"\x00" * 63)

    assert_that(str(error_info.value)).contains("63 bytes")


def test_static_base_inside_the_header_is_rejected(
    story_data: Callable[..., bytes],
) -> None:
    with pytest.raises(StoryFileError) as error_info:
        Memory(story_data(V3, static_memory_base=0x20))

    assert_that(str(error_info.value)).contains("inside the 64-byte header")


def test_static_base_beyond_the_file_is_rejected(
    story_data: Callable[..., bytes],
) -> None:
    with pytest.raises(StoryFileError) as error_info:
        Memory(story_data(V3, static_memory_base=0x2000))

    assert_that(str(error_info.value)).contains("past the end of the file")


def test_len_is_the_story_size() -> None:
    assert_that(len(Memory(blank_story(80)))).is_equal_to(80)


def test_static_memory_base_is_exposed() -> None:
    assert_that(Memory(blank_story()).static_memory_base).is_equal_to(0x40)


def test_read_byte() -> None:
    data = bytearray(blank_story())
    data[0x20] = 0xAB

    assert_that(Memory(bytes(data)).read_byte(0x20)).is_equal_to(0xAB)


def test_words_are_read_most_significant_byte_first() -> None:
    data = bytearray(blank_story())
    data[0x20] = 0x12
    data[0x21] = 0x34

    assert_that(Memory(bytes(data)).read_word(0x20)).is_equal_to(0x1234)


def test_read_bytes_returns_the_run() -> None:
    data = bytearray(blank_story())
    data[0x20:0x23] = b"abc"

    assert_that(Memory(bytes(data)).read_bytes(0x20, 3)).is_equal_to(b"abc")


def test_negative_length_reads_are_rejected() -> None:
    with pytest.raises(MemoryAccessError):
        Memory(blank_story()).read_bytes(0, -1)


def test_reads_beyond_the_story_are_rejected() -> None:
    with pytest.raises(MemoryAccessError) as error_info:
        Memory(blank_story()).read_byte(64)

    assert_that(str(error_info.value)).contains("outside the 64-byte story file")


def test_negative_addresses_do_not_wrap_around() -> None:
    # Without the bounds check, Python's negative indexing would silently
    # read the last byte of the file instead of failing.
    with pytest.raises(MemoryAccessError):
        Memory(blank_story()).read_byte(-1)


def test_write_word_round_trips() -> None:
    memory = Memory(blank_story(128))

    memory.write_word(0x20, 0x1234)

    assert_that(memory.read_word(0x20)).is_equal_to(0x1234)


def test_writes_to_static_memory_are_rejected() -> None:
    memory = Memory(blank_story(128))

    with pytest.raises(MemoryAccessError) as error_info:
        memory.write_word(0x40, 1)

    assert_that(str(error_info.value)).contains("read-only")


def test_oversized_word_values_are_rejected() -> None:
    with pytest.raises(MemoryAccessError) as error_info:
        Memory(blank_story(128)).write_word(0x20, 0x10000)

    assert_that(str(error_info.value)).contains("does not fit in a word")


def test_restart_restores_dynamic_memory_but_keeps_flags_2(
    story_data: Callable[..., bytes],
) -> None:
    memory = Memory(story_data(V3))

    memory.write_word(0x20, 0xBEEF)  # the game scribbles on dynamic memory
    memory.write_word(0x10, 0x0001)  # and turns transcription on

    memory.restore_dynamic_memory()

    # The scribble is gone, but Flags 2 survives the restart (§ 6.1.3).
    assert_that(memory.read_word(0x20)).is_equal_to(0)
    assert_that(memory.read_word(0x10)).is_equal_to(0x0001)
