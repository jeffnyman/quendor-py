"""Shared fixtures: synthetic story files and Blorbs, shaped per the specs."""

from collections.abc import Callable, Sequence

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


def make_blorb_bytes(
    resources: Sequence[tuple[bytes, bytes, bytes]] = (),
) -> bytes:
    """A Blorb holding `resources`, given as (usage, chunk id, body) triples."""

    index_size = 4 + 12 * len(resources)
    entries = b""
    chunks = b""
    position = 12 + 8 + index_size

    for number, (usage, identifier, body) in enumerate(resources):
        entries += usage + number.to_bytes(4, "big") + position.to_bytes(4, "big")

        chunk = identifier + len(body).to_bytes(4, "big") + body

        if len(body) % 2:
            chunk += b"\x00"

        chunks += chunk
        position += len(chunk)

    index = b"RIdx" + index_size.to_bytes(4, "big")
    index += len(resources).to_bytes(4, "big") + entries

    payload = b"IFRS" + index + chunks

    return b"FORM" + len(payload).to_bytes(4, "big") + payload


@pytest.fixture
def blorb_data() -> Callable[..., bytes]:
    return make_blorb_bytes
