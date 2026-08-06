"""Classify *why* each statute section differs from the live site.

The census (`nxt_validate.py --all`) produces two numbers -- how many
sections are byte-exact, and how many clear the 0.99 ratio threshold --
and neither is a verdict on its own.

The ratio threshold in particular is misleading here. Every section
carrying footnotes differs from the live site in the same known,
undecided way: the source encodes a literal `[1]` where the site renders
a stripped superscript `1`. That is a Phase 9 representation question,
not a defect. But its *cost to the ratio* depends on document length, so
short footnote-dense sections dip below 0.99 while long ones sail past
it. F.S. 122.18 scores 0.9883 with four footnote markers in 687
characters; F.S. 320.08058 scores 1.0000 with the same class of
difference in 171,038. Ranking by ratio sorts by length, not by badness.

So this script classifies the *shape* of every difference instead, and
runs entirely offline against the cache the census populated. The
question it answers is the one that matters: **are there any difference
shapes outside the known classes?** A census that ends with "24,866
sections, every difference is a footnote marker" is a strong result. The
same census reported as "N below threshold" is close to meaningless.

Known classes:
  footnote-marker  live `1`, ours `[1]` -- the undecided Phase 9 call
  note-marker      the same for lettered/starred editorial notations
  (anything else)  reported verbatim, with examples, as UNCLASSIFIED

This is throwaway analysis code, not part of the installable package.
"""

import collections
import difflib
import json
import pathlib
import re
import sys

from nxt_validate import (
    CACHE_DIR,
    INDEX_PATH,
    NXT_PATH,
    RATIO_PASS_THRESHOLD,
    comparable,
    decode_local_text,
    load_records,
)

FOOTNOTE_RE = re.compile(r"^\[?([0-9]+)\]?$")
NOTE_RE = re.compile(r"^\[?([a-z]|\*+)\]?$", re.IGNORECASE)
REPORT_PATH = pathlib.Path("data/fs2025_diff_classes.json")


def classify(live: list[str], ours: list[str]) -> str:
    """Name the shape of one aligned difference, or return UNCLASSIFIED."""
    live_join, our_join = " ".join(live).strip(), " ".join(ours).strip()
    if live_join == our_join:
        return "whitespace-only"
    live_m, our_m = FOOTNOTE_RE.match(live_join), FOOTNOTE_RE.match(our_join)
    if live_m and our_m and live_m.group(1) == our_m.group(1):
        return "footnote-marker"
    live_n, our_n = NOTE_RE.match(live_join), NOTE_RE.match(our_join)
    if live_n and our_n and live_n.group(1) == our_n.group(1):
        return "note-marker"
    return "UNCLASSIFIED"


def cache_path(citation: str) -> pathlib.Path:
    return CACHE_DIR / f"{citation.removeprefix('F.S. ')}.txt"


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    index = json.loads(INDEX_PATH.read_text())
    records = load_records(NXT_PATH)

    citations = sorted(e["title"] for e in index["entries"] if e["title"].startswith("F.S. "))
    citations = [c for c in citations if cache_path(c).exists()]
    if limit:
        citations = citations[:limit]

    classes: collections.Counter = collections.Counter()
    sections_by_class: collections.Counter = collections.Counter()
    unclassified_examples: list[tuple[str, str, str]] = []
    exact = below_threshold = 0
    clean_but_low: list[tuple[str, float]] = []

    for citation in citations:
        live_cmp = comparable(cache_path(citation).read_text())
        our_cmp = comparable(decode_local_text(citation, index, records))
        if live_cmp == our_cmp:
            exact += 1
            continue

        ratio = difflib.SequenceMatcher(None, live_cmp, our_cmp).ratio()
        if ratio < RATIO_PASS_THRESHOLD:
            below_threshold += 1

        live_words, our_words = live_cmp.split(" "), our_cmp.split(" ")
        seen: set[str] = set()
        matcher = difflib.SequenceMatcher(None, live_words, our_words, autojunk=False)
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                continue
            kind = classify(live_words[i1:i2], our_words[j1:j2])
            classes[kind] += 1
            seen.add(kind)
            if kind == "UNCLASSIFIED" and len(unclassified_examples) < 25:
                unclassified_examples.append(
                    (citation, " ".join(live_words[i1:i2])[:70],
                     " ".join(our_words[j1:j2])[:70])
                )
        for kind in seen:
            sections_by_class[kind] += 1
        # A section whose every difference is a known class, yet scores
        # below the threshold, is a threshold artifact -- not a defect.
        if ratio < RATIO_PASS_THRESHOLD and "UNCLASSIFIED" not in seen:
            clean_but_low.append((citation, ratio))

    n = len(citations)
    print(f"classified {n:,} cached sections\n")
    print(f"  byte-exact                     {exact:>7,}  ({exact / n:.2%})")
    print(f"  differ                         {n - exact:>7,}")
    print(f"  below the {RATIO_PASS_THRESHOLD} ratio threshold  {below_threshold:>7,}")
    print(f"  of those, only known classes   {len(clean_but_low):>7,}  <- threshold artifacts\n")

    print("difference shapes (occurrences / sections affected):")
    for kind, count in classes.most_common():
        print(f"  {kind:<18} {count:>8,}  in {sections_by_class[kind]:>6,} sections")

    if unclassified_examples:
        print("\nUNCLASSIFIED examples -- these are what need explaining:")
        for citation, live, ours in unclassified_examples:
            print(f"  [{citation}]\n      live: {live!r}\n      ours: {ours!r}")
    else:
        print("\nNo unclassified differences: every difference is a known class.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "sections_classified": n,
                "byte_exact": exact,
                "below_threshold": below_threshold,
                "below_threshold_but_only_known_classes": len(clean_but_low),
                "difference_shapes": dict(classes),
                "sections_affected_by_shape": dict(sections_by_class),
                "unclassified_examples": unclassified_examples,
                "threshold_artifacts": sorted(clean_but_low, key=lambda r: r[1])[:50],
            },
            indent=2,
        )
    )
    print(f"\nwrote {REPORT_PATH}")
    sys.exit(1 if classes.get("UNCLASSIFIED") else 0)


if __name__ == "__main__":
    main()
