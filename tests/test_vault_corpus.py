"""The three-destination contract, against real .md files on disk.

`tests/fixtures.py` holds markdown I invented, which only contains the mess I
thought to think of. This suite runs the same guarantees over
`examples/vault/`, where the notes are files rather than Python string
literals -- so it also exercises BOMs, CRLF, non-ASCII filenames, a missing
trailing newline, and folder structure.

The bridge itself is an example and is deliberately not imported here. What is
under test is the renderer.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from glanceable import HALO, Font, find_system_font
from glanceable.markdown import CODE, layout_markdown, parse_markdown

VAULT = pathlib.Path(__file__).resolve().parents[1] / "examples" / "vault"
NOTES = sorted(VAULT.rglob("*.md"))
FONT = find_system_font()
F13 = Font(FONT, 13)


def read(path: pathlib.Path) -> str:
    """Same normalisation the bridge does. Real vaults contain both."""
    return path.read_bytes().decode("utf-8-sig", errors="replace").replace(
        "\r\n", "\n"
    ).replace("\r", "\n")


def squash(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def pages(source, font=F13, limit=40):
    out = []
    for p in range(limit):
        lay = layout_markdown(source, HALO, font, page=p)
        out.append(lay)
        if not lay.has_more:
            return out
    raise AssertionError(f"pagination did not terminate within {limit} pages")


def test_the_vault_actually_has_notes():
    """A corpus test that silently tests nothing is worse than no test. This is
    exactly how the composite fixture rotted once already."""
    assert len(NOTES) >= 5, f"expected a populated vault, found {NOTES}"
    assert any("日本語" in p.name for p in NOTES), "non-ASCII filename missing"


@pytest.mark.parametrize("note", NOTES, ids=lambda p: p.stem)
def test_nothing_is_dropped_without_appearing_in_metadata(note):
    """Every word of every real note reaches the glass, leftover, or metadata."""
    src = read(note)
    ps = pages(src)
    meta = ps[0].metadata
    accounted = squash(
        "".join(p.text() for p in ps)
        + meta.frontmatter_raw
        + "".join(d.detail for d in meta.dropped)
        + "".join(meta.footnotes.values())
        + "".join(l.href for l in meta.links)
        + "".join(w.target for w in meta.wikilinks)
        + "".join(meta.reformatted)
    )
    for word in re.findall(r"\w+", src, flags=re.UNICODE):
        if len(word) < 4 or word.isdigit():
            continue
        assert squash(word) in accounted, (
            f"{note.name}: {word!r} is in the source but neither rendered "
            f"nor named in metadata"
        )


@pytest.mark.parametrize("note", NOTES, ids=lambda p: p.stem)
def test_no_line_leaves_the_circle(note):
    src = read(note)
    for size in (11, 13, 16):
        font = Font(FONT, size)
        for lay in pages(src, font=font):
            for line in lay.lines:
                y0 = line.run.baseline - line.font.ascent
                y1 = line.run.baseline + line.font.descent
                left = HALO.line_left(y0, y1)
                assert line.run.x >= left - 1, (note.name, size, line.run.text)
                assert (
                    line.run.x + line.run.width
                    <= left + HALO.line_width(y0, y1) + 1
                ), (note.name, size, line.run.text)


@pytest.mark.parametrize("note", NOTES, ids=lambda p: p.stem)
def test_pagination_terminates_and_is_pure(note):
    src = read(note)
    ps = pages(src)
    assert ps and not ps[-1].has_more
    assert all(p.has_more for p in ps[:-1])
    for p in range(len(ps)):
        assert layout_markdown(src, HALO, F13, page=p).text() == ps[p].text()


@pytest.mark.parametrize("note", NOTES, ids=lambda p: p.stem)
def test_leftover_source_resumes_the_document(note):
    """A caller can hand `leftover_source` back in and get the next page,
    without owning any parse state."""
    src = read(note)
    lay = layout_markdown(src, HALO, F13, page=0)
    if not lay.has_more:
        pytest.skip(f"{note.name} fits on one page")
    assert (
        layout_markdown(lay.leftover_source, HALO, F13, page=0).text()
        == layout_markdown(src, HALO, F13, page=1).text()
    )


@pytest.mark.parametrize("note", NOTES, ids=lambda p: p.stem)
def test_code_blocks_keep_one_left_edge(note):
    for lay in pages(read(note)):
        by_block = {}
        for line in lay.lines:
            if line.kind == CODE:
                by_block.setdefault(line.block, set()).add(line.run.x)
        for block, xs in by_block.items():
            assert len(xs) == 1, f"{note.name}: code block {block} has edges {xs}"


def test_frontmatter_never_reaches_the_glass():
    """The silent failure. Every note here has frontmatter with a `title:`; not
    one of those keys may render."""
    seen = 0
    for note in NOTES:
        src = read(note)
        doc = parse_markdown(src)
        if not doc.metadata.frontmatter_raw:
            continue
        seen += 1
        shown = " ".join(p.text() for p in pages(src))
        for key in doc.metadata.frontmatter:
            assert f"{key}:" not in shown, f"{note.name}: frontmatter key {key!r} rendered"
    assert seen >= 4, "corpus lost its frontmatter coverage"


def test_wikilink_targets_resolve_against_the_vault():
    """What the metadata is *for*: a caller resolves targets, the renderer does
    not. One target is deliberately unresolved, to prove a dangling link is
    reported rather than swallowed."""
    stems = {p.stem for p in NOTES}
    resolved, dangling = set(), set()
    for note in NOTES:
        for w in parse_markdown(read(note)).metadata.wikilinks:
            base = w.target.split("#")[0]
            (resolved if base in stems else dangling).add(base)
    assert "Chord Solver" in resolved and "Halo SDK" in resolved
    assert "Saccade Budget" in dangling
