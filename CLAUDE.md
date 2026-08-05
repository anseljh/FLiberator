# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The `fliberator` package is still scaffolded (src layout, managed with `uv`) — `src/fliberator/__init__.py` only exports `__version__`. The actual NXT-decoding logic exists as throwaway analysis scripts in `scripts/`, not yet promoted into the package: `nxt_survey.py` (header/corpus survey), `nxt_decode_poc.py` (tokenized-markup decoder), `nxt_build_index.py` (citation → byte-offset index), `nxt_validate.py` (validation harness vs. the live site), `download.py` (fetches + unzips the bulk data). See `docs/nxt-format.md` for the reverse-engineered format spec and `plans/re-plan.md` for phase-by-phase status (what's done vs. still open — promoting these scripts into the real package is one of the open phases).

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

1. **Download** the "Advanced Legislative Search & Browse" application zip from Florida's official download page into `download/` (git-ignored). Example: `https://www.leg.state.fl.us/Statutes/FLLawDL2025.zip` (2025 statutes). Automated: `uv run python scripts/download.py` scrapes the download page for the current year's zip link (doesn't hardcode a year) and fetches it.
2. **Unzip** the archive, also into `download/`. Automated by the same script — `download/FLLawDL2025/Library/*.nxt` ends up laid out identically to the frozen reference copy (see "Working conventions" below).
3. **Decode NXT → HTML + JSON directly.** The statutes are distributed as Rocket® NXT (`.nxt`) files — the key source file is `Library/fs2025.nxt`. This is a proprietary "Infobase" container, but its content layer turned out to be a thin opcode wrapper around otherwise-literal HTML text (a length-prefixed literal-text token plus a handful of control opcodes — see `docs/nxt-format.md`). Decoding it is a "decompress the tokens back to text" problem, not a format-conversion problem, which is why no intermediate format is needed: a proof-of-concept decoder (`scripts/nxt_decode_poc.py`) and citation index builder (`scripts/nxt_build_index.py`) already exist as analysis scripts; promoting them into the installable package, and deciding/implementing where in `output/` their results should land, are `plans/re-plan.md` Phases 7 and 9.

## Key external references

- Florida statutes download page: `https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes`
- Rocket NXT / Folio NXT software: `https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt`

## Working conventions

- Three data folders, all git-ignored except where noted:
  - `FLLawDL2025/` — the **frozen, read-only reference copy** this entire reverse-engineering effort (Phases 1-4) was developed and validated against. Never written to by any script; treat it as fixed ground truth for development, not as the live data source.
  - `download/` — where `scripts/download.py` fetches and unzips the **current, live** bulk data (`download/FLLawDL2025.zip`, `download/FLLawDL2025/Library/*.nxt`). This is what a real run of the pipeline should read from once one exists (Phase 7+); analysis scripts default to `FLLawDL2025/` for now since that's what they were developed and checked against.
  - `output/` — where decoded HTML/JSON output belongs once Phase 9 decides its shape. Currently empty/unused.
- Format research lives in `docs/nxt-format.md` (living notes — append as understanding grows, don't just overwrite history) and `plans/re-plan.md` (phase-by-phase status). Check both before re-deriving something about the format that's likely already been figured out.
