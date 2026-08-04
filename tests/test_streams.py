from collections.abc import Callable

from assertpy import assert_that

from quendor.zmachine.output import Screen
from quendor.zmachine.screen import ScreenModel
from quendor.zmachine.story import Story
from quendor.zmachine.streams import MemoryStream, OutputStreams
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V3


class RecordingScreen(Screen):
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


def streams_for(
    story_data: Callable[..., bytes],
) -> tuple[OutputStreams, RecordingScreen]:
    story = Story(story_data(V3))
    screen = RecordingScreen()
    text = TextCodec(story.memory, story.header)
    display = ScreenModel(story.memory, story.header, screen)

    return OutputStreams(story.memory, story.header, display, text), screen


def test_text_reaches_the_screen(story_data: Callable[..., bytes]) -> None:
    streams, screen = streams_for(story_data)

    streams.write("hello")

    assert_that(screen.written).is_equal_to(["hello"])
    assert_that(streams.printed).is_true()


def test_empty_writes_do_not_count_as_printing(
    story_data: Callable[..., bytes],
) -> None:
    streams, _screen = streams_for(story_data)

    streams.write("")

    assert_that(streams.printed).is_false()


def test_stream_three_swallows_everything(
    story_data: Callable[..., bytes],
) -> None:
    # White-box: the `output_stream` opcode is not implemented yet, so the
    # table selection is made directly. § 7.1.2.2: while stream 3 is
    # selected no other stream sees anything.
    streams, screen = streams_for(story_data)
    streams._tables.append(MemoryStream(table=0x0100))

    assert_that(streams.redirected).is_true()

    streams.write("a\nä€")

    # 'a' keeps its ASCII code, newline becomes ZSCII 13 rather than 10
    # (§ 7.1.2.2.1), a-umlaut has a table code, and the euro sign has no
    # code at all and becomes '?' (§ 7.5.3).
    assert_that(streams._tables[-1].characters).is_equal_to([97, 13, 155, 63])
    assert_that(screen.written).is_empty()
    assert_that(streams.printed).is_true()
