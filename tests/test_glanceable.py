import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from PIL import Image

from glanceable import (
    HALO,
    CircularDisplay,
    Font,
    FontLoadError,
    PILSurface,
    SpriteSurface,
    find_system_font,
    ramp_palette,
    render_text,
)

FONT = find_system_font()
LOREM = (
    "Peripheral motion is detected pre-attentionally, so anything that "
    "moves out there hijacks attention whether or not it matters."
)


# --- geometry ---------------------------------------------------------------

def test_chord_is_widest_at_equator():
    d = CircularDisplay(256, safe_inset=8)
    assert d.half_chord(128) == pytest.approx(120.0)
    assert d.half_chord(28) < d.half_chord(128)
    assert d.half_chord(8) == 0.0


def test_chord_symmetric():
    d = CircularDisplay(256, safe_inset=8)
    for off in (10, 40, 90):
        assert d.half_chord(128 - off) == pytest.approx(d.half_chord(128 + off))


def test_line_width_uses_narrow_edge_not_midpoint():
    """The bug this whole module exists to prevent: using the midpoint chord
    overestimates the usable width for any line box not centered on the
    equator, and the overhang clips against the curve."""
    d = CircularDisplay(256, safe_inset=8)
    y_top, y_bot = 30, 50  # entirely in the upper hemisphere
    midpoint_width = int(2 * d.half_chord((y_top + y_bot) / 2))
    assert d.line_width(y_top, y_bot) < midpoint_width


def test_line_width_beyond_panel_is_zero():
    d = CircularDisplay(256, safe_inset=8)
    assert d.line_width(0, 4) == 0
    assert not d.fits(0, 4)


def test_centered_block_straddles_equator():
    d = CircularDisplay(256, safe_inset=8)
    y = d.widest_band(line_height=20, n_lines=4)
    assert y < 128 < y + 80


# --- typography -------------------------------------------------------------

def test_font_load_failure_is_loud():
    """Stock TxTextSpriteBlock silently substitutes load_default() and ignores
    font_size. We raise instead."""
    with pytest.raises(FontLoadError):
        Font("/nonexistent/Nope.ttf", 14)


def test_metrics_are_stable_across_strings():
    f = Font(FONT, 14)
    assert f.ascent > 0 and f.descent >= 0
    assert f.line_height > f.ascent


def test_baselines_are_uniformly_spaced():
    """The stock path crops each line to its own ink bbox, so lines of
    differing ascender/descender content land at different offsets. Ours
    must be exactly line_height apart regardless of glyph content."""
    f = Font(FONT, 14)
    runs = f.layout(
        "acemn acemn Tphgy Tphgy acemn acemn Tphgy acemn Tphgy Tphgy acemn", HALO, max_lines=5
    )
    assert len(runs) >= 3
    deltas = {runs[i + 1].baseline - runs[i].baseline for i in range(len(runs) - 1)}
    assert deltas == {f.line_height}


def test_wrap_respects_narrowing_chord():
    """Lines near the poles must hold fewer pixels than lines at the equator."""
    f = Font(FONT, 13)
    runs = f.layout(LOREM, HALO, max_lines=5)
    assert len(runs) >= 4
    runs = runs.runs
    mid = min(range(len(runs)), key=lambda i: abs(runs[i].baseline - 128))
    assert runs[mid].width >= runs[0].width
    assert runs[mid].width >= runs[-1].width


def test_no_run_exceeds_its_chord():
    """The core invariant: nothing is ever drawn outside the circle."""
    for size in (11, 13, 16, 20):
        f = Font(FONT, size)
        for run in f.layout(LOREM, HALO, max_lines=6).runs:
            y0, y1 = run.baseline - f.ascent, run.baseline + f.descent
            assert run.x >= HALO.line_left(y0, y1) - 1
            assert run.x + run.width <= HALO.line_left(y0, y1) + HALO.line_width(y0, y1) + 1


def test_long_word_is_hyphenated_not_overflowed():
    f = Font(FONT, 16)
    runs = f.layout("Pneumonoultramicroscopicsilicovolcanoconiosis", HALO, max_lines=6).runs
    assert len(runs) > 1
    assert any(r.text.endswith("-") for r in runs)


def test_quantization_preserves_antialiasing():
    """Stock path thresholds at >127, collapsing coverage to 1 bit. With
    levels=4 we must see intermediate coverage values."""
    f = Font(FONT, 18)
    runs = f.layout("Sample", HALO, max_lines=1).runs
    cov = f.rasterize(runs[0], levels=4)
    values = set(cov.convert('L').tobytes())
    assert len(values) > 2, "expected intermediate coverage levels, got 1-bit"


# --- surface / golden -------------------------------------------------------

def test_pil_and_sprite_surfaces_receive_identical_ops():
    """The device boundary holds only if both backends get the same calls.
    The previous version of this test compared SpriteSurface against a
    recomputation that ignored the PIL surface entirely, so it could not have
    caught a divergence. Both op logs are now compared directly."""
    pal = ramp_palette(4)
    f = Font(FONT, 13)
    a, b = PILSurface(256, 256, pal), SpriteSurface(256, 256, pal)
    la = render_text(a, f, LOREM, levels=4)
    lb = render_text(b, f, LOREM, levels=4)
    assert len(la) == len(lb) > 0
    assert a.ops == [(o.x, o.y, o.width, o.height) for o in b.ops]


# --- regressions: bugs found in the v0.1 audit ------------------------------

def test_never_returns_blank_for_oversized_request():
    """BUG A: line_height * max_lines exceeding the panel pushed the probe
    origin off-glass, where every chord is zero-width, and layout returned []
    with no error. A dark HUD is the worst possible failure mode."""
    for size in range(9, 49, 3):
        f = Font(FONT, size)
        for ml in range(1, 9):
            assert len(f.layout(LOREM, HALO, max_lines=ml)) > 0, (size, ml)


def test_max_lines_clamped_to_what_fits():
    f = Font(FONT, 40)
    assert f.max_feasible_lines(HALO) < 6
    assert len(f.layout(LOREM, HALO, max_lines=6)) <= f.max_feasible_lines(HALO)


def test_text_is_conserved_never_dropped():
    """BUG B: when even two glyphs plus a hyphen exceeded the chord, `cut`
    fell to 1 and the remainder of the word was discarded silently."""
    src = "Pneumonoultramicroscopicsilicovolcanoconiosis"
    for size in (11, 16, 24, 40, 64):
        f = Font(FONT, size)
        lay = f.layout(src, HALO, max_lines=6)
        body = "".join(r.text[:-1] if r.text.endswith("-") else r.text for r in lay.runs)
        assert "".join((body + lay.leftover).split()) == src, size


def test_truncation_is_signalled_not_silent():
    f = Font(FONT, 40)
    lay = f.layout(LOREM * 3, HALO, max_lines=3)
    assert lay.truncated and lay.leftover
    short = Font(FONT, 12).layout("hello", HALO)
    assert not short.truncated and short.leftover == ""


def test_recentring_reaches_a_fixed_point():
    """BUG C: re-centring for N lines could itself change N, leaving the block
    centred for a count it no longer had."""
    for size in (11, 12, 13, 14, 16, 18, 20, 24):
        f = Font(FONT, size)
        for n in (2, 3, 4, 5, 6):
            txt = " ".join(["word"] * (n * 4))
            lay = f.layout(txt, HALO, max_lines=n)
            if not lay.runs:
                continue
            expected = int(HALO.widest_band(f.line_height, len(lay.runs)))
            assert abs((lay.runs[0].baseline - f.ascent) - max(0, expected)) <= 1, (size, n)


def test_all_ink_inside_circle_golden():
    """Golden invariant, not a golden file: no lit pixel may fall outside the
    safe radius. This survives font upgrades, unlike an image checksum."""
    pal = ramp_palette(4)
    surf = PILSurface(256, 256, pal)
    f = Font(FONT, 13)
    render_text(surf, f, LOREM, levels=4)
    img = surf.to_rgb()
    r = HALO.usable_radius
    for y in range(256):
        for x in range(256):
            if img.getpixel((x, y)) != (0, 0, 0):
                assert math.hypot(x - 128, y - 128) <= r + 1.5, f"ink outside at {x},{y}"


def test_dirty_rects_cleared_on_present():
    surf = PILSurface(256, 256, ramp_palette(4))
    surf.fill_rect(10, 10, 20, 20, 3)
    assert surf.dirty
    surf.present()
    assert not surf.dirty
