"""The execution loop and opcode semantics (§ 15)."""

from quendor.zmachine.errors import ExecutionError, UnimplementedOpcodeError
from quendor.zmachine.instructions import Decoder, Instruction, OperandType
from quendor.zmachine.numbers import to_signed, to_unsigned
from quendor.zmachine.state import GameState
from quendor.zmachine.story import Story


class Interpreter:
    """Runs a story file."""

    def __init__(self, story: Story) -> None:
        self.story = story

        self.decoder = Decoder(story.memory, story.header.version)
        self.state = GameState(story)

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

    def _op_ret(self, instruction: Instruction) -> None:
        self.state.return_value(self._values(instruction)[0])

    # -- Arithmetic (§ 2.2.1: signed) ----------------------------------

    def _op_add(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a + b))

    def _op_sub(self, instruction: Instruction) -> None:
        a, b = (to_signed(value) for value in self._values(instruction))
        self._store(instruction, to_unsigned(a - b))

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

    # -- Helpers -------------------------------------------------------

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
