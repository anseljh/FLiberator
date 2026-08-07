"""Identify and order the documents inside each primary-law `.nxt` file.

Scope is the three files holding Florida primary law. The eight finding-aid
files, `uscon.nxt` and the help PDF are deliberately out (see
plans/re-plan.md Phase 9).

Each collection needs its own identity scheme, because none of them can be
addressed the same way:

  statutes      `<title>F.S. 1.01</title>` -- unique per document. Note
                that `CHAPTER n` titles are *not*: every Part index of a
                chapter repeats the bare chapter title, so resolving a
                document by title is only safe for `F.S. n`.
  constitution  all 226 documents self-title `Florida Constitution`.
                Identity comes from the `<a name="A1S03">` anchor each
                section carries -- the same anchor leg.state.fl.us uses.
  session laws  `CHAPTER 2025-n`, unique. Two documents are joint
                resolutions proposing constitutional amendments and carry
                no chapter number at all; they are identified by their
                bill number instead.

The statutes also carry a hierarchy above the section: Title > Chapter >
Part. Only Part and Title need reconstructing -- the chapter is in the
citation itself -- and each comes from a different index document, because
neither is recorded on the sections they contain.

Ordering is canonical, not physical. Document bodies are stored in
build order, which has nothing to do with statutory order -- so every
collection is sorted by a parsed numeric key rather than by file position.
"""

import bisect
import re

STATUTE_TITLE_RE = re.compile(r"<title>\s*F\.S\.\s*([\d.]+)\s*</title>", re.IGNORECASE)
CHAPTER_TITLE_RE = re.compile(r"<title>\s*CHAPTER\s+([\d.]+)\s*</title>", re.IGNORECASE)
CATCHLINE_RE = re.compile(r"<CATCHLINE>(.*?)</CATCHLINE>", re.IGNORECASE | re.DOTALL)
SECTION_DIV_RE = re.compile(r'<div class="Section">', re.IGNORECASE)

CONSTITUTION_ANCHOR_RE = re.compile(r'<a name="A(\d+)S(\d+)"', re.IGNORECASE)
ARTICLE_DIV_RE = re.compile(r'<div class="Article">', re.IGNORECASE)

LAW_TITLE_RE = re.compile(r"<title>\s*CHAPTER\s+(\d{4}-\d+)\s*</title>", re.IGNORECASE)
LAW_HEADING_RE = re.compile(r"CHAPTER\s+(\d{4}-\d+)", re.IGNORECASE)
BILL_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
BILL_NAME_RE = re.compile(r"<BILLNUM>(.*?)</BILLNUM>", re.IGNORECASE | re.DOTALL)
LAW_TITLE_TEXT_RE = re.compile(r"<LAWTITLE>(.*?)</LAWTITLE>", re.IGNORECASE | re.DOTALL)

# Titles are the top tier of the hierarchy, above Chapter. Only the
# *first* chapter of each Title carries the Title header -- 49 documents,
# one per Florida Statutes Title -- so a Title's extent is the half-open
# chapter range up to the next Title's first chapter.
TITLE_MARKER = 'class="TitleNumber"'
TITLE_BLOCK_RE = re.compile(
    r'<div class="Title">\s*<div class="TitleNumber">\s*TITLE\s+([IVXL]+)\s*</div>'
    r"\s*(?P<name>.*?)\s*</div>",
    re.IGNORECASE | re.DOTALL,
)
CHAPTER_NUMBER_RE = re.compile(
    r'<div class="ChapterNumber">\s*CHAPTER\s+(\d+)\s*</div>', re.IGNORECASE
)

# Chapter and Part tables of contents, used to place a section in the
# statutory hierarchy. Their anchors carry the citation directly.
PART_CLASS_RE = re.compile(r'class="(?:Part|SubPart)"', re.IGNORECASE)
PART_NUMBER_RE = re.compile(
    r'<div class="(?:Part|SubPart)Number">\s*(?:PART|SUBPART)\s+([IVXL]+)', re.IGNORECASE
)
INDEX_ANCHOR_RE = re.compile(r"#ID=FS\d{4}(\d{4})\.([\d.]+)", re.IGNORECASE)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def statute_sort_key(citation: str) -> tuple:
    """Canonical order for a bare section number like "1.015".

    The part after the first dot is a *decimal fraction*, not an integer:
    the Florida Statutes run 1.01, 1.015, 1.02, 1.025, 1.04, so a new
    section can always be slotted between two existing ones. Reading it as
    an integer puts 1.015 after 1.02 -- verified against the file's own
    chapter tables of contents, which preserve canonical order.
    """
    chapter, _, rest = citation.partition(".")
    try:
        number = int(chapter)
    except ValueError:
        return (float("inf"), 0.0, citation)
    fraction = 0.0
    if rest:
        digits = rest.replace(".", "")
        fraction = float(f"0.{digits}") if digits.isdigit() else 0.0
    return (number, fraction, rest)


def body_of(html: str) -> str:
    start = html.lower().find("<body")
    return html[start:] if start >= 0 else html


def part_membership(decoded: list[str]) -> dict[str, str]:
    """Map a section citation to the Part it belongs to, e.g. "39.201" ->
    "PART III". Derived from the Part index documents, whose anchors list
    their sections; sections in chapters with no Parts are simply absent."""
    membership: dict[str, str] = {}
    for html in decoded:
        if not PART_CLASS_RE.search(html):
            continue
        number = PART_NUMBER_RE.search(html)
        if number is None:
            continue
        for chapter, section in INDEX_ANCHOR_RE.findall(html):
            membership[f"{int(chapter)}.{section}"] = f"PART {number.group(1)}"
    return membership


def titles(decoded: list[str]) -> list[dict]:
    """The Florida Statutes Titles, ordered, with the chapter each begins at.

    Only the first chapter of a Title carries the Title header, so this
    returns one record per Title (49 in the 2025 edition) rather than one
    per chapter."""
    found = []
    for html in decoded:
        block = TITLE_BLOCK_RE.search(html)
        if block is None:
            continue
        chapter = CHAPTER_NUMBER_RE.search(html)
        if chapter is None:
            continue
        found.append(
            {
                "number": block.group(1),
                "citation": f"TITLE {block.group(1)}",
                "name": _text(block.group("name")),
                "first_chapter": int(chapter.group(1)),
            }
        )
    found.sort(key=lambda title: title["first_chapter"])
    return found


def title_of(chapter: str | int, ordered: list[dict]) -> dict | None:
    """The Title a chapter belongs to: the last one starting at or before it.

    Titles cover half-open chapter ranges (Title I begins at chapter 1,
    Title II at chapter 6), and the ranges have gaps -- there is no chapter
    between 2 and 6 -- so membership is a predecessor search, not a lookup."""
    index = bisect.bisect_right([t["first_chapter"] for t in ordered], int(chapter)) - 1
    return ordered[index] if index >= 0 else None


def title_hierarchy(entries: list[dict]) -> list[dict]:
    """Group emitted sections into the Title tier of the hierarchy.

    Derived from the entries rather than re-scanning the corpus, so the
    Titles and their chapters come out in the same canonical order the
    entries are already in."""
    grouped: dict[str, dict] = {}
    for entry in entries:
        citation = entry.get("title")
        if citation is None:
            continue
        title = grouped.setdefault(
            citation,
            {
                "number": citation.split()[-1],
                "citation": citation,
                "name": entry.get("title_name"),
                "chapters": [],
            },
        )
        if entry["chapter"] not in title["chapters"]:
            title["chapters"].append(entry["chapter"])
    return list(grouped.values())


def statutes(decoded: list[str]) -> list[dict]:
    """One record per statute section, in canonical order."""
    parts = part_membership(decoded)
    hierarchy = titles(decoded)
    by_chapter: dict[str, dict | None] = {}
    found = []
    for html in decoded:
        match = STATUTE_TITLE_RE.search(html)
        if match is None or not SECTION_DIV_RE.search(html):
            continue
        citation = match.group(1)
        catchline = CATCHLINE_RE.search(html)
        chapter = citation.split(".")[0]
        if chapter not in by_chapter:
            by_chapter[chapter] = title_of(chapter, hierarchy)
        title = by_chapter[chapter]
        found.append(
            {
                "citation": f"F.S. {citation}",
                "number": citation,
                "title": title["citation"] if title else None,
                "title_name": title["name"] if title else None,
                "chapter": chapter,
                "part": parts.get(citation),
                "catchline": _text(catchline.group(1)) if catchline else None,
                "path": f"statutes/{int(chapter):04d}/{citation}.html",
                "html": html,
            }
        )
    found.sort(key=lambda d: statute_sort_key(d["number"]))
    return found


def constitution(decoded: list[str]) -> list[dict]:
    """One record per constitution section, keyed by its A<art>S<sec> anchor."""
    found = []
    for html in decoded:
        body = body_of(html)
        if ARTICLE_DIV_RE.search(body):
            continue  # an article's table of contents, not a section
        anchor = CONSTITUTION_ANCHOR_RE.search(body)
        if anchor is None:
            continue
        article, section = int(anchor.group(1)), int(anchor.group(2))
        catchline = CATCHLINE_RE.search(html)
        found.append(
            {
                "citation": f"Art. {article}, s. {section}, Fla. Const.",
                "anchor": f"A{article}S{section:02d}",
                "article": article,
                "section": section,
                "catchline": _text(catchline.group(1)) if catchline else None,
                "path": f"constitution/article-{article:02d}/section-{section:02d}.html",
                "html": html,
            }
        )
    found.sort(key=lambda d: (d["article"], d["section"]))
    return found


def session_laws(decoded: list[str]) -> list[dict]:
    """One record per session-law chapter, plus the joint resolutions."""
    found = []
    for html in decoded:
        match = LAW_TITLE_RE.search(html) or LAW_HEADING_RE.search(body_of(html)[:600])
        title = BILL_RE.search(html)
        name = _text(title.group(1)) if title else None
        if match is None:
            # A joint resolution: no Laws of Florida chapter number.
            if not name:
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
            found.append({
                "citation": name, "chapter": None, "order": (1, name),
                "catchline": name, "path": f"laws/joint-resolutions/{slug}.html",
                "html": html,
            })
            continue
        chapter = match.group(1)
        # The <title> of a session law is just "CHAPTER 2025-3", which
        # repeats the citation. The bill it enacted is the useful label.
        bill = BILL_NAME_RE.search(html)
        act = LAW_TITLE_TEXT_RE.search(html)
        summary = _text(act.group(1)) if act else None
        found.append({
            "citation": f"Ch. {chapter}, Laws of Fla.",
            "chapter": chapter,
            "order": (0, int(chapter.split("-")[1])),
            "bill": _text(bill.group(1)) if bill else None,
            "catchline": (_text(bill.group(1)) if bill else name),
            "summary": summary[:300] if summary else None,
            "path": f"laws/{chapter}.html",
            "html": html,
        })
    found.sort(key=lambda d: d["order"])
    for record in found:
        record.pop("order")
    return found
