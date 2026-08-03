from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V1, V3


def test_undefined_version_is_rejected(story_data: Callable[..., bytes]) -> None:
    with pytest.raises(StoryFileError) as error_info:
        Story(story_data(0))

    assert_that(str(error_info.value)).contains("declares Version 0")
    assert_that(str(error_info.value)).contains("Versions 1 to 8")


def test_oversized_story_is_rejected(story_data: Callable[..., bytes]) -> None:
    with pytest.raises(StoryFileError) as error_info:
        Story(story_data(V1, total_size=128 * 1024 + 1))

    assert_that(str(error_info.value)).contains("story file is 131073 bytes")
    assert_that(str(error_info.value)).contains("at most 131072")


def test_truncated_story_is_rejected(story_data: Callable[..., bytes]) -> None:
    with pytest.raises(StoryFileError) as error_info:
        Story(story_data(V3, file_length_words=1000))

    assert_that(str(error_info.value)).contains("looks truncated")


def test_padding_beyond_recorded_length_is_accepted(
    story_data: Callable[..., bytes],
) -> None:
    story = Story(story_data(V3, file_length_words=760))

    assert_that(story.header.file_length).is_equal_to(1520)
