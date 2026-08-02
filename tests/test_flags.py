from assertpy import assert_that

from quendor.zmachine.flags import describe_flags_1, describe_flags_2
from quendor.zmachine.versions import V1, V3, V4, V5, V6


def test_no_set_bits_means_no_labels() -> None:
    assert_that(describe_flags_1(V3, 0)).is_empty()
    assert_that(describe_flags_2(V3, 0)).is_empty()


def test_legacy_flags_1_labels() -> None:
    labels = describe_flags_1(V3, 0b0000_1010)

    assert_that(labels).contains(
        "status line shows hours:mins, not score/turns",
        'the legendary "Tandy" bit',
    )


def test_zip_only_byte_swap_bit() -> None:
    assert_that(describe_flags_1(V1, 0b1)).contains(
        "byte-swapped story file (ZIP spec; unused in practice)"
    )


def test_flags_1_bit_1_changes_meaning_at_v6() -> None:
    assert_that(describe_flags_1(V4, 0b10)).contains(
        "status line type (see § 11 Remarks)"
    )
    assert_that(describe_flags_1(V6, 0b10)).contains("picture displaying available")


def test_unlisted_set_bits_still_surface() -> None:
    assert_that(describe_flags_1(V4, 0b0100_0000)).contains("bit 6 (not in § 11.1)")


def test_flags_2_bit_4_changes_meaning_at_v5() -> None:
    assert_that(describe_flags_2(V3, 0b1_0000)).contains(
        'sound effects? (V3; seen in the Amiga "The Lurking Horror")'
    )
    assert_that(describe_flags_2(V5, 0b1_0000)).contains(
        "game wants to use the UNDO opcodes"
    )


def test_labels_come_lowest_bit_first() -> None:
    labels = describe_flags_2(V6, 0b0111_1000)

    assert_that(labels).is_equal_to(
        (
            "game wants to use pictures",
            "game wants to use the UNDO opcodes",
            "game wants to use a mouse",
            "game wants to use colors",
        )
    )
