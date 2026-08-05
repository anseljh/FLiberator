# Folio NXT `.nxt` Infobase format — working notes

Living notes from reverse-engineering the `.nxt` files in `FLLawDL2025/Library/`.
See `plans/re-plan.md` for the analysis plan these notes track against.
Everything here is derived from the 13 `.nxt` files in this repo's (git-ignored)
`FLLawDL2025/Library/` folder plus the live statute text at leg.state.fl.us —
re-run `scripts/nxt_survey.py` to regenerate the raw data behind this doc.

## Corpus

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

Working opcode hypotheses (sample size still small — Phase 2 in the plan is
to confirm these programmatically across thousands of instances, not by eye):

- **`\x13 <len> <len bytes>`** — opens a markup token. Length checks out
  exactly against real tag text in every sample seen so far (e.g. `\x13\x25`
  + 37 bytes = the 37-character `<a href="...">` string).
- **`\x08`** — precedes a literal text run (plain content, not markup).
  Terminator not yet confirmed — likely "until the next control opcode."
- **`\x15 <bytes>`** — short field, possibly paragraph/style marker or
  special-character escape (one instance carried a literal UTF-8 EM SPACE
  character, `\xe2\x80\x83`, immediately after it).

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

This is a meaningful result for the project's direction: it confirms `.nxt`
can be decoded **directly to HTML (+ a JSON metadata sidecar)**, without ever
producing `.fff` or running it through `folioxml` — see the "pipeline shape"
decision point in `plans/re-plan.md` Phase 5. Text-content extraction is
solid across two different document eras; what's left rough is decorative
markup and a handful of still-uncatalogued short opcodes.

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

### The 3.8% merge gap: likely cause found (not yet fixed)

Follow-up investigation (not yet implemented as a decoder fix) narrowed the
merge gap from "same unresolved decode edge case" to a specific, testable
hypothesis. Method: pulled all 991 flagged entries (`class="Section"`
appearing more than once in an entry's span), decoded a sample with the
Phase 2 `decode()`, and diffed the raw bytes at the internal boundary.

Concrete example — entry titled `F.S. 6.02` (offset 136270, length 3042):
decoding the whole span produces **two complete, correctly-formed
documents** back to back — 6.02's full section text (catchline, body,
history, matches its own title), immediately followed by 6.01's full
section text with no title tag of its own. Both bodies are intact; nothing
here is corrupted at the content level, only the second document's
`<title>` is unaccounted for.

The raw bytes right after the first document's `</html>` are the tell —
the same shape recurs across all 991 cases:

```
</html>  <handful of binary bytes, 5-13 long>  <ASCII text resumes mid-word>
```

e.g. (raw bytes, not decoded output):

```
</html>\xb7\x02\x00\x00\x03\x00tle>F.S...          (should read "<title>F.S...")
</html>\x05\x00\xe2\x07\x02\x00\x00\x00\x00\x00\x00\x00\xfffl...
</html>&\x00\x00\x00\x01\x00rida or...
```

A normal document's preamble (`<!DOCTYPE...><html>...<head><meta.../>`) is
~230 literal bytes; here only 5-13 binary bytes stand in for all of it,
clustering into a handful of recurring shapes (several sharing the exact
tail `...\x02\x00\x00\x00\x00\x00\x00\x00\xff`). That's far more consistent
with **an unrecognized opcode that back-references the boilerplate head**
than with random corruption — every one of these ~26,000 documents shares
byte-identical DOCTYPE/head/link boilerplate, so a back-reference/dictionary
opcode for it would be a natural, high-value compression choice for the
format to make. The current decoder doesn't recognize this opcode, falls
through to its dumb one-byte-at-a-time skip, and desyncs by a few bytes
right as the following `\x13\x37<len>` title token starts — sometimes
skipping past the whole title (the 6.02/6.01 case), sometimes chopping its
first few bytes (the `tle>F.S` case, missing `<ti`).

**Not yet fixed.** Next step, if pursued: bucket the ~991 boundary byte
sequences by shape/length and test whether the byte immediately following
each one always lands inside a `\x13\x37<len>` title token — if so this is
one new opcode rule (likely fixed-length or self-length-prefixed), not
further open-ended archaeology. See `plans/re-plan.md` Phase 2b.

## Not yet investigated

- The full byte-value vocabulary of remaining short control opcodes (Phase 2
  continued) — current fallback (skip unknown bytes one at a time, but pass
  through anything printable) is good enough for reliable text extraction,
  but doesn't explain everything structurally. This is also what's behind
  the ~4% title-extraction gap in the Phase 3 index above.
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
