"""The `Surface` ABC against a panel with no palette.

ROADMAP item 1 wants independent evidence that the three verbs are right.
`xg-glass-sdk` cannot give it -- its display API is `display(text)` and
`displayImage(png_bytes)`, whole frames rather than draw ops, so a backend for
it would exercise none of the op-level design.

A 1-bit panel does give it, from a direction no Brilliant device could: two of
`blit_coverage`'s five parameters have no meaning when a pixel is simply lit or
unlit. These tests record what survived that and what did not.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from PIL import Image

from glanceable import HALO, Font, find_system_font, ramp_palette, render_text
from glanceable.mono import MonoSurface
from glanceable.retained import RetainedSurface
from glanceable.surface import Surface

FONT = find_system_font()
TEXT = "Cmaj7 to Fmaj7 then G7 resolving home"
MARKDOWN = "# Chart\n\nPlay **Cmaj7** then Fmaj7.\n\n- resolve to G7\n"


def test_mono_surface_satisfies_the_abc():
    assert isinstance(MonoSurface(64, 64), Surface)


def test_render_text_works_unmodified_on_a_palette_free_panel():
    """The load-bearing result: nothing above surface.py changed."""
    surface = MonoSurface(256, 256)
    layout = render_text(surface, Font(FONT, 13), TEXT, HALO, max_lines=5, levels=4)
    assert len(layout) > 0
    assert surface.ops


def test_markdown_works_unmodified_on_a_palette_free_panel():
    from glanceable.markdown import render_markdown

    surface = MonoSurface(256, 256)
    render_markdown(surface, MARKDOWN, Font(FONT, 13), HALO, levels=4)
    assert surface.ops


def test_chord_invariant_holds_on_a_third_backend():
    """No lit pixel outside the safe radius -- the golden invariant, which is
    the actual claim, checked on a backend it was not written against."""
    from glanceable.markdown import render_markdown

    surface = MonoSurface(256, 256)
    render_markdown(surface, MARKDOWN, Font(FONT, 13), HALO, levels=4)
    img = surface.to_rgb()
    for y in range(256):
        for x in range(256):
            if img.getpixel((x, y)) != (0, 0, 0):
                assert math.hypot(x - 128, y - 128) <= HALO.usable_radius + 1.5


def test_retained_surface_wraps_a_third_backend():
    """RetainedSurface knows nothing about any device, so it should compose
    with a backend written after it."""
    surface = MonoSurface(256, 256)
    retained = RetainedSurface(surface)
    font = Font(FONT, 13)

    render_text(retained, font, TEXT, HALO, max_lines=5, levels=4)
    assert surface.ops
    before = len(surface.ops)

    render_text(retained, font, TEXT, HALO, max_lines=5, levels=4)
    assert len(surface.ops) == before, "an identical frame must forward nothing"


def test_unhonourable_parameters_are_recorded_not_swallowed():
    """Hard rule 7: an ignored parameter is a shape of silent loss.

    `levels` describes ramp quantisation and `palette_base` names a palette;
    neither exists on a 1-bit panel. The ABC requires both, so the backend
    accepts them and says so.
    """
    surface = MonoSurface(64, 64)
    coverage = Image.new("L", (16, 8), 255)

    surface.blit_coverage(coverage, 0, 0, 0, 2)
    assert surface.discarded == [], "levels=2 is honourable on a 1-bit panel"

    surface.blit_coverage(coverage, 0, 0, 4, 4)
    assert any("levels=4" in d for d in surface.discarded)
    assert any("palette_base=4" in d for d in surface.discarded)


def test_palette_parameters_fail_on_two_unrelated_backends():
    """Second independent line of evidence that the colour parameters are
    misplaced in the ABC.

    `SpriteSurface` raises on a non-zero base because the index cannot survive
    bit-depth masking on pack. `MonoSurface` cannot honour it because there is
    no palette. Different devices, different failures, same cause: Halo's
    colour model leaked into a signature that is otherwise general.
    """
    import pytest

    from glanceable import SpriteSurface

    coverage = Image.new("L", (16, 8), 255)

    with pytest.raises(ValueError, match="palette_base"):
        SpriteSurface(64, 64, ramp_palette(4)).blit_coverage(coverage, 0, 0, 4, 4)

    mono = MonoSurface(64, 64)
    mono.blit_coverage(coverage, 0, 0, 4, 4)
    assert any("palette_base" in d for d in mono.discarded)
