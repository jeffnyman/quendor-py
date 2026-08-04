"""The game state: the stack, call frames and variables (§ 6).

§ 6.1 defines the "state of play" as dynamic memory, the stack, the program
counter, and the routine call state -- and requires the last three to live
*outside* the Z-machine memory map, in the interpreter's own storage. That is
why this module holds them in Python objects rather than in `Memory`. Global
variables are the exception: they really are in dynamic memory (§ 6.2), so
reading one is a memory access like any other.

The three kinds of variable share a single numbering scheme (§ 4.2.2):

    $00        the stack
    $01 - $0f  local variables of the current routine
    $10 - $ff  global variables

Each routine gets a fresh evaluation stack, because § 6.3.1 and § 6.3.2
require the stack to be empty at the start of a routine and to be emptied
again when it returns. Modelling that as a list per frame makes both rules
structural rather than something to remember.
"""

from dataclasses import dataclass, field
from typing import Final

from quendor.zmachine.errors import ExecutionError, IllegalReturnError, StackError
from quendor.zmachine.numbers import WORD_MASK
from quendor.zmachine.routines import read_routine
from quendor.zmachine.story import Story

STACK_VARIABLE: Final = 0x00
FIRST_LOCAL_VARIABLE: Final = 0x01
FIRST_GLOBAL_VARIABLE: Final = 0x10
LAST_VARIABLE: Final = 0xFF

"""The global table is 240 two-byte words (§ 6.2)."""
GLOBAL_COUNT: Final = 240


@dataclass
class Frame:
    """One entry in the routine call state (§ 6.5)."""

    """Where execution resumes when this routine returns."""
    return_pc: int

    """Variable to receive the return value, or None to discard it.

    The `call_vn` family throws the result away (§ 6.4.1), and so does the
    outermost frame, which never returns at all.
    """
    store_variable: int | None

    local_variables: list[int]

    """How many arguments the call supplied, before any were discarded.

    Counted before truncation, because `check_arg_count` asks what the
    caller passed, not what fitted (§ 15).
    """
    argument_count: int

    evaluation_stack: list[int] = field(default_factory=list)


class GameState:
    """The program counter, the call stack, and variable access."""

    def __init__(self, story: Story) -> None:
        self._story = story
        self.memory = story.memory
        self.header = story.header
        self._version = story.header.version

        self.pc = 0
        self.frames: list[Frame] = []

        self.restart()

    # -- Starting and restarting ---------------------------------------

    def restart(self) -> None:
        """Return to the state the story file began in (§ 6.1.3).

        Dynamic memory is restored, the stack is emptied, and execution
        starts over. 'Flags 2' survives, which `Memory` handles.
        """

        self.memory.restore_dynamic_memory()

        if self.header.has_main_routine:
            # § 5.4: V6 stores the packed address of a "main" routine, so
            # execution begins inside a real routine with real locals.
            address = self.header.unpack_routine_address(
                self.header.initial_program_counter
            )

            routine = read_routine(self.memory, self._version, address)

            self.frames = [
                Frame(
                    return_pc=0,
                    store_variable=None,
                    local_variables=list(routine.initial_locals),
                    argument_count=0,
                )
            ]

            self.pc = routine.first_instruction
        else:
            # § 5.5: elsewhere the header holds a byte address, and the
            # starting environment has no local variables.
            self.frames = [
                Frame(
                    return_pc=0,
                    store_variable=None,
                    local_variables=[],
                    argument_count=0,
                )
            ]

            self.pc = self.header.initial_program_counter

    # -- Calls and returns (§ 6.4) -------------------------------------

    def call_routine(
        self,
        packed_address: int,
        arguments: list[int],
        store_variable: int | None,
    ) -> None:
        """Call a routine, given the *packed* address from the operand.

        The packed form matters: § 6.4.3 makes a call to packed address 0 a
        no-op returning false, and in V6 and V7 unpacking 0 yields the
        routine offset rather than 0, so the test has to happen first.
        """
        if packed_address == 0:
            if store_variable is not None:
                self.write_variable(store_variable, 0)

            return

        address = self.header.unpack_routine_address(packed_address)
        routine = read_routine(self.memory, self._version, address)

        # § 6.4.4: locals take their initial values from the routine header
        # (V1-4) or zero (V5+), and then the arguments are written over them,
        # argument 1 into local 1. § 6.4.4.1 allows a mismatch in either
        # direction; spare arguments are simply dropped.
        local_variables = list(routine.initial_locals)

        for index, value in enumerate(arguments[: len(local_variables)]):
            local_variables[index] = value & WORD_MASK

        self.frames.append(
            Frame(
                return_pc=self.pc,
                store_variable=store_variable,
                local_variables=local_variables,
                argument_count=len(arguments),
            )
        )

        self.pc = routine.first_instruction

    def return_value(self, value: int) -> None:
        """Return from the current routine (§ 6.4.5).

        The stored value lands in the *caller's* frame, so the frame is
        popped first -- storing to the stack must push onto the stack the
        caller will read.
        """

        if len(self.frames) == 1:
            message = "returned from the outermost routine (§ 5.4, § 5.5)"
            raise IllegalReturnError(message)

        frame = self.frames.pop()
        self.pc = frame.return_pc

        if frame.store_variable is not None:
            self.write_variable(frame.store_variable, value)

    # -- Frames --------------------------------------------------------

    @property
    def frame(self) -> Frame:
        """The routine currently executing."""
        return self.frames[-1]

    # -- The stack (§ 6.3) ---------------------------------------------

    def push(self, value: int) -> None:
        """Push a word onto the current routine's evaluation stack (§ 6.3)."""
        self.frame.evaluation_stack.append(value & WORD_MASK)

    def pop(self) -> int:
        """Pull the top word off the evaluation stack (§ 6.3).

        Underflow is a fault: the stack belongs to the current routine
        alone, so nothing can be pulled that this routine did not push
        (§ 6.3.1, § 6.3.2).
        """

        if not self.frame.evaluation_stack:
            message = "pulled from an empty stack (§ 6.3.1)"
            raise StackError(message)

        return self.frame.evaluation_stack.pop()

    def peek(self) -> int:
        """Read the top of the stack without removing it (§ 6.3.4)."""

        if not self.frame.evaluation_stack:
            message = "read the top of an empty stack (§ 6.3.1)"
            raise StackError(message)

        return self.frame.evaluation_stack[-1]

    def replace_top(self, value: int) -> None:
        """Overwrite the top of the stack in place (§ 6.3.4)."""

        if not self.frame.evaluation_stack:
            message = "wrote to the top of an empty stack (§ 6.3.1)"
            raise StackError(message)

        self.frame.evaluation_stack[-1] = value & WORD_MASK

    # -- Variables (§ 4.2.2, § 6.2) ------------------------------------

    def read_variable(self, number: int, *, indirect: bool = False) -> int:
        """Read a variable by number.

        `indirect` marks the seven opcodes that name a variable rather than
        taking its value -- inc, dec, inc_chk, dec_chk, load, store, pull.
        For those, referring to the stack reads the top item in place instead
        of pulling it (§ 6.3.4).
        """

        self._check_variable(number)

        if number == STACK_VARIABLE:
            return self.peek() if indirect else self.pop()

        if number < FIRST_GLOBAL_VARIABLE:
            return self.read_local(number - FIRST_LOCAL_VARIABLE)

        return self.read_global(number - FIRST_GLOBAL_VARIABLE)

    def write_variable(
        self, number: int, value: int, *, indirect: bool = False
    ) -> None:
        """Write a variable by number, with the § 6.3.4 rule."""

        self._check_variable(number)

        if number == STACK_VARIABLE:
            if indirect:
                self.replace_top(value)
            else:
                self.push(value)
            return

        if number < FIRST_GLOBAL_VARIABLE:
            self.write_local(number - FIRST_LOCAL_VARIABLE, value)
            return

        self.write_global(number - FIRST_GLOBAL_VARIABLE, value)

    def read_local(self, index: int) -> int:
        """The current routine's local, by zero-based index.

        Index 0 is variable $01; callers subtract FIRST_LOCAL_VARIABLE
        before arriving here (§ 4.2.2).
        """
        self._check_local(index)
        return self.frame.local_variables[index]

    def read_global(self, index: int) -> int:
        """A global by zero-based index, read from dynamic memory (§ 6.2)."""
        return self.memory.read_word(self._global_address(index))

    def write_local(self, index: int, value: int) -> None:
        """Set the current routine's local, by zero-based index."""
        self._check_local(index)
        self.frame.local_variables[index] = value & WORD_MASK

    def write_global(self, index: int, value: int) -> None:
        """Set a global by zero-based index, writing dynamic memory (§ 6.2)."""
        self.memory.write_word(self._global_address(index), value & WORD_MASK)

    def _check_variable(self, number: int) -> None:
        """A variable number is a single byte, $00 to $ff (§ 4.2.2)."""
        if not STACK_VARIABLE <= number <= LAST_VARIABLE:
            message = f"${number:x} is not a variable number (§ 4.2.2)"
            raise ExecutionError(message)

    def _check_local(self, index: int) -> None:
        """The current routine must actually have this local.

        § 4.2.2: "It is illegal to refer to local variables which do not
        exist for the current routine (there may even be none)."
        """

        if not 0 <= index < len(self.frame.local_variables):
            message = (
                f"local variable {index + 1} does not exist; the current "
                f"routine has {len(self.frame.local_variables)} (§ 4.2.2)"
            )
            raise ExecutionError(message)

    def _global_address(self, index: int) -> int:
        """Byte address of a global in the § 6.2 table, if it exists."""

        if not 0 <= index < GLOBAL_COUNT:
            message = (
                f"global variable {index} does not exist; "
                f"the table holds {GLOBAL_COUNT} words (§ 6.2)"
            )
            raise ExecutionError(message)
        return self.header.global_variables_address + 2 * index
