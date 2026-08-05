"""Phase 1 corpus survey for the Folio NXT .nxt format (see plans/re-plan.md).

For every .nxt file under a given Library directory, report:
  - file size
  - hex dump of the header region (0x00-0x200)
  - little-endian uint32 reads at the candidate "count field" offsets
    observed around 0x1B0-0x1BF
  - a byte-frequency histogram of the first N MB, to spot candidate
    opcodes (frequent low-value control bytes)

Throwaway analysis script, not part of the installable package.
"""

import argparse
import pathlib
import struct
from collections import Counter

HEADER_LEN = 0x200
CANDIDATE_COUNT_OFFSETS = [0x1B0, 0x1B4, 0x1B8, 0x1BC]
HISTOGRAM_SAMPLE_BYTES = 4 * 1024 * 1024


def hexdump(data: bytes, base: int = 0) -> str:
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{base + i:08x}  {hex_part:<47}  {ascii_part}")
    return "\n".join(lines)


def survey_file(path: pathlib.Path) -> str:
    size = path.stat().st_size
    with path.open("rb") as f:
        header = f.read(HEADER_LEN)
        f.seek(0)
        sample = f.read(min(size, HISTOGRAM_SAMPLE_BYTES))

    out = [f"=== {path.name} ({size:,} bytes) ==="]
    out.append(hexdump(header))

    out.append("\ncandidate count fields (little-endian uint32):")
    for off in CANDIDATE_COUNT_OFFSETS:
        if off + 4 <= len(header):
            (val,) = struct.unpack_from("<I", header, off)
            out.append(f"  0x{off:03x}: {val}")

    counts = Counter(sample)
    out.append(
        f"\ntop 20 byte values in first {len(sample):,} bytes "
        f"(value: count, %):"
    )
    total = len(sample)
    for byte_val, count in counts.most_common(20):
        pct = 100 * count / total
        ch = chr(byte_val) if 32 <= byte_val < 127 else "."
        out.append(f"  0x{byte_val:02x} {ch!r:>4}: {count:>10,}  ({pct:5.2f}%)")

    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "library_dir",
        type=pathlib.Path,
        nargs="?",
        default=pathlib.Path("FLLawDL2025/Library"),
    )
    args = parser.parse_args()

    nxt_files = sorted(args.library_dir.glob("*.nxt"), key=lambda p: p.stat().st_size)
    for path in nxt_files:
        print(survey_file(path))
        print()


if __name__ == "__main__":
    main()
