from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import ExecutionError, UnimplementedOpcodeError
from quendor.zmachine.input import Keyboard, ScriptedKeyboard
from quendor.zmachine.instructions import Instruction
from quendor.zmachine.interpreter import Interpreter
from quendor.zmachine.output import Screen
from quendor.zmachine.story import Story
from quendor.zmachine.text import TextCodec
from quendor.zmachine.versions import V3, V6

PROGRAM = 0x0500
ROUTINE = 0x0300


class RecordingScreen(Screen):
    def __init__(self) -> None:
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)


OBJECTS_AT = 0x0080
PROPS_AT = 0x0100


def object_patches() -> dict[int, bytes]:
    """The tiny world of test_objects: 1 contains 2 then 3; see there."""

    def entry(attrs: bytes, parent: int, sibling: int, child: int, props: int) -> bytes:
        return attrs + bytes([parent, sibling, child]) + props.to_bytes(2, "big")

    entries = (
        entry(bytes([0x04, 0, 0, 0]), 0, 0, 2, PROPS_AT)
        + entry(bytes(4), 1, 3, 0, PROPS_AT + 0x10)
        + entry(bytes(4), 1, 0, 0, PROPS_AT + 0x10)
    )

    props = (
        bytes([1, 0xB5, 0xC5])  # short name "hi"
        + bytes([0x25, 0xBE, 0xEF])  # property 5, length 2
        + bytes([0])
    )

    return {
        OBJECTS_AT + 62: entries,
        PROPS_AT: props,
        PROPS_AT + 0x10: bytes([0, 0]),
    }


def machine_running(
    program: bytes,
    story_data: Callable[..., bytes],
    *,
    routine: bytes | None = None,
    screen: Screen | None = None,
    keyboard: Keyboard | None = None,
    patches: dict[int, bytes] | None = None,
    version: int = V3,
    program_at: int = PROGRAM,
    **fields: int,
) -> Interpreter:
    data = bytearray(story_data(version, **fields))
    data[program_at : program_at + len(program)] = program

    if routine is not None:
        data[ROUTINE : ROUTINE + len(routine)] = routine

    for address, blob in (patches or {}).items():
        data[address : address + len(blob)] = blob

    return Interpreter(
        Story(bytes(data)),
        screen if screen is not None else Screen(),
        keyboard if keyboard is not None else ScriptedKeyboard([]),
    )


def dictionary_patch(story_data: Callable[..., bytes], words: list[str]) -> bytes:
    """A no-separator dictionary holding `words`, for the fixture's address."""

    base = Story(story_data(V3))
    codec = TextCodec(base.memory, base.header)

    entries = sorted(codec.encode_word(word) for word in words)
    table = bytes([0, 7]) + len(entries).to_bytes(2, "big")

    for entry in entries:
        table += entry + bytes(3)

    return table


def object_machine(
    program: bytes,
    story_data: Callable[..., bytes],
) -> Interpreter:
    return machine_running(
        program, story_data, patches=object_patches(), object_table=OBJECTS_AT
    )


def test_boot_state(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0xB0]), story_data)

    assert_that(machine.state.pc).is_equal_to(PROGRAM)
    assert_that(machine.instruction_count).is_equal_to(0)
    assert_that(machine.running).is_true()


def test_step_reports_unimplemented_opcodes(
    story_data: Callable[..., bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # rtrue is implemented these days; strip its handler so one opcode is
    # reliably unimplemented no matter how complete the interpreter gets.
    monkeypatch.delattr(Interpreter, "_op_rtrue")

    machine = machine_running(bytes([0xB0]), story_data)

    with pytest.raises(UnimplementedOpcodeError) as error_info:
        machine.step()

    message = str(error_info.value)
    assert_that(message).contains("$00500: rtrue (0OP:0)")
    assert_that(message).contains("not implemented yet")
    assert_that(message).contains("define `Interpreter._op_rtrue`")

    # The PC and count had already advanced: a call must record the address
    # after itself as the return point (§ 4.7.2 measures from there too).
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 1)
    assert_that(machine.instruction_count).is_equal_to(1)


def test_run_dispatches_to_handlers(
    story_data: Callable[..., bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = machine_running(bytes([0xB0]), story_data)

    def stop(_instruction: Instruction) -> None:
        machine.running = False

    # No opcode handlers exist yet; graft one on so the dispatch path is
    # exercised until the real ones arrive.
    monkeypatch.setattr(machine, "_op_rtrue", stop, raising=False)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.instruction_count).is_equal_to(1)


def test_add_is_signed(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x14, 0x05, 0x0A, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(15)


def test_sub_stores_negatives_as_complements(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0x15, 0x05, 0x0A, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0xFFFB)


def test_je_branches_when_equal(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x01, 0x05, 0x05, 0xC3]), story_data)

    machine.step()

    # Offset 3: land one byte past the instruction's end (§ 4.7.2).
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4 + 1)


def test_je_falls_through_when_unequal(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0x01, 0x05, 0x06, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4)


def test_je_matches_any_later_operand(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0xC1, 0x57, 0x05, 0x09, 0x05, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 6 + 1)


def test_branches_respect_their_polarity(
    story_data: Callable[..., bytes],
) -> None:
    # Branch byte $43: branch on FALSE. The operands are equal, so no jump.
    machine = machine_running(bytes([0x01, 0x05, 0x05, 0x43]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4)


def test_jz(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x90, 0x00, 0xC4]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 3 + 2)


def test_jump_takes_a_signed_offset(story_data: Callable[..., bytes]) -> None:
    forward = machine_running(bytes([0x8C, 0x00, 0x0A]), story_data)
    forward.step()

    assert_that(forward.state.pc).is_equal_to(PROGRAM + 3 + 10 - 2)

    backward = machine_running(bytes([0x8C, 0xFF, 0xF6]), story_data)
    backward.step()

    assert_that(backward.state.pc).is_equal_to(PROGRAM + 3 - 10 - 2)


def test_storew_and_loadw_round_trip(
    story_data: Callable[..., bytes],
) -> None:
    program = (
        bytes([0xE1, 0x57, 0x80, 0x01, 0xAB])  # storew #80 #01 #ab
        + bytes([0x0F, 0x80, 0x01, 0x00])  # loadw #80 #01 -> sp
    )
    machine = machine_running(program, story_data)

    machine.step()
    machine.step()

    assert_that(machine.state.memory.read_word(0x82)).is_equal_to(0xAB)
    assert_that(machine.state.pop()).is_equal_to(0xAB)


def test_call_and_ret_round_trip(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),  # call $0300 -> sp
        story_data,
        routine=bytes([0x00, 0x9B, 0x2A]),  # no locals; ret #2a
    )

    machine.step()

    assert_that(machine.state.frames).is_length(2)
    assert_that(machine.state.pc).is_equal_to(ROUTINE + 1)

    machine.step()

    assert_that(machine.state.frames).is_length(1)
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 5)
    assert_that(machine.state.pop()).is_equal_to(0x2A)


def test_branches_can_return_instead_of_jumping(
    story_data: Callable[..., bytes],
) -> None:
    # The routine's je branches with offset 1: return true (§ 4.7.1).
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),
        story_data,
        routine=bytes([0x00, 0x01, 0x05, 0x05, 0xC1]),
    )

    machine.step()
    machine.step()

    assert_that(machine.state.frames).is_length(1)
    assert_that(machine.state.pop()).is_equal_to(1)


def test_return_false_branches_store_zero(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),
        story_data,
        routine=bytes([0x00, 0x01, 0x05, 0x05, 0xC0]),
    )

    machine.step()
    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0)


def test_print_paddr_decodes_through_the_streams(
    story_data: Callable[..., bytes],
) -> None:
    screen = RecordingScreen()

    # The routine slot holds a packed string instead: "hi" in one word.
    machine = machine_running(
        bytes([0x8D, 0x01, 0x80]),  # print_paddr #0180
        story_data,
        routine=bytes([0xB5, 0xC5]),
        screen=screen,
    )

    machine.step()

    assert_that("".join(screen.written)).is_equal_to("hi")


def test_quit_stops_the_machine(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0xBA]), story_data)

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.instruction_count).is_equal_to(1)


def test_return_opcodes(story_data: Callable[..., bytes]) -> None:
    call = bytes([0xE0, 0x3F, 0x01, 0x80, 0x00])

    cases = [
        (bytes([0xB0]), 1),  # rtrue
        (bytes([0xB1]), 0),  # rfalse
        (bytes([0xE8, 0x7F, 0x07, 0xB8]), 7),  # push #07; ret_popped
    ]

    for body, expected in cases:
        machine = machine_running(call, story_data, routine=bytes([0x00]) + body)

        while len(machine.state.frames) > 1 or machine.instruction_count == 0:
            machine.step()

        assert_that(machine.state.pop()).is_equal_to(expected)


def test_object_opcodes_read_the_world(
    story_data: Callable[..., bytes],
) -> None:
    parent = object_machine(bytes([0x93, 0x02, 0x00]), story_data)
    parent.step()
    assert_that(parent.state.pop()).is_equal_to(1)

    child = object_machine(bytes([0x92, 0x01, 0x00, 0xC3]), story_data)
    child.step()
    assert_that(child.state.pop()).is_equal_to(2)
    assert_that(child.state.pc).is_equal_to(PROGRAM + 4 + 1)  # branched

    childless = object_machine(bytes([0x92, 0x03, 0x00, 0xC3]), story_data)
    childless.step()
    assert_that(childless.state.pop()).is_equal_to(0)
    assert_that(childless.state.pc).is_equal_to(PROGRAM + 4)  # fell through

    sibling = object_machine(bytes([0x91, 0x02, 0x00, 0xC3]), story_data)
    sibling.step()
    assert_that(sibling.state.pop()).is_equal_to(3)

    prop = object_machine(bytes([0x11, 0x01, 0x05, 0x00]), story_data)
    prop.step()
    assert_that(prop.state.pop()).is_equal_to(0xBEEF)


def test_object_opcodes_change_the_world(
    story_data: Callable[..., bytes],
) -> None:
    put = object_machine(bytes([0xE3, 0x57, 0x01, 0x05, 0x11]), story_data)
    put.step()
    assert_that(put.objects.get_property(1, 5)).is_equal_to(0x11)

    attr = object_machine(bytes([0x0B, 0x02, 0x00]), story_data)
    attr.step()
    assert_that(attr.objects.test_attribute(2, 0)).is_true()

    insert = object_machine(bytes([0x0E, 0x03, 0x02]), story_data)
    insert.step()
    assert_that(insert.objects.child(2)).is_equal_to(3)
    assert_that(insert.objects.parent(3)).is_equal_to(2)


def test_object_branches(story_data: Callable[..., bytes]) -> None:
    test_attr = object_machine(bytes([0x0A, 0x01, 0x05, 0xC3]), story_data)
    test_attr.step()
    assert_that(test_attr.state.pc).is_equal_to(PROGRAM + 4 + 1)

    jin = object_machine(bytes([0x06, 0x02, 0x01, 0xC3]), story_data)
    jin.step()
    assert_that(jin.state.pc).is_equal_to(PROGRAM + 4 + 1)


def test_jl_compares_signed(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x02, 0x03, 0x07, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4 + 1)


def test_variable_adjustment_opcodes(story_data: Callable[..., bytes]) -> None:
    program = (
        bytes([0x0D, 0x10, 0x2A])  # store g00 #2a
        + bytes([0x95, 0x10])  # inc g00
        + bytes([0x05, 0x10, 0x2A, 0xC3])  # inc_chk g00 #2a: 44 > 42
    )
    machine = machine_running(program, story_data, global_variables=0x0100)

    machine.step()
    machine.step()
    machine.step()

    assert_that(machine.state.read_variable(0x10)).is_equal_to(44)
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 9 + 1)  # branched


def test_inc_touches_the_stack_in_place(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0x95, 0x00]), story_data)
    machine.state.push(4)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(5)
    assert_that(machine.state.frame.evaluation_stack).is_empty()


def test_push_and_pull(story_data: Callable[..., bytes]) -> None:
    program = bytes([0xE8, 0x7F, 0x09]) + bytes([0xE9, 0x7F, 0x10])
    machine = machine_running(program, story_data, global_variables=0x0100)

    machine.step()
    machine.step()

    assert_that(machine.state.read_variable(0x10)).is_equal_to(9)
    assert_that(machine.state.frame.evaluation_stack).is_empty()


def test_v6_pull_stores_from_the_game_stack(
    story_data: Callable[..., bytes],
) -> None:
    program = bytes([0xE8, 0x7F, 0x0B]) + bytes([0xE9, 0xFF, 0x00])
    machine = machine_running(
        program,
        story_data,
        patches={0x0480: bytes([0x00])},  # the V6 main routine: no locals
        version=V6,
        program_at=0x0481,
        initial_pc=0x0100,
        routines_offset=0x10,
    )

    machine.step()
    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0x0B)


def test_v6_pull_reads_a_user_stack(story_data: Callable[..., bytes]) -> None:
    # § 6.6: the first word counts spare slots. One value sits above them.
    machine = machine_running(
        bytes([0xE9, 0x7F, 0x90, 0x00]),
        story_data,
        patches={
            0x0480: bytes([0x00]),
            0x0090: bytes([0x00, 0x01, 0x00, 0x00, 0xFA, 0xCE]),
        },
        version=V6,
        program_at=0x0481,
        initial_pc=0x0100,
        routines_offset=0x10,
    )

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0xFACE)
    assert_that(machine.state.memory.read_word(0x0090)).is_equal_to(2)


def test_bitwise_and_is_unsigned(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x09, 0x0C, 0x0A, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(8)


def test_loadb(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(
        bytes([0x10, 0x90, 0x01, 0x00]),
        story_data,
        patches={0x0091: bytes([0x7B])},
    )

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(0x7B)


def test_print_opcodes(story_data: Callable[..., bytes]) -> None:
    screen = RecordingScreen()

    program = (
        bytes([0xB2, 0xB5, 0xC5])  # print "hi"
        + bytes([0xBB])  # new_line
        + bytes([0xE6, 0x3F, 0xFF, 0xFB])  # print_num -5
        + bytes([0xE5, 0x7F, 0x68])  # print_char 'h'
    )
    machine = machine_running(program, story_data, screen=screen)

    for _ in range(4):
        machine.step()

    assert_that("".join(screen.written)).is_equal_to("hi\n-5h")


def test_print_obj_speaks_the_short_name(
    story_data: Callable[..., bytes],
) -> None:
    screen = RecordingScreen()
    machine = machine_running(
        bytes([0x9A, 0x01]),
        story_data,
        screen=screen,
        patches=object_patches(),
        object_table=OBJECTS_AT,
    )

    machine.step()

    assert_that("".join(screen.written)).is_equal_to("hi")


def test_sread_fills_both_buffers(story_data: Callable[..., bytes]) -> None:
    program = bytes([0xE4, 0x5F, 0x90, 0xB0]) + bytes([0xBA])  # sread; quit
    machine = machine_running(
        program,
        story_data,
        keyboard=ScriptedKeyboard(["OPEN Mailbox"]),
        patches={
            0x0300: dictionary_patch(story_data, ["mailbox", "open", "xyzzy"]),
            0x0090: bytes([20]),  # text buffer: up to 19 letters
            0x00B0: bytes([5]),  # parse buffer: up to 5 words
        },
    )

    machine.run()

    memory = machine.state.memory

    # Lowercased, zero-terminated, no carriage return (§ 15, read).
    assert_that(memory.read_bytes(0x91, 13)).is_equal_to(b"open mailbox\x00")

    assert_that(memory.read_byte(0xB1)).is_equal_to(2)

    first = memory.read_word(0xB2)
    assert_that(first).is_equal_to(machine.dictionary.lookup("open"))
    assert_that(first).is_not_equal_to(0)
    assert_that(memory.read_byte(0xB4)).is_equal_to(4)
    assert_that(memory.read_byte(0xB5)).is_equal_to(1)

    second = memory.read_word(0xB6)
    assert_that(second).is_equal_to(machine.dictionary.lookup("mailbox"))
    assert_that(memory.read_byte(0xB8)).is_equal_to(7)
    assert_that(memory.read_byte(0xB9)).is_equal_to(6)

    assert_that(machine.running).is_false()  # quit ran after the read


def test_sread_marks_unknown_words(story_data: Callable[..., bytes]) -> None:
    program = bytes([0xE4, 0x5F, 0x90, 0xB0, 0xBA])
    machine = machine_running(
        program,
        story_data,
        keyboard=ScriptedKeyboard(["xyzzy plugh"]),
        patches={
            0x0300: dictionary_patch(story_data, ["open"]),
            0x0090: bytes([20]),
            0x00B0: bytes([5]),
        },
    )

    machine.run()

    memory = machine.state.memory
    assert_that(memory.read_byte(0xB1)).is_equal_to(2)
    assert_that(memory.read_word(0xB2)).is_equal_to(0)
    assert_that(memory.read_word(0xB6)).is_equal_to(0)


def test_sread_without_a_parse_buffer(story_data: Callable[..., bytes]) -> None:
    program = bytes([0xE4, 0x7F, 0x90, 0xBA])
    machine = machine_running(
        program,
        story_data,
        keyboard=ScriptedKeyboard(["go"]),
        patches={0x0090: bytes([20])},
    )

    machine.run()

    assert_that(machine.state.memory.read_bytes(0x91, 3)).is_equal_to(b"go\x00")
    assert_that(machine.running).is_false()


def test_end_of_input_ends_the_session(story_data: Callable[..., bytes]) -> None:
    # The default keyboard has no script: reading from it is EOF, which is
    # a departure rather than a fault.
    machine = machine_running(
        bytes([0xE4, 0x7F, 0x90]), story_data, patches={0x0090: bytes([20])}
    )

    machine.run()

    assert_that(machine.running).is_false()
    assert_that(machine.instruction_count).is_equal_to(1)


def test_dec_family(story_data: Callable[..., bytes]) -> None:
    program = (
        bytes([0x0D, 0x10, 0x2A])  # store g00 #2a
        + bytes([0x96, 0x10])  # dec g00
        + bytes([0x04, 0x10, 0x2A, 0xC3])  # dec_chk g00 #2a: 40 < 42
    )
    machine = machine_running(program, story_data, global_variables=0x0100)

    machine.step()
    machine.step()
    machine.step()

    assert_that(machine.state.read_variable(0x10)).is_equal_to(40)
    assert_that(machine.state.pc).is_equal_to(PROGRAM + 9 + 1)  # branched


def test_test_branches_when_every_bit_is_set(
    story_data: Callable[..., bytes],
) -> None:
    all_set = machine_running(bytes([0x07, 0x0C, 0x04, 0xC3]), story_data)
    all_set.step()
    assert_that(all_set.state.pc).is_equal_to(PROGRAM + 4 + 1)

    partial = machine_running(bytes([0x07, 0x0C, 0x05, 0xC3]), story_data)
    partial.step()
    assert_that(partial.state.pc).is_equal_to(PROGRAM + 4)


def test_jg(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x03, 0x07, 0x05, 0xC3]), story_data)

    machine.step()

    assert_that(machine.state.pc).is_equal_to(PROGRAM + 4 + 1)


def test_mul(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x16, 0x06, 0x07, 0x00]), story_data)

    machine.step()

    assert_that(machine.state.pop()).is_equal_to(42)


def test_division_truncates_toward_zero(
    story_data: Callable[..., bytes],
) -> None:
    # The numbers.py prophecy: -11 div 2 is -5, where // would say -6.
    div = machine_running(bytes([0xD7, 0x1F, 0xFF, 0xF5, 0x02, 0x00]), story_data)
    div.step()
    assert_that(div.state.pop()).is_equal_to(0xFFFB)

    # And the remainder keeps the dividend's sign: -13 mod 4 is -1.
    mod = machine_running(bytes([0xD8, 0x1F, 0xFF, 0xF3, 0x04, 0x00]), story_data)
    mod.step()
    assert_that(mod.state.pop()).is_equal_to(0xFFFF)


def test_division_by_zero_faults(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0x17, 0x05, 0x00, 0x00]), story_data)

    with pytest.raises(ExecutionError) as error_info:
        machine.step()

    assert_that(str(error_info.value)).contains("division by zero")


def test_storeb(story_data: Callable[..., bytes]) -> None:
    machine = machine_running(bytes([0xE2, 0x57, 0x90, 0x01, 0xAB]), story_data)

    machine.step()

    assert_that(machine.state.memory.read_byte(0x91)).is_equal_to(0xAB)


def test_clear_attr(story_data: Callable[..., bytes]) -> None:
    machine = object_machine(bytes([0x0C, 0x01, 0x05]), story_data)

    machine.step()

    assert_that(machine.objects.test_attribute(1, 5)).is_false()


def test_get_prop_addr(story_data: Callable[..., bytes]) -> None:
    found = object_machine(bytes([0x12, 0x01, 0x05, 0x00]), story_data)
    found.step()
    assert_that(found.state.pop()).is_equal_to(PROPS_AT + 4)

    absent = object_machine(bytes([0x12, 0x02, 0x05, 0x00]), story_data)
    absent.step()
    assert_that(absent.state.pop()).is_equal_to(0)


def test_get_prop_len(story_data: Callable[..., bytes]) -> None:
    # 1OP with a large-constant operand: the data address of property 5.
    two = object_machine(bytes([0x84, 0x01, 0x04, 0x00]), story_data)
    two.step()
    assert_that(two.state.pop()).is_equal_to(2)

    zero = object_machine(bytes([0x84, 0x00, 0x00, 0x00]), story_data)
    zero.step()
    assert_that(zero.state.pop()).is_equal_to(0)


def test_print_ret(story_data: Callable[..., bytes]) -> None:
    screen = RecordingScreen()
    machine = machine_running(
        bytes([0xE0, 0x3F, 0x01, 0x80, 0x00]),  # call $0300 -> sp
        story_data,
        routine=bytes([0x00, 0xB3, 0xB5, 0xC5]),  # print_ret "hi"
        screen=screen,
    )

    machine.step()
    machine.step()

    assert_that("".join(screen.written)).is_equal_to("hi\n")
    assert_that(machine.state.frames).is_length(1)
    assert_that(machine.state.pop()).is_equal_to(1)


def test_call_with_no_operands_faults(
    story_data: Callable[..., bytes],
) -> None:
    machine = machine_running(bytes([0xE0, 0xFF]), story_data)

    with pytest.raises(ExecutionError) as error_info:
        machine.step()

    assert_that(str(error_info.value)).contains("has no routine to call")


def test_helpers_tolerate_absent_store_and_branch(
    story_data: Callable[..., bytes],
) -> None:
    # rtrue carries neither a store byte nor branch data; the helpers must
    # shrug rather than assume.
    machine = machine_running(bytes([0xB0]), story_data)
    rtrue = machine.decoder.decode(PROGRAM)

    machine._store(rtrue, 5)
    machine._branch(rtrue, condition=True)
    machine._op_print(rtrue)  # no inline text either: nothing to print

    assert_that(machine.state.frame.evaluation_stack).is_empty()
    assert_that(machine.state.pc).is_equal_to(PROGRAM)
