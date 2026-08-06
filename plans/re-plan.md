# Plan: Reverse-engineer the Folio NXT `.nxt` Infobase format

## Status

Phases 1, 2, 2b, 2c, 2d, 3, 4, 5, and 6 are **done**. Phase 5's pipeline
decision is settled: FLiberator decodes `.nxt` **directly to HTML + JSON**,
with no `.fff` intermediate and no dependency on `folioxml` — see
README.md and CLAUDE.md. Phase 4 (validation harness,
`scripts/nxt_validate.py`) found that content loss/corruption from the
Phase 2b paging-interruption mechanism is more widespread than previously
quantified — see docs/nxt-format.md "Phase 4" — which motivated Phase 2c.
Phase 2c (`scripts/nxt_find_gaps.py`) added a third, decoder-independent
detection signal, found 95 gaps caused by "closing-tag theft" (not true
data loss), patched it down to 28 in two passes, then closed the rest with
a v4 rewrite of `nxt_build_index.py`'s title-scan itself (tag-aware
matching, requiring an intact closing tag, plus a unified div-ownership
rule) — confirmed gaps now **0**. See docs/nxt-format.md "Phase 2c" for
the full history. Phase 2d (`scripts/nxt_depage.py`) then found the cause
underneath all of it: `fs2025.nxt` is a **paged store** (exactly
58,626 × 4096 bytes) whose documents are stored as chains of fragments
scattered across non-adjacent pages, and every phase before it had been
reading page headers and chain pointers as if they were content.
Reassembling the fragments first makes document boundaries exact instead
of inferred and eliminates the whole corruption class — see
docs/nxt-format.md "Phase 2d". Phase 6 (`scripts/download.py`)
established the `download/`/`output/` working-folder convention alongside
the frozen `FLLawDL2025/` reference copy — see CLAUDE.md "Working
conventions". Phases 7-9 (package promotion, rest-of-corpus, output
format) are scoped but not started.

**Since then**: Phase 2e accounted for every skipped byte and fixed two
shipping defects; Phase 4b closed the three verification gaps (nothing is
missing, the 1,440 non-section documents are validated, markup fidelity
measured); Phase 8a (`scripts/nxt_corpus_triage.py`) took both layers
across all 13 files — they all reassemble, 12 of 13 decode to well-formed
HTML, and every file is now identified from its content rather than its
filename; and Phase 4c (`scripts/nxt_check_output.py`) closed the
whitespace blind spot by checking the decoder against the source bytes
rather than the live site. The paragraph below is superseded on two
points: the `\x15` vocabulary is now decoded, and the other 12 files are
no longer untouched.

**Known content gaps, as of Phase 2d**: on `fs2025.nxt`, none are known.
All 26,306 reassembled documents carry exactly one intact title and at
most one Section div; title vs. `SectionNumber` disagreements, duplicate
titles, garbled titles and confirmed index gaps are all **0**; and the
three independent completeness signals (Section divs, index titles,
CatchlineIndex anchors) agree exactly at 24,866 sections with zero
corrupt anchors. A 200-section random sample validated against the live
site scores 100% at/above the 0.99 threshold and 96% byte-exact, with
every non-exact case traced to a footnote-marker notation difference
(`[1]` vs. a stripped superscript) rather than to missing content — the
mid-body content loss that had been open since Phase 2b is gone, not
merely smaller. What remains open: the `\x15` opcode vocabulary (cosmetic,
no known loss), and the other 12 `.nxt` files, still entirely untouched
(Phase 8) — nothing yet confirms the reassembly generalizes beyond
`fs2025.nxt`.

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
(~68 + ~48) remained as a documented, quantified residual at the time --
superseded by Phase 2c's v4 rewrite, which eliminated garbled titles
entirely and cut duplicates to 1. See `docs/nxt-format.md` "Phase 2b".
The "not worth modeling" call above was wrong: Phase 2d modelled it, in
0.6s and ~150 lines, and doing so removed this whole failure class at the
source rather than compensating for it downstream.

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
Footnote worth keeping: v1's document *count* — 26,306, straight from the
`LPDD` markers — was correct all along, as Phase 2d's reassembly confirms
independently. What v1 got wrong was assuming those documents were laid
out contiguously in file order; v2-v4's increasingly elaborate title
scans were all attempts to work around that one wrong assumption, and v5
discards them.

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
confirmed gaps** (0.38%) -- real sections completely absent from the
index. Root cause, confirmed by hand on three cases (§ 105.08, § 15.16,
§ 44.404): "closing-tag theft," where a *neighboring* document's own
closing tag was destroyed by page-boundary interruption, so the title-scan
regex's non-greedy match swallows forward and steals the target's closing
tag instead, merging both into one entry filed under the neighbor's title.
For § 15.16 specifically, confirmed the merged entry's own `SectionNumber`
is "15.16," not the neighbor's title -- meaning the real content isn't
lost, just mislabeled, a more fixable failure mode than assumed. Also
found (and corrected, see below): document *body* order in the file does
not follow statutory section-number order -- only the CatchlineIndex does
-- so "the preceding title in the file" and "the statutorily preceding
section" are different things. Separately, confirmed the "garbage" bytes
in at least the theft cases are not random: they decode as a real LPDD
page number elsewhere in the file (verified exactly, byte-for-byte, in two
independent cases), though their exact purpose is still unconfirmed.
**Correction:** § 145.11, the case that originally motivated this phase,
turned out to be a misdiagnosis -- it's cleanly indexed with no corruption;
the original claim came from a raw substring search that didn't account
for the standard per-token opcode always embedded before `</title>`. The
95-gap count and its cause are otherwise unaffected (145.11 isn't among
them).

**Fixed, in three passes -- the third closes it completely.** Checked all
95 gaps for recoverability first: every one had its own `SectionNumber`
findable inside an existing (mislabeled) entry -- 100%, no genuine
destruction cases among them. Pass 1, `fix_mismatched_titles`: compare
each entry's title against its own first Section div's `SectionNumber`,
relabel on mismatch (149 entries retitled, 95 → 41 gaps). Spot-checking
one recovery (F.S. 39.0142) against the live site surfaced a second
pattern: chapter 39 alone has 13 entries all literally titled
`CHAPTER 39` (real, distinct Part Index documents that share generic
title text -- not a bug), and one of them had swallowed F.S. 39.0143 the
same way, invisible to pass 1 because CHAPTER/Preface entries were
deliberately excluded from relabeling. Pass 2 extended
`find_orphaned_sections` to also orphan the first div in CHAPTER/Preface
spans specifically (63 more sections recovered, 41 → 28 gaps).

Pass 3 (v4) fixed the actual root cause instead of patching around it
again: v2's title-scan regex, `<title>(.*?)</title>`, is unbounded, so
when a title's own closing tag is destroyed the non-greedy match doesn't
fail -- it swallows forward past the corruption for the next `</title>`
it can find, which is the theft mechanism itself. Every clean title's
citation text is immediately followed by the exact opcode sequence
`\x13\x37\x08</title>` (`"</title>"` is always exactly 8 bytes); the
rewritten `TITLE_RE` requires that sequence immediately after a *bounded*
run of title text (an 80-byte cap), so a destroyed closer simply fails to
match at all -- no entry, no swallowing, no mislabeling. Paired with a
unified ownership rule in `find_orphaned_sections` (only the *first* div
in a span can be silently owned, and only if its number matches the
title). That rule change also surfaced a second non-contiguity fact:
title tags and their own Section div aren't always physically adjacent
(F.S. 175.341's title sits before F.S. 175.333's *entire* body, which
sits before 175.341's own body) -- an earlier "match anywhere in the
span" draft of the rule corrupted length assignment on exactly that case,
fixed by restricting ownership to the first div, unconditionally.

**Result:** confirmed gaps **28 → 0**. 1,204 sections recovered via
SectionNumber (up from 1,045), 26,428 total documents, 0 garbled titles,
1 unexplained duplicate remaining (`F.S. 559.921`). Runtime unchanged at
0.7s (still one linear regex pass). Spot-checked nine citations against
the live site and re-ran the Phase 4 validation harness -- content
fidelity unaffected, confirming this was purely an index-boundary fix.
See `docs/nxt-format.md` "Phase 2c" for the full writeup.

### Phase 2d — Undo the paged storage layer ✅ done
Phases 2b and 2c both ended at the same wall: an interruption mechanism
that could be worked around at the index level but not explained, and a
resulting mid-body content loss written off as "a real paging model, not
a single missing opcode rule -- not worth solving." That verdict was
wrong, and cheaply so. `fs2025.nxt` is exactly 58,626 × 4096 bytes: a
**paged store**, with a typed header on every page.

`scripts/nxt_depage.py` parses that structure — page type, slot
directory, and the chain pointers that link a document's fragments — and
reassembles documents before anything else looks at them. Only page type
5 carries document text (37,606 of 58,626 pages); the rest is
search-index machinery. Documents are stored as chains of fragments
scattered across non-adjacent pages and interleaved with unrelated
documents, linked by backwards `(page, reverse-fragment-index)` pointers.
The bytes earlier phases saw as "garbage interrupting a title" are those
pointers.

**Result:** the corruption class disappears rather than shrinking.
37,435 chain edges resolve with **zero** conflicts; 26,306 documents
reassemble, 100% with exactly one intact `<title>`, 100% ending in
`</html>`, at most one Section div each, and **0** title-vs-
`SectionNumber` disagreements. Three independent completeness signals
agree exactly at 24,866 sections, with zero CatchlineIndex anchors
discarded as corrupt (previously some always were). The `F.S. 559.921`
"duplicate" turned out never to have been duplicated. A 200-section
random sample against the live site scores **100% ≥ 0.99, 96%
byte-exact**, and the previously-failing citations (15.16, 44.404) are
now exact. This made `nxt_build_index.py` v5 almost trivial — the
DOCTYPE lookback, orphan recovery, stub dedup and ownership rule all had
nothing left to do and were deleted. Reassembly takes 0.6s.
See `docs/nxt-format.md` "Phase 2d" for the format details.

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

### Remaining work, after Phase 2e — items 1-4, 6 ✅ done; 5, 7 ⬜ open

**Item 4 is done** (Phase 8a): the page/fragment model is a property of
the container, not of `fs2025.nxt` — all 13 files reassemble cleanly, and
running the corpus caught a decoder defect that `fs2025.nxt` alone never
could have surfaced. Details in item 4 below.

**Items 1, 2 and 3 are done** (Phase 4b — see `docs/nxt-format.md`):
nothing is missing (all 26,306 `LPDD` markers are in content pages, every
fragment is reachable, the fragment tiling covers every byte, and `0x1BC`
is a bookkeeping counter, now trivia); the 1,440 non-section documents are
validated (chapter TOCs 120/120 exact, Part TOCs 120/120 exact, all 47
SubPart headings verbatim in the live Part pages, and no statute section
is among them); and markup fidelity is measured (99.46% of live elements
align exactly, **0 live elements and 0 link targets missing** once the
site's own `<span>`→`<p>` rewrite is accounted for). **Item 6 is done**
(Phase 4c): the whitespace blind spot is closed by checking the decoder
against the source bytes, which found 62 doubled ampersands the live-site
harness had scored as passing. Items 5 and 7 remain open.


Phase 2e's opcode tally closed the last genuinely *unknown* thing about
`fs2025.nxt`'s content layer — every byte is now accounted for. What's
left that matters is verification not yet done and decisions not yet
made, which is different work and worth keeping separate from the
reverse-engineering phases above. In the order they should be tackled:

1. **The `0x1BC` count says 26,348; we find 26,306.** (item 3 in the
   ordering below, but do it first — cheapest, and the only candidate for
   a real completeness hole.) A 42-document discrepancy against a count
   that is now exact. This is the one completeness question the
   three-signal agreement *cannot* answer: all three signals derive from
   documents already found, so 42 unreachable documents would be
   invisible to every one of them.
2. **The 1,440 documents with no Section div have never been validated.**
   All fidelity work to date is section-based, against the 24,866
   documents that have one. Prefaces, `CHAPTER n` pages and Part Indexes
   — 5.5% of the corpus — have zero fidelity evidence of any kind, and
   nobody has confirmed all 1,440 are legitimately structural rather than
   something broken.
3. **Attribute- and entity-level HTML fidelity is unmeasured.** Every
   fidelity number in this project strips all tags before comparing, and
   the Phase 2e structural check verified nesting only. `href` values,
   `class` names, `colspan`, entity correctness — never checked against
   the live site. Both defects found in Phase 2e hid in exactly this
   blind spot, and this is the deliverable itself.
4. ~~**Does the page/fragment model generalize?**~~ ✅ **done** (Phase 8a
   — see `docs/nxt-format.md`). Yes: all 13 files reassemble with zero
   chain conflicts, 45,520 documents total, and 12 of 13 decode to
   well-formed HTML (0 unclosed, 0 mismatched) — the 13th is a PDF
   payload. Every file is now identified from its decoded content rather
   than its filename, which corrected several wrong guesses. Worth having
   done for its own sake: the corpus exposed a decoder defect
   `fs2025.nxt` structurally could not reveal — the `0x15 0x04 0x01 <id>`
   field marker had only ever been seen with non-printable ids, so ids
   `0x4d`/`0x4e` leaked 39,200 stray `M`/`N` characters into 10 files.
   Fixed and re-validated (40/40 sections, no regression).
5. **The `[n]` footnote-marker representation is undecided.** Not an
   unknown: the source encodes a literal `[1]`, leg.state.fl.us renders a
   superscript. It is the only remaining difference in the 200-section
   sample (~4% of it). Which representation the output should use is a
   Phase 9 call. Open sub-question: whether a 200-section sample is large
   enough to have surfaced every editorial notation of this kind, or just
   the most common one.
6. ~~**Some output defects the harness structurally cannot see.**~~ ✅
   **done** (Phase 4c — see `docs/nxt-format.md`).
   `scripts/nxt_check_output.py` closes this by checking the decoder
   against the *source bytes* instead of the live page, asserting four
   invariants: every doubled-character marker is claimed, no character
   sits beside its own entity form, every source byte is consumed exactly
   once, and a whitespace census is recorded as a baseline. It
   immediately found the residual 62 markers Phase 2e's byte-width proxy
   had rejected — a literal `&` paired with `&amp;`, shipping `AT&&T` and
   `Child && Dependent` across 25 documents. Replaced the proxy with the
   real invariant (literal and entity must decode to the same character);
   coverage is now 385,305/385,305 corpus-wide with 0 adjacent
   duplicates, and byte accounting reports 0 gaps and 0 overlaps.
7. **Page geometry has only ever been tested on one file from one year.**
   The pipeline is meant to re-run against a fresh download annually.
   This needs no research — it needs `nxt_depage.py` to assert its
   assumptions and fail loudly rather than silently reassembling garbage
   if a future edition differs.

**Closed as trivia** (understood well enough, or irrelevant to the
deliverable — recorded so they stop being re-litigated): the
checksum-shaped fields at `0x11E`/`0x1AE` and page offset 2; the 8-byte
ID at `0x100` (a file hash serves the one real use); the physical
storage order of documents; `data1.cab`/`data2.cab`; the internals of the
21,020 search-index pages (only relevant if reproducing Folio's
full-text search, which FLiberator doesn't do); the exact meaning of
`\x08`; the 62 non-conforming `\x15\x01\x01\x01` runs; the single record
not ending in `</html>`; and the lone `Obsolete Cross-reference` title.

### Phase 7 — Promote scripts/ into the installable package ⬜ open
`src/fliberator/` is still just a scaffold (`__version__` only). Move the
decoder (`nxt_decode_poc.py`), index builder (`nxt_build_index.py`), and
eventually the downloader into real modules under `src/fliberator/`, add a
CLI entry point, and add unit tests (decoder opcode rules, index builder
against a small fixture) to replace ad hoc script runs.

### Phase 8 — Extend to the rest of the corpus 🟡 triage done, scope open
**Phase 8a (done)** answered the structural half: all 13 files reassemble
and decode cleanly, and every one is now identified from its decoded
content rather than a filename guess (`scripts/nxt_corpus_triage.py`,
write-up in `docs/nxt-format.md`). Four files hold primary law —
`fs2025.nxt` (26,306 docs), `lf2025.nxt` (255 session-law chapters),
`flcnst2025.nxt` (226) and `uscon.nxt` (2) — and the remaining eight
markup files are finding aids derived from it (subject/definition/
constitution indexes, cross-reference and tracing tables); the 13th is a
help PDF.

**Still open:** the per-file work those four need beyond reassembly —
citation indexes of their own (`nxt_build_index.py` is `F.S. n`-specific),
and validation against ground truth, which for `lf2025`/`flcnst2025`
means a different URL scheme than `nxt_validate.py`'s. And the scope
call: whether the eight finding-aid files are part of FLiberator's
output at all, or whether "liberate the statutes" stops at primary law.
That is a Phase 9 decision, but it is now a decision over a known list.

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

- The Phase 4 harness (`scripts/nxt_validate.py`: extract → strip tags →
  diff against live-fetched ground truth) is built and re-runnable. As of
  Phase 2d it also takes `--sample N [seed]` for a reproducible random
  sample, caching the fetched ground truth under `data/live_cache/`
  (git-ignored) so it stays cheap to re-run as a regression gate. Current
  result on `fs2025.nxt`: 200 random sections, 100% at/above the 0.99
  threshold, 96% byte-exact, mean ratio 0.99993, and every non-exact case
  attributable to footnote-marker notation rather than missing content.
  That is a statistical result on a random sample, not an exhaustive
  proof — and it covers only `fs2025.nxt`; `uscon.nxt` and the other 11
  files have not been run at all (Phase 8).
- `scripts/nxt_find_gaps.py` is the complementary index-completeness
  check (CatchlineIndex cross-reference, independent of the decoder) --
  this one *is* exhaustive over `fs2025.nxt`'s citations, currently 0
  confirmed gaps.
- No existing test suite needs to change yet; this work still produces
  analysis scripts (not yet part of the `fliberator` package — see Phase
  7) plus the `docs/nxt-format.md` writeup.
