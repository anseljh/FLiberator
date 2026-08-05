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
4. This version (v3): sidesteps the paging question entirely for the
   documents it breaks. `<div class="Section">` and the
   `<span class="SectionNumber">` text immediately inside it survive intact
   in 100% of the 971 checked cases (verified against every merged entry in
   the v2 index), even when the `<title>` tag itself is destroyed. So: keep
   the v2 title scan as the primary source of documents, then separately
   scan for every `<div class="Section">` occurrence; any such div that
   isn't the first one inside a title-scan entry's span is an orphaned
   document that v2 silently swallowed. Split it out as its own entry with
   a synthetic title (`F.S. <number>`, read from `SectionNumber`) and flag
   it `"source": "section-number"` so it's distinguishable from a real
   decoded <title>.

This is throwaway analysis code, not part of the installable package.
"""

import json
import pathlib
import re
import sys

TITLE_RE = re.compile(rb"<title>(.*?)</title>|<TITLE>(.*?)</TITLE>", re.DOTALL)
SECTION_DIV_RE = re.compile(rb'<div class="Section">')
SECNUM_RE = re.compile(rb'class="SectionNumber">[^0-9]{0,2}([0-9][0-9.]*)')
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


def find_orphaned_sections(data: bytes, title_entries: list[dict]) -> list[dict]:
    """Any `<div class="Section">` that isn't the first one inside a
    title-scan entry's span was silently swallowed by v2. Split those out,
    synthesizing a title from their own SectionNumber text."""
    spans = []
    for i, e in enumerate(title_entries):
        end = title_entries[i + 1]["offset"] if i + 1 < len(title_entries) else len(data)
        spans.append((e["offset"], end))

    div_positions = [m.start() for m in SECTION_DIV_RE.finditer(data)]

    orphans = []
    di = 0
    n_divs = len(div_positions)
    for start, end in spans:
        while di < n_divs and div_positions[di] < start:
            di += 1
        first = True
        while di < n_divs and div_positions[di] < end:
            pos = div_positions[di]
            if first:
                first = False
            else:
                m = SECNUM_RE.search(data[pos : pos + 120])
                title = f"F.S. {m.group(1).decode()}" if m else f"[unrecovered section @ {pos}]"
                orphans.append({"title": title, "offset": pos, "source": "section-number"})
            di += 1

    return orphans


def drop_stub_duplicates(data: bytes, entries: list[dict]) -> tuple[list[dict], int]:
    """Some real <title> matches are stubs: their whole body, not just the
    preamble, was swallowed by a page-boundary interruption right after the
    title, so the entry's span never reaches a <div class="Section"> at all.
    When that happens the section's real content still gets recovered
    separately by find_orphaned_sections, so the title ends up on two
    entries -- one empty stub, one real. When exactly that pattern holds for
    a title (excludes CHAPTER N headers, which legitimately repeat as
    part-boundary markers with no Section div of their own), drop the
    stub(s) and keep the entry/entries that actually contain a section."""
    ordered = sorted(entries, key=lambda e: e["offset"])
    for i, e in enumerate(ordered):
        end = ordered[i + 1]["offset"] if i + 1 < len(ordered) else len(data)
        e["_has_section"] = b'<div class="Section">' in data[e["offset"] : end]

    by_title: dict[str, list[dict]] = {}
    for e in ordered:
        by_title.setdefault(e["title"], []).append(e)

    drop_ids = set()
    for title, group in by_title.items():
        if len(group) < 2 or title.startswith("CHAPTER"):
            continue
        has = [e for e in group if e["_has_section"]]
        hasnt = [e for e in group if not e["_has_section"]]
        if has and hasnt:
            drop_ids.update(id(e) for e in hasnt)

    kept = [e for e in ordered if id(e) not in drop_ids]
    for e in kept:
        del e["_has_section"]
    return kept, len(drop_ids)


def build_index(data: bytes) -> dict:
    matches = list(TITLE_RE.finditer(data))
    title_entries = []
    for m in matches:
        raw_title = m.group(1) if m.group(1) is not None else m.group(2)
        title = clean_title(raw_title)
        offset = find_doc_start(data, m.start())
        title_entries.append({"title": title, "offset": offset, "source": "title"})
    title_entries.sort(key=lambda e: e["offset"])

    orphans = find_orphaned_sections(data, title_entries)

    entries = sorted(title_entries + orphans, key=lambda e: e["offset"])
    entries, dropped = drop_stub_duplicates(data, entries)

    for i, e in enumerate(entries):
        next_offset = entries[i + 1]["offset"] if i + 1 < len(entries) else len(data)
        e["length"] = next_offset - e["offset"]

    return {
        "total_documents": len(entries),
        "entries": entries,
        "recovered_sections": len(orphans),
        "dropped_stub_duplicates": dropped,
    }


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    out_path = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None

    data = (library / filename).read_bytes()
    index = build_index(data)

    print(f"{filename}: {index['total_documents']} documents "
          f"({index['recovered_sections']} recovered via SectionNumber, "
          f"{index['dropped_stub_duplicates']} empty-stub duplicates dropped)")

    by_title = {e["title"]: e for e in index["entries"]}
    for sample in (
        "Preface, Florida Statutes 2025",
        "CHAPTER 1",
        "F.S. 1.01",
        "F.S. 1.02",
        "F.S. 626.6215",
        "F.S. 626.631",
        "F.S. 6.01",
        "F.S. 6.02",
        "F.S. 7.08",
        "F.S. 7.07",
    ):
        e = by_title.get(sample)
        print(f"  {sample!r} -> {e}")

    still_merged = 0
    for e in index["entries"]:
        span = data[e["offset"] : e["offset"] + e["length"]]
        if span.count(b'<div class="Section">') > 1:
            still_merged += 1
    print(f"  entries still containing >1 <div class=\"Section\">: {still_merged}")

    if out_path:
        out_path.write_text(json.dumps(index, indent=1))
        print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
