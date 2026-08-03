"""Decoding instructions (§ 4).

An instruction is a sequence of optional parts in a fixed order (§ 4.1):

    opcode          1 or 2 bytes
    operand types   0, 1 or 2 bytes
    operands        0 to 8, each 1 or 2 bytes
    store variable  0 or 1 byte
    branch offset   0, 1 or 2 bytes
    inline text     an encoded string of any length

Which parts are present depends on the opcode, and for some opcodes on the
Version, which is why decoding consults the § 14 table in `opcodes`.

This module works out the *shape* of an instruction and nothing more. It does
not evaluate operands, follow branches, or decode inline text into characters
-- reading a variable operand means touching the stack, which belongs to
execution, and turning text into characters is § 3.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Final

from quendor.zmachine.errors import IllegalOpcodeError
from quendor.zmachine.memory import Memory
from quendor.zmachine.opcodes import (
    EXT,
    EXTENDED_ESCAPE,
    FIRST_IGNORABLE_EXT,
    ONE_OP,
    TWO_OP,
    VAR,
    ZERO_OP,
    Opcode,
    lookup,
    lookup_ignoring_version,
)
from quendor.zmachine.versions import V5

"""call_vs2 and call_vn2 take a second byte of operand types (§ 4.4.3.1)."""
_DOUBLE_VARIABLE_OPCODES: Final = frozenset({0x0C, 0x1A})

"""What the top two bits of an opcode byte say about its form (§ 4.3)."""
VARIABLE_FORM_BITS: Final = 0b11
SHORT_FORM_BITS: Final = 0b10


class OperandType(IntEnum):
    """The four operand types of § 4.2, as their 2-bit encodings."""

    LARGE_CONSTANT = 0b00
    SMALL_CONSTANT = 0b01
    VARIABLE = 0b10
    OMITTED = 0b11


@dataclass(frozen=True)
class Operand:
    """One operand: how it was encoded, and the value as stored.

    A VARIABLE operand's value is a variable *number* (§ 4.2.2), not the
    value held there; resolving it is the interpreter's job, not the
    decoder's.
    """

    type: OperandType
    value: int


@dataclass(frozen=True)
class Branch:
    """Branch data (§ 4.7).

    An offset of 0 or 1 does not name an address at all: it means return
    false or return true from the current routine (§ 4.7.1).
    """

    on_true: bool
    offset: int

    @property
    def returns_false(self) -> bool:
        """The branch returns false from the routine, not jumping (§ 4.7.1)."""
        return self.offset == 0

    @property
    def returns_true(self) -> bool:
        """The branch returns true from the routine, not jumping (§ 4.7.1)."""
        return self.offset == 1

    @property
    def is_return(self) -> bool:
        """The branch leaves the routine rather than naming a target."""
        return self.returns_false or self.returns_true


@dataclass(frozen=True)
class Instruction:
    """A decoded instruction and the span of memory it occupies."""

    """Byte address of the opcode."""
    address: int

    """Byte address just past the instruction; where the PC lands next."""
    next_address: int

    form: str
    namespace: str
    number: int
    opcode: Opcode
    operands: tuple[Operand, ...]
    store: int | None
    branch: Branch | None

    """Raw encoded string bytes for `print` and `print_ret` (§ 4.8)."""
    text: bytes | None

    store_address: int | None = None
    branch_address: int | None = None

    """Set when the opcode postdates the story file's own Version (§ 14.2)."""
    out_of_version: bool = False

    @property
    def length(self) -> int:
        """How many bytes of memory the instruction occupies."""
        return self.next_address - self.address

    @property
    def name(self) -> str:
        """The opcode's mnemonic, as § 14 spells it."""
        return self.opcode.name

    @property
    def branch_target(self) -> int | None:
        """Where a taken branch goes, or None if it returns instead.

        § 4.7.2: the destination is the address after the branch data, plus
        the offset, minus 2. Since no branching opcode also carries inline
        text, the address after the branch data is where the instruction
        ends.
        """

        if self.branch is None or self.branch.is_return:
            return None
        return self.next_address + self.branch.offset - 2


class Decoder:
    """Decodes instructions from a story's memory under one Version's rules."""

    def __init__(self, memory: Memory, version: int) -> None:
        self._memory = memory
        self._version = version

    def decode(self, address: int) -> Instruction:
        """Decode the instruction beginning at a byte address."""

        start = address
        opcode_byte = self._memory.read_byte(address)
        address += 1

        # $BE must be tested before the form bits are examined: its top two
        # bits are $$10, so it would otherwise read as short form (§ 4.3).
        if opcode_byte == EXTENDED_ESCAPE and self._version >= V5:
            # If the opcode is 190 ($BE in hexadecimal) and the version is
            # 5 or later, the form is "extended" (§ 4.3)
            form = "extended"
            namespace = EXT
            number = self._memory.read_byte(address)
            address += 1
            types, address = self._read_type_bytes(address, number, namespace)
        elif opcode_byte >> 6 == VARIABLE_FORM_BITS:
            form = "variable"
            # The opcode number is given in the bottom 5 bits (§ 4.3.3)
            number = opcode_byte & 0b0001_1111
            # if bit 5 is 0 then the count is 2OP; if it is 1, then the count is
            # VAR (§ 4.3.3)
            namespace = VAR if opcode_byte & 0b0010_0000 else TWO_OP
            types, address = self._read_type_bytes(address, number, namespace)
        elif opcode_byte >> 6 == SHORT_FORM_BITS:
            form = "short"
            # bits 4 and 5 of the opcode byte give an operand type (§ 4.3.1)
            number = opcode_byte & 0b0000_1111

            # In short form, bits 4 and 5 of the opcode give the type (§ 4.4.1)
            encoded = OperandType((opcode_byte >> 4) & 0b11)

            # An omitted operand here means no operands at all; otherwise there is one
            # operand (§ 4.3.1).
            if encoded is OperandType.OMITTED:
                namespace, types = ZERO_OP, ()
            else:
                namespace, types = ONE_OP, (encoded,)
        else:
            # Otherwise, the form is "long" (§ 4.3)
            # In long form the operand count is always 2OP (§ 4.3.2)
            form = "long"
            namespace = TWO_OP
            # The opcode number is given in the bottom 5 bits (§ 4.3.2)
            number = opcode_byte & 0b0001_1111

            # In long form a single bit per operand picks between small
            # constant and variable; large constants force variable form
            # instead (§ 4.4.2).
            types = (
                self._long_form_type(opcode_byte, bit=6),
                self._long_form_type(opcode_byte, bit=5),
            )

        # Formally, it is illegal for a game to contain an opcode not specified for
        # its version (§ 14.2)
        opcode, out_of_version = self._resolve(namespace, number, start)
        operands, address = self._read_operands(address, types)

        store = None
        store_address = None

        if opcode.stores:
            store_address = address
            store = self._memory.read_byte(address)
            address += 1

        branch = None
        branch_address = None

        if opcode.branches:
            branch_address = address
            branch, address = self._read_branch(address)

        text = None

        if opcode.text:
            text, address = self._read_text(address)

        return Instruction(
            address=start,
            next_address=address,
            form=form,
            namespace=namespace,
            number=number,
            opcode=opcode,
            operands=operands,
            store=store,
            branch=branch,
            text=text,
            out_of_version=out_of_version,
            store_address=store_address,
            branch_address=branch_address,
        )

    def _read_operands(
        self, address: int, types: tuple[OperandType, ...]
    ) -> tuple[tuple[Operand, ...], int]:
        """Read the operands that follow the types (§ 4.5).

        A large constant is a 2-byte word; small constants and variable
        numbers are single bytes (§ 4.2.1, § 4.2.2).
        """

        operands = []

        for operand_type in types:
            if operand_type is OperandType.LARGE_CONSTANT:
                value = self._memory.read_word(address)
                address += 2
            else:
                value = self._memory.read_byte(address)
                address += 1

            operands.append(Operand(operand_type, value))

        return tuple(operands), address

    def _read_text(self, address: int) -> tuple[bytes, int]:
        """Measure the inline string that follows `print` (§ 4.8).

        Encoded text runs until a word with the top bit set. The characters
        themselves are § 3's problem; here we only need the extent so that
        the instruction's length is right.
        """
        start = address

        while True:
            word = self._memory.read_word(address)
            address += 2

            if word & 0x8000:
                break

        return self._memory.read_bytes(start, address - start), address

    def _read_branch(self, address: int) -> tuple[Branch, int]:
        """Read 1 or 2 bytes of branch data (§ 4.7)."""

        first = self._memory.read_byte(address)
        address += 1
        on_true = bool(first & 0b1000_0000)

        if first & 0b0100_0000:
            # One byte: an unsigned offset of 0 to 63.
            return Branch(on_true, first & 0b0011_1111), address

        # Two bytes: a signed 14-bit offset, so it can also jump backwards.
        second = self._memory.read_byte(address)
        address += 1
        offset = ((first & 0b0011_1111) << 8) | second

        if offset & 0b0010_0000_0000_0000:
            offset -= 0b0100_0000_0000_0000

        return Branch(on_true, offset), address

    def _resolve(
        self, namespace: str, number: int, address: int
    ) -> tuple[Opcode, bool]:
        """Find the opcode, reporting whether it is early for this Version."""

        opcode = lookup(namespace, number, self._version)

        if opcode is not None:
            return opcode, False

        # § 14.2.1: extended opcodes above the specified range are to be
        # ignored rather than treated as errors. They still decode, because
        # the extended form always carries a type byte, so we can measure
        # them and step over them.
        if namespace == EXT and number >= FIRST_IGNORABLE_EXT:
            return Opcode(f"ext_{number}"), False

        # A known opcode number arriving early is a story file's fault, not a
        # decoding failure; we know its shape, so carry on and flag it.
        early = lookup_ignoring_version(namespace, number)

        if early is not None:
            return early, True

        message = (
            f"${address:05x}: {namespace}:{number} is not an opcode in "
            f"Version {self._version} (§ 14.2)"
        )

        raise IllegalOpcodeError(message)

    def _read_type_bytes(
        self, address: int, number: int, namespace: str
    ) -> tuple[tuple[OperandType, ...], int]:
        """Read the packed operand types of § 4.4.3."""

        types = list(self._unpack_types(self._memory.read_byte(address)))
        address += 1

        if namespace == VAR and number in _DOUBLE_VARIABLE_OPCODES:
            types += self._unpack_types(self._memory.read_byte(address))
            address += 1

        # "Once one type has been given as 'omitted', all subsequent ones
        # must be" (§ 4.4.3), so the operands stop at the first gap.
        kept: list[OperandType] = []

        for operand_type in types:
            if operand_type is OperandType.OMITTED:
                break

            kept.append(operand_type)

        return tuple(kept), address

    def _unpack_types(self, byte: int) -> tuple[OperandType, ...]:
        """Split a byte into 4 2-bit fields, most significant first."""

        return tuple(OperandType((byte >> shift) & 0b11) for shift in (6, 4, 2, 0))

    def _long_form_type(self, opcode_byte: int, *, bit: int) -> OperandType:
        """The operand type held in one bit of a long-form opcode (§ 4.4.2).

        Bit 6 gives the type of the first operand, bit 5 of the second: 0
        means a small constant and 1 a variable.
        """

        if opcode_byte & (1 << bit):
            return OperandType.VARIABLE

        return OperandType.SMALL_CONSTANT
