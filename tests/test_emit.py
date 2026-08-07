"""Resolving each collection's source file.

The year in `fs2025.nxt` used to be hardcoded, which meant `--download`
would correctly fetch a 2026 edition and then fail to find the 2025
filenames -- the downloader working and the pipeline still not running.
"""

import pathlib

import pytest

from fliberator import emit


def library(tmp_path: pathlib.Path, *names: str) -> pathlib.Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name in names:
        (tmp_path / name).write_bytes(b"")
    return tmp_path


DOCUMENTS = {
    "fs2025.nxt": (
        "<html><head><title>F.S. 1.01</title></head><body>"
        '<div class="Section"><CATCHLINE>Definitions.</CATCHLINE></div></body></html>'
    ),
    "flcnst2025.nxt": (
        "<html><head><title>Florida Constitution</title></head><body>"
        '<div class="Section"><a name="A1S03">SECTION 3.</a>'
        "<CATCHLINE>Religious freedom.</CATCHLINE></div></body></html>"
    ),
    "lf2025.nxt": "<html><head><title>CHAPTER 2025-1</title></head><body>x</body></html>",
}


def test_the_edition_year_is_discovered_not_hardcoded(tmp_path):
    found, edition = emit.sources(
        library(tmp_path, "fs2031.nxt", "flcnst2031.nxt", "lf2031.nxt", "uscon.nxt")
    )
    assert edition == 2031
    assert found["statutes"].name == "fs2031.nxt"
    assert found["laws"].name == "lf2031.nxt"


def test_a_missing_collection_file_says_what_it_looked_for(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"flcnst<year>\.nxt"):
        emit.sources(library(tmp_path, "fs2025.nxt", "lf2025.nxt"))


def test_two_editions_of_one_file_are_refused_rather_than_guessed(tmp_path):
    # Which edition is "the" corpus is the caller's decision, not a coin
    # flip made three layers down.
    with pytest.raises(ValueError, match="more than one edition"):
        emit.resolve(library(tmp_path, "fs2025.nxt", "fs2026.nxt"), "fs")


def test_a_library_mixing_editions_across_collections_is_refused(tmp_path):
    with pytest.raises(ValueError, match="mixes editions"):
        emit.sources(library(tmp_path, "fs2025.nxt", "flcnst2026.nxt", "lf2025.nxt"))


def test_the_prefixes_do_not_match_each_other(tmp_path):
    # "lf" must not pick up flcnst2025.nxt, and "fs" must not pick up
    # anything else in a Library that holds 13 .nxt files.
    found, _ = emit.sources(
        library(tmp_path, "fs2025.nxt", "flcnst2025.nxt", "lf2025.nxt", "defx2025.nxt")
    )
    assert found["laws"].name == "lf2025.nxt"
    assert found["constitution"].name == "flcnst2025.nxt"


def test_build_reads_each_collection_from_its_resolved_source(tmp_path, monkeypatch):
    # Cheap stand-in for the decoding layers, so this exercises build()'s own
    # wiring -- which resolved path feeds which extractor -- in milliseconds
    # rather than the 18 seconds a real run takes.
    monkeypatch.setattr(emit, "load_records", lambda path: [path.name.encode()])
    monkeypatch.setattr(emit, "decode", lambda record, *_: (DOCUMENTS[record.decode()], 0))

    metadata = emit.build(library(tmp_path / "Library", *DOCUMENTS), tmp_path / "out")

    assert metadata["edition"] == 2025
    assert metadata["collections"]["statutes"]["source"]["file"] == "fs2025.nxt"
    assert metadata["collections"]["laws"]["source"]["file"] == "lf2025.nxt"
    assert (tmp_path / "out/statutes/0001/1.01.html").is_file()
    assert (tmp_path / "out/constitution/article-01/section-03.html").is_file()
    assert (tmp_path / "out/laws/2025-1.html").is_file()
    assert (tmp_path / "out/metadata.json").is_file()
