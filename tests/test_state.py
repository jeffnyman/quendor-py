from collections.abc import Callable

from assertpy import assert_that

from quendor.zmachine.state import Frame, GameState
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3, V6


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
