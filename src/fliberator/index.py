"""A citation -> document index over a reassembled `.nxt` file.

One entry per document: its title, its position in `depage.reconstruct()`'s
output, and its length. There is deliberately no byte offset into the
original file -- a document's bytes are scattered across a chain of
fragments on non-adjacent pages, so "where it starts" isn't a number.

This is what the validation harnesses in `scripts/` consume (they read the
JSON this writes, at `data/fs<year>_citation_index.json`), and it is
separate from `documents.py`, which builds the *output* identity scheme.
The two answer different questions: this one indexes every record in the
file, including the ones that aren't sections; `documents.py` selects and
orders only what gets published.

Getting here took six versions, five of which existed only to work around
a problem that turned out not to be real. Versions 1-4 all read the file as
a flat byte stream and therefore had to *infer* document boundaries from
bytes where the paged store's own metadata had been decoded as if it were
content: a sibling-ID list that turned out to be a local breadcrumb, an
LPDD-marker scan that broke on both long and short documents, an unbounded
`<title>(.*?)</title>` regex that silently merged documents whenever a
closing tag was destroyed ("closing-tag theft"), and finally a bounded
title scan plus orphaned-`<div class="Section">` recovery. Phase 2d
(`depage.py`) removed the cause: reassemble the fragments first and every
record contains exactly one title and at most one Section div, so a record
*is* a document and none of that apparatus has anything left to do. See
docs/nxt-format.md "Phase 2c"/"Phase 2d" for the full history.

What survives from it is the cross-check below: a document's `<title>` and
its `<span class="SectionNumber">` are independent encodings of the same
citation, so a disagreement means a document was assembled wrong. It reads
0 across the corpus, and it is the check that would notice if that ever
stopped being true.
"""

import argparse
import collections
import json
import pathlib
import re
import sys

from . import download, emit
from .depage import load_records

# Every clean title's text is immediately followed by the exact 3-byte
# opcode + 8 literal bytes `\x13\x37\x08</title>` ("</title>" is always
# 8 bytes, so a well-formed closer's length prefix is always the 1-byte
# form). Requiring that exact sequence after a *bounded* run of title text
# is what stops a destroyed closing tag from swallowing the next document:
# the match simply fails here rather than searching forward. The 80-byte
# cap is well above the longest real title ("Preface, Florida Statutes
# 2025", 31 bytes) and far below the multi-KB gap any real interruption
# leaves.
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
    in `depage.reconstruct()`'s output, which is what callers slice with."""
    entries = []
    mismatched = []
    for i, record in enumerate(records):
        match = TITLE_RE.search(record)
        if match is None:
            entries.append({"title": f"[untitled record {i}]", "record": i, "length": len(record)})
            continue
        title = clean_title(match.group(1) if match.group(1) is not None else match.group(2))
        entries.append({"title": title, "record": i, "length": len(record)})

        div = SECTION_DIV_RE.search(record)
        expected = citation_number(title)
        if div is not None and expected is not None:
            number = SECNUM_RE.search(record[div.start() : div.start() + 120])
            if number is not None and number.group(1).decode() != expected:
                mismatched.append((title, number.group(1).decode()))

    return {
        "total_documents": len(entries),
        "entries": entries,
        "title_vs_sectionnumber_mismatches": mismatched,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m fliberator.index",
        description="Build a citation -> document index for one .nxt file.",
    )
    parser.add_argument(
        "source",
        nargs="?",
        help="a .nxt file (default: the statutes file in --library)",
    )
    parser.add_argument(
        "--library",
        type=pathlib.Path,
        help="directory holding the .nxt files (default: the newest edition "
        "under download/; pass FLLawDL2025/Library for the frozen reference copy)",
    )
    parser.add_argument("--out", type=pathlib.Path, help="where to write the JSON index")
    args = parser.parse_args(argv)

    library = args.library or download.default_library()
    if args.source is None:
        if library is None:
            parser.error("no --library found and no source given")
        source, year = emit.resolve(library, "fs")
        out = args.out or pathlib.Path(f"data/fs{year}_citation_index.json")
    else:
        source = pathlib.Path(args.source)
        source = source if source.is_file() else (library or pathlib.Path()) / source
        out = args.out or pathlib.Path(f"data/{source.stem}_citation_index.json")

    index = build_index(load_records(source))
    mismatches = index["title_vs_sectionnumber_mismatches"]
    print(f"{source.name}: {index['total_documents']:,} documents")
    print(f"  title vs. SectionNumber mismatches: {len(mismatches)} {mismatches[:5]}")

    counts = collections.Counter(e["title"] for e in index["entries"])
    duplicates = sorted(t for t, n in counts.items() if n > 1 and not t.startswith("CHAPTER"))
    print(f"  duplicate non-CHAPTER titles: {len(duplicates)} {duplicates[:5]}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(index, indent=1))
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
