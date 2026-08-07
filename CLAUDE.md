# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

The `fliberator` package is **real** (src layout, managed with `uv`): `src/fliberator/` holds `depage.py` (storage layer), `decode.py` (content layer), `footnotes.py` (semantic HTML5 footnote rewriting), `documents.py` (identity + canonical ordering per collection), `emit.py` (writes HTML + `metadata.json`) and `cli.py`. Run the whole pipeline with `uv run fliberate` — ~18 seconds for 25,334 documents.

Scope is **Florida primary law only**: `fs2025.nxt` (24,866 statute sections), `flcnst2025.nxt` (213 constitution sections), `lf2025.nxt` (255 session laws). The eight finding-aid files, `uscon.nxt` and the help PDF are deliberately out (see `plans/re-plan.md` Phase 9).

`scripts/` holds the throwaway analysis and validation code the reverse-engineering was done with — still useful as regression checks, not part of the package: `nxt_survey.py` (header/corpus survey), `nxt_depage.py`/`nxt_decode_poc.py` (the originals the package modules were promoted from), `nxt_build_index.py` (citation → document index), `nxt_find_gaps.py` (decoder-independent completeness check), `nxt_validate.py` (fidelity vs. the live site; `--sample N`, `--all` for the full census), `nxt_validate_markup.py` (element-stream fidelity), `nxt_check_output.py` (**decoder self-check against the source bytes** — catches whitespace/doubling defects `nxt_validate.py` structurally cannot see, since it collapses `\s+` before scoring), `nxt_classify_diffs.py` (classifies differences by *shape*, which matters because the 0.99 ratio threshold sorts by document length rather than badness), `nxt_check_entities.py` (entity-representation fidelity), `nxt_corpus_triage.py` (both layers over all 13 files), `nxt_validate_constitution.py` and `nxt_validate_session_laws.py` (ground truth for the other primary-law files; the latter needs `pdftotext`), `download.py` (fetches + unzips the bulk data). See `docs/nxt-format.md` for the format spec and `plans/re-plan.md` for phase-by-phase status.

## Commands

Dependency management, the venv, and script running all go through [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync                 # install/update the venv from pyproject.toml + uv.lock
uv run pytest           # run the test suite
uv run pytest tests/test_footnotes.py    # run one test file
uv run fliberate        # decode download/ -> output/
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
3. **Decode NXT → HTML + JSON directly.** The statutes are distributed as Rocket® NXT (`.nxt`) files — the key source file is `Library/fs2025.nxt`. This is a proprietary "Infobase" container with two layers that must be peeled in order:
   - **Storage layer (`scripts/nxt_depage.py`).** The file is a *paged store*: exactly 58,626 × 4096-byte pages, each with a typed header, where a document is a chain of fragments scattered across non-adjacent pages. Reassemble documents before reading any bytes as content. Skipping this step is what produced every "corruption" symptom recorded in `docs/nxt-format.md` before Phase 2d — the damage was never in the data.
   - **Content layer (`scripts/nxt_decode_poc.py`).** Once reassembled, a document is a thin opcode wrapper around otherwise-literal HTML text (a length-prefixed literal-text token plus a handful of control opcodes). Decoding it is a "decompress the tokens back to text" problem, not a format-conversion problem — which is why no intermediate format is needed.

   Both now live in the package as `fliberator.depage` and `fliberator.decode`; the `scripts/` copies are kept as the analysis originals.
4. **Emit** one HTML file per section plus a single `output/metadata.json` (`fliberator.emit`). Footnotes are rewritten as semantic HTML5 along the way (`fliberator.footnotes`).

## Key external references

- Florida statutes download page: `https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes`
- Rocket NXT / Folio NXT software: `https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt`

## Working conventions

- Three data folders, all git-ignored except where noted:
  - `FLLawDL2025/` — the **frozen, read-only reference copy** this entire reverse-engineering effort (Phases 1-4) was developed and validated against. Never written to by any script; treat it as fixed ground truth for development, not as the live data source.
  - `download/` — where `scripts/download.py` fetches and unzips the **current, live** bulk data (`download/FLLawDL2025.zip`, `download/FLLawDL2025/Library/*.nxt`). This is what `uv run fliberate` reads by default. The analysis scripts in `scripts/` still default to `FLLawDL2025/`, since that is what they were developed and checked against; the two are currently byte-identical.
  - `output/` — where `uv run fliberate` writes: `metadata.json` plus `statutes/`, `constitution/` and `laws/` trees. Regenerated from scratch each run.
- Format research lives in `docs/nxt-format.md` (living notes — append as understanding grows, don't just overwrite history) and `plans/re-plan.md` (phase-by-phase status). Check both before re-deriving something about the format that's likely already been figured out.
