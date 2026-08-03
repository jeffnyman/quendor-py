"""The execution loop and opcode semantics (§ 15)."""

from quendor.zmachine.errors import UnimplementedOpcodeError
from quendor.zmachine.instructions import Decoder
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

        handler = getattr(self, f"_op_{instruction.name}", None)

        if handler is None:
            message = (
                f"${instruction.address:05x}: {instruction.name} "
                f"({instruction.namespace}:{instruction.number}) "
                f"is not implemented yet"
            )

            raise UnimplementedOpcodeError(message)

        handler(instruction)
