from collections.abc import Callable

from assertpy import assert_that

from quendor.zmachine.story import Story
from quendor.zmachine.versions import V1, V2, V3, V4, V5, V6, V7, V8


def test_fixed_fields_read_back(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V3, release=88, flags_1=0x02, flags_2=0x10)).header

    assert_that(header.version).is_equal_to(V3)
    assert_that(header.release).is_equal_to(88)
    assert_that(header.flags_1).is_equal_to(0x02)
    assert_that(header.flags_2).is_equal_to(0x10)


def test_addresses_read_back(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V3)).header

    assert_that(header.dictionary_address).is_equal_to(0x0300)
    assert_that(header.object_table_address).is_equal_to(0x0340)
    assert_that(header.global_variables_address).is_equal_to(0x0380)
    assert_that(header.static_memory_base).is_equal_to(0x0200)
    assert_that(header.high_memory_base).is_equal_to(0x0400)
    assert_that(header.initial_program_counter).is_equal_to(0x0500)


def test_blank_serial_is_none(story_data: Callable[..., bytes]) -> None:
    assert_that(Story(story_data(V3)).header.serial).is_none()


def test_serial_reads_even_in_v1(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V1, serial=b"AS000C")).header

    assert_that(header.serial).is_equal_to("AS000C")
    assert_that(header.serial_is_official).is_false()
    assert_that(header.serial_is_compilation_date).is_false()


def test_v2_serial_is_official_but_not_dated(
    story_data: Callable[..., bytes],
) -> None:
    header = Story(story_data(V2, serial=b"UG3AU5")).header

    assert_that(header.serial).is_equal_to("UG3AU5")
    assert_that(header.serial_is_official).is_true()
    assert_that(header.serial_is_compilation_date).is_false()


def test_v3_serial_is_a_compilation_date(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V3, serial=b"840809")).header

    assert_that(header.serial_is_compilation_date).is_true()


def test_file_length_absent_before_v3(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V2, file_length_words=100)).header

    assert_that(header.file_length).is_none()


def test_file_length_zero_means_not_recorded(
    story_data: Callable[..., bytes],
) -> None:
    assert_that(Story(story_data(V3)).header.file_length).is_none()


def test_file_length_scales_with_version(story_data: Callable[..., bytes]) -> None:
    def file_length(version: int) -> int | None:
        return Story(story_data(version, file_length_words=100)).header.file_length

    assert_that(file_length(V3)).is_equal_to(200)
    assert_that(file_length(V4)).is_equal_to(400)
    assert_that(file_length(V8)).is_equal_to(800)


def test_checksum_absent_before_v3(story_data: Callable[..., bytes]) -> None:
    assert_that(Story(story_data(V2, checksum=0xBEEF)).header.checksum).is_none()


def test_checksum_zero_means_not_recorded(
    story_data: Callable[..., bytes],
) -> None:
    assert_that(Story(story_data(V3)).header.checksum).is_none()


def test_checksum_reads_back(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V3, checksum=0xBEEF)).header

    assert_that(header.checksum).is_equal_to(0xBEEF)


def test_abbreviations_absent_in_v1(story_data: Callable[..., bytes]) -> None:
    assert_that(Story(story_data(V1)).header.abbreviations_address).is_none()


def test_abbreviations_address_from_v2(story_data: Callable[..., bytes]) -> None:
    header = Story(story_data(V2)).header

    assert_that(header.abbreviations_address).is_equal_to(0x01C0)


def test_short_extension_table_reads_as_zero(
    story_data: Callable[..., bytes],
) -> None:
    # § 11.1.7.1: reading past the end of the extension table gives 0. The
    # Unicode table address is word 3; this table only has 2.
    data = bytearray(story_data(5))
    data[0x36:0x38] = (0x0320).to_bytes(2, "big")
    data[0x0320:0x0322] = (2).to_bytes(2, "big")

    header = Story(bytes(data)).header

    assert_that(header.extension_table_address).is_equal_to(0x0320)
    assert_that(header.unicode_translation_table_address).is_equal_to(0)


def test_only_v6_has_a_main_routine(story_data: Callable[..., bytes]) -> None:
    assert_that(Story(story_data(V6)).header.has_main_routine).is_true()
    assert_that(Story(story_data(V5)).header.has_main_routine).is_false()
    assert_that(Story(story_data(V7)).header.has_main_routine).is_false()


def test_only_v6_and_v7_unpack_with_offsets(
    story_data: Callable[..., bytes],
) -> None:
    assert_that(Story(story_data(V5)).header.unpacks_with_offsets).is_false()
    assert_that(Story(story_data(V6)).header.unpacks_with_offsets).is_true()
    assert_that(Story(story_data(V7)).header.unpacks_with_offsets).is_true()
    assert_that(Story(story_data(V8)).header.unpacks_with_offsets).is_false()


def test_routine_unpacking_by_version(story_data: Callable[..., bytes]) -> None:
    def unpacked(version: int, **fields: int) -> int:
        header = Story(story_data(version, **fields)).header
        return header.unpack_routine_address(0x0100)

    assert_that(unpacked(V3)).is_equal_to(0x0200)
    assert_that(unpacked(V5)).is_equal_to(0x0400)
    assert_that(unpacked(V7, routines_offset=0x10)).is_equal_to(0x0480)
    assert_that(unpacked(V8)).is_equal_to(0x0800)
