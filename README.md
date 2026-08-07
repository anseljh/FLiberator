# FLiberator

FLiberator is a small open-source software package that does exactly one thing: it liberates the downloadable Florida statutes from a weird proprietary format.

Florida publishes its statutes in bulk only as a Windows application built on Rocket® NXT, a proprietary "Infobase" container. FLiberator turns that into ordinary HTML — one file per section — plus a JSON sidecar with the ordering and hierarchy the HTML can't carry.

License: MIT

## Quick start

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.12+. Two commands, from a fresh clone:

```bash
uv sync                      # create .venv and install the package
uv run fliberate --download  # fetch Florida's bulk data, then decode it
```

That's the whole pipeline. It takes about **two minutes**, nearly all of it the download:

```
downloading https://www.leg.state.fl.us/Statutes/FLLawDL2025.zip
  248,586,704 bytes / 248,586,704 (100%)
extracted 13 .nxt files (371,822,592 bytes)
       edition: 2025
      statutes: 24,866 documents  <- fs2025.nxt
  constitution:    213 documents  <- flcnst2025.nxt
          laws:    255 documents  <- lf2025.nxt
         total: 25,334 documents written to output/
```

You need roughly **820 MB** of free disk: 249 MB for the zip, 372 MB unpacked, 201 MB of output. Decoding by itself, once the data is on disk, takes about 18 seconds.

Already have the data? Drop `--download` and it decodes what's in `download/` — the download and unzip steps are both skipped automatically if their results are already there, so re-running `--download` is safe and cheap.

## What you get

Output lands in the git-ignored `output/` folder:

```
output/
  metadata.json                            ordering, hierarchy, provenance
  statutes/0001/1.01.html                  24,866 sections
  constitution/article-01/section-03.html      213 sections
  laws/2025-1.html                             255 session laws
```

**What's covered:** the three files holding Florida primary law — the statutes, the Florida Constitution, and the Laws of Florida. The bulk distribution's eight finding-aid files (subject and definition indexes, cross-reference and tracing tables), the bundled US Constitution, and the help PDF are deliberately out of scope.

**Footnotes** are rewritten as semantic HTML5: each reference becomes a `<sup><a role="doc-noteref">`, and the note bodies are collected into a `<section role="doc-endnotes">` at the end of the section, with one backlink per referrer.

**`metadata.json`** carries what the HTML can't — canonical ordering (documents are stored in build order, which has nothing to do with statutory order), the full Title → Chapter → Part hierarchy, per-document footnote counts, and the edition year plus the SHA-256 of each source file so two years' output can be told apart.

The edition year is discovered from the filenames (`fs2025.nxt`, `flcnst2025.nxt`, `lf2025.nxt`), never hardcoded, so next year's data needs no code change.

## Commands

```bash
uv run fliberate --download          # fetch + unzip into download/, then decode
uv run fliberate                     # decode the newest edition already in download/
uv run fliberate --library DIR       # decode a specific Library/ directory
uv run fliberate --output DIR        # write somewhere other than output/
uv run fliberate --version
```

The package is also importable, if you'd rather drive it yourself:

```python
from fliberator import decode, depage

records = depage.load_records("download/FLLawDL2025/Library/fs2025.nxt")
html = decode.decode(records[0], 0, len(records[0]))[0]
```

## How it works

1. **Download.** FLiberator fetches the "Advanced Legislative Search & Browse" application zip from its [download page](https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes) into the git-ignored `download/` folder. It scrapes the page for the current year's link (currently `FLLawDL2025.zip`) rather than hardcoding a year.
2. **Unzip**, also into `download/` — extracting only the 13 `.nxt` data files, not the 1,369 other entries of the Windows viewer application Florida wraps them in.
3. **Decode** the Rocket NXT files directly into HTML plus the JSON sidecar. This is two layers: a paged storage layer (the file is a store of 4 KB pages, and a document is a chain of fragments scattered across non-adjacent ones, which must be reassembled before any byte is read as content) and a content layer (a thin opcode wrapper around otherwise-literal HTML). See [`docs/nxt-format.md`](docs/nxt-format.md) for how the format was reverse-engineered.

## Development

```bash
uv run pytest                # the test suite
uv run ruff check .          # lint
uv run ruff format .         # format
```

`scripts/` holds the analysis and validation code the reverse-engineering was done with — not part of the package, but still useful as regression checks against the live leg.state.fl.us pages. See [`plans/re-plan.md`](plans/re-plan.md) for phase-by-phase status.

## Background

- Florida provides a downloadable Windows desktop application called "Advanced Legislative Search & Browse", which contains a bulk dataset of the Florida statutes: <https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes>.
- After extracting the zip file for the application, there are several `.nxt` files. This is a proprietary "Infobase" container format produced by [Rocket® NXT / Folio NXT software](https://www.rocketsoftware.com/en-us/products/folio-nxt/nxt) (the Folio Views product line).
- The Florida statutes file is `Library/fs2025.nxt`.
- `.nxt` files turn out to contain **tokenized-but-mostly-literal HTML**: a thin, partially-reverse-engineered opcode layer wraps ordinary markup and text rather than replacing it. That made it possible to decode `.nxt` straight to HTML, without ever producing an intermediate Folio Flat File (`.fff`) or depending on the [`folioxml`](https://github.com/imazen/folioxml) converter — an earlier plan for this project, abandoned once the NXT content layer itself turned out to be understandable and sufficient on its own. See [`docs/nxt-format.md`](docs/nxt-format.md) for the full technical writeup.
