"""Storage-layer geometry checks.

Every constant in depage.py was derived from the 2025 edition. Without
checking, a future year's build with a different layout would not crash --
it would read nonsense as a valid slot directory and emit plausible-looking
but wrong documents. These tests pin the failure to a loud FormatError.
"""

import pathlib
import struct

import pytest

from fliberator import depage

BANNER = (
    b"Copyright (c) 1991-2025, Rocket Software, Inc.  "
    b"All Rights Reserved. Infobase\r\n"
)
PAYLOAD = depage.LPDD + b"a document"


def content_page(payload: bytes = PAYLOAD, sentinel: int | None = None) -> bytes:
    """One content page holding a single fragment, laid out per the format."""
    slot_end = 22
    page = bytearray(depage.PAGE_SIZE)
    struct.pack_into("<H", page, 0, depage.CONTENT_PAGE_TYPE)
    struct.pack_into("<H", page, 16, 1)  # slot count
    struct.pack_into("<H", page, 18, slot_end)
    # The one slot is the sentinel: offset field repeats slot_end, bit2 set.
    struct.pack_into("<H", page, 20, slot_end | (4 << 13) if sentinel is None else sentinel)
    page[slot_end : slot_end + len(payload)] = payload
    return bytes(page)


def container(*pages: bytes) -> bytes:
    header = bytearray(depage.PAGE_SIZE)
    header[: len(BANNER)] = BANNER
    return bytes(header) + b"".join(pages)


def test_a_well_formed_container_round_trips():
    (record,) = depage.reconstruct(container(content_page()))
    assert record.startswith(depage.LPDD)
    assert b"a document" in record


def test_a_file_that_is_not_whole_pages_is_rejected():
    # Truncation used to be silent: len(data) // PAGE_SIZE just dropped the
    # partial tail page and its documents with it.
    with pytest.raises(depage.FormatError, match="not a whole number"):
        depage.reconstruct(container(content_page())[:-100])


def test_a_file_without_the_infobase_banner_is_rejected():
    with pytest.raises(depage.FormatError, match="not an Infobase container"):
        depage.reconstruct(b"\x00" * (2 * depage.PAGE_SIZE))


def test_a_slot_directory_that_is_not_the_expected_shape_is_rejected():
    # A sentinel whose offset field disagrees with the end-of-array field
    # means the directory is not the shape this code assumes -- so every
    # fragment offset read from it is meaningless.
    with pytest.raises(depage.FormatError, match="sentinel"):
        depage.reconstruct(container(content_page(sentinel=99 | (4 << 13))))


def test_a_file_with_no_content_pages_is_rejected():
    index_page = bytearray(depage.PAGE_SIZE)
    struct.pack_into("<H", index_page, 0, 9)  # a search-index page type
    with pytest.raises(depage.FormatError, match="no type-5 content pages"):
        depage.reconstruct(container(bytes(index_page)))


def test_the_real_reference_file_still_satisfies_every_check():
    # The invariants above were chosen because they hold across all 13
    # files of the 2025 distribution; this keeps them honest against one.
    reference = pathlib.Path("FLLawDL2025/Library/flcnst2025.nxt")
    if not reference.is_file():
        pytest.skip("reference copy not present")
    assert len(depage.load_records(reference)) > 200
