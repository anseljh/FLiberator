"""Phase 3: build a citation -> document index for a .nxt file.

Approach history (see docs/nxt-format.md for the full story):

1. First attempt used the pre-LPDD manifest block's sibling-ID list --
   abandoned, it's a local "recent neighbors" breadcrumb, not a reliable
   per-document field.
2. Second attempt decoded a bounded window right after each LPDD marker and
   read its <title> tag -- worked for ~96% of documents, but LPDD turned out
   not to reliably mark "one document": long sections span multiple LPDD
   pages (continuations, no title of their own), and conversely a single
   LPDD page can contain more than one complete document back-to-back with
   no fresh LPDD between them (confirmed: FS 626.6215 and FS 626.631 sit in
   the same LPDD-to-LPDD span, and 626.631's own <head> preamble is garbled
   in a way the Phase 2 decoder can't parse, even though 626.631 is a
   perfectly normal, complete document).
3. Third attempt (v2): titles are stored as literal, undamaged bytes even
   when the DOCTYPE/meta preamble around them is garbled (confirmed against
   the 626.631 case above) -- so skip LPDD and the decoder entirely for
   index purposes. Scan the whole file directly for literal
   <title>...</title> / <TITLE>...</TITLE> byte sequences (every title tag
   is immediately preceded by a 3-byte \x13\x37<len> opcode, confirmed
   against a 2000-tag sample with zero exceptions) and use each match's
   position as a new document boundary. Left ~3.8% of documents (991 of
   26,197) silently merged into their predecessor's entry: investigation
   (see docs/nxt-format.md, "The 3.8% merge gap") found this isn't the same
   opcode-desync bug as everywhere else -- it's page/record-boundary marker
   bytes getting spliced into the *middle* of a literal text run (confirmed:
   one case shows a single 239-byte DOCTYPE token cut off after ~29 bytes by
   a second, unrelated binary marker, then resuming into a completely
   different document's body text). That's a real paging model, not a
   single missing opcode rule -- not worth solving in general for an
   index-building pass.
4. v3 sidestepped the paging question entirely for the documents it breaks:
   `<div class="Section">` and the `<span class="SectionNumber">` text
   immediately inside it survive intact even when the `<title>` tag itself
   is destroyed, so keep the v2 title scan as-is and separately recover any
   `<div class="Section">` that isn't the first one inside a title-scan
   entry's span. That closed most of the gap, but v2's non-greedy
   `<title>(.*?)</title>` regex has a sharper problem than "some titles are
   destroyed": when a title's own closing tag is the thing destroyed, the
   regex doesn't fail to match -- it keeps searching *forward*, past the
   corruption, until it finds some *later* document's closing tag, and
   silently merges both documents into one entry mislabeled with the first
   document's title ("closing-tag theft" -- see docs/nxt-format.md
   "Phase 2c"). v3 patched around this twice: retitling entries whose first
   Section div's SectionNumber didn't match their own title (recovers the
   *stolen* document but only by discarding the *thief*'s real identity),
   then extending orphan-recovery to CHAPTER/Preface entries specifically
   (which can never legitimately own a Section div). Both patches were
   real improvements (95 confirmed gaps -> 41 -> 28) but couldn't recover
   both sides of a theft pair when neither had a separate copy elsewhere.
5. This version (v4) fixes the root cause instead of patching around it.
   Every clean, undamaged title in the corpus has its citation text
   immediately followed by the *exact* 3-byte opcode + 8 literal bytes
   `\x13\x37\x08</title>` (confirmed: "</title>" is always exactly 8
   bytes, so a well-formed closer's length prefix is always the 1-byte
   form). `TITLE_RE` now requires that exact sequence immediately after a
   bounded run of title text (an 80-byte cap, well above the longest real
   title seen -- "Preface, Florida Statutes 2025" at 31 bytes -- but far
   below the multi-KB gap any real interruption leaves), instead of
   `.*?</title>` with no bound. When a title's closer is destroyed, this
   simply fails to match *at that position* -- no swallowing, no
   mislabeling, no entry at all for the broken title. The corresponding
   real content (if any is recoverable) falls to `find_orphaned_sections`
   exactly like content behind a fully destroyed title always has.
   `find_orphaned_sections` now applies one *uniform* ownership rule
   instead of the two ad hoc v3 patches (see its own docstring for why
   only the *first* div in a span, not "the first matching div anywhere
   in the span," can ever be silently owned). Result: confirmed gaps via
   `scripts/nxt_find_gaps.py` 28 -> 0. Spot-checked several previously
   broken citations against the live site (105.08, 15.16/15.182,
   44.404/44.406, 39.0142/39.0143, and the newly-discovered
   175.333/175.341 pair -- see its docstring) and all now decode
   correctly. Two of those (15.16, 44.404) now reach far enough into
   their own body to hit the pre-existing, separately-documented Phase 2b
   mid-token LPDD interruption -- real content loss inside a document
   body, not an index-boundary bug, and not new: their old (buggy,
   artificially short) span just didn't reach that far before.
6. v5 deletes nearly all of the above, because Phase 2d
   (`scripts/nxt_depage.py`) removed the problem those five versions were
   working around. Every one of them read `fs2025.nxt` as a flat byte
   stream, so every one of them had to guess at document boundaries in
   bytes where the file's paging metadata had been decoded as if it were
   content. Reassembling documents from the paged store first makes
   boundaries exact rather than inferred: all 26,306 reassembled records
   contain exactly one `<title>...</title>` and at most one
   `<div class="Section">`. So a record *is* a document, its title *is*
   its title, and the whole apparatus above -- the DOCTYPE lookback, the
   orphaned-section recovery, the stub-duplicate dedup, the ownership
   rule -- has nothing left to do. Measured against v4: garbled titles 0
   (unchanged), duplicate titles 1 -> 0 (`F.S. 559.921` was never
   genuinely duplicated -- it was one document counted twice by a scan
   that couldn't see where the first one ended), documents
   26,428 -> 26,306 (v4's count was inflated by the same effect).

This is throwaway analysis code, not part of the installable package.
"""

import collections
import json
import pathlib
import re
import sys

from nxt_depage import load_records

TITLE_RE = re.compile(
    rb"<title>([^\x13]{0,80})\x13\x37\x08</title>"
    rb"|<TITLE>([^\x13]{0,80})\x13\x37\x08</TITLE>",
    re.DOTALL,
)
SECTION_DIV_RE = re.compile(rb'<div class="Section">')
SECNUM_RE = re.compile(rb'class="SectionNumber">[^0-9]{0,2}([0-9][0-9.]*)')


def clean_title(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def citation_number(title: str) -> str | None:
    return title.removeprefix("F.S. ") if title.startswith("F.S. ") else None


def build_index(records: list[bytes]) -> dict:
    """One entry per reassembled document. `record` is the document's index
    in `nxt_depage.reconstruct()`'s output, which is what callers should
    slice with -- there is no meaningful byte offset into the original file
    any more, since a document's bytes are scattered across a chain of
    fragments on non-adjacent pages."""
    entries = []
    mismatched = []
    for i, record in enumerate(records):
        m = TITLE_RE.search(record)
        if m is None:
            entries.append({"title": f"[untitled record {i}]", "record": i, "length": len(record)})
            continue
        title = clean_title(m.group(1) if m.group(1) is not None else m.group(2))
        entries.append({"title": title, "record": i, "length": len(record)})

        # Cross-check the title against the document's own SectionNumber.
        # These are independent encodings of the same citation, so a
        # disagreement means a document got assembled wrong.
        div = SECTION_DIV_RE.search(record)
        expected = citation_number(title)
        if div is not None and expected is not None:
            num = SECNUM_RE.search(record[div.start() : div.start() + 120])
            if num is not None and num.group(1).decode() != expected:
                mismatched.append((title, num.group(1).decode()))

    return {
        "total_documents": len(entries),
        "entries": entries,
        "title_vs_sectionnumber_mismatches": mismatched,
    }


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

    records = load_records(library / filename)
    index = build_index(records)
    mismatches = index["title_vs_sectionnumber_mismatches"]

    print(f"{filename}: {index['total_documents']} documents")
    print(f"  title vs. SectionNumber mismatches: {len(mismatches)} {mismatches[:5]}")

    counts = collections.Counter(e["title"] for e in index["entries"])
    dupes = sorted(t for t, n in counts.items() if n > 1 and not t.startswith("CHAPTER"))
    print(f"  duplicate non-CHAPTER titles: {len(dupes)} {dupes[:5]}")

    by_title = {e["title"]: e for e in index["entries"]}
    for sample in (
        "Preface, Florida Statutes 2025",
        "CHAPTER 1",
        "F.S. 1.01",
        "F.S. 15.16",
        "F.S. 15.182",
        "F.S. 44.404",
        "F.S. 559.921",
        "F.S. 626.631",
    ):
        print(f"  {sample!r} -> {by_title.get(sample)}")

    if out_path:
        out_path.write_text(json.dumps(index, indent=1))
        print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
