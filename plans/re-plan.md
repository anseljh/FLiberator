# Plan: Reverse-engineer the Folio NXT `.nxt` Infobase format

## Status

Phases 1, 2, 2b, 2c, 3, 4, 5, and 6 are **done**. Phase 5's pipeline
decision is settled: FLiberator decodes `.nxt` **directly to HTML + JSON**,
with no `.fff` intermediate and no dependency on `folioxml` — see
README.md and CLAUDE.md. Phase 4 (validation harness,
`scripts/nxt_validate.py`) found that content loss/corruption from the
Phase 2b paging-interruption mechanism is more widespread than previously
quantified — see docs/nxt-format.md "Phase 4" — which motivated Phase 2c.
Phase 2c (`scripts/nxt_find_gaps.py`) added a third, decoder-independent
detection signal and confirmed 95 "double failure" gaps (0.38% of indexed
citations) — see docs/nxt-format.md "Phase 2c". Phase 6
(`scripts/download.py`) established the `download/`/`output/`
working-folder convention alongside the frozen `FLLawDL2025/` reference
copy — see CLAUDE.md "Working conventions". Phases 7-9 (package promotion,
rest-of-corpus, output format) are scoped but not started.

## Context

FLiberator's pipeline was originally assumed to be: download → unzip →
convert `.NXT` → `.FFF` → convert `.FFF` → XML (via `folioxml`), with step
3 (NXT → FFF) an unsolved TBD. Before writing any conversion code, this
plan's analysis phases set out to understand what's actually inside
`fs2025.nxt` (240MB, the 2025 Florida Statutes) well enough to extract its
content programmatically — and, along the way, to answer whether the FFF
intermediate was even necessary. It wasn't: see Phase 5 below.

This plan was originally scoped as **analysis only** — producing a working
understanding of the format and a proof-of-concept decoder, not a
production converter. Phases 6-9 now extend it into what a production
converter needs.

### What we already know (from hands-on inspection, early session)

This wasn't a cold start — direct inspection of `FLLawDL2025/Library/*.nxt`
and the bundled installer surfaced concrete, load-bearing facts before any
scripted analysis began:

1. **File header.** Every `.nxt` file (checked `uscon.nxt` and `fs2025.nxt`) starts with an identical 78-byte ASCII string: `Copyright (c) 1991-20XX, Rocket Software, Inc.  All Rights Reserved. Infobase\r\n`, then null-padded out to offset `0xE0`. This confirms "Infobase" as the internal format name (Rocket Folio's product lineage, per the Wikipedia Folio Corporation history).
2. **Fixed binary header, `0xE0`–~`0x200`.** A mix of constant fields shared across otherwise-unrelated files (format/version constants) and per-file fields that vary (a hash/GUID-looking value, little-endian `uint32` count fields around `0x1B0`–`0x1BF`). See `docs/nxt-format.md`'s header table for the fully-confirmed field-by-field breakdown (Phase 1 output).
3. **The content is tokenized HTML, not opaque binary.** Large stretches of both files are near-verbatim HTML/CSS with occasional 1-4 byte binary opcodes spliced in. Confirmed by locating actual statute text (§ 1.01, cross-checked against leg.state.fl.us). Per-section anchor IDs are embedded literally, e.g. `#!-- #ID=FS20250001.01 --#`, directly encoding year + chapter + section — this became the basis for the Phase 3 citation index.
4. **Ground truth source confirmed reachable.** `WebFetch` on leg.state.fl.us section URLs returns clean section text, live-fetchable per-section — a reliable oracle for validating decoded output (used throughout, and the basis for Phase 4).
5. **The bundled Windows binaries are a red herring for the core engine.** `copy/Work-Set.exe`, `Serv-Go.exe`, `Serv-Out.exe`, and the bundled DLLs are **WinBatch**-compiled installer/service-management helpers (confirmed via string-table matches to WinBatch's runtime) — they configure a local web server, they don't parse Infobase files.
6. **`data1.cab`/`data2.cab`** (InstallShield cabinets) are unextracted (no `cabextract`/`unshield`/`7z` available) and likely contain the real NXT engine binaries. Not touched — static analysis of the tokenized-markup layer turned out to be sufficient (see Phase 2), so this was never needed.

### Files available as test corpus

`Library/` has 13 `.nxt` files ranging 319KB (`uscon.nxt`, US Constitution — small, well-known ground truth) up to 240MB (`fs2025.nxt`). `uscon.nxt` was the primary small-scale target for header/opcode work (fast iteration, public and short content); `fs2025.nxt` is the main target for the actual deliverable. See `docs/nxt-format.md`'s Corpus table for the full file list and current understanding of each one's purpose.

## Goals

1. Produce a documented, reasonably confident model of the `.nxt` container: file header fields, the tokenized-markup opcode set, and how individual "documents" (statute sections / constitutional articles) are delimited and located. — **done, Phases 1-3**
2. Produce a working Python proof-of-concept script that can extract full, correctly-reconstructed sections from `fs2025.nxt`, cross-checked against the live site. — **done, Phase 2/3**
3. Leave enough written notes (`docs/nxt-format.md`) that the next session — or the actual converter implementation — doesn't have to re-derive this. — **ongoing, living document**

## Phases

### Phase 1 — Corpus survey ✅ done
Surveyed header fields (`0x00`-`0x200`) and byte-frequency histograms across
all 13 `.nxt` files via `scripts/nxt_survey.py`. Confirmed which header
fields are constant (format/version markers) vs. per-file (counts,
hashes). See `docs/nxt-format.md` "Container header".

### Phase 2 — Decode the tokenized-markup layer ✅ done
Built `scripts/nxt_decode_poc.py`: a byte-scanner implementing the
length-prefixed literal-text opcode (`\x13 <subtype> <len> <text>`,
1-or-2-byte length), universal printable/UTF-8 run sniffing (not
opcode-gated — a lot of real text is completely unprefixed), and the
character-formatting toggle opcode (`\x10 <0|1> 0x03 0x82 <id> 0x01`).
Extracts complete, verbatim section text from `fs2025.nxt` (verified
against § 1.01 word-for-word) and generalizes with no format-specific
logic to a completely different document era (`uscon.nxt`, pre-XHTML
markup). This result is what made the Phase 5 pipeline decision possible —
see `docs/nxt-format.md` "Phase 2: decoder for the tokenized-markup
layer".

### Phase 2b — Close the Phase 3 v2 merge gap ✅ done
Fixed the ~3.8% of Phase 3 v2 index entries that silently merged more than
one document. The cause (real `LPDD` page markers interrupting literal
text runs mid-token) turned out to be paging/storage-layout behavior, not
a missing opcode — not worth modeling in the decoder. Fixed instead at the
index-building level: recover orphaned `<div class="Section">` documents
directly via their `SectionNumber` text, which survives every case
checked. Result: 26,317 documents, 982 recovered, 0 entries left with more
than one Section div (was 991); a small number of duplicate/garbled titles
(~68 + ~48) remain as a documented, quantified residual. See
`docs/nxt-format.md` "Phase 2b".

### Phase 3 — Document boundaries & the citation index ✅ done
Two iterations before Phase 2b's fix — see `docs/nxt-format.md` "Phase 3"
and `scripts/nxt_build_index.py`. v1 indexed by decoding a window after
each `LPDD` marker (26,306 "documents", ~96% titled) until spot-checking
against the live statute site revealed `LPDD` doesn't reliably mark one
document (long sections span multiple pages as untitled continuations;
short sections can share a page with no `LPDD` between them). v2 dropped
`LPDD` and the decoder entirely for index-building, scanning the whole
file directly for literal `<title>` bytes instead (0.3s, 26,197 documents,
zero duplicate real-section citations, ~3.8% merge gap — closed by Phase
2b above). Settles the "is a random-access index needed" question: no,
linear scan is fast enough. Index saved to `data/fs2025_citation_index.json`.

### Phase 4 — Validation harness ✅ done
`scripts/nxt_validate.py` decodes a citation via the Phase 2/3 index,
fetches the live leg.state.fl.us page over plain HTTP (no tool dependency
-- a real, re-runnable regression check), and diffs the two using the
same class-name-based extraction on both sides. Ran against 5 sections
covering distinct edge cases (simple baseline, a `<table>`, heavy History
citations, cross-references, non-ASCII coordinates) -- see
`docs/nxt-format.md` "Phase 4" for full results and analysis. Headline
finding: all 5 sections showed some divergence, tracing back to the same
Phase 2b page-boundary-interruption mechanism now confirmed to also strike
*inside* documents that pass every existing index-quality check --
broader impact than the Phase 2b numbers alone suggested. One new,
distinct residual-gap category surfaced: **§ 145.11** is a real section
whose `<title>` *and* `SectionNumber` (the Phase 2b recovery path) both
failed to survive, a "double failure" the existing quality checks can't
detect. Not fixed -- this phase's job was to measure and characterize;
see Phase 2c below for the follow-up this motivates.

### Phase 2c — Investigate "double failure" section loss ✅ done
Built `scripts/nxt_find_gaps.py`: a third detection signal, independent of
both Phase 3 (title scan) and Phase 2b (SectionNumber recovery). Scans the
raw file for `fs2025.nxt`'s CatchlineIndex table-of-contents anchors
(`<a href="#!-- #ID=FS20250145.10 --#">145.10</a>`), which redundantly
encode each citation twice (the href target and the display text) --
requiring agreement between the two both filters out page-boundary
corruption and makes the signal a plain byte-level check with no
dependency on the decoder or index-builder. Result: 24,667 confirmed-clean
CatchlineIndex citations vs. 24,796 in the built index, with **95
confirmed double-failure gaps** (0.38%) -- real sections completely absent
from the index, the same category as § 145.11. Spot-checked § 105.08 and
found a distinct root cause from § 145.11 (title bytes fully intact but
"stolen" as the closing tag for a preceding corrupted title, rather than
destroyed outright) with the same net effect. Full list in
`data/fs2025_gap_report.json`. Not fixed -- measured and characterized, per
the same posture as Phase 4; see `docs/nxt-format.md` "Phase 2c" for full
writeup, including the fix approaches identified (tag-aware title
matching, or synthesizing index entries directly from the CatchlineIndex
scan).

### Phase 5 — Pipeline decision & write-up ✅ done
**Decision confirmed:** FLiberator decodes `.nxt` directly to HTML + a
JSON metadata sidecar (citation → offset/length, from the Phase 3/2b
index), never producing `.fff` and never depending on `folioxml`. The
tokenized-markup layer `.nxt` actually contains is close enough to literal
HTML (Phase 2) that the originally-planned FFF intermediate would have
added a conversion hop with no benefit. README.md and CLAUDE.md now state
this plainly instead of the original FFF/folioxml pipeline description;
`docs/nxt-format.md` carries the technical detail backing the decision.

### Phase 6 — Automate download + unzip ✅ done
`scripts/download.py` scrapes the leg.state.fl.us download page for its
current `FLLawDL<year>.zip` link (rather than hardcoding a year, so it
keeps working after the 2025 edition is superseded), downloads it into the
git-ignored `download/` folder, and extracts it there. Established the
three-way data-folder split now documented in CLAUDE.md:
- `FLLawDL2025/` stays exactly as it was — the frozen, read-only reference
  copy this whole project (Phases 1-4) was developed and validated
  against. Never written to.
- `download/` is the live target: `download/FLLawDL2025.zip` and
  `download/FLLawDL2025/Library/*.nxt`, laid out identically to the
  reference copy (the zip wraps everything in a top-level folder matching
  its own name, so extracting straight into `download/` reproduces that
  layout with no extra nesting).
- `output/` is reserved for decoded HTML/JSON output once Phase 9 decides
  its shape (created empty for now).

Ran end-to-end: downloaded the real 248,586,704-byte zip, extracted 1,352
files, and verified all 13 `Library/*.nxt` files are **byte-for-byte
identical** (SHA-256) to the frozen `FLLawDL2025/` reference copy — both
confirms the downloader works correctly and that Florida hasn't changed
the 2025 edition's data since the reference copy was made. Analysis
scripts (`nxt_decode_poc.py`, `nxt_build_index.py`, `nxt_validate.py`)
still default to reading `FLLawDL2025/` for now, since that's what they
were developed and checked against; pointing the real pipeline at
`download/` instead is part of Phase 7.

### Phase 7 — Promote scripts/ into the installable package ⬜ open
`src/fliberator/` is still just a scaffold (`__version__` only). Move the
decoder (`nxt_decode_poc.py`), index builder (`nxt_build_index.py`), and
eventually the downloader into real modules under `src/fliberator/`, add a
CLI entry point, and add unit tests (decoder opcode rules, index builder
against a small fixture) to replace ad hoc script runs.

### Phase 8 — Extend to the rest of the corpus ⬜ open
All work so far targets `fs2025.nxt` only. The other 12 `.nxt` files
(`flcnst2025.nxt` = FL Constitution, `uscon.nxt` = US Constitution, plus
various index/table files whose purpose is still guessed rather than
confirmed — see `docs/nxt-format.md`'s Corpus table) need the same
decode+index treatment, or an explicit decision that some of them (e.g.
the index files) aren't in scope for FLiberator's output.

### Phase 9 — Decide and implement the actual output shape ⬜ open
The "liberated" deliverable format has never been decided — one HTML file
per section? A single structured JSON/SQLite dataset keyed by citation?
Depends on Phase 4 (validated content) and Phase 7 (a real package to emit
it from). This is the phase that turns "we can decode this" into "here is
the liberated Florida Statutes."

## Tooling notes

- Pure Python (stdlib `struct`/regex) has been sufficient through Phase
  2b; no new runtime dependencies needed yet. If a future phase needs a
  real paging/record model (see the still-open Phase 2b residual gap),
  consider `construct` or a Kaitai Struct `.ksy` definition — Kaitai in
  particular is nice here because a `.ksy` file *is* the documentation and
  generates a visual structure browser, valuable for a format nobody else
  has documented.
- `cabextract`/`unshield` aren't installed; only worth adding if static
  analysis stalls on something Phases 1-3 haven't already solved and
  dynamic analysis (running the real NXT engine under Wine, extracted from
  `data1.cab`/`data2.cab`) becomes necessary. Still a fallback, not a
  starting point.
- Test-driven by construction: because ground truth is fetchable per-section from leg.state.fl.us on demand, every claim about the format should be checked against real reconstructed text, not just "the bytes look plausible." This is exactly what Phase 4 formalizes.

## Verification

- The Phase 4 harness (extract → strip tags → diff against live-fetched
  ground truth) is the end-to-end check, not yet built. Success criterion:
  a representative sample of `fs2025.nxt` sections (simple, table,
  amendment history, cross-references, non-ASCII), plus all articles of
  `uscon.nxt`, extract with text matching the live site (modulo
  whitespace/HTML-entity normalization).
- No existing test suite needs to change yet; this work still produces
  analysis scripts (not yet part of the `fliberator` package — see Phase
  7) plus the `docs/nxt-format.md` writeup.
