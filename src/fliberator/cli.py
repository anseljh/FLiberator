"""Command-line entry point: `fliberate`."""

import argparse
import pathlib
import sys

from . import __version__
from .emit import build

DEFAULT_LIBRARY = pathlib.Path("download/FLLawDL2025/Library")
DEFAULT_OUTPUT = pathlib.Path("output")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fliberate",
        description="Convert Florida's bulk statutes distribution to open HTML + JSON.",
    )
    parser.add_argument(
        "--library",
        type=pathlib.Path,
        default=DEFAULT_LIBRARY,
        help=f"directory holding the .nxt files (default: {DEFAULT_LIBRARY})",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT,
        help=f"where to write HTML and metadata.json (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--version", action="version", version=f"FLiberator {__version__}")
    args = parser.parse_args(argv)

    if not args.library.is_dir():
        parser.error(
            f"{args.library} is not a directory. "
            "Run `python -m fliberator.download` first, or pass --library."
        )

    metadata = build(args.library, args.output, __version__)
    total = 0
    for name, collection in metadata["collections"].items():
        count = collection["documents"]
        total += count
        print(f"{name:>14}: {count:>6,} documents  <- {collection['source']['file']}")
    print(f"{'total':>14}: {total:>6,} documents written to {args.output}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
