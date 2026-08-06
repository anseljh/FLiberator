"""Phase 4: validation harness -- diff decoded .nxt section text against the
live leg.state.fl.us page for the same citation.

Approach: leg.state.fl.us serves each section's HTML using the *same* class
vocabulary our decoder produces (`class="Section"`, `SectionBody`,
`Catchline`, `History`, ...) -- confirmed by fetching a live page and
comparing its markup to our decoded output. It embeds that markup as its
own self-contained mini-document (<!DOCTYPE...><html>...<body><div
class="Section">...</div></body></html>) inside a much larger page of site
chrome (nav, year picker, footer) that has its own separate <body>. So
both sides are reduced the same way: grab everything from
`<div class="Section">` to the next `</body>` (or to the end of the string,
for the small number of our own documents whose closing tags themselves
got swallowed by a page-boundary interruption -- see "Phase 4" in
docs/nxt-format.md), strip all tags, unescape HTML entities, collapse
whitespace, then fold away two confirmed-cosmetic differences (doubled
em-dash, straight vs. curly quotes -- see `comparable()`). What's left
should match almost exactly if the decoder is right, not just "roughly
similar."

Default citations were chosen to cover distinct edge cases (see
docs/nxt-format.md "Phase 4" for the full run results and analysis):
  - F.S. 1.01     simple baseline (hand-verified word-for-word in Phase 2 --
                   this harness found a small gap that check missed, see
                   docs/nxt-format.md)
  - F.S. 145.10   a real <table> (property appraiser salary schedule)
  - F.S. 215.22   heavy historical/amendment notes (59 History citations)
  - F.S. 775.082  cross-references to other chapters (32 internal anchors)
  - F.S. 6.081    non-ASCII text (degree/minute/second geographic coordinates)

This is throwaway analysis code, not part of the installable package.
"""

import difflib
import html as html_module
import json
import pathlib
import random
import re
import sys
import time
import urllib.request

from nxt_decode_poc import decode
from nxt_depage import load_records

INDEX_PATH = pathlib.Path("data/fs2025_citation_index.json")
NXT_PATH = pathlib.Path("FLLawDL2025/Library/fs2025.nxt")

TAG_RE = re.compile(r"<[^>]+>")
# Anchor on <div class="Section"> rather than <body>: the live page embeds
# the section as its own nested mini-document (<!DOCTYPE...><html>...<body>
# <div class="Section">...</div></body></html>) inside a much larger page
# of site chrome (nav, year picker, footer) that also has its own <body>.
# Matching from the outer <body> pulls in all of that chrome; matching from
# <div class="Section"> goes straight to the content on both the live page
# and our own decoded output.
SECTION_START_RE = re.compile(r'<div class="Section">', re.IGNORECASE)
BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)

DEFAULT_CITATIONS = [
    "F.S. 1.01",
    "F.S. 145.10",
    "F.S. 215.22",
    "F.S. 775.082",
    "F.S. 6.081",
]


def build_url(citation: str) -> str:
    """F.S. <chapter>.<rest> -> leg.state.fl.us section URL. Chapters are
    grouped into century-wide folders (e.g. chapter 626 -> 0600-0699/0626/),
    confirmed against known-good URLs used earlier in this project."""
    num = citation.removeprefix("F.S. ")
    chapter_str, _, rest = num.partition(".")
    chapter = int(chapter_str)
    century = (chapter // 100) * 100
    range_folder = f"{century:04d}-{century + 99:04d}"
    chapter_padded = f"{chapter:04d}"
    filename = f"{chapter_padded}.{rest}.html" if rest else f"{chapter_padded}.html"
    return (
        "https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute"
        f"&Search_String=&URL={range_folder}/{chapter_padded}/Sections/{filename}"
    )


def normalize(fragment: str) -> str:
    text = TAG_RE.sub(" ", fragment)
    text = html_module.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Our decoded HISTORY citations keep their <a href="...">...</a> anchor
    # wrapping (a real, confirmed bonus over the live page's plain text --
    # see docs/nxt-format.md "Phase 2"); stripping that closing tag leaves a
    # space before the punctuation that follows it (e.g. "90-92 ;") that the
    # live side, with no tag there, never had. Collapse it so the ratio
    # reflects real content, not this structural-fidelity side effect.
    return re.sub(r"\s+([;:,.)])", r"\1", text)


# Known, understood, non-bug differences between decoded and live text --
# folded away before the match/mismatch verdict so it reflects real content
# fidelity rather than these two already-documented cosmetic quirks:
#  - the raw NXT stream encodes some punctuation twice (a literal Unicode
#    character immediately followed by its own HTML-entity twin -- e.g.
#    em-space, confirmed in docs/nxt-format.md as deliberate, probably one
#    copy for full-text search indexing and one for guaranteed rendering).
#    Collapsing "each char run + its own entity" isn't practical generically,
#    so this only folds the two confirmed-common cases, doubled em-dash and
#    doubled en-dash (the latter found by the Phase 2d 200-section sample,
#    in F.S. 381.00316's "21 U.S.C. 360bbb--3" citation).
#  - leg.state.fl.us applies a "smart quotes" typographic upgrade when
#    rendering straight ASCII apostrophes from the source data (confirmed:
#    the raw .nxt bytes for one such case contain a plain 0x27 apostrophe,
#    not a curly one) -- cosmetic, not a decoding gap, so both sides are
#    normalized to plain ASCII quotes for comparison.
def comparable(text: str) -> str:
    text = text.replace("——", "—").replace("––", "–")
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text


def extract_body_text(full_html: str) -> str:
    """Grab the <div class="Section">...</div> content. Anchored on
    </body> when present (the live page always has one -- it's what keeps
    the surrounding site chrome out of the comparison); falls back to "rest
    of string" when it's not (our own decoder's output for some documents
    has no literal </body> at all -- its closing tags got swallowed by the
    same page-boundary interruption documented in docs/nxt-format.md
    "Phase 2b", this time hitting the tail of the document instead of its
    title). That fallback deliberately keeps whatever partial garbage
    trails off the end rather than discarding it -- this harness is
    supposed to surface exactly that kind of damage, not hide it."""
    start = SECTION_START_RE.search(full_html)
    if not start:
        return normalize(full_html)
    rest = full_html[start.end() :]
    end = BODY_CLOSE_RE.search(rest)
    fragment = rest[: end.start()] if end else rest
    return normalize(fragment)


CACHE_DIR = pathlib.Path("data/live_cache")
FETCH_DELAY_SECONDS = 0.4


def fetch_live_text(citation: str) -> tuple[str, str]:
    """Fetch and reduce the live page, caching the reduced text on disk.

    The cache exists so a corpus-wide run (`--sample N`) is a one-time cost
    against leg.state.fl.us and every re-run afterwards is free and offline
    -- which is what makes this usable as a routine regression gate rather
    than a thing to be run once and quoted from memory."""
    url = build_url(citation)
    cached = CACHE_DIR / f"{citation.removeprefix('F.S. ')}.txt"
    if cached.exists():
        return cached.read_text(), url

    req = urllib.request.Request(
        url, headers={"User-Agent": "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    text = extract_body_text(raw)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text)
    time.sleep(FETCH_DELAY_SECONDS)  # be a polite guest on a state web server
    return text, url


def decode_local_text(citation: str, index: dict, records: list[bytes]) -> str:
    by_title = {e["title"]: e for e in index["entries"]}
    entry = by_title.get(citation)
    if entry is None:
        raise KeyError(f"{citation!r} not found in index")
    span = records[entry["record"]]
    decoded_html, _stats = decode(span, 0, len(span))
    return extract_body_text(decoded_html)


RATIO_PASS_THRESHOLD = 0.99


def sample_citations(index: dict, count: int, seed: int) -> list[str]:
    """A reproducible random sample of real section citations, so the pass
    rate below describes the corpus rather than a hand-picked shortlist."""
    pool = sorted(e["title"] for e in index["entries"] if e["title"].startswith("F.S. "))
    return sorted(random.Random(seed).sample(pool, min(count, len(pool))))


def main() -> None:
    args = sys.argv[1:]
    index = json.loads(INDEX_PATH.read_text())

    if args and args[0] == "--sample":
        count = int(args[1]) if len(args) > 1 else 100
        seed = int(args[2]) if len(args) > 2 else 0
        citations = sample_citations(index, count, seed)
    else:
        citations = args or DEFAULT_CITATIONS

    records = load_records(NXT_PATH)
    ratios: list[float] = []

    all_ok = True
    for citation in citations:
        try:
            local_text = decode_local_text(citation, index, records)
        except KeyError as e:
            print(f"[{citation}] SKIP -- {e}")
            all_ok = False
            continue

        try:
            live_text, url = fetch_live_text(citation)
        except Exception as e:
            print(f"[{citation}] SKIP -- fetch failed: {e}")
            all_ok = False
            continue

        live_cmp, local_cmp = comparable(live_text), comparable(local_text)
        ratio = difflib.SequenceMatcher(None, live_cmp, local_cmp).ratio()
        exact = live_cmp == local_cmp
        ok = ratio >= RATIO_PASS_THRESHOLD
        all_ok &= ok

        ratios.append(ratio)
        status = "MATCH" if exact else ("CLOSE" if ok else "MISMATCH")
        print(f"[{citation}] {status} ratio={ratio:.4f} ({len(local_text)} chars) -- {url}")
        # In a large sample the near-misses are noise; only the real
        # failures are worth the screenfuls of word-level diff.
        if exact or (ok and len(citations) > 10):
            continue

        diff = difflib.unified_diff(
            live_cmp.split(" "),
            local_cmp.split(" "),
            fromfile="live",
            tofile="decoded",
            lineterm="",
        )
        for line in list(diff)[:60]:
            print("   ", line)
        print()

    print("=" * 60)
    if ratios:
        exact = sum(1 for r in ratios if r == 1.0)
        passing = sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD)
        n = len(ratios)
        print(f"compared {n} citations: {exact} exact ({exact / n:.1%}), "
              f"{passing} at/above {RATIO_PASS_THRESHOLD} ({passing / n:.1%})")
        print(f"mean ratio {sum(ratios) / n:.5f}, worst {min(ratios):.4f}")
    print("ALL PASS" if all_ok else "SOME BELOW THRESHOLD")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
