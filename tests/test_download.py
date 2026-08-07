"""Fetching, unpacking and locating the bulk data.

The point of scraping rather than hardcoding is that the link changes every
year, so what needs pinning is that a new year's filename still matches and
still resolves to an absolute URL.
"""

import contextlib
import io
import zipfile

import pytest

from fliberator import download

PAGE = """
<html><body>
  <a href="index.cfm?Mode=Statutes%20Download">Statutes Download</a>
  <a href="/Statutes/Download/FLLawDL2026.zip">Download the 2026 edition</a>
</body></html>
"""


@contextlib.contextmanager
def _serve(html: str):
    yield io.BytesIO(html.encode("utf-8"))


def test_the_zip_link_is_found_and_made_absolute(monkeypatch):
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k: _serve(PAGE))
    assert download.find_zip_url() == (
        "https://www.leg.state.fl.us/Statutes/Download/FLLawDL2026.zip"
    )


def test_a_page_without_a_zip_link_fails_loudly(monkeypatch):
    monkeypatch.setattr(
        download.urllib.request, "urlopen", lambda *a, **k: _serve("<html>maintenance</html>")
    )
    with pytest.raises(RuntimeError, match="no FLLawDL"):
        download.find_zip_url()


def test_only_the_nxt_files_come_out_of_the_zip(tmp_path, monkeypatch):
    # Issue #1: what Florida distributes is a Windows installer that happens
    # to contain the data. 13 of its 1,382 entries are Infobase files; the
    # rest is the bundled viewer, and unpacking it cost 178 MB.
    archive = tmp_path / "FLLawDL2099.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("FLLawDL2099/Library/fs2099.nxt", b"statutes")
        bundle.writestr("FLLawDL2099/Library/2099CD.libdef", b"library definition")
        bundle.writestr("FLLawDL2099/copy/viewer.dll", b"\x00" * 64)
        bundle.writestr("FLLawDL2099/applets/search.class", b"\x00" * 64)
    monkeypatch.setattr(download, "find_zip_url", lambda *a, **k: "https://x/FLLawDL2099.zip")

    found = download.library(root=tmp_path)
    assert found == tmp_path / "FLLawDL2099" / "Library"
    assert [p.name for p in found.iterdir()] == ["fs2099.nxt"]
    assert not (tmp_path / "FLLawDL2099" / "copy").exists()
    assert not (tmp_path / "FLLawDL2099" / "applets").exists()


def test_extraction_is_skipped_when_the_nxt_files_are_already_there(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "find_zip_url", lambda *a, **k: "https://x/FLLawDL2099.zip")
    (tmp_path / "FLLawDL2099.zip").write_bytes(b"not a real zip")
    unpacked = tmp_path / "FLLawDL2099" / "Library"
    unpacked.mkdir(parents=True)
    (unpacked / "fs2099.nxt").write_bytes(b"already here")
    # Reaching ZipFile at all would raise, since the archive is a stub.
    assert download.library(root=tmp_path) == unpacked


def test_the_newest_edition_is_the_default_library(tmp_path):
    for year in (2025, 2026):
        (tmp_path / f"FLLawDL{year}" / "Library").mkdir(parents=True)
    assert download.default_library(tmp_path).parent.name == "FLLawDL2026"
    assert download.default_library(tmp_path / "nothing-here") is None
