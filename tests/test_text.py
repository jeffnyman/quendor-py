from collections.abc import Callable, Sequence

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.story import Story
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V1, V2, V3, V5, V6

ABBREVIATIONS = 0x01C0
SCRATCH = 0x0300


def pack(zchars: Sequence[int]) -> bytes:
    """Pack Z-characters into words, three per word, end bit on the last.

    Padding uses Z-character 5, as real compilers do; at the end of a
    string it shifts and then nothing happens.
    """

    padded = list(zchars)

    while len(padded) % 3:
        padded.append(5)

    words = []

    for index in range(0, len(padded), 3):
        word = (padded[index] << 10) | (padded[index + 1] << 5) | padded[index + 2]

        if index + 3 >= len(padded):
            word |= 0x8000

        words.append(word)

    return b"".join(word.to_bytes(2, "big") for word in words)


def make_codec(
    story_data: Callable[..., bytes],
    version: int = V3,
    patches: dict[int, bytes] | None = None,
) -> TextCodec:
    data = bytearray(story_data(version))

    for address, blob in (patches or {}).items():
        data[address : address + len(blob)] = blob

    story = Story(bytes(data))

    return TextCodec(story.memory, story.header)


def test_lowercase_alphabet(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([13, 10, 17, 17, 20]))).is_equal_to("hello")


def test_zchar_zero_is_a_space(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([13, 10, 0, 13, 10]))).is_equal_to("he he")


def test_shift_applies_to_one_character(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([4, 13, 13]))).is_equal_to("Hh")


def test_a2_holds_digits_and_newline(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 8]))).is_equal_to("0")
    assert_that(codec.decode_bytes(pack([5, 7]))).is_equal_to("\n")


def test_ten_bit_escape(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 6, 2, 1]))).is_equal_to("A")


def test_truncated_escape_is_ignored(story_data: Callable[..., bytes]) -> None:
    # § 3.6.1: a string may legally end mid-construction.
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 6, 2]))).is_equal_to("")


def test_zscii_null_prints_nothing(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 6, 0, 0]))).is_equal_to("")


def test_undefined_zscii_is_dropped(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 6, 3, 31]))).is_equal_to("")


def test_v6_only_output_characters(story_data: Callable[..., bytes]) -> None:
    tab = pack([5, 6, 0, 9])
    gap = pack([5, 6, 0, 11])

    v6 = make_codec(story_data, version=V6)
    v3 = make_codec(story_data, version=V3)

    assert_that(v6.decode_bytes(tab)).is_equal_to("\t")
    assert_that(v6.decode_bytes(gap)).is_equal_to("\u2001")
    assert_that(v3.decode_bytes(tab)).is_equal_to("")
    assert_that(v3.decode_bytes(gap)).is_equal_to("")


def test_default_unicode_table(story_data: Callable[..., bytes]) -> None:
    # ZSCII 155 is a-umlaut in the default table (§ 3.8.5.3).
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([5, 6, 4, 27]))).is_equal_to("ä")


def test_abbreviation_expands(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(
        story_data,
        patches={
            ABBREVIATIONS: (SCRATCH // 2).to_bytes(2, "big"),
            SCRATCH: pack([13, 10, 17, 17, 20]),
        },
    )

    assert_that(codec.decode_bytes(pack([1, 0]))).is_equal_to("hello")


def test_abbreviations_do_not_nest(story_data: Callable[..., bytes]) -> None:
    # § 3.3.1: an abbreviation may not itself use abbreviations. The inner
    # reference is dropped rather than expanded.
    entry_1 = ABBREVIATIONS + 2

    codec = make_codec(
        story_data,
        patches={
            ABBREVIATIONS: (SCRATCH // 2).to_bytes(2, "big"),
            entry_1: ((SCRATCH + 8) // 2).to_bytes(2, "big"),
            SCRATCH: pack([13, 10, 17, 17, 20]),
            SCRATCH + 8: pack([1, 0]),
        },
    )

    assert_that(codec.decode_bytes(pack([1, 1]))).is_equal_to("")


def test_abbreviation_at_end_of_string_is_ignored(
    story_data: Callable[..., bytes],
) -> None:
    # § 3.6.1 again: the bank Z-character arrives with no index after it.
    codec = make_codec(story_data)

    assert_that(codec.decode_bytes(pack([13, 10, 1]))).is_equal_to("he")


def test_v1_zchar_one_is_a_newline(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data, version=V1)

    assert_that(codec.decode_bytes(pack([1]))).is_equal_to("\n")


def test_v1_a2_swaps_in_the_less_than_sign(
    story_data: Callable[..., bytes],
) -> None:
    codec = make_codec(story_data, version=V1)

    assert_that(codec.decode_bytes(pack([3, 27]))).is_equal_to("<")


def test_early_version_single_shifts_rotate(
    story_data: Callable[..., bytes],
) -> None:
    codec = make_codec(story_data, version=V2)

    assert_that(codec.decode_bytes(pack([2, 13]))).is_equal_to("H")


def test_early_version_shift_locks(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(story_data, version=V2)

    assert_that(codec.decode_bytes(pack([5, 8, 9]))).is_equal_to("01")


def test_v2_bank_one_abbreviation(story_data: Callable[..., bytes]) -> None:
    codec = make_codec(
        story_data,
        version=V2,
        patches={
            ABBREVIATIONS: (SCRATCH // 2).to_bytes(2, "big"),
            SCRATCH: pack([13, 10, 17, 17, 20]),
        },
    )

    assert_that(codec.decode_bytes(pack([1, 0]))).is_equal_to("hello")


def test_custom_alphabet_table(story_data: Callable[..., bytes]) -> None:
    alphabet = b"qwertyuiopasdfghjklzxcvbnm" + b"QWERTYUIOPASDFGHJKLZXCVBNM" + bytes(26)

    codec = make_codec(
        story_data,
        version=V5,
        patches={
            0x34: SCRATCH.to_bytes(2, "big"),
            SCRATCH: alphabet,
        },
    )

    assert_that(codec.decode_bytes(pack([6, 7]))).is_equal_to("qw")


def test_custom_unicode_table_replaces_the_default(
    story_data: Callable[..., bytes],
) -> None:
    extension = 0x0320
    table = 0x0330

    codec = make_codec(
        story_data,
        version=V5,
        patches={
            0x36: extension.to_bytes(2, "big"),
            extension: (3).to_bytes(2, "big") + bytes(4) + table.to_bytes(2, "big"),
            table: bytes([1]) + (0x263A).to_bytes(2, "big"),
        },
    )

    # 155 comes from the custom table; 156 is past its one entry and is
    # undefined rather than falling back to the default (§ 3.8.5.2.2).
    assert_that(codec.decode_bytes(pack([5, 6, 4, 27]))).is_equal_to("☺")
    assert_that(codec.decode_bytes(pack([5, 6, 4, 28]))).is_equal_to("")


def test_read_zchars_can_be_capped(story_data: Callable[..., bytes]) -> None:
    # White-box on purpose: the public consumer of `max_bytes` is the
    # dictionary (§ 3.7), which does not exist yet. Two words, no end bit.
    codec = make_codec(
        story_data,
        patches={SCRATCH: bytes([0x00, 0x41, 0x00, 0x41])},
    )

    zchars, after = codec._read_zchars(SCRATCH, max_bytes=2)

    assert_that(zchars).is_length(3)
    assert_that(after).is_equal_to(SCRATCH + 2)


def test_v1_abbreviation_means_a_broken_story(
    story_data: Callable[..., bytes],
) -> None:
    # White-box: unreachable through decoding, since `_is_abbreviation`
    # admits nothing in V1; the guard exists for mypy and corrupt stories.
    codec = make_codec(story_data, version=V1)

    with pytest.raises(StoryFileError):
        codec._abbreviation(1, 0, 0)
