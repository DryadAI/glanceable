"""Top-level convenience: text -> laid-out, rasterized, composited."""

from __future__ import annotations

from .geometry import CircularDisplay
from .surface import Surface
from .typography import Font, Layout

HALO = CircularDisplay(diameter=256, safe_inset=8)


def render_text(
    surface: Surface,
    font: Font,
    text: str,
    display: CircularDisplay = HALO,
    max_lines: int = 5,
    levels: int = 4,
    palette_base: int = 0,
) -> "Layout":
    """Lay out and draw `text`. Returns the Layout, whose `.truncated` flag and
    `.leftover` text let the caller paginate rather than silently cut off."""
    layout = font.layout(text, display, max_lines=max_lines)
    for run in layout.runs:
        cov = font.rasterize(run, levels)
        surface.blit_coverage(cov, run.x, run.baseline - font.ascent, palette_base, levels)
    surface.present()
    return layout
