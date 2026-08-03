from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.memory import Memory
from quendor.zmachine.routines import read_routine
from quendor.zmachine.versions import V3, V5

ROUTINE = 0x0300


def memory_holding(routine: bytes, story_data: Callable[..., bytes]) -> Memory:
    data = bytearray(story_data(V3))
    data[ROUTINE : ROUTINE + len(routine)] = routine

    return Memory(bytes(data))


def test_early_versions_store_initial_local_values(
    story_data: Callable[..., bytes],
) -> None:
    memory = memory_holding(bytes([2, 0x12, 0x34, 0x56, 0x78]), story_data)

    routine = read_routine(memory, V3, ROUTINE)

    assert_that(routine.address).is_equal_to(ROUTINE)
    assert_that(routine.initial_locals).is_equal_to((0x1234, 0x5678))
    assert_that(routine.first_instruction).is_equal_to(ROUTINE + 5)


def test_later_versions_start_locals_at_zero(
    story_data: Callable[..., bytes],
) -> None:
    memory = memory_holding(bytes([3]), story_data)

    routine = read_routine(memory, V5, ROUTINE)

    assert_that(routine.initial_locals).is_equal_to((0, 0, 0))
    assert_that(routine.first_instruction).is_equal_to(ROUTINE + 1)


def test_too_many_locals_is_a_broken_story(
    story_data: Callable[..., bytes],
) -> None:
    memory = memory_holding(bytes([16]), story_data)

    with pytest.raises(StoryFileError) as error_info:
        read_routine(memory, V3, ROUTINE)

    assert_that(str(error_info.value)).contains("at most 15")
