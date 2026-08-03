from assertpy import assert_that

from quendor.zmachine.opcodes import (
    ONE_OP,
    TWO_OP,
    VAR,
    ZERO_OP,
    lookup,
    lookup_ignoring_version,
)
from quendor.zmachine.versions import V3, V4, V5, V6, V8


def test_save_changes_shape_across_versions() -> None:
    v3 = lookup(ZERO_OP, 0x05, V3)
    v4 = lookup(ZERO_OP, 0x05, V4)

    assert v3 is not None
    assert_that(v3.branches).is_true()
    assert_that(v3.stores).is_false()

    assert v4 is not None
    assert_that(v4.stores).is_true()
    assert_that(v4.branches).is_false()

    assert_that(lookup(ZERO_OP, 0x05, V5)).is_none()


def test_one_op_fifteen_is_not_then_call_1n() -> None:
    v3 = lookup(ONE_OP, 0x0F, V3)
    v5 = lookup(ONE_OP, 0x0F, V5)

    assert v3 is not None
    assert_that(v3.name).is_equal_to("not")
    assert_that(v3.stores).is_true()

    assert v5 is not None
    assert_that(v5.name).is_equal_to("call_1n")
    assert_that(v5.stores).is_false()


def test_v8_uses_v5_rules() -> None:
    # pull only gains its store byte in V6, and V6 additions apply to V6
    # alone (§ 1.2.4): a V8 pull must stay one byte shorter.
    v6 = lookup(VAR, 0x09, V6)
    v8 = lookup(VAR, 0x09, V8)

    assert v6 is not None
    assert_that(v6.stores).is_true()

    assert v8 is not None
    assert_that(v8.stores).is_false()


def test_unknown_number_is_none() -> None:
    assert_that(lookup(TWO_OP, 0x00, V3)).is_none()


def test_ignoring_version_finds_the_earliest_definition() -> None:
    verify = lookup_ignoring_version(ZERO_OP, 0x0D)

    assert verify is not None
    assert_that(verify.name).is_equal_to("verify")


def test_ignoring_version_still_rejects_unknown_numbers() -> None:
    assert_that(lookup_ignoring_version(TWO_OP, 0x00)).is_none()
    # 0OP:14 is $BE's slot: never an opcode in any Version.
    assert_that(lookup_ignoring_version(ZERO_OP, 0x0E)).is_none()
