"""Tests for glanceable.markdown.

Organised by the contract each group defends, because that is what makes a
failure legible six months from now. The regression tests at the bottom each
name a specific defect found while building this; every one of them fails
against the commit before its fix.
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest

import fixtures
from glanceable import HALO, CircularDisplay, Font, PILSurface, find_system_font, ramp_palette
from glanceable.markdown import (
    CODE,
    HEADING,
    LIST,
    QUOTE,
    RULE,
    Block,
    MarkdownLayout,
    Policy,
    _resynth,
    has_glyph,
    layout_markdown,
    parse_markdown,
    render_markdown,
    usable_lines,
)

FONT = find_system_font()
F13 = Font(FONT, 13)


def pages(source, font=F13, display=HALO, limit=40, **kw):
    """Every page, in order. Guards against a non-terminating paginator."""
    out = []
    for p in range(limit):
        lay = layout_markdown(source, display, font, page=p, **kw)
        out.append(lay)
        if not lay.has_more:
            return out
    raise AssertionError(f"pagination did not terminate within {limit} pages")


def words(text):
    return re.findall(r"\w+", text, flags=re.UNICODE)


def squash(text):
    """Letters and digits only, lowercased.

    Conservation has to be checked on a squashed stream rather than a word set,
    because the renderer legitimately inserts breaks *inside* words -- a
    hyphenated long word, a continuation-marked code line, a CJK run with no
    spaces to break on. Removing the inserted punctuation and line structure
    leaves exactly the characters the author wrote.
    """
    return "".join(c for c in text.lower() if c.isalnum())


# --- parsing ----------------------------------------------------------------


def test_frontmatter_is_stripped_before_the_parser_sees_it():
    """THE silent one. CommonMark reads a leading `---` block as a thematic
    break plus a setext H2, so raw source renders frontmatter as a heading."""
    doc = parse_markdown(fixtures.FRONTMATTER)
    assert doc.metadata.frontmatter["title"] == "Chord solver"
    assert [b.kind for b in doc.blocks] == [HEADING, "paragraph"]
    assert doc.blocks[0].text == "Real heading"
    rendered = layout_markdown(fixtures.FRONTMATTER, HALO, F13).text()
    assert "title" not in rendered and "Chord solver" not in rendered


def test_unterminated_dashes_are_a_rule_not_frontmatter():
    """Treating an unclosed `---` as frontmatter would eat the entire note."""
    doc = parse_markdown(fixtures.FRONTMATTER_UNTERMINATED)
    assert doc.metadata.frontmatter_raw == ""
    assert any(b.kind == RULE for b in doc.blocks)
    assert any("thematic break" in b.text for b in doc.blocks)


def test_frontmatter_line_numbers_stay_aligned_with_the_original_source():
    """Blanking rather than deleting the frontmatter is what keeps every
    `token.map` -- and therefore `leftover_source` -- indexing real lines."""
    doc = parse_markdown(fixtures.FRONTMATTER)
    heading = doc.blocks[0]
    assert doc.source_lines[heading.source[0]] == "# Real heading"


def test_frontmatter_dict_is_documented_as_not_yaml():
    doc = parse_markdown(fixtures.FRONTMATTER)
    # A real YAML parse would give a list; the flat scan gives the literal.
    assert doc.metadata.frontmatter["tags"] == "[halo, round]"
    assert "aliases" in doc.metadata.frontmatter
    assert "chords" in doc.metadata.frontmatter_raw


def test_setext_headings_are_headings():
    doc = parse_markdown(fixtures.SETEXT)
    levels = [b.level for b in doc.blocks if b.kind == HEADING]
    assert levels == [1, 2]


def test_emphasis_markup_drops_but_text_survives():
    """`Font` has no style axis, so there is no emphasis to collapse *to*. The
    markup goes and the text stays -- including the `_` in an identifier, which
    a regex-based stripper would eat."""
    text = " ".join(p.text() for p in pages(fixtures.EMPHASIS))
    assert "*" not in text and "~~" not in text
    assert "bold" in text and "italic" in text and "both" in text
    assert "struck" in text
    assert "snake_case_name" in text, "underscores inside an identifier lost"
    assert squash("amidword") in squash(text)


def test_inline_code_keeps_text_drops_backticks():
    text = " ".join(p.text() for p in pages(fixtures.WIKILINKS))
    assert "`" not in text
    assert "literal in code" in text


def test_wikilinks_render_display_text_and_retain_targets():
    doc = parse_markdown(fixtures.WIKILINKS)
    by_target = {w.target: w for w in doc.metadata.wikilinks}
    assert by_target["Geometry"].display == "Geometry"
    assert by_target["Typography"].display == "the type note"
    assert by_target["Notes#Chord section"].display == "Chord section"
    assert by_target["Diagram.png"].embed is True


def test_wikilink_inside_a_code_span_is_not_a_wikilink():
    """Falls out of using a real parser: code spans are their own token, so the
    wikilink pass never sees them. A regex-only implementation gets this wrong.
    """
    targets = {w.target for w in parse_markdown(fixtures.WIKILINKS).metadata.wikilinks}
    assert "literal in code" not in targets


def test_footnote_definitions_reach_metadata_not_the_glass():
    doc = parse_markdown(fixtures.FOOTNOTES)
    assert doc.metadata.footnotes["src"].startswith("Read from brilliant-msg")
    assert doc.metadata.footnotes["2"].startswith("Measured at 13px")
    text = " ".join(p.text() for p in pages(fixtures.FOOTNOTES))
    assert "[^" not in text and "brilliant-msg" not in text


def test_html_blocks_are_opaque_and_scripts_never_render():
    text = " ".join(p.text() for p in pages(fixtures.HTML_AND_COMMENTS))
    assert "alert" not in text and "<div" not in text and "script" not in text
    kinds = {d.kind for d in parse_markdown(fixtures.HTML_AND_COMMENTS).metadata.dropped}
    assert "html" in kinds and "comment" in kinds
    assert "Visible text." in text


def test_images_drop_but_alt_and_target_are_recorded():
    doc = parse_markdown(fixtures.IMAGES)
    img = [d for d in doc.metadata.dropped if d.kind == "image"]
    assert len(img) == 1
    assert "A diagram of the chord solver" in img[0].detail
    assert "assets/chord.png" in img[0].detail
    assert "Text after the image." in pages(fixtures.IMAGES)[0].text()


def test_opaque_fences_drop_with_their_body_in_metadata():
    doc = parse_markdown(fixtures.DATAVIEW)
    op = [d for d in doc.metadata.dropped if d.kind == "opaque-fence"]
    assert len(op) == 1 and op[0].detail.startswith("dataview:")
    text = " ".join(p.text() for p in pages(fixtures.DATAVIEW))
    assert "SORT" not in text
    assert "Before the block." in text and "After the block." in text


def test_task_state_is_preserved_as_a_glyph():
    doc = parse_markdown(fixtures.TASKS)
    marks = [b.prefix for b in doc.blocks if b.kind == LIST]
    assert marks[:3] == ["[ ] ", "[x] ", "[x] "]
    assert marks[4:] == ["1. ", "2. "], "ordered list numbering lost"


def test_list_depth_becomes_indent_and_is_capped_not_dropped():
    doc = parse_markdown(fixtures.DEEP_LIST)
    assert [b.level for b in doc.blocks] == [0, 1, 2, 3, 4]
    text = " ".join(p.text() for p in pages(fixtures.DEEP_LIST))
    assert "five" in text, "text past the depth cap was dropped"

    # Indent is measured against each line's own chord, because the chord left
    # edge moves with y -- comparing raw x would test the circle, not the
    # indent. Depth grows to the cap and then stops; it never regresses.
    policy = Policy()
    offsets = []
    for lay in pages(fixtures.DEEP_LIST):
        for line in lay.lines:
            if line.kind != LIST:
                continue
            # The layout band is line_height tall, not ascent+descent. Using
            # the ink extent here would compute a different chord and put the
            # reference off by a pixel.
            y0 = line.run.baseline - F13.ascent
            offsets.append(line.run.x - HALO.line_left(y0, y0 + F13.line_height))
    assert len(offsets) == 5
    assert offsets == sorted(offsets), offsets
    assert offsets[3] == offsets[4] == policy.max_list_depth * policy.indent_px
    assert offsets[0] == 0


def test_callouts_collapse_to_a_prefixed_lead_line():
    doc = parse_markdown(fixtures.NESTED_CALLOUTS)
    quotes = [b for b in doc.blocks if b.kind == QUOTE]
    assert quotes[0].prefix == "WARNING: "
    assert quotes[0].text == "Outer warning"
    assert any(b.prefix == "NOTE: " for b in quotes)
    text = " ".join(p.text() for p in pages(fixtures.NESTED_CALLOUTS))
    assert "[!WARNING]" not in text
    assert squash("past the depth cap") in squash(text)


def test_hard_breaks_are_honoured_soft_breaks_are_not():
    lay = pages(fixtures.HARD_BREAKS)[0]
    texts = [l.run.text for l in lay.lines]
    assert texts[0].startswith("First line.")
    assert any(t.startswith("Second line") for t in texts)


# --- tables -----------------------------------------------------------------


def test_wide_table_renders_as_records_and_loses_no_cell():
    """`key: value` is lossless only at two columns. A four-column table under
    that policy silently discards columns three and four."""
    text = " ".join(p.text() for p in pages(fixtures.TABLE_WIDE))
    for cell in ("tables", "records", "N lines", "lossless",
                 "code", "sub-viewport", "none", "no reflow"):
        assert cell in text, f"cell {cell!r} dropped"
    for header in ("element", "treatment", "cost", "note"):
        assert header in text


def test_table_reformatting_is_declared_in_metadata():
    meta = parse_markdown(fixtures.TABLE_WIDE).metadata
    assert any("rendered as" in r for r in meta.reformatted)


def test_ragged_table_row_reports_the_cell_gfm_throws_away():
    """GFM truncates a row to the header count inside the parser, so the third
    cell never reaches our token stream. It cannot be rendered, but rule 4 says
    it cannot vanish either -- so it is counted in the source and named."""
    doc = parse_markdown(fixtures.TABLE_HEADERLESS_RAGGED)
    lost = [d for d in doc.metadata.dropped if d.kind == "table-cell"]
    assert lost and "3" in lost[0].detail
    text = " ".join(p.text() for p in pages(fixtures.TABLE_HEADERLESS_RAGGED))
    assert "a: 1" in text and "b: 2" in text


def test_omit_policy_states_the_omission_and_records_the_shape():
    p = Policy(table="omit")
    doc = parse_markdown(fixtures.TABLE_WIDE, p)
    assert any(d.kind == "table" for d in doc.metadata.dropped)
    text = layout_markdown(fixtures.TABLE_WIDE, HALO, F13, policy=p).text()
    assert "table omitted" in text


# --- URLs -------------------------------------------------------------------


def test_long_bare_url_is_elided_and_the_full_target_kept():
    doc = parse_markdown(fixtures.LONG_URL)
    link = doc.metadata.links[0]
    assert link.elided and link.href.startswith("https://example.com/segment/")
    assert "segment/" * 24 in link.href
    text = " ".join(p.text() for p in pages(fixtures.LONG_URL))
    assert "example.com" in text
    assert "segment/segment" not in text, "unelided URL ate the display"
    assert "trailing prose" in text


def test_short_url_is_left_alone():
    doc = parse_markdown("See https://x.example/a here.")
    assert doc.metadata.links[0].elided is False
    assert "https://x.example/a" in layout_markdown(
        "See https://x.example/a here.", HALO, F13
    ).text()


# --- geometry invariants ----------------------------------------------------


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_no_line_ever_leaves_the_circle(name):
    """The core invariant the whole package exists to hold. Applied to every
    fixture, at several sizes, on every page."""
    for size in (11, 13, 16):
        font = Font(FONT, size)
        for lay in pages(fixtures.ALL[name], font=font):
            for line in lay.lines:
                y0 = line.run.baseline - line.font.ascent
                y1 = line.run.baseline + line.font.descent
                left = HALO.line_left(y0, y1)
                assert line.run.x >= left - 1, (name, size, line.run.text)
                assert (
                    line.run.x + line.run.width
                    <= left + HALO.line_width(y0, y1) + 1
                ), (name, size, line.run.text)


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_baselines_sit_on_one_shared_grid(name):
    """Blocks of different kinds must not drift relative to each other; a page
    is one grid, not a stack of independently centred layouts."""
    for lay in pages(fixtures.ALL[name]):
        ys = sorted({l.run.baseline for l in lay.lines})
        deltas = {b - a for a, b in zip(ys, ys[1:])}
        assert all(d % F13.line_height == 0 for d in deltas), (name, sorted(deltas))


def test_usable_lines_is_stricter_than_max_feasible_lines():
    """`Font.max_feasible_lines` accepts any line >= 24px -- about four
    characters -- which is unusable once a block also carries an indent."""
    assert usable_lines(F13, HALO) < F13.max_feasible_lines(HALO)
    lines = usable_lines(F13, HALO)
    y0 = HALO.widest_band(F13.line_height, lines)
    widths = [
        HALO.line_width(y0 + i * F13.line_height, y0 + (i + 1) * F13.line_height)
        for i in range(lines)
    ]
    assert min(widths) >= Policy().min_line_width


def test_code_block_shares_one_left_edge():
    """Per-line chords would give left-aligned code a ragged left edge. The
    sub-viewport is what makes a code block readable on a circle."""
    for lay in pages(fixtures.CODE_LONG_LINES):
        xs = {l.run.x for l in lay.lines if l.kind == CODE}
        assert len(xs) <= 1, f"code block has {len(xs)} distinct left edges"


def test_code_is_never_reflowed_into_prose():
    text = "\n".join(
        l.run.text for lay in pages(fixtures.CODE_LONG_LINES) for l in lay.lines
        if l.kind == CODE
    )
    assert "def half_chord" in text
    # A reflow would let the def line and the return line share a rendered line.
    assert not any(
        "def half_chord" in ln and "return" in ln for ln in text.split("\n")
    )


# --- rule 4: nothing vanishes ------------------------------------------------


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_every_page_is_reachable_and_pagination_terminates(name):
    ps = pages(fixtures.ALL[name])
    assert ps and not ps[-1].has_more
    assert all(p.has_more for p in ps[:-1])


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_leftover_is_empty_exactly_when_there_is_no_more(name):
    for lay in pages(fixtures.ALL[name]):
        assert bool(lay.leftover_source) == lay.has_more
        assert lay.leftover is lay.leftover_source
        assert lay.truncated == lay.has_more


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_every_parsed_block_reaches_the_glass_across_pages(name):
    """Paging must not skip a block. Every block's text has to turn up
    somewhere in the union of pages."""
    src = fixtures.ALL[name]
    shown = squash("".join(p.text() for p in pages(src)))
    for block in parse_markdown(src).blocks:
        body = squash(block.text + "".join(block.lines))
        if len(body) < 4:
            continue
        assert body in shown, f"{name}: block {block.kind} {block.text[:40]!r} vanished"


@pytest.mark.parametrize("name", sorted(fixtures.ALL))
def test_nothing_is_dropped_without_appearing_in_metadata(name):
    """The corpus-level contract, and the reason the corpus exists: for every
    fixture, every word of source ends up on the glass, in leftover, or named
    in metadata. Never nowhere."""
    src = fixtures.ALL[name]
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
    for w in words(src):
        if len(w) < 4 or w.isdigit():
            continue
        assert squash(w) in accounted, (
            f"{name}: {w!r} is in the source but neither rendered nor in metadata"
        )


def test_long_word_is_broken_and_fully_conserved():
    src = fixtures.LONG_WORD
    body = "".join(
        l.run.text for p in pages(src) for l in p.lines
    ).replace("-", "").replace(" ", "")
    assert body.count("z") == 200, f"expected 200 z, got {body.count('z')}"
    assert "Prefix" in " ".join(p.text() for p in pages(src))
    assert "suffix" in " ".join(p.text() for p in pages(src))


def test_cjk_is_conserved_even_though_the_breaks_are_wrong():
    """No shaping and no dictionary breaking, so a spaceless run is hyphen-
    broken -- wrong for the script, but conserved, and the limitation is
    documented rather than silently mangling the text."""
    src = fixtures.CJK
    shown = "".join(l.run.text for p in pages(src) for l in p.lines)
    stripped = shown.replace("-", "").replace(" ", "").replace("▸", "")
    for ch in "近眼ディスプレイの可読性は行の垂直位置に依存します":
        assert ch in stripped, f"CJK character {ch!r} dropped"


def test_glyphs_the_face_cannot_draw_are_reported_not_silently_blank():
    """PIL renders a missing glyph as an invisible .notdef and raises nothing,
    so a character the face lacks would otherwise vanish without a trace."""
    lay = layout_markdown(fixtures.EMOJI, HALO, F13)
    assert has_glyph(F13, "A") and has_glyph(F13, " ")
    assert not has_glyph(F13, ""), "private-use probe should be missing"
    shown = "".join(l.run.text for l in lay.lines)
    for ch in shown:
        assert has_glyph(F13, ch) or ch in lay.metadata.unrenderable, (
            f"{ch!r} is unrenderable but not reported"
        )


# --- pagination purity -------------------------------------------------------


def test_pagination_is_a_pure_function_of_its_inputs():
    src = fixtures.EVERYTHING
    for p in range(4):
        a = layout_markdown(src, HALO, F13, page=p)
        b = layout_markdown(src, HALO, F13, page=p)
        assert a.text() == b.text()
        assert [l.run.x for l in a.lines] == [l.run.x for l in b.lines]


def test_no_hidden_cursor_pages_can_be_requested_out_of_order():
    src = fixtures.EVERYTHING
    forward = [layout_markdown(src, HALO, F13, page=p).text() for p in range(4)]
    backward = [layout_markdown(src, HALO, F13, page=p).text() for p in (3, 2, 1, 0)]
    assert forward == backward[::-1]


def test_leftover_source_re_paginates_to_the_same_continuation():
    """`leftover_source` is a continuation a caller can hand back in, which is
    the property that lets it own no parse state."""
    src = fixtures.EVERYTHING
    lay = layout_markdown(src, HALO, F13, page=0)
    assert lay.has_more
    direct = layout_markdown(src, HALO, F13, page=1).text()
    resumed = layout_markdown(lay.leftover_source, HALO, F13, page=0).text()
    assert resumed == direct


def test_pages_past_the_end_are_empty_not_an_error():
    lay = layout_markdown("Short note.", HALO, F13, page=7)
    assert lay.lines == () and not lay.has_more and lay.leftover_source == ""


def test_negative_page_is_loud():
    with pytest.raises(ValueError):
        layout_markdown("x", HALO, F13, page=-1)


# --- API shape ---------------------------------------------------------------


def test_markdown_layout_is_structurally_compatible_with_layout():
    """`render.render_text`'s blit loop reads `.runs`; keeping the shape means
    the existing drawing path works on a markdown page unchanged."""
    lay = layout_markdown(fixtures.EVERYTHING, HALO, F13)
    assert len(lay.runs) == len(lay.lines) == len(lay)
    assert lay[0] is lay.lines[0].run
    assert list(iter(lay)) == list(lay.runs)
    assert isinstance(lay, MarkdownLayout)


def test_parse_is_independent_of_font_and_display():
    a = parse_markdown(fixtures.EVERYTHING)
    b = parse_markdown(fixtures.EVERYTHING)
    assert a.blocks == b.blocks
    assert isinstance(a.blocks[0], Block)
    # Same doc laid out against two different panels.
    small = CircularDisplay(diameter=160, safe_inset=6)
    assert layout_markdown(a, small, F13).text() != layout_markdown(a, HALO, F13).text()


def test_emphasis_font_taller_than_the_body_face_is_rejected():
    """The page shares one baseline grid; a taller face would overrun its slot
    with no error, which is exactly the class of failure rule 5 rejects."""
    with pytest.raises(ValueError, match="baseline grid"):
        layout_markdown("# H", HALO, F13, emphasis_font=Font(FONT, 30))


def test_emphasis_font_replaces_the_heading_prefix():
    lay = layout_markdown("# Title\n\nBody.", HALO, F13)
    assert lay.lines[0].run.text.startswith(Policy().heading_prefix[0])
    emph = Font(FONT, 13)
    lay2 = layout_markdown("# Title\n\nBody.", HALO, F13, emphasis_font=emph)
    assert lay2.lines[0].run.text == "Title"
    assert lay2.lines[0].font is emph


def test_render_markdown_draws_and_leaves_all_ink_inside_the_circle():
    import math

    surf = PILSurface(256, 256, ramp_palette(4))
    lay = render_markdown(surf, fixtures.EVERYTHING, F13, HALO, levels=4)
    assert lay.lines and surf.ops
    img = surf.to_rgb()
    for y in range(256):
        for x in range(256):
            if img.getpixel((x, y)) != (0, 0, 0):
                assert math.hypot(x - 128, y - 128) <= HALO.usable_radius + 1.5, (x, y)


def test_marker_glyphs_fall_back_when_the_face_lacks_them():
    """A checkbox chosen without a coverage check disappears on any face that
    does not have it -- silently, because PIL draws .notdef and raises nothing.
    """
    policy = Policy(bullet=(" ", "- "), heading_prefix=(" ", "* "))
    lay = layout_markdown("# H\n\n- item", HALO, F13, policy=policy)
    text = lay.text()
    assert "" not in text and "" not in text
    assert text.startswith("* H")
    assert "- item" in text


# --- regressions -------------------------------------------------------------


def test_footnote_definition_is_not_mangled_into_a_stray_colon():
    """REGRESSION: `_scrub` stripped `[^1]` as a reference before the
    definition test ran, so `[^1]: body` reached the glass as ": body" and the
    definition never reached metadata. The test must run on raw content."""
    doc = parse_markdown(fixtures.FOOTNOTES)
    assert doc.metadata.footnotes, "definition never reached metadata"
    text = " ".join(p.text() for p in pages(fixtures.FOOTNOTES))
    assert not any(ln.strip().startswith(":") for ln in text.split("\n"))


def test_page_boundary_neither_duplicates_nor_skips_a_block():
    """REGRESSION: `_Page.next_block` conflated 'first unstarted block' with
    'the block that split', so a block straddling a page boundary could be
    rendered twice or skipped entirely."""
    src = "\n\n".join(f"Paragraph number {i} with several words in it." for i in range(14))
    seen = [l.run.text for p in pages(src) for l in p.lines]
    joined = " ".join(seen)
    for i in range(14):
        assert joined.count(f"number {i} ") == 1, (i, joined)


def test_code_split_across_pages_resumes_mid_line_exactly():
    """REGRESSION: the code path counted rendered fragments rather than source
    characters, so a line broken at a page boundary lost the piece that
    straddled it."""
    src = "```\n" + "\n".join(f"line_{i} = " + "x" * 40 for i in range(9)) + "\n```"
    shown = "".join(
        l.run.text for p in pages(src) for l in p.lines if l.kind == CODE
    )
    stripped = shown.replace("↳", "").replace("\\", "").replace(" ", "")
    for i in range(9):
        assert f"line_{i}=" in stripped, f"line_{i} lost across the page break"
        assert stripped.count(f"line_{i}=") == 1
    assert stripped.count("x") == 9 * 40


def test_hanging_indent_does_not_starve_a_long_callout_label():
    """REGRESSION: hanging indent was the full prefix advance, so a "WARNING: "
    label pushed every continuation line ~60px right -- a quarter of the
    equator chord -- on a panel that has ~33 characters to begin with."""
    lay = layout_markdown(fixtures.LONG_CALLOUT_TITLE, HALO, F13)
    quote = [l for l in lay.lines if l.kind == QUOTE]
    assert quote and quote[0].run.text.startswith("WARNING:")
    policy = Policy()
    conts = quote[1:]
    assert conts, "fixture no longer wraps; the cap would go untested"
    for c in conts:
        y0, y1 = c.run.baseline - F13.ascent, c.run.baseline + F13.descent
        indent = min(c.level, policy.max_list_depth) * policy.indent_px
        offset = c.run.x - HALO.line_left(y0, y1) - indent
        assert offset <= policy.hang_max_px + 1, (c.run.text, offset)


def test_short_final_page_is_centred_on_the_equator():
    """A three-line note must sit on the equator, not at the top of a
    ten-line grid."""
    lay = layout_markdown("A short note that wraps to two or three lines only.",
                          HALO, F13)
    assert not lay.has_more
    ys = [l.run.baseline - F13.ascent for l in lay.lines]
    block_mid = (ys[0] + ys[-1] + F13.line_height) / 2
    assert abs(block_mid - HALO.radius) <= F13.line_height


def _split_list_source():
    """A list whose last item is long enough to straddle a page boundary."""
    return (
        "\n".join(f"- short item {i}" for i in range(6))
        + "\n- "
        + " ".join(["continuation"] * 40)
        + "\n"
    )


def test_split_list_item_keeps_its_bullet_on_the_next_page():
    """REGRESSION: a list item split across a page dropped its prefix from the
    remainder, so the continuation rendered as unmarked text. On a HUD there is
    no scrollback -- the reader arriving at page 2 has no memory of page 1, so
    each page has to stand alone. Found against a real note; the invented
    fixtures never split a list item."""
    src = _split_list_source()
    ps = pages(src)
    assert len(ps) > 1, "fixture no longer splits; the regression would go untested"
    tail = [l for l in ps[1].lines if l.kind == LIST]
    assert tail, "no list lines on the continuation page"
    bullet = Policy().bullet[0]
    assert tail[0].run.text.startswith(bullet), tail[0].run.text


def test_leftover_of_a_split_list_item_round_trips_exactly():
    """REGRESSION: `_resynth` reused the *rendered* marker, so a split bullet
    came back as the literal "• text" -- which re-parses as a paragraph, not a
    list item, silently changing the block kind on the resumed page."""
    src = _split_list_source()
    first = layout_markdown(src, HALO, F13, page=0)
    assert first.has_more
    assert (
        layout_markdown(first.leftover_source, HALO, F13, page=0).text()
        == layout_markdown(src, HALO, F13, page=1).text()
    )


@pytest.mark.parametrize(
    "line,kind,prefix",
    [
        ("- plain bullet", LIST, "• "),
        ("- [ ] a task", LIST, "[ ] "),
        ("- [x] done task", LIST, "[x] "),
        ("3. ordered item", LIST, "3. "),
        ("> [!WARNING] a callout", QUOTE, "WARNING: "),
        ("> a plain quote", QUOTE, "│ "),
    ],
)
def test_resynth_markers_reparse_to_the_same_block(line, kind, prefix):
    """Every marker `_resynth` can emit must survive a parse round trip."""
    block = parse_markdown(line).blocks[0]
    assert (block.kind, block.prefix) == (kind, prefix)
    again = parse_markdown(_resynth(block, Policy())).blocks[0]
    assert (again.kind, again.prefix, again.text) == (kind, prefix, block.text)


def test_callout_body_carries_the_quote_marker():
    """There is no markdown for "blockquote continuation with no marker", so a
    bare callout body could not round-trip -- it came back as a centred
    paragraph. It carries the quote bar instead, which also ties it visually to
    its label."""
    blocks = parse_markdown("> [!NOTE] Title\n> The body line.").blocks
    assert [b.prefix for b in blocks] == ["NOTE: ", Policy().quote_prefix[0]]
    assert [b.kind for b in blocks] == [QUOTE, QUOTE]


def test_oversized_request_never_returns_a_blank_page():
    """The blank-screen failure typography.py already fixed, re-pinned at the
    markdown layer where `max_lines` is also caller-supplied."""
    for size in (11, 16, 24, 40):
        font = Font(FONT, size)
        for ml in range(1, 12):
            lay = layout_markdown(fixtures.EVERYTHING, HALO, font, max_lines=ml)
            assert lay.lines, (size, ml)
