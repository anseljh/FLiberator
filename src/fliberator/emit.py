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
the source-file provenance needed to tell two years' output apart.
"""

import datetime
import hashlib
import json
import pathlib

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

COLLECTIONS = {
    "statutes": ("fs2025.nxt", documents.statutes),
    "constitution": ("flcnst2025.nxt", documents.constitution),
    "laws": ("lf2025.nxt", documents.session_laws),
}


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
    metadata: dict = {
        "generator": f"FLiberator {version}",
        "generated": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "collections": {},
    }

    for name, (filename, extract) in COLLECTIONS.items():
        source = library / filename
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

        metadata["collections"][name] = {
            "source": {
                "file": filename,
                "bytes": source.stat().st_size,
                "sha256": _digest(source),
            },
            "documents": len(entries),
            "order": "canonical (parsed numerically), not source file order",
            "entries": entries,
        }

    output.mkdir(parents=True, exist_ok=True)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
