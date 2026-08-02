from collections.abc import Callable
from pathlib import Path

import pytest
from assertpy import assert_that

from quendor.zmachine.blorb import Blorb, story_beside, story_bytes
from quendor.zmachine.errors import BlorbError, StoryFileError
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3, V5


def test_plain_story_passes_through(
    tmp_path: Path,
    story_data: Callable[..., bytes],
) -> None:
    data = story_data(V3)
    path = tmp_path / "story.z3"
    path.write_bytes(data)

    assert_that(story_bytes(path)).is_equal_to(data)


def test_wrapped_story_is_unwrapped(
    tmp_path: Path,
    story_data: Callable[..., bytes],
    blorb_data: Callable[..., bytes],
) -> None:
    story = story_data(V3)
    path = tmp_path / "story.zblorb"
    path.write_bytes(blorb_data([(b"Exec", b"ZCOD", story)]))

    assert_that(story_bytes(path)).is_equal_to(story)


def test_wrapped_story_loads_end_to_end(
    tmp_path: Path,
    story_data: Callable[..., bytes],
    blorb_data: Callable[..., bytes],
) -> None:
    story = story_data(V3, serial=b"840809")
    path = tmp_path / "story.zblorb"
    path.write_bytes(blorb_data([(b"Exec", b"ZCOD", story)]))

    assert_that(Story.from_path(path).header.serial).is_equal_to("840809")


def test_odd_length_chunks_are_stepped_over(
    tmp_path: Path,
    story_data: Callable[..., bytes],
    blorb_data: Callable[..., bytes],
) -> None:
    story = story_data(V3)
    path = tmp_path / "story.zblorb"
    path.write_bytes(
        blorb_data(
            [
                (b"Pict", b"PNG ", b"odd"),
                (b"Exec", b"ZCOD", story),
            ]
        )
    )

    assert_that(story_bytes(path)).is_equal_to(story)


def test_resource_blorb_is_diagnosed(
    tmp_path: Path,
    blorb_data: Callable[..., bytes],
) -> None:
    path = tmp_path / "art.blb"
    path.write_bytes(
        blorb_data(
            [
                (b"Pict", b"PNG ", b"aa"),
                (b"Pict", b"PNG ", b"bb"),
                (b"Snd ", b"OGGV", b"cc"),
                (b"Data", b"TEXT", b"dd"),
            ]
        )
    )

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    message = str(error_info.value)
    assert_that(message).contains("holds 2 pictures and 1 sound")
    assert_that(message).contains("no executable chunk")


def test_picture_only_blorb_counts_pictures(
    tmp_path: Path,
    blorb_data: Callable[..., bytes],
) -> None:
    path = tmp_path / "art.blb"
    path.write_bytes(blorb_data([(b"Pict", b"PNG ", b"aa")]))

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    assert_that(str(error_info.value)).contains("holds 1 picture and no executable")


def test_resource_blorb_names_the_story_beside_it(
    tmp_path: Path,
    story_data: Callable[..., bytes],
    blorb_data: Callable[..., bytes],
) -> None:
    (tmp_path / "game.z5").write_bytes(story_data(V5))
    path = tmp_path / "game.blb"
    path.write_bytes(blorb_data([(b"Snd ", b"OGGV", b"aa")]))

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    message = str(error_info.value)
    assert_that(message).contains("holds 1 sound")
    assert_that(message).contains("the story file beside it is game.z5")


def test_empty_blorb_reports_no_resources(
    tmp_path: Path,
    blorb_data: Callable[..., bytes],
) -> None:
    path = tmp_path / "empty.blb"
    path.write_bytes(blorb_data())

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    assert_that(str(error_info.value)).contains("holds no indexed resources")


def test_glulx_blorb_is_identified(
    tmp_path: Path,
    blorb_data: Callable[..., bytes],
) -> None:
    path = tmp_path / "game.gblorb"
    path.write_bytes(blorb_data([(b"Exec", b"GLUL", b"\x00" * 4)]))

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    message = str(error_info.value)
    assert_that(message).contains("GLUL (a Glulx game)")
    assert_that(message).contains("rather than Z-code")


def test_other_executables_are_named(
    tmp_path: Path,
    blorb_data: Callable[..., bytes],
) -> None:
    path = tmp_path / "game.blorb"
    path.write_bytes(blorb_data([(b"Exec", b"TAD3", b"\x00" * 4)]))

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    message = str(error_info.value)
    assert_that(message).contains("TAD3")
    assert_that(message).does_not_contain("Glulx")


def test_blorb_without_index_is_reported(tmp_path: Path) -> None:
    payload = b"IFRS" + b"JUNK" + (2).to_bytes(4, "big") + b"hi"
    path = tmp_path / "broken.blorb"
    path.write_bytes(b"FORM" + len(payload).to_bytes(4, "big") + payload)

    with pytest.raises(StoryFileError) as error_info:
        story_bytes(path)

    assert_that(str(error_info.value)).contains("no resource index")


def test_blorb_class_rejects_non_iff_data() -> None:
    with pytest.raises(BlorbError):
        Blorb(b"\x00" * 16)


def test_story_beside_prefers_the_exact_name(
    tmp_path: Path,
    story_data: Callable[..., bytes],
) -> None:
    (tmp_path / "game.z3").write_bytes(story_data(V3))
    (tmp_path / "game-extras.z3").write_bytes(story_data(V3))

    found = story_beside(tmp_path / "game.blb")

    assert found is not None
    assert_that(found.name).is_equal_to("game.z3")


def test_story_beside_matches_a_longer_sibling_name(
    tmp_path: Path,
    story_data: Callable[..., bytes],
) -> None:
    (tmp_path / "game-r1.z3").write_bytes(story_data(V3))
    (tmp_path / "unrelated.z3").write_bytes(story_data(V3))

    found = story_beside(tmp_path / "game.blb")

    assert found is not None
    assert_that(found.name).is_equal_to("game-r1.z3")


def test_story_beside_matches_a_shorter_sibling_name(
    tmp_path: Path,
    story_data: Callable[..., bytes],
) -> None:
    (tmp_path / "game.z3").write_bytes(story_data(V3))

    found = story_beside(tmp_path / "game-full.blb")

    assert found is not None
    assert_that(found.name).is_equal_to("game.z3")


def test_story_beside_can_come_up_empty(tmp_path: Path) -> None:
    assert_that(story_beside(tmp_path / "game.blb")).is_none()
