"""Where printed text goes: the frontend boundary."""


class Screen:
    """A display a Z-machine can print on."""

    def write(self, text: str) -> None:
        """Show text at the current cursor, wrapping and scrolling as needed."""
        ...
