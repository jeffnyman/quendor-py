import pytest
from assertpy import assert_that

from quendor.zmachine.errors import MemoryAccessError, StoryFileError
from quendor.zmachine.memory import Memory


def test_data_shorter_than_a_header_is_rejected() -> None:
    with pytest.raises(StoryFileError) as error_info:
        Memory(b"\x00" * 63)

    assert_that(str(error_info.value)).contains("63 bytes")


def test_len_is_the_story_size() -> None:
    assert_that(len(Memory(bytes(80)))).is_equal_to(80)


def test_read_byte() -> None:
    data = bytearray(64)
    data[0x20] = 0xAB

    assert_that(Memory(bytes(data)).read_byte(0x20)).is_equal_to(0xAB)


def test_words_are_read_most_significant_byte_first() -> None:
    data = bytearray(64)
    data[0x20] = 0x12
    data[0x21] = 0x34

    assert_that(Memory(bytes(data)).read_word(0x20)).is_equal_to(0x1234)


def test_read_bytes_returns_the_run() -> None:
    data = bytearray(64)
    data[0x20:0x23] = b"abc"

    assert_that(Memory(bytes(data)).read_bytes(0x20, 3)).is_equal_to(b"abc")


def test_negative_length_reads_are_rejected() -> None:
    with pytest.raises(MemoryAccessError):
        Memory(bytes(64)).read_bytes(0, -1)
