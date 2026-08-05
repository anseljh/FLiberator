# FLiberator

FLiberator is a small open-source software package that does exactly one thing: it liberates the downloadable Florida statutes from a weird proprietary format.

License: MIT

## Install

FLiberator is managed with [`uv`](https://docs.astral.sh/uv/) and requires Python 3.12+.

```bash
uv sync
```

This installs the `fliberator` package (in editable mode) into a local `.venv`, importable as:

```python
import fliberator
```

## Steps

1. FLiberator downloads, into the git-ignored `download/` folder, the "Advanced Legislative Search & Browse" application zip file from its [download page](https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes). Run with `uv run python scripts/download.py` — it scrapes the download page for the current year's zip link (currently `FLLawDL2025.zip`) rather than hardcoding a year.
2. FLiberator unzips the file, also into `download/` (same script).
3. FLiberator decodes the Rocket NXT (`.nxt`) files directly into HTML, plus a JSON sidecar mapping each statute citation to its location in the source file. See [`docs/nxt-format.md`](docs/nxt-format.md) for how the format was reverse-engineered and how decoding works. Output will land in the git-ignored `output/` folder once its shape is decided (see `plans/re-plan.md`).

## Background

- Florida provides a downloadable Windows desktop application called "Advanced Legislative Search & Browse", which contains a bulk dataset of the Florida statutes: <https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes>.
- After extracting the zip file for the application, there are several `.nxt` files. This is a proprietary "Infobase" container format produced by [Rocket® NXT / Folio NXT software](https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt) (the Folio Views product line).
- The Florida statutes file is `Library/fs2025.nxt`.
- `.nxt` files turn out to contain **tokenized-but-mostly-literal HTML**: a thin, partially-reverse-engineered opcode layer wraps ordinary markup and text rather than replacing it. That made it possible to decode `.nxt` straight to HTML, without ever producing an intermediate Folio Flat File (`.fff`) or depending on the [`folioxml`](https://github.com/imazen/folioxml) converter — an earlier plan for this project, abandoned once the NXT content layer itself turned out to be understandable and sufficient on its own. See [`docs/nxt-format.md`](docs/nxt-format.md) for the full technical writeup.
