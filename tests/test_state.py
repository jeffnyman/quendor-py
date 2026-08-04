from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import ExecutionError, IllegalReturnError, StackError
from quendor.zmachine.state import Frame, GameState
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3, V6

ROUTINE = 0x0300
PACKED_ROUTINE = ROUTINE // 2


def state_with(
    story_data: Callable[..., bytes],
    patches: dict[int, bytes] | None = None,
    **fields: int,
) -> GameState:
    data = bytearray(story_data(V3, **fields))

    for address, blob in (patches or {}).items():
        data[address : address + len(blob)] = blob

    return GameState(Story(bytes(data)))


def test_boot_at_the_initial_program_counter(
    story_data: Callable[..., bytes],
) -> None:
    state = GameState(Story(story_data(V3)))

    assert_that(state.pc).is_equal_to(0x0500)
    assert_that(state.frames).is_length(1)
    assert_that(state.frames[0].local_variables).is_empty()


def test_v6_boots_inside_the_main_routine(
    story_data: Callable[..., bytes],
) -> None:
    state = GameState(Story(story_data(V6, initial_pc=0x0100, routines_offset=0x10)))

    # The main routine header sits at 4P + 8R_O = $0480; its local count
    # byte is zero, so execution starts one byte past it (§ 5.3).
    assert_that(state.pc).is_equal_to(0x0481)
    assert_that(state.frames).is_length(1)


def test_restart_reboots_the_machine(story_data: Callable[..., bytes]) -> None:
    state = GameState(Story(story_data(V3)))

    state.pc = 0x1234
    state.frames.append(
        Frame(return_pc=9, store_variable=None, local_variables=[], argument_count=0)
    )
    state.memory.write_word(0x20, 0xBEEF)

    state.restart()

    assert_that(state.pc).is_equal_to(0x0500)
    assert_that(state.frames).is_length(1)
    assert_that(state.memory.read_word(0x20)).is_equal_to(0)


def test_the_stack_round_trips_and_masks(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)

    state.push(0x1ABCD)

    assert_that(state.peek()).is_equal_to(0xABCD)
    assert_that(state.pop()).is_equal_to(0xABCD)


def test_the_empty_stack_faults_in_every_direction(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)

    with pytest.raises(StackError):
        state.pop()

    with pytest.raises(StackError):
        state.peek()

    with pytest.raises(StackError):
        state.replace_top(1)


def test_replace_top_writes_in_place(story_data: Callable[..., bytes]) -> None:
    state = state_with(story_data)

    state.push(1)
    state.replace_top(0x1000F)

    assert_that(state.pop()).is_equal_to(0x000F)


def test_variable_zero_is_the_stack(story_data: Callable[..., bytes]) -> None:
    state = state_with(story_data)

    state.write_variable(0x00, 5)

    assert_that(state.read_variable(0x00)).is_equal_to(5)
    assert_that(state.frame.evaluation_stack).is_empty()


def test_indirect_stack_access_works_in_place(
    story_data: Callable[..., bytes],
) -> None:
    # § 6.3.4: the seven indirect opcodes touch the top of the stack rather
    # than pushing and pulling.
    state = state_with(story_data)

    state.push(7)

    assert_that(state.read_variable(0x00, indirect=True)).is_equal_to(7)
    assert_that(state.read_variable(0x00, indirect=True)).is_equal_to(7)

    state.write_variable(0x00, 9, indirect=True)

    assert_that(state.pop()).is_equal_to(9)
    assert_that(state.frame.evaluation_stack).is_empty()


def test_locals_read_and_write_by_variable_number(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)
    state.frame.local_variables = [10, 20]

    assert_that(state.read_variable(0x01)).is_equal_to(10)

    state.write_variable(0x02, 0x1FFFF)

    assert_that(state.read_variable(0x02)).is_equal_to(0xFFFF)


def test_missing_locals_fault(story_data: Callable[..., bytes]) -> None:
    state = state_with(story_data)

    with pytest.raises(ExecutionError) as error_info:
        state.read_variable(0x03)

    assert_that(str(error_info.value)).contains("does not exist")


def test_globals_live_in_dynamic_memory(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data, global_variables=0x0100)

    state.write_variable(0x10, 0xBEEF)

    assert_that(state.read_variable(0x10)).is_equal_to(0xBEEF)
    assert_that(state.memory.read_word(0x0100)).is_equal_to(0xBEEF)


def test_variable_numbers_are_a_single_byte(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)

    with pytest.raises(ExecutionError) as error_info:
        state.read_variable(0x100)

    assert_that(str(error_info.value)).contains("not a variable number")


def test_the_global_table_has_240_entries(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)

    with pytest.raises(ExecutionError) as error_info:
        state.read_global(240)

    assert_that(str(error_info.value)).contains("table holds 240")


def test_calling_packed_address_zero_returns_false(
    story_data: Callable[..., bytes],
) -> None:
    # § 6.4.3: no call happens; the store variable simply receives 0.
    state = state_with(story_data)

    state.call_routine(0, [], 0x00)

    assert_that(state.pop()).is_equal_to(0)
    assert_that(state.frames).is_length(1)

    state.call_routine(0, [], None)

    assert_that(state.frame.evaluation_stack).is_empty()


def test_calling_a_routine_builds_a_frame(
    story_data: Callable[..., bytes],
) -> None:
    # Routine at $0300: two locals with initial values 5 and 7 (§ 5.2.1).
    state = state_with(
        story_data,
        patches={ROUTINE: bytes([2, 0x00, 0x05, 0x00, 0x07])},
    )

    state.call_routine(PACKED_ROUTINE, [0xAA], 0x03)

    assert_that(state.frames).is_length(2)
    assert_that(state.pc).is_equal_to(ROUTINE + 5)

    frame = state.frame
    assert_that(frame.local_variables).is_equal_to([0xAA, 7])
    assert_that(frame.argument_count).is_equal_to(1)
    assert_that(frame.store_variable).is_equal_to(0x03)
    assert_that(frame.return_pc).is_equal_to(0x0500)


def test_returning_pops_the_frame_and_stores(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data, patches={ROUTINE: bytes([0])})

    state.call_routine(PACKED_ROUTINE, [], 0x00)
    state.return_value(9)

    assert_that(state.frames).is_length(1)
    assert_that(state.pc).is_equal_to(0x0500)
    assert_that(state.pop()).is_equal_to(9)


def test_returning_without_a_store_variable_discards(
    story_data: Callable[..., bytes],
) -> None:
    # The call_vn family passes None: the value evaporates (§ 6.4.1).
    state = state_with(story_data, patches={ROUTINE: bytes([0])})

    state.call_routine(PACKED_ROUTINE, [], None)
    state.return_value(9)

    assert_that(state.frames).is_length(1)
    assert_that(state.frame.evaluation_stack).is_empty()


def test_returning_from_the_outermost_routine_faults(
    story_data: Callable[..., bytes],
) -> None:
    state = state_with(story_data)

    with pytest.raises(IllegalReturnError) as error_info:
        state.return_value(0)

    assert_that(str(error_info.value)).contains("outermost")
