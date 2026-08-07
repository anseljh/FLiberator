"""Rewrite the source's footnote markup as semantic HTML5.

The `.nxt` source already carries everything needed, which makes this a
re-labelling rather than a restructuring. Measured across all 24,866
statute sections:

  * 684 sections have footnotes.
  * Every inline reference resolves to a note body -- 0 dangling.
  * Note bodies already sit after the last inline reference, in 684 of
    684 sections, so nothing has to be moved.

What the source looks like:

    ...moved to<sup><a href="#1">[1]</a></sup> the...
    <div class="Note"><sup><a name="1">[1]</a></sup>
      <span class="NoteTitle">Note.</span>
      <span class="EmDash">&#x2014;</span>
      <span class="Text Intro Justify"><NOTES>Repealed by...</NOTES></span>
    </div>

What this produces:

    ...moved to<sup><a id="fnref-1-1" href="#fn-1"
      role="doc-noteref">1</a></sup> the...
    <section role="doc-endnotes">
      <h2>Notes</h2>
      <ol>
        <li id="fn-1" role="doc-endnote">Repealed by...
          <a href="#fnref-1-1" role="doc-backlink">&#8617;</a></li>
      </ol>
    </section>

Two decisions are baked in here:

  * The marker renders as a plain `1`, not the source's `[1]`. `<sup>`
    plus `role="doc-noteref"` already carries that meaning, and it is how
    leg.state.fl.us renders it. The bracketed original is preserved in
    the JSON sidecar rather than thrown away.
  * **One backlink per referrer.** 98 notes corpus-wide are cited from
    more than one place -- up to 15 times -- so a single backlink would
    silently pick one call site out of many. Each reference therefore
    gets a unique `fnref-<note>-<n>` id. Two notes have no referrer at
    all and get no backlink.
"""

import re

# The inline reference. Two spellings occur, and both mean "note N applies
# here": the usual `<sup><a href="#1">[1]</a></sup>`, and -- inside note
# bodies -- `<sup><a name="3">[3]</a></sup>`, where the source uses an
# anchor rather than a link. The `name=` spelling is why two notes appeared
# to have no referrer at all: their only call site was one of these.
# Matching only `href=` left those markers as a literal "[3]" in the output
# while every other marker rendered as "3".
REFERENCE_RE = re.compile(
    r'<sup>\s*<a\s+(?:href="#|name=")(\d+)"\s*>\s*\[?(\d+)\]?\s*</a>\s*</sup>',
    re.IGNORECASE,
)
# The note body. Its <sup><a name="..."> opener is matched separately so the
# surrounding <div class="Note"> can be replaced wholesale.
NOTE_DIV_RE = re.compile(
    r'<div class="Note">\s*<sup>\s*<a\s+name="(\d+)"\s*>\s*\[?\d+\]?\s*</a>\s*</sup>'
    r"(?P<body>.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)
# Folio's own semantic wrapper inside a note body; the text is what matters.
NOTES_TAG_RE = re.compile(r"</?NOTES>", re.IGNORECASE)
# "Note." label and the em dash that follows it -- redundant once the note
# is an <li> inside a labelled doc-endnotes section.
NOTE_LABEL_RE = re.compile(
    r'<span class="NoteTitle">.*?</span>\s*<span class="EmDash">.*?</span>',
    re.IGNORECASE | re.DOTALL,
)

BACKLINK = "&#8617;"


def _note_body(fragment: str) -> str:
    fragment = NOTE_LABEL_RE.sub("", fragment)
    fragment = NOTES_TAG_RE.sub("", fragment)
    return fragment.strip()


def transform(html: str) -> tuple[str, list[dict]]:
    """Rewrite footnotes in one decoded document.

    Returns the rewritten HTML and a per-note record for the JSON sidecar.
    A document with no footnotes is returned unchanged, with an empty list.
    """
    notes: dict[str, str] = {}
    for match in NOTE_DIV_RE.finditer(html):
        notes[match.group(1)] = _note_body(match.group("body"))
    if not notes and not REFERENCE_RE.search(html):
        return html, []

    # Lift the note bodies out first, so their own opening `<a name="N">`
    # is consumed and only genuine references remain to be rewritten. A
    # note body can itself contain a reference to another note, so the
    # bodies get the same rewrite as the document text.
    html = NOTE_DIV_RE.sub("", html)

    # Number each referrer so every one gets its own backlink target.
    seen: dict[str, int] = {}
    referrers: dict[str, list[str]] = {number: [] for number in notes}

    def replace_reference(match: re.Match) -> str:
        number = match.group(1)
        seen[number] = seen.get(number, 0) + 1
        anchor = f"fnref-{number}-{seen[number]}"
        referrers.setdefault(number, []).append(anchor)
        return (
            f'<sup><a id="{anchor}" href="#fn-{number}" '
            f'role="doc-noteref">{match.group(2)}</a></sup>'
        )

    html = REFERENCE_RE.sub(replace_reference, html)
    notes = {number: REFERENCE_RE.sub(replace_reference, body) for number, body in notes.items()}

    ordered = sorted(notes, key=int)
    items = []
    records = []
    for number in ordered:
        links = "".join(
            f' <a href="#{anchor}" role="doc-backlink">{BACKLINK}</a>'
            for anchor in referrers.get(number, [])
        )
        items.append(
            f'<li id="fn-{number}" role="doc-endnote">{notes[number]}{links}</li>'
        )
        records.append(
            {
                "number": int(number),
                "marker": f"[{number}]",  # the source's own notation, kept
                "referrers": len(referrers.get(number, [])),
            }
        )

    endnotes = (
        '<section role="doc-endnotes">\n<h2>Notes</h2>\n<ol>\n'
        + "\n".join(items)
        + "\n</ol>\n</section>"
    )

    closing = re.search(r"</body>", html, re.IGNORECASE)
    if closing:
        html = html[: closing.start()] + endnotes + "\n" + html[closing.start() :]
    else:
        html += "\n" + endnotes
    return html, records
