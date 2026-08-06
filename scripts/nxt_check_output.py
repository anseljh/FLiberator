"""Self-check the decoder's output, without reference to the live site.

`nxt_validate.py` is the fidelity harness, but it has a permanent blind
spot: `normalize()` collapses `\\s+` before scoring, and that collapsing is
load-bearing (the live pages and our decoded output carry different
template indentation, so without it nothing would ever match). The
consequence is that **extra whitespace is invisible to it** -- 263,569 of
Phase 2e's 327,048 doubled characters were em spaces and NBSPs that
collapsed away before the diff ever ran, so the harness scored 1.0000 on
documents that were visibly wrong.

That is not a gap that can be closed by diffing harder against the live
site. It has to be closed by checking the decoder against *the source
bytes*, which is what this script does. Four invariants:

  1. **Doubled-character markers are all claimed.** Every
     `0x15 0x01 0x01 0x01` in the source must be matched by
     `doubled_char_len`. A marker that falls through is emitted twice --
     once as the literal copy, once as the entity token -- which is
     exactly the Phase 2e defect. This is a complete guard on that class:
     if the count is 0, no doubling of this kind can be shipping.

  2. **No character sits next to its own entity form** in the output
     (`&` before `&amp;`, U+00A0 before `&#xA0;`). Same defect seen from
     the output side rather than the source side, so a *new* doubling
     shape that invariant 1 doesn't know about still gets caught.

  3. **Every source byte is consumed exactly once** -- no gaps, no
     overlapping reads. Byte accounting is what makes "we know what the
     whole file is" a checkable claim rather than an assertion.

  4. **A whitespace census**, printed as a baseline rather than judged.
     Adjacent-whitespace runs are legitimate in this corpus -- they are
     fill-in-the-blank rules in oath forms (`I, <NBSP><NBSP>, do solemnly
     swear`) and column alignment in the judge-count tables -- and each
     one traces to a repeated source marker. But their *counts* are
     precisely what the live-site harness cannot see, so recording them
     here means a future change that alters them shows up as a diff.

Invariant 1 is what caught the residual 62: markers whose literal copy is
a 1-byte `&` paired with `&amp;`, which the old multi-byte heuristic
rejected. They shipped `AT&&T`, `Child && Dependent` and `Flagler &&
Volusia` across 25 documents.

This is throwaway analysis code, not part of the installable package.
"""

import collections
import html
import re
import sys
import unicodedata

from nxt_decode_poc import (
    DOUBLED_CHAR_MARKER,
    LPDD_MARKER,
    decode,
    doubled_char_len,
    is_field_marker,
    is_text_byte,
)
from nxt_depage import load_records

TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&(?:#x[0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]*);")
# Whitespace runs in rendered text, ignoring the \x00 marks left where tags were.
WS_RUN_RE = re.compile(r"[^\S\x00]{2,}")


def consumed_spans(data: bytes) -> list[tuple[int, int]]:
    """Re-walk a record with decode()'s control flow, recording the byte span
    each step consumes. Used for the byte-accounting invariant."""
    spans = []
    i, end = 0, len(data)
    while i < end:
        b = data[i]
        start = i
        if b == 0x11 and data[i : i + len(LPDD_MARKER)] == LPDD_MARKER:
            i += len(LPDD_MARKER)
        elif b == 0x15 and (skip := doubled_char_len(data, i, end)):
            i += skip
        elif b == 0x15 and is_field_marker(data, i, end):
            i += 4
        elif b == 0x13 and i + 1 < end:
            length_byte = data[i + 2]
            if length_byte & 0x80:
                length, header = ((length_byte & 0x7F) << 8) | data[i + 3], 4
            else:
                length, header = length_byte, 3
            i += header + length
        elif (
            b == 0x10
            and i + 5 < end
            and data[i + 1] in (0x00, 0x01)
            and data[i + 2] == 0x03
            and data[i + 3] == 0x82
            and data[i + 5] == 0x01
        ):
            i += 6
        elif is_text_byte(data, i):
            j = i
            while j < end and (n := is_text_byte(data, j)):
                j += n
            i = j
        else:
            i += 1
        spans.append((start, min(i, end)))
    return spans


def adjacent_entity_duplicates(decoded: str) -> list[str]:
    """Find every place a character sits immediately beside its own entity
    form -- the output-side signature of a doubled-character defect."""
    found = []
    for match in ENTITY_RE.finditer(decoded):
        char = html.unescape(match.group())
        if len(char) != 1 or char == match.group():
            continue  # not a real entity, or didn't resolve
        before = decoded[max(0, match.start() - len(char)) : match.start()]
        after = decoded[match.end() : match.end() + len(char)]
        if before == char or after == char:
            found.append(match.group())
    return found


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    records = load_records()
    if limit:
        records = records[:limit]

    markers = matched = 0
    unmatched_shapes: collections.Counter = collections.Counter()
    duplicates: collections.Counter = collections.Counter()
    docs_with_duplicates = 0
    gaps = overlaps = 0
    ws_chars: collections.Counter = collections.Counter()
    ws_runs: collections.Counter = collections.Counter()

    for record in records:
        # 1. doubled-character marker coverage
        pos = record.find(DOUBLED_CHAR_MARKER)
        while pos != -1:
            markers += 1
            if doubled_char_len(record, pos, len(record)):
                matched += 1
            else:
                unmatched_shapes[bytes(record[pos + 4 : pos + 10])] += 1
            pos = record.find(DOUBLED_CHAR_MARKER, pos + 4)

        # 3. byte accounting
        cursor = 0
        for start, stop in consumed_spans(record):
            if start > cursor:
                gaps += 1
            elif start < cursor:
                overlaps += 1
            cursor = stop

        decoded, _stats = decode(record, 0, len(record))

        # 2. output-side duplicate signature
        found = adjacent_entity_duplicates(decoded)
        if found:
            docs_with_duplicates += 1
            duplicates.update(found)

        # 4. whitespace census
        text = html.unescape(TAG_RE.sub("\x00", decoded))
        for char in text:
            if char != "\x00" and char.isspace():
                ws_chars[char] += 1
        for run in WS_RUN_RE.finditer(text):
            ws_runs["+".join(f"U+{ord(c):04X}" for c in run.group())] += 1

    print(f"checked {len(records):,} documents\n")

    ok = True
    print("1. doubled-character markers")
    print(f"   {markers:,} in source, {matched:,} claimed by the rule, "
          f"{markers - matched:,} fell through")
    if markers != matched:
        ok = False
        for shape, count in unmatched_shapes.most_common(8):
            print(f"     !! {count:>6,}  bytes after marker: {shape!r}")

    print("\n2. characters adjacent to their own entity form")
    if duplicates:
        ok = False
        print(f"   !! {sum(duplicates.values()):,} in {docs_with_duplicates:,} documents")
        for entity, count in duplicates.most_common(8):
            print(f"     !! {count:>6,}  {entity}")
    else:
        print("   none")

    print("\n3. byte accounting")
    print(f"   {gaps:,} gaps, {overlaps:,} overlapping reads")
    if gaps or overlaps:
        ok = False

    print("\n4. whitespace census (baseline -- invisible to the live-site harness)")
    for char, count in ws_chars.most_common(8):
        name = unicodedata.name(char, repr(char))
        print(f"   {count:>10,}  U+{ord(char):04X}  {name}")
    print("   adjacent-whitespace runs:")
    for shape, count in ws_runs.most_common(8):
        print(f"   {count:>10,}  {shape}")

    print("\n" + ("ALL INVARIANTS HOLD" if ok else "INVARIANT VIOLATED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
