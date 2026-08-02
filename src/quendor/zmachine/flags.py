"""Decoding the header flag fields (§ 11.1.2, § 11.1.4).

The tables mirror the bit tables in § 11.1.2 and § 11.1.4 of the Standard.
Where the same bit means different things in different Versions, the describe
functions pick the label for the Version at hand.
"""

from typing import Final

from quendor.zmachine.versions import V4, V5, V6

FLAGS_1_WIDTH: Final = 8
FLAGS_2_WIDTH: Final = 16

# § 11.1.4, "Flags 1: Versions 1 to 3". Bit 0 is absent from the Standard;
# the ZIP Specification defines it as the byte-swap flag, never used in
# practice since shipped story files are all big-endian.
_FLAGS_1_LEGACY: Final[dict[int, str]] = {
    0: "byte-swapped story file (ZIP spec; unused in practice)",
    1: "status line shows hours:mins, not score/turns",
    2: "story file split across two discs",
    3: 'the legendary "Tandy" bit',
    4: "status line not available",
    5: "screen-splitting available",
    6: "variable-pitch font is the default",
}

# § 11.1.4, "Flags 1: from Version 4".
_FLAGS_1_MODERN: Final[dict[int, str]] = {
    0: "colors available",
    1: "picture displaying available",
    2: "boldface available",
    3: "italic available",
    4: "fixed-space style available",
    5: "sound effects available",
    7: "timed keyboard input available",
}

# § 11.1.2. Bits 3, 4, 5, 7, and 8 are requests the interpreter clears again
# if it cannot provide the effect.
_FLAGS_2: Final[dict[int, str]] = {
    0: "transcripting is on",
    1: "game forces fixed-pitch printing",
    2: "interpreter requests screen redraw",
    3: "game wants to use pictures",
    4: "game wants to use the UNDO opcodes",
    5: "game wants to use a mouse",
    6: "game wants to use colors",
    7: "game wants to use sound effects",
    8: "game wants to use menus",
    10: "printer error during transcription (uncertain; § 11.1.2)",
}


def describe_flags_1(version: int, value: int) -> tuple[str, ...]:
    """Spec labels for each set bit of Flags 1, lowest bit first (§ 11.1.4)."""
    return _describe(_flags_1_table(version), value, FLAGS_1_WIDTH)


def describe_flags_2(version: int, value: int) -> tuple[str, ...]:
    """Spec labels for each set bit of Flags 2, lowest bit first (§ 11.1.2)."""
    return _describe(_flags_2_table(version), value, FLAGS_2_WIDTH)


def _flags_1_table(version: int) -> dict[int, str]:
    if version < V4:
        return _FLAGS_1_LEGACY

    table = dict(_FLAGS_1_MODERN)

    if version < V6:
        # The same bit only comes to mean picture support in V6 (§ 11.1.4).
        table[1] = "status line type (see § 11 Remarks)"

    return table


def _flags_2_table(version: int) -> dict[int, str]:
    table = dict(_FLAGS_2)

    if version < V5:
        # Before UNDO existed, the only known use of this bit is the Amiga
        # release of The Lurking Horror; even the spec is unsure (§ 11.1.2).
        table[4] = 'sound effects? (V3; seen in the Amiga "The Lurking Horror")'

    return table


def _describe(table: dict[int, str], value: int, width: int) -> tuple[str, ...]:
    return tuple(
        table.get(bit, f"bit {bit} (not in § 11.1)")
        for bit in range(width)
        if value & (1 << bit)
    )
