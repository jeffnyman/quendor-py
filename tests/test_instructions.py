import pytest
from assertpy import assert_that

from quendor.zmachine.errors import IllegalOpcodeError
from quendor.zmachine.instructions import Decoder, Instruction, OperandType
from quendor.zmachine.memory import Memory
from quendor.zmachine.versions import V3, V4, V5

CODE = 0x40


def decode(raw: bytes, version: int = V3) -> Instruction:
    memory = Memory(bytes(CODE) + raw)
    return Decoder(memory, version).decode(CODE)


def test_long_form_with_small_constants() -> None:
    instruction = decode(bytes([0x14, 0x05, 0x0A, 0x07]))

    assert_that(instruction.name).is_equal_to("add")
    assert_that(instruction.form).is_equal_to("long")
    assert_that(instruction.namespace).is_equal_to("2OP")
    assert_that([o.type for o in instruction.operands]).is_equal_to(
        [OperandType.SMALL_CONSTANT, OperandType.SMALL_CONSTANT]
    )
    assert_that([o.value for o in instruction.operands]).is_equal_to([0x05, 0x0A])
    assert_that(instruction.store).is_equal_to(0x07)
    assert_that(instruction.store_address).is_equal_to(CODE + 3)
    assert_that(instruction.length).is_equal_to(4)
    assert_that(instruction.next_address).is_equal_to(CODE + 4)


def test_long_form_type_bits_pick_variables() -> None:
    instruction = decode(bytes([0x54, 0x01, 0x0A, 0x00]))

    assert_that([o.type for o in instruction.operands]).is_equal_to(
        [OperandType.VARIABLE, OperandType.SMALL_CONSTANT]
    )


def test_short_form_with_branch() -> None:
    instruction = decode(bytes([0x90, 0x2A, 0xC5]))

    assert_that(instruction.name).is_equal_to("jz")
    assert_that(instruction.form).is_equal_to("short")
    assert_that(instruction.namespace).is_equal_to("1OP")
    assert_that([o.value for o in instruction.operands]).is_equal_to([0x2A])

    branch = instruction.branch
    assert branch is not None
    assert_that(branch.on_true).is_true()
    assert_that(branch.offset).is_equal_to(5)
    assert_that(branch.is_return).is_false()

    # § 4.7.2: destination is the address after the branch data, plus the
    # offset, minus 2.
    assert_that(instruction.branch_address).is_equal_to(CODE + 2)
    assert_that(instruction.branch_target).is_equal_to(CODE + 3 + 5 - 2)


def test_branch_offsets_zero_and_one_mean_return() -> None:
    returns_false = decode(bytes([0x90, 0x00, 0xC0])).branch
    returns_true = decode(bytes([0x90, 0x00, 0xC1])).branch

    assert returns_false is not None
    assert_that(returns_false.returns_false).is_true()
    assert_that(returns_false.is_return).is_true()

    assert returns_true is not None
    assert_that(returns_true.returns_true).is_true()

    assert_that(decode(bytes([0x90, 0x00, 0xC0])).branch_target).is_none()


def test_two_byte_branch_offsets_are_signed() -> None:
    # First byte: on_true clear, two-byte form, top offset bits $$111111.
    instruction = decode(bytes([0x90, 0x00, 0x3F, 0xFC]))

    branch = instruction.branch
    assert branch is not None
    assert_that(branch.on_true).is_false()
    assert_that(branch.offset).is_equal_to(-4)
    assert_that(instruction.branch_target).is_equal_to(CODE + 4 - 4 - 2)

    forward = decode(bytes([0x90, 0x00, 0x00, 0x50])).branch
    assert forward is not None
    assert_that(forward.offset).is_equal_to(0x50)


def test_full_type_byte_gives_four_operands() -> None:
    instruction = decode(bytes([0xC1, 0x55, 0x01, 0x02, 0x03, 0x04, 0xC0]))

    assert_that([o.value for o in instruction.operands]).is_equal_to([1, 2, 3, 4])


def test_zero_op() -> None:
    instruction = decode(bytes([0xB0]))

    assert_that(instruction.name).is_equal_to("rtrue")
    assert_that(instruction.operands).is_empty()
    assert_that(instruction.store).is_none()
    assert_that(instruction.branch).is_none()
    assert_that(instruction.text).is_none()
    assert_that(instruction.length).is_equal_to(1)


def test_inline_text_is_measured() -> None:
    instruction = decode(bytes([0xB2, 0x00, 0x41, 0x80, 0x00]))

    assert_that(instruction.name).is_equal_to("print")
    assert_that(instruction.text).is_equal_to(bytes([0x00, 0x41, 0x80, 0x00]))
    assert_that(instruction.next_address).is_equal_to(CODE + 5)


def test_variable_form_with_var_count() -> None:
    instruction = decode(bytes([0xE0, 0x3F, 0x12, 0x34, 0x07]))

    assert_that(instruction.name).is_equal_to("call")
    assert_that(instruction.form).is_equal_to("variable")
    assert_that(instruction.namespace).is_equal_to("VAR")
    assert_that([o.type for o in instruction.operands]).is_equal_to(
        [OperandType.LARGE_CONSTANT]
    )
    assert_that(instruction.operands[0].value).is_equal_to(0x1234)
    assert_that(instruction.store).is_equal_to(0x07)


def test_variable_form_with_two_op_count() -> None:
    instruction = decode(bytes([0xC1, 0x57, 0x01, 0x02, 0x03, 0xC0]))

    assert_that(instruction.name).is_equal_to("je")
    assert_that(instruction.namespace).is_equal_to("2OP")
    assert_that([o.value for o in instruction.operands]).is_equal_to([1, 2, 3])
    assert_that(instruction.branch).is_not_none()


def test_call_vs2_reads_a_second_type_byte() -> None:
    raw = bytes([0xEC, 0x55, 0x7F, 0x01, 0x02, 0x03, 0x04, 0x05, 0x00])
    instruction = decode(raw, version=V4)

    assert_that(instruction.name).is_equal_to("call_vs2")
    assert_that([o.value for o in instruction.operands]).is_equal_to([1, 2, 3, 4, 5])
    assert_that(instruction.length).is_equal_to(len(raw))


def test_variable_form_numbers_use_five_bits() -> None:
    # VAR:21 is sound_effect, famously legal in V3 (§ 14). A four-bit
    # mask would read $F5 as VAR:5, print_char.
    instruction = decode(bytes([0xF5, 0x5F, 0x01, 0x02]))

    assert_that(instruction.name).is_equal_to("sound_effect")
    assert_that(instruction.out_of_version).is_false()

    # VAR:26 is call_vn2, which owns a second type byte; masked to VAR:10
    # it would lose it and desynchronize.
    raw = bytes([0xFA, 0x55, 0x7F, 0x01, 0x02, 0x03, 0x04, 0x05])
    vn2 = decode(raw, version=V5)

    assert_that(vn2.name).is_equal_to("call_vn2")
    assert_that([o.value for o in vn2.operands]).is_equal_to([1, 2, 3, 4, 5])


def test_extended_form() -> None:
    instruction = decode(bytes([0xBE, 0x02, 0x5F, 0x01, 0x02, 0x00]), version=V5)

    assert_that(instruction.name).is_equal_to("log_shift")
    assert_that(instruction.form).is_equal_to("extended")
    assert_that(instruction.namespace).is_equal_to("EXT")
    assert_that([o.value for o in instruction.operands]).is_equal_to([1, 2])
    assert_that(instruction.store).is_equal_to(0)


def test_high_extended_numbers_are_stepped_over() -> None:
    # § 14.2.1: EXT:30 and up are ignored rather than rejected.
    instruction = decode(bytes([0xBE, 0x30, 0xFF]), version=V5)

    assert_that(instruction.name).is_equal_to("ext_48")
    assert_that(instruction.operands).is_empty()
    assert_that(instruction.out_of_version).is_false()
    assert_that(instruction.next_address).is_equal_to(CODE + 3)


def test_early_opcodes_are_flagged_not_fatal() -> None:
    # piracy is 0OP:15, specified only from V5; in a V3 story it decodes
    # by its known shape and carries the flag.
    instruction = decode(bytes([0xBF, 0xC0]))

    assert_that(instruction.name).is_equal_to("piracy")
    assert_that(instruction.out_of_version).is_true()
    assert_that(instruction.branch).is_not_none()


def test_unknown_opcodes_raise() -> None:
    with pytest.raises(IllegalOpcodeError) as error_info:
        decode(bytes([0x00, 0x00, 0x00]))

    message = str(error_info.value)
    assert_that(message).contains("2OP:0")
    assert_that(message).contains("§ 14.2")


def test_extended_escape_is_not_an_opcode_before_v5() -> None:
    # In V3, $BE reads as short form 0OP:14, which no Version defines.
    with pytest.raises(IllegalOpcodeError):
        decode(bytes([0xBE, 0x00]))


def test_save_shape_follows_the_version() -> None:
    v3 = decode(bytes([0xB5, 0xC0]), version=V3)
    v4 = decode(bytes([0xB5, 0x00]), version=V4)

    assert_that(v3.branch).is_not_none()
    assert_that(v3.store).is_none()

    assert_that(v4.store).is_equal_to(0)
    assert_that(v4.branch).is_none()
