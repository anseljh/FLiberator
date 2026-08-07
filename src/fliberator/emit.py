"""Write the liberated corpus: one HTML file per section, one JSON sidecar.

Output shape (plans/re-plan.md Phase 9):

    output/
      metadata.json                     <- ordering, hierarchy, provenance
      statutes/0001/1.01.html
      constitution/article-01/section-03.html
      laws/2025-1.html

The HTML files are the decoded source with footnotes rewritten as semantic
HTML5 (see footnotes.py) and a minimal document wrapper. Nothing else about
the markup is altered: the decoded body is what the `.nxt` file contains,
which the validation work established is a faithful -- and in places
strictly more complete -- rendering of what leg.state.fl.us publishes.

`metadata.json` is the single file carrying everything the HTML can't:
canonical ordering (document bodies are stored in build order, which has
nothing to do with statutory order), the Title/Chapter/Part hierarchy, and
the edition year plus source-file provenance needed to tell two years'
output apart.
"""

import datetime
import hashlib
import json
import pathlib
import re

from . import documents
from .decode import decode
from .depage import load_records
from .footnotes import transform

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="generator" content="FLiberator {version}">
<link rel="canonical" href="{canonical}">
</head>
{body}
</html>
"""

# name -> (filename prefix, section extractor, grouping over the emitted
# entries). Only the statutes have a tier above the document itself.
#
# Source files are named <prefix><year>.nxt -- fs2025.nxt, flcnst2025.nxt,
# lf2025.nxt -- and the year is *discovered*, not hardcoded, so next year's
# edition needs no code change. Getting this wrong is the difference
# between the downloader being useful and being decorative: `--download`
# would fetch FLLawDL2026 correctly and then fail to find fs2025.nxt.
COLLECTIONS = {
    "statutes": ("fs", documents.statutes, documents.title_hierarchy),
    "constitution": ("flcnst", documents.constitution, None),
    "laws": ("lf", documents.session_laws, None),
}


def resolve(library: pathlib.Path, prefix: str) -> tuple[pathlib.Path, int]:
    """Find `<prefix><year>.nxt` in a Library directory; return it and the year."""
    pattern = re.compile(rf"{prefix}(\d{{4}})\.nxt", re.IGNORECASE)
    matched = sorted(
        (int(m.group(1)), p) for p in library.glob("*.nxt") if (m := pattern.fullmatch(p.name))
    )
    if not matched:
        raise FileNotFoundError(f"no {prefix}<year>.nxt in {library}")
    if len(matched) > 1:
        # Never guess between editions: which one is "the" corpus is the
        # caller's decision, not a coin flip made three layers down.
        raise ValueError(
            f"{library} holds more than one edition of {prefix}<year>.nxt: "
            + ", ".join(p.name for _, p in matched)
        )
    year, path = matched[0]
    return path, year


def sources(library: pathlib.Path) -> tuple[dict[str, pathlib.Path], int]:
    """Every collection's source file, plus the edition year they share."""
    found = {name: resolve(library, prefix) for name, (prefix, _, _) in COLLECTIONS.items()}
    years = {year for _, year in found.values()}
    if len(years) > 1:
        raise ValueError(
            f"{library} mixes editions: "
            + ", ".join(f"{name}={path.name}" for name, (path, _) in found.items())
        )
    return {name: path for name, (path, _) in found.items()}, years.pop()


def _digest(path: pathlib.Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def _wrap(record: dict, body: str, version: str) -> str:
    title = record["citation"]
    if record.get("catchline"):
        title = f"{title} — {record['catchline']}"
    return PAGE_TEMPLATE.format(
        title=title, version=version, canonical=record["path"], body=body
    )


def build(library: pathlib.Path, output: pathlib.Path, version: str = "0.1.0") -> dict:
    """Decode, rewrite and write every collection. Returns the metadata."""
    library, output = pathlib.Path(library), pathlib.Path(output)
    source_files, edition = sources(library)
    metadata: dict = {
        "generator": f"FLiberator {version}",
        "generated": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "edition": edition,
        "collections": {},
    }

    for name, (_, extract, group) in COLLECTIONS.items():
        source = source_files[name]
        records = load_records(source)
        decoded = [decode(r, 0, len(r))[0] for r in records]
        found = extract(decoded)

        entries = []
        for order, record in enumerate(found):
            html, notes = transform(record.pop("html"))
            body = documents.body_of(html)
            if not body.lower().startswith("<body"):
                body = f"<body>{body}</body>"
            destination = output / record["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(_wrap(record, body, version), encoding="utf-8")

            entry = {k: v for k, v in record.items() if v is not None}
            entry["order"] = order
            entry["bytes"] = destination.stat().st_size
            if notes:
                entry["footnotes"] = notes
            entries.append(entry)

        collection = {
            "source": {
                "file": source.name,
                "bytes": source.stat().st_size,
                "sha256": _digest(source),
            },
            "documents": len(entries),
            "order": "canonical (parsed numerically), not source file order",
        }
        if group is not None:
            collection["titles"] = group(entries)
        collection["entries"] = entries
        metadata["collections"][name] = collection

    output.mkdir(parents=True, exist_ok=True)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
