"""Phase 2 decoder for the .nxt tokenized-markup content layer.

Opcode rules (see docs/nxt-format.md for how these were derived):
  0x13 <subtype> <len> <len bytes> -- literal text, length-prefixed. <subtype>
                                      byte varies (0x37 for markup tags, 0x39
                                      seen for HTML entities like &#x2003; --
                                      framing is identical either way, so it's
                                      treated as opaque/unclassified here).
                                      <len> is 1 byte if its high bit is clear;
                                      if set, it's a 2-byte big-endian length:
                                      ((b1 & 0x7F) << 8) | b2 (confirmed against
                                      a 239-byte <!DOCTYPE...><meta.../> run).
  <printable/UTF-8 run>            -- literal text, sniffed at every position
                                      (not only after a particular opcode --
                                      confirmed some text, e.g. "Definitions."
                                      inside <CATCHLINE></CATCHLINE>, appears
                                      completely unprefixed). 0x08 turned out
                                      not to be a dedicated "text" opcode; it's
                                      just another byte that happens to often
                                      precede a text run, so it's treated the
                                      same as any other unrecognized byte.
  0x10 <0|1> 0x03 0x82 <id> 0x01  -- paired character-formatting toggle
                                      (0=open/1=close), redundant with the
                                      literal <B>/<I>/<TITLE> tags it wraps.
                                      <id> is a small per-style integer that
                                      sometimes lands in printable ASCII range
                                      (':', '>', '@', '0'...) -- without this
                                      explicit rule it gets misread as stray
                                      text by the printable-run sniffer.
                                      Confirmed via 1,936 instances split
                                      evenly 970 open / 966 close.
  0x15 0x01 0x01 0x01 [0x08] <ch> -- "the character that follows is stored
                                      twice": one literal UTF-8 copy (here),
                                      then a 0x13 0x39 token carrying the *same*
                                      character as an HTML entity. Emitting both
                                      renders it twice, so the literal copy is
                                      dropped and the entity token is kept -- the
                                      entity is the markup copy (0x39 is a real
                                      token subtype), the literal is presumably
                                      the plain-text copy the search index reads.
                                      Confirmed across 327,048 pairs in 94.8% of
                                      documents, dominated by EM SPACE (254,468),
                                      EM DASH (63,428) and NBSP (8,894); only 62
                                      occurrences corpus-wide don't fit the shape,
                                      and those fall through to the old behaviour.
  0x15 <0x03|0x04> 0x01 <id>      -- field marker: a 4-byte unit whose <id> says
                                      which Folio field is being opened or
                                      closed. Redundant with the literal markup
                                      that follows either way, so the whole unit
                                      is skipped, same as the 0x10 toggle.
                                      Confirmed ids, all perfectly balanced in
                                      open/close pairs:
                                        0x05/0x06  History-note field -- 0x05
                                                   introduces a hyperlink (always
                                                   followed by a 0x13 0x37 token
                                                   opening `<a href="#!--`), 0x06
                                                   a non-link field. 549,848 each
                                                   corpus-wide, 184,764 in
                                                   fs2025.nxt alone.
                                        0x4d/0x4e  the document Title field --
                                                   0x4d sits immediately before
                                                   <TITLE>, 0x4e immediately
                                                   after </TITLE>. 19,600 each,
                                                   in 10 of the 13 files but
                                                   *not* in fs2025.nxt.
                                        0x03 0x01  end-of-body marker, exactly
                                                   one per document, xrt2025.nxt
                                                   only (613).
                                      The <id> byte matters: 0x4d/0x4e are the
                                      printable ASCII "M"/"N", so before this
                                      rule was generalized beyond 0x05/0x06 the
                                      first three bytes were skipped one at a
                                      time and the id fell through to the
                                      printable-run sniffer, emitting a literal
                                      "M" before every <TITLE> and "N" after
                                      every </TITLE> -- 39,200 stray characters
                                      across 10 files. fs2025.nxt was immune only
                                      because both of its ids are non-printable.
  0x11 0x06 0x0b 0x04 0x00 "LPDD" -- start-of-document record marker, 14 bytes
    + 5 zero bytes                    including trailing padding. Skipped as a
                                      unit: "LPDD" is printable ASCII, so without
                                      this rule the sniffer emitted it as literal
                                      text at the head of all 26,306 documents.
  anything else < 0x20            -- unrecognized opcode; skipped one byte at a
                                      time (logged) as a deliberately dumb
                                      fallback, so decoding degrades instead of
                                      halting when the opcode table is incomplete

"""

import html
from collections import Counter


def is_text_byte(data: bytes, i: int) -> int:
    """Return the number of bytes a printable/UTF-8 run at i consumes (0 if none)."""
    b = data[i]
    if b in (0x09, 0x0A, 0x0D) or 0x20 <= b <= 0x7E:
        return 1
    # crude UTF-8 continuation check for multi-byte sequences (curly quotes, EM SPACE, etc.)
    if 0xC2 <= b <= 0xDF and i + 1 < len(data) and 0x80 <= data[i + 1] <= 0xBF:
        return 2
    if 0xE0 <= b <= 0xEF and i + 2 < len(data) and all(
        0x80 <= data[i + k] <= 0xBF for k in (1, 2)
    ):
        return 3
    return 0


LPDD_MARKER = b"\x11\x06\x0b\x04\x00LPDD\x00\x00\x00\x00\x00"
DOUBLED_CHAR_MARKER = b"\x15\x01\x01\x01"

# 0x15 <kind> 0x01 <id>. Kind 0x01 is the doubled-character marker, which
# carries a payload and is handled separately; these two are bare 4-byte
# field markers whose trailing id byte must be consumed as part of the unit.
FIELD_MARKER_KINDS = (0x03, 0x04)


def doubled_char_len(data: bytes, i: int, end: int) -> int:
    """If a doubled-character marker starts at i, return the number of bytes to
    drop (marker + optional 0x08 + the literal copy of the character), leaving
    the 0x13 0x39 entity token that follows to be emitted normally. Returns 0 if
    the bytes at i don't match the confirmed shape.

    The shape is confirmed by *checking the pair*: the literal copy and the
    entity token that follows must encode the same character. An earlier
    version approximated this with "the literal copy is multi-byte UTF-8",
    on the reasoning that a 1-byte run would be ordinary ASCII text. That
    proxy held for 327,048 of 327,110 markers and silently failed on the
    other 62, every one of them a literal `&` paired with `&amp;` -- so the
    decoder emitted both and shipped `AT&&T`, `Child && Dependent` and
    `Flagler && Volusia` across 25 documents. Comparing the two copies
    directly is both stricter (a mismatched pair no longer matches on the
    strength of byte width alone) and correct for single-byte characters.
    """
    if data[i : i + 4] != DOUBLED_CHAR_MARKER:
        return 0
    j = i + 4
    if j < end and data[j] == 0x08:
        j += 1
    n = is_text_byte(data, j)
    if n == 0:
        return 0
    literal = data[j : j + n].decode("utf-8", errors="replace")
    j += n
    if data[j : j + 2] != b"\x13\x39":
        return 0
    length_byte = data[j + 2]
    if length_byte & 0x80:
        length, header = ((length_byte & 0x7F) << 8) | data[j + 3], 4
    else:
        length, header = length_byte, 3
    entity = data[j + header : j + header + length].decode("utf-8", errors="replace")
    if html.unescape(entity) != literal:
        return 0
    return j - i


def is_field_marker(data: bytes, i: int, end: int) -> bool:
    """True if a bare 4-byte 0x15 field marker starts at i."""
    return (
        i + 4 <= end
        and data[i] == 0x15
        and data[i + 1] in FIELD_MARKER_KINDS
        and data[i + 2] == 0x01
    )


def decode(data: bytes, start: int, end: int) -> tuple[str, dict]:
    out = []
    i = start
    stats = {"tag_tokens": 0, "text_runs": 0, "unknown_bytes_skipped": 0}
    subtypes: Counter = Counter()
    while i < end:
        b = data[i]
        if b == 0x11 and data[i : i + len(LPDD_MARKER)] == LPDD_MARKER:
            stats["record_markers"] = stats.get("record_markers", 0) + 1
            i += len(LPDD_MARKER)
        elif b == 0x15 and (skip := doubled_char_len(data, i, end)):
            stats["doubled_chars_dropped"] = stats.get("doubled_chars_dropped", 0) + 1
            i += skip
        elif b == 0x15 and is_field_marker(data, i, end):
            stats["field_markers"] = stats.get("field_markers", 0) + 1
            i += 4
        elif b == 0x13 and i + 1 < end:
            subtype = data[i + 1]
            b1 = data[i + 2]
            if b1 & 0x80:
                length = ((b1 & 0x7F) << 8) | data[i + 3]
                header_len = 4
            else:
                length = b1
                header_len = 3
            text = data[i + header_len : i + header_len + length]
            out.append(text.decode("utf-8", errors="replace"))
            stats["tag_tokens"] += 1
            subtypes[subtype] += 1
            i += header_len + length
        elif (
            b == 0x10
            and i + 5 < end
            and data[i + 1] in (0x00, 0x01)
            and data[i + 2] == 0x03
            and data[i + 3] == 0x82
            and data[i + 5] == 0x01
        ):
            stats["format_toggles"] = stats.get("format_toggles", 0) + 1
            i += 6
        elif is_text_byte(data, i):
            j = i
            while j < end:
                n = is_text_byte(data, j)
                if n == 0:
                    break
                j += n
            out.append(data[i:j].decode("utf-8", errors="replace"))
            stats["text_runs"] += 1
            i = j
        else:
            stats["unknown_bytes_skipped"] += 1
            i += 1
    stats["tag_subtypes"] = dict(subtypes)
    return "".join(out), stats
