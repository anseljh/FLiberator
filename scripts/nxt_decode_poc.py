"""Phase 2 proof-of-concept decoder for the .nxt tokenized-markup content layer.

Opcode rules (hypotheses under test, see docs/nxt-format.md):
  0x13 0x37 <len:1> <len bytes>   -- literal markup/tag text, length-prefixed
  0x08 <printable-run>            -- literal text run, consumes printable/UTF-8
                                      bytes until a non-text byte is hit
  anything else < 0x20            -- unrecognized opcode; skipped one byte at a
                                      time (logged) as a deliberately dumb
                                      fallback, so decoding degrades instead of
                                      halting when the opcode table is incomplete

This is throwaway analysis code, not part of the installable package.
"""

import pathlib
import sys


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
    while i < end:
        b = data[i]
        if b == 0x13 and i + 1 < end and data[i + 1] == 0x37:
            length = data[i + 2]
            text = data[i + 3 : i + 3 + length]
            out.append(text.decode("utf-8", errors="replace"))
            stats["tag_tokens"] += 1
            i += 3 + length
        elif b == 0x08:
            j = i + 1
            while j < end:
                n = is_text_byte(data, j)
                if n == 0:
                    break
                j += n
            if j > i + 1:
                out.append(data[i + 1 : j].decode("utf-8", errors="replace"))
                stats["text_runs"] += 1
            i = j
        else:
            stats["unknown_bytes_skipped"] += 1
            i += 1
    return "".join(out), stats


def main() -> None:
    library = pathlib.Path("FLLawDL2025/Library")
    data = (library / "fs2025.nxt").read_bytes()

    lpdd = data.find(b"LPDD", 100_000)
    body_start = lpdd + len(b"LPDD")
    next_lpdd = data.find(b"LPDD", body_start)
    body_end = next_lpdd if next_lpdd != -1 else body_start + 20_000

    print(f"LPDD marker @ {lpdd}, body [{body_start}:{body_end}] ({body_end - body_start} bytes)")

    html, stats = decode(data, body_start, body_end)
    print("decode stats:", stats)
    print("=" * 80)
    print(html)


if __name__ == "__main__":
    main()
