"""glanceable -- a layout and typography engine for round, glanceable displays."""

from .geometry import CircularDisplay
from .typography import Font, FontLoadError, GlyphRun, Layout, ramp_palette
from .surface import (
    Surface, PILSurface, SpriteSurface, SpriteOp, SpritePayload, SpriteCoords,
)
from .render import render_text, HALO
from .fonts import find_system_font

# glanceable.markdown is NOT imported here. It needs the optional `markdown`
# extra, and importing it eagerly would turn a missing optional dependency into
# an ImportError on `import glanceable`. Reach it as:
#     from glanceable.markdown import layout_markdown

__version__ = "0.2.0"
__all__ = [
    "CircularDisplay", "Font", "FontLoadError", "GlyphRun", "Layout", "ramp_palette",
    "Surface", "PILSurface", "SpriteSurface", "SpriteOp", "SpritePayload",
    "SpriteCoords", "render_text", "HALO",
    "find_system_font",
]
