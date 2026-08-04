"""Numbers and arithmetic (§ 2).

Z-machine values are 2-byte words holding $0000 to $ffff, but most arithmetic
treats them as signed, with -n stored as 65536-n (§ 2.1, § 2.2). Comparison,
multiplication, addition, subtraction, division, remainder and printing are
all signed; bitwise operations are not (§ 2.2.1). So values arrive from memory
unsigned, get interpreted as signed for the operation, and go back unsigned.

The rounding rule for division is not in the Standard. § 15 says only "signed
16-bit division", and § 2 does not elaborate. The Z-machine rounds toward
zero, which Python's `//` does not -- it rounds toward minus infinity, so
`-11 // 2` is -6 where the Z-machine wants -5. Viola carries this knowledge
with a comment noting it is the oldest surviving code in the project; it is
the sort of thing that is obvious only once something has told you.
"""

from typing import Final

"""$ffff in its masking role: truncate a result back into a word."""
WORD_MASK: Final = 0xFFFF

"""The same value in its bounding role: the largest storable word (§ 2.1)."""
MAXIMUM_WORD: Final = WORD_MASK

WORD_SIZE: Final = 0x10000
SIGN_BIT: Final = 0x8000


def to_signed(value: int) -> int:
    """Interpret an unsigned word as signed (§ 2.2)."""
    value &= WORD_MASK
    return value - WORD_SIZE if value & SIGN_BIT else value


def to_unsigned(value: int) -> int:
    """Store a number as an unsigned word (§ 2.2).

    Out-of-range results are reduced modulo $10000, which § 2.3.2 records as
    the author's suggestion rather than a requirement -- nothing else is
    specified, and every interpreter does this.
    """
    return value & WORD_MASK
