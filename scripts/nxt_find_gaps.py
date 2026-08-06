"""Phase 2c: find index gaps via a third, independent signal.

Phase 4 found that F.S. 145.11 is silently absent from the citation index
(data/fs2025_citation_index.json) because *both* existing detection paths
failed for it: the Phase 3 <title> scan and the Phase 2b SectionNumber
recovery. Since the index-quality checks in nxt_build_index.py rely on
exactly those two signals, that category of loss is invisible to them --
its true prevalence across the full 26,317-document index was unknown.

This script adds a signal that doesn't depend on either: fs2025.nxt embeds
a "CatchlineIndex" table of contents near the front of each chapter, where
every section gets a self-referencing link:

    <a href="#!-- #ID=FS20250145.10 --#">145.10</a>

The href's #ID= citation and the link's own display text are redundant --
both encode the same chapter.section number. Requiring them to agree (the
"self-ref" check below) is what makes this signal independent of the
decoder/index-builder: it's a plain byte-level regex match against the raw
file, with a built-in corruption filter (a citation is only trusted if its
two independent encodings still agree -- page-boundary interruption
scrambles the digits, so a genuine match confirms this stretch of bytes
survived intact).

Any chapter.section number that (a) appears as a clean, confirmed
CatchlineIndex entry but (b) is absent from the built citation index is a
confirmed double-failure gap, the same category as F.S. 145.11.

Since Phase 2d this scans the *reassembled* documents rather than the raw
file (see scripts/nxt_depage.py). That matters in both directions: a
CatchlineIndex anchor split across a fragment boundary is no longer
scrambled, so more citations are confirmed rather than discarded, and the
index it is checked against is now derived from the same reassembly -- so
the two signals stay independent in what they read (TOC anchors vs.
<title> tags) without one of them silently working from damaged bytes.

This is throwaway analysis code, not part of the installable package.
"""

import json
import pathlib
import re
import sys

from nxt_depage import load_records

ANCHOR_RE = re.compile(rb'#ID=FS2025(\d{4})\.([0-9.]+) --#">\x08([0-9.]+)')


def find_catchline_citations(data: bytes) -> tuple[set[str], int]:
    """Scan for CatchlineIndex self-referencing anchors. Returns the set of
    confirmed (self-ref matches) citations, and a count of matches discarded
    because the two encodings disagreed (corruption, or a non-TOC anchor
    whose display text isn't the bare citation)."""
    confirmed = set()
    discarded = 0
    for m in ANCHOR_RE.finditer(data):
        chapter_raw, section, display = m.groups()
        chapter = int(chapter_raw)
        expected = f"{chapter}.{section.decode()}"
        if display.decode() != expected:
            discarded += 1
            continue
        confirmed.add(f"F.S. {expected}")
    return confirmed, discarded


def find_gaps(data: bytes, index: dict) -> list[str]:
    catchline_citations, discarded = find_catchline_citations(data)
    index_citations = {e["title"] for e in index["entries"] if e["title"].startswith("F.S. ")}
    gaps = sorted(
        catchline_citations - index_citations,
        key=lambda c: [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", c)],
    )
    print(f"CatchlineIndex citations found: {len(catchline_citations)} confirmed, "
          f"{discarded} discarded (corrupted or non-self-referencing)")
    print(f"Index F.S. citations: {len(index_citations)}")
    print(f"Confirmed gaps (in CatchlineIndex, absent from index): {len(gaps)}")
    return gaps


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    index_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path(
        "data/fs2025_citation_index.json"
    )

    data = b"".join(load_records(library / filename))
    index = json.loads(index_path.read_text())

    gaps = find_gaps(data, index)
    for g in gaps:
        print(f"  {g}")

    out_path = pathlib.Path("data/fs2025_gap_report.json")
    out_path.write_text(json.dumps({"gaps": gaps, "count": len(gaps)}, indent=1))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
