"""Fetch and unpack Florida's bulk statutes distribution.

Downloads the current year's "Advanced Legislative Search & Browse" zip from
the leg.state.fl.us download page into a git-ignored `download/` folder and
extracts it there, leaving `download/FLLawDL<year>/Library/*.nxt` -- which
is what `fliberate` reads.

Only the `.nxt` files come out of the zip (issue #1). What Florida
distributes is a Windows installer that happens to contain the data: 13 of
its 1,382 entries are Infobase files and the rest are the bundled viewer
application, which FLiberator never reads.

The zip's filename and link are discovered by scraping the download page
rather than hardcoded, so this keeps working as each year's edition replaces
the last (the page's own link text is `FLLawDL<year>.zip`, e.g.
`FLLawDL2025.zip` as of this writing).

`FLLawDL2025/` in the repository root -- the read-only reference copy the
reverse-engineering work was developed and validated against -- is never
touched. This always writes to `download/`.
"""

import pathlib
import re
import urllib.parse
import urllib.request
import zipfile

DOWNLOAD_PAGE = (
    "https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes"
)
ZIP_LINK_RE = re.compile(r'href="([^"]*FLLawDL\d{4}\.zip)"', re.IGNORECASE)
USER_AGENT = "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"

DOWNLOAD_DIR = pathlib.Path("download")
BLOCK = 1 << 20
NXT_SUFFIX = ".nxt"


def _silent(message: str) -> None:
    pass


def is_data(name: str) -> bool:
    """Is this zip member one of the Infobase files we actually decode?

    The zip is a Windows installer: 1,382 entries, of which 13 are the data
    (issue #1). The other 1,369 are the bundled viewer application -- DLLs,
    Java applets, icons, an InstallShield payload -- which FLiberator never
    reads and which cost 178 MB of disk to unpack."""
    return name.lower().endswith(NXT_SUFFIX)


def find_zip_url(page: str = DOWNLOAD_PAGE) -> str:
    """The absolute URL of the current edition's zip, scraped from the page."""
    request = urllib.request.Request(page, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")
    match = ZIP_LINK_RE.search(html)
    if match is None:
        raise RuntimeError(f"no FLLawDL<year>.zip link found on {page}")
    return urllib.parse.urljoin(page, match.group(1))


def fetch(url: str, destination: pathlib.Path, progress=None) -> pathlib.Path:
    """Download to a `.part` file, then rename -- so an interrupted run
    never leaves a truncated zip looking complete.

    `progress`, if given, is called with (bytes so far, total or 0)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        total = int(response.headers.get("Content-Length", 0))
        written = 0
        while chunk := response.read(BLOCK):
            handle.write(chunk)
            written += len(chunk)
            if progress is not None:
                progress(written, total)
    partial.rename(destination)
    return destination


def default_library(root: pathlib.Path = DOWNLOAD_DIR) -> pathlib.Path | None:
    """The Library directory of the newest edition already under `root`.

    Discovered rather than hardcoded so that decoding keeps working once
    `FLLawDL2025` is superseded. Editions sort by name because the year is
    fixed-width."""
    found = sorted(p for p in pathlib.Path(root).glob("FLLawDL*/Library") if p.is_dir())
    return found[-1] if found else None


def library(root: pathlib.Path = DOWNLOAD_DIR, log=_silent, progress=None) -> pathlib.Path:
    """Ensure the bulk data is present under `root`; return its Library path.

    Both steps are idempotent: an existing zip is not re-fetched and an
    existing non-empty extraction is not re-extracted, so re-running this
    after a successful run costs one request for the download page.
    """
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)

    url = find_zip_url()
    archive = root / url.rsplit("/", 1)[-1]
    if archive.exists():
        log(f"{archive} already present ({archive.stat().st_size:,} bytes)")
    else:
        log(f"downloading {url}")
        fetch(url, archive, progress)
        log(f"wrote {archive} ({archive.stat().st_size:,} bytes)")

    # The zip wraps everything in one top-level folder matching its own name
    # (FLLawDL2025.zip's entries all start with "FLLawDL2025/"), so
    # extracting straight into `root` reproduces the expected layout instead
    # of double-nesting it.
    extracted = root / archive.stem
    found = extracted / "Library"
    if found.is_dir() and any(found.glob(f"*{NXT_SUFFIX}")):
        log(f"{found} already extracted")
        return found

    log(f"extracting {archive} into {root}")
    with zipfile.ZipFile(archive) as bundle:
        members = [item for item in bundle.infolist() if is_data(item.filename)]
        if not members:
            raise RuntimeError(f"{archive} holds no {NXT_SUFFIX} files")
        bundle.extractall(root, members=members)
    log(
        f"extracted {len(members)} {NXT_SUFFIX} files "
        f"({sum(item.file_size for item in members):,} bytes)"
    )

    if not found.is_dir():
        raise RuntimeError(f"{archive} did not contain the expected {found}")
    return found
