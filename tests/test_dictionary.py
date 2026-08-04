from collections.abc import Callable

from assertpy import assert_that

from quendor.zmachine.dictionary import Dictionary, tokenize
from quendor.zmachine.story import Story
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V3

DICTIONARY_AT = 0x0300
WORDS = ["go", "look", "mailbox", "open"]


def dictionary_for(
    story_data: Callable[..., bytes],
) -> tuple[Dictionary, TextCodec]:
    """A story whose dictionary holds WORDS, sorted as § 13.5 demands."""

    base = Story(story_data(V3))
    codec = TextCodec(base.memory, base.header)

    entries = sorted(codec.encode_word(word) for word in WORDS)

    table = bytes([2]) + b".," + bytes([7]) + len(entries).to_bytes(2, "big")

    for entry in entries:
        table += entry + bytes(3)  # entry length 7: 4 encoded + 3 data

    data = bytearray(story_data(V3))
    data[DICTIONARY_AT : DICTIONARY_AT + len(table)] = table

    story = Story(bytes(data))
    text = TextCodec(story.memory, story.header)

    return Dictionary(story.memory, story.header, text), text


def test_the_header_is_parsed(story_data: Callable[..., bytes]) -> None:
    dictionary, _codec = dictionary_for(story_data)

    assert_that(dictionary.separators).is_equal_to(frozenset({ord("."), ord(",")}))
    assert_that(len(dictionary)).is_equal_to(4)
    assert_that(dictionary.entry_address(1) - dictionary.entry_address(0)).is_equal_to(
        7
    )


def test_every_word_is_found(story_data: Callable[..., bytes]) -> None:
    dictionary, _codec = dictionary_for(story_data)

    for word in WORDS:
        address = dictionary.lookup(word)

        assert_that(address).is_not_equal_to(0)


def test_absent_words_answer_zero(story_data: Callable[..., bytes]) -> None:
    dictionary, _codec = dictionary_for(story_data)

    # Before the first entry, past the last, and in between.
    assert_that(dictionary.lookup("aaa")).is_equal_to(0)
    assert_that(dictionary.lookup("zzz")).is_equal_to(0)
    assert_that(dictionary.lookup("hello")).is_equal_to(0)


def test_entries_decode_back_to_their_words(
    story_data: Callable[..., bytes],
) -> None:
    dictionary, _codec = dictionary_for(story_data)

    decoded = sorted(dictionary.word(index) for index in range(len(dictionary)))

    # "mailbox" comes back as "mailbo": the six-character V3 horizon.
    assert_that(decoded).is_equal_to(sorted(word[:6] for word in WORDS))


def test_tokenize_splits_on_spaces() -> None:
    tokens = tokenize("open  mailbox", frozenset())

    assert_that(tokens).is_equal_to([("open", 0), ("mailbox", 6)])


def test_separators_divide_and_are_words() -> None:
    # § 13.6.1: each separator is a word in its own right.
    tokens = tokenize("look, mailbox", frozenset({ord(",")}))

    assert_that(tokens).is_equal_to([("look", 0), (",", 4), ("mailbox", 6)])


def test_tokenize_handles_the_edges() -> None:
    assert_that(tokenize("", frozenset())).is_equal_to([])
    assert_that(tokenize("   ", frozenset())).is_equal_to([])
    assert_that(tokenize("go", frozenset())).is_equal_to([("go", 0)])
