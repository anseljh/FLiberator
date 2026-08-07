"""Validate lf2025.nxt (the 2025 Laws of Florida) against the official PDFs.

The session laws are the second of the three primary-law files that had no
fidelity evidence. They are harder to check than the statutes or the
constitution because **there is no HTML ground truth**: laws.flrules.org
publishes each chapter only as a PDF, so the comparison runs against
`pdftotext` output.

That makes the extraction, not our decoder, the noisy side. Three
adjustments are needed, and each one is a documented property of the PDF
rather than a fudge factor:

  page furniture  every page carries a running head
                  (`Ch. 2025-3 LAWS OF FLORIDA Ch. 2025-3`) and a footer
                  (`CODING: Words stricken are deletions; words underlined
                  are additions.`) with a page number. None of it is
                  statutory text.
  hyphenation     the typeset PDF breaks words across lines with a hyphen,
                  which `pdftotext` preserves: `revi- sion` for
                  "revision". Our text is the correct one here.
  em-dash spacing our HTML wraps the em dash in its own
                  `<span class="EmDash">`, so tag-stripping puts spaces
                  around it where the PDF's inline text has none. This is
                  the same `tag-boundary-space` artifact already
                  identified in the statutes census -- present in neither
                  side's actual output, introduced by comparing.

Chapters are identified by their document title (`CHAPTER 2025-n`), which
is unique here, unlike the `CHAPTER n` collisions in `fs2025.nxt`.

Extracted text is cached under `data/live_cache_laws/`; the PDFs
themselves are deleted after extraction rather than kept, since some
chapters (the General Appropriations Act) run to megabytes.

This is throwaway analysis code, not part of the installable package.
"""

import collections
import difflib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

from nxt_decode_poc import decode
from nxt_depage import reconstruct
from nxt_validate import RATIO_PASS_THRESHOLD, comparable, normalize

NXT_PATH = pathlib.Path("FLLawDL2025/Library/lf2025.nxt")
CACHE_DIR = pathlib.Path("data/live_cache_laws")
REPORT_PATH = pathlib.Path("data/lf2025_validation.json")
FETCH_DELAY_SECONDS = 0.4
YEAR = 2025

TITLE_RE = re.compile(r"<title>\s*CHAPTER\s+(\d{4}-\d+)\s*</title>", re.IGNORECASE)
# The General Appropriations Act titles itself differently ("Chapter
# 2025-198, 2025 Laws of Florida"), so fall back to the chapter number in
# the document's own heading. Two documents legitimately have neither:
# joint resolutions proposing constitutional amendments, which are not
# assigned a Laws of Florida chapter number.
CHAPTER_HEADING_RE = re.compile(r"CHAPTER\s+(\d{4}-\d+)", re.IGNORECASE)


def chapter_of(decoded: str) -> str | None:
    match = TITLE_RE.search(decoded)
    if match:
        return match.group(1)
    body = decoded[decoded.lower().find("<body") :]
    heading = CHAPTER_HEADING_RE.search(body[:600])
    return heading.group(1) if heading else None

# PDF page furniture. Matched against the *un-collapsed* text, because the
# page number is identifiable only by sitting alone on its own line
# immediately above the CODING footer -- once whitespace is collapsed it is
# indistinguishable from a statutory number, and an earlier version of this
# script duly deleted real ones.
# The footer text varies: most chapters carry "CODING: Words stricken are
# deletions; words underlined are additions.", but the General
# Appropriations Act uses "CODING: Language stricken has been vetoed by
# the Governor" on all 533 of its pages. Match the CODING: line whatever
# follows it, rather than enumerating variants.
PAGE_BREAK_RE = re.compile(r"\n\s*\d{1,4}\s*\n\s*CODING:[^\n]*\n", re.I)
RUNNING_HEAD_RE = re.compile(
    r"\x0c\s*(?:Ch\.|CHAPTER)\s*\d{4}-\d+\s+LAWS\s+OF\s+FLORIDA\s+(?:Ch\.|CHAPTER)\s*\d{4}-\d+",
    re.I,
)


# Dot leaders align the appropriations tables. Our HTML keeps them attached
# to the preceding word ("FUND....."); `pdftotext -layout` renders them as
# standalone tokens (53,763 of them in the General Appropriations Act
# alone). Collapsing any run of two-or-more periods -- with or without
# spaces between -- on both sides makes the two comparable. A digit or
# letter between periods stops the match, so "s. 1." and "U.S." survive.
#
# The inner quantifier is bounded (` ?`, not `\s*`) deliberately: the
# obvious `(?:\s*\.\s*){2,}` nests unbounded quantifiers and backtracks
# catastrophically on the appropriations act's dot runs -- it did not
# finish. Both sides have already had whitespace collapsed to single
# spaces by normalize()/clean_pdf_text(), so ` ?` is sufficient.
LEADER_DOTS_RE = re.compile(r"(?:\. ?){2,}")


def clean_pdf_text(text: str) -> str:
    text = PAGE_BREAK_RE.sub("\n", text)
    text = RUNNING_HEAD_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def fold_typesetting(text: str) -> str:
    """Fold the two artifacts that are inherent to comparing against a
    typeset PDF, applied to *both* sides so the fold stays symmetric.

    Em-dash spacing: our HTML wraps the dash in its own span, so
    tag-stripping puts spaces around it that the PDF's inline text lacks.

    Hyphens: the PDF breaks words across lines with a hyphen that
    `pdftotext` keeps (`revi- sion`). De-hyphenating only the PDF side is
    not safe -- it silently merges genuine compounds that happen to break
    at a line end, which is how an earlier version turned `twenty-seven`
    into `twentyseven` and reported it as a difference. Removing every
    hyphen (and any space following it) from both sides is symmetric and
    cannot invent a difference. The cost is that a hyphen we genuinely got
    wrong would be invisible here -- acceptable, and stated, because this
    comparison is against extracted PDF text rather than HTML.
    """
    text = re.sub(r"\s*—\s*", "—", text)
    text = re.sub(r"-\s*", "", text)
    text = LEADER_DOTS_RE.sub(" ", text)
    # Re-collapse: the substitutions above can leave doubled spaces, and
    # callers compare `text.split(" ")`, which turns each one into an empty
    # token. Left in, those empties dominated the word counts -- 7,117 of
    # the appropriations act's reported 10,067 "missing words" were this.
    return re.sub(r"\s+", " ", text).strip()


def fetch_chapter_text(chapter: str) -> str | None:
    cached = CACHE_DIR / f"{chapter}.txt"
    if cached.exists():
        return cached.read_text()
    url = f"http://laws.flrules.org/{YEAR}/{chapter.split('-')[1]}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
    except Exception as exc:
        print(f"[{chapter}] fetch failed: {exc}")
        return None
    if not payload.startswith(b"%PDF"):
        print(f"[{chapter}] not a PDF ({len(payload)} bytes)")
        return None

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as handle:
        handle.write(payload)
        handle.flush()
        result = subprocess.run(
            ["pdftotext", "-layout", handle.name, "-"],
            capture_output=True, text=True, timeout=300, check=False,
        )
    if result.returncode != 0:
        print(f"[{chapter}] pdftotext failed: {result.stderr[:120]}")
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(result.stdout)
    time.sleep(FETCH_DELAY_SECONDS)
    return result.stdout


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    records = reconstruct(NXT_PATH.read_bytes())

    ours: dict[str, str] = {}
    unnumbered = 0
    for record in records:
        decoded, _stats = decode(record, 0, len(record))
        chapter = chapter_of(decoded)
        if chapter is None:
            unnumbered += 1
            continue
        ours[chapter] = decoded[decoded.lower().find("<body") :]

    chapters = sorted(ours, key=lambda c: int(c.split("-")[1]))
    if limit:
        chapters = chapters[:limit]
    print(f"{len(records)} documents = {len(ours)} numbered chapters + "
          f"{unnumbered} joint resolutions (no chapter number)\n")

    ratios: list[float] = []
    exact = 0
    skipped: list[str] = []
    failures: list[tuple[str, float]] = []

    word_gaps: list[tuple[str, int, int]] = []
    for chapter in chapters:
        raw = fetch_chapter_text(chapter)
        if raw is None:
            skipped.append(chapter)
            continue
        live = fold_typesetting(comparable(clean_pdf_text(raw)))
        mine = fold_typesetting(comparable(normalize(ours[chapter])))
        if live == mine:
            exact += 1
            ratios.append(1.0)
            continue

        # Word-level, and multiset-based rather than alignment-based.
        # difflib's ratio() is O(n*m): on the General Appropriations Act
        # (2,024,799 bytes decoded) a character-level ratio simply does not
        # finish. quick_ratio() is the same similarity measure difflib
        # defines, computed from the word multiset in linear time, and the
        # concrete counts below are what actually gets judged.
        live_words, our_words = live.split(" "), mine.split(" ")
        ratio = difflib.SequenceMatcher(None, live_words, our_words).quick_ratio()
        ratios.append(ratio)

        live_count, our_count = collections.Counter(live_words), collections.Counter(our_words)
        missing = sum((live_count - our_count).values())
        extra = sum((our_count - live_count).values())
        if missing or extra:
            word_gaps.append((chapter, missing, extra))
        if ratio < RATIO_PASS_THRESHOLD:
            failures.append((chapter, ratio))
            print(f"[{chapter}] BELOW ratio={ratio:.4f} "
                  f"({missing:,} words only in the PDF, {extra:,} only in ours)")

    n = len(ratios)
    print("=" * 60)
    if n:
        passing = sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD)
        print(f"compared {n} chapters: {exact} byte-exact ({exact / n:.1%}), "
              f"{passing} at/above {RATIO_PASS_THRESHOLD} ({passing / n:.1%})")
        print(f"mean ratio {sum(ratios) / n:.5f}, worst {min(ratios):.4f}")
    if word_gaps:
        total_missing = sum(g[1] for g in word_gaps)
        total_extra = sum(g[2] for g in word_gaps)
        print(f"{len(word_gaps)} chapters differ by word content: "
              f"{total_missing:,} words only in the PDFs, {total_extra:,} only in ours")
        for chapter, missing, extra in sorted(word_gaps, key=lambda g: -(g[1] + g[2]))[:6]:
            print(f"   {chapter}: -{missing:,} / +{extra:,}")
    if skipped:
        print(f"skipped (no usable PDF): {len(skipped)} -- {skipped[:8]}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        "chapters_compared": n,
        "byte_exact": exact,
        "at_or_above_threshold": sum(1 for r in ratios if r >= RATIO_PASS_THRESHOLD),
        "mean_ratio": (sum(ratios) / n) if n else None,
        "below_threshold": sorted(failures, key=lambda f: f[1]),
        "word_gaps": sorted(word_gaps, key=lambda g: -(g[1] + g[2]))[:25],
        "skipped": skipped,
    }, indent=2))
    print(f"wrote {REPORT_PATH}")
    sys.exit(0 if not failures and not skipped else 1)


if __name__ == "__main__":
    main()
