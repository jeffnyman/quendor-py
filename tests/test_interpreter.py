from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import UnimplementedOpcodeError
from quendor.zmachine.instructions import Instruction
from quendor.zmachine.interpreter import Interpreter
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3

PROGRAM = 0x0500


def machine_running(program: bytes, story_data: Callable[..., bytes]) -> Interpreter:
    data = bytearray(story_data(V3))
    data[PROGRAM : PROGRAM + len(program)] = program

    return Interpreter(Story(bytes(data)))


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
