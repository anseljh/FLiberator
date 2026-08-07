"""Opcode rules for the content layer.

Each case encodes a rule that was derived from the corpus and, in two
instances, a defect that shipped before the rule was right -- see
docs/nxt-format.md Phases 2e, 4c and 8a.
"""

from fliberator.decode import decode, doubled_char_len, is_field_marker


def run(data: bytes) -> str:
    return decode(data, 0, len(data))[0]


def test_literal_token_one_byte_length():
    assert run(b"\x13\x37\x05hello") == "hello"


def test_literal_token_two_byte_length():
    payload = b"x" * 300
    assert run(b"\x13\x37" + bytes([0x80 | (300 >> 8), 300 & 0xFF]) + payload) == "x" * 300


def test_record_marker_is_not_emitted_as_text():
    # "LPDD" is printable, so without an explicit rule the run-sniffer
    # emitted it at the head of all 26,306 documents.
    assert run(b"\x11\x06\x0b\x04\x00LPDD\x00\x00\x00\x00\x00\x13\x37\x02hi") == "hi"


def test_doubled_character_keeps_only_the_entity():
    # 0x15 01 01 01 <char> then a 0x13 0x39 token carrying the same
    # character as an entity. Emitting both rendered it twice.
    data = b"\x15\x01\x01\x01\xe2\x80\x83\x13\x39\x08&#x2003;"
    assert run(data) == "&#x2003;"


def test_doubled_character_accepts_single_byte_literal():
    # The rule used to require a multi-byte literal, which let 62 markers
    # through and shipped "AT&&T": a literal "&" paired with "&amp;".
    data = b"\x15\x01\x01\x01&\x13\x39\x05&amp;"
    assert doubled_char_len(data, 0, len(data)) > 0
    assert run(data) == "&amp;"


def test_doubled_character_rejects_mismatched_pair():
    # The pair must encode the *same* character; a mismatch is ordinary text.
    data = b"\x15\x01\x01\x01&\x13\x39\x08&#x2003;"
    assert doubled_char_len(data, 0, len(data)) == 0


def test_field_marker_consumes_its_printable_id():
    # Ids 0x4d/0x4e are "M"/"N". Skipping only the first three bytes let
    # the id fall through to the text sniffer -- 39,200 stray characters
    # across 10 files, invisible in fs2025.nxt because its ids are not
    # printable.
    assert is_field_marker(b"\x15\x04\x01\x4d", 0, 4)
    assert run(b"\x15\x04\x01\x4d\x13\x37\x07<TITLE>") == "<TITLE>"
    assert run(b"\x15\x04\x01\x05\x13\x37\x02ok") == "ok"


def test_format_toggle_is_skipped():
    assert run(b"\x10\x01\x03\x82\x2e\x01\x13\x37\x02ok") == "ok"


def test_unknown_control_byte_degrades_rather_than_halting():
    out, stats = decode(b"\x01\x13\x37\x02ok", 0, 5)
    assert out == "ok"
    assert stats["unknown_bytes_skipped"] == 1
