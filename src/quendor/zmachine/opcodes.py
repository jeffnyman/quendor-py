"""The opcode table of § 14.

An instruction cannot be decoded from its bytes alone. Whether a store byte
or a branch offset follows the operands depends on *which* opcode it is, and
for a handful of opcodes that answer changes with the Version. `save` is the
clearest example: in V1-3 it branches, in V4 it stores a result instead, and
in V5 it disappears entirely in favour of EXT:0 (§ 14). Decoding a V3 file
with V5 rules would therefore consume the wrong number of bytes and desertify
everything after it.

That is why this table exists and why entries are keyed by Version.

Reading the "V" column of § 14: an empty column means the opcode has existed
since Version 1. A single number means it exists from that Version onward.
A pair like "5/3" means the opcode belongs to the Version 5 specification but
is known to appear in a Version 3 story file -- `sound_effect` is the famous
case, used by 'The Lurking Horror' -- so only the first number describes the
rules, and the second is a historical note. Opcodes that become illegal again
are marked `[illegal]` there, and `None` here.
"""

from dataclasses import dataclass
from typing import Final

"""Opcode byte 190 introduces an extended opcode, from V5 (§ 4.3)."""
EXTENDED_ESCAPE: Final = 0xBE

"""EXT:30 to EXT:255 must be ignored rather than rejected (§ 14.2.1)."""
FIRST_IGNORABLE_EXT: Final = 30

# Namespaces. These are the operand counts of § 4.3, except EXT, which is a
# separate opcode space reached through the $BE escape byte (§ 4.3.4).
TWO_OP: Final = "2OP"
ONE_OP: Final = "1OP"
ZERO_OP: Final = "0OP"
VAR: Final = "VAR"
EXT: Final = "EXT"

# Each entry maps an opcode number to the Versions at which its meaning
# changes, newest first, as (since_version, opcode). `None` means the opcode
# is illegal from that Version onward.
type _Variants = tuple[tuple[int, Opcode | None], ...]


@dataclass(frozen=True)
class Opcode:
    """What an opcode's encoding looks like, beyond its operands."""

    name: str
    stores: bool = False
    branches: bool = False
    text: bool = False


def _op(name: str, *, st: bool = False, br: bool = False, text: bool = False) -> Opcode:
    return Opcode(name, stores=st, branches=br, text=text)


_TWO_OP: Final[dict[int, _Variants]] = {
    0x01: ((1, _op("je", br=True)),),
    0x02: ((1, _op("jl", br=True)),),
    0x03: ((1, _op("jg", br=True)),),
    0x04: ((1, _op("dec_chk", br=True)),),
    0x05: ((1, _op("inc_chk", br=True)),),
    0x06: ((1, _op("jin", br=True)),),
    0x07: ((1, _op("test", br=True)),),
    0x08: ((1, _op("or", st=True)),),
    0x09: ((1, _op("and", st=True)),),
    0x0A: ((1, _op("test_attr", br=True)),),
    0x0B: ((1, _op("set_attr")),),
    0x0C: ((1, _op("clear_attr")),),
    0x0D: ((1, _op("store")),),
    0x0E: ((1, _op("insert_obj")),),
    0x0F: ((1, _op("loadw", st=True)),),
    0x10: ((1, _op("loadb", st=True)),),
    0x11: ((1, _op("get_prop", st=True)),),
    0x12: ((1, _op("get_prop_addr", st=True)),),
    0x13: ((1, _op("get_next_prop", st=True)),),
    0x14: ((1, _op("add", st=True)),),
    0x15: ((1, _op("sub", st=True)),),
    0x16: ((1, _op("mul", st=True)),),
    0x17: ((1, _op("div", st=True)),),
    0x18: ((1, _op("mod", st=True)),),
    0x19: ((4, _op("call_2s", st=True)),),
    0x1A: ((5, _op("call_2n")),),
    0x1B: ((5, _op("set_colour")),),
    0x1C: ((5, _op("throw")),),
}

_ONE_OP: Final[dict[int, _Variants]] = {
    0x00: ((1, _op("jz", br=True)),),
    0x01: ((1, _op("get_sibling", st=True, br=True)),),
    0x02: ((1, _op("get_child", st=True, br=True)),),
    0x03: ((1, _op("get_parent", st=True)),),
    0x04: ((1, _op("get_prop_len", st=True)),),
    0x05: ((1, _op("inc")),),
    0x06: ((1, _op("dec")),),
    0x07: ((1, _op("print_addr")),),
    0x08: ((4, _op("call_1s", st=True)),),
    0x09: ((1, _op("remove_obj")),),
    0x0A: ((1, _op("print_obj")),),
    0x0B: ((1, _op("ret")),),
    # `jump` takes a signed offset as a normal operand; it is not a branch
    # instruction in the § 4.7 sense and carries no branch data.
    0x0C: ((1, _op("jump")),),
    0x0D: ((1, _op("print_paddr")),),
    0x0E: ((1, _op("load", st=True)),),
    # The store byte vanishes here in V5: same opcode number, different
    # instruction, one byte shorter.
    0x0F: ((5, _op("call_1n")), (1, _op("not", st=True))),
}

_ZERO_OP: Final[dict[int, _Variants]] = {
    0x00: ((1, _op("rtrue")),),
    0x01: ((1, _op("rfalse")),),
    0x02: ((1, _op("print", text=True)),),
    0x03: ((1, _op("print_ret", text=True)),),
    0x04: ((1, _op("nop")),),
    # save and restore change shape twice: branch, then store, then gone.
    0x05: ((5, None), (4, _op("save", st=True)), (1, _op("save", br=True))),
    0x06: ((5, None), (4, _op("restore", st=True)), (1, _op("restore", br=True))),
    0x07: ((1, _op("restart")),),
    0x08: ((1, _op("ret_popped")),),
    0x09: ((5, _op("catch", st=True)), (1, _op("pop"))),
    0x0A: ((1, _op("quit")),),
    0x0B: ((1, _op("new_line")),),
    0x0C: ((4, None), (3, _op("show_status"))),
    0x0D: ((3, _op("verify", br=True)),),
    # $BE is the extended-form escape from V5 and is intercepted before any
    # table lookup happens (§ 4.3). Below V5 it is simply not an opcode.
    0x0E: ((1, None),),
    0x0F: ((5, _op("piracy", br=True)),),
}

_VAR: Final[dict[int, _Variants]] = {
    0x00: ((4, _op("call_vs", st=True)), (1, _op("call", st=True))),
    0x01: ((1, _op("storew")),),
    0x02: ((1, _op("storeb")),),
    0x03: ((1, _op("put_prop")),),
    0x04: ((5, _op("aread", st=True)), (1, _op("sread"))),
    0x05: ((1, _op("print_char")),),
    0x06: ((1, _op("print_num")),),
    0x07: ((1, _op("random", st=True)),),
    0x08: ((1, _op("push")),),
    0x09: ((6, _op("pull", st=True)), (1, _op("pull"))),
    0x0A: ((3, _op("split_window")),),
    0x0B: ((3, _op("set_window")),),
    0x0C: ((4, _op("call_vs2", st=True)),),
    0x0D: ((4, _op("erase_window")),),
    0x0E: ((4, _op("erase_line")),),
    0x0F: ((4, _op("set_cursor")),),
    0x10: ((4, _op("get_cursor")),),
    0x11: ((4, _op("set_text_style")),),
    0x12: ((4, _op("buffer_mode")),),
    0x13: ((3, _op("output_stream")),),
    0x14: ((3, _op("input_stream")),),
    # Specified for V5, but 'The Lurking Horror' uses it in V3 (§ 14), and
    # that story file is in our corpus, so V3 must accept it.
    0x15: ((3, _op("sound_effect")),),
    0x16: ((4, _op("read_char", st=True)),),
    0x17: ((4, _op("scan_table", st=True, br=True)),),
    0x18: ((5, _op("not", st=True)),),
    0x19: ((5, _op("call_vn")),),
    0x1A: ((5, _op("call_vn2")),),
    0x1B: ((5, _op("tokenise")),),
    0x1C: ((5, _op("encode_text")),),
    0x1D: ((5, _op("copy_table")),),
    0x1E: ((5, _op("print_table")),),
    0x1F: ((5, _op("check_arg_count", br=True)),),
}

_EXT: Final[dict[int, _Variants]] = {
    0x00: ((5, _op("save", st=True)),),
    0x01: ((5, _op("restore", st=True)),),
    0x02: ((5, _op("log_shift", st=True)),),
    0x03: ((5, _op("art_shift", st=True)),),
    0x04: ((5, _op("set_font", st=True)),),
    0x05: ((6, _op("draw_picture")),),
    0x06: ((6, _op("picture_data", br=True)),),
    0x07: ((6, _op("erase_picture")),),
    0x08: ((6, _op("set_margins")),),
    0x09: ((5, _op("save_undo", st=True)),),
    0x0A: ((5, _op("restore_undo", st=True)),),
    0x0B: ((5, _op("print_unicode")),),
    0x0C: ((5, _op("check_unicode", st=True)),),
    0x0D: ((5, _op("set_true_colour")),),
    0x10: ((6, _op("move_window")),),
    0x11: ((6, _op("window_size")),),
    0x12: ((6, _op("window_style")),),
    0x13: ((6, _op("get_wind_prop", st=True)),),
    0x14: ((6, _op("scroll_window")),),
    0x15: ((6, _op("pop_stack")),),
    0x16: ((6, _op("read_mouse")),),
    0x17: ((6, _op("mouse_window")),),
    0x18: ((6, _op("push_stack", br=True)),),
    0x19: ((6, _op("put_wind_prop")),),
    0x1A: ((6, _op("print_form")),),
    0x1B: ((6, _op("make_menu", br=True)),),
    0x1C: ((6, _op("picture_table")),),
    0x1D: ((6, _op("buffer_screen", st=True)),),
}

_TABLE: Final[dict[str, dict[int, _Variants]]] = {
    TWO_OP: _TWO_OP,
    ONE_OP: _ONE_OP,
    ZERO_OP: _ZERO_OP,
    VAR: _VAR,
    EXT: _EXT,
}


def lookup(namespace: str, number: int, version: int) -> Opcode | None:
    """Find the opcode for a number in a namespace under a Version's rules.

    Returns None when no such opcode exists for that Version, which § 14.2
    makes an error the interpreter should halt on.
    """

    variants = _TABLE[namespace].get(number)

    if variants is None:
        return None

    effective = _rules_version(version)

    for since, opcode in variants:
        if effective >= since:
            return opcode

    return None


def lookup_ignoring_version(namespace: str, number: int) -> Opcode | None:
    """The earliest definition of an opcode number, whatever Version it needs.

    Some real story files use opcodes their Version does not permit. Inform
    compiled 'destruct' to Version 1 with a `verify` action routine, and
    `verify` is 0OP:189, specified only from Version 3 (§ 14). § 14.2 says an
    interpreter "should normally halt" on such an opcode, and "normally"
    is doing real work in that sentence.

    Quendor's compromise: an *unrecognised* opcode number still halts, since
    that is the signal that decoding has lost its place in the instruction
    stream and everything after it is noise. An opcode that is merely early
    for its Version is decoded anyway -- its shape is known -- and flagged on
    the instruction so that callers can report it.
    """

    variants = _TABLE[namespace].get(number)

    if variants is None:
        return None

    # Oldest first: the definition the story file most likely intends.
    for _since, opcode in reversed(variants):
        if opcode is not None:
            return opcode

    return None


def _rules_version(version: int) -> int:
    """The Version whose opcode rules apply to a story file.

    § 1.2.4: "Throughout the specification, Versions 7 and 8 are identical to
    Version 5" apart from the maximum file length, the packed address
    formula, and the file length constant -- none of which are opcode rules.

    This matters more than it looks. `pull` gains a store byte in Version 6
    (VAR:233), so treating "since Version 6" as "Version 6 and later" makes
    every V8 `pull` one byte too long and desynchronizes the rest of the
    routine. V6 additions apply to V6 alone.
    """

    if version in (7, 8):
        return 5

    return version
