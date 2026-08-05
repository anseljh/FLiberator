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

## Phase 2 update: proof-of-concept decoder works

`scripts/nxt_decode_poc.py` implements a first decoder and successfully
extracts the **complete, verbatim body text of § 1.01** from `fs2025.nxt`
— all 19 numbered definitions plus the 9 lettered wartime-service periods in
subsection (14) — matching the live leg.state.fl.us page word-for-word. It
also recovered a bonus the plain web page doesn't show: a `<HISTORY>` block
of session-law citation anchors (`LAW90-092`, `LAW92-080`, ... `LAW2024-147`).
See `scripts/sample_output_1.01.txt` for the raw decoded output.

This is a meaningful result for the project's direction: it means `.nxt` can
plausibly be decoded **directly to HTML (+ a JSON metadata sidecar)** without
ever producing `.fff` or running it through `folioxml` — see the "pipeline
shape" decision point in `plans/re-plan.md` Phase 5. Text-content extraction
looks solid; what's still rough is decorative markup.

### Framing correction

The earlier "`\x13 <len> <text>`" hypothesis was slightly wrong — the lead-in
is a **fixed 2-byte sequence `\x13 \x37`**, not `\x13` alone (confirmed
against `<div class="Catchline">`, 23 bytes, length byte `\x17` = 23 exactly).
Corrected rule: **`\x13 \x37 <len:1> <text>`**.

`\x08` was confirmed as "literal text run" — but only when what follows is
actually printable/UTF-8. When `\x08` precedes non-printable bytes (e.g. the
recurring 6-byte block `10 00 03 82 3a 01` seen before both `<TITLE>` in the
Preface and `<title>` in § 1.01's `<head>`), it's something else entirely —
likely an attribute/style-flag opcode that happens to reuse the byte value
0x08. The POC decoder resolves this by only treating `\x08`'s payload as text
if it starts with a printable byte; otherwise it falls through to the generic
"unknown opcode, skip one byte" fallback.

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
index in Phase 3.

### Known gaps in the POC decoder

- Boilerplate `<head>`/`<meta>` tags and a couple of `<link>` attributes come
  out mangled — they route through opcodes the decoder doesn't know, so the
  "skip one unknown byte at a time" fallback eats into them unevenly.
- `<CATCHLINE></CATCHLINE>` decodes **empty** in the body — the catchline
  text ("Definitions.") isn't duplicated inline here; it lives in the
  TOC/index block found in Phase 1 and is presumably substituted at render
  time. Confirms the JSON-sidecar plan should pull title/catchline from the
  index structures, not expect to find it in every document body.
- One isolated attribute corruption mid-document (`class="Text Intro  #<binary>Vietnam War:`
  instead of `class="Text Intro Justify"` before item (f)) — an unknown
  opcode landed inside a tag's attribute list. Notably this did **not**
  cascade or desync the rest of the decode — everything after it decoded
  correctly, which is a good sign the format is reasonably self-synchronizing
  even when an opcode is mishandled.

## Not yet investigated

- The exact terminator rule for `\x08` text runs, and the full byte-value
  vocabulary of control opcodes (Phase 2).
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
