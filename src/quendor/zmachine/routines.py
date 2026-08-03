"""Routine headers (§ 5).

A routine is not just code. It begins with a header giving how many local
variables it has, and in Versions 1 to 4 the initial values of those locals
as well (§ 5.2). Execution starts at the byte after that header (§ 5.3),
which is why the address in a `call` operand is never the address of an
instruction.
"""

from dataclasses import dataclass
from typing import Final

from quendor.zmachine.errors import StoryFileError
from quendor.zmachine.memory import Memory

"""A routine has between 0 and 15 local variables (§ 5.2)."""
MAXIMUM_LOCALS: Final = 15

"""From V5 locals start at zero rather than from the header (§ 5.2.1)."""
FIRST_VERSION_WITHOUT_INITIAL_VALUES: Final = 5


@dataclass(frozen=True)
class Routine:
    """A routine's header, and where its code begins."""

    """Byte address of the header."""
    address: int

    """Starting values for the locals, in order (§ 5.2.1)."""
    initial_locals: tuple[int, ...]

    """Byte address of the first instruction (§ 5.3)."""
    first_instruction: int


def read_routine(memory: Memory, version: int, address: int) -> Routine:
    """Read the routine header at a byte address (§ 5.2)."""

    count = memory.read_byte(address)

    if count > MAXIMUM_LOCALS:
        message = (
            f"${address:05x}: routine claims {count} local variables; "
            f"a routine may have at most {MAXIMUM_LOCALS} (§ 5.2)"
        )
        raise StoryFileError(message)

    cursor = address + 1

    if version < FIRST_VERSION_WITHOUT_INITIAL_VALUES:
        # V1-4 store two bytes per local giving its initial value (§ 5.2.1).
        values = tuple(memory.read_word(cursor + 2 * index) for index in range(count))
        cursor += 2 * count
    else:
        values = (0,) * count

    return Routine(
        address=address,
        initial_locals=values,
        first_instruction=cursor,
    )
