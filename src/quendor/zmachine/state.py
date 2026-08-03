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

from dataclasses import dataclass

from quendor.zmachine.routines import read_routine
from quendor.zmachine.story import Story


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
