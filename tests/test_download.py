"""Locating the current edition's zip on the download page.

The point of scraping rather than hardcoding is that the link changes every
year, so what needs pinning is that a new year's filename still matches and
still resolves to an absolute URL.
"""

import contextlib
import io

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
