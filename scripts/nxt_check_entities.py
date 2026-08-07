"""Compare *entity representation* inside elements against the live site.

This is the last unverified layer of fidelity. Three things were already
checked and are not rechecked here:

  Phase 4d  the rendered characters, over all 24,866 sections -- but the
            harness unescapes both sides before comparing, so it proves
            the text is right while saying nothing about how it's spelled.
  Phase 4b  the element stream (tags, classes, link targets).
  Phase 4c  whitespace and doubling, against the source bytes.

What none of them covers: whether a given character arrives as `&#x2003;`
or as a literal em space. Both render identically, so this cannot break
the text -- but the deliverable is HTML, and "our HTML differs from
theirs in ways nobody has ever looked at" is not a claim worth shipping
unexamined.

Method. For each side, walk the HTML with `convert_charrefs=False` so
character references survive as their own events, and build a list of
(character, representation) pairs -- representation being `literal` or the
exact entity text. Because Phase 4d established the rendered strings
agree, the two lists can be aligned on the characters alone; then for
every aligned pair, the representations are compared.

Only the characters that *can* differ are interesting, so pure-ASCII
letters and digits are dropped from the comparison: they are never
entity-encoded on either side and would swamp the signal.

Runs offline against the raw-HTML cache that `nxt_validate_markup.py`
populated (`data/live_cache_html/`), which the reduced-text cache used by
`nxt_validate.py` cannot substitute for -- that one already threw the
entities away.

This is throwaway analysis code, not part of the installable package.
"""

import collections
import difflib
import html
import json
import pathlib
import re
from html.parser import HTMLParser

from nxt_decode_poc import decode
from nxt_depage import load_records
from nxt_validate import INDEX_PATH, NXT_PATH
from nxt_validate_markup import CACHE_DIR, content_fragment

REPORT_PATH = pathlib.Path("data/fs2025_entity_report.json")

# Characters that are never entity-encoded on either side; comparing them
# adds millions of trivially-equal pairs and hides the real signal.
BORING_RE = re.compile(r"[A-Za-z0-9 ]")

# Elements whose text is code, not prose.
SKIP_CONTENT = {"script", "style"}


class CharStream(HTMLParser):
    """Collect (character, representation) for all rendered text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.pairs: list[tuple[str, str]] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in SKIP_CONTENT:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_CONTENT and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self.pairs.extend((char, "literal") for char in data)

    def _reference(self, text: str) -> None:
        if self._skip:
            return
        resolved = html.unescape(text)
        # A multi-character expansion is rare but real; attribute it to the
        # first character so the alignment stays one-to-one.
        for index, char in enumerate(resolved):
            self.pairs.append((char, text if index == 0 else "literal"))

    def handle_entityref(self, name: str) -> None:
        self._reference(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._reference(f"&#{name};")


def stream(fragment: str) -> list[tuple[str, str]]:
    parser = CharStream()
    parser.feed(fragment)
    parser.close()
    return [p for p in parser.pairs if not BORING_RE.fullmatch(p[0])]


def main() -> None:
    index = json.loads(INDEX_PATH.read_text())
    records = load_records(NXT_PATH)
    by_title = {e["title"]: e for e in index["entries"]}

    cached = sorted(CACHE_DIR.glob("*.html"))
    agree = disagree = 0
    shapes: collections.Counter = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    sections_with_disagreement = 0
    compared = 0

    for path in cached:
        citation = f"F.S. {path.stem}"
        entry = by_title.get(citation)
        if entry is None:
            continue
        record = records[entry["record"]]
        decoded, _stats = decode(record, 0, len(record))

        ours = stream(content_fragment(decoded))
        theirs = stream(content_fragment(path.read_text()))
        compared += 1

        our_chars = [c for c, _ in ours]
        their_chars = [c for c, _ in theirs]
        dirty = False
        matcher = difflib.SequenceMatcher(None, their_chars, our_chars, autojunk=False)
        for op, i1, i2, j1, _j2 in matcher.get_opcodes():
            if op != "equal":
                continue
            for k in range(i2 - i1):
                their_repr = theirs[i1 + k][1]
                our_repr = ours[j1 + k][1]
                if their_repr == our_repr:
                    agree += 1
                    continue
                disagree += 1
                dirty = True
                char = their_chars[i1 + k]
                shape = f"U+{ord(char):04X}  live={their_repr!r}  ours={our_repr!r}"
                shapes[shape] += 1
                if len(examples[shape]) < 4:
                    examples[shape].append(citation)
        if dirty:
            sections_with_disagreement += 1

    total = agree + disagree
    print(f"compared {compared} sections, {total:,} aligned non-trivial characters\n")
    if not total:
        print("nothing to compare")
        return
    print(f"  same representation      {agree:>9,}  ({agree / total:.3%})")
    print(f"  different representation {disagree:>9,}  ({disagree / total:.3%})")
    print(f"  sections affected        {sections_with_disagreement:>9,} / {compared}\n")

    if shapes:
        print("representation differences, most common first:")
        for shape, count in shapes.most_common(15):
            print(f"  {count:>7,}  {shape}")
            print(f"           e.g. {', '.join(examples[shape])}")
    else:
        print("No representation differences at all.")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "sections_compared": compared,
                "characters_aligned": total,
                "same_representation": agree,
                "different_representation": disagree,
                "sections_affected": sections_with_disagreement,
                "shapes": dict(shapes),
            },
            indent=2,
        )
    )
    print(f"\nwrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
