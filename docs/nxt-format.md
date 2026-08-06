# Folio NXT `.nxt` Infobase format — working notes

Living notes from reverse-engineering the `.nxt` files in `FLLawDL2025/Library/`.
See `plans/re-plan.md` for the analysis plan these notes track against.
Everything here is derived from the 13 `.nxt` files in this repo's (git-ignored)
`FLLawDL2025/Library/` folder plus the live statute text at leg.state.fl.us —
re-run `scripts/nxt_survey.py` to regenerate the raw data behind this doc.

**Pipeline decision (settled, plan Phase 5):** FLiberator decodes `.nxt`
**directly to HTML + a JSON metadata sidecar**. The originally-planned
Folio Flat File (`.fff`) intermediate and the [`folioxml`](https://github.com/imazen/folioxml)
converter are not used. This is a direct consequence of the Phase 2
finding below: `.nxt`'s content layer is a thin opcode wrapper around what
is otherwise ordinary, literal HTML text — decoding it is a "decompress
the tokens back to text" problem, not a format-conversion problem, so
routing through an intermediate format would have added a hop with no
benefit. See README.md and CLAUDE.md for the user-facing statement of this
decision.

## Corpus

> **Superseded in part by Phase 8a** (below), which identifies every file from
> its decoded content rather than its filename. Several "likely …" guesses in
> this table are wrong — notably `conndx2025.nxt`, which is the **Florida
> Constitution** index, not a "connection index." Kept here as written for
> history; see the Phase 8a table for what each file actually holds.

| file | size | notes |
|---|---|---|
| `uscon.nxt` | 319,488 | US Constitution. Older build (copyright range ends 2018). Best small test target. |
| `sct2025.nxt` | 528,384 | |
| `TT2025.nxt` | 864,256 | |
| `conndx2025.nxt` | 1,085,440 | "conn[ection] ndx" — likely a cross-reference/connection index |
| `flcnst2025.nxt` | 1,773,568 | Florida Constitution |
| `lndx2025.nxt` | 2,809,856 | likely a name/location index |
| `rtt2025.nxt` | 4,812,800 | |
| `Law_Download_Help_PDF.nxt` | 8,413,184 | a PDF wrapped in the Infobase container (0x1BC record-count field = 2) |
| `xrt2025.nxt` | 12,562,432 | alphabetical `<CATCHLINE>`-tagged keyword/catchline index (confirmed — see below) |
| `defx2025.nxt` | 19,243,008 | "def[inition] x[index]" — likely a definitions/term index |
| `lf2025.nxt` | 26,951,680 | |
| `stin2025.nxt` | 52,326,400 | |
| `fs2025.nxt` | 240,132,096 | **2025 Florida Statutes — the main target** |

## Container header (bytes `0x00`–`0x1FF`)

Confirmed identical structure across all 13 files (ran `scripts/nxt_survey.py`
over the full corpus, not just a couple of samples). Fields:

| offset | contents | behavior across corpus |
|---|---|---|
| `0x00`–`0x4C` | ASCII: `Copyright (c) 1991-20XX, Rocket Software, Inc.  All Rights Reserved. Infobase\0\r\n` | year-range end varies (`2018` for `uscon.nxt`, `2024` for every 2025-vintage file) |
| `0x4D`–`0xDF` | zero-padded | constant |
| `0xE0`–`0xE1` | `04 00` | constant, all files |
| `0xE2` | `2d` (uscon) or `2f` (every 2025-dated file) | **tracks the copyright end-year**, not per-file — likely an infobase/build sub-version, not a document count |
| `0xE3`–`0xE7` | zero | constant |
| `0xE8`–`0xEF` | `fc ae 56 89 62 74 bf ae` | **identical in all 13 files** — format magic/constant |
| `0xF0`–`0xFD` | zero | constant |
| `0xFE`–`0xFF` | `90 32` (uscon) or `7e 39` (every 2025-dated file) | tracks the same grouping as `0xE2` — a build/library identifier shared by everything compiled into this "Library" (see `Library.libinst`/`2025CD.libdef`), not per-file |
| `0x100`–`0x107` | 8 bytes, unique per file | last 2 bytes are `be 18` in **every** file; bytes 5–6 cluster around `66`/`67` for the 2025 batch. Looks like a per-file hash or ID with a shared high-order "epoch" — unconfirmed, possibly time-derived |
| `0x108`–`0x10B` | zero | constant |
| `0x10C`–`0x10F` | `01 00 00 80` | constant, all files — likely a flags word |
| `0x110`–`0x11D` | zero | constant |
| `0x11E`–`0x11F` | 2 bytes, unique per file, no obvious correlation with size | possibly a checksum |
| `0x150`–`0x151` | `03 04` | constant, all files |
| `0x180`–`0x181` | `00 04` | constant, all files |
| `0x1AE`–`0x1AF` | 2 bytes, unique per file | another possible checksum, distinct from the one at `0x11E` |
| `0x1B0` (uint32 LE) | **`2`** | constant across all 13 files — likely a format major version |
| `0x1B4` (uint32 LE) | varies, range 39–67, **not** correlated with file size (e.g. `sct2025.nxt` @ 528KB and `rtt2025.nxt` @ 4.8MB both = 49) | hypothesis: count of defined fields/index columns for this infobase (Folio infobases have a configurable field schema — Title, Text, Citation, Date, etc.) |
| `0x1B8` (uint32 LE) | **`1`** | constant across all 13 files |
| `0x1BC` (uint32 LE) | varies, strongly tracks content volume: `uscon`=3, `sct2025`=13, `TT2025`=218, `rtt2025`=22, `Law_Download_Help_PDF`=2, `xrt2025`=625, `defx2025`=12723, `stin2025`=3810, **`fs2025`=26348** | Originally read as "document count" on the strength of `fs2025`'s value nearly matching an early index-building result. **Revised in Phase 3**: the actual, carefully-verified document count for `fs2025.nxt` is 26,197 (§ Phase 3 below), not 26,348 — the earlier near-match was coincidental. More likely this counts storage pages/records, a related but distinct quantity. Still clearly tracks content volume either way. |
| `0x1C0`+ | zero (at least through `0x200`) | |

Regenerate this table with `uv run python scripts/nxt_survey.py` (dumps all of
the above for every file, plus a byte-frequency histogram).

## Content layer: tokenized markup

Confirmed by locating real statute text (§ 1.01 "Definitions", fetched live
from leg.state.fl.us as ground truth) inside `fs2025.nxt` at byte offsets
~70,800 and ~106,300:

```
<div class="CatchlineIndex"><div class="IndexItem">\x15\x04\x01\x05\x13\x37%<a href="#!-- #ID=FS20250001.01 --#">\x081.01\x13\x37\x04</a>...
...<div class="Catchline">\x08Definitions.\x13\x37#</div></div>...
...<span class="Text Intro Justify">\x08Crude turpentine gum (oleoresin)...
```

Initial opcode hypotheses, formed from this small eyeballed sample before
Phase 2 confirmed things programmatically across thousands of instances
(kept here for the record; see "Phase 2" below for what actually held up):

- **`\x13 <len> <len bytes>`** — opens a markup token. **Held up** — this is
  exactly rule 1 of the Phase 2 decoder below (refined to a 2-byte subtype +
  length framing).
- **`\x08`** — guessed as "precedes a literal text run." **Wrong** — Phase 2
  found real text appears completely unprefixed just as often; `\x08` isn't
  a dedicated text opcode at all, just a byte that happens to often sit near
  one.
- **`\x15 <bytes>`** — short field, possibly paragraph/style marker or
  special-character escape (one instance carried a literal UTF-8 EM SPACE
  character, `\xe2\x80\x83`, immediately after it). **Still unconfirmed** —
  never fully decoded; current decoder just skips it byte-by-byte via the
  generic unknown-opcode fallback (harmless for text extraction, since the
  em-space's HTML-entity twin `&#x2003;` is emitted anyway via rule 1).

Also confirmed: `xrt2025.nxt` (and likely `defx2025.nxt`) use the same
tokenized-markup scheme for a completely different kind of content — an
alphabetically-sorted **keyword/catchline index**, using a literal
`<CATCHLINE>...` pseudo-tag around thousands of statute catchlines (e.g.
`<CATCHLINE>Conversion of existing corporations.`). This means the opcode
grammar is shared across all files in the product family, not `fs2025.nxt`-specific
— useful, since `uscon.nxt` and `xrt2025.nxt` are much smaller test targets to
iterate the decoder against before trusting it on the 240MB main file.

Per-section anchor IDs are embedded literally in the text, e.g.
`#!-- #ID=FS20250001.01 --#`, directly encoding year + chapter + section.
This is the leading candidate for a citation → byte-offset index (Phase 3 of
the plan).

## Phase 2: decoder for the tokenized-markup layer

`scripts/nxt_decode_poc.py` decodes the content layer using two rules:

1. **`\x13 <subtype:1> <len> <text>`** — length-prefixed literal text.
   `<subtype>` varies (`0x37` for markup tags, `0x39` for HTML numeric
   entities like `&#x2003;`) but the framing is identical either way, so the
   decoder treats it as opaque. `<len>` is 1 byte normally; if its high bit
   is set, it's a 2-byte big-endian length instead:
   `((b1 & 0x7F) << 8) | b2` (confirmed against a 239-byte
   `<!DOCTYPE...><meta.../>` run — this was the earlier decoder's biggest
   source of mangled boilerplate, since most `<head>` tags exceed 255 bytes).
2. **Printable/UTF-8 runs are sniffed at every byte position**, not just
   after a specific opcode. Earlier hypotheses treated `0x08` as "the text
   opcode," but that's wrong: plenty of real text (e.g. `Definitions.`
   inside `<CATCHLINE>Definitions.</CATCHLINE>`, and `Justify` inside a
   `class="Text Intro Justify"` attribute) appears **completely unprefixed**,
   with no `0x08` in front of it at all. The old decoder was silently
   dropping this text because its fallback path didn't check printability.
   `0x08` isn't a dedicated text opcode — it's just one more byte that
   happens to often sit right before a text run.
3. Anything else `< 0x20` and not part of rule 1 is an unrecognized opcode,
   skipped one byte at a time (deliberately dumb, so decoding degrades
   instead of halting on an incomplete opcode table).

With these three rules, the decoder extracts the **complete, verbatim body
text of § 1.01** from `fs2025.nxt` — all 19 numbered definitions and the 9
lettered wartime-service periods in subsection (14) — matching the live
leg.state.fl.us page word-for-word, plus a bonus the plain web page doesn't
show: a `<HISTORY>` block of session-law citation anchors (`LAW90-092`,
`LAW92-080`, ... `LAW2024-147`). See `scripts/sample_output_1.01.txt`.

It also generalizes to a **completely different document era**: run against
`uscon.nxt` (copyright range ends 2018 vs. 2024 — an older Folio build, using
plain `<P CLASS="ARTICLE">`/`<A NAME="...">` markup instead of `fs2025.nxt`'s
XHTML `<div>`/`<span>` style), the same two rules — no format-specific
logic — correctly extract the Constitution's preamble and Article I verbatim
("We the People of the United States, in Order to form a more perfect
Union..."). See `scripts/sample_output_uscon.txt`. `uscon.nxt` only has 2
`LPDD` markers total (one real content document covering the whole
Constitution, then a second one that's mostly binary index data — the
`0x1BC` header field being `3` for this file evidently isn't "3 LPDD
documents"; likely a different count, e.g. top-level records or fields).

This was the result that settled the project's pipeline shape (see the
pipeline decision note at the top of this document, and `plans/re-plan.md`
Phase 5): `.nxt` decodes **directly to HTML (+ a JSON metadata sidecar)**,
without ever producing `.fff` or running it through `folioxml`.
Text-content extraction is solid across two different document eras;
what's left rough is decorative markup and a handful of still-uncatalogued
short opcodes.

### New structure found: per-document manifest block

Immediately before each document's `LPDD`-prefixed HTML body, there's a
manifest/nav block listing sibling document IDs with a descending counter
(`FS20250001.02` counter=7, `FS20250001.015` counter=6, `FS20250001.01`
counter=5, ...), plus for the current document: its own ID, a filename
(`0001.015.html`-style), encoding (`utf-8`), content-type (`text/html`), and
a **generation timestamp** (`2025-08-31 17:02:13 UTC` — i.e. this is when
Rocket's tooling built this particular `.nxt`, not a statute date). Not yet
fully parsed field-by-field, but the sibling-ID list is a second candidate
(besides the TOC anchors from Phase 1) for building the citation → offset
index in Phase 3. The same `\xff\xff\xff\xff\x01\x00\x16\x00\x16...` byte
signature that opens this manifest block was also found to recur **inline,
mid-document** (see below) — so it's a generic embedded-record marker, not
something confined to document headers.

### Chased down: the character-formatting toggle

The stray digit leaks (`"0"` around `<CATCHLINE>`, `"9"` near an EM SPACE)
traced back to one specific, now-fully-resolved opcode:

**`0x10 <0|1> 0x03 0x82 <style-id> 0x01`** — a paired open/close
character-formatting toggle, redundant with the literal `<B>`/`<I>`/`<TITLE>`
tags it wraps (e.g. `10 00 03 82 3a 01` before `<TITLE>`, `10 00 03 82 3e 01`
before `<B>`, `10 01 03 82 3e 01` after `</B>`). Verified against 1,936
instances in the first 3MB of `fs2025.nxt`: `<0|1>` splits evenly (970 open /
966 close), and `<style-id>` is a small per-style integer that happens to
land in printable ASCII range often enough (`:`, `>`, `@`, `'0'`, `'6'`...)
to fool a printable-byte sniffer into treating it as leaked content. The
decoder now matches this 6-byte shape explicitly and discards it whole,
which fixed more than the stray digits — it also **recovered previously-lost
content that shared the same root cause**: the `<title>` tag was empty
before (now correctly `F.S. 1.01`), and the `<HISTORY>` section's citation
links were empty `<a href="...">` before (now contain their visible text,
e.g. `<a href="#!-- #ID=LAW90-092 --#">90-92</a>`) — both were unprefixed
text sitting right after one of these toggle blocks, which the old decoder's
byte-by-byte unknown-skip was eating alongside the block itself.

Not present at all in `uscon.nxt` (0 matches) — consistent with that file's
older, non-XHTML tag vocabulary (`<P CLASS="...">` instead of `<span>`based
character styling), so this opcode is likely specific to the newer render
pipeline. No regression there either; output is byte-for-byte identical to
before this fix.

### Remaining known gap (diagnosed, not resolved — low value)

One isolated spot mid-§1.01 (inside item (f)'s `class="Text Intro Justify"`
attribute) still decodes with ~10 bytes of garbage before `Justify">`. Traced
to a distinct 34-byte embedded record sharing the per-document manifest
block's signature (`\xff\xff\xff\xff\x01\x00\x16\x00\x16...`) but with a
different flag byte (`\xe0` here vs. `\xc0` in document headers) — plausibly
an editorial revision/edit-tracking stamp left behind by Rocket's authoring
tool. This affects a single decorative CSS class name, once, in the whole
file; the substantive statute text on both sides of it is unaffected. Not
worth chasing further unless it turns out to recur densely elsewhere.

The redundant-looking `<EM SPACE char> + &#x2003;` sequence appearing after
every subsection/item number (e.g. `(1)` then both a literal Unicode EM
SPACE and the equivalent HTML entity) was checked against multiple instances
and is consistently present — a real feature of the format (probably: raw
character for full-text search indexing, entity for guaranteed-correct
rendering), not a decoder artifact.

## Phase 3: citation → byte-offset index

### v1 (superseded): decode a window after each `LPDD`

First working version decoded a bounded window right after each `LPDD`
marker and read its `<title>` tag. Ran against the full `fs2025.nxt`: 3.2
seconds, 26,306 "documents" found — which matched the `0x1BC` header field's
predicted count (`26,348`, Phase 1) to within 0.2% and looked like a strong
confirmation. **It wasn't** (see below) — the closeness of that match was
coincidental. ~4% of entries had no extractable title.

### The bug this hid, and how it was found

Picked one of the ~4% "untitled" entries to show as an example (a 12,286-byte
span). It decoded as real, readable statute text — but jumbled: what looked
like the tail of one section's grounds-for-discipline list, followed
abruptly by a fragment about repeat license revocations, followed by a
*complete second document* (§ 626.631, with its own working `<title>`)
embedded mid-stream. Initial read: byte-level corruption in the source file.
**Wrong** — flagged by cross-checking against the actual live statute text
and the chapter's table of contents: the "jumbled" text was in fact the
complete, correctly-ordered text of **§ 626.6215** verbatim, and § 626.6215
→ § 626.631 really are sequential neighbors in the chapter, no jump at all.

The real mechanism, confirmed by checking title-entry length distribution
across the whole index: lengths cluster tightly around **exact multiples of
4096 bytes** (4096, 8192, 12288, 16384...). `LPDD` doesn't mark "one
document" — it marks something closer to a storage page. Most sections fit
in one page (why the v1 heuristic worked ~96% of the time), but § 626.6215
is long enough to spill across page boundaries as a **continuation with no
title of its own** — not corruption, just not a new document. And in the
other direction, § 626.631 turned out to start **mid-page**, immediately
after § 626.6215's content ends, with no fresh `LPDD` before it at all —
so a page can also hold more than one complete document back-to-back. Given
both failure modes, indexing by `LPDD` boundaries was the wrong foundation
regardless of how the per-page title extraction was implemented.

### v2 (current): scan the whole file for literal `<title>` bytes

Key fact that unlocks a much simpler design: `<title>`/`</title>` text is
stored as literal, undamaged bytes even in cases (like § 626.631) where the
DOCTYPE/meta preamble around it is garbled — confirmed by finding
`F.S. 626.631` sitting in the raw file completely intact despite the broken
head around it. So `scripts/nxt_build_index.py` v2 drops `LPDD` and the
Phase 2 decoder entirely for index-building: a single regex pass finds every
literal `<title>...</title>` / `<TITLE>...</TITLE>` occurrence in the whole
file (every one immediately preceded by a 3-byte `\x13\x37<len>` opcode,
confirmed with zero exceptions across a 2,000-sample check), and each
match's position becomes a document boundary. A document's length is simply
"distance to the next document's start" — which is what makes multi-page
sections come out with their correct full length automatically, with no
need to understand paging at all.

Run against the full `fs2025.nxt`: **0.3 seconds** (faster than v1, since
there's no per-document decode call anymore), **26,197 documents**. Verified
directly: § 626.6215 now gets its own entry with the correct full length
(9,104 bytes, up from v1's truncated 4,098) and decodes cleanly end-to-end
matching the live statute text; § 626.631 — previously missing from the
index entirely — now gets its own correct entry too.

Quality checks on v2:
- **Zero duplicate citations among real sections** (same as v1) — all
  duplicate titles are `CHAPTER N` part-boundary headers.
- **~3.8% of entries (991 of 26,197) still show signs of holding more than
  one document** (checked via counting `class="Section"` occurrences per
  entry's raw span — a real document body marker that should appear exactly
  once). Same root cause as the original ~4% gap: in a small number of
  cases the `<title>` tag itself, not just its surrounding preamble, hits
  the still-unresolved `\x13\x37` length-desync issue and doesn't survive as
  literal text, so that document is silently swallowed into the *previous*
  entry's span instead of getting its own. This is meaningfully better than
  v1 (documents are lost, not mislabeled — no more phantom "untitled"
  entries, and the swallowed content is still present, just under the wrong
  citation) but not eliminated. Chasing the remaining ~4% further means
  going back into Phase 2 opcode archaeology, not index-building — left as a
  documented, quantified gap.
- **One expected, benign edge case:** the last document's stated length
  balloons to ~73MB because there's no further title to bound it — the tail
  of the file past the last real document is non-HTML binary index data
  (compiled search structures), not more documents. Not fixed; just don't
  trust the very last index entry's `length`.

This still settles the plan's Phase 3 open question ("is there a true
random-access index, or is a linear scan good enough") in favor of linear
scan — 0.3 seconds for the full file leaves no performance reason to keep
looking for a binary offset table. It also means the Phase 1 cross-check
("26,306 found vs. `0x1BC`'s predicted 26,348") should be discounted: with
v2's more accurate 26,197, `0x1BC` likely counts storage pages, not logical
documents — the earlier near-match was coincidental, not a confirmation.

### Phase 2b: the 3.8% merge gap, fixed (index-level, not decoder-level)

The initial hypothesis (single unrecognized "boilerplate back-reference"
opcode) didn't survive a wider sample. Bucketing all 991 flagged entries'
boundary bytes by shape surfaced two different phenomena:

1. **Real `LPDD` page markers, spliced mid-token.** Some boundaries contain
   the literal ASCII `LPDD` plus a recognizable fixed-ish binary structure
   (page number, `0xffffffff` neighbor-pointer fields, etc.) — this is the
   same 4KB-page marker from the Phase 3 v1 story, just appearing *inside*
   a document instead of between them. Worse: it can interrupt a literal
   text run mid-flight, not just between tokens. Concrete example (`F.S.
   7.08`'s entry): a `\x13\x37<len=239>` token for the standard
   `<!DOCTYPE...>` preamble gets cut off after only ~29 of its 239 declared
   bytes by a second, different 6-byte marker, and what resumes afterward
   is unrelated body text from a completely different document (a
   metes-and-bounds boundary description). This means length-prefixed
   tokens aren't reliably contiguous in the file — a real fix requires a
   paging/record model the decoder doesn't have, not one opcode rule.
2. **Short 5-13 byte markers with no `LPDD` text**, standing in for the
   ~230-byte DOCTYPE/head/title preamble entirely (the original "back
   reference" guess). Also not a simple opcode: the replaced title text
   differs per document, so it can't be a straight byte-for-byte
   back-reference — more likely the preamble/title for these documents was
   never re-emitted at all and lives only in the earlier `CatchlineIndex`
   TOC block, not in the document body.

Both are real paging/storage-layout behavior, not a decoder opcode gap —
correctly modeling either means understanding how NXT lays out pages and
records, which is a much bigger undertaking than Phase 2's opcode table.
Given it's not material to extracting section content (the bodies
themselves are intact either way — confirmed against every case checked),
**Phase 2b did not attempt to solve paging.** Instead it fixed the
*symptom* at the index-building level, where the actual goal lives.

**The fix (`scripts/nxt_build_index.py` v3):** `<div class="Section">` and
the `<span class="SectionNumber">` text immediately inside it turned out to
survive perfectly in every one of the 971 broken cases checked (100%
recovery), even when `<title>` doesn't. So v3 keeps the v2 title scan as
the primary pass, then separately scans the whole file for every
`<div class="Section">` occurrence; any such div that isn't the first one
inside a title-entry's span is a document v2 silently swallowed. Each
becomes its own entry with a synthesized title (`F.S. <number>`, read
straight from `SectionNumber`) and `"source": "section-number"` so it's
distinguishable from a real decoded `<title>`.

Result on `fs2025.nxt`: **26,317 documents, 982 recovered via
SectionNumber, 0 entries left containing more than one
`<div class="Section">`** (down from 991) — runs in 0.7s.

**Side effect, also cleaned up:** recovering a swallowed document doesn't
remove the *original*, now-orphaned `<title>` match — it's a real title
tag, just one whose body was itself cut short by the same page-boundary
interruption before reaching its own `<div class="Section">` (i.e., a
content-free stub). This produced ~930 duplicate-titled entries (one empty
stub + one real). 862 of them matched this exact pattern cleanly (one
entry with a Section div, one without, excluding legitimate `CHAPTER N`
part-boundary repeats) and are dropped by a follow-up pass
(`drop_stub_duplicates`), tracked as `dropped_stub_duplicates` in the
index. **~68 duplicate titles and ~48 garbled titles remain** — the
garbled ones are cases where the page-boundary interruption hit inside the
`<title>...</title>` span itself, fooling the non-greedy regex into
matching across it to a later, unrelated closing tag. Both are
small-in-number (68 and 48 out of 26,317) and same root cause as above
(paging, not a decoder bug) — left as a documented, quantified gap rather
than chased into full paging archaeology, consistent with how the
original merge gap was scoped before this fix.

## Phase 4: validation harness

`scripts/nxt_validate.py` decodes a citation via the Phase 2/3 index and
decoder, fetches the live leg.state.fl.us page for the same citation over
plain HTTP (`urllib` -- no dependency on any interactive tool, so this is
a real, re-runnable regression check), and diffs the two. Both sides get
reduced the same way: both leg.state.fl.us and our own decoded output
embed the section as a self-contained `<div class="Section">...</div>`
mini-document using identical class names, so extraction just grabs that
fragment, strips tags, unescapes entities, and collapses whitespace --
this is a much tighter comparison than a generic whole-page text diff.

Two confirmed **non-bugs** get folded away before scoring (see
`comparable()`):
- **Doubled em-dash.** The raw `.nxt` stream encodes some punctuation
  twice -- a literal Unicode character immediately followed by its own
  HTML-entity twin. Already documented for em-space; this run confirms it
  also applies to em-dash (`—` decodes as `——`). Real, deliberate format
  behavior (per the existing hypothesis: one copy for full-text search
  indexing, one for guaranteed rendering), not a decoding error.
- **Straight vs. curly apostrophes/quotes.** leg.state.fl.us applies a
  "smart quotes" typographic upgrade at render time. Checked directly: the
  raw `.nxt` bytes for one such case (`Children's` in § 215.22) contain a
  plain ASCII `'` (0x27), not a curly one. The decoder is being faithful
  to the source; the live page is prettifying it. Not a gap.

### Results (5 sections, chosen to cover distinct edge cases)

| citation | edge case | ratio | verdict |
|---|---|---|---|
| F.S. 1.01 | simple baseline | 0.9930 | close |
| F.S. 145.10 | has a `<table>` | 0.6535 | mismatch |
| F.S. 215.22 | heavy History (59 citations) | 0.9387 | mismatch |
| F.S. 775.082 | cross-references (32 internal anchors) | 0.9804 | mismatch |
| F.S. 6.081 | non-ASCII (degree/minute/second coordinates) | 0.8264 | mismatch |

**Every one of the 5 sections showed some divergence**, more than the
existing Phase 2b gap estimate (~68 duplicate + ~48 garbled *titles* out of
26,317, i.e. index-boundary problems) would have suggested. Investigating
each mismatch traced all of them to the *same already-documented*
page/record-boundary interruption mechanism from Phase 2b -- just now
confirmed to also strike **inside document bodies that are otherwise
correctly, uniquely indexed**, which the existing "count Section divs per
entry" quality check has no way to catch:

- **F.S. 1.01** (the most scrutinized section in this whole project) is
  missing its trailing `<div class="Note">` block and closing tags. Not an
  index-boundary bug -- checked the raw bytes right at and past the
  entry's boundary and confirmed § 1.02's clean `<!DOCTYPE...><title>`
  begins exactly there, with no leftover 1.01 content sitting just past
  the cutoff. The Note text simply isn't present as literal bytes anywhere
  in the file; a page interruption swallowed it before the boundary was
  ever reached.
- **F.S. 145.10** is the clearest and most significant finding: real
  content loss, not cosmetic. Decoding stops mid-sentence
  (`"...maintain a certified Florida property"`) right at the entry's
  length boundary, well before the section's live text ends. This
  originally looked like it pointed at a second problem too -- § 145.11
  appearing to be entirely absent from the index, a "double failure" where
  both the `<title>` scan and the Phase 2b `SectionNumber` recovery missed
  it. **That second claim was wrong** -- see the Phase 2c correction below.
  The 145.10 content-loss finding itself stands.
- **F.S. 215.22 / F.S. 775.082** show only isolated 2-4 character
  corruption mid-prose (`person` → `pOgierson`, `exemptions` →
  `exemptioh1ns`, `c.` → `c.vHik`) -- concrete, in-the-wild confirmation of
  the Phase 2b mid-token interruption mechanism, small in magnitude here.
- **F.S. 6.081** shows a large content-bleed: a block of unrelated prose
  (an older historical boundary description, itself plausibly quoted
  elsewhere in the same section) appears out of place mid-sentence. Same
  family as the "F.S. 7.08" example documented in Phase 2b.

**Not fixed.** This harness's job was to measure and characterize, not to
solve paging -- consistent with how Phase 2b already scoped that work as
out of reach for a targeted opcode fix. The materially new information is
that the impact is broader than the Phase 2b index-quality numbers alone
suggested: real (if usually small) content loss/corruption can occur
inside documents that pass every existing index-quality check. Left as a
documented, better-characterized gap; see `plans/re-plan.md` for the
follow-up phase this motivates.

## Phase 2c: quantifying the "double failure" gap

Phase 4 originally reported F.S. 145.11 as silently absent from the index
because *both* existing detection paths -- the Phase 3 `<title>` scan and
the Phase 2b `SectionNumber` recovery -- supposedly failed for it. **That
specific claim turned out to be wrong** (see "Correction: F.S. 145.11 is
fine" below) -- but chasing it down first required building an independent
way to check, and that check found the category is real, just not
evidenced by that example. The index-quality checks in
`scripts/nxt_build_index.py` rely on exactly the title-scan and
SectionNumber signals, so any failure mode that defeats both is invisible
to them by construction -- their true prevalence was unknown either way.

**A third, independent signal.** `fs2025.nxt` embeds a "CatchlineIndex"
table of contents near the front of each chapter, where every section gets
a self-referencing link:

```
<a href="#!-- #ID=FS20250145.10 --#">145.10</a>
```

The href's `#ID=` citation and the link's own display text both encode the
same chapter.section number redundantly. `scripts/nxt_find_gaps.py`
regex-scans the raw file for these anchors and only trusts a match when
the two encodings agree -- this is what makes it independent of the
decoder/index-builder (a plain byte-level check against the raw file) and
self-correcting for corruption (page-boundary interruption scrambles
digits, so agreement between the two independent encodings confirms this
stretch of bytes survived intact). Any citation confirmed present in the
CatchlineIndex but absent from the built index is a confirmed gap.

**Result:** 24,667 confirmed-clean CatchlineIndex citations survived the
self-reference check (out of 25,325 raw anchor matches; 42 discarded as
corrupted or non-self-referencing, the rest deduplicated). Comparing that
set against the built index's 24,796 F.S. citations found **95 confirmed
gaps** -- real sections completely absent from
`data/fs2025_citation_index.json` (0.38%). Full list:
`data/fs2025_gap_report.json`.

### Root cause: closing-tag theft, not tag destruction

Spot-checked F.S. 105.08, F.S. 15.16, and F.S. 44.404 by hand. All three
show the *same* mechanism, and it is not what Phase 4 assumed for 145.11
(outright byte destruction). In each case the target citation's own
`<title>...</title>` bytes are **fully intact** in the file. What's
missing is a *neighboring* document's closing tag: that neighbor's
`</title>` was overwritten by page-boundary interruption, so the Phase 3
regex's non-greedy match -- unable to find its own closer -- runs forward
and consumes the next `</title>` it finds, which belongs to the real
target. Both documents get merged into one entry, filed under the
neighbor's (garbled) title. Confirmed three ways:

- **F.S. 105.08**: the neighboring entry's title is garbled to literal
  `LPDD` marker bytes; the merge swallows 105.08's title as the
  "closer" for that garbled entry.
- **F.S. 44.404**: the neighboring title is F.S. 44.406, whose own closing
  tag is overwritten starting mid-word (`</tit` then corruption); the
  merged entry (`F.S. 44.406`, length 8,186 -- more than double a normal
  section) swallows 44.404's content along with it.
- **F.S. 15.16**: same pattern, with a twist worth its own section below
  (see "What's actually inside the stolen entries").

**Important correction: the "preceding" document is not the statutory
predecessor.** Initially assumed (and stated to a reviewer) that F.S.
15.16's neighbor-in-corruption would be its statutory predecessor,
F.S. 15.155. It isn't -- it's F.S. 15.182, a section that comes numerically
*after* both 15.16 and 15.18. Checking the raw byte order for the whole
chapter 15 neighborhood resolved this: the CatchlineIndex (TOC) order
matches the live site's canonical numeric order exactly (`15.15 → 15.155 →
15.16 → 15.18 → 15.182 → 15.21`), but the **document body order does
not** -- physically, the file stores `15.15 → 15.13 → 15.155 → 15.182 →
15.16 → 15.18 → 15.21`, with plenty of other locally out-of-order pairs
nearby (`15.03`/`15.02` swapped, `15.0326`/`15.0325`/`15.032` in
descending order, etc.). This is a previously undocumented structural
fact: **only the CatchlineIndex preserves statutory section order; the
document bodies are stored in some other order** (plausibly insertion/
build order -- sections get appended wherever there's room as the
statutes are amended over the years, never physically re-sorted). "The
preceding title in the file" and "the statutorily preceding section" are
different things, and only the former is relevant to this corruption
mechanism.

### What's actually inside the stolen entries

For F.S. 15.16, the merged/stolen entry ends up filed under the title
`F.S. 15.182` (that neighbor's own title text decoded correctly right up
until its closing tag) -- but its `<div class="Section">`/`SectionNumber`
inside that span reads **`15.16`**, not `15.182`. In other words: this is
not a case of lost content. F.S. 15.16's real, complete, undamaged section
body is sitting right there in the index, just filed under the wrong
citation string. (The genuine F.S. 15.182 document exists separately,
further down the file, correctly titled and indexed on its own.) This
generalizes: checked all 95 confirmed gaps and found every one recoverable
the same way -- see "Fixed: SectionNumber-vs-title cross-check" below.

### The "garbage" is a real field, not noise

Tested a hypothesis: is the interrupting "garbage" actually a page/segment
pointer rather than corruption? Yes, partially. The bytes immediately
after F.S. 15.16's stolen `</title>` opcode (`fc 02 00 00`) decode as a
little-endian `uint32` = **764**. `764 * 4096` (the LPDD page size) lands
at byte 3,129,344 -- and a genuine `LPDD` marker sits at byte 3,129,377,
exactly 33 bytes later. Checked a second, independent case (the
F.S. 44.404/44.406 pair): the equivalent field decodes to **1862**, and
`1862 * 4096 + 33` lands exactly on another real `LPDD` marker at byte
7,626,785. Both hit the same page (`page * 4096 + 33`) alignment exactly.
This is not coincidence -- it's a legitimate embedded field that encodes a
real page number elsewhere in the file.

That said, it's a *different, smaller* structure than the previously
documented full LPDD splice (the ~14-byte `...LPDD...` record seen at
genuine page transitions, immediately followed by a whole new document's
`<!DOCTYPE...>` -- e.g. the garbled neighbor in the F.S. 105.08 case is
this *other*, larger pattern). This shorter fragment doesn't cause an
immediate jump: in both cases checked, the byte stream just continues
reading linearly afterward and reaches that same page naturally, later,
on its own. So its exact purpose -- why the page number shows up here at
all, ahead of actually reaching that page -- is still an open question.
Worth another look if paging is revisited, but not solved.

### Correction: F.S. 145.11 is fine

Re-checked F.S. 145.11 (the case that originally motivated this phase)
with proper opcode-aware matching. The current index has a clean entry:
`<title>F.S. 145.11</title>` matches in a single 29-byte regex hit (no
corruption), single `<div class="Section">`, `SectionNumber` reading
`145.11` -- a completely normal, correctly-indexed document. It is **not**
one of the 95 confirmed gaps.

The original Phase 4 claim ("both title-scan and SectionNumber recovery
failed for 145.11") came from a naive raw-bytes substring search for the
literal string `<title>F.S. 145.11</title>` with nothing in between --
which will always fail to match, because *every* title in this format has
a `\x13\x37\x08` opcode spliced between the citation text and `</title>`
(that's the standard length-prefixed literal-token boundary, not
corruption). Searching for the exact un-tokenized string was the bug, not
the file. This is worth remembering: a `-1` from a raw substring search
against this format is not proof of missing content -- it has to be
checked against the tokenized structure, or cross-referenced with an
actual regex match, before concluding bytes are gone.

The underlying category this phase set out to quantify -- real,
independently-confirmed index gaps -- is still real and still 95-strong;
it just isn't evidenced by the specific example that prompted the
investigation.

### Fixed: SectionNumber-vs-title cross-check

Before building anything, checked how many of the 95 confirmed gaps were
actually recoverable this way: searched the raw file for each gap
citation's own `SectionNumber` text and confirmed it falls inside an
*existing* (mislabeled) index entry's span. Result: **all 95 -- 100%**.
None were genuinely destroyed; every one was sitting inside a
closing-tag-theft merge, exactly like F.S. 15.16.

Implemented the fix in `scripts/nxt_build_index.py`
(`fix_mismatched_titles`): for every title-scan entry that isn't a
CHAPTER/Preface heading, compare its title against the first
`<div class="Section">`'s own `SectionNumber` in its span; on mismatch
(including a garbled, unparseable title, like the `LPDD`-corrupted ones),
trust the `SectionNumber` and relabel the entry. Runs before the existing
Phase 2b orphan-recovery step, which is unaffected (it only looks at
*extra* Section divs beyond the first, so the two checks compose cleanly).

**Result:** 149 entries retitled; total documents 26,317 → 26,286 (net
-31, from newly-collapsed duplicates now getting caught by the existing
stub-duplicate dropper -- 862 → 893 dropped); confirmed gaps via
`scripts/nxt_find_gaps.py` **95 → 41**.

**Why not 0.** The fix can only give one merged entry one label. For
citations like F.S. 105.08, F.S. 15.16, and F.S. 44.404, the container's
*original* (pre-fix) title was either unparseable garbage or a real
citation that also has its own separate, correctly-indexed entry
elsewhere in the file (F.S. 15.182 and F.S. 44.406 both do) -- so
relabeling the container was a clean win with no regression. But for
citations like F.S. 39.0143 -- see the next section, this specific example
turned out to have its own additional wrinkle -- the container's original
title *looked* like a real citation without a separate copy anywhere else,
which would make relabeling a wash rather than a win. 41 gaps remained at
this point.

### Fixed further: CHAPTER/Part-Index entries can swallow a section too

Asked to spot-check a recovered section (F.S. 39.0142) against the live
site -- it matched (only the already-documented doubled-em-dash quirk).
But the live site also shows F.S. 39.0143 as chapter 39's actual *last*
section, and it was one of the 41 still-missing citations. Checking where
its content really was turned up something `fix_mismatched_titles`
couldn't see: it was the sole `<div class="Section">` inside a
`CHAPTER 39`-titled entry.

That looked like corruption at first -- why would a chapter heading
contain a section? It isn't. Chapter 39 alone has **13 separate entries
all literally titled `CHAPTER 39`**, and 12 of them are genuine, complete,
independent documents: Part Index (table-of-contents) pages, one per Part
of the chapter, each using its own `FSPartIndex.css` stylesheet -- they
just all share the same generic title text in this format, which is a
property of the source, not a bug. `drop_stub_duplicates` already knew to
leave `CHAPTER`-titled duplicates alone for exactly this reason. But the
*13th* one is 16,382 bytes long, several times any of the other 12 --
because its own closing tag was destroyed by the same page-interruption
mechanism as everywhere else in this phase, so the title-scan regex
swallowed forward into unrelated content and picked up F.S. 39.0143's
real, complete section along the way. Same closing-tag-theft mechanism as
before, just landing on a Part Index page's lost closing tag instead of
another section's.

Checked how widespread this is: **63 more sections** across the corpus
turn out to be hiding inside `CHAPTER`-titled entries this way (out of
1,435 total `CHAPTER`-titled entries) -- most of the still-missing 41
citations were exactly this. Extended `find_orphaned_sections` to handle
it: `CHAPTER`/`Preface` documents never legitimately contain a Section div
of their own, so for those entries specifically, treat *any* div found in
their span -- including the first -- as an orphan to recover, instead of
only extras beyond the first (the rule used for ordinary entries, which
stays as-is since a real section document legitimately owns its own first
div).

**Result:** confirmed gaps **41 → 28**; 1,045 sections now recovered via
SectionNumber (up from 982); total documents 26,286 → 26,299. F.S. 39.0142
and F.S. 39.0143 both spot-checked against the live site and both match
cleanly. The remaining 28 are the genuinely harder cases -- theft pairs
where neither twin has a rescuable second copy anywhere in the file --
left for the tag-aware Phase 3 rewrite described next.

### v4: the tag-aware Phase 3 rewrite -- closing gaps at the root

Both v3 patches above worked by detecting damage *after the fact* and
correcting the index entries it produced. `scripts/nxt_build_index.py`
v4 fixes the cause instead: v2's title-scan regex,
`<title>(.*?)</title>`, is *unbounded* -- when a title's own closing tag
is destroyed, `.*?` doesn't fail, it keeps searching forward past the
corruption for the next `</title>` it can find, silently stitching two
documents together. Every clean title in the corpus was already known to
have its citation text immediately followed by the exact opcode sequence
`\x13\x37\x08</title>` (`"</title>"` is always exactly 8 bytes, so a
well-formed closer's length prefix is always the 1-byte form -- confirmed
against every clean example in this document). `TITLE_RE` now requires
that sequence immediately after a *bounded* run of title text (an 80-byte
cap -- well above the longest real title, "Preface, Florida Statutes
2025" at 31 bytes, far below the multi-KB gap any real interruption
leaves). When a closer is destroyed, the regex simply doesn't match at
that position at all -- no swallowing, no mislabeling, no entry.

`find_orphaned_sections` was rewritten to match: one rule instead of two.
Within a span, the *first* Section div is "owned" (kept implicit, no
separate entry) only if its own SectionNumber matches the span's title
exactly; every other div -- the first one when it doesn't match (which
subsumes the old CHAPTER/Preface special case, since those titles never
parse as `F.S. <number>` and so never match), and any div after the
first regardless -- is an orphan, recovered under its own SectionNumber.

**A second non-contiguity discovery, found while verifying this.** An
earlier draft of this rule let *any* div in the span claim ownership if
its number matched, not just the first one. That produced 5 entries
that still failed the "at most one Section div per entry" check.
Investigating one (F.S. 175.341) found a case stranger than anything
else in this document: **a title and its own Section div aren't always
contiguous.** Physically, the file lays out F.S. 175.341's `<title>` tag,
then *all of F.S. 175.333's real content*, then finally F.S. 175.341's
own body. An index entry can only describe one contiguous byte range, so
granting 175.341 "ownership" of its (distant) real div corrupts the
length assigned to 175.333 sitting in between. Fixed by restricting
ownership to the *first* div only, unconditionally -- a mismatched first
div (like 175.333, which doesn't match 175.341's title) always becomes
its own orphan entry, and the original title becomes a harmless stub
that `drop_stub_duplicates` already knows how to clean up when a
same-titled entry with a real Section div exists elsewhere (which
175.341's orphan-recovered copy now is).

**Result:** confirmed gaps via `scripts/nxt_find_gaps.py` **28 → 0**.
1,204 sections recovered via SectionNumber (up from 1,045); 972 stub
duplicates dropped (up from 943); 26,428 total documents. Runtime: 0.7s
for the full 240MB file, unchanged from v3 (still a single linear regex
pass, no token-by-token walk needed). Spot-checked nine citations against
the live site -- 105.08, 15.16/15.182, 44.404/44.406, 39.0142/39.0143,
and the newly-found 175.333/175.341 pair -- all decode correctly.
Re-ran the original Phase 4 validation harness (`nxt_validate.py`) too:
identical ratios to the original run, confirming the index-boundary fix
didn't touch (or regress) decoder-level content fidelity.

One thing worth knowing if you re-run the spot checks: F.S. 15.16 and
F.S. 44.404 now show *lower* fidelity against the live site (~0.89) than
they did under v3's shorter, artificially-truncated spans. This isn't a
regression -- both entries now correctly extend far enough into their own
body to reach the pre-existing, already-documented Phase 2b mid-token
LPDD interruption (visible directly in the decoded output as literal
`LPDD` marker bytes). That's real content loss inside a document body, a
decoder-level limitation that was already known and already scoped as
out of reach for an index-building fix -- it just wasn't visible on these
two citations before because their old spans, corrupted by closing-tag
theft, happened to stop short of the interruption point.

## Phase 2d: the file is a paged store — everything above was reading it wrong

Every phase up to here treated `fs2025.nxt` as one flat byte stream and read
it linearly. It isn't, and that single wrong assumption is the origin of
*every* corruption symptom this document has been chasing: the destroyed
closing tags, the "garbage" interrupting titles, the 3.8% merge gap, the
double-failure sections, the mid-token `LPDD` content loss. None of it was
damage in the data. It was storage metadata being decoded as if it were
content.

The tell was sitting in plain sight: the file is **exactly** 58,626 × 4096
bytes. Not approximately — exactly. Every page after the header page opens
with its own typed header.

### Page layout

Offsets are within the page; integers are little-endian.

| Offset | Type | Meaning |
| --- | --- | --- |
| `0` | `uint16` | page type — **5** is the document-content type |
| `16` | `uint16` | slot count |
| `18` | `uint16` | end-of-slot-array offset |
| `20` | `uint16[]` | slot directory, one per fragment, in *descending* offset order |
| … | 6 bytes each | page-level chain pointers, back-pointer first |

Slot entries pack two things into 16 bits: the low 13 bits are a fragment's
page offset, the high 3 bits are flags. The final slot is a sentinel — its
offset field repeats the value at offset `18`, and its flag bits declare
which 6-byte page-level pointers follow it: bit 0 (`1`) a back-pointer,
bit 1 (`2`) a forward pointer. Bit 2 (`4`) is always set on the sentinel.
So the header length is `field@18 + 6 × (bit0 + bit1)`.

Only page type 5 carries document text. Types 2, 3, 7, 9, 10 and 16 were
sampled and are all search-index / B-tree machinery — this is where the
`binaryindex`/`strindex`/`PruneHitThreshold` vocabulary from the Phase 1
survey lives. Of 58,626 pages, 37,606 are content pages.

### Fragments and chains

A page holds one or more **fragments**, packed contiguously from the end of
the header to the end of the page. A fragment is a slice of *one* document.
A document too long for the space available is stored as a **chain** of
fragments scattered across the file — not in increasing page order, and
interleaved with fragments of entirely unrelated documents.

Page 761 is a clean illustration. It has four fragments:

| Fragment | Content |
| --- | --- |
| 0 | start of F.S. 15.182 — cut off mid-token inside its own `</title>` |
| 1 | tail of a document that started on page 764 |
| 2 | tail of a document that started on page 763 |
| 3 | tail of a document that started on page 760 |

Chain links are always encoded *backwards*, as `(uint32 page, uint16 index)`
where `index` counts fragments from the **end** of that page's fragment list
(so index 0 is the last fragment). There are two places the back-pointer can
live:

- **Fragments after the first on their page** carry it inline, as their own
  first 6 bytes. These are exactly the bytes the earlier "The 'garbage' is a
  real field, not noise" section identified as encoding a real page number —
  that guess was right, and this is what the field is for. They are *not*
  content and must be stripped.
- **Fragment 0** has no room for an inline prefix, so its back-pointer is
  the page-level bit-0 pointer instead.
- A fragment beginning with the `LPDD` record marker starts a fresh document
  and has no back-pointer at all.

Inverting those links gives a successor map. Across the whole file that is
**37,435 edges with zero conflicts** — every fragment has exactly one
predecessor and one successor, which is about as strong a confirmation as a
reverse-engineered format offers. Following them yields 26,306 chains.

A chain can hold more than one whole document (a short section can start and
end inside a single fragment), so documents are split out of the reassembled
chains on the `LPDD` record marker.

Implemented in `scripts/nxt_depage.py`; the whole reassembly takes 0.6s.

### What reassembly fixes

Read as a flat stream vs. reassembled from the paged store:

| Measure | Linear read | Reassembled |
| --- | --- | --- |
| Documents | 26,428 (inflated) | **26,306** |
| Intact `<title>…</title>` | 26,196 | **26,306 (100%)** |
| Documents ending in `</html>` | — | **26,305 (100.0%)** |
| `<title>` per document | 1 or 0 or merged | **exactly 1, always** |
| `<div class="Section">` per document | up to several | **at most 1** |
| Title vs. own `SectionNumber` mismatches | (patched around) | **0** |
| Garbled titles | 0 (after v4) | **0** |
| Duplicate non-CHAPTER titles | 1 (`F.S. 559.921`) | **0** |
| CatchlineIndex anchors confirmed / discarded | 24,667 / some | **24,866 / 0** |
| Confirmed index gaps | 0 (after v4) | **0** |

Three independent signals now agree exactly: 24,866 documents contain a
`<div class="Section">`, 24,866 index entries are titled `F.S. …`, and
24,866 CatchlineIndex table-of-contents anchors pass their self-reference
check — with zero anchors discarded as corrupt, where before some always
were. That mutual agreement, plus zero title-vs-`SectionNumber`
disagreements across all 26,306 documents, is the real evidence the
reassembly is correct; the per-section live-site checks below are
confirmation on top of it.

The `F.S. 559.921` duplicate is resolved rather than explained away: it was
never duplicated in the file. It was one document counted twice by a scan
that couldn't see where the first one ended.

### Content fidelity, measured corpus-wide

`nxt_validate.py --sample N [seed]` now takes a reproducible random sample of
section citations, fetches each from leg.state.fl.us, and caches the reduced
text under `data/live_cache/` (git-ignored) so re-runs are free and offline.

200 randomly sampled sections, seed 0:

- **200 / 200 (100%)** at or above the 0.99 pass threshold
- **192 / 200 (96%)** byte-exact
- mean ratio **0.99993**, worst **0.9903**

All eight non-exact cases have the same single cause, and it is not content
loss: leg.state.fl.us renders footnote markers as superscripts, which reduce
to a bare `1` after tag-stripping, where the NXT source encodes them as a
literal `[1]`. Every difference is an *insertion* on our side — nothing is
missing from any of the 200. Arguably our output is the more faithful of the
two.

The previously-failing citations are now exact. F.S. 15.16 and F.S. 44.404,
which sat at ~0.89 under v4 because they reached into a mid-token `LPDD`
interruption, both score **1.0000**. So do 15.182, 105.08 and 39.0143.

This closes the mid-body content-loss item that had been open since Phase 2b
and carried as the project's main unquantified risk. It was never a missing
opcode rule and never needed one — the interruptions were fragment
boundaries, and reassembling the fragments removes them entirely.

## Phase 2e: tallying the skipped bytes, and the two defects it found

The decoder's fallback — skip unrecognized control bytes one at a time, pass
through anything printable — was never measured, only trusted. Counting what
it actually skipped across all 26,306 reassembled documents turned up
**3,852,947 skipped bytes, 2.52% of the content**, spread over only **nine
distinct byte values**. Two of those skips were producing wrong output.

### `\x15` decoded: two shapes, one of them a real defect

`\x15` accounted for 696,638 skips and turned out to be two unrelated things.

**`\x15\x04\x01\x05` and `\x15\x04\x01\x06` — 184,764 each, exactly balanced.**
Field markers inside History notes: `…05` always introduces a hyperlink (every
instance is immediately followed by a `\x13\x37` token opening
`<a href="#!--`), `…06` introduces a non-link field (plain text, a `<div>`, or
`</HISTORY>`). The literal `<a>` markup is present either way, so skipping
these loses nothing — the same redundancy already documented for the `\x10`
formatting toggle. **Correctly skipped.**

**`\x15\x01\x01\x01` — 327,110 occurrences — the character-doubling marker.**
It precedes a literal UTF-8 character which is then immediately repeated as an
HTML entity in a `\x13\x39` token:

```
\x15\x01\x01\x01 \xe2\x80\x83 \x13\x39\x08 &#x2003;     (EM SPACE)
\x15\x01\x01\x01 \x08 \xe2\x80\x94 \x13\x39\x08 &#x2014  (EM DASH)
\x15\x01\x01\x01 \x08 \xc2\xa0 \x13\x39\x06 &#xA0;       (NBSP)
```

This confirms the long-standing guess (see the doubled-punctuation note in the
Phase 4 harness) that the format stores some punctuation twice — but the
consequence had been misattributed. It is not a quirk to normalize away at
comparison time: the decoder was emitting **both** halves, so the output HTML
rendered the character twice. Measured before the fix: **327,048 pairs across
24,926 documents — 94.8% of the corpus.**

| Character | Instances |
| --- | --- |
| U+2003 EM SPACE | 254,468 |
| U+2014 EM DASH | 63,428 |
| U+00A0 NO-BREAK SPACE | 8,894 |
| U+2002 EN SPACE / U+2013 EN DASH / curly quotes | 258 |

Only **62** occurrences of `\x15\x01\x01\x01` corpus-wide don't fit the shape,
so the rule is effectively universal; those fall through to the old
byte-at-a-time behaviour. The fix drops the literal copy and keeps the entity
token — `\x13\x39` is a real markup subtype, so the entity is the rendering
copy and the literal is presumably what the full-text index reads.

**Why no metric ever caught this.** `nxt_validate.py`'s `normalize()` collapses
`\s+` to a single space, which hides all 263,569 doubled-whitespace cases
outright, and `comparable()` explicitly folded doubled em- and en-dashes,
hiding the other 63,455. Masking was total: 100% of a defect affecting 94.8%
of documents was invisible to a harness reporting 96% byte-exact. The
dash-folding has been **deleted** rather than kept — with the decoder fixed it
is unnecessary, and keeping it would let the same class of defect return
unnoticed.

### `LPDD` was leaking into every document

The record marker `\x11\x06\x0b\x04\x00LPDD\x00\x00\x00\x00\x00` contains four
printable ASCII bytes, so the text sniffer emitted them. Every one of the
26,306 decoded documents began `LPDD<!DOCTYPE html PUBLIC …`. Invisible to
validation because `extract_body_text()` anchors on `<div class="Section">`
and discards everything before it. Now skipped as a 14-byte unit.

### After the fix

| Measure | Before | After |
| --- | --- | --- |
| Unknown bytes skipped | 3,852,947 (2.52%) | **2,214,078 (1.45%)** |
| Doubled characters in output | 327,048 | **0** |
| Documents starting with `LPDD` | 26,306 | **0** |
| Documents starting with `<!DOCTYPE` | 0 | **1,000 / 1,000 sampled** |

Every remaining skipped byte is now accounted for exactly: 735,718 `\x08`
text-run prefixes, and 1,478,360 bytes making up the 369,528 History field
markers plus the 62 non-conforming `\x15` runs. Nothing unexplained is left in
`fs2025.nxt`'s content layer.

Live-site validation was re-run afterwards *without* the dash-folding crutch —
a strictly harder comparison than before — and holds at **200/200 above the
0.99 threshold, 192/200 byte-exact, mean 0.99993**. The eight non-exact cases
are unchanged and share one cause: leg.state.fl.us renders footnote markers as
superscripts, which reduce to a bare `1` after tag-stripping, where the source
encodes a literal `[1]`. Every difference remains an insertion on our side.

### HTML structural fidelity: a first look

Worth recording what this *doesn't* cover. Every fidelity number in this
document comes from stripping all tags and comparing plain text, so nesting,
attributes and table structure have never been checked. A first spot check —
six deliberately awkward documents (a real `<table>`, 32 cross-reference
anchors, 59 History citations, non-ASCII coordinates, a Part Index) plus 1,000
random documents, parsed with a strict tag-matching parser — found **1,000 /
1,000 structurally clean**: no unclosed tags, no mismatched closers, no
implicit closes, and balanced `<div>` / `<span>` / `<table>` counts in every
one. That is less surprising than it first looks: the format stores tags as
literal text, so there is no tag-reconstruction step that could get nesting
wrong. The residual risk is narrower than "is the HTML valid" — it is
attribute- and entity-level fidelity, which would need a tag-and-attribute
sequence comparison rather than another nesting check.

## Phase 4b: closing the three verification gaps

Phase 2e left three things unverified rather than unknown. All three are now
measured.

### Is anything missing? The `0x1BC` count says 26,348; we find 26,306

The header field at `0x1BC` exceeds the reassembled document count by 42, and
that gap is the one completeness question the three-signal agreement cannot
answer — Section divs, index titles and CatchlineIndex anchors all derive from
documents already found, so unreachable documents would be invisible to every
one of them. Four independent checks say nothing is missing:

- Every `LPDD` record marker in the entire 240 MB file — all **26,306** of them
  — lies in a type-5 content page. Zero appear in any other page type, so no
  document text hides in the pages reassembly skips.
- Every one of the 63,741 type-5 fragments is reachable: 26,306 chain heads +
  37,435 successor targets, **zero unreachable**.
- Every chain head begins with the `LPDD` marker — no chain starts mid-document.
- The fragment tiling covers **every byte** of every type-5 page after its
  header: zero unaccounted byte ranges between fragments or at page ends.

`0x1BC` is therefore not a count of reachable documents. Across all 13 files it
is always slightly *more* than the true count — never fewer, never equal — by
between 1 and 44, with no correlation to file size, page count, page-type
histogram, or B-tree entry count (checked all four). Six of the 13 files are
off by exactly 1. That pattern fits an allocation high-water mark or a counter
that still includes deleted records; it does not fit missing content. Moved to
trivia.

The same sweep incidentally confirmed that **`nxt_depage.py` reassembles all 13
`.nxt` files without error** — the page/fragment model is not specific to
`fs2025.nxt`. Nine of the 13 produce documents with intact titles; the other
four (`Law_Download_Help_PDF`, `rtt2025`, `sct2025`, `TT2025`) reassemble but
carry no `<title>` tags, which is a Phase 8 question, not a reassembly failure.

### The 1,440 documents with no Section div

All fidelity work before this was section-based, against the 24,866 documents
that have a `<div class="Section">`. The remaining 1,440 had no evidence of any
kind. They break down cleanly, and **no statute section is among them** — every
`F.S. n` document has a body:

| Kind | Count | Validation |
| --- | --- | --- |
| Chapter-level TOC (`class="Chapter"`) | 638 | 120 sampled — **120/120 exact** |
| Part TOC (`class="Part"`) | 753 | 120 sampled — **120/120 exact** |
| SubPart TOC (`class="SubPart"`) | 47 | no live page exists; see below |
| `Preface, Florida Statutes 2025` | 1 | boilerplate, no live equivalent |
| `Obsolete Cross-reference` | 1 | boilerplate, no live equivalent |

leg.state.fl.us publishes chapter and Part contents pages using the *same*
class vocabulary our decoder emits (`ChapterTitle`, `ChapterNumber`,
`CatchlineIndex`, `IndexItem`, `Catchline`), so they diff exactly like sections
do — `nxt_validate.py` gained `--chapters N` and `--parts N` for this. Both
score **1.00000 mean**, byte-exact on every sampled document.

SubParts have no live counterpart at all: the site's Part page lists subpart
*headings* only and publishes no subpart contents page. What can be checked,
is: all **47/47** subpart headings (letter + title, e.g. "A. Registration and
Enforcement of Support Order") appear verbatim in the live Part page for their
chapter, and all **490/490** section anchors they list resolve to real indexed
documents.

One latent bug surfaced here and is worth knowing about before Phase 9:
**resolving a document by title is unsafe for `CHAPTER n` titles.** Every Part
index of a chapter shares the bare title `CHAPTER 39`, so a `{title: entry}`
dict silently keeps whichever happens to be last. Only `F.S. n` titles are
unique. `nxt_validate.py` now passes record numbers explicitly.

### Markup fidelity: `nxt_validate_markup.py`

Every fidelity number before this stripped all tags first, so it measured
whether the words were right and nothing more — the blind spot both Phase 2e
defects lived in. `scripts/nxt_validate_markup.py` compares the *element
stream* instead: the ordered sequence of (tag, class, other attributes), plus
every anchor's target citation normalized so the two sides are comparable
(ours encodes `#!-- #ID=FS20250001.01 --#`, the live site a real URL; both mean
"1.01").

200 random sections, seed 0:

| | |
| --- | --- |
| Live elements | 7,042 |
| Our elements | 8,290 |
| **Aligned exactly** | **7,004 (99.46% of live)** |
| Live elements missing from ours | **0** (see below) |
| Live link targets missing from ours | **0** |

The 38 elements that first appear as "missing" are all the same thing, and it
is not data loss: the live site rewrites `<span class="Text X Justify">` as
`<p class="X Justify">`. Verified against raw bytes — the `.nxt` file literally
contains `<span xml:space="preserve" class="Text Reversion Justify">`, so our
output is the faithful one and the transformation is the website's. Counting
those as matches, **no live element is unaccounted for**.

Our output is a strict superset of the live markup, by 1,286 elements:

| Extra element | Count | Why |
| --- | --- | --- |
| `<a>` | 610 | session-law citations in History notes, which the live site renders as plain text |
| `<catchline>` `<secbody>` `<history>` | 200 each | Folio's own semantic tags, which the live site strips |
| `<notes>` | 38 | same |
| `<span class="Text …">` | 38 | the counterparts of the `<p>` rewrite above |

**Methodology note worth keeping.** The first version of this comparison
reported 167 missing elements, 131 of them in F.S. 39.303 alone — against text
that matches the live page character for character (ratio 1.0, identical
length). The cause was `difflib.SequenceMatcher`'s `autojunk` heuristic, which
discards elements appearing in more than 1% of a sequence of length ≥ 200 as
"popular". Statute markup repeats `div.Subsection` and `span.Number` hundreds
of times, so exactly the anchors alignment depends on were thrown away.
`autojunk=False` is mandatory here; with it on, the measurement invents
differences.

## Phase 4c: checking the decoder against the source, not the site

The fidelity harness has a permanent blind spot. `normalize()` collapses
`\s+` before scoring, and that collapsing is load-bearing — the live pages
and our decoded output carry different template indentation, so without it
nothing would ever match. The consequence is that **extra whitespace is
invisible to it**: 263,569 of Phase 2e's 327,048 doubled characters were em
spaces and NBSPs that collapsed away before the diff ran, so the harness
scored 1.0000 on documents that were visibly wrong.

That cannot be closed by diffing harder against the live site. It has to be
closed by checking the decoder against the *source bytes*. That is
`scripts/nxt_check_output.py`, which asserts four invariants:

1. **Every `0x15 0x01 0x01 0x01` marker is claimed by the doubled-character
   rule.** A marker that falls through gets emitted twice — once as the
   literal copy, once as the entity token. This is a *complete* guard on
   that defect class: at zero fall-throughs, no doubling of this kind can
   be shipping.
2. **No character sits next to its own entity form** in the output. The
   same defect seen from the output side, so a new doubling shape that
   invariant 1 doesn't know about still gets caught.
3. **Every source byte is consumed exactly once** — no gaps, no overlapping
   reads.
4. **A whitespace census**, recorded as a baseline rather than judged.

### The residual it found: 62 doubled ampersands

Phase 2e's rule identified the doubled-character shape partly by *byte
width*: the literal copy had to be multi-byte UTF-8, on the reasoning that
a 1-byte run there would be ordinary ASCII text. That proxy held for
327,048 of 327,110 markers and silently failed on the other 62 — every one
a literal `&` paired with `&amp;`:

```
15 01 01 01  '&'  13 39 05  "&amp;"
```

Both copies were emitted, shipping `AT&&T Mobility`, `Child && Dependent
Care Tax Credit` and `Flagler && Volusia` across **25 documents**.

Fixed by replacing the width proxy with the real invariant: **the literal
copy and the entity token must decode to the same character**. That is both
stricter (a mismatched pair no longer matches on byte width alone) and
correct for single-byte characters. Coverage went 327,048 → 327,110 of
327,110, and corpus-wide **385,305 of 385,305 markers are now claimed, with
0 adjacent duplicates** in any of the 12 markup files.

Worth noting how this one hid. Unlike the em-space doublings, `&&` is *not*
whitespace, so the live-site harness could see it — but only as a
single-character difference in documents up to 171,038 characters, scoring
0.9999 and passing the 0.99 threshold as `CLOSE` rather than `MATCH`. With
only 250 of 24,866 sections sampled, none of the 25 affected documents had
ever been drawn. Sampling plus a ratio threshold will systematically miss
small defects in large documents; that is the argument for the census.

Re-validated the affected sections against the live site afterwards: F.S.
61.30, 215.61, 672.320 and 202.20 are now byte-exact, and the only residual
difference in 921.0022 and 320.08058 is the known `[n]` footnote-marker
representation question (the source encodes a literal `[1]`, the site
renders a superscript) — a Phase 9 decision, not a defect.

### Baseline census (fs2025.nxt, all 26,306 documents)

All four invariants hold: 327,110/327,110 markers claimed, 0 adjacent
duplicates, **0 gaps and 0 overlapping reads** — which turns Phase 2e's
"every byte is accounted for" from an assertion into a mechanically
checked claim.

| whitespace character | count |
|---|---|
| U+0020 SPACE | 11,273,116 |
| U+2003 EM SPACE | 254,468 |
| U+00A0 NO-BREAK SPACE | 8,894 |
| U+2002 EN SPACE | 207 |

Adjacent-whitespace runs are legitimate here and each traces to a repeated
source marker: 2,772 `NBSP NBSP` and 149 runs of five NBSPs are
fill-in-the-blank rules in oath forms (`I, ␠␠, do solemnly swear`) and
column alignment in the judge-count tables of F.S. 26.031 and 34.022.
Their *counts* are exactly what the live-site harness cannot see — emitting
three NBSPs where the source has five would still score 1.0000 — so
recording them means a future change that alters them shows up as a diff.

## Phase 8a: the model generalizes — and the corpus found a defect `fs2025` couldn't

Everything through Phase 4b was measured against `fs2025.nxt` alone. The open
question ("remaining work" item 4) was whether the page/fragment model is a
property of the *container* or just of that one file — a real risk rather than
a curiosity, since `flcnst2025.nxt` and `lf2025.nxt` turn out to hold primary
law FLiberator would publish.

Reproduce with `uv run python scripts/nxt_corpus_triage.py`.

### The storage layer is a container property

All **13 files reassemble with zero chain conflicts** — no exceptions, no
out-of-range back-pointers, no unreachable fragments. Nothing about
`nxt_depage.py` is specific to `fs2025.nxt`. Combined across the corpus that
is **45,520 documents**.

### The content layer is nearly universal, and decodes to well-formed HTML

12 of the 13 are tokenized markup; the 13th (`Law_Download_Help_PDF.nxt`) is a
single record wrapping a PDF byte stream, which is why its "unknown byte"
figures are meaningless. Across all 45,519 markup documents, the decoded output
has **0 unclosed elements and 0 mismatched close tags** — with exactly one
outlier, discussed below.

After the fix in the next subsection, the byte-level skip rate falls to well
under 1% almost everywhere, and **99.4% of everything still unaccounted for is
the single byte `0x08`**, already closed as trivia (it emits nothing and
precedes text runs). `rtt2025.nxt`'s comparatively high 3.3% is *entirely*
`0x08` — an artifact of that file being a dense table of short cells, not a
defect.

### The defect: 39,200 stray characters, in 10 files, invisible in `fs2025`

Phase 2e established the `0x15 0x04 0x01 <id>` field marker from its two
`fs2025.nxt` instances, `0x05` and `0x06`, and the decoder hardcoded those two
ids. The corpus has two more: **`0x4d`/`0x4e`**, bracketing the document Title
field (`0x4d` immediately before `<TITLE>`, `0x4e` immediately after
`</TITLE>`), perfectly balanced at 19,600 each, present in 10 of the 13 files.

`0x4d` and `0x4e` are the printable ASCII `M` and `N`. Because the rule didn't
match, the decoder skipped the first three bytes one at a time and then handed
the id to the printable-run sniffer, which emitted it as literal text:

```
<HTML>\r\n<HEAD>\r\nM<TITLE>Constitution of the United States</TITLE>N\r\n<link ...
                   ^                                                ^
```

**`fs2025.nxt` was immune purely by luck** — both of its ids happen to be
non-printable, so the identical bug produced no visible output there. No amount
of further work on `fs2025.nxt` would have found this; only running the corpus
did. This is the same failure mode as Phase 2e's leaked `LPDD`, and the third
defect of that shape.

Fixed by generalizing the rule to `0x15 <0x03|0x04> 0x01 <id>` for any id,
consuming all four bytes as a unit. A fourth shape confirmed at the same time:
`0x15 0x03 0x01 0x01`, an end-of-body marker appearing exactly once per
document in `xrt2025.nxt` (613 of them). Skip rates before → after:

| file | before | after |
|---|---|---|
| `stin2025.nxt` | 5.61% | 0.83% |
| `xrt2025.nxt` | 6.47% | 1.30% |
| `fs2025.nxt` | 1.45% | 0.48% |

Re-validated `fs2025.nxt` against the live site afterwards: 40/40 sections
pass, mean ratio 0.99999 — no regression.

### The one structural outlier is real content, not damage

`lf2025.nxt` record 197 — *Chapter 2025-198*, the General Appropriations Act,
2,025,026 bytes decoded — closes with `</approp>` rather than `</html>` and
uses a custom tag vocabulary (`<LAWBODY>`, `<LSECT>`, `<approp>`, `<PRE>`).
That is what the source contains. It is the sole source of the corpus-wide 3
unclosed / 1 mismatched element counts, and is the same class as `fs2025.nxt`'s
single non-`</html>` record already closed as trivia.

### What each file actually holds

The filenames are abbreviations, and several earlier guesses in the Corpus
table above were wrong. These are identified from each file's decoded `<title>`
and first document body, not from the filename:

| file | documents | contents |
|---|---|---|
| `fs2025.nxt` | 26,306 | **Florida Statutes** — the main target |
| `defx2025.nxt` | 12,692 | index of **defined terms** → statute section (`AAF intercity rail passenger, 343.545`) |
| `stin2025.nxt` | 3,783 | the general **statutes subject index** |
| `lndx2025.nxt` | 1,018 | index to the **Laws of Florida**, keyed to session-law chapters (`…authentication by judge, 2025-163`) |
| `xrt2025.nxt` | 613 | **cross-reference tables**, one document per statutes chapter |
| `conndx2025.nxt` | 374 | index to the **Florida Constitution**, keyed to article/section (`ADVERSE MEDICAL INCIDENTS, A10 S25`) |
| `lf2025.nxt` | 255 | **Laws of Florida** — 2025 session laws, one document per chapter |
| `flcnst2025.nxt` | 226 | **Florida Constitution** |
| `TT2025.nxt` | 217 | **Tracing Table** |
| `rtt2025.nxt` | 21 | **Repealed and Transferred Sections Table** |
| `sct2025.nxt` | 12 | **Section Changes Table** |
| `uscon.nxt` | 2 | **US Constitution** + its index |
| `Law_Download_Help_PDF.nxt` | 1 | the help PDF, wrapped in the container |

Four files (`conndx`, `lndx`, `defx`, `stin`) all self-title `Subject Index`,
so the `<title>` alone doesn't separate them — the distinction above comes from
what their entries point *at*. Note this corrects the Corpus table's earlier
guesses: `conndx` is the **Constitution** index, not a "connection index."

**Consequence for Phase 8/9 scope:** three files hold primary law
(`fs2025`, `flcnst2025`, `lf2025`, plus `uscon`), and the rest are
finding aids derived from it. That is a scope decision for Phase 9, but it is
now a decision over a known list rather than an unknown one.

## Not yet investigated

- Entity-level fidelity *within* elements. The element stream and the
  tag-stripped text are both verified; what has not been compared is the
  exact entity encoding of text inside each element (e.g. whether a given
  character arrives as `&#x2003;` or as a literal). Low risk — the text
  comparison unescapes both sides and matches — but it is not zero.
- Whitespace-class defects remain invisible to live-site diffing, because
  `normalize()` collapses `\s+` and that collapsing is load-bearing for other
  reasons. This is how 263,569 of Phase 2e's 327,048 doubled characters hid.
  Catching that class needs a check against the decoder's own output rather
  than against the live page.
- Page geometry has only ever been exercised on the 2025 edition. Phase 8a
  widened this to all 13 files of that edition — the 4096-byte page and the
  slot/chain layout hold across every one — but they were all built by the
  same tooling in the same year, so this says nothing about a future
  edition. The reassembler should still assert its assumptions rather than
  silently produce garbage if a later year's layout differs.
- Fidelity for the non-`fs2025` files is unmeasured. Phase 8a shows they
  reassemble and decode to well-formed HTML, and the Florida Constitution
  spot-checks verbatim against the live text, but no systematic diff
  against ground truth has been run for `flcnst2025.nxt`, `lf2025.nxt` or
  `uscon.nxt` — `nxt_validate.py`'s URL builder is `F.S. n`-specific.
- The meaning of the remaining page-header fields: the `uint32` at offset 2
  of every page (varies per page, not sequential — plausibly a checksum),
  and the constant `ffffffff` at offset 12 of content pages. Not needed for
  reassembly, which uses only the slot directory and the chain pointers.
- What determines the *order* of documents in the file. Reassembly confirms
  the earlier chapter-15 and chapter-39 finding at file-structure level:
  physical storage order has nothing to do with statutory order, and only
  the CatchlineIndex preserves the canonical sequence.
- `data1.cab`/`data2.cab` (InstallShield cabinets bundled in `FLLawDL2025/`) —
  unextracted; likely contain the real Folio/NXT rendering engine
  (`nfoenu6.dll`, referenced by name inside `fs2025.nxt` itself, isn't present
  in this download). Only relevant if static analysis stalls and dynamic
  analysis becomes necessary.
- The bundled `copy/*.exe`/`*.dll` (`Work-Set.exe`, `Serv-Go.exe`,
  `Serv-Out.exe`, `wbdIB44I.dll`, `WBDLA44I.DLL`, `wwwnt34i.dll`) are
  **WinBatch**-compiled installer/service-management helpers, not the
  Infobase engine — confirmed via their string tables (`"Dialog: ..."` error
  boilerplate, `"Extender loaded: %s"`, `xAllocPrintf`, `wntServerList` all
  match WinBatch's runtime). Dead end for format analysis.
