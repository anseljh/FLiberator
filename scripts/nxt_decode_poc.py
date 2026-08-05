"""Phase 2 decoder for the .nxt tokenized-markup content layer.

Opcode rules (see docs/nxt-format.md for how these were derived):
  0x13 <subtype> <len> <len bytes> -- literal text, length-prefixed. <subtype>
                                      byte varies (0x37 for markup tags, 0x39
                                      seen for HTML entities like &#x2003; --
                                      framing is identical either way, so it's
                                      treated as opaque/unclassified here).
                                      <len> is 1 byte if its high bit is clear;
                                      if set, it's a 2-byte big-endian length:
                                      ((b1 & 0x7F) << 8) | b2 (confirmed against
                                      a 239-byte <!DOCTYPE...><meta.../> run).
  <printable/UTF-8 run>            -- literal text, sniffed at every position
                                      (not only after a particular opcode --
                                      confirmed some text, e.g. "Definitions."
                                      inside <CATCHLINE></CATCHLINE>, appears
                                      completely unprefixed). 0x08 turned out
                                      not to be a dedicated "text" opcode; it's
                                      just another byte that happens to often
                                      precede a text run, so it's treated the
                                      same as any other unrecognized byte.
  anything else < 0x20            -- unrecognized opcode; skipped one byte at a
                                      time (logged) as a deliberately dumb
                                      fallback, so decoding degrades instead of
                                      halting when the opcode table is incomplete

This is throwaway analysis code, not part of the installable package.
"""

import pathlib
import sys
from collections import Counter


def is_text_byte(data: bytes, i: int) -> int:
    """Return the number of bytes a printable/UTF-8 run at i consumes (0 if none)."""
    b = data[i]
    if b in (0x09, 0x0A, 0x0D) or 0x20 <= b <= 0x7E:
        return 1
    # crude UTF-8 continuation check for multi-byte sequences (curly quotes, EM SPACE, etc.)
    if 0xC2 <= b <= 0xDF and i + 1 < len(data) and 0x80 <= data[i + 1] <= 0xBF:
        return 2
    if 0xE0 <= b <= 0xEF and i + 2 < len(data) and all(
        0x80 <= data[i + k] <= 0xBF for k in (1, 2)
    ):
        return 3
    return 0


def decode(data: bytes, start: int, end: int) -> tuple[str, dict]:
    out = []
    i = start
    stats = {"tag_tokens": 0, "text_runs": 0, "unknown_bytes_skipped": 0}
    subtypes: Counter = Counter()
    while i < end:
        b = data[i]
        if b == 0x13 and i + 1 < end:
            subtype = data[i + 1]
            b1 = data[i + 2]
            if b1 & 0x80:
                length = ((b1 & 0x7F) << 8) | data[i + 3]
                header_len = 4
            else:
                length = b1
                header_len = 3
            text = data[i + header_len : i + header_len + length]
            out.append(text.decode("utf-8", errors="replace"))
            stats["tag_tokens"] += 1
            subtypes[subtype] += 1
            i += header_len + length
        elif is_text_byte(data, i):
            j = i
            while j < end:
                n = is_text_byte(data, j)
                if n == 0:
                    break
                j += n
            out.append(data[i:j].decode("utf-8", errors="replace"))
            stats["text_runs"] += 1
            i = j
        else:
            stats["unknown_bytes_skipped"] += 1
            i += 1
    stats["tag_subtypes"] = dict(subtypes)
    return "".join(out), stats


def iter_documents(data: bytes, search_from: int = 0):
    """Yield (body_start, body_end) for every LPDD-delimited document."""
    pos = data.find(b"LPDD", search_from)
    while pos != -1:
        body_start = pos + len(b"LPDD")
        next_pos = data.find(b"LPDD", body_start)
        body_end = next_pos if next_pos != -1 else len(data)
        yield body_start, body_end
        pos = next_pos


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    filename = sys.argv[1] if len(sys.argv) > 1 else "fs2025.nxt"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    search_from = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    data = (library / filename).read_bytes()

    total_stats = {"tag_tokens": 0, "text_runs": 0, "unknown_bytes_skipped": 0}
    subtypes: Counter = Counter()
    for n, (body_start, body_end) in enumerate(iter_documents(data, search_from)):
        if n >= limit:
            break
        html, stats = decode(data, body_start, body_end)
        subtypes.update(stats.pop("tag_subtypes"))
        for k in total_stats:
            total_stats[k] += stats[k]
        print(f"--- doc {n} @ [{body_start}:{body_end}] ({body_end - body_start} bytes) ---")
        print("stats:", stats)
        print(html)
        print()

    print("=" * 80)
    print(f"TOTAL across {min(limit, n + 1)} docs:", total_stats, "subtypes:", dict(subtypes))


if __name__ == "__main__":
    main()
