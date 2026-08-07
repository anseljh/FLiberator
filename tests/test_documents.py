"""Document identification and canonical ordering."""

from fliberator import documents


def statute(citation: str, catchline: str = "Definitions.") -> str:
    return (
        f"<html><head><title>F.S. {citation}</title></head><body>"
        f'<div class="Section"><span class="SectionNumber">{citation}</span>'
        f"<CATCHLINE>{catchline}</CATCHLINE></div></body></html>"
    )


def chapter_index(title_number: str, title_name: str, chapter: str) -> str:
    """A chapter's table of contents. Only the *first* chapter of a Title
    carries the Title header, which is what makes Title membership a range
    lookup rather than a per-chapter field."""
    return (
        f"<html><head><title>CHAPTER {chapter}</title></head><body>"
        f'<div class="Chapter"><div class="Title">'
        f'<div class="TitleNumber">TITLE {title_number}</div>'
        f'<p xml:space="preserve">{title_name}</p></div>'
        f'<div class="ChapterTitle"><div class="ChapterNumber">CHAPTER {chapter}</div>'
        f'<div class="ChapterName">DEFINITIONS</div></div></div></body></html>'
    )


def test_statute_sort_key_is_numeric_not_lexical():
    # 1.015 sorts between 1.01 and 1.02; a string sort would put it after 1.02.
    order = sorted(["1.02", "1.015", "1.01", "10.01", "2.01"], key=documents.statute_sort_key)
    assert order == ["1.01", "1.015", "1.02", "2.01", "10.01"]


def test_statutes_are_returned_in_canonical_order():
    # Documents are stored in build order, which is unrelated to statutory
    # order -- so the extractor must sort rather than trust file position.
    found = documents.statutes([statute("2.01"), statute("1.015"), statute("1.01")])
    assert [d["number"] for d in found] == ["1.01", "1.015", "2.01"]


def test_statute_record_carries_chapter_and_path():
    (record,) = documents.statutes([statute("122.18", "Certain officers.")])
    assert record["citation"] == "F.S. 122.18"
    assert record["chapter"] == "122"
    assert record["catchline"] == "Certain officers."
    assert record["path"] == "statutes/0122/122.18.html"


def test_chapter_index_documents_are_not_mistaken_for_sections():
    # A chapter TOC has no Section div; only real sections are emitted.
    toc = (
        "<html><head><title>CHAPTER 122</title></head>"
        '<body><div class="Chapter"></div></body></html>'
    )
    assert documents.statutes([toc, statute("122.18")]) == documents.statutes(
        [statute("122.18")]
    )


def test_part_membership_comes_from_the_part_index():
    part = (
        '<html><body><div class="Part"><div class="PartNumber">PART III</div>'
        '<a href="#!-- #ID=FS20250039.201 --#">39.201</a></div></body></html>'
    )
    found = documents.statutes([part, statute("39.201")])
    assert found[0]["part"] == "PART III"


def test_titles_are_read_from_the_first_chapter_of_each():
    found = documents.titles(
        [chapter_index("II", "STATE ORGANIZATION", "6"), chapter_index("I", "CONSTRUCTION", "1")]
    )
    assert [t["citation"] for t in found] == ["TITLE I", "TITLE II"]
    assert found[1]["name"] == "STATE ORGANIZATION"
    assert found[1]["first_chapter"] == 6


def test_a_multiline_title_name_is_flattened():
    # Several Title names carry an explicit <br /> line break.
    (title,) = documents.titles([chapter_index("XVI", "TEACHERS<br />BONDS", "238")])
    assert title["name"] == "TEACHERS BONDS"


def test_title_membership_spans_the_chapters_up_to_the_next_title():
    ordered = documents.titles(
        [chapter_index("I", "CONSTRUCTION", "1"), chapter_index("II", "STATE", "6")]
    )
    # Chapter 2 has no Title header of its own; it belongs to Title I.
    assert documents.title_of("2", ordered)["citation"] == "TITLE I"
    assert documents.title_of("6", ordered)["citation"] == "TITLE II"
    # Ranges have gaps -- there is no chapter 3, 4 or 5 -- so membership is
    # a predecessor search, not a lookup into a dense table.
    assert documents.title_of("99", ordered)["citation"] == "TITLE II"
    assert documents.title_of("0", ordered) is None


def test_a_section_carries_its_title():
    found = documents.statutes([chapter_index("I", "CONSTRUCTION", "1"), statute("1.01")])
    assert found[0]["title"] == "TITLE I"
    assert found[0]["title_name"] == "CONSTRUCTION"


def test_the_title_tier_groups_chapters_in_canonical_order():
    decoded = [
        chapter_index("I", "CONSTRUCTION", "1"),
        chapter_index("II", "STATE", "6"),
        statute("6.01"),
        statute("2.01"),
        statute("1.01"),
    ]
    (first, second) = documents.title_hierarchy(documents.statutes(decoded))
    assert first["citation"] == "TITLE I"
    assert first["chapters"] == ["1", "2"]
    assert second["chapters"] == ["6"]


def test_constitution_identity_comes_from_the_anchor():
    section = (
        '<html><head><title>Florida Constitution</title></head><body>'
        '<div class="Section"><span class="SectionNumber"><a name="A1S03">SECTION 3.</a></span>'
        "<CATCHLINE>Religious freedom.</CATCHLINE></div></body></html>"
    )
    (record,) = documents.constitution([section])
    assert record["article"] == 1 and record["section"] == 3
    assert record["citation"] == "Art. 1, s. 3, Fla. Const."
    assert record["path"] == "constitution/article-01/section-03.html"


def test_article_index_documents_are_skipped():
    article = '<html><body><div class="Article"><a name="A1S03">x</a></div></body></html>'
    assert documents.constitution([article]) == []


def test_session_laws_sort_numerically_and_keep_joint_resolutions_last():
    def law(n):
        return f"<html><head><title>CHAPTER 2025-{n}</title></head><body>x</body></html>"

    jr = (
        "<html><head><title>House Joint Resolution No. 5019</title></head>"
        "<body>A joint resolution</body></html>"
    )
    found = documents.session_laws([law(10), jr, law(2)])
    assert [d["chapter"] for d in found] == ["2025-2", "2025-10", None]
    assert found[-1]["path"].startswith("laws/joint-resolutions/")
