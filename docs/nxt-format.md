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
| `0x1BC` (uint32 LE) | varies, strongly tracks content volume: `uscon`=3, `sct2025`=13, `TT2025`=218, `rtt2025`=22, `Law_Download_Help_PDF`=2, `xrt2025`=625, `defx2025`=12723, `stin2025`=3810, **`fs2025`=26348** | **best candidate for a document/record count.** 26,348 is plausible for the total section/subsection/note count of the full Florida Statutes. `Law_Download_Help_PDF.nxt`=2 fits "one wrapped PDF ≈ 2 records" (e.g. title + content). |
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

### Known gaps

- Boilerplate `<head>` still has minor rough edges from opcodes not yet
  catalogued (the decoder handles the big DOCTYPE/meta run fine now via the
  2-byte length fix, but a handful of surrounding bytes are still opaque).
- Two stray digit characters (`"0"` before/after `<CATCHLINE>`, previously a
  `"9"` near an EM SPACE) leak into output from an unresolved ~6-byte block
  (`10 00 03 82 <byte> 01`) that recurs before hidden/structural tags — one
  of its bytes happens to be a printable ASCII digit, which the
  printable-run sniffer picks up as if it were content. Cosmetic only; does
  not affect actual legal text.
- Confirmed **not a bug**: what looked like a mid-document corruption near
  item (f) turned out to be a real embedded binary record (the same
  `\xff\xff\xff\xff...` signature as the per-document manifest block,
  appearing inline before the literal, unprefixed text `Justify">`) — a
  likely revision/edit-tracking marker. The decoder now passes through the
  unprefixed text correctly; the embedded record itself is still opaque
  (skipped byte-by-byte) but doesn't need to be understood to get the text
  right.
- The redundant-looking `<EM SPACE char> + &#x2003;` sequence appearing
  after every subsection/item number (e.g. `(1)` then both a literal Unicode
  EM SPACE and the equivalent HTML entity) was checked against multiple
  instances and is consistently present — a real feature of the format
  (probably: raw character for full-text search indexing, entity for
  guaranteed-correct rendering), not a decoder artifact.

## Not yet investigated

- The full byte-value vocabulary of remaining short control opcodes (Phase 2
  continued) — current fallback (skip unknown bytes one at a time, but pass
  through anything printable) is good enough for reliable text extraction,
  but doesn't explain everything structurally.
- Whether there's a true random-access offset index anywhere in the file, vs.
  relying on a single linear scan (Phase 3).
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
