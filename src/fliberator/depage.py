"""Phase 2d: undo the .nxt paged-storage layer before decoding anything.

Everything before this treated `fs2025.nxt` as one flat byte stream and read
it linearly. It isn't. The file is a **paged store**: its size is exactly
58,626 * 4096, and every page after the header page starts with its own
typed page header. Reading straight through those headers is what produced
every "corruption" symptom this project has been chasing -- destroyed
closing tags, titles interrupted by a little-endian page number, the
"double failure" sections, the mid-body content loss measured in Phase 4.
None of it was damage in the data; it was storage metadata being decoded as
if it were content.

Page layout (offsets are within the page; all integers little-endian):

    0   uint16  page type -- 5 is the document-content type. Everything
                else is search-index/B-tree machinery and carries no
                document text (verified by sampling types 2,3,7,9,10,16).
    16  uint16  slot count
    18  uint16  end-of-slot-array offset
    20  uint16[slot count]
                slot directory, one entry per fragment on the page, in
                *descending* offset order. Low 13 bits are the fragment's
                page offset; high 3 bits are flags. The final slot is a
                sentinel: its offset field equals the field at 18, and its
                flag bits say which page-level pointers follow --
                bit0 (1) = a back-pointer,  bit1 (2) = a forward pointer.
                Bit2 (4) is always set on the sentinel.
    ..  6 bytes each, one per flag bit set, back-pointer first:
                uint32 page, uint16 index

A page holds one or more **fragments**, packed contiguously from the end of
that header to the end of the page. A fragment is a slice of one document,
and a document that doesn't fit on a page is stored as a *chain* of
fragments scattered across the file -- not necessarily in increasing page
order, and interleaved with fragments of unrelated documents. Fragment 0 of
p761, for instance, is the start of F.S. 15.182 and continues on p767,
while fragments 1-3 of that same page are the tails of three other
documents that started on pages 764, 763 and 760.

Chain links are doubly-encoded and always point *backwards* by
(page, index), where index is the fragment's position counted from the
**end** of its page's fragment list (so index 0 is the last fragment):

  - A fragment after the first on its page carries its 6-byte back-pointer
    inline, as its own first 6 bytes -- these are the bytes that earlier
    phases saw as garbage interrupting a <title> and correctly guessed
    encoded a page number (docs/nxt-format.md, "The 'garbage' is a real
    field, not noise"). They are not content and must be stripped.
  - Fragment 0 has no room for an inline prefix, so its back-pointer is the
    page-level bit0 pointer instead.
  - A fragment that begins with the LPDD record marker starts a fresh
    document and has no back-pointer at all.

Following those links reassembles every document exactly. Across the whole
file that yields 37,435 successor edges with **zero** conflicts, 26,306
chains, and 26,306 reassembled documents of which 100% carry an intact
`<title>...</title>` and 100% end in `</html>` -- against 26,196 intact
titles when the same file is read linearly.

Every constant and field offset above was derived from the 2025 edition, so
the layout is *checked*, not assumed: `check_container` validates the file
as a whole and `parse_pages` validates each content page's slot directory.
A future year's build that changed the page size, the directory shape or the
offset mask would otherwise produce plausible-looking but wrong documents
rather than failing; instead it raises `FormatError`.
"""

import pathlib
import re
import struct

PAGE_SIZE = 4096
CONTENT_PAGE_TYPE = 5
LPDD = b"\x11\x06\x0b\x04\x00LPDD"

# Every .nxt file opens with the same ASCII banner, null-padded to 0xE0.
SIGNATURE = b"Copyright (c) 19"
INFOBASE = b"Infobase"
FILE_HEADER_SIZE = 0xE0

# Documents are delimited by this record marker rather than by page or
# fragment boundaries -- a single fragment can hold the tail of one
# document, several whole short ones, and the head of the next.
LPDD_RE = re.compile(re.escape(LPDD))


class FormatError(ValueError):
    """The file does not match the paged-store layout described above.

    Every constant here (page size, page type, the header field offsets,
    the 13-bit offset mask) was derived from the 2025 edition. A future
    year's build could change any of them -- and the failure mode without
    checking is silent: nonsense read as a valid slot directory yields
    plausible-looking but wrong documents. These invariants all hold across
    all 13 files of the 2025 distribution, so violating one means the
    assumption, not the data, is what broke. Fail loudly instead.
    """


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise FormatError(message)


def check_container(data: bytes) -> None:
    """Validate the whole-file assumptions before reading any page."""
    _require(
        data[: len(SIGNATURE)] == SIGNATURE and INFOBASE in data[:FILE_HEADER_SIZE],
        "not an Infobase container: the Rocket copyright banner is missing "
        "from the first page header",
    )
    _require(
        len(data) % PAGE_SIZE == 0,
        f"file is {len(data):,} bytes, not a whole number of {PAGE_SIZE}-byte "
        f"pages ({len(data) % PAGE_SIZE} bytes left over) -- the page size may "
        "have changed",
    )
    _require(
        len(data) >= 2 * PAGE_SIZE,
        f"file is {len(data):,} bytes: too small to hold a header page and any content",
    )


def parse_pages(data: bytes) -> tuple[dict, dict]:
    """Return (fragments, back_pointers).

    fragments: page -> [(start, end), ...] in ascending page-offset order.
    back_pointers: (page, 0) -> (source_page, source_index), for the pages
    whose fragment 0 continues an earlier fragment.
    """
    check_container(data)
    fragments: dict[int, list[tuple[int, int]]] = {}
    back_pointers: dict[tuple[int, int], tuple[int, int]] = {}

    for page in range(1, len(data) // PAGE_SIZE):
        base = page * PAGE_SIZE
        if struct.unpack_from("<H", data, base)[0] != CONTENT_PAGE_TYPE:
            continue

        n_slots = struct.unpack_from("<H", data, base + 16)[0]
        slot_end = struct.unpack_from("<H", data, base + 18)[0]
        _require(n_slots >= 1, f"page {page}: content page with an empty slot directory")
        _require(
            20 + 2 * n_slots <= slot_end <= PAGE_SIZE,
            f"page {page}: {n_slots} slots do not fit before the end-of-array "
            f"offset {slot_end}",
        )
        slots = [struct.unpack_from("<H", data, base + 20 + 2 * i)[0] for i in range(n_slots)]

        # The last slot is a sentinel rather than a fragment: its offset
        # field repeats the field at 18 and its flags say which page-level
        # pointers follow. If that identity fails, the directory is not the
        # shape this code assumes and every offset below is meaningless.
        flags = slots[-1] >> 13
        _require(
            slots[-1] & 0x1FFF == slot_end and flags & 4,
            f"page {page}: final slot {slots[-1]:#06x} is not the expected "
            f"sentinel for end-of-array offset {slot_end}",
        )
        has_back, has_forward = flags & 1, (flags >> 1) & 1
        if has_back:
            back_pointers[(page, 0)] = struct.unpack_from("<IH", data, base + slot_end)

        # Only the back-pointer is needed to rebuild chains: every link is
        # recorded from the far end, so the forward pointer here is
        # redundant and is deliberately left unread.
        header_len = slot_end + 6 * (has_back + has_forward)
        _require(
            header_len <= PAGE_SIZE,
            f"page {page}: header of {header_len} bytes overruns the page",
        )
        offsets = [s & 0x1FFF for s in slots[:-1]]
        _require(
            all(header_len < offset <= PAGE_SIZE for offset in offsets),
            f"page {page}: fragment offset outside the page body "
            f"({header_len}, {PAGE_SIZE}]: {offsets}",
        )
        _require(
            all(a > b for a, b in zip(offsets, offsets[1:], strict=False)),
            f"page {page}: slot directory is not in strictly descending "
            f"offset order: {offsets}",
        )

        starts = [header_len] + offsets[::-1]
        fragments[page] = [
            (starts[i], starts[i + 1] if i + 1 < len(starts) else PAGE_SIZE)
            for i in range(len(starts))
        ]

    _require(bool(fragments), f"no type-{CONTENT_PAGE_TYPE} content pages found")
    return fragments, back_pointers


def build_chains(data: bytes, fragments: dict, back_pointers: dict) -> tuple[dict, set]:
    """Invert the back-pointers into a successor map.

    Returns (successors, prefixed) where successors maps a fragment to the
    fragment that continues it, and `prefixed` is the set of fragments whose
    first 6 bytes are an inline back-pointer and must be skipped as content.
    """
    successors: dict[tuple[int, int], tuple[int, int]] = {}
    prefixed: set[tuple[int, int]] = set()

    def link(source: tuple[int, int], target: tuple[int, int]) -> None:
        source_page, source_index = source
        # source_index counts from the end of the source page's fragments.
        key = (source_page, len(fragments[source_page]) - 1 - source_index)
        if key in successors:
            raise ValueError(f"conflicting successor for {key}: {successors[key]} and {target}")
        successors[key] = target

    for page, page_fragments in fragments.items():
        for index in range(1, len(page_fragments)):
            start, end = page_fragments[index]
            _require(
                end - start >= 6,
                f"page {page} fragment {index}: {end - start} bytes, too short "
                "to hold an inline back-pointer",
            )
            source_page, source_index = struct.unpack_from("<IH", data, page * PAGE_SIZE + start)
            if source_page not in fragments or source_index >= len(fragments[source_page]):
                continue  # starts a fresh document; no inline back-pointer
            prefixed.add((page, index))
            link((source_page, source_index), (page, index))

    for target, source in back_pointers.items():
        link(source, target)

    return successors, prefixed


def reconstruct(data: bytes) -> list[bytes]:
    """Reassemble every document in the file, in chain-head page order."""
    fragments, back_pointers = parse_pages(data)
    successors, prefixed = build_chains(data, fragments, back_pointers)

    linked = set(successors.values())
    heads = sorted(
        (page, index)
        for page, page_fragments in fragments.items()
        for index in range(len(page_fragments))
        if (page, index) not in linked
    )

    records: list[bytes] = []
    for head in heads:
        pieces = []
        seen: set[tuple[int, int]] = set()
        cursor = head
        while cursor is not None:
            # build_chains rejects two fragments claiming the same
            # successor, which rules out most malformed links -- but not a
            # closed loop, which would otherwise spin here forever.
            _require(cursor not in seen, f"fragment chain from {head} loops back to {cursor}")
            seen.add(cursor)
            page, index = cursor
            start, end = fragments[page][index]
            skip = 6 if cursor in prefixed else 0
            pieces.append(data[page * PAGE_SIZE + start + skip : page * PAGE_SIZE + end])
            cursor = successors.get(cursor)
        chain = b"".join(pieces)

        # A chain can carry more than one whole document; split on the
        # record marker so each returned record is exactly one document.
        marks = [m.start() for m in LPDD_RE.finditer(chain)]
        for i, mark in enumerate(marks):
            records.append(chain[mark : marks[i + 1] if i + 1 < len(marks) else len(chain)])

    return records


def load_records(path: pathlib.Path) -> list[bytes]:
    """Reassemble every document in a .nxt file."""
    path = pathlib.Path(path)
    try:
        records = reconstruct(path.read_bytes())
    except FormatError as error:
        raise FormatError(f"{path}: {error}") from None
    _require(bool(records), f"{path}: no documents found")
    return records
