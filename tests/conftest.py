"""Shared fixtures: synthetic story files shaped per the § 11.1 header."""

from collections.abc import Callable

import pytest


def _write_word(data: bytearray, address: int, value: int) -> None:
    data[address] = value >> 8
    data[address + 1] = value & 0xFF


def make_story_bytes(
    version: int,
    *,
    release: int = 42,
    serial: bytes = b"\x00\x00\x00\x00\x00\x00",
    flags_1: int = 0,
    flags_2: int = 0,
    high_memory_base: int = 0x0400,
    initial_pc: int = 0x0500,
    dictionary: int = 0x0300,
    object_table: int = 0x0340,
    global_variables: int = 0x0380,
    static_memory_base: int = 0x0200,
    abbreviations: int = 0x01C0,
    file_length_words: int = 0,
    checksum: int = 0,
    routines_offset: int = 0,
    static_strings_offset: int = 0,
    total_size: int = 0x0600,
) -> bytes:
    data = bytearray(total_size)

    data[0x00] = version
    data[0x01] = flags_1
    _write_word(data, 0x02, release)
    _write_word(data, 0x04, high_memory_base)
    _write_word(data, 0x06, initial_pc)
    _write_word(data, 0x08, dictionary)
    _write_word(data, 0x0A, object_table)
    _write_word(data, 0x0C, global_variables)
    _write_word(data, 0x0E, static_memory_base)
    _write_word(data, 0x10, flags_2)
    data[0x12:0x18] = serial
    _write_word(data, 0x18, abbreviations)
    _write_word(data, 0x1A, file_length_words)
    _write_word(data, 0x1C, checksum)
    _write_word(data, 0x28, routines_offset)
    _write_word(data, 0x2A, static_strings_offset)

    return bytes(data)


@pytest.fixture
def story_data() -> Callable[..., bytes]:
    return make_story_bytes
