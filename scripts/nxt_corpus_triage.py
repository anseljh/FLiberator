"""Phase 8 triage: does the page/fragment model generalize past fs2025.nxt?

Everything through Phase 4b was measured against `fs2025.nxt` alone. That
left an open risk rather than a curiosity: if `flcnst2025.nxt` (the Florida
Constitution) or `lf2025.nxt` (the session laws) hold real primary content
and reassembly quietly breaks on them, that is content loss in a file
FLiberator would publish.

This script runs the full storage layer (`nxt_depage.reconstruct`) and
content layer (`nxt_decode_poc.decode`) over every `.nxt` file in a Library
directory and reports, per file:

  records      documents reassembled
  closed       share whose decoded markup ends in </html>
  unclosed     elements left open at end of document, summed
  mismatched   close tags with no matching open tag, summed
  unknown      bytes that fell through to the decoder's skip-one-byte
               fallback, as a share of reassembled content
  title        the document <title>, which is what actually identifies
               what a file holds -- the filenames are abbreviations and
               several were guessed wrong before this ran

Findings, run over the frozen FLLawDL2025 reference copy:

  * All 13 files reassemble with **zero** chain conflicts. The page and
    fragment model is a property of the container, not of fs2025.nxt.
  * 12 of 13 are tokenized markup and decode to well-formed HTML: 0
    unclosed and 0 mismatched elements across 46,520 documents, except
    for one 2MB record noted below. The 13th is a PDF payload.
  * Decoding surfaced a real defect invisible in fs2025.nxt -- see the
    0x15 field-marker note in nxt_decode_poc.py. fs2025.nxt was immune by
    luck, which is the whole argument for running the corpus.
  * The one structural outlier is lf2025.nxt record 197, Chapter 2025-198
    (the General Appropriations Act, 2,025,026 bytes decoded). It closes
    with </approp> rather than </html> and uses a custom tag vocabulary
    (<LAWBODY>, <LSECT>, <approp>). That is what the source contains, not
    a reassembly failure.

This is throwaway analysis code, not part of the installable package.
"""

import collections
import pathlib
import re
import sys
from html.parser import HTMLParser

from nxt_decode_poc import decode
from nxt_depage import reconstruct

LIBRARY = pathlib.Path("FLLawDL2025/Library")

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
VOID = {"br", "hr", "img", "input", "meta", "link", "source", "col", "area", "base"}

# Not tokenized markup: a single record wrapping a PDF byte stream, so the
# element and unknown-byte checks below are meaningless for it.
BINARY_PAYLOAD = {"Law_Download_Help_PDF.nxt"}


class Structure(HTMLParser):
    """Count elements left open, and close tags matching nothing."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.mismatched = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.mismatched += 1


def triage(path: pathlib.Path) -> dict:
    records = reconstruct(path.read_bytes())
    result = {
        "records": len(records),
        "content_bytes": sum(len(r) for r in records),
        "unknown": 0,
        "closed": 0,
        "unclosed": 0,
        "mismatched": 0,
        "titles": collections.Counter(),
    }
    if path.name in BINARY_PAYLOAD:
        result["titles"]["(PDF payload, not markup)"] = len(records)
        return result

    for record in records:
        html, stats = decode(record, 0, len(record))
        result["unknown"] += stats["unknown_bytes_skipped"]
        if html.rstrip().lower().endswith("</html>"):
            result["closed"] += 1
        checker = Structure()
        checker.feed(html)
        checker.close()
        result["unclosed"] += len(checker.stack)
        result["mismatched"] += checker.mismatched
        match = TITLE_RE.search(html)
        result["titles"][match.group(1).strip() if match else "(no title)"] += 1
    return result


def main() -> None:
    library = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else LIBRARY
    paths = sorted(library.glob("*.nxt"), key=lambda p: p.stat().st_size)

    header = f"{'file':<26} {'records':>8} {'closed':>7} {'uncl':>5} {'mism':>5} {'unknown':>8}"
    print(header)
    print("-" * len(header))
    totals: collections.Counter = collections.Counter()
    titles: dict[str, collections.Counter] = {}

    for path in paths:
        try:
            r = triage(path)
        except Exception as exc:  # a reassembly failure is the headline result
            print(f"{path.name:<26} !! FAILED: {exc!r}")
            totals["failed"] += 1
            continue
        share = r["closed"] / r["records"] if r["records"] else 0
        rate = r["unknown"] / r["content_bytes"] if r["content_bytes"] else 0
        print(
            f"{path.name:<26} {r['records']:>8,} {share:>6.1%} "
            f"{r['unclosed']:>5} {r['mismatched']:>5} {rate:>7.3%}"
        )
        titles[path.name] = r["titles"]
        for key in ("records", "unclosed", "mismatched"):
            totals[key] += r[key]

    print(
        f"\n{len(paths)} files, {totals['failed']} reassembly failures, "
        f"{totals['records']:,} documents, "
        f"{totals['unclosed']} unclosed and {totals['mismatched']} mismatched elements"
    )

    print("\nWhat each file holds (by document <title>, not by filename):")
    for name, counter in titles.items():
        top = ", ".join(f"{t!r}×{n:,}" for t, n in counter.most_common(2))
        extra = f" (+{len(counter) - 2:,} more distinct)" if len(counter) > 2 else ""
        print(f"  {name:<26} {top}{extra}")


if __name__ == "__main__":
    main()
