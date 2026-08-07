"""Document identification and canonical ordering."""

from fliberator import documents


def statute(citation: str, catchline: str = "Definitions.") -> str:
    return (
        f"<html><head><title>F.S. {citation}</title></head><body>"
        f'<div class="Section"><span class="SectionNumber">{citation}</span>'
        f"<CATCHLINE>{catchline}</CATCHLINE></div></body></html>"
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
