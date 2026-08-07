"""Validate flcnst2025.nxt (the Florida Constitution) against the live site.

All fidelity work through Phase 4d targeted `fs2025.nxt`. Three other files
hold primary law, and had no fidelity evidence of any kind -- they were
known to reassemble and to decode to well-formed HTML, nothing more. This
covers the constitution, which is the most valuable of the three.

Two things make it easier than the statutes:

  * The live site publishes the whole constitution as **one page** rather
    than one page per section, so this costs a single request instead of
    213. The page is cached anyway, for offline re-runs.
  * Our section documents carry `<a name="A1S03">` -- the *same* anchor the
    live page uses -- so a document maps to its live counterpart directly.
    No ordering assumption is needed, which matters: the documents are not
    stored in canonical order (document 2 is A1S03, document 3 is A1S02),
    exactly as in `fs2025.nxt`.

The counts line up before any comparison runs: 226 documents = 1
constitution-title page + 12 article indexes + 213 sections, against 213
`A#S##` anchors on the live page.

Scoring reuses `nxt_validate.normalize`/`comparable` so the numbers mean
the same thing they do for the statutes.

This is throwaway analysis code, not part of the installable package.
"""

import difflib
import pathlib
import re
import sys
import urllib.request

from nxt_decode_poc import decode
from nxt_depage import reconstruct
from nxt_validate import RATIO_PASS_THRESHOLD, comparable, normalize

NXT_PATH = pathlib.Path("FLLawDL2025/Library/flcnst2025.nxt")
CACHE_PATH = pathlib.Path("data/live_cache/florida_constitution.html")
LIVE_URL = (
    "https://www.leg.state.fl.us/Statutes/index.cfm"
    "?Mode=Constitution&Submenu=3&Tab=statutes"
)

OUR_ANCHOR_RE = re.compile(r'<a name="(A\d+S\d+)">', re.IGNORECASE)
SECTION_DIV_RE = re.compile(r'<div class="Section">', re.IGNORECASE)
ARTICLE_DIV_RE = re.compile(r'<div class="Article">', re.IGNORECASE)
BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)


def fetch_live() -> str:
    if CACHE_PATH.exists():
        return CACHE_PATH.read_text()
    request = urllib.request.Request(
        LIVE_URL,
        headers={"User-Agent": "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(raw)
    return raw


def live_sections(page: str) -> dict[str, str]:
    """Split the single live page into one fragment per section anchor.

    A section runs from its own `<div class="Section">` to whichever comes
    first: the next section, the next article's heading block, or the end
    of the content. That last boundary is load-bearing -- the constitution
    is embedded in the site's own page, so without it the final section
    (A12S42) absorbs the footer chrome and scores 0.88 on a copyright
    notice. `</body>` is the same content boundary `nxt_validate.py` uses.
    """
    starts = [m.start() for m in SECTION_DIV_RE.finditer(page)]
    articles = [m.start() for m in ARTICLE_DIV_RE.finditer(page)]
    content_end = BODY_CLOSE_RE.search(page)
    boundaries = sorted(starts + articles + [content_end.start() if content_end else len(page)])

    found: dict[str, str] = {}
    for start in starts:
        end = next(b for b in boundaries if b > start)
        fragment = page[start:end]
        anchor = OUR_ANCHOR_RE.search(fragment)
        if anchor:
            found[anchor.group(1).upper()] = fragment
    return found


def main() -> None:
    verbose = "--verbose" in sys.argv
    records = reconstruct(NXT_PATH.read_bytes())
    page = fetch_live()
    live = live_sections(page)

    ours: dict[str, str] = {}
    articles = 0
    other = 0
    for record in records:
        decoded, _stats = decode(record, 0, len(record))
        body = decoded[decoded.lower().find("<body") :]
        if ARTICLE_DIV_RE.search(body):
            articles += 1
            continue
        anchor = OUR_ANCHOR_RE.search(body)
        if anchor is None:
            other += 1
            continue
        ours[anchor.group(1).upper()] = body

    print(f"{len(records)} documents = {other} front matter + {articles} article indexes "
          f"+ {len(ours)} sections")
    print(f"live page: {len(page):,} bytes, {len(live)} section anchors\n")

    missing = sorted(set(live) - set(ours))
    extra = sorted(set(ours) - set(live))
    if missing:
        print(f"!! {len(missing)} live sections with no document of ours: {missing[:10]}")
    if extra:
        print(f"!! {len(extra)} documents with no live counterpart: {extra[:10]}")

    ratios: list[float] = []
    exact = 0
    failures: list[tuple[str, float]] = []
    for anchor in sorted(set(ours) & set(live)):
        live_text = comparable(normalize(live[anchor]))
        our_text = comparable(normalize(ours[anchor]))
        ratio = difflib.SequenceMatcher(None, live_text, our_text).ratio()
        ratios.append(ratio)
        if live_text == our_text:
            exact += 1
        elif ratio < RATIO_PASS_THRESHOLD:
            failures.append((anchor, ratio))
        if verbose and live_text != our_text:
            print(f"[{anchor}] ratio={ratio:.4f}")
            diff = difflib.unified_diff(
                live_text.split(" "), our_text.split(" "),
                fromfile="live", tofile="decoded", lineterm="",
            )
            for line in list(diff)[:24]:
                print("   ", line)

    n = len(ratios)
    print("=" * 60)
    print(f"compared {n} sections: {exact} byte-exact ({exact / n:.1%}), "
          f"{sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD)} at/above "
          f"{RATIO_PASS_THRESHOLD} ({sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD) / n:.1%})")
    print(f"mean ratio {sum(ratios) / n:.5f}, worst {min(ratios):.4f}")
    for anchor, ratio in sorted(failures, key=lambda f: f[1])[:10]:
        print(f"  BELOW THRESHOLD  {anchor}  {ratio:.4f}")

    ok = not missing and not extra and not failures
    print("ALL PASS" if ok else "SOME BELOW THRESHOLD")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
