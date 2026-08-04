from collections.abc import Callable

import pytest
from assertpy import assert_that

from quendor.zmachine.errors import ExecutionError, UnimplementedOpcodeError
from quendor.zmachine.instructions import Instruction
from quendor.zmachine.interpreter import Interpreter
from quendor.zmachine.output import Screen
from quendor.zmachine.story import Story
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

    return Interpreter(Story(bytes(data)), screen if screen is not None else Screen())


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
