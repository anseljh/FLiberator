"""Phase 3: build a citation -> byte-offset index for a .nxt file.

Approach (see plans/re-plan.md Phase 3 and docs/nxt-format.md): rather than
reverse-engineering the pre-LPDD manifest block further (its sibling-ID list
turned out to be a local "recent neighbors" breadcrumb, not a reliable
per-document field -- most documents have no FS... ID within reach of it),
this leverages the already-validated Phase 2 decoder directly: decode just
enough of each LPDD-delimited document's <head> to read its <title> tag,
which reliably carries the citation (e.g. "F.S. 1.01", "CHAPTER 1").

A single re.finditer pass locates all LPDD positions up front (O(n) total)
rather than repeated .find() calls (which would be O(n^2) on a 240MB file).

This is throwaway analysis code, not part of the installable package.
"""

import json
import pathlib
import re
import sys

from nxt_decode_poc import decode

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
HEAD_WINDOW = 2000


def build_index(data: bytes) -> dict:
    lpdd_positions = [m.start() for m in re.finditer(rb"LPDD", data)]
    body_starts = [p + 4 for p in lpdd_positions] + [len(data)]

    entries = []
    untitled = 0
    for i in range(len(body_starts) - 1):
        body_start = body_starts[i]
        body_end = body_starts[i + 1]
        head_end = min(body_end, body_start + HEAD_WINDOW)
        html, _ = decode(data, body_start, head_end)
        m = TITLE_RE.search(html)
        title = m.group(1).strip() if m else None
        if title is None:
            untitled += 1
        entries.append(
            {"title": title, "offset": body_start, "length": body_end - body_start}
        )

    return {
        "total_documents": len(entries),
        "untitled": untitled,
        "entries": entries,
    }


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

    data = (library / filename).read_bytes()
    index = build_index(data)

    print(f"{filename}: {index['total_documents']} documents, {index['untitled']} untitled")

    by_title = {e["title"]: e for e in index["entries"] if e["title"]}
    for sample in ("Preface, Florida Statutes 2025", "CHAPTER 1", "F.S. 1.01", "F.S. 1.02"):
        e = by_title.get(sample)
        print(f"  {sample!r} -> {e}")

    if out_path:
        out_path.write_text(json.dumps(index, indent=1))
        print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
