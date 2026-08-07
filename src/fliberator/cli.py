"""Command-line entry point: `fliberate`."""

import argparse
import pathlib
import sys

from . import __version__, download
from .emit import build

DEFAULT_LIBRARY = pathlib.Path("download/FLLawDL2025/Library")
DEFAULT_OUTPUT = pathlib.Path("output")


def _progress(written: int, total: int) -> None:
    share = f" / {total:,} ({100 * written / total:.0f}%)" if total else ""
    done = total and written >= total
    print(f"\r  {written:,} bytes{share}", end="\n" if done else "", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fliberate",
        description="Convert Florida's bulk statutes distribution to open HTML + JSON.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="fetch and unzip the current bulk data into download/ first, "
        "and decode what that produces",
    )
    parser.add_argument(
        "--library",
        type=pathlib.Path,
        help=f"directory holding the .nxt files (default: {DEFAULT_LIBRARY}, "
        "or whatever --download produces)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=DEFAULT_OUTPUT,
        help=f"where to write HTML and metadata.json (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--version", action="version", version=f"FLiberator {__version__}")
    args = parser.parse_args(argv)

    library = args.library
    if args.download:
        # An explicit --library still wins; otherwise decode the edition
        # just fetched, whatever year it turns out to be.
        fetched = download.library(log=print, progress=_progress)
        library = library or fetched
    library = library or DEFAULT_LIBRARY

    if not library.is_dir():
        parser.error(f"{library} is not a directory. Run `fliberate --download` first, "
                     "or pass --library.")

    metadata = build(library, args.output, __version__)
    total = 0
    for name, collection in metadata["collections"].items():
        count = collection["documents"]
        total += count
        print(f"{name:>14}: {count:>6,} documents  <- {collection['source']['file']}")
    print(f"{'total':>14}: {total:>6,} documents written to {args.output}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
