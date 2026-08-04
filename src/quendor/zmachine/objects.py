"""The object table (§ 12)."""

from dataclasses import dataclass
from typing import Final

from quendor.zmachine.errors import ExecutionError
from quendor.zmachine.header import Header
from quendor.zmachine.memory import Memory
from quendor.zmachine.numbers import BYTE_MASK, WORD_MASK
from quendor.zmachine.versions import V3

"""Object 0 means "nothing"; there is formally no such object (§ 12.3).

Games name it constantly -- walking a tree reaches "nothing" at the end of
every branch -- so reads about object 0 answer "nothing" and writes to it do
nothing, rather than being errors. 'Zork: The Undiscovered Underground' calls
`get_child` on it within a few moves.

`entry_address` stays strict, because there is genuinely no entry to point at,
and § 15 makes `print_obj` of an invalid object something to halt on.
"""
NOTHING: Final = 0

"""A stored length of 0 in the two-byte form means 64 (§ 12.4.2.1.1)."""
MAXIMUM_LONG_PROPERTY: Final = 64

"""Bit 7 of a size byte marks the two-byte form (§ 12.4.2.1)."""
V4_LONG_PROPERTY: Final = 0x80

"""Bit 6 of a one-byte size byte: set means length 2, clear means 1."""
V4_TWO_BYTE_LENGTH: Final = 0x40

V4_PROPERTY_NUMBER_MASK: Final = 0b0011_1111
V4_LENGTH_MASK: Final = 0b0011_1111

V3_NUMBER_MASK: Final = 0b0001_1111
V3_LENGTH_SHIFT: Final = 5

BITS_PER_BYTE: Final = 8


@dataclass(frozen=True)
class ObjectFormat:
    """How wide everything is, for one Version family (§ 12.3)."""

    attribute_bytes: int
    attribute_count: int

    """Bytes per parent/sibling/child number."""
    link_size: int

    entry_size: int
    default_count: int
    maximum_object: int


V3_FORMAT: Final = ObjectFormat(
    attribute_bytes=4,
    attribute_count=32,
    link_size=1,
    entry_size=9,
    default_count=31,
    maximum_object=255,
)

V4_FORMAT: Final = ObjectFormat(
    attribute_bytes=6,
    attribute_count=48,
    link_size=2,
    entry_size=14,
    default_count=63,
    maximum_object=65535,
)


@dataclass(frozen=True)
class Property:
    """One entry in an object's property table (§ 12.4)."""

    number: int
    length: int
    data_address: int

    """Where the following property's size byte begins."""
    next_address: int


class ObjectTable:
    """Reads and writes the object table of § 12."""

    def __init__(self, memory: Memory, header: Header) -> None:
        self._memory = memory
        self._version = header.version

        self._defaults = header.object_table_address
        self.format = V3_FORMAT if header.version <= V3 else V4_FORMAT

        # The entries follow the property defaults table (§ 12.2).
        self._entries = self._defaults + 2 * self.format.default_count

    # -- Entries -------------------------------------------------------

    def entry_address(self, number: int) -> int:
        """Byte address of an object's entry (§ 12.3)."""

        self._check(number)
        return self._entries + (number - 1) * self.format.entry_size

    def _check(self, number: int) -> None:
        if number == NOTHING:
            message = "object 0 means nothing; it has no entry (§ 12.3)"
            raise ExecutionError(message)

        if not 0 < number <= self.format.maximum_object:
            message = (
                f"object {number} is out of range for Version {self._version} (§ 12.3)"
            )
            raise ExecutionError(message)

    # -- Attributes (§ 12.3.1) -----------------------------------------
    #
    # Stored topmost bit first: attribute 0 is bit 7 of the first byte.

    def set_attribute(self, number: int, attribute: int) -> None:
        """Set an object's attribute flag (§ 15, `set_attr`).

        Object 0 has no attributes to set, so nothing happens -- the
        `NOTHING` policy above, in its write form.
        """
        if number == NOTHING:
            return

        offset, bit = self._attribute_position(attribute)
        address = self.entry_address(number) + offset
        self._memory.write_byte(address, self._memory.read_byte(address) | (1 << bit))

    def test_attribute(self, number: int, attribute: int) -> bool:
        """Whether an object's attribute flag is set (§ 12.3.1).

        Object 0 has no attributes, so every test on it answers False --
        the `NOTHING` policy above, in its read form.
        """
        if number == NOTHING:
            return False

        offset, bit = self._attribute_position(attribute)
        byte = self._memory.read_byte(self.entry_address(number) + offset)

        return bool(byte & (1 << bit))

    def _attribute_position(self, attribute: int) -> tuple[int, int]:
        if not 0 <= attribute < self.format.attribute_count:
            message = (
                f"attribute {attribute} does not exist; Version "
                f"{self._version} objects have {self.format.attribute_count} "
                f"(§ 12.3)"
            )
            raise ExecutionError(message)

        offset, bit = divmod(attribute, BITS_PER_BYTE)

        return offset, BITS_PER_BYTE - 1 - bit

    # -- Property tables (§ 12.4) --------------------------------------

    def short_name_address(self, number: int) -> int:
        """Where the object's short name begins (§ 12.4).

        The table opens with a byte giving the name's length in *words*.
        """
        return self.property_table_address(number) + 1

    def property_table_address(self, number: int) -> int:
        """Byte address of an object's property table (§ 12.3.1).

        The pointer word ends the object's entry, after the attributes and
        the three family links, in every Version's layout.
        """
        address = (
            self.entry_address(number)
            + self.format.attribute_bytes
            + 3 * self.format.link_size
        )

        return self._memory.read_word(address)

    def first_property_address(self, number: int) -> int:
        """Where an object's first property entry begins (§ 12.4).

        The property table opens with the object's short name: one byte
        giving its length in 2-byte words, then the encoded text itself.
        The properties follow immediately after.
        """
        table = self.property_table_address(number)
        words = self._memory.read_byte(table)
        return table + 1 + 2 * words

    def read_property_header(self, address: int) -> Property | None:
        """Parse the size byte or bytes at an address (§ 12.4.1, § 12.4.2).

        Returns None at the terminating zero byte that ends a property list.
        """

        first = self._memory.read_byte(address)

        if first == 0:
            return None

        if self._version <= V3:
            # 32 times (length - 1), plus the property number (§ 12.4.1).
            number = first & V3_NUMBER_MASK
            length = (first >> V3_LENGTH_SHIFT) + 1
            data = address + 1
        elif first & V4_LONG_PROPERTY:
            # Two size bytes; the second holds the length (§ 12.4.2.1).
            number = first & V4_PROPERTY_NUMBER_MASK
            length = self._memory.read_byte(address + 1) & V4_LENGTH_MASK
            length = length or MAXIMUM_LONG_PROPERTY
            data = address + 2
        else:
            # One size byte; bit 6 chooses length 2 or 1 (§ 12.4.2.2).
            number = first & V4_PROPERTY_NUMBER_MASK
            length = 2 if first & V4_TWO_BYTE_LENGTH else 1
            data = address + 1

        return Property(
            number=number,
            length=length,
            data_address=data,
            next_address=data + length,
        )

    def find_property(self, number: int, property_number: int) -> Property | None:
        """The property an object provides, or None if it does not (§ 12.4).

        The search stops as soon as it passes the number it wants. § 12.4
        stores properties "in descending numerical order" and says "this order
        is essential and is not a matter of convention", so a smaller number
        means the wanted one is absent -- and reading on is not merely wasted
        work but unsafe.

        `destruct-r1-s030509.z1` is why. Its object 23 holds properties 20, 4
        and 1, and the bytes after them do not decode as a property list at
        all: walked to the end, the search ran out of the object's table
        entirely and reported a property 24 forty bytes away. The Inform
        library read that as a `found_in` routine, called it, and landed in
        the middle of somebody else's code.
        """
        if number == NOTHING:
            return None

        address = self.first_property_address(number)

        while (entry := self.read_property_header(address)) is not None:
            if entry.number == property_number:
                return entry

            if entry.number < property_number:
                return None

            address = entry.next_address

        return None

    def put_property(self, number: int, property_number: int, value: int) -> None:
        """Write a property (§ 15, `put_prop`)."""

        if number == NOTHING:
            return

        entry = self.find_property(number, property_number)

        if entry is None:
            message = (
                f"object {number} has no property {property_number} to write "
                f"(§ 15, put_prop)"
            )
            raise ExecutionError(message)

        if entry.length == 1:
            self._memory.write_byte(entry.data_address, value & BYTE_MASK)
        else:
            self._memory.write_word(entry.data_address, value & WORD_MASK)

    def get_property(self, number: int, property_number: int) -> int:
        """Read a property, falling back to the default (§ 15, `get_prop`)."""
        if number == NOTHING:
            return 0

        entry = self.find_property(number, property_number)

        if entry is None:
            return self.default_property(property_number)

        if entry.length == 1:
            return self._memory.read_byte(entry.data_address)

        # § 15 makes lengths above 2 illegal here and leaves the result
        # unspecified; reading the first word is what interpreters do.
        return self._memory.read_word(entry.data_address)

    def default_property(self, property_number: int) -> int:
        """The value used when an object does not provide a property (§ 12.2)."""

        if not 1 <= property_number <= self.format.default_count:
            message = (
                f"property {property_number} has no default; Version "
                f"{self._version} defines {self.format.default_count} (§ 12.2)"
            )
            raise ExecutionError(message)

        return self._memory.read_word(self._defaults + 2 * (property_number - 1))

    # -- The tree (§ 12.3) ---------------------------------------------
    #
    # Reads about object 0 answer NOTHING, per the policy above. The
    # `set_` methods are the strict layer: they write real entries, and
    # `insert` and `remove` do the object-0 guarding before reaching them.

    def parent(self, number: int) -> int:
        """The object containing this one, or NOTHING (§ 12.3)."""
        return NOTHING if number == NOTHING else self._read_link(number, 0)

    def child(self, number: int) -> int:
        """The first object inside this one, or NOTHING (§ 12.3)."""
        return NOTHING if number == NOTHING else self._read_link(number, 2)

    def sibling(self, number: int) -> int:
        """The next object in the same container, or NOTHING (§ 12.3)."""
        return NOTHING if number == NOTHING else self._read_link(number, 1)

    def set_parent(self, number: int, value: int) -> None:
        """Point an object's parent link at another object, or NOTHING."""
        self._write_link(number, 0, value)

    def set_sibling(self, number: int, value: int) -> None:
        """Point an object's sibling link at another object, or NOTHING."""
        self._write_link(number, 1, value)

    def set_child(self, number: int, value: int) -> None:
        """Point an object's child link at another object, or NOTHING."""
        self._write_link(number, 2, value)

    def insert(self, number: int, destination: int) -> None:
        """Make an object the first child of another (§ 15, `insert_obj`).

        Afterwards the destination's child is this object, and this object's
        sibling is whatever the destination's child used to be.
        """

        if number == NOTHING:
            return

        self.remove(number)
        self.set_parent(number, destination)
        self.set_sibling(number, self.child(destination))
        self.set_child(destination, number)

    def remove(self, number: int) -> None:
        """Detach an object from its parent (§ 15, `remove_obj`).

        Its own children come with it; only the link upward is broken.
        """

        if number == NOTHING:
            return

        parent = self.parent(number)

        if parent != NOTHING:
            self._unlink_from(parent, number)

        self.set_parent(number, NOTHING)
        self.set_sibling(number, NOTHING)

    def _link_address(self, number: int, index: int) -> int:
        """Byte address of family link `index` in an object's entry."""
        return (
            self.entry_address(number)
            + self.format.attribute_bytes
            + index * self.format.link_size
        )

    def _read_link(self, number: int, index: int) -> int:
        """Read family link `index`: 0 parent, 1 sibling, 2 child (§ 12.3.1).

        A link is one byte in V1-3 and a word from V4, per the format.
        """

        address = self._link_address(number, index)

        if self.format.link_size == 1:
            return self._memory.read_byte(address)

        return self._memory.read_word(address)

    def _write_link(self, number: int, index: int, value: int) -> None:
        """Write family link `index`, at the format's link width."""

        address = self._link_address(number, index)

        if self.format.link_size == 1:
            self._memory.write_byte(address, value)
        else:
            self._memory.write_word(address, value)

    def _unlink_from(self, parent: int, number: int) -> None:
        """Close the gap this object leaves in its parent's child list."""

        eldest = self.child(parent)

        if eldest == number:
            self.set_child(parent, self.sibling(number))
            return

        previous = eldest

        while previous != NOTHING:
            following = self.sibling(previous)

            if following == number:
                self.set_sibling(previous, self.sibling(number))
                return

            previous = following
