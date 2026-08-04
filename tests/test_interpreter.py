from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import ExecutionError, UnimplementedOpcodeError
from quendor.zmachine.instructions import Instruction
from quendor.zmachine.interpreter import Interpreter
from quendor.zmachine.output import Screen
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3

PROGRAM = 0x0500
ROUTINE = 0x0300


class RecordingScreen(Screen):
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


def machine_running(
    program: bytes,
    story_data: Callable[..., bytes],
    routine: bytes | None = None,
    screen: Screen | None = None,
) -> Interpreter:
    data = bytearray(story_data(V3))
    data[PROGRAM : PROGRAM + len(program)] = program

    if routine is not None:
        data[ROUTINE : ROUTINE + len(routine)] = routine

    return Interpreter(Story(bytes(data)), screen if screen is not None else Screen())


def test_boot_state(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0xB0]), story_data)

    assert_that(machine.state.pc).is_equal_to(PROGRAM)
    assert_that(machine.instruction_count).is_equal_to(0)
    assert_that(machine.running).is_true()


def test_step_reports_unimplemented_opcodes(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0xB0]), story_data)

    with pytest.raises(UnimplementedOpcodeError) as error_info:
        machine.step()

    message = str(error_info.value)
    assert_that(message).contains("$00500: rtrue (0OP:0)")
    assert_that(message).contains("not implemented yet")
    assert_that(message).contains("define `Interpreter._op_rtrue`")

    # The PC and count had already advanced: a call must record the address
    # after itself as the return point (§ 4.7.2 measures from there too).
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 1)
    assert_that(machine.instruction_count).is_equal_to(1)


def test_run_dispatches_to_handlers(
    story_data: Callable[..., bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = machine_running(bytes([0xB0]), story_data)

    def stop(_instruction: Instruction) -> None:
        machine.running = False

    # No opcode handlers exist yet; graft one on so the dispatch path is
    # exercised until the real ones arrive.
    monkeypatch.setattr(machine, "_op_rtrue", stop, raising=False)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.instruction_count).is_equal_to(1)


def test_add_is_signed(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x14, 0x05, 0x0A, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(15)


def test_sub_stores_negatives_as_complements(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0x15, 0x05, 0x0A, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0xFFFB)


def test_je_branches_when_equal(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x01, 0x05, 0x05, 0xC3]), story_data)

    machine.step()

    # Offset 3: land one byte past the instruction's end (§ 4.7.2).
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4 + 1)


def test_je_falls_through_when_unequal(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0x01, 0x05, 0x06, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4)


def test_je_matches_any_later_operand(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0xC1, 0x57, 0x05, 0x09, 0x05, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 6 + 1)


def test_branches_respect_their_polarity(
    story_data: Callable[..., bytes],
) -> None:
    # Branch byte $43: branch on FALSE. The operands are equal, so no jump.
    machine = machine_running(bytes([0x01, 0x05, 0x05, 0x43]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4)


def test_jz(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x90, 0x00, 0xC4]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 3 + 2)


def test_jump_takes_a_signed_offset(story_data: Callable[..., bytes]) -> None:
    forward = machine_running(bytes([0x8C, 0x00, 0x0A]), story_data)
    forward.step()

    assert_that(forward.state.pc).is_equal_to(PROGRAM + 3 + 10 - 2)

    backward = machine_running(bytes([0x8C, 0xFF, 0xF6]), story_data)
    backward.step()

    assert_that(backward.state.pc).is_equal_to(PROGRAM + 3 - 10 - 2)


def test_storew_and_loadw_round_trip(
    story_data: Callable[..., bytes],
) -> None:
    program = (
        bytes([0xE1, 0x57, 0x80, 0x01, 0xAB])  # storew #80 #01 #ab
        + bytes([0x0F, 0x80, 0x01, 0x00])  # loadw #80 #01 -> sp
    )
    machine = machine_running(program, story_data)

    machine.step()
    machine.step()

    assert_that(machine.state.memory.read_word(0x82)).is_equal_to(0xAB)
    assert_that(machine.state.pop()).is_equal_to(0xAB)


def test_call_and_ret_round_trip(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),  # call $0300 -> sp
        story_data,
        routine=bytes([0x00, 0x9B, 0x2A]),  # no locals; ret #2a
    )

    machine.step()

    assert_that(machine.state.frames).is_length(2)
    assert_that(machine.state.pc).is_equal_to(ROUTINE + 1)

    machine.step()

    assert_that(machine.state.frames).is_length(1)
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 5)
    assert_that(machine.state.pop()).is_equal_to(0x2A)


def test_branches_can_return_instead_of_jumping(
    story_data: Callable[..., bytes],
) -> None:
    # The routine's je branches with offset 1: return true (§ 4.7.1).
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),
        story_data,
        routine=bytes([0x00, 0x01, 0x05, 0x05, 0xC1]),
    )

    machine.step()
    machine.step()

    assert_that(machine.state.frames).is_length(1)
    assert_that(machine.state.pop()).is_equal_to(1)


def test_return_false_branches_store_zero(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),
        story_data,
        routine=bytes([0x00, 0x01, 0x05, 0x05, 0xC0]),
    )

    machine.step()
    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0)


def test_print_paddr_decodes_through_the_streams(
    story_data: Callable[..., bytes],
) -> None:
    screen = RecordingScreen()

    # The routine slot holds a packed string instead: "hi" in one word.
    machine = machine_running(
        bytes([0x8D, 0x01, 0x80]),  # print_paddr #0180
        story_data,
        routine=bytes([0xB5, 0xC5]),
        screen=screen,
    )

    machine.step()

    assert_that("".join(screen.written)).is_equal_to("hi")


def test_quit_stops_the_machine(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0xBA]), story_data)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.instruction_count).is_equal_to(1)


def test_call_with_no_operands_faults(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0xE0, 0xFF]), story_data)

    with pytest.raises(ExecutionError) as error_info:
        machine.step()

    assert_that(str(error_info.value)).contains("has no routine to call")


def test_helpers_tolerate_absent_store_and_branch(
    story_data: Callable[..., bytes],
) -> None:
    # rtrue carries neither a store byte nor branch data; the helpers must
    # shrug rather than assume.
    machine = machine_running(bytes([0xB0]), story_data)
    rtrue = machine.decoder.decode(PROGRAM)

    machine._store(rtrue, 5)
    machine._branch(rtrue, condition=True)

    assert_that(machine.state.frame.evaluation_stack).is_empty()
    assert_that(machine.state.pc).is_equal_to(PROGRAM)
