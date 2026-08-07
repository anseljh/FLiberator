"""Footnote rewriting into semantic HTML5 (plans/re-plan.md Phase 9)."""

import re

from fliberator.footnotes import transform

REFERENCE = '<sup><a href="#1">[1]</a></sup>'
NOTE = (
    '<div class="Note"><sup><a name="1">[1]</a></sup>'
    '<span class="NoteTitle">Note.</span><span class="EmDash">&#x2014;</span>'
    '<span class="Text Intro Justify"><NOTES>Repealed by s. 20, ch. 97-180.</NOTES></span>'
    "</div>"
)


def document(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def test_document_without_footnotes_is_untouched():
    html = document("<p>Nothing to see.</p>")
    out, notes = transform(html)
    assert out == html
    assert notes == []


def test_reference_becomes_a_noteref():
    out, notes = transform(document(f"text{REFERENCE}{NOTE}"))
    assert '<sup><a id="fnref-1-1" href="#fn-1" role="doc-noteref">1</a></sup>' in out
    assert len(notes) == 1
    assert notes[0]["referrers"] == 1


def test_marker_renders_without_the_source_brackets():
    out, _ = transform(document(f"text{REFERENCE}{NOTE}"))
    assert ">1</a>" in out
    assert "[1]" not in out


def test_source_marker_is_preserved_in_metadata():
    _, notes = transform(document(f"text{REFERENCE}{NOTE}"))
    assert notes[0]["marker"] == "[1]"


def test_note_body_moves_into_an_endnotes_section():
    out, _ = transform(document(f"text{REFERENCE}{NOTE}"))
    assert '<section role="doc-endnotes">' in out
    assert '<li id="fn-1" role="doc-endnote">' in out
    assert "Repealed by s. 20, ch. 97-180." in out
    # the original presentational wrapper and label are gone
    assert '<div class="Note">' not in out
    assert "NoteTitle" not in out


def test_endnotes_sit_before_the_closing_body_tag():
    out, _ = transform(document(f"text{REFERENCE}{NOTE}"))
    assert out.index('<section role="doc-endnotes">') < out.index("</body>")


def test_every_referrer_gets_its_own_backlink():
    # 98 notes corpus-wide are cited more than once, up to 15 times.
    out, notes = transform(document(f"a{REFERENCE}b{REFERENCE}c{REFERENCE}{NOTE}"))
    assert notes[0]["referrers"] == 3
    assert [m for m in re.findall(r'id="(fnref-1-\d)"', out)] == [
        "fnref-1-1", "fnref-1-2", "fnref-1-3",
    ]
    assert out.count('role="doc-backlink"') == 3
    for n in (1, 2, 3):
        assert f'href="#fnref-1-{n}"' in out


def test_anchor_spelling_also_counts_as_a_reference():
    # Some call sites use `<a name="N">` rather than `href="#N"`; matching
    # only href left those markers as a literal "[3]" and made their notes
    # look unreferenced.
    inline = '<sup><a name="1">[1]</a></sup>'
    out, notes = transform(document(f"text{inline}{NOTE}"))
    assert notes[0]["referrers"] == 1
    assert ">1</a>" in out
    assert "[1]" not in out


def test_notes_are_numbered_in_order():
    ref2 = '<sup><a href="#2">[2]</a></sup>'
    note2 = NOTE.replace('"1"', '"2"').replace("[1]", "[2]").replace("Repealed", "Second")
    out, notes = transform(document(f"a{ref2}b{REFERENCE}{NOTE}{note2}"))
    assert [n["number"] for n in notes] == [1, 2]
    assert out.index('id="fn-1"') < out.index('id="fn-2"')
