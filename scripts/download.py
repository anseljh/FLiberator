"""Phase 6: download + unzip the Florida statutes bulk data.

Fetches the current year's "Advanced Legislative Search & Browse" zip from
the leg.state.fl.us download page into a git-ignored `download/` folder and
extracts it there. The current zip filename/link is discovered by scraping
the download page rather than hardcoding a year, so this keeps working as
each year's edition replaces the last (confirmed: the page's own link text
is `FLLawDL<year>.zip`, e.g. `FLLawDL2025.zip` as of this writing).

`FLLawDL2025/` -- the read-only reference copy this whole project's
reverse-engineering work was developed and validated against -- is never
touched by this script. It always writes to `download/` instead, which is
meant to become the live/current working copy once the rest of the
pipeline (Phase 7+) runs against it. Output from decoding that data belongs
in the separate git-ignored `output/` folder, not here.

This is throwaway analysis code, not part of the installable package.
"""

import pathlib
import re
import sys
import urllib.parse
import urllib.request
import zipfile

DOWNLOAD_PAGE = (
    "https://www.leg.state.fl.us/Statutes/index.cfm?Mode=Statutes%20Download&Submenu=7&Tab=statutes"
)
ZIP_LINK_RE = re.compile(r'href="([^"]*FLLawDL\d{4}\.zip)"', re.IGNORECASE)
USER_AGENT = "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"

DOWNLOAD_DIR = pathlib.Path("download")


def find_zip_url() -> str:
    req = urllib.request.Request(DOWNLOAD_PAGE, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = ZIP_LINK_RE.search(html)
    if not m:
        raise RuntimeError(f"couldn't find a FLLawDL<year>.zip link on {DOWNLOAD_PAGE}")
    return urllib.parse.urljoin(DOWNLOAD_PAGE, m.group(1))


def download(url: str, dest: pathlib.Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        written = 0
        while chunk := resp.read(1024 * 1024):
            f.write(chunk)
            written += len(chunk)
            if total:
                print(f"\r  {written:,} / {total:,} bytes ({100 * written / total:.0f}%)", end="")
    print()
    tmp.rename(dest)


def main() -> None:
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    url = find_zip_url()
    zip_name = url.rsplit("/", 1)[-1]
    zip_path = DOWNLOAD_DIR / zip_name

    if zip_path.exists():
        print(f"{zip_path} already exists ({zip_path.stat().st_size:,} bytes) -- skipping download")
    else:
        print(f"downloading {url}")
        download(url, zip_path)
        print(f"wrote {zip_path} ({zip_path.stat().st_size:,} bytes)")

    # The zip itself wraps everything in one top-level folder matching its
    # own name (confirmed: FLLawDL2025.zip's entries all start with
    # "FLLawDL2025/"), so extracting straight into DOWNLOAD_DIR reproduces
    # the same layout FLLawDL2025/ already has (Library/ etc. directly
    # inside download/FLLawDL2025/) instead of double-nesting it.
    extract_dir = DOWNLOAD_DIR / zip_path.stem
    if extract_dir.exists() and any(extract_dir.iterdir()):
        print(f"{extract_dir} already exists and is non-empty -- skipping extraction")
    else:
        print(f"extracting to {DOWNLOAD_DIR}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(DOWNLOAD_DIR)
        n = sum(1 for p in extract_dir.rglob("*") if p.is_file())
        print(f"extracted {n} files")

    library = extract_dir / "Library"
    print()
    print(f"Library files: {library}" + (" (not found!)" if not library.is_dir() else ""))
    if library.is_dir():
        for p in sorted(library.glob("*.nxt")):
            print(f"  {p.name}  {p.stat().st_size:,} bytes")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
