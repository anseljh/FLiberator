# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The `fliberator` package is scaffolded (src layout, managed with `uv`) but has no pipeline logic implemented yet — `src/fliberator/__init__.py` only exports `__version__`. The conversion pipeline described below (download → unzip → NXT→FFF → FFF→XML) still needs to be built.

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

FLiberator converts Florida's officially-distributed statutes bulk data out of a proprietary format into open, usable formats. It does exactly one thing: liberate the downloadable Florida statutes.

## Planned pipeline

The intended data flow, in order:

1. **Download** the "Advanced Legislative Search & Browse" application zip from Florida's official download page into a git-ignored working folder. Example: `https://www.leg.state.fl.us/Statutes/FLLawDL2025.zip` (2025 statutes).
2. **Unzip** the archive.
3. **Convert NXT → FFF**: the statutes are distributed as Rocket® NXT (`.nxt`) files — the key source file is `Library/fs2025.nxt`. This is a proprietary format. Conversion to Folio Flat File (`.fff`) format is the hardest, currently-unsolved step (marked TBD in the README) — expect to research Rocket NXT/Folio internals here.
4. **Convert FFF → XML**: once `.fff` files exist, the Apache 2.0-licensed [`folioxml`](https://github.com/imazen/folioxml) package converts them to XML. This step is believed to be solved by existing tooling; the hard part of this project is step 3.

## Key external references

- Florida statutes download page: `https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes`
- Rocket NXT / Folio NXT software: `https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt`
- `folioxml` (FFF → XML converter, Apache 2.0): `https://github.com/imazen/folioxml`

## Working conventions

- Downloaded/unzipped artifacts (the statutes zip, extracted `.nxt`/`.fff` files) belong in a git-ignored working folder, not committed to the repo.
