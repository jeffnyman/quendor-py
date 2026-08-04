import pytest
from assertpy import assert_that

from quendor.zmachine.errors import EndOfInputError
from quendor.zmachine.input import ScriptedKeyboard


def test_scripted_lines_replay_in_order() -> None:
    keyboard = ScriptedKeyboard(["north", "open mailbox"])

    assert_that(keyboard.read_line(80)).is_equal_to("north")
    assert_that(keyboard.read_line(80)).is_equal_to("open mailbox")


def test_scripted_lines_trim_to_the_maximum() -> None:
    keyboard = ScriptedKeyboard(["abcdefgh"])

    assert_that(keyboard.read_line(3)).is_equal_to("abc")


def test_an_exhausted_script_is_the_end_of_input() -> None:
    with pytest.raises(EndOfInputError):
        ScriptedKeyboard([]).read_line(80)
