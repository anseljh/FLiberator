"""Phase 4b: compare *markup* against leg.state.fl.us, not just text.

`nxt_validate.py` strips every tag before comparing, so it measures whether
the words are right and in the right order -- nothing more. Both defects
found in Phase 2e (doubled characters, the leaked `LPDD` record marker)
lived in exactly that blind spot, and Phase 9 ships HTML, so "the words are
right" is not the property that actually matters.

This script compares the element stream instead: for the same content
region on both sides, the ordered sequence of (tag name, attributes). Three
things are checked separately, because they fail for different reasons:

  tags     the element sequence, ignoring attributes entirely
  classes  the `class` attribute on each element, in order
  links    every anchor's *target citation*, normalized so the two sides
           are comparable at all -- ours encodes an internal reference
           (`#!-- #ID=FS20250001.01 --#`), the live site a real URL
           (`...URL=0000-0099/0001/Sections/0001.01.html`). Both encode
           "1.01", and that is what gets compared.

Other attributes (`xml:space`, `colspan`, `xmlns`, ...) are compared as a
group. `href` values are deliberately excluded from that comparison and
handled by the `links` check instead, since their raw text can never match.

Raw HTML is cached under data/live_cache_html/ (git-ignored), separately
from nxt_validate.py's reduced-text cache -- that one has already thrown
the tags away.

This is throwaway analysis code, not part of the installable package.
"""

import collections
import difflib
import json
import pathlib
import random
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

from nxt_decode_poc import decode
from nxt_depage import load_records
from nxt_validate import INDEX_PATH, NXT_PATH, build_url

CACHE_DIR = pathlib.Path("data/live_cache_html")
FETCH_DELAY_SECONDS = 0.4

CONTENT_START_RE = re.compile(r'<div class="Section">', re.IGNORECASE)
BODY_CLOSE_RE = re.compile(r"</body>", re.IGNORECASE)

# Our internal reference vs. the live site's URL, both carrying a citation.
OUR_ID_RE = re.compile(r"#ID=FS\d{4}(\d{4})\.([0-9.]+)")
LIVE_URL_RE = re.compile(r"/Sections/(\d{4})\.([0-9.]+)\.html", re.IGNORECASE)
# Non-section anchor targets that appear on both sides (session laws, etc.)
OUR_LAW_RE = re.compile(r"#ID=(LAW[0-9-]+)")

VOID = {"br", "hr", "img", "input", "meta", "link", "source", "col", "area", "base"}


class ElementStream(HTMLParser):
    """Collect (tag, attrs) in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict]] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.elements.append((tag, dict(attrs)))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        self.elements.append((tag, dict(attrs)))


def content_fragment(full_html: str) -> str:
    start = CONTENT_START_RE.search(full_html)
    if not start:
        return full_html
    rest = full_html[start.start() :]
    end = BODY_CLOSE_RE.search(rest)
    return rest[: end.start()] if end else rest


def link_target(href: str) -> str | None:
    """Reduce an anchor's href to the citation it points at, on either side."""
    for pattern in (OUR_ID_RE, LIVE_URL_RE):
        m = pattern.search(href)
        if m:
            return f"{int(m.group(1))}.{m.group(2)}"
    m = OUR_LAW_RE.search(href)
    return m.group(1) if m else None


def profile(fragment: str) -> dict:
    stream = ElementStream()
    stream.feed(fragment)
    tags, classes, others, links = [], [], [], []
    for tag, attrs in stream.elements:
        tags.append(tag)
        classes.append(attrs.get("class", ""))
        rest = {k: v for k, v in attrs.items() if k not in ("href", "class")}
        others.append(tuple(sorted(rest.items())))
        if "href" in attrs:
            links.append(link_target(attrs["href"]))
    return {"tags": tags, "classes": classes, "others": others, "links": links}


def fetch_live_html(citation: str) -> str:
    cached = CACHE_DIR / f"{citation.removeprefix('F.S. ')}.html"
    if cached.exists():
        return cached.read_text()
    req = urllib.request.Request(
        build_url(citation),
        headers={"User-Agent": "FLiberator/0.1 (+https://github.com/anseljh/FLiberator)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(raw)
    time.sleep(FETCH_DELAY_SECONDS)
    return raw


def main() -> None:
    args = sys.argv[1:]
    count = int(args[0]) if args else 100
    seed = int(args[1]) if len(args) > 1 else 0

    index = json.loads(INDEX_PATH.read_text())
    records = load_records(NXT_PATH)
    by_title = {e["title"]: e for e in index["entries"]}
    pool = sorted(t for t in by_title if t.startswith("F.S. "))
    citations = sorted(random.Random(seed).sample(pool, min(count, len(pool))))

    totals = collections.Counter()
    extra: collections.Counter = collections.Counter()      # in ours, not live
    missing: collections.Counter = collections.Counter()    # in live, not ours
    changed: collections.Counter = collections.Counter()    # aligned but different
    link_extra: collections.Counter = collections.Counter()
    link_missing: collections.Counter = collections.Counter()
    clean_sections = 0

    for citation in citations:
        record = records[by_title[citation]["record"]]
        decoded, _stats = decode(record, 0, len(record))
        try:
            live_raw = fetch_live_html(citation)
        except Exception as exc:  # network problems shouldn't abort the run
            print(f"[{citation}] SKIP -- fetch failed: {exc}")
            continue

        mine = profile(content_fragment(decoded))
        theirs = profile(content_fragment(live_raw))
        totals["compared"] += 1
        totals["live_elements"] += len(theirs["tags"])
        totals["our_elements"] += len(mine["tags"])

        # Align on (tag, class, other attributes) rather than comparing
        # position by position -- a single inserted element would otherwise
        # shift everything after it and report as hundreds of differences.
        # autojunk must be off: statute markup repeats a handful of class
        # names (div.Subsection, span.Number, ...) hundreds of times, and
        # SequenceMatcher's default heuristic discards exactly those as
        # "popular", which wrecks the alignment on long sections (F.S.
        # 39.303 reported 131 bogus differences with it on, against text
        # that matches the live page character for character).
        a = list(zip(theirs["tags"], theirs["classes"], theirs["others"], strict=True))
        b = list(zip(mine["tags"], mine["classes"], mine["others"], strict=True))
        dirty = False
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if op == "equal":
                totals["matched_elements"] += i2 - i1
                continue
            dirty = True
            if op in ("delete", "replace"):
                for tag, cls, _o in a[i1:i2]:
                    missing[f"<{tag} class={cls!r}>"] += 1
            if op in ("insert", "replace"):
                for tag, cls, _o in b[j1:j2]:
                    extra[f"<{tag} class={cls!r}>"] += 1
            if op == "replace":
                changed[f"{a[i1][:2]} -> {b[j1][:2]}"] += 1
        if not dirty:
            clean_sections += 1

        live_links = collections.Counter(theirs["links"])
        our_links = collections.Counter(mine["links"])
        for target, k in (our_links - live_links).items():
            link_extra[str(target)] += k
        for target, k in (live_links - our_links).items():
            link_missing[str(target)] += k

    n = totals["compared"]
    print(f"\ncompared {n} sections, element stream vs. leg.state.fl.us")
    print(f"  live elements   {totals['live_elements']:>7,}")
    print(f"  our elements    {totals['our_elements']:>7,}")
    print(f"  aligned exactly {totals['matched_elements']:>7,} "
          f"({totals['matched_elements'] / totals['live_elements']:.2%} of live)")
    print(f"  sections with an identical element stream: {clean_sections}/{n}")

    print(f"\nelements in LIVE but not ours (missing markup) -- {sum(missing.values()):,} total:")
    for kind, k in missing.most_common(8):
        print(f"  {k:>6,}  {kind}")
    if not missing:
        print("   (none)")
    print(f"\nelements in OURS but not live (extra markup) -- {sum(extra.values()):,} total:")
    for kind, k in extra.most_common(8):
        print(f"  {k:>6,}  {kind}")
    if changed:
        print("\naligned-but-different elements:")
        for kind, k in changed.most_common(6):
            print(f"  {k:>6,}  {kind}")

    print(f"\nlink targets in LIVE but not ours: {sum(link_missing.values()):,}")
    for t, k in link_missing.most_common(5):
        print(f"  {k:>6,}  {t}")
    print(f"link targets in OURS but not live: {sum(link_extra.values()):,}")
    for t, k in link_extra.most_common(5):
        print(f"  {k:>6,}  {t}")


if __name__ == "__main__":
    main()
