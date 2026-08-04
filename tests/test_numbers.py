from assertpy import assert_that

from quendor.zmachine.numbers import to_signed, to_unsigned


def test_small_values_are_themselves() -> None:
    assert_that(to_signed(0)).is_equal_to(0)
    assert_that(to_signed(0x7FFF)).is_equal_to(32767)


def test_the_high_bit_means_negative() -> None:
    assert_that(to_signed(0xFFFF)).is_equal_to(-1)
    assert_that(to_signed(0x8000)).is_equal_to(-32768)


def test_to_signed_masks_before_interpreting() -> None:
    assert_that(to_signed(0x1FFFF)).is_equal_to(-1)


def test_negatives_are_stored_as_complements() -> None:
    assert_that(to_unsigned(-1)).is_equal_to(0xFFFF)
    assert_that(to_unsigned(-5)).is_equal_to(0xFFFB)


def test_overflow_reduces_modulo_word_size() -> None:
    assert_that(to_unsigned(0x10003)).is_equal_to(3)
