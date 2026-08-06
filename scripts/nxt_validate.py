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
SECTION_START_RE = re.compile(r'<div class="(?:Section|ChapterTitle)">', re.IGNORECASE)
# Part indexes need their own anchor. The live Part page starts at
# <div class="PartTitle"> with no chapter heading above it, while our decoded
# Part document carries the chapter heading first -- anchoring both sides on
# PartTitle lines them up; anchoring on the default would leave our side with
# an extra "CHAPTER n" the live side never had.
PART_START_RE = re.compile(r'<div class="(?:Part|SubPart)Title">', re.IGNORECASE)
BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)

DEFAULT_CITATIONS = [
    "F.S. 1.01",
    "F.S. 145.10",
    "F.S. 215.22",
    "F.S. 775.082",
    "F.S. 6.081",
]


def build_url(citation: str) -> str:
    """Citation -> leg.state.fl.us URL. Chapters are grouped into century-wide
    folders (e.g. chapter 626 -> 0600-0699/0626/), confirmed against known-good
    URLs used earlier in this project. Two shapes are handled:
      "F.S. 15.01" -> .../0015/Sections/0015.01.html   (a statute section)
      "CHAPTER 15" -> .../0015/0015ContentsIndex.html  (a chapter TOC page)"""
    if citation.startswith("CHAPTER "):
        rest = citation.removeprefix("CHAPTER ")
        number, _, part = rest.partition(" PART ")
        chapter = int(number)
        century = (chapter // 100) * 100
        padded = f"{chapter:04d}"
        page = f"{padded}Part{part}ContentsIndex.html" if part else f"{padded}ContentsIndex.html"
        return (
            "https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute"
            f"&URL={century:04d}-{century + 99:04d}/{padded}/{page}"
            "&StatuteYear=2025"
        )
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


# One known, understood, non-bug difference between decoded and live text,
# folded away before the match/mismatch verdict: leg.state.fl.us applies a
# "smart quotes" typographic upgrade when rendering straight ASCII apostrophes
# from the source data (confirmed: the raw .nxt bytes for one such case contain
# a plain 0x27 apostrophe, not a curly one) -- cosmetic, not a decoding gap, so
# both sides are normalized to plain ASCII quotes for comparison.
#
# This used to also fold doubled em-dashes and en-dashes, on the theory that
# the doubling was a quirk of the source data. It wasn't -- it was our own
# decoder emitting both halves of a 0x15-marked character pair, a real defect
# in the output HTML that this fold was hiding from the score (see
# nxt_decode_poc.py's 0x15 rule). The fold is deliberately gone: with the
# decoder fixed it is unnecessary, and keeping it would let the same class of
# defect return unnoticed.
def comparable(text: str) -> str:
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text


def extract_body_text(full_html: str, anchor: re.Pattern | None = None) -> str:
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
    start = (anchor or SECTION_START_RE).search(full_html)
    if not start:
        return normalize(full_html)
    rest = full_html[start.end() :]
    end = BODY_CLOSE_RE.search(rest)
    fragment = rest[: end.start()] if end else rest
    return normalize(fragment)


CACHE_DIR = pathlib.Path("data/live_cache")
FETCH_DELAY_SECONDS = 0.4


def fetch_live_text(citation: str, anchor: re.Pattern | None = None) -> tuple[str, str]:
    """Fetch and reduce the live page, caching the reduced text on disk.

    The cache exists so a corpus-wide run (`--sample N`) is a one-time cost
    against leg.state.fl.us and every re-run afterwards is free and offline
    -- which is what makes this usable as a routine regression gate rather
    than a thing to be run once and quoted from memory."""
    url = build_url(citation)
    cached = CACHE_DIR / (citation.replace(" ", "_") + ".txt"
                          if citation.startswith("CHAPTER ")
                          else f"{citation.removeprefix('F.S. ')}.txt")
    if cached.exists():
        return cached.read_text(), url

    req = urllib.request.Request(
        url, headers={"User-Agent": "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    text = extract_body_text(raw, anchor)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text)
    time.sleep(FETCH_DELAY_SECONDS)  # be a polite guest on a state web server
    return text, url


def decode_local_text(
    citation: str,
    index: dict,
    records: list[bytes],
    record: int | None = None,
    anchor: re.Pattern | None = None,
) -> str:
    """Decode one document. `record` wins when given -- resolving by title
    alone is only safe for `F.S. n` citations, which are unique; CHAPTER
    titles repeat once per Part, so chapter mode passes the record it means."""
    if record is None:
        by_title = {e["title"]: e for e in index["entries"]}
        entry = by_title.get(citation)
        if entry is None:
            raise KeyError(f"{citation!r} not found in index")
        record = entry["record"]
    span = records[record]
    decoded_html, _stats = decode(span, 0, len(span))
    return extract_body_text(decoded_html, anchor)


RATIO_PASS_THRESHOLD = 0.99
DEFAULT_REPORT_PATH = pathlib.Path("data/fs2025_validation_census.json")


def citation_sort_key(citation: str) -> tuple:
    """Sort F.S. citations numerically (1.01 < 1.015 < 1.02 < 2.01), so a
    long run's progress output reads in statutory order."""
    number = citation.removeprefix("F.S. ")
    return tuple(int(p) if p.isdigit() else p for p in number.split("."))


def sample_citations(index: dict, count: int, seed: int) -> list[str]:
    """A reproducible random sample of real section citations, so the pass
    rate below describes the corpus rather than a hand-picked shortlist."""
    pool = sorted(e["title"] for e in index["entries"] if e["title"].startswith("F.S. "))
    return sorted(random.Random(seed).sample(pool, min(count, len(pool))))


# The chapter-level table-of-contents documents. These are the only ones of
# the 1,440 non-section documents that have a directly comparable page on
# leg.state.fl.us, and happily the live site emits the *same* class vocabulary
# for them (`ChapterTitle`, `ChapterNumber`, `CatchlineIndex`, `IndexItem`,
# `Catchline`) that our decoder produces, so they diff exactly like sections do.
CHAPTER_CLASS_RE = re.compile(rb'class="Chapter"')
PART_CLASS_RE = re.compile(rb'class="(?:Part|SubPart)"')
PART_NUMBER_RE = re.compile(r'<div class="(?:Part|SubPart)Number">\s*(?:PART|SUBPART)\s+([IVXL]+)')


def chapter_index_records(index: dict, records: list[bytes]) -> dict[str, int]:
    """Map "CHAPTER n" -> the record holding that chapter's *chapter-level*
    TOC. Many documents share a title like "CHAPTER 39" (one per Part -- see
    docs/nxt-format.md), so the title alone does not identify a document:
    only the one carrying `class="Chapter"` without a `class="Part"` is the
    chapter-level index. Callers must pass the record explicitly rather than
    re-resolving by title, or they'll silently get a Part index instead."""
    found: dict[str, int] = {}
    for entry in index["entries"]:
        title = entry["title"]
        if not title.startswith("CHAPTER "):
            continue
        record = records[entry["record"]]
        if not CHAPTER_CLASS_RE.search(record) or PART_CLASS_RE.search(record):
            continue
        found.setdefault(title, entry["record"])
    return found


def part_index_records(index: dict, records: list[bytes]) -> dict[str, int]:
    """Map "CHAPTER n PART R" -> the record holding that Part's TOC. The Part
    number lives only in the decoded markup (`<div class="PartNumber">PART
    III</div>`), not in the document title -- every Part index of a chapter
    shares the bare title "CHAPTER n", which is why they need disambiguating
    the same way chapter-level indexes do."""
    found: dict[str, int] = {}
    for entry in index["entries"]:
        title = entry["title"]
        if not title.startswith("CHAPTER "):
            continue
        record = records[entry["record"]]
        if not PART_CLASS_RE.search(record):
            continue
        decoded, _stats = decode(record, 0, len(record))
        match = PART_NUMBER_RE.search(decoded)
        if match:
            found.setdefault(f"{title} PART {match.group(1)}", entry["record"])
    return found


def sample_chapters(
    index: dict, records: list[bytes], count: int, seed: int
) -> tuple[list[str], dict[str, int]]:
    pool = chapter_index_records(index, records)
    chosen = random.Random(seed).sample(sorted(pool), min(count, len(pool)))
    chosen.sort(key=lambda t: int(t.removeprefix("CHAPTER ")))
    return chosen, pool


def main() -> None:
    args = sys.argv[1:]
    index = json.loads(INDEX_PATH.read_text())

    records = load_records(NXT_PATH)
    record_overrides: dict[str, int] = {}
    anchor: re.Pattern | None = None

    report_path: pathlib.Path | None = None
    if args and args[0] == "--all":
        # Census rather than sample: every statute section in the index.
        # Resumable -- fetch_live_text caches, so a re-run after a decoder
        # change re-scores from disk in minutes instead of hours.
        citations = sorted(
            (e["title"] for e in index["entries"] if e["title"].startswith("F.S. ")),
            key=citation_sort_key,
        )
        report_path = pathlib.Path(args[1]) if len(args) > 1 else DEFAULT_REPORT_PATH
    elif args and args[0] == "--sample":
        count = int(args[1]) if len(args) > 1 else 100
        seed = int(args[2]) if len(args) > 2 else 0
        citations = sample_citations(index, count, seed)
    elif args and args[0] in ("--chapters", "--parts"):
        count = int(args[1]) if len(args) > 1 else 100
        seed = int(args[2]) if len(args) > 2 else 0
        if args[0] == "--chapters":
            citations, record_overrides = sample_chapters(index, records, count, seed)
        else:
            anchor = PART_START_RE
            record_overrides = part_index_records(index, records)
            pool = sorted(record_overrides)
            citations = sorted(random.Random(seed).sample(pool, min(count, len(pool))))
    else:
        citations = args or DEFAULT_CITATIONS

    ratios: list[float] = []
    results: list[dict] = []
    started = time.time()

    all_ok = True
    for n, citation in enumerate(citations):
        if report_path is not None and n and n % 250 == 0:
            done = time.time() - started
            rate = n / done
            print(
                f"... {n:,}/{len(citations):,} in {done / 60:.0f}m "
                f"({rate:.1f}/s, ~{(len(citations) - n) / rate / 60:.0f}m left)",
                flush=True,
            )
        try:
            local_text = decode_local_text(
                citation, index, records, record_overrides.get(citation), anchor
            )
        except KeyError as e:
            print(f"[{citation}] SKIP -- {e}")
            results.append({"citation": citation, "status": "SKIP", "reason": str(e)})
            all_ok = False
            continue

        try:
            live_text, url = fetch_live_text(citation, anchor)
        except Exception as e:
            print(f"[{citation}] SKIP -- fetch failed: {e}")
            results.append({"citation": citation, "status": "FETCH_FAILED", "reason": str(e)})
            all_ok = False
            continue

        live_cmp, local_cmp = comparable(live_text), comparable(local_text)
        ratio = difflib.SequenceMatcher(None, live_cmp, local_cmp).ratio()
        exact = live_cmp == local_cmp
        ok = ratio >= RATIO_PASS_THRESHOLD
        all_ok &= ok

        ratios.append(ratio)
        status = "MATCH" if exact else ("CLOSE" if ok else "MISMATCH")
        results.append(
            {"citation": citation, "status": status, "ratio": ratio, "chars": len(local_text)}
        )
        # A census prints only what isn't already known-good; at 24,866
        # sections a per-citation MATCH line is 24,866 lines of noise.
        if report_path is None or not exact:
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
    if report_path is not None:
        failures = [r for r in results if r.get("status") not in ("MATCH",)]
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "compared": len(ratios),
                    "exact": sum(1 for r in ratios if r == 1.0),
                    "at_or_above_threshold": sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD),
                    "mean_ratio": (sum(ratios) / len(ratios)) if ratios else None,
                    "elapsed_seconds": round(time.time() - started, 1),
                    "not_exact": sorted(failures, key=lambda r: r.get("ratio", -1)),
                },
                indent=2,
            )
        )
        print(f"wrote {report_path} ({len(failures)} citations not byte-exact)")
    print("ALL PASS" if all_ok else "SOME BELOW THRESHOLD")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
