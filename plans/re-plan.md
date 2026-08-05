# Plan: Reverse-engineer the Folio NXT `.nxt` Infobase format

## Context

FLiberator's pipeline (per README) is: download → unzip → convert `.NXT` → `.FFF` → convert `.FFF` → XML (via `folioxml`). Step 3 (NXT → FFF) is currently a TBD with no known tooling. Before writing any conversion code, we need to understand what's actually inside `fs2025.nxt` (240MB, the 2025 Florida Statutes) well enough to extract its content programmatically.

This plan is for the **analysis** phase only — producing a working understanding of the format (and ideally a proof-of-concept decoder), not a production converter.

### What we already know (from hands-on inspection this session)

This isn't a cold start — direct inspection of `FLLawDL2025/Library/*.nxt` and the bundled installer already surfaced concrete, load-bearing facts:

1. **File header.** Every `.nxt` file (checked `uscon.nxt` and `fs2025.nxt`) starts with an identical 78-byte ASCII string: `Copyright (c) 1991-20XX, Rocket Software, Inc.  All Rights Reserved. Infobase\r\n`, then null-padded out to offset `0xE0`. This confirms "Infobase" as the internal format name (Rocket Folio's product lineage, per the Wikipedia Folio Corporation history the user linked).
2. **Fixed binary header, `0xE0`–~`0x200`.** Contains a mix of (a) apparently constant fields shared across otherwise-unrelated files (e.g. 8 identical bytes at `0xE8`: `fc ae 56 89 62 74 bf ae` — likely a format/version constant), and (b) per-file fields that vary (an 8-byte value at `0x100` that looks like a hash/GUID, and what appear to be little-endian `uint32` count fields around `0x1B0`–`0x1BF`, e.g. `39` for `uscon.nxt` vs `26348` for `fs2025.nxt` — plausibly a document/record count worth confirming against known section counts).
3. **The content is tokenized HTML, not opaque binary.** Large stretches of both files are near-verbatim HTML/CSS with occasional 1–4 byte binary opcodes spliced in. Confirmed by locating actual statute text: searching `fs2025.nxt` for distinctive phrases from § 1.01 (fetched live from leg.state.fl.us as ground truth — see below) landed at byte offsets ~70,800 and ~106,300, e.g.:
   ```
   <div class="CatchlineIndex"><div class="IndexItem">\x15\x04\x01\x05\x13\x37%<a href="#!-- #ID=FS20250001.01 --#">\x081.01\x13\x37\x04</a>...
   ...<div class="Catchline">\x08Definitions.\x13\x37#</div></div>...
   ```
   and in the body text:
   ```
   <div class="Subsection"><span class="Number">\x08(9)...<span class="Text Intro Justify">\x08Crude turpentine gum (oleoresin)...
   ```
   Pattern observed: `\x13 <len-byte> <len bytes of literal tag text>` appears to open markup tokens (e.g. `\x13\x25` + 37 bytes = the 37-character `<a href=...>` tag — length checks out exactly), `\x08` precedes plain-text content runs, and `\x15` appears to mark short fixed/variable binary fields (possibly paragraph or style markers) — sample size is only ~5 instances, so these rules are hypotheses, not confirmed.
   - Critically, **per-section anchor IDs are embedded literally**: `#!-- #ID=FS20250001.01 --#` ties directly to the citation scheme (year + chapter + section). This is very likely the key for building a citation → byte-offset index.
4. **Ground truth source confirmed reachable.** `WebFetch` on the URL the user gave (`.../Sections/0001.01.html`) returns clean section text (§ 1.01 "Definitions", 19 numbered subsections). This is a reliable oracle for validating any decoder — and it's live-fetchable per-section, so we can automate diffing reconstructed text against it for many sections, not just one.
5. **The bundled Windows binaries are a red herring for the core engine.** `copy/Work-Set.exe`, `Serv-Go.exe`, `Serv-Out.exe`, and `copy/wbdIB44I.dll` / `WBDLA44I.DLL` / `wwwnt34i.dll` are **WinBatch**-compiled installer/service-management helpers (strings match WinBatch's runtime almost exactly: `"Dialog: ..."` error boilerplate, `"----- Extender loaded: %s"`, `xAllocPrintf`, `wntServerList`) — they configure a local web server, they don't parse Infobase files. One useful lead found in `fs2025.nxt` itself though: the string `NextPage US English Server Extension Module. Version 2.01` and a reference to `nfoenu6.dll` — the actual Folio/NXT rendering engine DLL name, which is *not* present in this download (it'd be `Library/Library.libinst` / the InstallShield cabs, or a full desktop/server install). Not required for static analysis, but worth knowing if dynamic analysis becomes necessary.
6. **`data1.cab`/`data2.cab`** (InstallShield cabinets) are unextracted in the current environment (no `cabextract`/`unshield`/`7z` available) and likely contain the real NXT engine binaries. Not touched yet.
7. Two of the referenced background pages didn't load in this session — `justsolve.archiveteam.org/wiki/Folio_Infobase` (connection refused) and the Apriorit blog post (403). Worth a retry (or Wayback Machine) early in execution since ArchiveTeam often documents prior art for legacy formats.

### Files available as test corpus

`Library/` has 13 `.nxt` files ranging 319KB (`uscon.nxt`, US Constitution — small, well-known ground truth) up to 240MB (`fs2025.nxt`). Recommend using `uscon.nxt` as the primary small-scale target for header/opcode work (fast iteration, content is public and short — 7 articles + 27 amendments), then validating against `fs2025.nxt` where we already have a confirmed offset for § 1.01.

## Goals

1. Produce a documented, reasonably confident model of the `.nxt` container: file header fields, the tokenized-markup opcode set, and how individual "documents" (statute sections / constitutional articles) are delimited and located.
2. Produce a working Python proof-of-concept script that can extract at least one full, correctly-reconstructed section (§ 1.01, cross-checked against the live page) from `fs2025.nxt`, and ideally all articles/amendments from `uscon.nxt`.
3. Leave enough written notes (a `FORMAT.md` or `docs/nxt-format.md` in the repo) that the next session — or the actual converter implementation — doesn't have to re-derive this.

## Approach

### Phase 1 — Corpus survey (breadth, cheap)
- Write a small script (`scripts/nxt_survey.py` or similar, throwaway is fine) that, for every `.nxt` file in `Library/`, dumps: file size, the full header region (`0x00`–`0x200`) as hex, and a byte-frequency histogram of the first N MB. Goal: confirm which header fields are constant (format/version markers) vs. per-file (counts, hashes), and get a first-pass guess at what the `~0x1B0` count field represents (compare against known section/article counts for `uscon.nxt` and other small files like `sct2025.nxt`, `TT2025.nxt`).
- Run `strings -n 8` (both 8-bit and `-e l` for UTF-16) across each file and skim for more structural vocabulary (we already found `Folio Views`, `PruneHitThreshold`, `LengthNormalization`, `__MAINSET`/`__PROPSET`, `binaryindex`/`strindex` — some of this may belong to a search-index region later in the file, worth locating).

### Phase 2 — Decode the tokenized-markup layer (the main event)
- Focus on `uscon.nxt` first (small, fast to iterate on).
- Write a byte-scanner that walks the file and, at every occurrence of the candidate opcodes found so far (`\x13`, `\x08`, `\x15`, and whatever else Phase 1's histogram surfaces as suspiciously frequent low-value bytes), records: the opcode byte, the byte(s) immediately following, and whether treating the next byte as a length + literal run produces valid-looking ASCII/UTF-8 text. This is exactly the "formulate and test a theory, then check it against many samples" loop the Wikibooks RE guide describes — do it programmatically across thousands of instances rather than eyeballing a handful.
- Specifically resolve:
  - Is `\x13 <len> <text>` consistent everywhere, and what's the max length (1-byte length caps at 255 — check for a 2-byte-length variant for longer tags)?
  - What terminates a `\x08`-prefixed text run — a following control byte, or an implicit length encoded elsewhere?
  - What is `\x15` doing — decode the 3–4 trailing bytes seen so far (`04 01 05`, `04 01 06`, `01 01 <UTF-8 char>`) across many more instances to find the pattern (paragraph/style markers? entity references?).
- Deliverable: a decoder that, given a byte range, reconstructs literal HTML — essentially "decompressing" the tokenized markup back to plain HTML text.

### Phase 3 — Document boundaries & the citation index ✅ done
- **Done, in two iterations** — see `docs/nxt-format.md` "Phase 3" section and `scripts/nxt_build_index.py`. v1 indexed by decoding a window after each `LPDD` marker; looked solid (26,306 documents, 96% titled, near-matched the `0x1BC` header field) until spot-checking one "untitled" entry against the live statute site revealed `LPDD` doesn't reliably mark one document — long sections span multiple `LPDD` pages as untitled continuations, and short sections can share a page with no `LPDD` between them at all (confirmed: § 626.6215 and § 626.631 sit back-to-back in one page, and v1 silently merged them under 626.6215's truncated entry while missing 626.631 entirely). v2 drops `LPDD` and the decoder entirely for index-building: a single regex pass finds every literal `<title>` occurrence directly (title text survives as literal bytes even when the surrounding head is otherwise garbled), and each match becomes a document boundary, with length = distance to the next title. Runs in 0.3 seconds, finds 26,197 correctly-bounded documents, zero duplicate section citations. ~3.8% still silently merge more than one document (same root cause, now smaller and better-characterized: the `<title>` tag itself occasionally hits the same decode edge case, rather than just its preamble) — documented as a known gap rather than chased further. The Phase 1 "0x1BC = document count" hypothesis is now discounted — the earlier near-match to v1's count was coincidental. Index saved to `data/fs2025_citation_index.json`.

### Phase 4 — Validation harness
- Build a small script that: picks N statute section IDs, extracts the corresponding text via the Phase 2/3 decoder, fetches the equivalent page live via `WebFetch` (as already proven to work for § 1.01), and diffs the two (strip HTML tags for a first-pass text-only comparison, since exact HTML fidelity is a stretch goal).
- Pick sections deliberately covering edge cases: a simple one (1.01, already done), one with a table, one with historical/amendment notes, one with cross-references to other chapters, one with non-ASCII characters (the `\x15`-prefixed special-character opcode gives a hint these exist).
- This harness becomes the regression check for any future decoder changes — cheap to keep running as understanding improves.

### Phase 5 — Write up findings & decide the pipeline shape
- Write `docs/nxt-format.md` documenting the header layout, opcode table, and document/anchor scheme discovered, with byte-offset examples (like the ones above) so it's independently verifiable.
- Explicit decision point to flag back to the user once Phases 1–4 are done: the original README pipeline assumes NXT → FFF (via unknown tooling) → XML (via `folioxml`). Given that `.nxt` already contains tokenized HTML with usable structure, it may be simpler to decode NXT → HTML/XML **directly**, skipping the FFF intermediate and `folioxml` entirely. Don't decide this now — surface it as a fork once there's enough data to judge which path is less work.

## Proposed remaining phases (post Phase 1-3, not yet started)

Phases 1-3 above are done (Phase 3 in two iterations — see `docs/nxt-format.md`).
Phase 4 (harness) and Phase 5 (write-up/decision) as originally scoped are
still open, folded into the numbering below alongside newly-identified work.
None of these have been started; order is a suggestion, not a commitment.

### Phase 2b — Decode the boilerplate back-reference opcode
- Targeted fix for the Phase 3 v2 "~3.8% merge" gap. Investigation (see
  `docs/nxt-format.md`, "The 3.8% merge gap: likely cause found") found that
  the merges aren't random corruption: right after `</html>`, a short
  (5-13 byte) binary marker stands in for what should be ~230 bytes of
  literal DOCTYPE/head/link boilerplate, and the decoder's dumb fallback
  desyncs a few bytes into the following title token as a result.
- Next step: bucket the ~991 known boundary sequences by shape/length,
  confirm the byte immediately after each one always lands inside a
  `\x13\x37<len>` token, and add one new opcode rule for it. Small and
  well-scoped — high confidence of closing most of the gap without further
  open-ended archaeology.

### Phase 4 — Validation harness (as originally scoped above)
- Not yet built. Depends on Phase 2b to avoid the harness flagging known,
  already-understood merge cases as new failures.

### Phase 5 — Pipeline decision write-up (as originally scoped above)
- The direct NXT → HTML+JSON path (skipping `.fff`/`folioxml` entirely) is
  the de facto direction of all work so far but hasn't been formally
  recorded. Update README.md and CLAUDE.md to state this decision plainly
  and retire the FFF/folioxml language from the "planned pipeline"
  description.

### Phase 6 — Automate download + unzip
- Currently `FLLawDL2025/` is manually populated. Build the actual step
  1-2 of the original pipeline: fetch the zip from the leg.state.fl.us
  download page into the git-ignored working folder, unzip it, with basic
  handling for a new year's URL/filename changing.

### Phase 7 — Promote scripts/ into the installable package
- `src/fliberator/` is still just a scaffold (`__version__` only). Move the
  decoder (`nxt_decode_poc.py`), index builder (`nxt_build_index.py`), and
  eventually the downloader into real modules under `src/fliberator/`, add
  a CLI entry point, and add unit tests (decoder opcode rules, index
  builder against a small fixture) to replace ad hoc script runs.
- Do this after Phase 2b so the decoder logic being promoted isn't
  immediately stale.

### Phase 8 — Extend to the rest of the corpus
- All work so far targets `fs2025.nxt` only. The other 12 `.nxt` files
  (`flcnst2025.nxt` = FL Constitution, `uscon.nxt` = US Constitution, plus
  various index/table files whose purpose is still guessed rather than
  confirmed — see the Corpus table above) need the same decode+index
  treatment, or an explicit decision that some of them (e.g. the index
  files) aren't in scope for FLiberator's output.

### Phase 9 — Decide and implement the actual output shape
- The "liberated" deliverable format has never been decided — one HTML
  file per section? A single structured JSON/SQLite dataset keyed by
  citation? Depends on Phase 4 (validated content) and Phase 7 (a real
  package to emit it from). This is the phase that turns "we can decode
  this" into "here is the liberated Florida Statutes."

## Tooling notes

- Pure Python (stdlib `struct`/regex) is sufficient for Phases 1–3; no new runtime dependencies needed yet. If the opcode grammar turns out to be more of a real mini-language (nested/recursive), consider `construct` or a Kaitai Struct `.ksy` definition — Kaitai in particular is nice here because a `.ksy` file *is* the documentation and generates a visual structure browser, which is valuable for a format nobody else has documented.
- `cabextract`/`unshield` aren't installed; only worth adding if Phase 2 static analysis stalls and dynamic analysis (running the real NXT engine under Wine, extracted from `data1.cab`/`data2.cab`) becomes necessary. Treat as a fallback, not a starting point.
- Retry the ArchiveTeam and Apriorit URLs early (both failed to fetch this session) — ArchiveTeam in particular sometimes documents prior art or existing partial parsers for legacy formats like this.
- Test-driven by construction: because we can fetch ground truth per-section from leg.state.fl.us on demand, every claim about the format should be checked against real reconstructed text, not just "the bytes look plausible."

## Verification

- Phase 2/4 harness (extract → strip tags → diff against live-fetched ground truth) is the end-to-end check. Success criterion for this analysis phase: § 1.01 and at least 2–3 other sections from `fs2025.nxt`, plus all articles of `uscon.nxt`, extract with text matching the live site (modulo whitespace/HTML-entity normalization).
- No existing test suite needs to change; this work produces new throwaway/analysis scripts (not yet part of the `fliberator` package) plus the `docs/nxt-format.md` writeup.
