from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import ExecutionError
from quendor.zmachine.memory import Memory
from quendor.zmachine.objects import NOTHING, ObjectTable, Property
from quendor.zmachine.story import Story
from quendor.zmachine.versions import V3, V4

OBJECTS_AT = 0x0080
ENTRIES_AT = OBJECTS_AT + 62
PROPS_1 = 0x0100
PROPS_2 = 0x0120


def world() -> dict[int, bytes]:
    """A tiny V3 world: object 1 contains 2 then 3.

    Object 1 has attribute 5 set, a short name of "hi", property 5 (two
    bytes, $beef) and property 3 (one byte, $42). Objects 2 and 3 share a
    nameless, propertyless table. The default for property 7 is $1234.
    """

    defaults = bytearray(62)
    defaults[12:14] = (0x1234).to_bytes(2, "big")

    def entry(attrs: bytes, parent: int, sibling: int, child: int, props: int) -> bytes:
        return attrs + bytes([parent, sibling, child]) + props.to_bytes(2, "big")

    entries = (
        entry(bytes([0x04, 0, 0, 0]), 0, 0, 2, PROPS_1)
        + entry(bytes(4), 1, 3, 0, PROPS_2)
        + entry(bytes(4), 1, 0, 0, PROPS_2)
    )

    props_1 = (
        bytes([1, 0xB5, 0xC5])  # short name, one word: "hi"
        + bytes([0x25, 0xBE, 0xEF])  # property 5, length 2
        + bytes([0x03, 0x42])  # property 3, length 1
        + bytes([0])
    )

    props_2 = bytes([0, 0])  # nameless and propertyless

    return {
        OBJECTS_AT: bytes(defaults) + entries,
        PROPS_1: props_1,
        PROPS_2: props_2,
    }


def table_for(
    story_data: Callable[..., bytes],
    version: int = V3,
    patches: dict[int, bytes] | None = None,
) -> tuple[ObjectTable, Memory]:
    data = bytearray(story_data(version, object_table=OBJECTS_AT))

    for address, blob in (patches if patches is not None else world()).items():
        data[address : address + len(blob)] = blob

    story = Story(bytes(data))

    return ObjectTable(story.memory, story.header), story.memory


def test_entries_follow_the_defaults_table(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    assert_that(table.entry_address(1)).is_equal_to(ENTRIES_AT)
    assert_that(table.entry_address(2)).is_equal_to(ENTRIES_AT + 9)


def test_object_zero_has_no_entry(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    with pytest.raises(ExecutionError) as error_info:
        table.entry_address(0)

    assert_that(str(error_info.value)).contains("object 0 means nothing")


def test_object_numbers_have_a_version_ceiling(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    with pytest.raises(ExecutionError) as error_info:
        table.entry_address(999)

    assert_that(str(error_info.value)).contains("out of range")


def test_attributes_read_and_write(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    assert_that(table.test_attribute(1, 5)).is_true()
    assert_that(table.test_attribute(1, 6)).is_false()
    assert_that(table.test_attribute(NOTHING, 5)).is_false()

    # Attribute 9 lives in the second byte: the divmod at work.
    table.set_attribute(2, 9)

    assert_that(table.test_attribute(2, 9)).is_true()

    table.set_attribute(NOTHING, 9)  # the policy's write form: a no-op


def test_attributes_have_a_version_ceiling(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    with pytest.raises(ExecutionError) as error_info:
        table.test_attribute(1, 32)

    assert_that(str(error_info.value)).contains("attribute 32 does not exist")


def test_property_table_locations(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    assert_that(table.property_table_address(1)).is_equal_to(PROPS_1)
    assert_that(table.short_name_address(1)).is_equal_to(PROPS_1 + 1)
    assert_that(table.first_property_address(1)).is_equal_to(PROPS_1 + 3)


def test_v3_property_headers(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    entry = table.read_property_header(PROPS_1 + 3)

    assert_that(entry).is_equal_to(
        Property(
            number=5,
            length=2,
            data_address=PROPS_1 + 4,
            next_address=PROPS_1 + 6,
        )
    )

    assert_that(table.read_property_header(PROPS_1 + 8)).is_none()


def test_v4_property_headers(story_data: Callable[..., bytes]) -> None:
    # Raw size bytes at a scratch address; the parser reads memory alone.
    table, _memory = table_for(
        story_data,
        version=V4,
        patches={
            0x0150: bytes([0x85, 0x03]),  # two-byte form, length 3
            0x0160: bytes([0x86, 0x00]),  # two-byte form, length 0 means 64
            0x0170: bytes([0x45]),  # one byte, bit 6 set: length 2
            0x0180: bytes([0x05]),  # one byte, bit 6 clear: length 1
        },
    )

    long_form = table.read_property_header(0x0150)
    assert long_form is not None
    assert_that((long_form.number, long_form.length)).is_equal_to((5, 3))

    longest = table.read_property_header(0x0160)
    assert longest is not None
    assert_that(longest.length).is_equal_to(64)

    two = table.read_property_header(0x0170)
    assert two is not None
    assert_that((two.number, two.length)).is_equal_to((5, 2))

    one = table.read_property_header(0x0180)
    assert one is not None
    assert_that((one.number, one.length)).is_equal_to((5, 1))


def test_find_property(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    found = table.find_property(1, 3)
    assert found is not None
    assert_that(found.length).is_equal_to(1)

    # 4 is between the stored 5 and 3: the descending order proves absence.
    assert_that(table.find_property(1, 4)).is_none()
    assert_that(table.find_property(1, 99)).is_none()
    assert_that(table.find_property(2, 5)).is_none()
    assert_that(table.find_property(NOTHING, 5)).is_none()


def test_put_property(story_data: Callable[..., bytes]) -> None:
    table, memory = table_for(story_data)

    table.put_property(1, 5, 0x1111)
    table.put_property(1, 3, 0xABCD)  # one byte: truncates
    table.put_property(NOTHING, 5, 1)  # the policy's write form

    assert_that(memory.read_word(PROPS_1 + 4)).is_equal_to(0x1111)
    assert_that(memory.read_byte(PROPS_1 + 7)).is_equal_to(0xCD)


def test_put_property_requires_the_property(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    with pytest.raises(ExecutionError) as error_info:
        table.put_property(2, 5, 1)

    assert_that(str(error_info.value)).contains("no property 5")


def test_get_property_falls_back_to_defaults(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    assert_that(table.get_property(1, 5)).is_equal_to(0xBEEF)
    assert_that(table.get_property(1, 3)).is_equal_to(0x42)
    assert_that(table.get_property(2, 7)).is_equal_to(0x1234)
    assert_that(table.get_property(NOTHING, 7)).is_equal_to(0)


def test_defaults_have_a_version_ceiling(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    with pytest.raises(ExecutionError) as error_info:
        table.default_property(32)

    assert_that(str(error_info.value)).contains("no default")


def test_the_tree_reads(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    assert_that(table.parent(2)).is_equal_to(1)
    assert_that(table.child(1)).is_equal_to(2)
    assert_that(table.sibling(2)).is_equal_to(3)

    assert_that(table.parent(NOTHING)).is_equal_to(NOTHING)
    assert_that(table.child(NOTHING)).is_equal_to(NOTHING)
    assert_that(table.sibling(NOTHING)).is_equal_to(NOTHING)


def test_insert_makes_the_first_child(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data)

    # 3 is mid-list under 1; moving it exercises the sibling-walk unlink.
    table.insert(3, 2)

    assert_that(table.parent(3)).is_equal_to(2)
    assert_that(table.child(2)).is_equal_to(3)
    assert_that(table.sibling(2)).is_equal_to(NOTHING)  # 3 left 1's list
    assert_that(table.sibling(3)).is_equal_to(NOTHING)

    # Now insert 2 under 3's old position: 2 was the eldest child of 1.
    table.insert(2, 1)

    assert_that(table.child(1)).is_equal_to(2)

    table.insert(NOTHING, 1)  # the policy's write form


def test_remove_detaches_the_eldest_child(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    table.remove(2)

    assert_that(table.parent(2)).is_equal_to(NOTHING)
    assert_that(table.sibling(2)).is_equal_to(NOTHING)
    assert_that(table.child(1)).is_equal_to(3)


def test_remove_tolerates_the_parentless_and_the_lost(
    story_data: Callable[..., bytes],
) -> None:
    table, _memory = table_for(story_data)

    table.remove(1)  # object 1 has no parent: only its own links reset
    table.remove(NOTHING)

    # A corrupt tree: object 3 claims a parent whose child list does not
    # contain it. The unlink walk comes up empty and shrugs.
    table.set_parent(3, 2)
    table.remove(3)

    assert_that(table.parent(3)).is_equal_to(NOTHING)


def test_unlinking_walks_past_earlier_siblings(
    story_data: Callable[..., bytes],
) -> None:
    # White-box: a child list long enough to step through needs an object
    # that is not in it at all, so the walk visits every sibling and ends.
    table, _memory = table_for(story_data)

    table._unlink_from(1, 99)

    assert_that(table.child(1)).is_equal_to(2)
    assert_that(table.sibling(2)).is_equal_to(3)


def test_v4_links_are_words(story_data: Callable[..., bytes]) -> None:
    table, _memory = table_for(story_data, version=V4, patches={})

    table.set_parent(1, 0x1234)

    assert_that(table.parent(1)).is_equal_to(0x1234)
