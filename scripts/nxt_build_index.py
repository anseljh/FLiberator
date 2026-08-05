"""Phase 3: build a citation -> byte-offset index for a .nxt file.

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
3. This version: titles are stored as literal, undamaged bytes even when
   the DOCTYPE/meta preamble around them is garbled (confirmed against the
   626.631 case above) -- so skip LPDD and the decoder entirely for index
   purposes. Scan the whole file directly for literal <title>...</title> /
   <TITLE>...</TITLE> byte sequences (every title tag is immediately
   preceded by a 3-byte \x13\x37<len> opcode, confirmed against a 2000-tag
   sample with zero exceptions) and use each match's position as a new
   document boundary. A document's end is simply the next document's start
   (or EOF) -- this is what makes multi-page sections come out with their
   correct full length automatically, without needing to understand paging
   at all.

This is throwaway analysis code, not part of the installable package.
"""

import json
import pathlib
import re
import sys

TITLE_RE = re.compile(rb"<title>(.*?)</title>|<TITLE>(.*?)</TITLE>", re.DOTALL)
DOCTYPE_LOOKBACK = 300


def clean_title(raw: bytes) -> str:
    """Strip the trailing \x13\x37<len> opcode (and anything after) that the
    non-greedy regex sometimes pulls in before it finds the literal closing
    tag bytes."""
    cut = raw.find(b"\x13")
    if cut != -1:
        raw = raw[:cut]
    return raw.decode("utf-8", errors="replace").strip()


def find_doc_start(data: bytes, title_pos: int) -> int:
    """Best-effort: find this document's own <!DOCTYPE.../<HTML> opening
    within a bounded lookback window, so the index entry captures the head
    boilerplate too. Falls back to the title tag's own position (losing
    only boilerplate, never body content) if no marker is found nearby."""
    window_start = max(0, title_pos - DOCTYPE_LOOKBACK)
    window = data[window_start:title_pos]
    best = -1
    for marker in (b"<!DOCTYPE", b"<HTML>\r\n<HEAD>\r\n"):
        i = window.rfind(marker)
        if i != -1:
            best = max(best, window_start + i)
    return best if best != -1 else title_pos


def build_index(data: bytes) -> dict:
    matches = list(TITLE_RE.finditer(data))
    entries = []
    for m in matches:
        raw_title = m.group(1) if m.group(1) is not None else m.group(2)
        title = clean_title(raw_title)
        offset = find_doc_start(data, m.start())
        entries.append({"title": title, "offset": offset})

    for i, e in enumerate(entries):
        next_offset = entries[i + 1]["offset"] if i + 1 < len(entries) else len(data)
        e["length"] = next_offset - e["offset"]

    return {"total_documents": len(entries), "entries": entries}


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

    data = (library / filename).read_bytes()
    index = build_index(data)

    print(f"{filename}: {index['total_documents']} documents")

    by_title = {e["title"]: e for e in index["entries"]}
    for sample in (
        "Preface, Florida Statutes 2025",
        "CHAPTER 1",
        "F.S. 1.01",
        "F.S. 1.02",
        "F.S. 626.6215",
        "F.S. 626.631",
    ):
        e = by_title.get(sample)
        print(f"  {sample!r} -> {e}")

    if out_path:
        out_path.write_text(json.dumps(index, indent=1))
        print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
