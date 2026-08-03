# Quendor

A Z-Machine emulator and interpreter, written in Python.

The Z-Machine is the virtual machine that Infocom designed in 1979 to run its
text adventures, and which the interactive fiction community has used ever
since. Quendor reads a compiled story file and executes it.

> **Status:** pre-alpha. Quendor can load, validate, inspect, and disassemble
> story files; it cannot yet run them.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/) for dependency and environment management

## Installation

```bash
git clone https://github.com/jeffnyman/quendor-py.git
cd quendor-py
uv sync --all-groups
```

## Usage

Quendor takes a story file -- a compiled Z-Machine game -- and, for now,
inspects it. Running it comes later.

```bash
uv run quendor STORY.z3                        # load and validate a story
uv run quendor STORY.z3 --header               # display the header
uv run quendor STORY.z3 --disassemble          # decode instructions
uv run quendor STORY.z3 --disassemble --start 6e9b --count 8
```

- `--header` reports the story's identity (Version, release, serial), its
  flags decoded into words, the memory map, table addresses, and where
  execution begins, laid out for comparison against ztools' `infodump`.
- `--disassemble` lists instructions in roughly `txd`'s layout: address,
  raw bytes, mnemonic, operands, store, branch, and inline text. `--start`
  takes a hex byte address and defaults to the first instruction; `--count`
  defaults to 16.
- A `.zblorb` package is unwrapped and its story loaded. A resource-only
  Blorb is rejected with a message saying what it holds instead -- and
  naming the story file sitting beside it, when there is an obvious one.

The package is also runnable as a module:

```bash
uv run python -m quendor STORY.z3
```

## Development

All commands assume the environment created by `uv sync --all-groups`.

| Task | Command |
| --- | --- |
| Run the test suite | `uv run pytest` |
| Run tests without coverage | `uv run pytest --no-cov` |
| Lint | `uv run ruff check .` |
| Lint and autofix | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Check formatting only | `uv run ruff format --check .` |
| Type check | `uv run mypy` |
| Build distributions | `uv build` |

### Pre-commit hooks

Install the hooks once, after which lint, format, and type checks run on every
commit, and commit messages are validated:

```bash
uv run pre-commit install
```

Every hook is a `repo: local` entry that runs its tool out of the project
environment via `uv run`, so pre-commit never clones hook repositories or
builds cached environments under `~/.cache/pre-commit`. Tool versions have a
single source of truth: `uv.lock`.

To run every hook against the whole tree:

```bash
uv run pre-commit run --all-files
```

### Commit messages

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced at commit time by [commitizen](https://commitizen-tools.github.io/commitizen/)
through the `commit-msg` hook installed above:

```text
feat: add object table parsing
fix(memory): reject story files shorter than the header
docs: explain the save file format
```

To check a message by hand, or to compose one interactively:

```bash
uv run cz check -m "feat: add object table parsing"
uv run cz commit
```

Because the history is machine-readable, commitizen can also derive the next
version, tag it, and update the changelog once releases begin:

```bash
uv run cz bump
```

### Optional test artifacts

Quendor does not depend on anything under `entharion/`. It is neither needed
to install the project nor to run the test suite, and CI does not fetch it.
Git leaves submodules empty unless asked, so a plain clone simply skips it.

It exists for hands-on work on the interpreter: story files to run, and tools
to inspect what they contain.

| Path | Source | Contains |
| --- | --- | --- |
| `entharion/` | [entharion](https://github.com/jeffnyman/entharion) | ZIL sources and Z-Machine reference material |

To fetch it, along with the [frotz](https://gitlab.com/DavidGriffith/frotz),
[ztools](https://github.com/jeffnyman/ztools), and
[reform6](https://github.com/jeffnyman/reform6) submodules it carries:

```bash
git submodule update --init --recursive
```

To discard it again, freeing the disk space without affecting the project:

```bash
git submodule deinit --all
```

None of it is treated as project source. Ruff excludes the directory via
`extend-exclude`, and mypy and pytest never see it, being scoped to `src` and
`tests`.

To move the pinned commit to the latest upstream:

```bash
git submodule update --remote entharion
git add entharion
git commit -m "Update entharion submodule"
```

### Project conventions

- **Layout.** Source lives under `src/quendor`, tests under `tests/`. The `src`
  layout ensures tests exercise the installed package rather than the working
  directory.
- **Typing.** `mypy` runs in strict mode over both `src` and `tests`, and the
  package ships a `py.typed` marker so downstream consumers get its types.
- **Coverage.** The suite is gated at 100% branch coverage. This is deliberate
  for a project of this size; adjust `fail_under` in `pyproject.toml` if it
  stops being useful.
- **Spec citations.** The `§` references in code, docstrings, and output
  follow the HTML rendering of the Z-Machine Standard 1.1 vendored at
  `entharion/specs/Z-Machine-Standard-1.1/`. Other renderings of the same
  Standard, including the PDF beside it, number some paragraphs differently.
- **Line endings.** LF everywhere except Windows script files, enforced by both
  `.gitattributes` and `.editorconfig`.

## License

Released under the [MIT License](LICENSE).
