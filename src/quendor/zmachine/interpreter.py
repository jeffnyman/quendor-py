"""The execution loop and opcode semantics (§ 15)."""

from quendor.zmachine.dictionary import Dictionary, tokenize
from quendor.zmachine.errors import (
    EndOfInputError,
    ExecutionError,
    UnimplementedOpcodeError,
)
from quendor.zmachine.input import Keyboard
from quendor.zmachine.instructions import Decoder, Instruction, OperandType
from quendor.zmachine.numbers import BYTE_MASK, to_signed, to_unsigned
from quendor.zmachine.objects import ObjectTable
from quendor.zmachine.output import Screen
from quendor.zmachine.screen import ScreenModel
from quendor.zmachine.state import GameState
from quendor.zmachine.story import Story
from quendor.zmachine.streams import OutputStreams
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V6


class Interpreter:
    """Runs a story file."""

    def __init__(self, story: Story, screen: Screen, keyboard: Keyboard) -> None:
        self.story = story
        self.screen = screen
        self.keyboard = keyboard

        self._version = story.header.version
        self.decoder = Decoder(story.memory, story.header.version)
        self.text = TextCodec(story.memory, story.header)
        self.dictionary = Dictionary(story.memory, story.header, self.text)
        self.display = ScreenModel(story.memory, story.header, screen)
        self.objects = ObjectTable(story.memory, story.header)
        self.state = GameState(story)

        self.streams = OutputStreams(
            story.memory, story.header, self.display, self.text
        )

        self.instruction_count = 0
        self.running = True

    def run(self) -> None:
        """Execute until the story quits."""

        while self.running:
            self.step()

    def step(self) -> None:
        """Decode and execute one instruction."""

        instruction = self.decoder.decode(self.state.pc)

        # Advance before executing: § 4.7.2 measures branch offsets from the
        # address after the instruction, and a call records this as its
        # return address.
        self.state.pc = instruction.next_address
        self.instruction_count += 1

        handler_name = f"_op_{instruction.name}"
        handler = getattr(self, handler_name, None)

        if handler is None:
            message = (
                f"${instruction.address:05x}: {instruction.name} "
                f"({instruction.namespace}:{instruction.number}) "
                f"is not implemented yet; define `Interpreter.{handler_name}`"
            )

            raise UnimplementedOpcodeError(message)

        handler(instruction)

    # -- Routine calls (§ 6.4) -----------------------------------------

    def _op_call(self, instruction: Instruction) -> None:
        self._call(instruction, store=True)

    def _op_rtrue(self, _instruction: Instruction) -> None:
        self.state.return_value(1)

    def _op_rfalse(self, _instruction: Instruction) -> None:
        self.state.return_value(0)

    def _op_ret_popped(self, _instruction: Instruction) -> None:
        self.state.return_value(self.state.pop())

    # V4 renamed VAR:224 to call_vs; the semantics did not change (§ 14).
    _op_call_vs = _op_call

    def _op_ret(self, instruction: Instruction) -> None:
        self.state.return_value(self._values(instruction)[0])

    # -- Objects (§ 12) ------------------------------------------------

    def _op_put_prop(self, instruction: Instruction) -> None:
        number, property_number, value = self._values(instruction)
        self.objects.put_property(number, property_number, value)

    def _op_test_attr(self, instruction: Instruction) -> None:
        number, attribute = self._values(instruction)
        self._branch(instruction, self.objects.test_attribute(number, attribute))

    def _op_insert_obj(self, instruction: Instruction) -> None:
        number, destination = self._values(instruction)
        self.objects.insert(number, destination)

    def _op_set_attr(self, instruction: Instruction) -> None:
        number, attribute = self._values(instruction)
        self.objects.set_attribute(number, attribute)

    def _op_clear_attr(self, instruction: Instruction) -> None:
        number, attribute = self._values(instruction)
        self.objects.clear_attribute(number, attribute)

    def _op_get_parent(self, instruction: Instruction) -> None:
        """§ 15: unlike its siblings, get_parent does not branch."""
        self._store(instruction, self.objects.parent(self._values(instruction)[0]))

    def _op_get_prop(self, instruction: Instruction) -> None:
        number, property_number = self._values(instruction)
        self._store(instruction, self.objects.get_property(number, property_number))

    def _op_get_prop_addr(self, instruction: Instruction) -> None:
        """§ 15: the property data's byte address, or 0 when absent."""
        number, property_number = self._values(instruction)
        entry = self.objects.find_property(number, property_number)
        self._store(instruction, entry.data_address if entry is not None else 0)

    def _op_get_prop_len(self, instruction: Instruction) -> None:
        address = self._values(instruction)[0]
        self._store(instruction, self.objects.property_length_at(address))

    def _op_get_child(self, instruction: Instruction) -> None:
        value = self.objects.child(self._values(instruction)[0])
        self._store(instruction, value)
        self._branch(instruction, value != 0)

    def _op_get_sibling(self, instruction: Instruction) -> None:
        """§ 15: store the next object in the tree, branching if it exists."""
        value = self.objects.sibling(self._values(instruction)[0])
        self._store(instruction, value)
        self._branch(instruction, value != 0)

    # -- Variables -----------------------------------------------------
    #
    # The first operand of these names a variable rather than supplying a
    # value, so the resolved operand is a variable *number* and the access
    # is indirect: naming the stack reads or writes its top item in place
    # rather than pushing or pulling (§ 4.2.3, § 6.3.4).

    def _op_inc(self, instruction: Instruction) -> None:
        self._adjust(self._values(instruction)[0], 1)

    def _op_dec(self, instruction: Instruction) -> None:
        self._adjust(self._values(instruction)[0], -1)

    def _op_store(self, instruction: Instruction) -> None:
        number, value = self._values(instruction)
        self.state.write_variable(number, value, indirect=True)

    def _op_inc_chk(self, instruction: Instruction) -> None:
        """§ 15: increment, then branch if now greater than value."""
        number, limit = self._values(instruction)
        self._branch(instruction, self._adjust(number, 1) > to_signed(limit))

    def _op_dec_chk(self, instruction: Instruction) -> None:
        """§ 15: decrement, then branch if now less than value."""
        number, limit = self._values(instruction)
        self._branch(instruction, self._adjust(number, -1) < to_signed(limit))

    def _op_push(self, instruction: Instruction) -> None:
        self.state.push(self._values(instruction)[0])

    def _op_pull(self, instruction: Instruction) -> None:
        """§ 15: pull a value off a stack.

        Version 6 is a different instruction wearing the same name: it takes
        a user stack rather than a variable, and *stores* the result. With no
        operand, or a zero one, it pulls from the game stack instead.
        """

        values = self._values(instruction)

        if self._version != V6:
            self.state.write_variable(values[0], self.state.pop(), indirect=True)
            return

        table = values[0] if values else 0

        if table == 0:
            self._store(instruction, self.state.pop())
            return

        # § 6.6: the first word counts spare slots, so a pull frees one and
        # reads the value that was stored just above the new count.
        memory = self.state.memory
        spare = memory.read_word(table) + 1
        self._store(instruction, memory.read_word(table + 2 * spare))
        memory.write_word(table, spare)

    # -- Arithmetic (§ 2.2.1: signed) ----------------------------------

    def _op_add(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a + b))

    def _op_sub(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a - b))

    def _op_mul(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a * b))

    def _op_div(self, instruction: Instruction) -> None:
        """§ 15: signed division, truncating toward zero (see `numbers`)."""
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(self._divide(a, b)))

    def _op_mod(self, instruction: Instruction) -> None:
        """§ 15: the remainder of the truncating division."""
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a - b * self._divide(a, b)))

    def _divide(self, a: int, b: int) -> int:
        """Divide truncating toward zero, which Python's `//` does not.

        The Z-machine rounds toward zero; `//` rounds toward minus infinity
        (the trap recorded in `numbers`). § 15 makes division by zero a
        fault to halt on.
        """

        if b == 0:
            message = "division by zero (§ 15)"
            raise ExecutionError(message)

        quotient = abs(a) // abs(b)

        return -quotient if (a < 0) != (b < 0) else quotient

    # -- Bitwise (§ 2.2.1: unsigned) -----------------------------------

    def _op_and(self, instruction: Instruction) -> None:
        a, b = self._values(instruction)
        self._store(instruction, a & b)

    def _op_test(self, instruction: Instruction) -> None:
        """§ 15: branch when every bit of `flags` is set in `bitmap`."""
        bitmap, flags = self._values(instruction)
        self._branch(instruction, bitmap & flags == flags)

    # -- Control flow --------------------------------------------------

    def _op_je(self, instruction: Instruction) -> None:
        """§ 15: jump if the first operand equals any of the others."""
        values = self._values(instruction)
        self._branch(instruction, any(values[0] == other for other in values[1:]))

    def _op_jz(self, instruction: Instruction) -> None:
        self._branch(instruction, self._values(instruction)[0] == 0)

    def _op_jump(self, instruction: Instruction) -> None:
        """§ 15: not a branch; the operand is a signed offset."""
        offset = to_signed(self._values(instruction)[0])
        self.state.pc = instruction.next_address + offset - 2

    def _op_jin(self, instruction: Instruction) -> None:
        """§ 15: branch if the first object's parent is the second."""
        child, parent = self._values(instruction)
        self._branch(instruction, self.objects.parent(child) == parent)

    def _op_jl(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._branch(instruction, a < b)

    def _op_jg(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._branch(instruction, a > b)

    # -- Arrays --------------------------------------------------------
    #
    # Indices are signed (§ 2.2.1 makes arithmetic signed, and Viola reads
    # them that way), so a table can be addressed backwards from its base.

    def _op_storew(self, instruction: Instruction) -> None:
        array, index, value = self._values(instruction)
        self.state.memory.write_word(array + 2 * to_signed(index), to_unsigned(value))

    def _op_loadw(self, instruction: Instruction) -> None:
        array, index = self._values(instruction)
        self._store(
            instruction, self.state.memory.read_word(array + 2 * to_signed(index))
        )

    def _op_storeb(self, instruction: Instruction) -> None:
        array, index, value = self._values(instruction)
        self.state.memory.write_byte(array + to_signed(index), value & BYTE_MASK)

    def _op_loadb(self, instruction: Instruction) -> None:
        array, index = self._values(instruction)
        self._store(instruction, self.state.memory.read_byte(array + to_signed(index)))

    # -- Input (§ 13, § 15) --------------------------------------------

    def _op_sread(self, instruction: Instruction) -> None:
        """Read a command from the keyboard (§ 15, `read`).

        § 15 also asks V1-3 to redisplay the status line first; that arrives
        with the status line's own branch.
        """

        values = self._values(instruction)
        text_buffer = values[0]
        parse_buffer = values[1] if len(values) > 1 else 0

        try:
            typed = self._read_line(text_buffer)
        except EndOfInputError:
            # The player closed the session. Stop rather than reporting a
            # fault: there is nothing wrong, there is just nobody there.
            self.running = False
            return

        if parse_buffer:
            self._parse(typed, parse_buffer)

    # -- Printing ------------------------------------------------------

    def _op_print_paddr(self, instruction: Instruction) -> None:
        """The operand is a packed *string* address (§ 1.2.3)."""
        packed = self._values(instruction)[0]
        address = self.state.header.unpack_string_address(packed)
        self.streams.write(self.text.decode(address))

    def _op_print(self, instruction: Instruction) -> None:
        """§ 4.8: the text follows the opcode inline."""
        if instruction.text is not None:
            self.streams.write(self.text.decode_bytes(instruction.text))

    def _op_new_line(self, _instruction: Instruction) -> None:
        self.streams.write("\n")

    def _op_print_ret(self, instruction: Instruction) -> None:
        """§ 15: print the inline text, then a new-line, then return true."""
        self._op_print(instruction)
        self.streams.write("\n")
        self.state.return_value(1)

    def _op_print_num(self, instruction: Instruction) -> None:
        """§ 2.2.1: printing numbers is signed."""
        self.streams.write(str(to_signed(self._values(instruction)[0])))

    def _op_print_char(self, instruction: Instruction) -> None:
        """§ 15: the operand is a ZSCII code (§ 3.8)."""
        self.streams.write(self.text.zscii_to_text([self._values(instruction)[0]]))

    def _op_print_obj(self, instruction: Instruction) -> None:
        """§ 15: the short name from the object's property table, not a property."""
        number = self._values(instruction)[0]
        self.streams.write(self.text.decode(self.objects.short_name_address(number)))

    # -- Miscellaneous -------------------------------------------------

    def _op_quit(self, _instruction: Instruction) -> None:
        self.running = False

    # -- Helpers -------------------------------------------------------

    def _read_line(self, text_buffer: int) -> str:
        """Fill the text buffer from the keyboard, returning what was typed.

        § 15, read: byte 0 holds the maximum letters plus one for the zero
        terminator; the text is reduced to lower case and stored from byte 1,
        zero-terminated, with no carriage return code.
        """

        memory = self.state.memory
        maximum = memory.read_byte(text_buffer) - 1
        typed = self.keyboard.read_line(maximum).lower()

        for index, character in enumerate(typed):
            memory.write_byte(text_buffer + 1 + index, self.text.zscii_for(character))

        memory.write_byte(text_buffer + 1 + len(typed), 0)

        return typed

    def _parse(self, typed: str, parse_buffer: int) -> None:
        """Write the § 15 parse blocks: entry address, letters, position.

        Byte 0 holds the most words the buffer can take; the count goes in
        byte 1 and each word gets a 4-byte block. Position counts from
        byte 1 of the text buffer, where the typed text begins.
        """

        memory = self.state.memory
        maximum = memory.read_byte(parse_buffer)
        tokens = tokenize(typed, self.dictionary.separators)[:maximum]

        memory.write_byte(parse_buffer + 1, len(tokens))

        for index, (word, position) in enumerate(tokens):
            block = parse_buffer + 2 + 4 * index

            memory.write_word(block, self.dictionary.lookup(word))
            memory.write_byte(block + 2, len(word))
            memory.write_byte(block + 3, position + 1)

    def _adjust(self, number: int, delta: int) -> int:
        """Add `delta` to a variable in place, signed (§ 15, inc and kin).

        The variable is *named* rather than read, so the access is indirect
        (§ 6.3.4). Returns the new signed value, which is what the `_chk`
        variants compare against their limit.
        """
        value = to_signed(self.state.read_variable(number, indirect=True)) + delta
        self.state.write_variable(number, to_unsigned(value), indirect=True)
        return value

    def _values(self, instruction: Instruction) -> list[int]:
        """Resolve operands to values, first to last.

        The order is part of the specification, not an implementation
        detail: reading a variable operand that names the stack pops it, so
        `@sub sp sp` subtracts the second-from-top from the top (§ 4.5.2).
        """

        return [
            self.state.read_variable(operand.value)
            if operand.type is OperandType.VARIABLE
            else operand.value
            for operand in instruction.operands
        ]

    def _call(
        self, instruction: Instruction, *, store: bool, values: list[int] | None = None
    ) -> None:
        """Shared body of the call family (§ 6.4)."""

        resolved = self._values(instruction) if values is None else values

        if not resolved:
            # A `call` with no operands names no routine. § 4.5 lets a VAR
            # instruction carry none, so this is decodable but meaningless;
            # `crashme.z5` assembles one deliberately.
            message = (
                f"${instruction.address:05x}: {instruction.name} "
                f"has no routine to call (§ 15)"
            )
            raise ExecutionError(message)

        packed, arguments = resolved[0], resolved[1:]

        self.state.call_routine(
            packed,
            arguments,
            instruction.store if store else None,
        )

    def _store(self, instruction: Instruction, value: int) -> None:
        if instruction.store is not None:
            self.state.write_variable(instruction.store, value)

    def _branch(self, instruction: Instruction, condition: bool) -> None:
        """Take or ignore a branch (§ 4.7)."""

        branch = instruction.branch

        if branch is None or condition is not branch.on_true:
            return

        if branch.is_return:
            self.state.return_value(1 if branch.returns_true else 0)
            return

        # The same arithmetic as `branch_target` (§ 4.7.2); that property is
        # None exactly when the branch returns instead, handled above.
        self.state.pc = instruction.next_address + branch.offset - 2
