# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The `fliberator` package is still scaffolded (src layout, managed with `uv`) — `src/fliberator/__init__.py` only exports `__version__`. The actual NXT-decoding logic exists as throwaway analysis scripts in `scripts/`, not yet promoted into the package: `nxt_survey.py` (header/corpus survey), `nxt_decode_poc.py` (tokenized-markup decoder), `nxt_build_index.py` (citation → byte-offset index). See `docs/nxt-format.md` for the reverse-engineered format spec and `plans/re-plan.md` for phase-by-phase status (what's done vs. still open — promoting these scripts into the real package is one of the open phases).

## Commands

Dependency management, the venv, and script running all go through [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                 # install/update the venv from pyproject.toml + uv.lock
uv run pytest           # run the test suite
uv run pytest tests/test_import.py::test_version_is_set  # run a single test
uv run ruff check .     # lint
uv run ruff format .    # format
```

The package targets Python 3.12+ and builds with `hatchling`. Source lives under `src/fliberator/` (src layout — always run code via `uv run`, not a bare interpreter pointed at the repo root, so the installed package is used).

## What FLiberator does

FLiberator converts Florida's officially-distributed statutes bulk data out of a proprietary format into open, usable formats: HTML plus a JSON metadata sidecar. It does exactly one thing: liberate the downloadable Florida statutes.

## Pipeline

The intended data flow, in order — **settled** (see `plans/re-plan.md` Phase 5; this pipeline shape replaces an earlier NXT→FFF→XML plan, abandoned once the NXT content layer itself turned out to be directly decodable):

1. **Download** the "Advanced Legislative Search & Browse" application zip from Florida's official download page into a git-ignored working folder. Example: `https://www.leg.state.fl.us/Statutes/FLLawDL2025.zip` (2025 statutes). Not yet automated (`plans/re-plan.md` Phase 6).
2. **Unzip** the archive. Not yet automated.
3. **Decode NXT → HTML + JSON directly.** The statutes are distributed as Rocket® NXT (`.nxt`) files — the key source file is `Library/fs2025.nxt`. This is a proprietary "Infobase" container, but its content layer turned out to be a thin opcode wrapper around otherwise-literal HTML text (a length-prefixed literal-text token plus a handful of control opcodes — see `docs/nxt-format.md`). Decoding it is a "decompress the tokens back to text" problem, not a format-conversion problem, which is why no intermediate format is needed: a proof-of-concept decoder (`scripts/nxt_decode_poc.py`) and citation index builder (`scripts/nxt_build_index.py`) already exist as analysis scripts; promoting them into the installable package is `plans/re-plan.md` Phase 7.

## Key external references

- Florida statutes download page: `https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes`
- Rocket NXT / Folio NXT software: `https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt`

## Working conventions

- Downloaded/unzipped artifacts (the statutes zip, extracted `.nxt` files) belong in a git-ignored working folder, not committed to the repo.
- Format research lives in `docs/nxt-format.md` (living notes — append as understanding grows, don't just overwrite history) and `plans/re-plan.md` (phase-by-phase status). Check both before re-deriving something about the format that's likely already been figured out.
